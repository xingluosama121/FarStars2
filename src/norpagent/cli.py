# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Command-line entry: norpagent.

Usage::

    norpagent --list-modes
    norpagent --mode minimal                       # interactive REPL
    norpagent --mode ptc --prompt "..."            # single task
    norpagent --mode-file my_mode.py               # creative mode: load a custom mode file
    norpagent --mode standard --ui web --port 8787 # web UI (HTTP + SSE)
    norpagent --mode standard --plugin-dir ./my_plugins   # load external plugins
    norpagent --safe-mode                                 # safe mode: load only the minimal kernel
    norpagent plugin-sign --gen                    # generate a plugin signing key pair
    norpagent plugin-sign my_plugin.py --key <private key hex>

Central Nervous Bus (CNB) subcommands (kernel-integrated since v1.0.7;
nervous_bus ships inside the PyPI package; equivalent to
`python -m nervous_bus.cli ...`)::

    norpagent cortex --port 17800 --repl                  # start the cortex (tree root)
    norpagent node --id norpbot-01 --kind bot --parent http://127.0.0.1:17800 --port 17801 --level 3
    norpagent topo --root http://127.0.0.1:17800          # show the neural tree
    norpagent ping|exec|stop|reload|perm|reports|audit|sync ...   # cortex control

Since v1.0.7 the cortex/node processes carry a full norpagent engine by
default (every atom is a real agent; --bare runs the plain nervous shell),
and the cortex can drive kernel-level actions (run_task / snapshot /
rollback / remount / reload_plugins / stop_engine / ...) via
`norpagent exec --node X --action <action> --args '<json>'`.

Legacy spellings `norpagent --norp-cortex ...` / `norpagent --norp-node ...`
(used by the repository-root `python main.py` entry) are forwarded to the same
subcommands automatically.

Crash rescue (roll back snapshots when the main program cannot start; an independent
pure-standard-library tool)::

    norpagent-rescue list
    norpagent-rescue rollback --last-good

Human rescue (model provider down -> drive the tools by hand)::

    norpagent-rescue tools
    norpagent-rescue tool-call echo --args '{"text": "ping"}'
    norpagent-rescue manual        # interactive manual tool console
    norpagent-rescue serve         # HTTP API + operator page (127.0.0.1:8799)

Model options supported since P2 (--model overrides the preset's default model).
"""

from __future__ import annotations

import argparse
import sys
import threading
from typing import List, Optional

from norpagent.builtin import install_defaults
from norpagent.kernel.agent import AgentRuntime
from norpagent.kernel.presets import load_preset_file
from norpagent.kernel.registry import Registry, ComponentError
from norpagent.modes import register_all_presets

# CNB subcommands dispatched to norpagent.cnb.cli (kernel-integrated v1.0.7;
# kept separate so the two argument parsers never clash: the CNB tree has its
# own cortex/node/topo/... grammar while the norpagent top level keeps
# mode/UI options).
_CNB_SUBCOMMANDS = frozenset({
    "cortex", "node", "topo", "ping", "exec", "stop",
    "reload", "perm", "reports", "audit", "sync",
    # v2.0.0：freeze/unfreeze（隔离冻结态）、subpoena 系（传票取证）、
    # behavior（行为基线分级）
    "freeze", "unfreeze",
    "subpoena", "subpoena_box", "subpoena_purge", "subpoena_audit",
    "behavior",
})


def _build_registry(args: Any) -> Registry:
    """Build the registry (built-in components + presets + security policy + external plugin dirs)."""
    reg = Registry()
    install_defaults(reg)
    register_all_presets(reg)
    # norpagent.safe(): one call to enable the full security suite (basic/standard/high)
    # default hooks zero-intervention: only runtime policies, no hooks; --safe-hooks explicitly mounts hooks.
    safe_level = getattr(args, "safe", None)
    if safe_level:
        from norpagent import safe

        kit = safe(reg, level=safe_level, hooks=bool(args.safe_hooks))
        mode = "hook intervention enabled" if args.safe_hooks else "zero hook intervention (runtime policies only)"
        print(f"[security] norpagent.safe() enabled (level: {safe_level}, {mode})")
        for key, val in kit.context.to_dict().items():
            print(f"       {key}={val}")
    # safe mode: skip all plugins (plugins are the most likely source of startup failures)
    if getattr(args, "safe_mode", False):
        print("[safe mode] loading only the minimal kernel: all plugin directories skipped")
        return reg
    plugin_dirs = list(getattr(args, "plugin_dir", None) or [])
    if plugin_dirs:
        from norpagent.plugins import install_plugin_dirs

        loader = install_plugin_dirs(reg, plugin_dirs, config={
            "plugin_security_audit": "warn",
            "plugin_security_import_restrict": "off",
            "plugin_signature_verify": True,
            "plugin_network_policy": "deny",
            "plugin_isolation": getattr(args, "plugin_isolation", "auto"),
        })
        for info in loader.plugins:
            mark = "OK " if info.enabled else "FAIL"
            print(f"[plugin] {mark} {info.name} v{info.version}"
                  f" (signature: {info.signature_status}, tools: {len(info.tools)})")
            if not info.enabled and info.error:
                print(f"       {info.error.splitlines()[0] if info.error else ''}")
    return reg


def _apply_model_options(reg: Registry, args: Any) -> None:
    """Re-register model instances per CLI options (overriding install_defaults' default instances)."""
    if args.model_name or args.base_url or args.api_key:
        from norpagent.builtin.models.openai_compat import OpenAICompatProvider

        reg.register_model(
            "openai_compat",
            OpenAICompatProvider(
                model_name=args.model_name or None,
                base_url=args.base_url or None,
                api_key=args.api_key or None,
            ),
        )
    if args.api_key or args.model_name:
        from norpagent.builtin.models.anthropic import AnthropicProvider

        reg.register_model(
            "anthropic",
            AnthropicProvider(
                model_name=args.model_name or None,
                api_key=args.api_key or None,
            ),
        )


def _list_modes(reg: Registry, stream=None) -> None:
    out = stream or sys.stdout
    out.write("built-in preset modes:\n")
    for name in reg.list_presets():
        p = reg.resolve_preset(name)
        out.write(f"  {p.name:<10} {p.description}\n")
        out.write(f"      model={p.model} tools={p.tools}\n")
        if p.components:
            out.write(f"      components={p.components}\n")


def _make_runtime(
    reg: Registry,
    mode: str,
    args: Any,
) -> AgentRuntime:
    from norpagent.kernel.presets import Preset

    preset = reg.resolve_preset(mode)
    model = getattr(args, "model", None)
    session = getattr(args, "session", None)
    ui_name = getattr(args, "ui", None) or preset.ui

    ui = None
    if ui_name == "web":
        from norpagent.builtin.ui.web import WebUI

        ui = WebUI(port=int(getattr(args, "port", None) or 8787))

    if model or session or ui is not None:
        preset = Preset(
            name=preset.name,
            description=preset.description,
            model=model or preset.model,
            tools=list(preset.tools),
            session=session or preset.session,
            sandbox=preset.sandbox,
            scheduler=preset.scheduler,
            ui=ui_name,
            mode=preset.mode,
            params=dict(preset.params),
            components=dict(preset.components),
        )
    return AgentRuntime(reg, preset, ui=ui)


def _run_web(reg: Registry, mode: str, args: Any, prompt: Optional[str]) -> int:
    """Web UI mode: start the HTTP + SSE service (front.html); tasks submitted via /chat."""
    from norpagent.builtin.ui.web import WebUI

    # safe mode: do not read the WebUI settings file (a bad config may be the very
    # cause of startup failure). config_path="" = disable disk read/write (None uses the default path).
    ui = WebUI(port=int(getattr(args, "port", None) or 8787),
               config_path="" if getattr(args, "safe_mode", False) else None)
    from norpagent.kernel.presets import Preset

    preset = reg.resolve_preset(mode)
    if getattr(args, "model", None) or getattr(args, "session", None):
        preset = Preset(
            name=preset.name, description=preset.description,
            model=getattr(args, "model") or preset.model,
            tools=list(preset.tools),
            session=getattr(args, "session") or preset.session,
            sandbox=preset.sandbox, scheduler=preset.scheduler, ui="web",
            mode=preset.mode, params=dict(preset.params),
            components=dict(preset.components),
        )
    agent = AgentRuntime(reg, preset, ui=ui)
    gate = threading.Lock()

    def handler(prompt_text: str, session_id: Optional[str],
                task_params: Optional[dict] = None):
        with gate:  # tasks run serially on the same runtime
            return agent.run(prompt_text, session_id=session_id,
                             task_params=task_params)

    ui.set_handler(handler)
    ui.attach_runtime(agent)
    ui.start()
    print(f"[norpagent] frontend web listening on 127.0.0.1:{ui.port} (/exit to quit)")
    try:
        from norpagent.builtin import list_loaded_lazy_modules

        lazy_loaded = list_loaded_lazy_modules()
        if lazy_loaded:
            print("[norpagent] lazy-loaded modules: " + ", ".join(lazy_loaded))
    except Exception:  # noqa: BLE001 — silent in environments without packages
        pass
    try:
        if prompt:
            task_id = ui.submit(prompt, None)
            print(f"[norpagent] task submitted: {task_id}")
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                break
            if line.strip() in ("/exit", "/quit", "quit", "exit"):
                break
    finally:
        ui.shutdown()
        agent.shutdown()
    return 0


def _run_once(reg: Registry, mode: str, args: Any) -> int:
    try:
        agent = _make_runtime(reg, mode, args)
    except ComponentError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    try:
        result = agent.run(args.prompt)
    finally:
        agent.shutdown()
    if not result.ok:
        print(f"\n[failure] {result.status}: {result.error}", file=sys.stderr)
        return 1
    return 0


def _repl(reg: Registry, mode: str, args: Any) -> int:
    try:
        agent = _make_runtime(reg, mode, args)
    except ComponentError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    print(f"norpagent interactive mode [{mode}]. Type /help for commands, /exit to quit.")
    session_id = None
    try:
        while True:
            try:
                line = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line in ("/exit", "/quit"):
                break
            if line == "/help":
                print("  /exit     quit\n  /modes    list preset modes\n  /tools    list available tools\n  /reset    start a new session")
                continue
            if line == "/modes":
                _list_modes(reg)
                continue
            if line == "/tools":
                print("available tools:", reg.list_tools())
                continue
            if line == "/reset":
                session_id = None
                print("new session started")
                continue
            result = agent.run(line, session_id=session_id)
            session_id = result.session_id
            if result.status == "error":
                print(f"[failure] {result.error}", file=sys.stderr)
    finally:
        agent.shutdown()
    return 0


def _plugin_sign_cmd(args: Any) -> int:
    from norpagent.security.signature import generate_keypair, sign_plugin_file

    if args.gen:
        pair = generate_keypair()
        if pair is None:
            print("[error] the cryptography library is required: pip install norpagent[security]",
                  file=sys.stderr)
            return 1
        pub, priv = pair
        print(f"PUBLIC_KEY = {pub}")
        print(f"PRIVATE_KEY = {priv}")
        print("\nAdd PUBLIC_KEY to config → plugin_trusted_keys; "
              "keep PRIVATE_KEY safe and never commit it to a repository.")
        return 0
    if not args.path or not args.key:
        print("[error] specify the plugin file and --key (or use --gen to generate keys)", file=sys.stderr)
        return 1
    try:
        block = sign_plugin_file(args.path, args.key)
        print(f"[OK] signed: {args.path} -> {args.path}.sig")
        print(f"     public_key = {block['public_key']}")
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    # ── 中枢神经总线（CNB）子命令转发 ──────────────────────────────
    # v1.0.7 起 CNB 内核集成：神经实现与引擎绑定层位于 norpagent.cnb 子模块
    # （旧独立包 nervous_bus 保留为兼容 shim）：
    #   norpagent cortex --port 17800 --repl
    #   norpagent node --id norpbot-01 --kind bot --parent ... --port 17801 --level 3
    #   norpagent topo|ping|exec|stop|reload|perm|reports|audit|sync ...
    # cortex/node 子命令默认装配完整内核引擎（每个原子是真实 norpagent 实例；
    # --bare 回到纯神经空壳探针）。
    # 兼容仓库源码旧写法 --norp-cortex / --norp-node（等价 python main.py 的 CNB 分支）。
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--norp-cortex" in argv or "--norp-node" in argv:
        _sub = "cortex" if "--norp-cortex" in argv else "node"
        argv = [_sub] + [a for a in argv
                         if a not in ("--norp-cortex", "--norp-node")]
    if argv and argv[0] in _CNB_SUBCOMMANDS:
        from norpagent.cnb.cli import main as _cnb_cli_main

        return _cnb_cli_main(argv)
    parser = argparse.ArgumentParser(
        prog="norpagent",
        description="norpagent Agent framework CLI",
        epilog=(
            "Central Nervous Bus (CNB) subcommands (kernel-integrated into "
            "norpagent.cnb since v1.0.7; cortex / node / topology control):\n"
            "  norpagent cortex --port 17800 [--repl]      start the brain cortex "
            "(tree root, level 0; controls atoms of any level)\n"
            "  norpagent node --id NAME --kind TYPE --parent http://127.0.0.1:17800 "
            "--port PORT --level N    mount an atom under the parent\n"
            "  norpagent topo|ping|exec|stop|reload|perm|reports|audit|sync ...   "
            "cortex control commands\n"
            "  v2.0.0 (FarStars): freeze|unfreeze (quarantine), behavior "
            "(baseline grading), subpoena|subpoena_box|subpoena_purge|"
            "subpoena_audit (evidence), exec actions incl. task_records "
            "(mol acceptance receipts)\n"
            "  legacy spellings still work: norpagent --norp-cortex ... / "
            "norpagent --norp-node ...\n"
            "  run 'norpagent <subcommand> --help' for the CNB grammar; ordinary "
            "GUI instances auto-mount via NORP_CNB_* env vars (see manual 30.8). "
            "cortex/node run a full engine by default (--bare = plain shell); "
            "exec actions include kernel-level snapshot/rollback/remount/... "
            "(see manual 30.15)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list-modes", action="store_true", help="list all preset modes")
    parser.add_argument("--mode", "-m", help="preset mode name (minimal/standard/ptc/creative or custom)")
    parser.add_argument("--mode-file", "-f", help="creative mode: load a custom mode from a .py file (module-level PRESET)")
    parser.add_argument("--prompt", "-p", help="single-task input (defaults to the interactive REPL)")
    parser.add_argument("--model", help="override the preset's default model (must be registered, e.g. mock/openai_compat/anthropic)")
    parser.add_argument("--model-name", help="remote model name (e.g. deepseek-v4-flash / claude-sonnet-4-5)")
    parser.add_argument("--base-url", help="OpenAI-compatible service endpoint (e.g. https://api.deepseek.com/v1)")
    parser.add_argument("--api-key", help="API key (defaults to the OPENAI_API_KEY / ANTHROPIC_API_KEY environment variables)")
    parser.add_argument("--session", help="session storage backend (memory/sqlite)")
    parser.add_argument("--call-timeout", type=float, default=None, help="hard timeout in seconds for a single model call (0=unlimited)")
    parser.add_argument("--ui", help="UI adapter override (console/web)")
    parser.add_argument("--port", type=int, default=None, help="web UI port (used with --ui web; default 8787)")
    parser.add_argument("--plugin-dir", action="append", default=None,
                        help="external plugin directory (repeatable; security pipeline: signature→audit→import restrictions)")
    parser.add_argument("--plugin-isolation", default="auto",
                        choices=["auto", "inproc", "process"],
                        help="plugin isolation mode (auto=per plugin ISOLATION declaration; process=force process-level isolation)")
    parser.add_argument("--safe", default=None, choices=["basic", "standard", "high"],
                        help="norpagent.safe() security level (runtime policies: approval/audit/signature; no hooks by default)")
    parser.add_argument("--safe-hooks", action="store_true",
                        help="with --safe: explicitly enable hook intervention (before_input jailbreak blocking + prompt hardening)")
    parser.add_argument("--safe-mode", action="store_true",
                        help="safe mode: load only the minimal kernel (skip all plugins, do not read WebUI settings), keeping core fallback capabilities")
    # plugin signing subcommand
    sub = parser.add_subparsers(dest="subcmd")
    psign = sub.add_parser("plugin-sign", help="plugin signing tool (NORP plugin signature protocol v1)")
    psign.add_argument("path", nargs="?", help="plugin entry file (.py)")
    psign.add_argument("--key", help="Ed25519 private key hex (for signing)")
    psign.add_argument("--gen", action="store_true", help="generate a signing key pair")

    args = parser.parse_args(argv)

    if args.subcmd == "plugin-sign":
        return _plugin_sign_cmd(args)

    # crash rescue: consume the rollback target left by the previous
    # norpagent-rescue run — file-level restore (WebUI settings / session files)
    # already ran; here the snapshot's CLI arguments are merged into this startup
    # (arguments explicitly given on the command line take priority).
    try:
        from norpagent.recovery import apply_pending_rollback_cli

        pending = apply_pending_rollback_cli()
    except Exception:  # noqa: BLE001
        pending = None
    if pending and isinstance(pending, dict):
        cli_part = pending.get("cli") or {}
        if cli_part.get("mode") and not args.mode and not args.mode_file:
            args.mode = cli_part["mode"]
        if cli_part.get("plugin_dir") and not args.plugin_dir:
            args.plugin_dir = list(cli_part["plugin_dir"])
        if cli_part.get("model") and not args.model:
            args.model = cli_part["model"]
        if cli_part.get("ui") and not args.ui:
            args.ui = cli_part["ui"]
        if cli_part.get("port") and not args.port:
            args.port = cli_part["port"]
        print(f"[norpagent] applied crash-rescue rollback snapshot: "
              f"{pending.get('description') or pending.get('snapshot_id') or ''}")

    # safe mode: force the minimal preset (even if the user specified another mode —
    # safe mode's job is to bypass every suspicious configuration)
    if args.safe_mode:
        args.mode = "minimal"
        args.mode_file = None

    try:
        reg = _build_registry(args)
        _apply_model_options(reg, args)
    except Exception as exc:  # noqa: BLE001 — startup failure: give self-rescue hints
        print(f"[error] startup failed: {exc}", file=sys.stderr)
        _print_rescue_hints()
        return 1

    if args.mode_file:
        preset = load_preset_file(args.mode_file)
        reg.register_preset(preset)
    mode = args.mode or (preset.name if args.mode_file else None)

    if args.list_modes:
        _list_modes(reg)
        return 0
    if not mode:
        parser.print_help()
        print("\nhint: use --list-modes to see available modes")
        return 1
    if mode not in reg.list_presets():
        print(f"unknown mode '{mode}'. Available: {reg.list_presets()}", file=sys.stderr)
        return 1
    if args.call_timeout is not None:
        preset = reg.resolve_preset(mode)
        preset.params = dict(preset.params)
        preset.params["call_timeout"] = args.call_timeout

    # work rollback: CLI startup baseline snapshot (failure does not block startup)
    try:
        from norpagent.recovery import snapshot_cli

        snapshot_cli({
            "mode": mode,
            "model": getattr(args, "model", None),
            "model_name": getattr(args, "model_name", None),
            "base_url": getattr(args, "base_url", None),
            "session": getattr(args, "session", None),
            "ui": getattr(args, "ui", None),
            "port": getattr(args, "port", None),
            "plugin_dir": list(getattr(args, "plugin_dir", None) or []),
            "safe": getattr(args, "safe", None),
            "safe_mode": bool(getattr(args, "safe_mode", False)),
        }, description="CLI startup baseline" + (" (safe mode)" if args.safe_mode else ""),
            tag="baseline")
    except Exception:  # noqa: BLE001
        pass

    try:
        if (args.ui or reg.resolve_preset(mode).ui) == "web":
            return _run_web(reg, mode, args, args.prompt)
        if args.prompt is not None:
            return _run_once(reg, mode, args)
        return _repl(reg, mode, args)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] run failed: {exc}", file=sys.stderr)
        _print_rescue_hints()
        return 1


def _print_rescue_hints() -> None:
    """Self-rescue hints on startup / run failures (safe mode + crash rescue + manual takeover)."""
    print("\nself-rescue hints:", file=sys.stderr)
    print("  1. start in safe mode (loads only the minimal kernel; skips all plugins):", file=sys.stderr)
    print("       norpagent --safe-mode", file=sys.stderr)
    print("       (in code: np(safemode='on'))", file=sys.stderr)
    print("  2. crash rescue: roll back to the last known-good snapshot:", file=sys.stderr)
    print("       norpagent-rescue list", file=sys.stderr)
    print("       norpagent-rescue rollback --last-good", file=sys.stderr)
    print("  3. restart after the rollback (the rollback target is consumed automatically).", file=sys.stderr)
    print("  4. model provider down: take over tool calls manually (human rescue):", file=sys.stderr)
    print("       norpagent-rescue tools", file=sys.stderr)
    print("       norpagent-rescue tool-call echo --args '{\"text\": \"ping\"}'", file=sys.stderr)
    print("       norpagent-rescue manual      # interactive manual tool console", file=sys.stderr)
    print("       norpagent-rescue serve       # HTTP API + operator page (127.0.0.1:8799)", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
