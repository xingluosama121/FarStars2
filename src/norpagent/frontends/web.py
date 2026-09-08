# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Web frontend: HTTP + SSE interface (front.html multi-host frontend, zero dependencies).

Default frontend (used automatically when norpagent() is called without arguments):
- starts a zero-dependency HTTP service; the console prints the listening address;
- the browser opens http://127.0.0.1:<port>/ for the full chat interface
  (front.html: multi-tab sessions / streaming rendering / settings / plugin panel);
- tasks are submitted via /chat; events are pushed via SSE (event translation done
  by the in-page bridge).

Common parameters (np() keywords or config={"web": {...}}):
    port         port (default 8787)
    host         listen address (default 127.0.0.1)
    open_browser auto-open the browser (default False)
    language     UI language (default "en", e.g. "zh_CN")
    html         custom main page (slot mount parameter): a file path or HTML
                 content (starting with "<" after strip is treated as content,
                 otherwise as a file path; a nonexistent file makes the WebUI
                 constructor raise ValueError). Replaces the / route's default
                 front.html without physically overwriting library files. Four
                 ways to pass it:
                   1. constructor   WebFrontend(html="/path/to/my.html")
                   2. address clause np(frontend="norpagent.frontends.web:WebFrontend;html=/path/to/my.html")
                   3. config dict   np(config={"web": {"html": "<html>...</html>"}})
                   4. runtime param np(html="/path/to/my.html")
    flow_html     custom flow page (slot mount parameter): same four ways as above,
                  replaces the /flow route's default norp-flow.html.
    frontend slot direct HTML-path mount (v0.9):
                 np(frontend="/path/to/my.html") — when the slot value itself is an
                 existing .html/.htm file path, it auto-assembles as
                 WebFrontend(html=<that path>), equivalent to address-style mounting.

Hot page replacement at runtime (HTTP service not restarted; port unchanged):
    frontend.mount_page("front", html)   # replace the / route page
    frontend.mount_page("flow", html)    # replace the /flow route page
    frontend.mount_page("flow", None)    # unmount; fall back to the library built-in
Physically replacing the library's assets/front.html or assets/norp-flow.html
also takes effect automatically (page byte cache validated by file mtime/size).

Stopping: the page's "exit program" button, np.stop() lifecycle polling, or
np.shutdown() / engine request_stop().
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from norpagent.frontends.base import Frontend


class WebFrontend:
    """HTTP + SSE frontend shell (page = front.html)."""

    frontend_id = "web"

    def __init__(
        self,
        port: int = 8787,
        host: str = "127.0.0.1",
        open_browser: bool = False,
        html: Optional[str] = None,
        flow_html: Optional[str] = None,
        farstars_html: Optional[str] = None,
        sse_queue_size: Optional[int] = None,
        sse_queue_policy: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        # the architecture-layer factory may inject a config dict (e.g.
        # np(config={"web": {...}}) or the address clause
        # np(frontend="...:WebFrontend;html=..."))
        cfg = kwargs.get("config") or {}
        if isinstance(cfg, dict):
            port = cfg.get("port", port)
            host = cfg.get("host", host)
            open_browser = bool(cfg.get("open_browser", open_browser))
            html = cfg.get("html", html)
            flow_html = cfg.get("flow_html", flow_html)
            farstars_html = cfg.get("farstars_html", farstars_html)
            if sse_queue_size is None:
                sse_queue_size = cfg.get("sse_queue_size")
            if sse_queue_policy is None:
                sse_queue_policy = cfg.get("sse_queue_policy")
        self.port = int(port)
        self.host = str(host)
        self.open_browser = bool(open_browser)
        # SSE backpressure (high concurrency): None lets the WebUI use defaults / env vars
        self._sse_queue_size: Optional[int] = (
            int(sse_queue_size) if sse_queue_size is not None else None
        )
        self._sse_queue_policy: Optional[str] = sse_queue_policy
        # custom main page (None = library built-in front.html).
        # final resolution (content / file path) happens in the WebUI constructor:
        # a nonexistent file raises ValueError (fail fast) instead of silently
        # falling back to the default page.
        self._html: Optional[str] = html if html else None
        # custom flow page (None = library built-in norp-flow.html).
        self._flow_html: Optional[str] = flow_html if flow_html else None
        # custom farstars console page (None = library built-in norp-farstars.html).
        self._farstars_html: Optional[str] = farstars_html if farstars_html else None
        self._engine: Optional[Any] = None
        self._ui: Optional[Any] = None
        self._base_tools: List[str] = []  # snapshot of the preset's default tool set
        self._gate = threading.Lock()

    def attach(self, engine: Any) -> None:
        from norpagent.builtin.ui.web import WebUI

        self._engine = engine
        # snapshot of the preset's default tool set: fallback base when
        # agent_tools is not explicit. Must be captured before any _apply_config
        # (apply rewrites preset.tools).
        agent = engine.agent
        if agent is not None:
            preset = getattr(agent, "preset", None)
            if preset is not None:
                self._base_tools = list(getattr(preset, "tools", ()) or ())
        # runtime parameter passthrough (np(port=..., language=..., html=...) and other non-slot keys)
        params: Dict[str, Any] = dict(getattr(engine, "params", None) or {})
        self.port = int(params.get("port", self.port))
        self.host = str(params.get("host", self.host))
        if "open_browser" in params:
            self.open_browser = bool(params["open_browser"])
        # SSE backpressure runtime parameter passthrough (np(sse_queue_size=..., sse_queue_policy=...))
        if params.get("sse_queue_size") is not None:
            self._sse_queue_size = int(params["sse_queue_size"])
        if params.get("sse_queue_policy"):
            self._sse_queue_policy = str(params["sse_queue_policy"])
        language = str(params.get("language") or "en")
        # np(html=...) passthrough takes priority over constructor config (same as port/host).
        # an empty string counts as unspecified and falls back to the constructor value.
        if params.get("html"):
            self._html = str(params["html"])
        # np(flow_html=...) passthrough takes priority over constructor config (same as html).
        if params.get("flow_html"):
            self._flow_html = str(params["flow_html"])
        # np(farstars_html=...) passthrough takes priority over constructor config.
        if params.get("farstars_html"):
            self._farstars_html = str(params["farstars_html"])

        # safe mode: do not read the WebUI settings file (a bad config may be the
        # very cause of startup failure); keep only core fallback capabilities.
        # config_path="" = disable disk read/write (None uses the default path).
        config_path = "" if getattr(engine, "safe_mode", False) else \
            params.get("webui_config_path")
        self._ui = WebUI(
            port=self.port, host=self.host, language=language,
            html=self._html,
            flow_html=self._flow_html,
            farstars_html=self._farstars_html,
            sse_queue_size=self._sse_queue_size,
            sse_queue_policy=self._sse_queue_policy,
            config_path=config_path,
        )
        self._ui.set_handler(self._handle_task)
        self._ui.attach_runtime(engine.agent)
        self._ui.set_config_apply(self._apply_config)
        self._ui.set_recovery_handler(self._handle_recovery)
        self._ui.set_quit_callback(
            lambda: engine.request_stop()
        )
        self._ui.set_engine_state_fn(lambda: getattr(engine, "state", None).value)

        # point the agent runtime's ctx.ui at this instance: human approval /
        # clarification questions are then pushed to the browser over SSE
        # (otherwise they would land on the registered singleton WebUI and no one
        # would ever answer). Unsubscribe the old silent listener on replacement.
        agent = engine.agent
        if agent is not None:
            old_listener = getattr(agent, "_ui_listener", None)
            if old_listener is not None and old_listener is not self._ui.on_event:
                try:
                    engine._bus.unsubscribe(old_listener)
                except Exception:  # noqa: BLE001
                    pass
            agent.ui = self._ui
            agent._ui_listener = self._ui.on_event
            engine._bus.subscribe(self._ui.on_event)
        engine.subscribe_ui(self._ui)

        # restore the persisted agent tool set at startup (the agent_tools config saved last time)
        try:
            saved = self._ui.get_config()
            self._apply_agent_tools(saved or {})
        except Exception:  # noqa: BLE001 — restore failure must not block startup
            pass

    def reattach_agent(self, engine: Any) -> None:
        """Runtime hot mount: rebind the renderer and data sources after the AgentRuntime is rebuilt.

        Does not restart the HTTP service (port unchanged; pages stay connected);
        only points the UI's data sources at the new runtime and switches the
        human-approval / clarification interaction channel to the new runtime's
        renderer (ctx.ui).
        """
        self._engine = engine
        agent = getattr(engine, "agent", None)
        if agent is None or self._ui is None:
            return
        # rebind UI data sources (session REST / plugin list / debug info read from agent)
        self._ui.attach_runtime(agent)
        # ctx.ui points at this instance: approvals / questions pushed to the browser over SSE
        old_listener = getattr(agent, "_ui_listener", None)
        if old_listener is not None and old_listener is not self._ui.on_event:
            try:
                engine._bus.unsubscribe(old_listener)
            except Exception:  # noqa: BLE001
                pass
        agent.ui = self._ui
        agent._ui_listener = self._ui.on_event
        engine._bus.subscribe(self._ui.on_event)
        engine.subscribe_ui(self._ui)

    def mount_page(self, page: str, html: Optional[str] = None) -> bytes:
        """Hot-replace page bytes at runtime (HTTP service not restarted; port unchanged).

        - ``page``: "front" (/ route), "flow" (/flow route) or "farstars" (/farstars route);
        - ``html``: a file path or HTML content (starting with "<" after strip is
          treated as content, otherwise as a file path; a nonexistent file raises
          ValueError);
        - ``html=None``: unmount the mount; fall back to the library's built-in asset.

        When already attached, applies to the WebUI immediately (returns the new
        page bytes); when not attached, only updates the mount parameters, taking
        effect on attach. Keeps _html / _flow_html / _farstars_html consistent with
        the page's actual state (so a later frontend hot-swap via remount reuses them).
        """
        if page not in ("front", "flow", "farstars"):
            raise ValueError(
                f"mount_page only supports 'front' / 'flow' / 'farstars' pages, got {page!r}"
            )
        if page == "front":
            self._html = html
        elif page == "flow":
            self._flow_html = html
        else:
            self._farstars_html = html
        if self._ui is not None:
            return self._ui.mount_page(page, html)
        return b""

    def _handle_task(self, prompt_text: str, session_id: Optional[str],
                     task_params: Optional[Dict[str, Any]] = None) -> Any:
        # tasks run serially on the same runtime
        with self._gate:
            return self._engine.submit(
                prompt_text, session_id=session_id, task_params=task_params
            )

    def _apply_config(self, cfg: Dict[str, Any]) -> None:
        """Apply after the page saves config: mode / model / remote endpoint / API key / plugin dirs / security."""
        engine = self._engine
        if engine is None or cfg is None:
            return
        reg = engine.registry

        # ── mode: registry preset hot-switch (front "mode" selector) ──
        # remount(preset=...) hot-rebuilds the AgentRuntime (stop old sandbox →
        # build new runtime → frontend rebind), so it is skipped while a task is
        # running (gate held); it takes effect on the next config application or
        # restart; unchanged values are also skipped.
        # note: with slot overrides the assembly layer names derived presets
        # {base}_arch; comparisons use the base name so saving config does not
        # misjudge every time as a "mode change".
        preset_name = str(cfg.get("preset_name") or "")
        agent = engine.agent
        current_name = ""
        if agent is not None:
            preset = getattr(agent, "preset", None)
            raw = str(getattr(preset, "name", "") or "")
            current_name = raw[:-5] if raw.endswith("_arch") else raw
        if preset_name and preset_name != current_name:
            if not self._gate.locked():
                try:
                    engine.remount(preset=preset_name)
                except Exception:  # noqa: BLE001 — keep the current mode when the preset name is invalid
                    pass
                agent = engine.agent
                if agent is not None:
                    preset = getattr(agent, "preset", None)
                    if preset is not None:
                        # refresh the default tool-set snapshot after the preset
                        # hot-switch (the apply_agent_tools fallback base follows
                        # the new preset, not the old one's tool set)
                        self._base_tools = list(getattr(preset, "tools", ()) or ())

        # ── model: two semantics — registry adapter name / remote model name ──
        agent = engine.agent
        model = str(cfg.get("model") or "")
        api_base = str(cfg.get("api_base") or "") or None
        api_key = str(cfg.get("api_key") or "") or None

        if model in reg.list_models():
            if model in ("openai_compat", "anthropic"):
                try:
                    if model == "openai_compat":
                        from norpagent.builtin.models.openai_compat import OpenAICompatProvider

                        reg.register_model("openai_compat", OpenAICompatProvider(
                            model_name=None, base_url=api_base, api_key=api_key,
                        ))
                    else:
                        from norpagent.builtin.models.anthropic import AnthropicProvider

                        reg.register_model("anthropic", AnthropicProvider(
                            model_name=None, api_key=api_key,
                        ))
                except Exception:  # noqa: BLE001 — keep the original provider when parameters are incomplete
                    pass
            # other registered adapter names: nothing to do
        elif model:
            # remote model name: mount onto the openai_compat adapter
            try:
                from norpagent.builtin.models.openai_compat import OpenAICompatProvider

                reg.register_model("openai_compat", OpenAICompatProvider(
                    model_name=model, base_url=api_base, api_key=api_key,
                ))
            except Exception:  # noqa: BLE001
                pass
            model = "openai_compat"

        # make the runtime use the new model on the next run()
        if agent is not None and model:
            preset = getattr(agent, "preset", None)
            if preset is not None:
                try:
                    preset.model = model
                except Exception:  # noqa: BLE001
                    pass

        # ── agent tool set (file-as-module → front auto-invoked) ──
        self._apply_agent_tools(cfg)

        # ── NORP security: install when enabled (one call for the full security suite) ──
        if cfg.get("norp_safe_enabled") and getattr(reg, "security", None) is None:
            try:
                from norpagent import safe

                safe(reg, level="standard")
            except Exception:  # noqa: BLE001
                pass

        # ── plugin dirs: reinstall (signature→audit→import-restriction pipeline) ──
        dirs = cfg.get("plugin_dirs") or []
        if dirs:
            try:
                from norpagent.plugins import install_plugin_dirs

                install_plugin_dirs(reg, [str(d) for d in dirs], config={
                    "plugin_security_audit": cfg.get("plugin_security_audit") or "warn",
                    "plugin_signature_verify": True,
                })
            except Exception:  # noqa: BLE001
                pass

        # ── work rollback: a saved setting is a system change → auto snapshot ──
        try:
            from norpagent.recovery import notify_system_change

            notify_system_change(engine, description="WebUI settings saved")
        except Exception:  # noqa: BLE001
            pass

    def _handle_recovery(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Backend handler of the Web UI rollback panel (/api/snapshots goes here).

        action: list / capture / undo / redo / rollback / mark_good.
        Returns an error field when the engine is missing or the action is unknown,
        without raising exceptions that would break the HTTP server.
        """
        engine = self._engine
        try:
            from norpagent import recovery
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"recovery unavailable: {exc}"}
        if engine is None:
            return {"ok": False, "error": "engine not assembled"}
        try:
            if action == "list":
                items = recovery.list_snapshots()
                return {"ok": True, "items": items,
                        "current": recovery.store.current_id()
                        if hasattr(recovery, "store") else None,
                        "last_good": recovery.last_good_id()}
            if action == "capture":
                info = recovery.snapshot_system(
                    description=str(payload.get("description") or "manual snapshot"),
                    tag="manual", engine=engine)
                return {"ok": True, "snapshot": info}
            if action == "undo":
                return {"ok": True, "result": recovery.undo(engine)}
            if action == "redo":
                return {"ok": True, "result": recovery.redo(engine)}
            if action == "rollback":
                result = recovery.rollback(
                    snap_id=payload.get("id") or None, engine=engine)
                return {"ok": True, "result": result}
            if action == "mark_good":
                info = recovery.mark_good(payload.get("id") or None)
                return {"ok": True, "snapshot": info}
            if action == "delete":
                ok = recovery.delete_snapshot(payload.get("id") or None)
                if not ok:
                    return {"ok": False, "error": "snapshot not found"}
                return {"ok": True, "deleted": payload.get("id")}
            if action == "rename":
                info = recovery.rename_snapshot(
                    str(payload.get("id") or ""),
                    str(payload.get("description") or ""))
                if info is None:
                    return {"ok": False, "error": "snapshot not found"}
                return {"ok": True, "snapshot": info}
            return {"ok": False, "error": f"unknown action: {action}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def _apply_agent_tools(self, cfg: Dict[str, Any]) -> None:
        """Hot-apply the agent tool set from config to the running agent.

        - ``agent_tools_explicit`` True: ``agent_tools`` is the exact tool set
          (unregistered tool names are filtered automatically; no errors after a
          module is unloaded);
        - otherwise fall back to the preset's default tool set (the
          ``self._base_tools`` snapshot).
        The next run() reads preset.tools to generate tool schemas, letting the
        model auto-invoke them (tool calling). Tools registered by file-as-module
        and native tools are mounted on equal footing here.
        """
        engine = self._engine
        if engine is None or not isinstance(cfg, dict):
            return
        agent = engine.agent
        if agent is None:
            return
        preset = getattr(agent, "preset", None)
        if preset is None:
            return
        try:
            registered = set(engine.registry.list_tools())
        except Exception:  # noqa: BLE001
            registered = set()
        if cfg.get("agent_tools_explicit"):
            preset.tools = [
                str(t) for t in (cfg.get("agent_tools") or [])
                if str(t) in registered
            ]
        else:
            preset.tools = list(self._base_tools)

    def start(self) -> None:
        if self._ui is not None:
            self._ui.start()
            self.port = int(self._ui.port)
            print(f"[norpagent] frontend web listening on {self.host}:{self.port}")
            self._print_lazy_modules()
            if self.open_browser:
                try:
                    import webbrowser

                    threading.Thread(
                        target=lambda: webbrowser.open(
                            f"http://{self.host}:{self.port}/"
                        ),
                        daemon=True,
                        name="norpagent-webui-browser",
                    ).start()
                except Exception:  # noqa: BLE001 — silent in headless environments
                    pass

    def stop(self) -> None:
        if self._ui is not None:
            try:
                self._ui.shutdown()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _print_lazy_modules() -> None:
        """Print the lazy-loaded modules of this process (diagnostics; silent in environments without packages)."""
        try:
            from norpagent.builtin import list_loaded_lazy_modules

            loaded = list_loaded_lazy_modules()
        except Exception:  # noqa: BLE001 — silent in environments without packages
            return
        if loaded:
            print("[norpagent] lazy-loaded modules: " + ", ".join(loaded))

    def is_alive(self) -> bool:
        return bool(self._ui is not None and getattr(self._ui, "_running", True))


__all__ = ["WebFrontend"]
