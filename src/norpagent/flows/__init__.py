# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Module flow orchestration kernel (FLOW): truly connects the visual canvas to the registry.

The "module flow" (/flow) is not an animated demo; it executes the canvas graph
with real registered components:

1. ``build_snapshot(registry, agent)``
   registry snapshot: models / tools / sessions / sandboxes / schedulers /
   plugins / presets / hooks. The frontend's "core module dock" renders cards per
   real component (one card per registered component).

2. ``ModuleWorkspace.register(...)``
   true registration of "file-as-module": dropping in a .py runs the full
   security pipeline (signature verification -> AST audit -> import restrictions
   -> registration into the registry); .json registers as a pure-description
   module (passthrough node); other types error explicitly, letting the frontend
   fall back to official modules. Successfully registered plugin hooks each become
   a hook node on the canvas (one hook = one node).

3. ``FlowRunner``
   executes the canvas graph (nodes + beams) topologically. Every node is
   independently try/except'ed: a single node failure records an error but does
   not interrupt the whole chain (zero-interruption semantics). Progress is
   pushed via the publish callback as ``flow.*`` events; the Web UI reuses the
   SSE channel (/events) to deliver them to the browser in real time.

Node execution semantics (type -> real action):

- trigger   reads the prompt input and produces a start signal;
- model     calls a real registered model (default engine preset model; per-node
            override possible); the tools port = the tool set mounted on the
            container (schemas auto-resolved and passed to the provider);
            system_prompt port = the system prompt (beam value > input panel >
            node config > engine preset params; empty values do not inject a
            system message);
- tool      calls a real registered tool: every input port = one schema parameter
            (no longer a global query/result black box);
- toolbox   tool container: input ports = the union of member tool parameters
            (fanned out by port name), output ports = each member's qualified
            "tool name.port name" plus a tools packaging port;
- sandbox   executes code in a real registered sandbox (child-process isolation);
- security  runs jailbreak/injection scanning on the payload (norpagent.security.guard);
- session   reads/writes the session manager (default engine session storage);
- plugin    plugin container (members = tool+hook members, port-union semantics)
            or standalone plugin tool execution;
- hook      fires one plugin hook (one hook = one node; mutating hooks go through
            intercept; the return value becomes the node output);
- other     passthrough (payload forwarded as-is);
- output    aggregates the final result;
- path      path module: produces a relative path value validated by the common
            path-safety checks (absolute paths / .. traversal rejected), beamed to
            any tool's path input port; empty value = workspace root ".";
- file      file module: when registered as a plugin, executes as a plugin;
            otherwise passthrough.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from norpagent.kernel.context import RunContext
from norpagent.kernel.registry import ComponentError

# plugin hook name -> business-argument keys of the legacy hook signature (aligned
# with plugins/loader.py; used to map a hook node's input payload into hook function arguments).
HOOK_ARG_KEYS: Dict[str, Tuple[str, ...]] = {
    "on_agent_init": (),
    "on_agent_shutdown": (),
    "on_task_start": ("user_input",),
    "on_task_done": ("content",),
    "on_task_error": ("error",),
    "on_task_stopped": ("reason",),
    "on_task_timeout": ("timeout",),
    "before_step": ("step", "messages"),
    "after_step": ("step", "content", "tool_calls"),
    "before_tool_call": ("tool_name", "args"),
    "after_tool_call": ("tool_name", "args"),
    "on_user_input_required": ("question",),
    "on_reasoning": ("content",),
    "on_content": ("content",),
    "on_event": ("event_type", "data"),
    "on_usage_update": ("total",),
}

_MUTATING_HOOKS = {"before_step", "before_tool_call", "after_tool_call"}

# canvas node type -> registry component kind mapping (frontend module dock grouping -> execution semantics)
NODE_KIND_GROUP = {
    "model": "models",
    "tool": "tools",
    "session": "sessions",
    "sandbox": "sandboxes",
    "scheduler": "schedulers",
    "plugin": "plugins",
    "preset": "presets",
    "hook": "plugins",
}

_MAX_MODULE_SIZE = 200 * 1024  # single-file module cap: 200KB
_MAX_OUTPUT_CHARS = 4000       # single event output truncation length


def default_modules_dir() -> str:
    """Disk directory of flow modules (where file-as-module .py / .json files live).

    Overridable via the NORPAGENT_FLOW_MODULES env var; default ~/.norpagent/flow_modules.
    """
    env = os.environ.get("NORPAGENT_FLOW_MODULES")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(os.path.expanduser("~"), ".norpagent", "flow_modules")


def _truncate(text: Any, limit: int = _MAX_OUTPUT_CHARS) -> str:
    s = "" if text is None else str(text)
    if len(s) > limit:
        return s[:limit] + f"\n... [truncated {len(s) - limit} chars]"
    return s


def _pick_color(name: str) -> str:
    palette = ["#c084fc", "#22d3ee", "#fb7185", "#a3e635", "#38bdf8",
               "#facc15", "#f472b6", "#4ade80", "#ffd166", "#94a3b8"]
    h = 0
    for ch in name or "module":
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return palette[h % len(palette)]


def _extract_ports(text: str, tag: str) -> List[str]:
    """Extract @in / @out port markers from module source comments / JSON."""
    arr = re.search(tag + r'["\s:=]*\[([^\]]*)\]', text)
    if arr:
        names = re.findall(r'["\']?([\w-]{1,16})["\']?', arr.group(1))
        return [n for n in names if n][:4]
    return [m.group(1) for m in re.finditer(
        tag + r'\s*:?\s*[\'"\[]?([\w-]{1,16})', text)][:4]


def _extract_module_name(text: str, fallback: str) -> str:
    m = re.search(r'@module["\'\s:=]*["\']?([\w\u4e00-\u9fa5-]{1,32})', text)
    return (m.group(1) if m else fallback).strip()


def _norm_tool_schema(schema: Any, name: str = "unknown") -> Dict[str, Any]:
    """Normalize a tool schema into the OpenAI ``{"type":"function","function":{...}}`` shape.

    OpenAI-compatible endpoints require ``tools[].type``. Previously the function
    wrapper was stripped and the inner dict passed to the provider; the inner dict
    lacks ``type`` and the remote returns 400 (missing field `type`). Three input
    shapes are handled uniformly:

    - already function-wrapped: keep function, add type;
    - bare schema: wrap the whole thing into function;
    - empty / non-dict: give the minimal legal definition (name fallback).
    """
    if isinstance(schema, dict):
        fn = schema.get("function")
        inner = dict(fn) if isinstance(fn, dict) else dict(schema)
        if not inner.get("name"):
            inner["name"] = str(name or "unknown")
        return {"type": "function", "function": inner}
    return {"type": "function", "function": {"name": str(name or "unknown")}}


def _tool_ports(schema: Any) -> Tuple[List[str], List[str]]:
    """Extract a tool's real hook ports from its OpenAI function schema.

    - input ports = schema parameter names (required first; at most 8);
    - output ports = result / success.
    Falls back to query / result on parse failure or an empty schema.
    """
    try:
        func = schema.get("function", schema) if isinstance(schema, dict) else {}
        params = func.get("parameters") or {}
        props = params.get("properties") or {}
        if isinstance(props, dict) and props:
            required = list(params.get("required") or ())
            names = [str(k) for k in props.keys()][:8]
            names = sorted(names, key=lambda k: (k not in required, names.index(k)))
            return names, ["result", "success"]
    except Exception:  # noqa: BLE001
        pass
    return ["query"], ["result"]


# ── registry snapshot ────────────────────────────────────


def build_snapshot(registry: Any, agent: Any = None,
                   engine_state: str = "unknown") -> Dict[str, Any]:
    """Registry -> module manifest snapshot (drives the frontend module dock / node instance selection)."""
    try:
        from norpagent import __version__
    except Exception:  # noqa: BLE001
        __version__ = "?"

    tool_plugin: Dict[str, str] = {}
    plugins: Dict[str, Any] = {}
    try:
        for pname, plugin in sorted((getattr(registry, "_plugins", {}) or {}).items()):
            tools = [getattr(t, "name", "") for t in plugin.get_tools()
                     if getattr(t, "name", "")]
            hooks = list((plugin.get_hooks() or {}).keys())
            for t in tools:
                tool_plugin[t] = pname
            plugins[pname] = {
                "name": pname,
                "version": str(getattr(plugin, "version", "") or ""),
                "publisher": str(getattr(plugin, "publisher", "") or ""),
                "description": str(getattr(plugin, "description", "") or ""),
                "tools": tools,
                "hooks": [{"name": h, "args": list(HOOK_ARG_KEYS.get(h, ()))}
                          for h in hooks],
            }
    except Exception:  # noqa: BLE001 — snapshots must never raise
        pass

    tools: List[Dict[str, Any]] = []
    for name in registry.list_tools():
        desc = ""
        ins, outs = ["query"], ["result"]
        try:
            schema = registry.resolve_tool(name).schema() or {}
            func = schema.get("function", schema) if isinstance(schema, dict) else {}
            desc = str(func.get("description", "") or "").strip()
            ins, outs = _tool_ports(schema)
        except Exception:  # noqa: BLE001
            pass
        tools.append({
            "name": name,
            "description": desc[:160],
            "plugin": tool_plugin.get(name, ""),
            "ins": ins,
            "outs": outs,
        })

    presets: List[Dict[str, Any]] = []
    try:
        for pname in registry.list_presets():
            preset = registry.resolve_preset(pname)
            presets.append({
                "name": pname,
                "model": getattr(preset, "model", "") or "",
                "tools": list(getattr(preset, "tools", ()) or ()),
                "mode": getattr(preset, "mode", "") or "",
                "description": (getattr(preset, "description", "") or "")[:120],
            })
    except Exception:  # noqa: BLE001
        pass

    security: Dict[str, Any] = {"installed": False}
    sec = getattr(registry, "security", None)
    if sec is not None:
        security = {
            "installed": True,
            "level": str(getattr(sec, "level", "") or ""),
            "audit_level": str(getattr(sec, "audit_level", "") or ""),
            "import_restrict": str(getattr(sec, "import_restrict", "") or ""),
        }

    hook_names: List[str] = []
    try:
        hook_names = registry.hooks.list_hook_names()
    except Exception:  # noqa: BLE001
        pass

    preset_name = ""
    model_name = ""
    agent_tools: List[str] = []
    if agent is not None:
        preset_name = getattr(getattr(agent, "preset", None), "name", "") or ""
        model_name = getattr(getattr(agent, "preset", None), "model", "") or ""
        agent_tools = list(
            getattr(getattr(agent, "preset", None), "tools", ()) or ())
    model_names = registry.list_models()
    default_model = model_name or (model_names[0] if model_names else "")

    # workspace root (the base directory of path modules; consistent with the file tools' pathsafe resolution)
    workspace_root = os.getcwd()
    try:
        params = getattr(agent, "params", None) or {}
        if isinstance(params, dict) and str(params.get("workspace_root") or ""):
            workspace_root = os.path.abspath(
                os.path.expanduser(str(params["workspace_root"])))
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "version": __version__,
        "engine_state": engine_state,
        "preset": preset_name,
        "default_model": default_model,
        "agent_tools": agent_tools,
        "security": security,
        "workspace_root": workspace_root,
        "groups": {
            "models": [
                {"name": n, "default": n == default_model}
                for n in model_names
            ],
            "tools": tools,
            "sessions": [{"name": n} for n in registry.list_sessions()],
            "sandboxes": [{"name": n} for n in registry.list_sandboxes()],
            "schedulers": [{"name": n} for n in registry.list_schedulers()],
            "plugins": list(plugins.values()),
            "presets": presets,
        },
        "hooks": hook_names,
        "modules_dir": default_modules_dir(),
    }


# ── file-as-module: true registration ────────────────────


class ModuleWorkspace:
    """Flow module workspace: disk persistence + security-pipeline registration + idempotent dedup.

    Re-dropping the same file content does not re-subscribe hooks (idempotent);
    .py goes through the full PluginLoader pipeline; .json is a pure-description module.
    """

    def __init__(self, directory: Optional[str] = None,
                 config: Optional[Dict[str, Any]] = None) -> None:
        self.directory = os.path.abspath(
            directory or default_modules_dir()
        )
        os.makedirs(self.directory, exist_ok=True)
        self.config = dict(config or {})
        self._loader: Any = None
        self._content_hash: Dict[str, str] = {}
        self._defs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _get_loader(self) -> Any:
        if self._loader is None:
            from norpagent.plugins.loader import PluginLoader

            self._loader = PluginLoader([self.directory], config=self.config)
        return self._loader

    @staticmethod
    def _safe_filename(name: str, ext: str) -> str:
        stem = os.path.splitext(name)[0]
        stem = re.sub(r"[^\w\u4e00-\u9fa5-]", "_", stem).strip("_")
        return f"{stem or 'module'}.{ext}"

    @staticmethod
    def _parse_py_meta(content: str) -> Dict[str, Any]:
        """Parse the module header declarations of a .py file (module-level variables).

        Supports: ``__norpagent_type__`` / ``__norpagent_name__`` /
        ``__norpagent_desc__`` / ``__norpagent_params__`` /
        ``__norpagent_hooks__``. Undeclared types fall back to other.
        """
        meta: Dict[str, Any] = {"mtype": "", "name": "", "desc": "",
                                "params": None, "hooks": None}
        for key, raw in re.findall(
                r"^__norpagent_(type|name|desc|params|hooks)__\s*=\s*(.+)$",
                content, re.MULTILINE):
            val = raw.strip().rstrip(",").strip()
            out_key = "mtype" if key == "type" else key
            if key in ("params", "hooks"):
                try:
                    import ast
                    meta[out_key] = ast.literal_eval(val)
                except Exception:  # noqa: BLE001
                    meta[out_key] = None
                continue
            m = re.match(r"^([\"'])(.*)\1$", val)
            meta[out_key] = m.group(2) if m else val
        return meta

    def register(self, registry: Any, name: str,
                 content: str) -> Dict[str, Any]:
        """Register a dropped-in module file; returns {ok, module|reason}.

        - .py: registered through the full plugin security pipeline; the module
          header declaration decides the frontend routing type;
        - .json / .yaml / .yml: description modules (the ``type`` field declares the routing type);
        - .html / .htm / .js / .ts: frontend modules (FE), persisted and hosted at
          ``/fe/<safe_name>`` for "open in a new tab".
        """
        content = content or ""
        if len(content.encode("utf-8", errors="replace")) > _MAX_MODULE_SIZE:
            return {"ok": False, "reason": "module file too large (200KB cap)"}
        ext = (os.path.splitext(name)[1] or "").lstrip(".").lower()
        with self._lock:
            if ext == "py":
                return self._register_python(registry, name, content)
            if ext == "json":
                return self._register_json(name, content)
            if ext in ("yaml", "yml"):
                return self._register_yaml(name, content)
            if ext in ("html", "htm", "js", "ts"):
                return self._register_frontend(name, content, ext)
            if ext in ("md", "txt"):
                return {
                    "ok": False,
                    "reason": (
                        "the backend cannot execute .%s files — real registration "
                        "supports only .py plugins (full security pipeline), "
                        ".json/.yaml module descriptions, and .html/.js/.ts frontend modules" % ext
                    ),
                }
            return {"ok": False, "reason": f"unsupported extension .{ext or '?'}"}

    def _register_python(self, registry: Any, name: str,
                         content: str) -> Dict[str, Any]:
        fname = self._safe_filename(name, "py")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if self._content_hash.get(fname) == digest and fname in self._defs:
            return {"ok": True, "module": dict(self._defs[fname]),
                    "cached": True}

        path = os.path.join(self.directory, fname)
        tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)

        loader = self._get_loader()
        info = self._load_single(registry, loader, fname, path)
        if info is None:
            return {"ok": False, "reason": "plugin file was not loaded (directory scan failed)"}
        if not getattr(info, "enabled", True):
            return {"ok": False, "reason": str(getattr(info, "error", "") or "plugin load failed")}

        module_name = getattr(info, "name", "") or os.path.splitext(fname)[0]
        meta = self._parse_py_meta(content)
        ins = _extract_ports(content, "@in") or [
            h for h in getattr(info, "hook_names", ()) or ()][:4] or ["input"]
        outs = _extract_ports(content, "@out") or list(
            getattr(info, "tools", ()) or ())[:4] or ["output"]
        color = _pick_color(module_name)
        mcolor = re.search(r'@color["\'\s:=]*["\']?(#[0-9a-fA-F]{3,6})', content)
        if mcolor:
            color = mcolor.group(1)

        module_def = {
            "name": meta.get("name") or module_name,
            "desc": (meta.get("desc") or getattr(info, "description", "")
                     or f"plugin module · {module_name}")[:160],
            "color": color,
            "kind": "file",
            "mtype": str(meta.get("mtype") or "other")[:32],
            "params": meta.get("params"),
            "declared_hooks": meta.get("hooks"),
            "plugin": module_name,
            "tools": list(getattr(info, "tools", ()) or ()),
            "hooks": [{"name": h, "args": list(HOOK_ARG_KEYS.get(h, ()))}
                      for h in (getattr(info, "hook_names", ()) or ())],
            "signature_status": getattr(info, "signature_status", "") or "",
            "audit_issues": len(getattr(info, "audit_issues", ()) or ()),
            "ins": ins,
            "outs": outs,
        }
        self._content_hash[fname] = digest
        self._defs[fname] = dict(module_def)
        return {"ok": True, "module": module_def}

    @staticmethod
    def _load_single(registry: Any, loader: Any, fname: str,
                     path: str) -> Any:
        """Load a single plugin file (reusing the PluginLoader security pipeline)."""
        before = len(loader.plugins)
        loader._load_from_file(registry, os.path.splitext(fname)[0], path,
                               manifest=None)  # noqa: SLF001 — single-file pipeline entry
        return loader.plugins[before] if len(loader.plugins) > before else None

    def _register_json(self, name: str, content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
        except ValueError as exc:
            return {"ok": False, "reason": f"JSON parse failed: {exc}"}
        if not isinstance(data, dict):
            return {"ok": False, "reason": "the module description must be a JSON object"}
        if not (data.get("@module") or data.get("type")):
            return {"ok": False, "reason": "missing @module or type declaration (not a valid module description)"}
        return self._register_described(name, data)

    def _register_yaml(self, name: str, content: str) -> Dict[str, Any]:
        """.yaml/.yml description module (zero-dependency parse; isomorphic with JSON)."""
        try:
            import yaml  # noqa: F401  optional dependency
        except ImportError:
            return {"ok": False, "reason": "PyYAML not installed (pip install pyyaml); cannot parse .yaml descriptions"}
        try:
            data = yaml.safe_load(content)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"YAML parse failed: {exc}"}
        if not isinstance(data, dict):
            return {"ok": False, "reason": "the module description must be a YAML object"}
        if not (data.get("@module") or data.get("type")):
            return {"ok": False, "reason": "missing @module or type declaration (not a valid module description)"}
        return self._register_described(name, data)

    def _register_described(self, name: str,
                            data: Dict[str, Any]) -> Dict[str, Any]:
        """Unified registration of description modules (.json/.yaml): the type field = frontend routing type."""
        mtype = str(data.get("type") or data.get("@type") or "other")[:32]
        mname = str(data.get("name") or data.get("@module"))[:32]
        ins = [str(k) for k in (data.get("@in") or data.get("ins") or ["input"]) if k][:4]
        outs = [str(k) for k in (data.get("@out") or data.get("outs") or ["output"]) if k][:4]
        color = str(data.get("@color") or data.get("color") or _pick_color(mname))
        module_def = {
            "name": mname,
            "desc": str(data.get("desc") or data.get("@desc")
                        or f"description module · {mname}")[:160],
            "color": color,
            "kind": "file",
            "mtype": mtype,
            "params": data.get("params"),
            "declared_hooks": data.get("hooks"),
            "plugin": "",
            "tools": [],
            "hooks": [],
            "signature_status": "",
            "audit_issues": 0,
            "ins": ins or ["input"],
            "outs": outs or ["output"],
        }
        fname = self._safe_filename(name, "json")
        self._defs[fname] = dict(module_def)
        return {"ok": True, "module": module_def}

    def _register_frontend(self, name: str, content: str,
                           ext: str) -> Dict[str, Any]:
        """Frontend module (.html/.htm/.js/.ts): persisted and hosted at /fe/<safe_name>.

        The browser's "open in a new tab" visits that URL; module_def.kind=frontend
        makes the frontend route the dropped-in file as an FE node (settings ports
        = that FE's own config items).
        """
        fname = self._safe_filename(name, ext)
        path = os.path.join(self.directory, fname)
        tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp, path)
        except OSError as exc:
            return {"ok": False, "reason": f"frontend module persist failed: {exc}"}
        stem = os.path.splitext(fname)[0]
        module_def = {
            "name": stem,
            "desc": f"frontend module · {stem} (.{ext})",
            "color": "#4ade80",
            "kind": "frontend",
            "mtype": "frontend",
            "format": ext,
            "url": f"/fe/{fname}",
            "params": None,
            "declared_hooks": None,
            "plugin": "",
            "tools": [],
            "hooks": [],
            "ins": [],
            "outs": [],
        }
        self._defs[fname] = dict(module_def)
        return {"ok": True, "module": module_def}


# ── flow executor ────────────────────────────────────────


def normalize_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a frontend-saved / exported graph into the FlowRunner execution format.

    The frontend's "auto-save" and "export flow" share the same serialization
    format (including x/y coordinates and container / members display fields);
    when the canvas RUNs, buildGraph additionally writes config.delegate_to
    (container member delegation) and config.members / config.tools (container
    member lists). This function fills in those runtime fields so that the chat
    task of "apply to the agent" and the canvas RUN have fully identical
    semantics. Idempotent for buildGraph output (existing fields untouched).
    """
    g = dict(graph or {})
    nodes = [dict(n) for n in (g.get("nodes") or [])
             if isinstance(n, dict)]
    by_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        nid = str(n.get("id") or "")
        if nid:
            by_id[nid] = n
    for n in nodes:
        cfg = n.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
            n["config"] = cfg
        container = n.get("container")
        if container and not cfg.get("delegate_to"):
            cfg["delegate_to"] = str(container)
        member_ids = n.get("members")
        if isinstance(member_ids, list) and member_ids \
                and "members" not in cfg:
            items: List[Dict[str, str]] = []
            tool_names: List[str] = []
            for mid in member_ids:
                m = by_id.get(str(mid))
                if not m:
                    continue
                kind = str(m.get("type") or "")
                mcfg = m.get("config") if isinstance(m.get("config"), dict) else {}
                name = str(mcfg.get("tool") or mcfg.get("hook")
                           or m.get("label") or "")
                if not name:
                    continue
                items.append({"kind": kind, "name": name,
                              "plugin": str(mcfg.get("plugin") or "")})
                if kind == "tool":
                    tool_names.append(name)
            cfg["members"] = items
            cfg["tools"] = tool_names
    g["nodes"] = nodes
    return g


class FlowRunner:
    """Executes real components topologically per the canvas graph.

    The publish(item) callback receives {type, payload, ts} event dicts:
    flow.node_start / flow.node_output / flow.node_done / flow.node_error /
    flow.done / flow.log.
    """

    def __init__(self, registry: Any, agent: Any = None,
                 publish: Optional[Callable[[Dict[str, Any]], None]] = None,
                 flow_id: Optional[str] = None,
                 workspace: Optional[ModuleWorkspace] = None) -> None:
        self.registry = registry
        self.agent = agent
        self.publish = publish or (lambda item: None)
        self.flow_id = flow_id or uuid.uuid4().hex[:12]
        self.workspace = workspace
        self._stop = threading.Event()

    # ── events ────────────────────────────────────────────

    def _pub(self, etype: str, **payload: Any) -> None:
        try:
            self.publish({
                "type": etype,
                "payload": {"flow_id": self.flow_id, **payload},
                "ts": time.time(),
            })
        except Exception:  # noqa: BLE001 — event failures must not interrupt the flow
            pass

    def request_stop(self) -> None:
        self._stop.set()

    # ── main flow ─────────────────────────────────────────

    def run(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the canvas graph; returns {status, final_output, errors, interrupts, nodes}."""
        raw_nodes = graph.get("nodes") or []
        links = graph.get("links") or []
        top_prompt = str(graph.get("prompt") or "")

        node_by_id: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for n in raw_nodes:
            nid = str(n.get("id") or f"n{len(order)}")
            if nid in node_by_id:
                continue
            node = dict(n)
            node["id"] = nid
            node.setdefault("type", "other")
            node.setdefault("config", {})
            node.setdefault("inputs", {})
            node_by_id[nid] = node
            order.append(nid)

        # in-degree / adjacency (node-level topology)
        indeg = {nid: 0 for nid in order}
        adj: Dict[str, List[str]] = {nid: [] for nid in order}
        for l in links:
            f, t = (l.get("from") or {}).get("id"), (l.get("to") or {}).get("id")
            if f in node_by_id and t in node_by_id and f != t:
                indeg[t] += 1
                adj[f].append(t)

        queue = [nid for nid in order if indeg[nid] == 0]
        outputs: Dict[str, Dict[str, str]] = {}
        errors = 0
        done: Set[str] = set()

        self._pub("flow.log", level="info",
                  message=f"topology parsed · {len(order)} nodes / {len(links)} beams")
        if not queue:
            # all-cycles (the canvas side already rejects cycles; defensive here): degrade to declaration order
            queue = list(order)

        while queue:
            if self._stop.is_set():
                break
            nid = queue.pop(0)
            if nid in done or nid not in node_by_id:
                continue
            done.add(nid)
            node = node_by_id[nid]

            # aggregate upstream inputs: {port: value}
            payload: Dict[str, str] = {}
            for l in links:
                f, t = (l.get("from") or {}), (l.get("to") or {})
                if t.get("id") == nid and f.get("id") in outputs:
                    payload[t.get("port") or "any"] = \
                        outputs[f["id"]].get(f.get("port") or "", "")

            # container member delegation: members belonging to a container and
            # without "outside-container" inputs skip individual execution — the
            # container node (toolbox / plugin container) executes them uniformly
            # per the port union, avoiding duplicate member tool calls (members on
            # the canvas are only visual hook views). Exception: when a member is
            # consumed directly by an external link (a downstream beam outside the
            # container), it executes once separately so the downstream never hangs.
            delegate_to = str((node.get("config") or {}).get("delegate_to") or "")
            if delegate_to:
                incoming = [l for l in links
                            if (l.get("to") or {}).get("id") == nid
                            and (l.get("from") or {}).get("id") in node_by_id]
                from_inside = all(
                    str((node_by_id.get(l.get("from", {}).get("id"), {})
                         .get("config") or {}).get("delegate_to") or "")
                    == delegate_to
                    for l in incoming
                )
                wants_output = any(
                    (l.get("from") or {}).get("id") == nid
                    and (l.get("to") or {}).get("id") != delegate_to
                    and str((node_by_id.get((l.get("to") or {}).get("id"), {})
                             .get("config") or {}).get("delegate_to") or "")
                        != delegate_to
                    for l in links
                )
                if (not incoming or from_inside) and not wants_output:
                    self._pub("flow.node_done", node_id=nid,
                              label=str(node.get("label") or nid),
                              status="boxed")
                    outputs[nid] = {}
                    for m in adj[nid]:
                        indeg[m] -= 1
                        if indeg[m] == 0 and m not in done:
                            queue.append(m)
                    continue

            self._pub("flow.node_start", node_id=nid,
                      label=str(node.get("label") or nid),
                      type=str(node.get("type") or "other"))
            try:
                result = self._execute_node(node, payload, top_prompt)
            except Exception as exc:  # noqa: BLE001 — a single node failure does not interrupt the chain
                errors += 1
                self._pub("flow.node_error", node_id=nid,
                          label=str(node.get("label") or nid),
                          error=f"{type(exc).__name__}: {exc}")
                outputs[nid] = {}
                self._pub("flow.node_done", node_id=nid,
                          label=str(node.get("label") or nid),
                          status="error")
            else:
                outs = {str(k): str(v) for k, v in (result or {}).items()}
                outputs[nid] = outs
                for port, value in outs.items():
                    self._pub("flow.node_output", node_id=nid, port=port,
                              output=_truncate(value), stream=False)
                self._pub("flow.node_done", node_id=nid,
                          label=str(node.get("label") or nid),
                          status="done", outputs={
                              k: _truncate(v) for k, v in outs.items()})

            for m in adj[nid]:
                indeg[m] -= 1
                if indeg[m] == 0 and m not in done:
                    queue.append(m)

        # unreachable nodes (missing upstream) marked waiting; no interruption
        for nid in order:
            if nid not in done:
                self._pub("flow.node_done", node_id=nid,
                          label=str(node_by_id[nid].get("label") or nid),
                          status="wait")

        final = self._final_output(node_by_id, outputs)
        status = "stopped" if self._stop.is_set() else "done"
        interrupts = 1 if self._stop.is_set() else 0
        self._pub("flow.done", status=status, final_output=_truncate(final),
                  errors=errors, interrupts=interrupts,
                  nodes=len(order), steps=len(done))
        return {
            "status": status,
            "final_output": final,
            "errors": errors,
            "interrupts": interrupts,
            "nodes": len(order),
        }

    @staticmethod
    def _final_output(node_by_id: Dict[str, Any],
                      outputs: Dict[str, Dict[str, str]]) -> str:
        for nid, node in node_by_id.items():
            if node.get("type") == "output":
                out = outputs.get(nid) or {}
                return out.get("final") or " / ".join(
                    v for v in out.values() if v) or ""
        for nid in reversed(list(node_by_id)):
            out = outputs.get(nid) or {}
            if out:
                return " / ".join(v for v in out.values() if v) or ""
        return ""

    # ── node execution ────────────────────────────────────

    def _execute_node(self, node: Dict[str, Any],
                      payload: Dict[str, str], top_prompt: str) -> Dict[str, str]:
        ntype = str(node.get("type") or "other")
        config = node.get("config") or {}
        inputs = node.get("inputs") or {}
        text = self._primary_input(node, payload, inputs)
        ctx = self._make_ctx(node)

        if ntype == "trigger":
            prompt = str(inputs.get("prompt") or top_prompt or "")
            self._pub("flow.log", level="info",
                      message=f"trigger signal · prompt length {len(prompt)}")
            return {"start": prompt}
        if ntype == "model":
            return self._exec_model(node, text, config, payload)
        if ntype == "tool":
            return self._exec_tool(node, text, config, ctx, payload)
        if ntype == "toolbox":
            # tool container: execute all member tools in batch per the port union
            return self._exec_toolbox(node, payload, config, ctx)
        if ntype == "sandbox":
            return self._exec_sandbox(node, text, config)
        if ntype == "security":
            return self._exec_security(text)
        if ntype == "session":
            return self._exec_session(text, config)
        if ntype == "plugin":
            if config.get("members") is not None:
                # plugin container: same port-union execution semantics as the tool container
                return self._exec_toolbox(node, payload, config, ctx)
            return self._exec_plugin(node, text, config, ctx)
        if ntype == "hook":
            return self._exec_hook(text, config, ctx, inputs)
        if ntype == "output":
            return {"final": text}
        if ntype == "path":
            # path module: produces a safety-validated relative path value
            return self._exec_path(node, payload, inputs)
        if ntype == "scheduler":
            return self._exec_scheduler(text, config)
        if ntype == "context_store":
            return self._exec_context_store(payload, inputs, ctx)
        if ntype == "project_manager":
            return self._exec_project_manager(text, ctx)
        if ntype == "preset":
            return self._exec_preset(config)
        if ntype in ("frontend", "settings"):
            # FE frontend node / global settings node: settings-item ports (beam
            # value > panel value); scope=global (settings node) writes the global config
            return self._exec_frontend(node, payload, inputs, ntype == "settings")
        if ntype == "ui":
            return self._exec_ui(text)
        if ntype == "async_loop":
            # event loop node: task submission passthrough (the real loop is held by the engine)
            return {"result": text}
        if ntype == "agent_runtime":
            return self._exec_agent_runtime(text, config)
        if ntype in ("file", "file:module"):
            if config.get("plugin"):
                return self._exec_plugin(node, text, config, ctx)
            return {"output": text}
        # other / unknown types: passthrough
        return {"any": text}

    @staticmethod
    def _primary_input(node: Dict[str, Any], payload: Dict[str, str],
                       inputs: Dict[str, Any]) -> str:
        ntype = str(node.get("type") or "other")
        own = {
            "trigger": "prompt", "model": "prompt", "tool": "query",
            "sandbox": "code", "security": "payload", "session": "context",
            "plugin": "query", "hook": "payload", "output": "final",
            "other": "any", "file": "any", "toolbox": "", "path": "value",
        }.get(ntype, "any")
        if ntype == "tool":
            # tool: every input port = one schema parameter, consumed directly by
            # _exec_tool; here only the fallback text for unconnected inputs
            for port, value in (payload or {}).items():
                if port == "query" and value:
                    return str(value)
            return str(inputs.get("query") or inputs.get("value") or "")
        if ntype == "model":
            # model: prompt + context; the tools port belongs to tool-set mounting
            # and must never mix into prompt text
            values: List[str] = []
            for port, value in (payload or {}).items():
                if port in ("prompt", "context") and value:
                    if port == "prompt":
                        values.insert(0, str(value))
                    else:
                        values.append(str(value))
            if values:
                return "\n".join(values)
            return str(inputs.get("value") or inputs.get("prompt") or "")
        values = []
        for port, value in (payload or {}).items():
            if value is None:
                continue
            if port == own:
                values.insert(0, str(value))
            else:
                values.append(str(value))
        if values:
            return "\n".join(v for v in values if v is not None)
        if ntype == "sandbox":
            return str(inputs.get("code") or "echo NORP-FLOW-SANDBOX")
        return str(inputs.get("value") or inputs.get(own) or "")

    def _make_ctx(self, node: Dict[str, Any]) -> RunContext:
        agent = self.agent
        config = (node.get("config") or {}).get("params") or {}
        params: Dict[str, Any] = {}
        if agent is not None:
            params.update(getattr(agent, "params", None) or {})
        if isinstance(config, dict):
            params.update(config)
        return RunContext(
            registry=self.registry,
            session_manager=getattr(agent, "session_manager", None) or None,
            session_id=getattr(self, "_flow_session_id", None) or "",
            sandbox=getattr(agent, "sandbox", None) or None,
            scheduler=getattr(agent, "scheduler", None) or None,
            ui=getattr(agent, "ui", None) or None,
            params=params,
            task_id=self.flow_id,
            preset_name=getattr(getattr(agent, "preset", None), "name", "") or "",
            components=getattr(agent, "components", None) or {},
        )

    # ── new node types (scheduler / context store / project manager / preset / FE / UI / agent loop) ──

    def _exec_scheduler(self, text: str,
                        config: Dict[str, Any]) -> Dict[str, str]:
        """Scheduler node: submit a long-run task to the engine scheduler."""
        sched = getattr(self.agent, "scheduler", None) if self.agent is not None else None
        if sched is None or not text:
            return {"submitted": ""}
        try:
            task = sched.submit(text)
            tid = str(getattr(task, "id", "") or task)
            self._pub("flow.log", level="info",
                      message=f"scheduler submitted task <b>{tid or '?'}</b>")
            return {"submitted": tid}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"scheduler submit failed: {exc}") from exc

    def _exec_context_store(self, payload: Optional[Dict[str, str]],
                            inputs: Dict[str, Any], ctx: RunContext) -> Dict[str, str]:
        """Context-store node: op=add/search/list/delete + query."""
        comp = ctx.context_store
        if comp is None:
            comp = (getattr(self.agent, "components", None) or {}).get("context_store")
        op = str((payload or {}).get("op") or inputs.get("op") or "search").strip()
        query = str((payload or {}).get("query") or inputs.get("query") or "").strip()
        if comp is None:
            raise RuntimeError("the engine has no context_store component assembled")
        try:
            if op == "add":
                if query and hasattr(comp, "add"):
                    comp.add(query)
                return {"result": "added"}
            if op == "list":
                items = comp.list() if hasattr(comp, "list") else []
                return {"result": json.dumps(items, ensure_ascii=False)[:_MAX_OUTPUT_CHARS]}
            if op == "delete":
                if query and hasattr(comp, "delete"):
                    comp.delete(query)
                return {"result": "deleted"}
            res = comp.search(query) if hasattr(comp, "search") else []
            return {"result": json.dumps(res, ensure_ascii=False)[:_MAX_OUTPUT_CHARS]}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"context-store operation failed: {exc}") from exc

    def _exec_project_manager(self, text: str, ctx: RunContext) -> Dict[str, str]:
        """Project-management node: query → project status."""
        comp = ctx.project_manager
        if comp is None:
            comp = (getattr(self.agent, "components", None) or {}).get("project_manager")
        if comp is None:
            raise RuntimeError("the engine has no project_manager component assembled")
        try:
            status = getattr(comp, "status", None)
            if status is not None:
                res = status()
            else:
                res = {"project": text or ""}
            if isinstance(res, str):
                return {"status": res}
            return {"status": json.dumps(res, ensure_ascii=False, default=str)[:_MAX_OUTPUT_CHARS]}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"project-management query failed: {exc}") from exc

    def _exec_preset(self, config: Dict[str, Any]) -> Dict[str, str]:
        """Preset node: outputs the preset name (beamable to a model node's preset selector)."""
        name = str(config.get("preset") or "")
        return {"preset": name}

    def _exec_ui(self, text: str) -> Dict[str, str]:
        """UI rendering node: content rendered/notified via the engine's UI adapter; outputs rendered."""
        ui = getattr(self.agent, "ui", None) if self.agent is not None else None
        if ui is not None and text:
            notify = getattr(ui, "notify", None)
            if notify is not None:
                try:
                    notify(text)
                except Exception:  # noqa: BLE001 — render failures do not block the flow
                    pass
        return {"rendered": text}

    def _exec_frontend(self, node: Dict[str, Any],
                       payload: Optional[Dict[str, str]],
                       inputs: Dict[str, Any],
                       global_scope: bool = False) -> Dict[str, str]:
        """FE frontend node: settings-item ports (beam value > panel value).

        Execution = write the merged settings items into that FE's independent
        config (persisted via agent.ui's fe_save_config; scope=global writes the
        global config); output = each setting item's current value, for nearby
        wiring (a model node's api_key / api_base ports).
        """
        cfg: Dict[str, str] = {}
        scope = str(node.get("config") or {}).get("scope") or ""
        if global_scope:
            scope = "global"
        for port in node.get("ins") or []:
            key = port if isinstance(port, str) else (port.get("key") or "")
            if not key:
                continue
            val = str((payload or {}).get(key) or "").strip()
            if not val:
                val = str(inputs.get(key) or "").strip()
            cfg[key] = val
        ui = getattr(self.agent, "ui", None) if self.agent is not None else None
        if ui is not None:
            if scope == "global":
                saver = getattr(ui, "save_config", None)
                if saver is not None:
                    try:
                        saver({k: v for k, v in cfg.items() if v})
                    except Exception:  # noqa: BLE001
                        pass
            else:
                saver = getattr(ui, "fe_save_config", None)
                if saver is not None:
                    try:
                        saver(str(node.get("id") or node.get("label") or ""), cfg)
                    except Exception:  # noqa: BLE001
                        pass
        self._pub("flow.log", level="info",
                  message=f"FE <b>{node.get('label')}</b> config applied "
                          f"({'global' if scope == 'global' else 'fe'}) · {len(cfg)} items")
        return cfg

    def _exec_agent_runtime(self, text: str,
                            config: Dict[str, Any]) -> Dict[str, str]:
        """Agent-loop node: submit the input to the engine's full agent loop for execution."""
        if self.agent is None or not text:
            return {"result": ""}
        run = getattr(self.agent, "run", None)
        if run is None:
            raise RuntimeError("agent_runtime nodes need the engine agent loop")
        result = run(text)
        content = str(getattr(result, "final_content", "") or "")
        return {"result": content}

    # ── model ─────────────────────────────────────────────

    def _exec_model(self, node: Dict[str, Any], text: str,
                    config: Dict[str, Any],
                    payload: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        model_name = self._resolve_model_name(config)
        provider = self.registry.resolve_model(model_name) \
            if self._model_registered(model_name) else None
        params_override: Dict[str, Any] = {}
        if provider is None:
            # remote model name (e.g. deepseek-v4-flash): automatically mount onto
            # the openai_compat adapter (same behavior as saving a remote model in settings)
            provider = self._fallback_provider(model_name)
            if provider is not None:
                params_override["model_name"] = model_name
        if provider is None:
            raise ComponentError(
                f"model '{model_name}' is not registered, and no openai_compat adapter can host it")
        inputs = node.get("inputs") or {}
        context = str(inputs.get("context") or "")
        # FE nearby wiring: an upstream frontend node's api_key / api_base ports
        # directly override this call
        for port, value in (payload or {}).items():
            if port in ("api_key", "api_base") and value:
                params_override[port] = str(value)
        # tool set: containers mount via the tools port (JSON list); config.tools is the static declaration
        tool_names: List[str] = [str(x) for x in (config.get("tools") or [])]
        for port, value in (payload or {}).items():
            if port != "tools" or not value:
                continue
            try:
                parsed = json.loads(str(value))
                if isinstance(parsed, list):
                    tool_names = [str(x) for x in parsed]
            except (ValueError, TypeError):
                tool_names = [x.strip() for x in str(value).split(",")
                              if x.strip()]
        tool_schemas: List[Dict[str, Any]] = []
        for tname in tool_names:
            try:
                sch = self.registry.resolve_tool(tname).schema() or {}
                tool_schemas.append(_norm_tool_schema(sch, tname))
            except Exception:  # noqa: BLE001 — a missing tool does not block the model
                self._pub("flow.log", level="warn",
                          message=f"tool {tname} schema resolution failed; skipped")
        # system prompt priority: beam port > node input panel > node config >
        # engine preset params (only falls back when all are empty)
        system = (str((payload or {}).get("system_prompt") or "").strip()
                  or str(inputs.get("system_prompt") or "").strip()
                  or str(config.get("system_prompt") or "").strip()
                  or str((self.agent and getattr(getattr(self.agent, "preset", None),
                                                 "params", {}) or {}).get("system_prompt", "") or "").strip())
        from norpagent.protocols.model import ChatMessage

        messages = []
        if system:
            messages.append(ChatMessage(role="system", content=system))
        user_content = text if text else str(inputs.get("prompt") or "")
        if context:
            user_content = f"{user_content}\n\n[context]\n{context}" if user_content else context
        messages.append(ChatMessage(role="user", content=user_content or "(empty input)"))

        params: Dict[str, Any] = {}
        if self.agent is not None:
            params.update(getattr(self.agent, "params", None) or {})
        if isinstance(config.get("params"), dict):
            params.update(config["params"])
        params.update(params_override)

        self._pub("flow.log", level="info",
                  message=f"model call <b>{model_name}</b> · input {len(user_content or '')} chars"
                          + (f" · tool set {len(tool_schemas)}" if tool_schemas else ""))
        stream = getattr(provider, "stream", None)
        if stream is not None and config.get("stream") is not False:
            return self._stream_model(provider, messages, tool_schemas, params,
                                      model_name)
        output = provider.generate(messages, tool_schemas or None, params)
        content = (getattr(output, "content", "") or "").strip()
        self._pub("flow.node_output", node_id=node.get("id"), port="inference",
                  output=_truncate(content), stream=False)
        return {
            "inference": content,
            "reasoning": str(getattr(output, "reasoning", "") or ""),
            "model": model_name,
        }

    def _model_registered(self, name: str) -> bool:
        try:
            self.registry.resolve_model(name)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _fallback_provider(self, model_name: str) -> Any:
        """Remote model name → openai_compat adapter (same as saving a remote model in settings)."""
        for adapter in ("openai_compat",):
            try:
                provider = self.registry.resolve_model(adapter)
                self._pub("flow.log", level="info",
                          message=f"remote model <b>{model_name}</b> mounted onto the "
                                  f"<b>{adapter}</b> adapter")
                return provider
            except Exception:  # noqa: BLE001
                continue
        return None

    def _stream_model(self, provider: Any, messages: List[Any],
                      tool_schemas: Optional[List[Dict[str, Any]]],
                      params: Dict[str, Any], model_name: str) -> Dict[str, str]:
        parts: List[str] = []
        reasoning: List[str] = []
        for chunk in provider.stream(messages, tool_schemas or None, params):
            if self._stop.is_set():
                break
            if getattr(chunk, "reasoning", ""):
                reasoning.append(chunk.reasoning)
                self._pub("flow.node_output", node_id=None, port="reasoning",
                          output=_truncate(chunk.reasoning), stream=True)
            if getattr(chunk, "delta_content", ""):
                parts.append(chunk.delta_content)
                self._pub("flow.node_output", port="inference",
                          output=chunk.delta_content, stream=True)
        return {
            "inference": "".join(parts).strip(),
            "reasoning": "".join(reasoning),
            "model": model_name,
        }

    def _resolve_model_name(self, config: Dict[str, Any]) -> str:
        if config.get("model"):
            return str(config["model"])
        if config.get("preset"):
            try:
                preset = self.registry.resolve_preset(str(config["preset"]))
                return getattr(preset, "model", "") or ""
            except Exception:  # noqa: BLE001
                pass
        if self.agent is not None:
            name = getattr(getattr(self.agent, "preset", None), "model", "") or ""
            if name:
                return name
        models = self.registry.list_models()
        if models:
            return models[0]
        raise RuntimeError("the registry has no models")

    # ── tool / sandbox / security / session ───────────────

    def _exec_tool(self, node: Dict[str, Any], text: str,
                   config: Dict[str, Any], ctx: RunContext,
                   payload: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        tool_name = str(config.get("tool") or "")
        if not tool_name:
            raise RuntimeError("tool nodes must specify tool (pick a registered tool in the node config)")
        tool = self.registry.resolve_tool(tool_name)
        # every input port = one schema parameter (no longer a global query/result black box)
        args: Dict[str, Any] = {}
        for port, value in (payload or {}).items():
            if value is not None and str(value):
                args[str(port)] = str(value)
        if not args and text:
            try:
                props = ((tool.schema() or {}).get("function", {})
                         .get("parameters", {}).get("properties", {}))
                first = next(iter(props), "query")
            except Exception:  # noqa: BLE001
                first = "query"
            args[str(first)] = text
        if isinstance(config.get("args"), dict):
            for k, v in config["args"].items():
                if v not in (None, "") and k not in args:
                    args[k] = v
        self._pub("flow.log", level="info",
                  message=f"tool call <b>{tool_name}</b> · args {sorted(args)}")
        result = tool.run(args, ctx)
        output = getattr(result, "output", None)
        if output is None:
            output = str(result)
        return {
            "result": str(output),
            "success": str(bool(getattr(result, "success", True))),
            "tool": tool_name,
        }

    def _exec_toolbox(self, node: Dict[str, Any],
                      payload: Dict[str, str], config: Dict[str, Any],
                      ctx: RunContext) -> Dict[str, str]:
        """Tool/plugin container: execute all members in batch per the port union.

        - container input ports = the union of member hook parameters; values are
          delivered by port name to every member owning that parameter (fan-out semantics);
        - container output ports = each member's qualified ``member name.port name``
          (union, eliminating name collisions) plus the container's own ports
          (e.g. the ``tools`` packaging port);
        - members can be any module kind (tool / hook / session / sandbox / model /
          security / scheduler / preset): each member is independently fault-tolerant;
          a single member failure does not interrupt the container or other members.
        """
        members: List[Dict[str, Any]] = [
            dict(m) for m in (config.get("members") or [])
            if isinstance(m, dict) and m.get("kind") and m.get("name")
        ]
        if not members:
            # legacy graph compatibility: execute as tool members when only a tools list exists
            for tname in (config.get("tools") or []):
                if tname:
                    members.append({"kind": "tool", "name": str(tname)})
        results: Dict[str, str] = {}
        for item in members:
            kind = str(item.get("kind") or "tool")
            name = str(item.get("name") or "")
            if not name:
                continue
            if kind == "tool":
                self._run_tool_member(name, payload, ctx, results)
                continue
            # non-tool members: build a pseudo member node and run the unified executor
            pseudo: Dict[str, Any] = {
                "type": kind,
                "label": name,
                "config": {kind: name},
                "inputs": {},
            }
            if kind == "hook":
                pseudo["config"] = {
                    "plugin": str(item.get("plugin") or ""),
                    "hook": name,
                }
            elif kind == "preset":
                pseudo = {
                    "type": "model",
                    "label": name,
                    "config": {"preset": name},
                    "inputs": {},
                }
            self._pub("flow.log", level="info",
                      message=f"container member <b>{kind}</b> <b>{name}</b> executing")
            try:
                r = self._execute_node(pseudo, payload, "")
            except Exception as exc:  # noqa: BLE001 — member failures do not interrupt the container
                results[f"{name}.result"] = f"{type(exc).__name__}: {exc}"
                results[f"{name}.success"] = "false"
                continue
            r = r or {}
            primary = next((v for v in r.values()
                            if v not in (None, "")), "")
            results[f"{name}.result"] = str(primary)
            results[f"{name}.success"] = "true"
        tool_names = [str(m.get("name") or "")
                      for m in members if m.get("kind") == "tool"]
        results["tools"] = json.dumps(tool_names, ensure_ascii=False)
        results["count"] = str(len(members))
        return results

    def _run_tool_member(self, tname: str, payload: Dict[str, str],
                         ctx: RunContext, results: Dict[str, str]) -> None:
        """Fan-out execution of one tool member inside the container (member-name-qualified output ports)."""
        try:
            tool = self.registry.resolve_tool(tname)
        except Exception as exc:  # noqa: BLE001
            results[f"{tname}.result"] = f"(not registered: {exc})"
            results[f"{tname}.success"] = "false"
            return
        args: Dict[str, Any] = {}
        for port, value in (payload or {}).items():
            if value is not None and str(value):
                args[str(port)] = str(value)
        # keep only the parameters declared in this tool's schema (other ports belong to other members)
        try:
            schema = tool.schema() or {}
            props = (schema.get("function", schema)
                     .get("parameters", {}).get("properties", {})
                     if isinstance(schema, dict) else {})
            if isinstance(props, dict) and props:
                args = {k: v for k, v in args.items() if k in props}
        except Exception:  # noqa: BLE001
            pass
        if not args:
            args = {"query": (payload or {}).get("query") or ""}
        self._pub("flow.log", level="info",
                  message=f"container member tool <b>{tname}</b> executing · args {sorted(args)}")
        try:
            result = tool.run(args, ctx)
        except Exception as exc:  # noqa: BLE001 — member failures do not interrupt the container
            results[f"{tname}.result"] = f"{type(exc).__name__}: {exc}"
            results[f"{tname}.success"] = "false"
            return
        output = getattr(result, "output", None)
        results[f"{tname}.result"] = str(
            output if output is not None else result)
        results[f"{tname}.success"] = str(
            bool(getattr(result, "success", True)))

    def _exec_sandbox(self, node: Dict[str, Any], text: str,
                      config: Dict[str, Any]) -> Dict[str, str]:
        name = str(config.get("sandbox") or "")
        if not name and self.agent is not None:
            name = getattr(getattr(self.agent, "preset", None), "sandbox", "") or ""
        name = name or "subprocess"
        sb = self.registry.build_sandbox(name)
        try:
            timeout = float(config.get("timeout") or 60)
        except (TypeError, ValueError):
            timeout = 60.0
        self._pub("flow.log", level="info",
                  message=f"sandbox <b>{name}</b> isolated execution · code {len(text or '')} chars")
        try:
            result = sb.run_shell(text or "echo NORP-FLOW-SANDBOX", timeout=timeout)
            stdout = str(getattr(result, "stdout", "") or "")
            stderr = str(getattr(result, "stderr", "") or "")
            output = (stdout + ("\n[stderr]\n" + stderr if stderr else "")).strip()
            return {
                "output": output,
                "exit_code": str(getattr(result, "exit_code", 0)),
                "sandbox": name,
            }
        finally:
            try:
                sb.close()
            except Exception:  # noqa: BLE001
                pass

    def _exec_path(self, node: Dict[str, Any],
                   payload: Dict[str, str],
                   inputs: Dict[str, Any]) -> Dict[str, str]:
        """Path module: produces a relative path value validated by the common path-safety checks.

        Value priority: the path value entered in the node config > upstream beam
        path / base port values > the workspace root ".". Validation reuses the
        file tools' common protection layer (pathsafe): absolute paths and ..
        traversal are rejected, guaranteeing a beamed value never triggers
        out-of-bounds on any tool's path port.
        """
        value = str(inputs.get("value") or "").strip()
        if not value:
            for port in ("path", "base"):
                up = str((payload or {}).get(port) or "").strip()
                if up:
                    value = up
                    break
        value = value or "."
        try:
            from norpagent.builtin.tools.pathsafe import resolve_safe_path

            ctx = self._make_ctx(node)
            resolved = resolve_safe_path(ctx, value)
            display = str(resolved)
        except Exception as exc:  # noqa: BLE001 — a validation failure rejects the node
            raise RuntimeError(f"invalid path: {exc}") from exc
        self._pub("flow.log", level="info",
                  message=f"path module <b>{value}</b> → <b>{display}</b> (safety-validated)")
        return {"path": value, "resolved": display}

    def _exec_security(self, text: str) -> Dict[str, str]:
        from norpagent.security.guard import scan_message

        blocked, reason, _matches = scan_message(text or "")
        self._pub("flow.log", level="warn" if blocked else "info",
                  message="security scan: %s" % ("blocked" if blocked else "passed"))
        return {
            "audited": text or "",
            "blocked": "true" if blocked else "false",
            "reason": reason or "",
        }

    def _exec_session(self, text: str,
                      config: Dict[str, Any]) -> Dict[str, str]:
        sm = None
        if self.agent is not None:
            sm = getattr(self.agent, "session_manager", None)
        if sm is None:
            name = str(config.get("session") or "memory")
            sm = self.registry.build_session(name)
        sid = str(config.get("session_id") or "")
        sess = None
        if sid:
            try:
                sess = sm.get_session(sid)
            except Exception:  # noqa: BLE001
                sess = None
        if sess is None:
            sess = sm.create_session(title=f"flow-{self.flow_id[:8]}")
        self._flow_session_id = str(sess.id)
        if text:
            from norpagent.protocols.model import ChatMessage

            try:
                sm.append_message(sess.id, ChatMessage(role="user", content=text))
            except Exception:  # noqa: BLE001
                pass
        history = []
        try:
            history = list(sm.history(sess.id))
        except Exception:  # noqa: BLE001
            pass
        self._pub("flow.log", level="info",
                  message=f"session <b>{sess.id[:8]}</b> · history {len(history)} messages")
        return {"session_id": str(sess.id), "messages": str(len(history)),
                "state": f"session {sess.id[:8]} ({len(history)} messages)"}

    # ── plugin / hook ─────────────────────────────────────

    def _exec_plugin(self, node: Dict[str, Any], text: str,
                     config: Dict[str, Any], ctx: RunContext) -> Dict[str, str]:
        tool_name = str(config.get("tool") or "")
        if not tool_name:
            tools = self._plugin_tools(str(config.get("plugin") or ""))
            tool_name = tools[0] if tools else ""
        if tool_name:
            tool = self.registry.resolve_tool(tool_name)
            args: Dict[str, Any] = {"query": text}
            if isinstance(config.get("args"), dict):
                args.update(config["args"])
            self._pub("flow.log", level="info",
                      message=f"plugin tool <b>{tool_name}</b> executing")
            result = tool.run(args, ctx)
            output = getattr(result, "output", None)
            return {"result": str(output if output is not None else result),
                    "tool": tool_name}
        # tool-less plugin: emit a custom event on the bus; plugin hooks can respond
        self.registry.bus.emit("on_event", event_type=f"flow.plugin.{config.get('plugin')}",
                               data=text, context=ctx)
        return {"result": text, "tool": ""}

    def _plugin_tools(self, plugin_name: str) -> List[str]:
        plugins = getattr(self.registry, "_plugins", {}) or {}
        plugin = plugins.get(plugin_name)
        if plugin is None:
            return []
        return [getattr(t, "name", "") for t in plugin.get_tools()
                if getattr(t, "name", "")]

    def _exec_hook(self, text: str, config: Dict[str, Any],
                   ctx: RunContext, inputs: Dict[str, Any]) -> Dict[str, str]:
        hook_name = str(config.get("hook") or "")
        if not hook_name:
            raise RuntimeError("hook nodes must specify hook")
        arg_keys = HOOK_ARG_KEYS.get(hook_name, ())
        payload: Dict[str, Any] = {"data": text, "context": ctx}
        for key in arg_keys:
            payload[key] = inputs.get(key) if inputs.get(key) is not None else text
        self._pub("flow.log", level="info",
                  message=f"hook <b>{hook_name}</b> fired (plugin {config.get('plugin')})")
        if hook_name in _MUTATING_HOOKS:
            try:
                result = self.registry.bus.intercept(hook_name, **payload)
            except Exception as exc:  # noqa: BLE001 — hook vetoes/exceptions do not interrupt
                self._pub("flow.log", level="warn",
                          message=f"hook {hook_name} vetoed/errored: {exc}")
                result = None
            return {"result": str(result) if result is not None else text}
        self.registry.bus.emit(hook_name, **payload)
        return {"result": text, "hook": hook_name}


__all__ = [
    "build_snapshot",
    "ModuleWorkspace",
    "FlowRunner",
    "normalize_graph",
    "default_modules_dir",
    "HOOK_ARG_KEYS",
]
