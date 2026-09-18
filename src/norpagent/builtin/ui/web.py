# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Web UI adapter: zero-dependency HTTP + SSE service (standard library http.server).

The Agent's "interface" is pluggable: this adapter implements the UIAdapter
protocol and is fully decoupled from the kernel:

- subscribes to the EventBus and pushes all agent events to the browser in real
  time (Server-Sent Events);
- ``POST /chat`` submits tasks (background thread execution; does not block HTTP);
- ``ask_user``: human-approval / clarification questions pushed to the page,
  waiting for the user's answer (timeout falls back to default, so automation
  scenarios never hang);
- ``notify``: non-blocking notifications;
- pages: by default serves front.html (multi-host frontend shared by the
  pywebview desktop and the browser, see front_src/bridge.js); when assets are
  missing it falls back to a built-in simple page; the constructor parameter
  ``html`` can mount a custom main page (file path or HTML content; starting
  with "<" after strip counts as content), replacing the / route's default page
  without physically overwriting library files; ``flow_html`` mounts the /flow
  module-flow page (norp-flow.html) the same way;
- runtime hot page replacement: ``mount_page(page, html)`` swaps the / (front) or
  /flow page bytes directly (HTTP service not restarted; port unchanged);
  physically replacing HTML files under the library's assets also takes effect
  automatically (page byte cache validated by file mtime/size);
- REST API (for the browser bridge of front.html):
  /api/sessions session CRUD, /api/config config, /api/models models,
  /api/presets preset modes (front "mode" selector), /api/plugins* plugins,
  /api/security security, /api/health health, /api/usage usage,
  /api/upload file upload, /api/quit quit, etc.

Usage (host application / CLI integration)::

    ui = WebUI(port=8787)
    ui.set_handler(lambda prompt, session_id, task_params: agent.run(...))
    ui.attach_runtime(agent)
    ui.start()          # start the HTTP service in a background thread
    ...                 # open http://127.0.0.1:8787/
    ui.shutdown()

When mounted via AgentRuntime: ``AgentRuntime(reg, preset, ui=ui)``; the runtime
automatically subscribes ui.on_event to the event bus.
"""

from __future__ import annotations

import base64
import errno
import json
import logging
import os
import re
import select
import socket
import sys
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse
import urllib.error
import urllib.request

_ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
_FRONT_HTML_PATH = os.path.join(_ASSET_DIR, "front.html")
# standalone categorized page: module flow orchestration (FLOW; hook-level visual
# flows similar to ComfyUI). It does not override the WebUI main page; it is an
# independent entry.
_FLOW_HTML_PATH = os.path.join(_ASSET_DIR, "norp-flow.html")
# standalone console page: FarStars 星轨控制台 (norp-farstars.html), the
# star-chain dispatch/observation console — an independent entry served at
# /farstars, /farstars.html and /norp-farstars.html.
_FARSTARS_HTML_PATH = os.path.join(_ASSET_DIR, "norp-farstars.html")
_logger = logging.getLogger("norpagent.ui.web")

# client-disconnect style exceptions (Windows: WinError 10053/10054; POSIX:
# EPIPE/ECONNRESET). These are normal for browser refreshes / tab closes / curl
# interrupts and must be handled silently; tracebacks must never flood the console.
_CLIENT_GONE_ERRORS = (
    BrokenPipeError,
    ConnectionAbortedError,
    ConnectionResetError,
    ConnectionError,
    TimeoutError,
)

# API key persistence: on Windows the key is DPAPI-encrypted (per-user, no
# dependencies) with this marker prefix; on other platforms it is stored as-is
# in the 0600 config file. Legacy plaintext values (no marker) still load.
_KEY_ENC_PREFIX = "enc:v1:"


def _dpapi_protect(data: bytes) -> bytes:
    """Windows DPAPI CryptProtectData wrapper (ctypes, zero dependencies)."""
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    buf = ctypes.create_string_buffer(data)
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(blob: bytes) -> bytes:
    """Windows DPAPI CryptUnprotectData wrapper (ctypes, zero dependencies)."""
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    buf = ctypes.create_string_buffer(blob)
    blob_in = _DATA_BLOB(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _encrypt_api_key(text: str) -> str:
    """Encrypt an API key for on-disk persistence (Windows DPAPI; passthrough elsewhere)."""
    text = str(text or "")
    if not text:
        return ""
    if sys.platform != "win32":
        return text
    try:
        blob = _dpapi_protect(text.encode("utf-8"))
    except Exception:  # noqa: BLE001 — DPAPI unavailable: fall back to plaintext
        return text
    return _KEY_ENC_PREFIX + base64.b64encode(blob).decode("ascii")


def _decrypt_api_key(value: str) -> str:
    """Decrypt a persisted API key value (marker-prefixed DPAPI blob → plaintext).

    Values without the marker (legacy plaintext or non-Windows storage) pass
    through unchanged, so existing configs keep working.
    """
    value = str(value or "")
    if not value.startswith(_KEY_ENC_PREFIX):
        return value
    if sys.platform != "win32":
        return value  # cannot decrypt on this platform; keep the stored form
    try:
        blob = base64.b64decode(value[len(_KEY_ENC_PREFIX):])
        return _dpapi_unprotect(blob).decode("utf-8")
    except Exception:  # noqa: BLE001
        return value


# Secret config keys persisted encrypted (DPAPI on Windows): the model API key
# plus the v0.9.9 multimodal service keys (TTS / STT).
_SECRET_KEYS = (
    "api_key", "tts_service_api_key", "stt_service_api_key",
    "vision_service_api_key", "audio_service_api_key", "video_service_api_key",
)


def _safe_delete_plugin_path(path: str, plugin_dirs: List[str]) -> "tuple[bool, str]":
    """Safely delete a plugin file / package directory (must live inside a plugin dir).

    Returns (ok, path-or-error). Rules:
    - the path must exist and resolve inside one of the configured plugin
      directories (no path traversal, never the plugin directory itself);
    - a single-file plugin is removed as a file; an entry inside a package
      folder (a subdirectory carrying manifest.json) removes the whole folder.
    """
    import shutil

    if not path or not os.path.exists(path):
        return False, "plugin path does not exist"
    real = os.path.realpath(path)
    allowed_roots = [os.path.realpath(d) for d in (plugin_dirs or []) if d]
    if not allowed_roots:
        return False, "no plugin directory configured"
    inside = False
    for root in allowed_roots:
        try:
            if os.path.commonpath([real, root]) == root and real != root:
                inside = True
                break
        except ValueError:
            continue
    if not inside:
        return False, "refusing to delete outside the configured plugin directories"

    target = real
    if os.path.isfile(real):
        parent = os.path.dirname(real)
        root_set = set(allowed_roots)
        if os.path.realpath(parent) not in root_set and \
                os.path.isfile(os.path.join(parent, "manifest.json")):
            target = parent  # package entry file -> remove the whole package folder
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
    except OSError as exc:
        return False, f"delete failed: {exc}"
    return True, target


class _RobustHTTPServer(ThreadingHTTPServer):
    """Robust ThreadingHTTPServer (pip-library friendly; high-concurrency tuned).

    - ``handle_error`` overridden: socketserver calls ``traceback.print_exc()``
      for every uncaught exception of each connection thread by default, and
      client-disconnect noise (e.g. WinError 10053) would be printed straight to
      the user's console. Here: disconnects are silent, everything else logs at
      DEBUG;
    - ``daemon_threads``: request threads are daemon; process exit never hangs;
    - ``allow_reuse_address``: the port is reusable immediately after a restart
      (avoiding TIME_WAIT). NOTE: SO_REUSEADDR is POSIX-only safe. On Windows
      SO_REUSEADDR allows *two processes to bind the exact same port at the same
      time* (full duplicate binding, unlike POSIX), which silently defeats the
      port-stepping logic in WebUI._bind and routes browser traffic to a stale
      server process. Therefore the flag is applied per-platform in
      ``server_bind``: Windows uses SO_EXCLUSIVEADDRUSE (occupied port raises
      WSAEADDRINUSE and _bind steps to the next port), POSIX keeps SO_REUSEADDR;
    - ``request_queue_size``: enlarged listen backlog (high-concurrency arrivals
      never drop SYN);
    - ``block_on_close = False``: shutdown does not wait for connections to close;
      faster shutdown under many active connections (request threads are daemon anyway)."""

    daemon_threads = True
    allow_reuse_address = False  # applied per-platform in server_bind (see docstring)
    request_queue_size = 256
    block_on_close = False

    def server_bind(self) -> None:
        """Bind with the platform-correct reuse semantics (see class docstring).

        Windows: SO_EXCLUSIVEADDRUSE prevents a second process from duplicating
        this listen port; an occupied port then raises WSAEADDRINUSE so
        ``WebUI._bind`` can step to the next free port as designed.
        POSIX: SO_REUSEADDR only relaxes TIME_WAIT reuse and never allows two
        live listeners on the same address.
        """
        if sys.platform == "win32":
            excl = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if excl is not None:
                try:
                    self.socket.setsockopt(socket.SOL_SOCKET, excl, 1)
                except OSError:  # noqa: BLE001 — non-fatal; bind will still validate
                    pass
        else:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()

    def handle_error(self, request: Any, client_address: Any) -> None:
        import sys as _sys

        exc = _sys.exc_info()[1]
        if isinstance(exc, _CLIENT_GONE_ERRORS):
            return
        _logger.debug(
            "http request error from %s: %s", client_address, exc, exc_info=True
        )


def default_project_root() -> str:
    """Give the default project root per the operating system (Windows / macOS / Linux each have conventions).

    - Windows: ``%USERPROFILE%\\Documents\\NORP-Agent``
    - macOS: ``~/Documents/NORP-Agent``
    - Linux/others: ``~/norpagent-workspace``
    """
    import sys as _sys

    home = os.path.expanduser("~") or ""
    if _sys.platform == "win32":
        base = os.environ.get("USERPROFILE") or home
        return os.path.join(base, "Documents", "NORP-Agent")
    if _sys.platform == "darwin":
        return os.path.join(home, "Documents", "NORP-Agent")
    return os.path.join(home, "norpagent-workspace")


def _default_config_path() -> str:
    """Path of the Web UI config persistence file (overridable via an environment variable).

    All browser-frontend settings (model / API key / language / plugin dirs etc.)
    are saved here: neither page refreshes nor np() process restarts lose them.
    Default ``~/.norpagent/webui_config.json``; tests may pass a temporary path.
    """
    env = os.environ.get("NORPAGENT_WEBUI_CONFIG")
    if env:
        return str(env)
    return os.path.join(os.path.expanduser("~"), ".norpagent",
                        "webui_config.json")


def _default_flow_graph_path() -> str:
    """Path of the flow auto-save file (overridable via an environment variable).

    Every canvas change on the /flow page auto-saves here (including the "apply to
    agent" switch state); it restores automatically after a refresh / restart;
    when active, the front main page's chat tasks execute per that flow. Default
    ``~/.norpagent/flow_graph.json``.
    """
    env = os.environ.get("NORPAGENT_FLOW_GRAPH")
    if env:
        return str(env)
    return os.path.join(os.path.expanduser("~"), ".norpagent",
                        "flow_graph.json")


# frontend "reasoning strength" options → reasoning_effort parameter.
# note: DeepSeek V4 accepts only low / high / max; values are normalized
# uniformly in the adapter layer (medium → high; see openai_compat.normalize_effort);
# "off" = none, translated by the adapter into DeepSeek V4's thinking=disabled.
_THINK_LEVEL_MAP = {
    "off": "none",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "max": "max",
    # legacy aliases kept for configs saved by older builds
    "xhigh": "max",
    # legacy Chinese values written by early FarStars console builds
    # (the old "高" option carried the label "最大（深度推理）" → maps to max)
    "关": "none",
    "低": "low",
    "中": "medium",
    "高": "max",
}


def _think_to_effort(value: Any) -> str:
    """Map an input-bar reasoning level to a reasoning_effort value ("" when unknown).

    Accepts off / low / medium / high / max plus legacy aliases (xhigh, plus the
    Chinese values written by older FarStars console builds). "off" maps to
    "none" so the adapter can explicitly disable thinking on capable models.
    """
    return _THINK_LEVEL_MAP.get(str(value or "").strip().lower(), "")

# 设置事实源分层标题（Web 面板展示「继承自 X」；与 evolution.store 保持一致）
try:
    from norpagent.evolution.store import SCOPE_TITLES as _SCOPE_TITLES_CACHE
except Exception:  # noqa: BLE001 — 极端环境下退回英文键
    _SCOPE_TITLES_CACHE = {
        "global": "global", "profile": "profile",
        "session": "session", "temp": "temp",
    }

# simple fallback page: used when assets/front.html is missing (keeping it runnable with zero dependencies)
_HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>norpagent Web UI</title>
<style>
  body { font-family: "Segoe UI", system-ui, sans-serif; margin: 0; display: flex;
         height: 100vh; background: #111827; color: #e5e7eb; }
  #main { flex: 1; display: flex; flex-direction: column; max-width: 900px;
          margin: 0 auto; width: 100%; }
  #events { flex: 1; overflow-y: auto; padding: 16px; }
  .ev { margin: 4px 0; padding: 6px 10px; border-radius: 6px; font-size: 13px;
        white-space: pre-wrap; word-break: break-all; }
  .ev-user { background: #1f2937; }
  .ev-content { background: #065f46; }
  .ev-tool { background: #1e3a5f; }
  .ev-meta { background: #374151; color: #9ca3af; }
  .ev-error { background: #7f1d1d; }
  #input-bar { display: flex; padding: 12px; gap: 8px; background: #0b1220; }
  #prompt { flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #374151;
            background: #111827; color: #e5e7eb; font-size: 14px; }
  button { padding: 10px 20px; border-radius: 8px; border: 0; background: #2563eb;
           color: white; cursor: pointer; font-size: 14px; }
  button:disabled { background: #374151; cursor: wait; }
  h3 { margin: 0 16px; color: #9ca3af; font-weight: normal; font-size: 13px; }
</style>
</head>
<body>
<div id="main">
  <h3>norpagent Web UI &middot; live event stream (SSE)</h3>
  <div id="events"></div>
  <div id="input-bar">
    <input id="prompt" placeholder="Type a task and press Enter to send" autofocus>
    <button id="send">Send</button>
  </div>
</div>
<script>
const events = document.getElementById('events');
const promptEl = document.getElementById('prompt');
const sendBtn = document.getElementById('send');
let sessionId = null;

function addLine(cls, text) {
  const div = document.createElement('div');
  div.className = 'ev ' + cls;
  div.textContent = text;
  events.appendChild(div);
  events.scrollTop = events.scrollHeight;
  while (events.childNodes.length > 400) events.removeChild(events.firstChild);
}

async function send() {
  const prompt = promptEl.value.trim();
  if (!prompt) return;
  addLine('ev-user', 'User: ' + prompt);
  promptEl.value = '';
  sendBtn.disabled = true;
  try {
    const resp = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, session_id: sessionId })
    });
    const data = await resp.json();
    if (data.session_id) sessionId = data.session_id;
    if (!data.ok) addLine('ev-error', '[failed] ' + (data.error || data.status));
  } catch (e) {
    addLine('ev-error', '[request failed] ' + e);
  } finally {
    sendBtn.disabled = false;
    promptEl.focus();
  }
}

sendBtn.onclick = send;
promptEl.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

const es = new EventSource('/events');
es.onmessage = (msg) => {
  try {
    const ev = JSON.parse(msg.data);
    if (ev.type === 'on_content') {
      addLine('ev-content', ev.content);
    } else if (ev.type === 'on_task_start') {
      addLine('ev-meta', '[task start] ' + ev.task_id + ' input: ' + ev.user_input);
    } else if (ev.type === 'before_tool_call') {
      addLine('ev-tool', '[tool] ' + ev.tool_name + ' ' + JSON.stringify(ev.args || {}));
    } else if (ev.type === 'after_tool_call') {
      addLine('ev-tool', '[tool result] ' + ev.tool_name + ' -> ' +
        (String(ev.result || '').slice(0, 300)));
    } else if (ev.type === 'on_task_done') {
      addLine('ev-meta', '[task done] steps=' + (ev.steps || '?'));
    } else if (ev.type === 'on_task_error' || ev.type === 'on_task_timeout') {
      addLine('ev-error', '[task error] ' + (ev.error || ev.timeout));
    } else if (ev.type === 'on_usage_update') {
      addLine('ev-meta', '[usage] in=' + ev.input + ' out=' + ev.output);
    } else if (ev.type === 'question') {
      addLine('ev-error', '[question] ' + ev.question);
      const answer = window.prompt(ev.question, '');
      fetch('/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: ev.question_id, answer: answer || '' })
      });
    } else if (ev.type === 'notify') {
      addLine('ev-meta', '[notify] ' + ev.message);
    }
  } catch (e) { /* ignore non-JSON lines */ }
};
es.onerror = () => addLine('ev-error', '[event stream interrupted, reconnecting...]');
</script>
</body>
</html>
"""

# default config: aligned with the settings-panel fields of front.html
DEFAULT_CONFIG: Dict[str, Any] = {
    "language": "en",                     # UI language (np(language=...) overrides)
    "model": "",                          # model (default = the engine preset model)
    "title_model": "",                    # optional model for auto session titles ("" = the session's current model; a separate one-off call)
    "context_token_budget": 32000,   # 0 = unlimited; over budget: compress first, truncate last            # clamp the request to this estimated token budget by dropping the oldest whole turns (0 = unlimited)
    "session_isolation": "per_session",   # concurrency isolation between sessions: per_session (default) | isolated_instance
    "api_base": "https://api.deepseek.com",
    "api_key": "",
    "remote_models": [],                  # remote model list from the last successful fetch (shown in the flow module dock)
    "project_root": default_project_root(),  # default workspace (per the operating system)
    "snapshot_dir": "",                     # snapshot storage dir (empty = default ~/.norpagent/snapshots/)
    # plugin management (2026-09-11): names disabled by the user / per-plugin log
    # directory ("" = default ~/.norpagent/plugin_logs) / host-side capability
    # restriction (None = unrestricted)
    "plugin_disabled": [],
    "plugin_log_dir": "",
    "plugin_capabilities": None,
    "plugin_dirs": [],
    "norp_safe_enabled": True,
    "security_enabled": True,
    "security_level": "standard",         # norpagent.safe() level (relaxed/basic/standard/high); the suite is always mounted
    # native tool confirmation (settings panel): master OFF by default; the three
    # per-class switches default ON and only apply while the master is on.
    "native_confirm_enabled": False,
    "native_confirm_write": True,
    "native_confirm_delete": True,
    "native_confirm_exec": True,
    "plugins_enabled": True,
    "use_responses_api": False,
    "queue_max_size": 200,
    "max_steps": 128,
    "task_timeout": 0,
    "api_request_timeout": 180,
    "enable_web_search": False,
    "think_level": "high",
    "temperature": 1.0,
    "top_p": 1.0,
    "call_timeout": 0,
    "max_tokens": 32767,
    "memory": True,
    "memory_mode": "full",
    "max_rounds": 10,
    "custom_system_prompt_enabled": False,
    "custom_system_prompt": "",
    "custom_system_prompt_file": "",
    "jailbreak_guard_enabled": True,
    "jailbreak_guard_action": "warn",
    "vision_enabled": False,
    "vision_service_url": "",
    "vision_service_api_key": "",
    # v2.x multimodal native passthrough: each modality routes either
    # "direct" (the attachment itself is passed to the model as a native
    # multimodal part) or "service" (an external service converts it to text).
    "mm_image_route": "direct",
    "mm_audio_route": "direct",
    "mm_video_route": "direct",
    # 文本附件（上传文件 / 粘贴内容）传给模型的字符上限；attachment_text_unlimited
    # 为真时忽略上限、完整传入。默认上限 1034324，可在多模态设置里调 512~2147483647。
    "attachment_text_max_chars": 1034324,
    "attachment_text_unlimited": False,
    "audio_service_url": "",
    "audio_service_api_key": "",
    "video_service_url": "",
    "video_service_api_key": "",
    # v0.9.9 multimodal: sound (TTS / STT) backend settings.
    # Native TTS works out of the box on Windows (SAPI) / macOS (say) / Linux
    # (espeak-ng) with zero configuration; STT uses the Windows local recognizer
    # or a configured OpenAI-compatible /audio/transcriptions service.
    "tts_enabled": True,
    "tts_service_url": "",        # optional OpenAI-compatible /audio/speech endpoint
    "tts_service_api_key": "",
    "tts_voice": "",              # e.g. "Microsoft Huihui Desktop" / "alloy"
    "tts_rate": 1.0,              # speech rate multiplier (0.5 ~ 2.0)
    "stt_service_url": "",        # optional OpenAI-compatible /audio/transcriptions endpoint
    "stt_service_api_key": "",
    "stt_language": "en-US",      # native recognizer language (zh-CN needs a Windows language pack)
    "sound_notify_enabled": True, # new-message notification tone
    "auto_speak_enabled": False,  # auto-read assistant replies aloud
    "plugin_security_audit": "warn",
    "plugin_security_import_restrict": "soft",
    "plugin_security_require_permissions": True,
    "plugin_security_resource_limit": False,
    "plugin_signature_verify": True,
    "plugin_trusted_keys": [],
    "plugin_isolation": "auto",
    "plugin_network_policy": "deny",
    "plugin_network_url_allowlist": [],
    "plugin_network_domain_allowlist": [],
    "approval_enabled": True,
    "preset_name": "",                     # front "mode" selector: a registry preset name (empty = the engine's current preset)
    "flow_modules_dir": "",               # module-flow "file-as-module" disk directory (empty = default ~/.norpagent/flow_modules)
    # front agent tool mounting (file-as-module → model auto-invocation):
    "agent_tools": [],                    # the explicit full tool set (effective when explicit=True; empty + non-explicit = the preset default set)
    "agent_tools_explicit": False,        # True = agent_tools is the agent's exact tool set (including the empty set)
    "_initialized": False,                # whether the first configuration has completed
}

# Signatures of a security / sandbox interception inside a tool result or a task
# stop reason. Matched centrally in WebUI.on_event so EVERY interception (sandbox
# AST precheck, jailbreak/injection guard, tool veto, approval denial, SSRF
# network policy) raises a prominent top-right alert on the frontend, regardless
# of which subsystem produced it.
_SEC_BLOCK_SIGNATURES = (
    "NORP安全系统拦截", "NORP 安全系统拦截", "安全系统拦截",
    "NORP安全系统介入拦截", "NORP 安全系统介入拦截", "安全系统介入拦截",
    "[run_python security blocked]", "security blocked",
    "security restriction:",
    "blocked_by_hook", "tool call vetoed by a hook",
    "tool call blocked by a plugin hook",
    "approval_denied", "the user denied the approval request",
    "input blocked by security protection",
    "jailbreak/injection", "jailbreak_guard",
    # 未签名/不受信插件：不是硬拦截，归 notice 挡（默认门槛 major 下不显示，
    # 只有把 security.alert_level 放宽到 all 才会以一闪而过的小提示出现）
    "unsigned plugin", "untrusted plugin", "未签名插件", "不受信插件",
)

# 定级依据（2026-09-14 修复）：**只看文本里有没有"拦截"二字会把"仅警告"误判成红色**。
# 因此改为「结构化字段优先 → 明确警告词 → 明确拦截词 → 默认警告」。红色（danger）只
# 用于"确实被拦住"，其余一律黄色（warn）——少吓人比多吓人安全。
_SEC_WARN_MARKERS = (
    "仅警告", "警告", "提醒", "warn", "warning", "advisory", "notice",
)
_SEC_DANGER_MARKERS = (
    "blocked", "denied", "veto", "forbidden", "rejected", "refused",
    "拦截", "阻断", "禁止", "已阻止",
)
_SEC_BLOCK_VALUES = ("block", "blocked", "deny", "denied", "danger", "reject",
                     "rejected", "veto", "vetoed", "error", "forbid", "forbidden")
_SEC_WARN_VALUES = ("warn", "warning", "advisory", "notice", "info",
                    "allow", "allowed", "pass", "audit")
# 严重度挡位（2026-09-15 分级）：把安全提示拆成四挡，默认只在「真被拦截」时提示。
# 起因：此前判定不出时一律回落到 warn，任何沾边事件都弹常驻横幅，用户（尤其非
# 开发者）会误以为"把电脑弄坏了"。挡位越高越少打扰：danger > warn > notice > silent。
_SEC_SEVERITY = {"silent": 0, "notice": 1, "warn": 2, "danger": 3}

# 界面提示门槛：security.alert_level 设置值 -> 最低显示挡位（99 = 全静默）
_SEC_THRESHOLD = {"off": 99, "major": 3, "normal": 2, "all": 1}

# 拦截类别 -> 默认挡位（显式「挡位表」；文本与结构化字段都没给出更明确信号时采用）
_SEC_CODE_SEVERITY = {
    "hook_veto": "danger",
    "approval_denied": "danger",
    "ssrf": "danger",
    "jailbreak": "danger",
    "sandbox": "danger",
    "unsafe_command": "danger",
    "plugin_untrusted": "notice",
    "unknown": "silent",
}
_SEC_ALERT_CODES = (
    ("hook_veto", ("blocked_by_hook", "vetoed by a hook",
                   "blocked by a plugin hook", "hook veto")),
    ("approval_denied", ("approval_denied", "denied the approval request")),
    ("ssrf", ("security restriction:", "ssrf", "internal address")),
    ("jailbreak", ("jailbreak", "injection")),
    ("sandbox", ("[run_python security blocked]", "security blocked", "sandbox")),
    ("unsafe_command", ("安全系统拦截", "norp safe", "危险命令", "uac",
                        "path traversal", "路径穿越")),
    ("plugin_untrusted", ("unsigned plugin", "未签名插件", "untrusted plugin")),
)


def _sec_alert_level(struct: Dict[str, Any], payload: Dict[str, Any],
                     text: str, code: str = "") -> str:
    """判定严重度挡位（四挡：danger / warn / notice / silent）。

    2026-09-15 分级：此前判定不出时一律回落到 warn，导致任何沾边事件都弹常驻
    横幅。现在四挡分明：只有「确实被拦住」是 danger；「仅警告」类降为 warn，而默认
    门槛是 major（只提示真拦截），因此默认不会显示；判定不出来的归 silent，只进审计日志。
    """
    for src in (struct, payload):
        if not isinstance(src, dict):
            continue
        for key in ("blocked", "denied", "blocked_by_hook", "vetoed"):
            value = src.get(key)
            if value is True:
                return "danger"
            if value is False:
                return "warn"
        for key in ("action", "level", "severity", "verdict", "decision",
                    "audit_level", "mode"):
            value = str(src.get(key) or "").strip().lower()
            if value in _SEC_BLOCK_VALUES:
                return "danger"
            if value in _SEC_WARN_VALUES:
                return "warn"
    low = text.lower()
    for marker in _SEC_WARN_MARKERS:
        if marker in text or marker in low:
            return "warn"
    for marker in _SEC_DANGER_MARKERS:
        if marker in text or marker in low:
            return "danger"
    return _SEC_CODE_SEVERITY.get(code or "", "silent")


def _sec_alert_code(text: str) -> str:
    """告警分类码（前端据此本地化文案，不再直接抛后端中文原文）。"""
    low = text.lower()
    for code, markers in _SEC_ALERT_CODES:
        for marker in markers:
            if marker in text or marker in low:
                return code
    return "unknown"

_MAX_JSON = 1_000_000
_MAX_UPLOAD_JSON = 64_000_000
_MAX_UPLOAD_FILE = 10 * 1024 * 1024
_MAX_VIDEO_UPLOAD_FILE = 32 * 1024 * 1024
# Fallback for the text-attachment length cap when the config key is absent.
# Mirrors the settings default (mm.text_attachment_limit = 1034324); the panel
# can raise it up to 2147483647 or switch on the no-limit option (0 = no cap).
_DEFAULT_TEXT_ATTACHMENT_MAX = 1034324

def filter_remote_models(models: Any) -> List[str]:
    """Filter out remote model names retired upstream.

    The vendor-specific retired list lives in the model adapter; the generic UI
    layer must not hardcode model names. When the adapter is unavailable no
    filtering is applied (the list is shown as fetched).
    """
    if not isinstance(models, (list, tuple, set)):
        return []
    try:
        from norpagent.builtin.models.openai_compat import (
            filter_remote_models as _adapter_filter,
        )
    except Exception:  # noqa: BLE001 — adapter unavailable: no filtering
        _adapter_filter = None
    if _adapter_filter is not None:
        return _adapter_filter(models)
    return [str(m) for m in models]


def json_safe(obj: Any, depth: int = 0) -> Any:
    """Recursively convert any object into a JSON-serializable structure (unserializable ones become strings).

    Fixes: when SSE pushes contain ChatMessage / RunContext objects, json.dumps
    raises TypeError, breaking the whole event stream.
    """
    if depth > 8:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): json_safe(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [json_safe(v, depth + 1) for v in obj]
    try:
        if hasattr(obj, "to_dict") and callable(obj.to_dict):
            return json_safe(obj.to_dict(), depth + 1)
    except Exception:  # noqa: BLE001
        pass
    return str(obj)


# ── SSE backpressure policy (slow-client governance under extreme concurrency) ──

_SSE_POLICIES = ("drop_oldest", "drop_newest", "unlimited")
# default SSE buffer cap (events). Under high-concurrency pushes each connection
# accumulates at most this many events; slow clients drop events (oldest by
# default) instead of unbounded memory growth.
_DEFAULT_SSE_QUEUE_SIZE = 1024
_DEFAULT_SSE_POLICY = "drop_oldest"
# frame batched write: one write+flush once this many frames accumulate or this
# interval elapses. Drastically reduces system-call count under high-frequency
# streaming token pushes (critical for extreme concurrency).
_DEFAULT_SSE_BATCH = 32
_DEFAULT_SSE_BATCH_INTERVAL = 0.05


def _encode_sse_frame(item: dict) -> bytes:
    """Encode one event into an SSE data frame (module-level reuse; avoids building a lambda per frame)."""
    return (
        f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"
        .encode("utf-8")
    )


class _SSESubscriber:
    """Event buffer of one SSE connection: bounded deque + condition-variable wakeup.

    Backpressure policy (``sse_queue_policy``; hot-changeable at runtime):

    - ``drop_oldest``: drop the oldest event when full (default — clients degrade
      gracefully without disconnecting; suitable for display frontends);
    - ``drop_newest``: drop the newest event when full (keep the old state, sacrifice
      new events; suitable for "state-sync" consumers);
    - ``unlimited``: no cap (legacy behavior; slow clients may grow memory; use only
      with an explicit reason).

    The buffer cap ``maxsize`` (0 = unlimited) and the policy can both be
    hot-changed at runtime via ``WebUI.set_sse_queue()`` (taking effect
    immediately on existing connections).
    """

    __slots__ = ("buffer", "cond", "maxsize", "policy", "dropped")

    def __init__(self, maxsize: int, policy: str) -> None:
        self.buffer: deque = deque()
        self.cond = threading.Condition()
        self.maxsize = max(0, int(maxsize))
        self.policy = policy if policy in _SSE_POLICIES else _DEFAULT_SSE_POLICY
        self.dropped = 0  # events dropped by backpressure (monitoring metric)

    def push(self, item: dict) -> None:
        """Push one event (thread-safe). Wakes the reader once on an empty→non-empty
        transition — every reader wakeup drains the buffer, so no per-item notify
        is needed (fewer locks under high concurrency)."""
        with self.cond:
            was_empty = not self.buffer
            if self.maxsize <= 0 or self.policy == "unlimited":
                self.buffer.append(item)
            elif self.policy == "drop_newest":
                if len(self.buffer) >= self.maxsize:
                    self.dropped += 1
                else:
                    self.buffer.append(item)
            else:  # drop_oldest (default)
                while len(self.buffer) >= self.maxsize:
                    self.buffer.popleft()
                    self.dropped += 1
                self.buffer.append(item)
            if was_empty:
                self.cond.notify()

    def resize(self, maxsize: int, policy: str) -> None:
        """Hot-change the cap and policy (effective immediately on the existing buffer)."""
        with self.cond:
            self.maxsize = max(0, int(maxsize))
            if policy in _SSE_POLICIES:
                self.policy = policy
            if self.policy != "unlimited" and self.maxsize > 0:
                while len(self.buffer) > self.maxsize:
                    self.buffer.popleft()
                    self.dropped += 1

    def wait(self, timeout: float) -> Optional[dict]:
        """Block for one event; None on timeout. Only one item per wakeup — the
        rest is left for the batched drain inside the reader loop (batched write)."""
        with self.cond:
            if not self.buffer:
                self.cond.wait(timeout)
            if self.buffer:
                return self.buffer.popleft()
        return None

    def drain(self, max_items: int) -> List[dict]:
        """Bulk-take at most max_items (paired with batched SSE frame writes)."""
        with self.cond:
            out = []
            while self.buffer and len(out) < max_items:
                out.append(self.buffer.popleft())
            return out

    def stats(self) -> Dict[str, Any]:
        with self.cond:
            return {
                "buffered": len(self.buffer),
                "maxsize": self.maxsize,
                "policy": self.policy,
                "dropped": self.dropped,
            }


class WebUI:
    """Web UI adapter (HTTP + SSE; zero third-party dependencies; pages: front.html + norp-farstars.html)."""

    ui_id = "web"

    def __init__(
        self,
        port: int = 8787,
        host: str = "127.0.0.1",
        ask_timeout: float = 300.0,
        history_limit: int = 2000,
        language: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[str] = None,
        html: Optional[str] = None,
        flow_html: Optional[str] = None,
        farstars_html: Optional[str] = None,
        sse_queue_size: Optional[int] = None,
        sse_queue_policy: Optional[str] = None,
        sse_batch: Optional[int] = None,
        sse_batch_interval: Optional[float] = None,
    ) -> None:
        self.port = int(port)
        self.host = host
        self.ask_timeout = float(ask_timeout)
        self.history_limit = int(history_limit)
        self._language = language or "en"
        # custom main page (slot mount parameter): the page bytes of the / route.
        # resolution rules: None = the library built-in front.html;
        #   starting with "<" after strip → used directly as HTML content;
        #   otherwise → treated as a file path (a nonexistent file raises
        #   ValueError; fail fast).
        self._html_override: Optional[bytes] = self._resolve_html(html)
        # custom flow page (slot mount parameter): the page bytes of the /flow route.
        # resolution rules identical to html; the fallback object is the library
        # built-in norp-flow.html.
        self._flow_html_override: Optional[bytes] = self._resolve_html(flow_html)
        # custom farstars console page (slot mount parameter): the page bytes of
        # the /farstars route; fallback = library built-in norp-farstars.html.
        self._farstars_html_override: Optional[bytes] = self._resolve_html(farstars_html)
        # config persistence path: None = no disk persistence (pure memory;
        # testing / embedded scenarios)
        self._config_path = (
            config_path if config_path is not None else _default_config_path()
        )
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._config["language"] = self._language
        # embedded optimization: constructing the WebUI triggers no disk I/O
        # (config / FE / flow-graph reads are all deferred to _ensure_disk_loaded
        # in start()). Explicit parameters are recorded and replayed after the
        # disk load, keeping the "explicit > persisted > default" priority.
        self._init_language = language
        self._init_config = dict(config) if config else None
        if language is not None:
            self._config["language"] = language
        if config:
            self._config.update(config)
        # SSE backpressure and batched writes (high-concurrency tuning;
        # hot-changeable at runtime): the environment variables
        # NORPAGENT_SSE_QUEUE_SIZE / NORPAGENT_SSE_QUEUE_POLICY only apply when
        # explicit parameters are not given.
        env_size = os.environ.get("NORPAGENT_SSE_QUEUE_SIZE")
        if sse_queue_size is None and env_size:
            try:
                sse_queue_size = int(env_size)
            except (TypeError, ValueError):
                sse_queue_size = None
        self._sse_queue_size = (
            max(0, int(sse_queue_size))
            if sse_queue_size is not None else _DEFAULT_SSE_QUEUE_SIZE
        )
        env_policy = os.environ.get("NORPAGENT_SSE_QUEUE_POLICY")
        policy = sse_queue_policy or env_policy or _DEFAULT_SSE_POLICY
        self._sse_queue_policy = (
            policy if policy in _SSE_POLICIES else _DEFAULT_SSE_POLICY
        )
        self._sse_batch = (
            max(1, int(sse_batch))
            if sse_batch is not None else _DEFAULT_SSE_BATCH
        )
        self._sse_batch_interval = (
            max(0.005, float(sse_batch_interval))
            if sse_batch_interval is not None else _DEFAULT_SSE_BATCH_INTERVAL
        )
        self._handler_fn: Optional[Callable] = None
        self._recovery_handler: Optional[Callable] = None
        self._agent: Any = None
        # CNB hosted instances (FarStars console one-click launch; node_id -> entry)
        self._cnb_hosted: Dict[str, Dict[str, Any]] = {}
        # snapshot of the preset's default tool set (captured at attach_runtime;
        # the fallback base of agent_tools)
        self._agent_base_tools: List[str] = []
        self._config_apply: Optional[Callable[[Dict[str, Any]], None]] = None
        self._quit_callback: Optional[Callable[[], None]] = None
        self._engine_state_fn: Optional[Callable[[], str]] = None
        self._lock = threading.RLock()
        self._subscribers: List[_SSESubscriber] = []
        self._history: List[dict] = []
        self._questions: Dict[str, Any] = {}
        self._question_sessions: Dict[str, str] = {}
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._task_session: Dict[str, str] = {}
        self._running_sessions: Dict[str, str] = {}
        self._stop_requests: set = set()
        # per-session cancel events (2026-09-13): the Web "stop" button sets the
        # event, and the kernel's model streaming loop polls it on every chunk, so
        # a generation in flight stops immediately instead of only at the next
        # step boundary.
        self._stop_events: Dict[str, threading.Event] = {}
        self._session_meta: Dict[str, Dict[str, Any]] = {}
        # sessions whose title has already been auto-summarized by the model
        # (2026-09-13): the title is generated once, from the first round only.
        self._auto_titled_sids: set = set()
        self._usage: Dict[str, int] = {"input_tokens": 0, "output_tokens": 0,
                                       "tool_call_tokens": 0}
        self._flow_runs: Dict[str, Any] = {}
        self._flow_ws: Any = None
        # FE frontend modules (file-as-frontend): .html/.js/.ts files dropped in
        # are registered and hosted at /fe/<safe_name>; "open in a new tab" visits
        # that URL. Each FE owns an independent config scope (mutually isolated);
        # defaults come from the global config.
        self._frontend_modules: Dict[str, Dict[str, Any]] = {}
        self._fe_scanned = False
        self._fe_config_dir = os.path.join(
            os.path.expanduser("~"), ".norpagent", "fe_configs")
        self._fe_configs: Dict[str, Dict[str, Any]] = {}
        # flow auto-save: the canvas graph + the "apply to agent" activation switch.
        # when active, the front main page's chat tasks execute per that flow
        # (behavior hot-switch).
        self._flow_graph: Optional[Dict[str, Any]] = None
        self._flow_active: bool = False
        self._flow_graph_path = _default_flow_graph_path()
        # sid/task_id -> the FlowRunner currently running for the chat session (STOP support)
        self._chat_flow_runs: Dict[str, Any] = {}
        self._disk_loaded = False       # lazy flag of disk state loading (embedded optimization)
        # page byte cache: {page: (resource signature, bytes)}. The signature =
        # the resource file's (mtime_ns, size); cache hits need no open+read disk
        # I/O; physically replacing the file makes the signature mismatch and
        # auto-rereads (hot-replacing the frontend needs no process restart).
        self._page_cache: Dict[str, Tuple[Tuple[int, int], bytes]] = {}
        self._tlocal = threading.local()
        self._start_ts = time.time()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._closed = False

    def _ensure_disk_loaded(self) -> None:
        """Load disk state once at startup (config / FE configs / flow graph).

        No disk reads at construction time (embedded / read-only-root filesystems
        friendly); explicit constructor parameters are replayed after the disk
        load, keeping the "explicit > disk > default" priority.
        """
        if self._disk_loaded:
            return
        with self._lock:
            if self._disk_loaded:
                return
            self._load_config_from_disk()
            # replay explicit constructor parameters (original construction-time
            # semantics: explicit overrides disk)
            if self._init_language is not None:
                self._config["language"] = self._init_language
            if self._init_config:
                self._config.update(self._init_config)
            self._load_fe_configs()
            self._load_flow_graph_from_disk()
            self._load_session_meta()
            self._disk_loaded = True

    @staticmethod
    def _resolve_html(html: Optional[str]) -> Optional[bytes]:
        """Resolve the html mount parameter into page bytes.

        - None / empty → not mounted (None; falls back to the library built-in front.html);
        - starting with "<" after strip → HTML content (UTF-8 encoded);
        - otherwise → a file path: read its content when it exists;
          a nonexistent file raises ValueError (fail fast; never silently fall
          back to the default page, so users are not fooled into thinking the
          mount took effect when they still see the built-in page).
        """
        if html is None:
            return None
        src = str(html).strip()
        if not src:
            return None
        if src.startswith("<"):
            return src.encode("utf-8")
        if not os.path.isfile(src):
            raise ValueError(
                f"WebUI html mount parameter is neither HTML content (starting with '<') "
                f"nor an existing file: {src!r}"
            )
        with open(src, "rb") as f:
            return f.read()

    # ── host integration ─────────────────────────────────

    def set_handler(self, fn: Callable) -> None:
        """Set the task-execution callback: fn(prompt, session_id, task_params) -> a RunResult-like object."""
        self._handler_fn = fn

    def set_recovery_handler(self, fn: Callable) -> None:
        """Set the work-rollback handler: fn(action, payload) -> dict.

        Injected by WebFrontend.attach; when not injected, /api/snapshots returns
        an explicit error (the frontend rollback panel hides or shows unavailable).
        """
        self._recovery_handler = fn

    def recovery_handle(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Work-rollback API dispatch (/api/snapshots). Without an injected handler,
        return an explicit error instead of a 500 that leaves the frontend guessing."""
        fn = self._recovery_handler
        if fn is None:
            return {"ok": False, "error": "work rollback not mounted (engine not assembled)"}
        try:
            return fn(action, payload or {})
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def restore_config(self, incoming: Dict[str, Any]) -> Dict[str, Any]:
        """Restore config (work rollback): snapshot's WebUI settings → memory + disk + apply.

        Only accepts the DEFAULT_CONFIG allowlist keys (same rule as disk loading).
        """
        if not isinstance(incoming, dict):
            return {"ok": False, "error": "config must be an object"}
        with self._lock:
            allowed = set(DEFAULT_CONFIG) | {"_initialized"}
            merged = dict(self._config)
            for key, value in incoming.items():
                if key in allowed:
                    if key in _SECRET_KEYS:
                        # accept plaintext or an already-encrypted (marker) value
                        merged[key] = _decrypt_api_key(value)
                    else:
                        merged[key] = value
            merged["_initialized"] = True
            self._config = merged
            cfg = dict(merged)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
        return {"ok": True, "config": self.get_config()}

    def attach_runtime(self, agent: Any) -> None:
        """Bind the agent runtime (the data source of session REST / plugin list / debug info)."""
        self._agent = agent
        if agent is not None:
            preset = getattr(agent, "preset", None)
            if preset is not None and not self._config.get("model"):
                self._config["model"] = getattr(preset, "model", "") or ""
            # snapshot of the preset's default tool set (the fallback base when agent_tools is not explicit)
            self._agent_base_tools = list(
                getattr(preset, "tools", ()) or ())
            # an explicit np(workspace_root=...) overrides the platform default workspace
            params = getattr(agent, "params", None) or {}
            if params.get("workspace_root"):
                self._config["project_root"] = str(params["workspace_root"])

    def set_config_apply(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        """Apply callback after config saves (WebFrontend re-registers models/plugins/security from it)."""
        self._config_apply = cb

    def set_quit_callback(self, cb: Callable[[], None]) -> None:
        self._quit_callback = cb

    def set_engine_state_fn(self, fn: Callable[[], str]) -> None:
        self._engine_state_fn = fn

    # ── service lifecycle ────────────────────────────────

    def start(self) -> "WebUI":
        """Start the HTTP service in a background thread (non-blocking).

        When the port is occupied, it advances to the next port automatically (up
        to 10 ports), taking the actually bound port as authoritative (``self.port``
        is updated); a total bind failure raises a RuntimeError with a clear
        message (no traceback spam).
        """
        if self._server is not None:
            return self
        ui = self

        class _Handler(BaseHTTPRequestHandler):
            server_version = "norpagent-webui/0.4"
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # silent access logs
                pass

            # ── connection robustness ────────────────────

            def handle(self):  # noqa: N802
                """Override BaseHTTPRequestHandler.handle: client disconnects do not print tracebacks.

                Browser refreshes / tab closes / curl interrupts make reads and
                writes raise ConnectionAbortedError / ConnectionResetError /
                BrokenPipeError, which previously bubbled to socketserver and
                flooded the console with tracebacks. Here the disconnect noise is
                swallowed uniformly; real internal errors log at DEBUG and
                attempt to return 500.
                """
                try:
                    super().handle()
                except _CLIENT_GONE_ERRORS:
                    pass
                except Exception as exc:  # noqa: BLE001 — defensive fallback
                    self.close_connection = True
                    _logger.debug(
                        "request %s failed: %s", getattr(self, "path", "?"),
                        exc, exc_info=True,
                    )
                    try:
                        self._json(500, {"error": "internal server error"})
                    except Exception:  # noqa: BLE001
                        pass

            def finish(self):  # noqa: N802
                """wfile flush also raises on client disconnect; equally silent."""
                try:
                    super().finish()
                except (OSError, _CLIENT_GONE_ERRORS):  # noqa: BLE001
                    pass

            def _json(self, code: int, obj: dict) -> None:
                body = json.dumps(json_safe(obj), ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self, limit: int = _MAX_JSON) -> dict:
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    length = 0
                if length > limit:
                    # oversized body: refuse and close the connection, preventing
                    # leftover unread bytes from desynchronizing the keep-alive
                    # protocol (later requests parsing garbage).
                    self.close_connection = True
                    return {}
                if length < 0:
                    length = 0  # negative Content-Length: treat as no body
                raw = self.rfile.read(length) if length else b""
                try:
                    data = json.loads(raw.decode("utf-8"))
                    return data if isinstance(data, dict) else {}
                except Exception:
                    return {}

            def _html(self, code: int, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                # the page must not be cached by the browser: every refresh takes
                # the latest front.html, otherwise a fixed frontend (e.g. the
                # chain-of-thought "thinking" block translation) is hidden behind
                # the stale cache
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _attach(self, body: bytes, filename: str,
                        mime: str = "application/octet-stream") -> None:
                """下载响应（进化包 / 设置快照导出用）。"""
                self.send_response(200)
                self.send_header("Content-Type", mime + "; charset=utf-8")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{filename}"')
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)
                if path in ("/", "/index.html"):
                    self._html(200, ui.page_bytes())
                elif path in ("/flow", "/flow.html", "/norp-flow.html"):
                    # standalone category "module flow": hook-level visual orchestration (drag modules / beam wiring)
                    self._html(200, ui.page_bytes("flow"))
                elif path in ("/farstars", "/farstars.html", "/norp-farstars.html"):
                    # standalone console page: FarStars 星轨控制台（跨节点星链调度与观测工作台）
                    self._html(200, ui.page_bytes("farstars"))
                elif path == "/favicon.ico":
                    self.send_response(204)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                elif path == "/assets/i18n.js":
                    # 三端共通多语言核心（2026-09-12）：帧内共享语言状态/存储/事件
                    body = ui.asset_bytes("i18n.js")
                    self.send_response(200)
                    self.send_header("Content-Type",
                                     "application/javascript; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif path == "/events":
                    self._handle_sse()
                elif path == "/api/status":
                    self._json(200, ui.stats())
                elif path == "/api/cnb/health":
                    # FarStars 星轨控制台：同源中枢总线代理（只允许本机回环
                    # 目标；浏览器侧无法跨源直连 CNB 总线，统一走本代理）。
                    base = str(query.get("base", [""])[0] or "").strip()
                    self._json(200, ui.cnb_proxy("GET", base))
                elif path == "/api/cnb/instances":
                    # 星轨控制台：本进程托管拉起的 CNB 实例清单
                    self._json(200, ui.cnb_instances())
                elif path == "/api/sessions":
                    self._json(200, {"sessions": ui.list_sessions()})
                elif path.startswith("/api/sessions/"):
                    self._handle_session_get(path)
                elif path == "/api/config":
                    self._json(200, ui.get_config())
                elif path == "/api/first_run":
                    self._json(200, {"first_run": ui.first_run()})
                elif path == "/api/models":
                    self._json(200, ui.list_models(query.get("base_url", [""])[0]))
                elif path == "/api/presets":
                    self._json(200, {"presets": ui.list_presets()})
                elif path == "/api/fe/config":
                    self._json(200, ui.fe_load_config(
                        str(query.get("fe_id", [""])[0])))
                elif path == "/api/plugins":
                    self._json(200, {"plugins": ui.list_plugins()})
                elif path == "/api/plugins/dirs":
                    self._json(200, {"dirs": ui.get_plugin_dirs()})
                elif path == "/api/security":
                    self._json(200, ui.get_security())
                elif path == "/api/health":
                    self._json(200, ui.health())
                elif path == "/api/streams":
                    # SSE backpressure config query + runtime hot change (high-concurrency ops)
                    self._json(200, ui.streams_info())
                elif path == "/api/usage":
                    self._json(200, ui.usage())
                elif path == "/api/balance":
                    self._json(200, {"balance": None, "error": None})
                elif path == "/api/debug":
                    self._json(200, ui.debug_info())
                elif path == "/api/evolution/points":
                    self._json(200, ui.evolution_points())
                elif path == "/api/evolution/proposals":
                    status = str(query.get("status", [""])[0] or "") or None
                    self._json(200, ui.evolution_proposals(status))
                elif path == "/api/evolution/log":
                    n = int(query.get("n", ["50"])[0] or 50)
                    self._json(200, ui.evolution_log(n))
                elif path == "/api/evolution/export":
                    kind = str(query.get("kind", ["settings"])[0] or "settings")
                    author = str(query.get("author", [""])[0] or "")
                    try:
                        body, fname, mime = ui.evolution_export(kind, author=author)
                        self._attach(body, fname, mime)
                    except Exception as exc:  # noqa: BLE001 — 导出失败如实报错
                        self._json(500, {"ok": False,
                                         "error": f"{type(exc).__name__}: {exc}"})
                elif path == "/api/settings/schema":
                    # 设置事实源（§5 / §6.3）：注册表（支持 category / view 过滤）
                    self._json(200, ui.settings_schema(
                        category=str(query.get("category", [""])[0] or "") or None,
                        view=str(query.get("view", [""])[0] or "") or None))
                elif path == "/api/settings/values":
                    self._json(200, ui.settings_values())
                elif path == "/api/settings/audit":
                    n = int(query.get("n", ["50"])[0] or 50)
                    self._json(200, ui.settings_audit(n))
                elif path == "/api/settings/export":
                    try:
                        body, fname, mime = ui.settings_export()
                        self._attach(body, fname, mime)
                    except Exception as exc:  # noqa: BLE001 — 导出失败如实报错
                        self._json(500, {"ok": False,
                                         "error": f"{type(exc).__name__}: {exc}"})
                elif path == "/api/whitebox/overview":
                    # 白盒总览（§4）：环节树统一遍历（可看 / 可测 / 可改 / 可设）
                    self._json(200, ui.whitebox_overview())
                elif path == "/api/snapshots":
                    # work rollback: snapshot timeline (the rollback panel's data source)
                    self._json(200, ui.recovery_handle("list", {}))
                elif path == "/api/flow/snapshot":
                    self._json(200, ui.flow_snapshot())
                elif path == "/api/flow/load":
                    self._json(200, ui.flow_load())
                elif path.startswith("/fe/"):
                    # FE frontend module hosting: the standalone frontend visited by "open in a new tab"
                    fname = path[len("/fe/"):]
                    body, mime = ui.fe_read_file(fname)
                    if body is None:
                        self._json(404, {"error": "frontend module not found"})
                    else:
                        self.send_response(200)
                        self.send_header("Content-Type", mime + "; charset=utf-8")
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                elif path == "/api/memory":
                    # 会话记忆读取（星轨控制台外部通道；?session_id= 省略 → 最近会话）
                    self._json(200, ui.memory_read(
                        str(query.get("session_id", [""])[0] or "")))
                elif path == "/api/fs/list":
                    q = parse_qs(parsed.query)
                    self._json(200, ui.list_fs(
                        q.get("path", [""])[0],
                        include_files=q.get("files", ["0"])[0] == "1",
                    ))
                elif path == "/api/fs/read":
                    q = parse_qs(parsed.query)
                    self._json(200, ui.read_fs_file(q.get("path", [""])[0]))
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self):  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/chat":
                    data = self._read_json(limit=_MAX_UPLOAD_JSON)
                    prompt = str(data.get("prompt") or "").strip()
                    attachments = data.get("attachments")
                    if not prompt and not (isinstance(attachments, list) and attachments):
                        self._json(400, {"ok": False, "error": "prompt is empty"})
                        return
                    task_params: Dict[str, Any] = {}
                    if isinstance(attachments, list) and attachments:
                        task_params["attachments"] = attachments
                    # per-message reasoning strength from the input-bar control
                    # (off / low / medium / high / max); an explicit value wins
                    # over the settings default inside _compose_task_params.
                    effort = _think_to_effort(data.get("think_level"))
                    if effort:
                        task_params["reasoning_effort"] = effort
                    task_id = ui.submit(
                        prompt, str(data.get("session_id") or "") or None,
                        task_params or None,
                    )
                    self._json(200, {
                        "ok": True, "task_id": task_id,
                        "session_id": ui._tasks.get(task_id, {}).get("session_id"),
                    })
                elif path == "/answer":
                    data = self._read_json()
                    ui.answer(
                        str(data.get("question_id") or ""),
                        str(data.get("answer") or ""),
                        str(data.get("session_id") or "") or None,
                    )
                    self._json(200, {"ok": True})
                elif path == "/stop":
                    data = self._read_json()
                    ui.stop_task(str(data.get("session_id") or "") or None)
                    self._json(200, {"ok": True})
                elif path == "/api/cnb/ctrl":
                    # FarStars 星轨控制台：同源中枢控制代理（base 仅回环）。
                    # body 原样作为 /cnb/ctrl 请求转发（topo/reports/audit/
                    # behavior/exec/freeze/sweep/config...）。
                    _q = parse_qs(parsed.query)
                    base = str(_q.get("base", [""])[0] or "").strip()
                    body = self._read_json()
                    self._json(200, ui.cnb_proxy("POST", base, ctrl=body))
                elif path == "/api/cnb/launch":
                    # 星轨控制台：一键拉起 CNB（中枢 / 节点，托管在本进程）
                    data = self._read_json()
                    self._json(200, ui.cnb_launch(data))
                elif path == "/api/cnb/stop":
                    # 星轨控制台：停止托管中的 CNB 实例（node_id 省略 = 全部）
                    data = self._read_json()
                    self._json(200, ui.cnb_stop(data))
                elif path == "/api/sessions":
                    data = self._read_json()
                    try:
                        sess = ui.create_session(
                            title=str(data.get("title") or ""),
                            workspace=str(data.get("workspace") or ""),
                        )
                        self._json(200, sess)
                    except Exception as exc:  # noqa: BLE001
                        self._json(500, {"error": str(exc)})
                elif path == "/api/sessions/clear":
                    # chat 批量清除 / 清空全部（2026-09-12）：ids 省略 = 全部
                    data = self._read_json()
                    ids = data.get("ids")
                    if ids is not None and not isinstance(ids, list):
                        self._json(400, {"error": "ids must be a list"})
                        return
                    self._json(200, ui.clear_sessions(ids))
                elif path.startswith("/api/sessions/"):
                    self._handle_session_post(path, data=self._read_json())
                elif path == "/api/config":
                    data = self._read_json()
                    self._json(200, {"ok": True, "config": ui.save_config(
                        data.get("config") or {})})
                elif path == "/api/system_prompt/global":
                    # editable global system prompt (from the "system prompt" dialog;
                    # applies to every session immediately, existing ones included)
                    data = self._read_json()
                    self._json(200, ui.set_global_system_prompt(
                        str(data.get("prompt") or "")))
                elif path == "/api/models":
                    # "fetch model list": directly use the current Key/Base from
                    # the form (applied immediately; no save needed); on success
                    # the remote model cache updates (shown in the flow module dock)
                    data = self._read_json()
                    self._json(200, ui.list_models(
                        str(data.get("base_url") or ""),
                        str(data.get("api_key") or "") or None,
                    ))
                elif path == "/api/fe/config":
                    data = self._read_json()
                    self._json(200, ui.fe_save_config(
                        str(data.get("fe_id") or ""),
                        data.get("config") or {},
                    ))
                elif path == "/api/config/reset":
                    self._json(200, {"ok": True, "config": ui.reset_config()})
                elif path == "/api/key":
                    data = self._read_json()
                    self._json(200, ui.set_api_key(str(data.get("api_key") or "")))
                elif path == "/api/key/validate":
                    data = self._read_json()
                    self._json(200, ui.validate_api_key(
                        str(data.get("api_key") or ""),
                        str(data.get("base_url") or ""),
                    ))
                elif path == "/api/upload":
                    data = self._read_json(limit=_MAX_UPLOAD_JSON)
                    files = data.get("files")
                    if not isinstance(files, list):
                        self._json(400, {"error": "files must be a list"})
                        return
                    self._json(200, {"files": ui.upload_files(files)})
                elif path == "/api/vision":
                    data = self._read_json(limit=_MAX_UPLOAD_JSON)
                    self._json(200, ui.vision_describe(data))
                elif path == "/api/tts":
                    data = self._read_json(limit=_MAX_JSON)
                    self._json(200, ui.tts_speak(data))
                elif path == "/api/stt":
                    data = self._read_json(limit=_MAX_UPLOAD_JSON)
                    self._json(200, ui.stt_transcribe(data))
                elif path == "/api/beep":
                    data = self._read_json()
                    self._json(200, ui.beep_notify(data))
                elif path == "/api/plugins/dirs":
                    data = self._read_json()
                    self._json(200, {"ok": True, "dirs": ui.add_plugin_dir(
                        str(data.get("path") or ""))})
                elif path == "/api/plugins/reload":
                    self._json(200, {"ok": True, "plugins": ui.reload_plugins()})
                elif path == "/api/plugins/toggle":
                    # enable / disable a single plugin (persisted in plugin_disabled)
                    data = self._read_json()
                    self._json(200, {"ok": True, "plugins": ui.set_plugin_enabled(
                        str(data.get("name") or ""),
                        bool(data.get("enabled", True)))})
                elif path == "/api/plugins/remove":
                    # uninstall: delete the plugin's file (or package directory)
                    data = self._read_json()
                    self._json(200, ui.delete_plugin(str(data.get("name") or "")))
                elif path == "/api/plugins/upload":
                    # install: upload a single-file .py plugin into the first plugin dir
                    data = self._read_json(limit=_MAX_UPLOAD_JSON)
                    self._json(200, ui.install_plugin_file(
                        str(data.get("filename") or ""),
                        str(data.get("content") or ""),
                        bool(data.get("base64", True)),
                    ))
                elif path == "/api/security":
                    data = self._read_json()
                    self._json(200, ui.set_security(data))
                elif path == "/api/snapshots":
                    # work rollback: capture / undo / redo / rollback / mark_good
                    data = self._read_json()
                    action = str(data.get("action") or "")
                    payload = data.get("payload")
                    if not isinstance(payload, dict):
                        payload = {}
                    self._json(200, ui.recovery_handle(action, payload))
                elif path == "/api/memory/clear":
                    # 会话记忆清除（真实删除；反馈轮 2 修复空实现假成功）
                    data = self._read_json()
                    self._json(200, ui.memory_clear(data))
                elif path == "/api/evolution/points":
                    data = self._read_json()
                    self._json(200, ui.evolution_set_point(data))
                elif path == "/api/evolution/import":
                    data = self._read_json(limit=_MAX_UPLOAD_JSON)
                    self._json(200, ui.evolution_import(data))
                elif path == "/api/evolution/proposals":
                    # 提案引擎 / 熔断（§7.1）：create / decide / execute / resume
                    data = self._read_json()
                    self._json(200, ui.evolution_proposals_action(data))
                elif path == "/api/settings/set":
                    # 设置事实源写入（§5 / §6.3；schema 校验 + 桥接热应用）
                    data = self._read_json()
                    self._json(200, ui.settings_set(data))
                elif path == "/api/settings/import":
                    data = self._read_json(limit=_MAX_UPLOAD_JSON)
                    self._json(200, ui.settings_import(data))
                elif path == "/api/log":
                    data = self._read_json()
                    self._json(200, ui.frontend_log(data))
                elif path == "/api/fs/mkdir":
                    data = self._read_json()
                    self._json(200, ui.make_fs_dir(
                        str(data.get("parent") or ""),
                        str(data.get("name") or ""),
                    ))
                elif path == "/api/quit":
                    self._json(200, {"ok": True})
                    ui.request_quit()
                elif path == "/api/flow/run":
                    data = self._read_json(limit=_MAX_JSON)
                    self._json(200, ui.flow_run(data))
                elif path == "/api/flow/save":
                    data = self._read_json(limit=_MAX_JSON)
                    self._json(200, ui.flow_save(data))
                elif path == "/api/flow/stop":
                    data = self._read_json()
                    self._json(200, ui.flow_stop(
                        str(data.get("flow_id") or "")))
                elif path == "/api/flow/register":
                    data = self._read_json(limit=_MAX_UPLOAD_JSON)
                    self._json(200, ui.flow_register(
                        str(data.get("name") or ""),
                        str(data.get("content") or "")))
                elif path == "/api/agent/tools":
                    data = self._read_json()
                    self._json(200, ui.set_agent_tools(data))
                elif path == "/api/streams":
                    # runtime hot change of SSE backpressure (no restart; effective immediately on existing connections)
                    data = self._read_json()
                    self._json(200, ui.set_sse_queue(
                        data.get("sse_queue_size"),
                        data.get("sse_queue_policy"),
                    ))
                else:
                    self._json(404, {"error": "not found"})

            def _drain_body(self, limit: int = _MAX_JSON) -> None:
                """Consume leftover request-body bytes so keep-alive parsing stays aligned.

                Browsers may attach a body to DELETE (the page sends ``{}``); when
                a handler ignores it, the unread bytes become the prefix of the
                next request line on the same connection ("{}DELETE") and the
                stdlib answers 501 Unsupported method. Reading them here prevents
                that keep-alive desynchronization (HTTP/1.1 connections are reused
                heavily by the page, batch deletes fire many requests in a row).
                """
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    length = 0
                if length <= 0:
                    return
                if length > limit:
                    self.close_connection = True
                    return
                try:
                    while length > 0:
                        chunk = self.rfile.read(length)
                        if not chunk:
                            break
                        length -= len(chunk)
                except _CLIENT_GONE_ERRORS:
                    self.close_connection = True

            def do_DELETE(self):  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path
                if path.startswith("/api/sessions/"):
                    # the page sends "{}" as the DELETE body; drain it before
                    # responding, otherwise the next keep-alive request line on
                    # this connection starts with the leftover bytes → 501.
                    self._drain_body()
                    sid = path[len("/api/sessions/"):].strip("/")
                    self._json(200, ui.close_session(sid))
                elif path == "/api/plugins/dirs":
                    data = self._read_json()
                    self._json(200, {"ok": True, "dirs": ui.remove_plugin_dir(
                        str(data.get("path") or ""))})
                else:
                    self._json(404, {"error": "not found"})

            # ── subroutes ─────────────────────────────────

            def _handle_session_get(self, path: str) -> None:
                rest = path[len("/api/sessions/"):].strip("/")
                parts = rest.split("/")
                sid = parts[0] if parts else ""
                if not sid:
                    self._json(404, {"error": "session id missing"})
                    return
                if len(parts) == 1:
                    self._json(200, {"session": ui.session_info(sid)})
                elif parts[1] == "messages":
                    self._json(200, {"messages": ui.session_messages(sid)})
                elif parts[1] == "variants":
                    self._json(200, ui.session_variants(sid))
                elif parts[1] == "system_prompt":
                    self._json(200, ui.session_system_prompt(sid))
                else:
                    self._json(404, {"error": "not found"})

            def _handle_session_post(self, path: str, data: dict) -> None:
                rest = path[len("/api/sessions/"):].strip("/")
                parts = rest.split("/")
                sid = parts[0] if parts else ""
                if len(parts) >= 2:
                    if parts[1] == "title":
                        # rename (persisted; 2026-09-12 round 9)
                        self._json(200, ui.set_session_title(
                            sid, str(data.get("title") or "")))
                        return
                    if parts[1] == "pin":
                        # pin / unpin to the top of the list (2026-09-12 round 9)
                        self._json(200, ui.set_session_pinned(
                            sid, bool(data.get("pinned"))))
                        return
                    if parts[1] == "workspace":
                        ui.set_session_workspace(sid, str(data.get("workspace") or ""))
                        self._json(200, {"ok": True})
                        return
                    if parts[1] == "system_prompt":
                        # per-session system prompt: text + append/replace mode
                        self._json(200, ui.set_session_system_prompt(
                            sid, str(data.get("prompt") or ""),
                            str(data.get("mode") or "append")))
                        return
                    if parts[1] == "truncate":
                        # rewind: keep the first N messages (regenerate / edit a turn)
                        self._json(200, ui.truncate_session(
                            sid, int(data.get("keep") or 0)))
                        return
                    if parts[1] == "rewind":
                        # rewind: drop the turn-th user message (0-based) and
                        # everything after it, resolving the cutoff on the server
                        # (regenerate / edit a turn — robust to local messages).
                        if "turn" not in data:
                            self._json(400, {"ok": False, "error": "turn required"})
                            return
                        self._json(200, ui.rewind_turn(
                            sid, int(data.get("turn") or 0),
                            bool(data.get("snapshot", True))))
                        return
                    if parts[1] == "variants" and len(parts) >= 3:
                        if parts[2] == "snapshot":
                            self._json(200, ui.variant_snapshot(
                                sid, int(data.get("turn") or 0),
                                int(data.get("keep") or 0)))
                            return
                        if parts[2] == "restore":
                            self._json(200, ui.variant_restore(
                                sid, int(data.get("turn") or 0),
                                int(data.get("index") or 0)))
                            return
                self._json(404, {"error": "not found"})

            def _handle_sse(self) -> None:
                """SSE long connection: batched frame writes + bounded backpressure + fast disconnect reclamation.

                - batched frame writes: one write + flush once ``_sse_batch``
                  frames accumulate or ``_sse_batch_interval`` seconds elapse —
                  system-call count drops drastically under high-frequency
                  streaming token pushes;
                - backpressure: one ``_SSESubscriber`` bounded buffer per
                  connection (size / policy configurable at startup and
                  hot-changeable at runtime); slow clients drop events (oldest by
                  default) instead of dragging down the publisher or eating memory
                  unboundedly;
                - disconnect reclamation: after a TCP half-close the first write
                  does not error (writes still work after FIN), so only
                  heartbeats would notice, with up to 15s latency — an idle
                  poll every 1s probes connection readability with non-blocking
                  select (FIN visible immediately), releasing the thread and
                  buffer within ≤1s after a disconnect (prevents thread
                  accumulation under extreme concurrency); the heartbeat comment
                  still runs every 15s, adding no network burden.
                """
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                # reverse proxies (nginx etc.) must disable response buffering,
                # otherwise SSE gets delayed in batches
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                sub = ui._new_subscriber()
                batch = ui._sse_batch
                interval = ui._sse_batch_interval
                pending: List[bytes] = []
                last_keepalive = time.monotonic()

                def _client_readable() -> bool:
                    """Whether the connection is readable (peer sent data or closed; SSE clients should not send data)."""
                    try:
                        readable, _, _ = select.select(
                            [self.connection], [], [], 0)
                        return bool(readable)
                    except OSError:
                        return True

                def _flush() -> None:
                    if pending:
                        self.wfile.write(b"".join(pending))
                        self.wfile.flush()
                        pending.clear()

                try:
                    # first replay recent history (one batched write)
                    recent = ui._recent_history()
                    if recent:
                        self.wfile.write(b"".join(
                            _encode_sse_frame(item) for item in recent))
                        self.wfile.flush()
                    while True:
                        # with a backlog, wait by the batch interval (new events
                        # wake and join the batch anytime); when idle, wake every
                        # 1s for a disconnect probe; heartbeat comments still run
                        # on a 15s cadence.
                        timeout = min(interval, 1.0) if pending else 1.0
                        item = sub.wait(timeout)
                        if item is not None:
                            pending.append(_encode_sse_frame(item))
                            if len(pending) >= batch:
                                _flush()
                            continue
                        if _client_readable():
                            break  # client disconnected: reclaim the thread and buffer immediately
                        if pending:
                            # batch window ended: flush the remaining frames
                            # (single-event stream latency ≤ sse_batch_interval)
                            _flush()
                        else:
                            now = time.monotonic()
                            if now - last_keepalive >= 15.0:
                                self.wfile.write(b": keepalive\n\n")
                                self.wfile.flush()
                                last_keepalive = now
                except (_CLIENT_GONE_ERRORS, OSError):
                    pass
                finally:
                    ui._drop_subscriber(sub)

        # load disk state once at startup (zero disk I/O at construction; embedded optimization)
        self._ensure_disk_loaded()
        self._server = self._bind(_Handler)
        # port=0 or port shifting: the actual bind result is authoritative (used for the listening-on print)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(
            target=self._serve, daemon=True, name="norpagent-webui"
        )
        self._thread.start()
        return self

    def _bind(self, handler_cls: type) -> "_RobustHTTPServer":
        """Bind the listen port: retry with the next port when occupied; raise a clear error on total failure."""
        in_use_errnos = (
            getattr(errno, "EADDRINUSE", -1),       # POSIX / Windows 10048
            getattr(errno, "WSAEADDRINUSE", -1),    # Windows 10048
            getattr(errno, "EACCES", -1),           # Linux privileged/reserved ports
            getattr(errno, "WSAEACCES", -1),        # Windows 10013: port occupied by a listener
        )
        last_exc: Optional[OSError] = None
        for offset in range(10):
            candidate = self.port + offset
            try:
                return _RobustHTTPServer((self.host, candidate), handler_cls)
            except OSError as exc:
                last_exc = exc
                if exc.errno not in in_use_errnos or offset >= 9:
                    break
                _logger.warning(
                    "port %s is in use; trying %s", candidate, candidate + 1
                )
        raise RuntimeError(
            f"cannot start the Web UI (bind failed on {self.host}:{self.port}): {last_exc}"
        ) from last_exc

    def _serve(self) -> None:
        """serve_forever wrapper: the daemon thread covers itself; abnormal exits do not spam the console."""
        server = self._server
        if server is None:
            return
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:  # pragma: no cover — defensive
            pass
        except Exception:  # noqa: BLE001
            _logger.exception("web server exited abnormally")
        finally:
            with self._lock:
                if self._server is server:
                    self._server = None

    def page_bytes(self, page: str = "front") -> bytes:
        """Return the page bytes: front = the main chat page (front.html),
        flow = the module-flow orchestration page (norp-flow.html),
        farstars = the FarStars console page (norp-farstars.html). Falls back to
        the built-in simple page when assets are missing.

        The front page prefers the custom content specified by the html mount
        parameter; the flow page prefers flow_html; the farstars page prefers
        farstars_html (file path or HTML content, resolved and cached at
        construction; hot-replaceable at runtime with mount_page()); the library
        built-in asset file is only read when nothing is mounted.

        v0.9 optimization: page bytes are cached in memory — under high
        concurrency, GET / no longer reads the disk repeatedly; but the cache
        records the resource's mtime/size signature and every page GET does one
        stat check: after physically replacing a library HTML file, a browser
        refresh takes effect automatically (hot-replacing the frontend needs no
        process restart), while cache hits still avoid open+read disk I/O.
        """
        override = (
            self._html_override if page == "front"
            else self._flow_html_override if page == "flow"
            else self._farstars_html_override if page == "farstars"
            else None
        )
        if override is not None:
            return override
        paths = {
            "front": _FRONT_HTML_PATH,
            "flow": _FLOW_HTML_PATH,
            "farstars": _FARSTARS_HTML_PATH,
        }
        path = paths.get(page, _FRONT_HTML_PATH)
        try:
            st = os.stat(path)
            sig = (st.st_mtime_ns, st.st_size)
        except OSError:
            # assets missing: fall back to the built-in simple page (not cached,
            # so fixing the file never stays stuck behind the old fallback).
            return _HTML_PAGE.encode("utf-8")
        cached = self._page_cache.get(page)
        if cached is not None and cached[0] == sig:
            return cached[1]
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return _HTML_PAGE.encode("utf-8")
        self._page_cache[page] = (sig, data)
        return data

    def asset_bytes(self, name: str) -> bytes:
        """Return a built-in shared asset's bytes（如 i18n.js；带 mtime 缓存）。

        路径限定在 assets 目录内（basename 过滤，防目录穿越）；缺失文件返回 b""。
        """
        safe = os.path.basename(str(name or ""))
        if not safe:
            return b""
        path = os.path.join(_ASSET_DIR, safe)
        try:
            st = os.stat(path)
            sig = (st.st_mtime_ns, st.st_size)
        except OSError:
            return b""
        key = f"asset:{safe}"
        cached = self._page_cache.get(key)
        if cached is not None and cached[0] == sig:
            return cached[1]
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return b""
        self._page_cache[key] = (sig, data)
        return data

    def mount_page(self, page: str, html: Optional[str]) -> bytes:
        """Hot-replace page bytes at runtime (HTTP service not restarted; port unchanged).

        - ``page``: "front" (/ route), "flow" (/flow route) or "farstars" (/farstars route);
        - ``html``: a file path or HTML content (starting with "<" after strip is
          treated as content, otherwise as a file path; a nonexistent file raises
          ValueError, same resolution rule as the constructor parameters html /
          flow_html);
        - ``html=None``: unmount the mount; fall back to the library built-in asset file.

        Returns the page bytes after mounting. Thread-safe (mutually exclusive with page GETs).
        """
        if page not in ("front", "flow", "farstars"):
            raise ValueError(
                f"mount_page only supports 'front' / 'flow' / 'farstars' pages, got {page!r}"
            )
        with self._lock:
            override = self._resolve_html(html)
            if page == "front":
                self._html_override = override
            elif page == "flow":
                self._flow_html_override = override
            else:
                self._farstars_html_override = override
            # invalidate the disk cache on unmount or page change: the next GET
            # re-reads per the latest resource signature, keeping fallback content consistent.
            self._page_cache.pop(page, None)
        return self.page_bytes(page)

    def request_quit(self) -> None:
        """Request the host application to quit (non-blocking)."""
        cb = self._quit_callback
        if cb is not None:
            threading.Thread(target=cb, daemon=True, name="norpagent-webui-quit").start()

    # ── task execution ────────────────────────────────────

    def _task_defaults(self) -> Dict[str, Any]:
        """Translate the settings panel's sampling parameters into task-level model parameters.

        - reasoning strength (think_level) → reasoning_effort (off = not passed; temperature applies);
        - temperature (omitted by the adapter when reasoning is on);
        - max_tokens.
        Injected via task_params, the AgentRuntime passes them verbatim to the model adapter.
        """
        with self._lock:
            think = str(self._config.get("think_level") or "high")
            temperature = self._config.get("temperature")
            top_p = self._config.get("top_p")
            call_timeout = self._config.get("call_timeout")
            max_tokens = self._config.get("max_tokens")
            ctx_budget = self._config.get("context_token_budget")
            max_steps = self._config.get("max_steps")
        effort = _THINK_LEVEL_MAP.get(think, "high")
        defaults: Dict[str, Any] = {}
        if effort != "none":
            defaults["reasoning_effort"] = effort
        else:
            try:
                defaults["temperature"] = float(temperature) if temperature is not None else 1.0
            except (TypeError, ValueError):
                defaults["temperature"] = 1.0
        # top_p (nucleus sampling; 1.0 = no truncation). Forwarded verbatim to the
        # adapter, which passes it to the endpoint alongside temperature.
        try:
            if top_p is not None:
                defaults["top_p"] = float(top_p)
        except (TypeError, ValueError):
            pass
        # per-call hard timeout (0 = unlimited): the kernel aborts a single model
        # call that exceeds it (AgentRuntime.params["call_timeout"]).
        try:
            if call_timeout:
                defaults["call_timeout"] = float(call_timeout)
        except (TypeError, ValueError):
            pass
        if max_tokens:
            try:
                defaults["max_tokens"] = int(max_tokens)
            except (TypeError, ValueError):
                pass
        # 2026-09-13: context window budget (0 = unlimited). Passed to the kernel,
        # which drops the oldest whole turns when the request would exceed it.
        try:
            if ctx_budget:
                defaults["context_token_budget"] = int(ctx_budget)
        except (TypeError, ValueError):
            pass
        try:
            if max_steps:
                defaults["max_steps"] = int(max_steps)
        except (TypeError, ValueError):
            pass
        return defaults

    def submit(self, prompt: str, session_id: Optional[str],
               task_params: Optional[Dict[str, Any]] = None) -> str:
        """Submit a task; executes in a background thread (does not block HTTP)."""
        sid = session_id or ""
        task_id = uuid.uuid4().hex[:12]
        record = {
            "task_id": task_id,
            "status": "running",
            "prompt": prompt,
            "session_id": sid,
            "result": None,
            "error": "",
        }
        with self._lock:
            self._tasks[task_id] = record
            self._task_session[task_id] = sid
            if sid:
                self._running_sessions[sid] = task_id
                # create the cancel event up-front (before the worker starts) so a
                # stop request arriving immediately is never missed
                self._stop_events[sid] = threading.Event()
            self._prune_tasks()
        self._publish({
            "type": "notify",
            "level": "info",
            "message": f"Task {task_id} submitted",
            "ts": time.time(),
            "sid": sid or None,
        })

        def worker() -> None:
            self._tlocal.session_id = sid
            try:
                active = self._active_chat_flow()
                if active is not None:
                    # "apply to agent" is active: chat tasks execute per the saved flow
                    result = self._run_flow_task(active, prompt, sid, task_id)
                else:
                    if self._handler_fn is None:
                        raise RuntimeError("WebUI has no execution callback (ui.set_handler(...))")
                    tp = self._compose_task_params(task_params, sid)
                    # v2.x multimodal attachments: route per settings (direct /
                    # service); service-routed items become text, direct ones stay
                    # native multimodal parts for the model.
                    final_prompt = prompt
                    prepared = self._prepare_chat_attachments(tp.get("attachments"))
                    if prepared is not None:
                        extra_text, media = prepared
                        if extra_text:
                            final_prompt = (prompt + "\n\n" + extra_text) if prompt else extra_text
                        tp["attachments"] = media or None
                    # immediate stop: hand the per-session cancel event to the task
                    # so the model streaming loop aborts mid-generation (checked on
                    # every chunk); _stop_check still covers step boundaries.
                    stop_ev = self._stop_events.get(sid)
                    if isinstance(stop_ev, threading.Event):
                        tp.setdefault("_cancel_event", stop_ev)
                        tp.setdefault(
                            "_stop_check",
                            lambda: stop_ev.is_set() or (sid in self._stop_requests),
                        )
                    else:
                        tp.setdefault("_stop_check", lambda: sid in self._stop_requests)
                    result = self._invoke_handler(self._handler_fn, final_prompt, sid, tp)
                status = getattr(result, "status", "done")
                content = getattr(result, "final_content", "") or ""
                error = getattr(result, "error", "") or ""
                record["status"] = status
                record["result"] = content
                record["error"] = error
                record["session_id"] = getattr(result, "session_id", "") or sid
                self._publish({
                    "type": "notify",
                    "level": "info" if status == "done" else "error",
                    "message": f"Task {task_id} finished ({status})",
                    "ts": time.time(),
                    "sid": getattr(result, "session_id", "") or sid or None,
                })
                # 2026-09-13: the first round has finished — auto-summarize the
                # session title with a separate one-off model call. Runs on its
                # own thread and never blocks or breaks the task result.
                try:
                    self._maybe_auto_title(getattr(result, "session_id", "") or sid)
                except Exception:  # noqa: BLE001 — titles must never break a task
                    pass
            except Exception as exc:  # noqa: BLE001
                record["status"] = "error"
                record["error"] = str(exc)
                self._publish({
                    "type": "notify",
                    "level": "error",
                    "message": f"Task {task_id} failed: {exc}",
                    "ts": time.time(),
                    "sid": sid or None,
                })
            finally:
                self._tlocal.session_id = None
                with self._lock:
                    self._task_session.pop(task_id, None)
                    if sid:
                        self._running_sessions.pop(sid, None)
                        self._stop_events.pop(sid, None)
                    self._stop_requests.discard(sid)

        threading.Thread(
            target=worker, daemon=True, name=f"norpagent-webui-task-{task_id}"
        ).start()
        return task_id

    def _compose_task_params(self, task_params: Optional[Dict[str, Any]],
                             sid: str) -> Dict[str, Any]:
        """Compose the task-level parameters of one chat submission (2026-09-12 round 9).

        Workspace root priority: explicit task params > per-session workspace >
        global config ``project_root`` (settings "workspace root" / composer
        workspace field). Previously the global value never reached the task —
        the file tools / sandbox kept using the process working directory, so
        changing the workspace directory looked like a no-op.
        """
        tp = dict(task_params or {})
        # the settings panel's sampling parameters inject into the task
        # (callers may override explicitly)
        for key, value in self._task_defaults().items():
            tp.setdefault(key, value)
        with self._lock:
            meta = dict(self._session_meta.get(sid) or {})
            global_root = str(self._config.get("project_root") or "").strip()
        if meta.get("workspace") and "workspace_root" not in tp:
            tp["workspace_root"] = str(meta["workspace"])
        if "workspace_root" not in tp and global_root:
            tp["workspace_root"] = global_root
        # per-session system prompt: composed fresh on every submission so a
        # global-prompt edit also reaches already-open sessions on their next
        # message (2026-09-13).
        if "system_prompt" not in tp:
            composed = self.compose_session_system_prompt(sid)
            if composed:
                tp["system_prompt"] = composed
        return tp

    # ── system prompt composition（2026-09-13）──────────────
    #
    # effective prompt = global base + per-session prompt
    #   global base  = settings "custom system prompt" when enabled and non-empty,
    #                  otherwise the engine preset's built-in prompt;
    #   per-session  = stored on the session (append after the base / replace it).
    # A session without its own prompt keeps the previous behaviour.
    def _preset_default_prompt(self) -> str:
        agent = self._agent
        if agent is None:
            return ""
        preset = getattr(agent, "preset", None)
        params = getattr(preset, "params", None) or {}
        try:
            return str(params.get("system_prompt") or "")
        except Exception:  # noqa: BLE001
            return ""

    def _global_system_prompt(self) -> str:
        """The settings-level global system prompt; empty when not enabled."""
        try:
            with self._lock:
                cfg = dict(self._config or {})
        except Exception:  # noqa: BLE001
            cfg = {}
        if not bool(cfg.get("custom_system_prompt_enabled", False)):
            return ""
        text = str(cfg.get("custom_system_prompt") or "").strip()
        if not text:
            path = str(cfg.get("custom_system_prompt_file") or "").strip()
            if path:
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        text = fh.read().strip()
                except OSError:
                    text = ""
        return text

    def _global_base_prompt(self) -> str:
        return self._global_system_prompt() or self._preset_default_prompt()

    def session_prompt_state(self, sid: str) -> Dict[str, Any]:
        """Return ``{prompt, mode}`` of a session (empty prompt when unset)."""
        prompt, mode = "", "append"
        if sid:
            try:
                sess = self._session_manager().get_session(sid)
            except Exception:  # noqa: BLE001
                sess = None
            if sess is not None:
                prompt = str(getattr(sess, "system_prompt", "") or "")
                mode = str(getattr(sess, "system_prompt_mode", "append") or "append")
        if mode not in ("append", "replace"):
            mode = "append"
        return {"prompt": prompt, "mode": mode}

    def compose_session_system_prompt(self, sid: str) -> str:
        base = self._global_base_prompt()
        state = self.session_prompt_state(sid)
        text = state["prompt"].strip()
        if not text:
            return base
        if state["mode"] == "replace":
            return text
        return (base + "\n\n" + text) if base.strip() else text

    def session_system_prompt(self, sid: str) -> Dict[str, Any]:
        state = self.session_prompt_state(sid)
        base = self._global_base_prompt()
        return {
            "ok": True,
            "session_id": sid,
            "prompt": state["prompt"],
            "mode": state["mode"],
            "global_prompt": base,
            "effective": self.compose_session_system_prompt(sid),
        }

    def set_session_system_prompt(self, sid: str, prompt: str,
                                  mode: str = "append") -> Dict[str, Any]:
        if not sid:
            return {"ok": False, "error": "session id required"}
        mode = "replace" if str(mode or "").strip().lower() == "replace" else "append"
        try:
            sm = self._session_manager()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if sm.get_session(sid) is None:
            return {"ok": False, "error": "session not found"}
        fn = getattr(sm, "set_system_prompt", None)
        if callable(fn):
            ok = bool(fn(sid, str(prompt or ""), mode))
        else:
            # fallback for custom managers without the optional capability
            sess = sm.get_session(sid)
            try:
                sess.system_prompt = str(prompt or "")
                sess.system_prompt_mode = mode
                ok = True
            except Exception:  # noqa: BLE001
                ok = False
        return {"ok": ok, "session_id": sid,
                "prompt": str(prompt or ""), "mode": mode}

    def set_global_system_prompt(self, text: str) -> Dict[str, Any]:
        """Update the settings-level global system prompt (applies to every session).

        Writes ``custom_system_prompt`` (+ its enable flag) and persists at once,
        so the next composed prompt of any session — new or existing — picks up
        the change without re-creating the session.
        """
        text = str(text or "")
        with self._lock:
            self._config["custom_system_prompt"] = text
            self._config["custom_system_prompt_enabled"] = bool(text.strip())
            self._config["_initialized"] = True
            cfg = dict(self._config)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
        self._mirror_settings_to_store(cfg)
        return {"ok": True, "global_prompt": self._global_base_prompt()}

    def stop_task(self, session_id: Optional[str]) -> None:
        """Request stopping the running task of a session.

        Immediate: the per-session cancel event is set synchronously, so the model
        streaming loop aborts mid-generation (not only at the next step boundary).
        """
        sid = session_id or ""
        runner = None
        stop_ev = None
        with self._lock:
            if sid and sid in self._running_sessions:
                self._stop_requests.add(sid)
            runner = self._chat_flow_runs.get(sid)
            stop_ev = self._stop_events.get(sid)
        # set the cancel event outside the lock: the running model stream polls it
        # on every chunk and unwinds at once (clearing the UI "generating" state)
        if stop_ev is not None:
            try:
                stop_ev.set()
            except Exception:  # noqa: BLE001 — a dead event must not break the request
                pass
        # a task executing under the active flow: send a stop signal directly to
        # the FlowRunner (the same node-boundary safe-wrap semantics as /api/flow/stop)
        if runner is not None:
            try:
                runner.request_stop()
            except Exception:  # noqa: BLE001
                pass

    # task-record history cap: a long-running WebUI must not let _tasks grow unboundedly
    _TASKS_HISTORY_LIMIT = 200

    def _prune_tasks(self) -> None:
        """Prune finished historical task records (call while holding the lock).

        Only the oldest non-running records are removed; running tasks are never
        pruned, so /api/tasks status queries and SSE replays are unaffected.
        """
        if len(self._tasks) <= self._TASKS_HISTORY_LIMIT:
            return
        overflow = len(self._tasks) - self._TASKS_HISTORY_LIMIT
        finished = [
            tid for tid, rec in self._tasks.items()
            if rec.get("status") != "running"
        ]
        for tid in finished[:overflow]:
            self._tasks.pop(tid, None)

    @staticmethod
    def _invoke_handler(fn: Callable, prompt: str, session_id: str,
                        task_params: Dict[str, Any]) -> Any:
        """Call the handler per its signature: declared task_params → pass task parameters; otherwise a two-argument call."""
        try:
            import inspect

            sig = inspect.signature(fn)
            accepts = (
                any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())
                or "task_params" in sig.parameters
            )
        except (TypeError, ValueError):
            accepts = False
        if accepts:
            return fn(prompt, session_id, task_params)
        return fn(prompt, session_id)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            tasks = list(self._tasks.values())
            subscribers = self._subscribers
        streams = self.streams_info()
        return {
            "ui": self.ui_id,
            "port": self.port,
            "subscribers": len(subscribers),
            "history": len(self._history),
            "tasks_total": len(tasks),
            "tasks_running": len(self._running_sessions),
            "language": self._config.get("language", "en"),
            "sse_queue_size": streams["sse_queue_size"],
            "sse_queue_policy": streams["sse_queue_policy"],
            "sse_dropped_total": streams["dropped_total"],
            "tasks": tasks[-20:],
        }

    # ── UIAdapter protocol ───────────────────────────────

    def on_event(self, event: Any) -> None:
        """Receive an AgentEvent: push it to all SSE subscribers and record it in history.

        The payload is first sanitized with json_safe (objects like ChatMessage
        fall into place safely), and every event gets a session id (sid) attached,
        letting the frontend route by tab.

        sid resolution priority: the task_id registered by submit() → the original
        browser session id (highest priority — preventing the kernel from opening
        another session on session drift and misdelivering events); only then the
        payload's own session_id.
        """
        raw_payload = getattr(event, "payload", {}) or {}
        payload = json_safe(raw_payload)
        task_id = payload.get("task_id")
        sid = None
        if task_id:
            with self._lock:
                sid = self._task_session.get(task_id)
        if not sid:
            sid = payload.get("session_id")
        if not sid:
            sid = getattr(self._tlocal, "session_id", None) or ""
        if task_id and sid:
            with self._lock:
                self._task_session.setdefault(task_id, sid)
        item = {
            "type": getattr(event, "type", "?"),
            "payload": payload,
            "ts": getattr(event, "ts", time.time()),
            "sid": sid or None,
        }
        # flatten common fields for direct frontend reads
        for key in ("content", "tool_name", "args", "result", "task_id",
                    "user_input", "error", "steps", "timeout", "stream",
                    "input", "output", "total", "session_id", "question",
                    "reason", "reasoning", "tool_call_tokens",
                    "gen_seconds", "stats", "estimated"):
            if key in payload:
                item[key] = payload[key]
        # usage accumulation
        if item["type"] == "on_usage_update":
            try:
                with self._lock:
                    self._usage["input_tokens"] += int(payload.get("input") or 0)
                    self._usage["output_tokens"] += int(payload.get("output") or 0)
                    self._usage["tool_call_tokens"] += int(payload.get("tool_call_tokens") or 0)
            except (TypeError, ValueError):
                pass
        self._publish(item)
        # security / sandbox interception -> prominent top-right alert
        _alert = self._security_alert_for(item)
        if _alert is not None:
            self._publish({
                "type": "security_alert",
                "level": _alert[0],
                "code": _alert[1],
                "message": _alert[2],
                "sid": sid or None,
                "ts": time.time(),
            })

    def _security_alert_for(self, item: Dict[str, Any]) -> Optional[tuple]:
        """Detect a security / sandbox interception in an agent event.

        Returns (level, message) where level is "danger" for a hard block and
        "warn" otherwise, or None when the event is not a security intervention.
        This is the single choke point where every subsystem's block (sandbox AST
        precheck, jailbreak/injection guard, hook veto, approval denial, SSRF
        network policy) is turned into a frontend alert — no per-tool plumbing.
        """
        etype = item.get("type") or ""
        payload = item.get("payload") or {}
        if not isinstance(payload, dict):
            return None
        text = ""
        struct: Dict[str, Any] = {}
        if etype == "after_tool_call":
            res = payload.get("result")
            if isinstance(res, dict):
                struct = res
                text = " ".join(str(res.get(k) or "") for k in ("output", "error"))
            else:
                text = str(res or "")
            text += " " + str(payload.get("error") or "")
        elif etype == "on_tool_error":
            text = " ".join(str(payload.get(k) or "") for k in ("error", "tool_name"))
        elif etype in ("on_task_stopped", "on_task_error"):
            struct = payload
            text = " ".join(str(payload.get(k) or "") for k in ("reason", "error", "detail"))
        else:
            return None
        text = text.strip()
        if not text:
            return None
        low = text.lower()
        for sig in _SEC_BLOCK_SIGNATURES:
            if sig.lower() in low:
                code = _sec_alert_code(text)
                level = _sec_alert_level(struct, payload, text, code)
                if _SEC_SEVERITY.get(level, 0) < self._sec_alert_threshold():
                    return None
                return (level, code, text[:300])
        return None

    def _sec_alert_threshold(self) -> int:
        """界面提示门槛（security.alert_level）。

        默认 major = 只提示「真被拦截」；off 全静默；normal / all 逐级放宽。
        读取失败时回落到 major（宁可少打扰）。结果缓存 5 秒，避免每个事件
        都去读设置库。
        """
        now = time.time()
        cached = getattr(self, "_sec_thr_cache", None)
        if cached and (now - cached[0]) < 5.0:
            return cached[1]
        try:
            value = self._settings_store().get("security.alert_level", "major")
            threshold = _SEC_THRESHOLD.get(str(value or "major"), 3)
        except Exception:
            threshold = 3
        self._sec_thr_cache = (now, threshold)
        return threshold

    def ask_user(self, question: str, default: str = "", kind: str = "") -> str:
        """Ask the user (human approval / clarification). Waits for the user to
        answer on the page; on timeout returns default, so automation scenarios
        never hang.

        ``kind`` is forwarded to the frontend so the modal can switch controls:
        ``"approval"`` hides the free-text box and shows only reject/approve,
        while a clarification keeps the text box.
        """
        question_id = uuid.uuid4().hex[:12]
        box = {"answer": None, "event": threading.Event()}
        sid = getattr(self._tlocal, "session_id", None) or ""
        if not sid:
            # fallback: outside a task thread (or lost thread context), the only
            # running session is the owner
            with self._lock:
                running = list(self._running_sessions.keys())
                if len(running) == 1:
                    sid = running[0]
        with self._lock:
            self._questions[question_id] = box
            if sid:
                self._question_sessions[sid] = question_id
        self._publish({
            "type": "question", "question": question,
            "kind": kind or "clarify",
            "question_id": question_id, "ts": time.time(),
            "sid": sid or None,
        })
        box["event"].wait(self.ask_timeout)
        with self._lock:
            self._questions.pop(question_id, None)
            if sid:
                self._question_sessions.pop(sid, None)
        answer = box["answer"]
        if answer is None:
            return default
        return str(answer)

    def answer(self, question_id: str, answer: str,
               session_id: Optional[str] = None) -> None:
        with self._lock:
            box = self._questions.get(question_id)
            if box is None and session_id:
                qid = self._question_sessions.get(session_id)
                box = self._questions.get(qid) if qid else None
        if box is not None:
            box["answer"] = answer
            box["event"].set()

    def notify(self, message: str, level: str = "info") -> None:
        self._publish({
            "type": "notify", "message": message,
            "level": level, "ts": time.time(),
            "sid": getattr(self._tlocal, "session_id", None),
        })

    # ── session REST ─────────────────────────────────────

    def _session_manager(self) -> Any:
        if self._agent is None:
            raise RuntimeError("runtime not bound (attach_runtime)")
        return self._agent.session_manager

    def create_session(self, title: str = "", workspace: str = "") -> Dict[str, Any]:
        sm = self._session_manager()
        sess = sm.create_session(title=title or "")
        ws = str(workspace or "").strip()
        if not ws:
            # 每会话独立工作区（2026-09-12）：未显式指定时，默认落在全局根目录下的
            # sessions/<sid> 子目录，物理隔离每个会话；全局根目录为空则不设（沿用
            # 运行态默认工作目录）。
            with self._lock:
                root = str(self._config.get("project_root") or "").strip()
            if root:
                ws = os.path.join(root, "sessions", sess.id)
                try:
                    os.makedirs(ws, exist_ok=True)
                except OSError:
                    ws = ""
        with self._lock:
            self._session_meta[sess.id] = {
                "title": title or sess.title or sess.id[:8],
                "workspace": ws,
                "created_at": getattr(sess, "created_at", time.time()),
            }
        self._save_session_meta()
        return self.session_info(sess.id)

    def session_info(self, sid: str) -> Dict[str, Any]:
        sm = self._session_manager()
        sess = sm.get_session(sid)
        with self._lock:
            meta = self._session_meta.get(sid) or {}
        if sess is None and not meta:
            return {"id": sid, "exists": False}
        created = meta.get("created_at") or getattr(sess, "created_at", 0.0)
        updated = getattr(sess, "updated_at", 0.0) or created
        return {
            "id": sid,
            "title": meta.get("title") or (getattr(sess, "title", "") or sid[:8]),
            "workspace": meta.get("workspace") or "",
            "created_at": created,
            "updated_at": max(updated, created or 0.0),
            "pinned": bool(meta.get("pinned")
                           if "pinned" in meta else getattr(sess, "pinned", False)),
            "exists": sess is not None,
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        sm = self._session_manager()
        sessions = sm.list_sessions()
        with self._lock:
            meta_map = dict(self._session_meta)
            running = set(self._running_sessions.keys())
        out = []
        for sess in sessions:
            meta = meta_map.get(sess.id) or {}
            created = meta.get("created_at") or getattr(sess, "created_at", time.time())
            updated = getattr(sess, "updated_at", 0.0) or created
            out.append({
                "id": sess.id,
                "title": meta.get("title") or getattr(sess, "title", "") or sess.id[:8],
                "workspace": meta.get("workspace") or "",
                "created_at": created,
                # last activity time: the front session list sorts by this field
                # (newest first) and buckets by date — 2026-09-12 round 9
                "updated_at": max(updated, created or 0.0),
                # user pinned to the top of the list — 2026-09-12 round 9
                "pinned": bool(meta.get("pinned")
                               if "pinned" in meta else getattr(sess, "pinned", False)),
                # front session-pill state: whether a task is currently running
                "running": sess.id in running,
                "has_task": bool(sess.id in running
                                 or getattr(sess, "message_count", 0)),
            })
        # pinned first, then last-activity descending (stable across stores)
        out.sort(key=lambda r: (
            0 if r.get("pinned") else 1,
            -(r.get("updated_at") or 0.0),
            -(r.get("created_at") or 0.0),
        ))
        return out

    def session_messages(self, sid: str) -> List[Dict[str, Any]]:
        """Display messages of a session (2026-09-12 round 9: ordered segments).

        Tool messages stay internal (not returned as standalone messages); each
        assistant message additionally carries ``segments`` (ordered
        think/output/tool blocks). Tool segments are filled with their execution
        result (joined from the following tool messages by tool_call id) so the
        front can re-render the interleaved timeline after a reload.
        """
        sm = self._session_manager()
        raw = list(sm.history(sid))
        # tool_call_id -> result text (for joining into the assistant segments)
        tool_results: Dict[str, str] = {}
        for m in raw:
            if (getattr(m, "role", "") or "") == "tool":
                cid = str(getattr(m, "tool_call_id", "") or "")
                if cid:
                    tool_results[cid] = str(getattr(m, "content", "") or "")
        messages: List[Dict[str, Any]] = []
        for ridx, m in enumerate(raw):
            role = getattr(m, "role", "") or ""
            if role == "tool":
                continue  # tool messages are internal process; not shown in the chat panel
            attachments = []
            for a in getattr(m, "attachments", None) or []:
                if not isinstance(a, dict):
                    continue
                attachments.append({
                    "kind": str(a.get("kind") or ""),
                    "name": str(a.get("name") or ""),
                    "mime": str(a.get("mime") or ""),
                    "route": str(a.get("route") or "direct"),
                })
            messages.append({
                "role": role,
                "content": getattr(m, "content", "") or "",
                # 思考过程随历史返回，前端切会话 / 空闲同步重绘后思考块不丢失
                "thinking": getattr(m, "reasoning", "") or "",
                # 有序分段（多段思考 / 多段输出 / 工具卡片）——多段工作回载的关键
                "segments": self._message_segments(m, tool_results),
                # 附件摘要（不携带 base64 数据）：历史回显附件标记
                "attachments": attachments,
                # 生成统计（token 速度 / 总 token / 生成时间）：刷新后仍可回显
                "stats": getattr(m, "stats", None) or None,
                # 原始消息下标（含内部 tool 消息）：重新生成 / 编辑对话的回退定位锚点
                "ridx": ridx,
            })
        return messages

    @staticmethod
    def _message_segments(message: Any,
                          tool_results: Dict[str, str]) -> List[Dict[str, Any]]:
        """Normalize the display segments of one assistant message.

        - stored ``segments`` are passed through (tool results joined);
        - legacy messages without segments are synthesized from reasoning/content;
        - best-effort: malformed entries are dropped instead of raising.
        """
        out: List[Dict[str, Any]] = []
        raw = getattr(message, "segments", None)
        if isinstance(raw, list) and raw:
            for item in raw:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("type") or "")
                if kind == "think":
                    text = str(item.get("text") or "")
                    if text:
                        out.append({"type": "think", "text": text})
                elif kind == "output":
                    text = str(item.get("text") or "")
                    if text:
                        out.append({"type": "output", "text": text})
                elif kind == "tool":
                    cid = str(item.get("id") or "")
                    result = str(item.get("result") or "")
                    if not result and cid:
                        result = tool_results.get(cid, "")
                    if len(result) > 4000:
                        result = result[:4000] + " …[truncated]"
                    status = str(item.get("status") or "")
                    if status == "running":
                        status = "ok" if result else "running"
                    out.append({
                        "type": "tool",
                        "id": cid,
                        "name": str(item.get("name") or "tool"),
                        "args": item.get("args") or {},
                        "status": status or ("ok" if result else "running"),
                        "result": result,
                    })
            if out:
                return out
        # legacy fallback: think block then output block
        thinking = str(getattr(message, "reasoning", "") or "")
        content = str(getattr(message, "content", "") or "")
        if thinking:
            out.append({"type": "think", "text": thinking})
        if content:
            out.append({"type": "output", "text": content})
        return out

    def close_session(self, sid: str) -> Dict[str, Any]:
        """Close (delete) one session; reports whether it was really removed.

        2026-09-12：删除结果如实回传（deleted / existed / error），
        供「清空全部 / 清除记忆」等路径如实记账，不再无条件默认成功。
        """
        self.stop_task(sid)
        deleted = False
        error = ""
        try:
            sm = self._session_manager()
            deleted = bool(sm.delete_session(sid))
        except Exception as exc:  # noqa: BLE001 — runtime not bound etc.
            error = f"{type(exc).__name__}: {exc}"
        with self._lock:
            had_meta = self._session_meta.pop(sid, None) is not None
        self._save_session_meta()
        return {"ok": True, "session_id": sid, "deleted": deleted,
                "existed": bool(deleted or had_meta), "error": error}

    def clear_sessions(self, ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """批量清除会话（chat「批量清除 / 清空全部」，2026-09-12）。

        ``ids`` 为 None/空 → 清空全部；给定列表 → 只清选中项。运行中的会话
        先停止任务再删除（close_session 语义，幂等）。返回实际删除清单与失败
        清单（反馈轮 2：删除失败不再谎报成功）。
        """
        if self._agent is None:
            return {"ok": False, "error": "engine not assembled (runtime not bound)"}
        try:
            all_sessions = self.list_sessions()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        targets = [str(s.get("id") or "") for s in all_sessions]
        targets = [t for t in targets if t]
        if ids:
            wanted = {str(i) for i in ids}
            targets = [t for t in targets if t in wanted]
        cleared: List[str] = []
        failed: List[str] = []
        for sid in targets:
            try:
                res = self.close_session(sid)
                (cleared if res.get("deleted") else failed).append(sid)
            except Exception:  # noqa: BLE001 — 单个失败不阻塞其余
                failed.append(sid)
        return {"ok": True, "cleared": cleared, "count": len(cleared),
                "failed": failed, "total": len(targets)}

    def memory_clear(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """清空会话记忆（星轨控制台「清除记忆」外部通道；2026-09-12 反馈轮 2）。

        - ``session_id`` 省略/为空 → 清空全部会话（真实删除；返回数量与失败清单）；
        - 给定 ``session_id`` → 只清该会话；
        - 引擎未装配 / 存储异常时如实返回 ``ok=False``（修复：原先为空实现，
          返回 ok 但什么都不删的假成功）。
        """
        if self._agent is None:
            return {"ok": False, "error": "engine not assembled (runtime not bound)"}
        payload = data if isinstance(data, dict) else {}
        sid = str(payload.get("session_id") or "").strip()
        if sid:
            res = self.close_session(sid)
            if res.get("error"):
                return {"ok": False, "scope": "session", "session_id": sid,
                        "error": res.get("error"), "count": 0, "cleared": []}
            cleared = [sid] if res.get("deleted") else []
            return {"ok": True, "scope": "session", "session_id": sid,
                    "cleared": cleared, "count": len(cleared),
                    "total": 1, "failed": [] if cleared else [sid]}
        result = self.clear_sessions(None)
        result["scope"] = "all"
        return result

    def memory_read(self, sid: str = "") -> Dict[str, Any]:
        """读取会话记忆（星轨控制台外部通道；``sid`` 为空 → 最近一次会话）。

        返回 ``content``：最近若干条非工具消息的纯文本（无会话 = None）。
        """
        if self._agent is None:
            return {"ok": False, "content": None,
                    "error": "engine not assembled (runtime not bound)"}
        try:
            sm = self._session_manager()
            if not sid:
                sessions = sm.list_sessions()
                sid = sessions[0].id if sessions else ""
            if not sid:
                return {"ok": True, "session_id": "", "content": None,
                        "messages": 0}
            messages = sm.history(sid)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "content": None,
                    "error": f"{type(exc).__name__}: {exc}"}
        lines: List[str] = []
        for m in messages[-20:]:
            role = getattr(m, "role", "") or ""
            if role == "tool":
                continue
            text = str(getattr(m, "content", "") or "").strip()
            if text:
                lines.append(f"[{role}] {text}")
        content = "\n".join(lines)
        if len(content) > 4000:
            content = content[-4000:]
        return {"ok": True, "session_id": sid, "content": content or None,
                "messages": len(messages)}

    # ── session title auto-summary (2026-09-13) ─────────────

    _TITLE_SYSTEM_PROMPT = (
        "You name chat sessions. Read the user's first request and the "
        "assistant's first reply, then output a concise title for the session. "
        "Rules: at most 6 words (or 16 Chinese characters); no quotes, no "
        "trailing punctuation, no explanation; output the title only."
    )

    def _title_provider(self, agent: Any) -> Any:
        """Provider used for title generation (a separate one-off call).

        Priority: the optional ``title_model`` config (a registered model name,
        or a remote model name mounted on the openai_compat adapter) > the
        session's current effective model. This keeps summarizing on a cheap
        model when the user configures one, without reusing the chat loop.
        """
        reg = getattr(agent, "registry", None)
        if reg is None:
            return None
        with self._lock:
            name = str(self._config.get("title_model") or "").strip()
        preset = getattr(agent, "preset", None)
        current = str(getattr(preset, "model", "") or "")
        if name and name != current:
            try:
                if name in reg.list_models():
                    return reg.resolve_model(name)
            except Exception:  # noqa: BLE001
                pass
            try:
                from norpagent.builtin.models.openai_compat import OpenAICompatProvider

                cfg = self._config
                return OpenAICompatProvider(
                    model_name=name,
                    base_url=str(cfg.get("api_base") or "") or None,
                    api_key=str(cfg.get("api_key") or "") or None,
                )
            except Exception:  # noqa: BLE001
                return None
        if current:
            try:
                return reg.resolve_model(current)
            except Exception:  # noqa: BLE001
                return None
        return None

    def _run_title_call(self, provider: Any, first_user: str,
                        first_assistant: str) -> str:
        """One-shot, tool-free model call summarizing the first round."""
        from norpagent.protocols.model import ChatMessage

        body = "User's first request:\n%s\n\nAssistant's first reply:\n%s" % (
            first_user[:4000], first_assistant[:4000])
        messages = [
            ChatMessage(role="system", content=self._TITLE_SYSTEM_PROMPT),
            ChatMessage(role="user", content=body),
        ]
        params = {"max_tokens": 32, "temperature": 0.3}
        text = ""
        gen = getattr(provider, "generate", None)
        if callable(gen):
            try:
                out = gen(messages, None, dict(params))
                text = str(getattr(out, "content", "") or "")
            except NotImplementedError:
                text = ""
            except Exception:  # noqa: BLE001 — fall back to streaming
                text = ""
        if not text:
            stream = getattr(provider, "stream", None)
            if callable(stream):
                try:
                    parts = []
                    for chunk in stream(messages, None, dict(params)):
                        parts.append(str(getattr(chunk, "delta_content", "") or ""))
                    text = "".join(parts)
                except Exception:  # noqa: BLE001
                    text = ""
        return self._clean_title(text)

    @staticmethod
    def _clean_title(text: str) -> str:
        """Normalize a model-produced title: first line, no quotes / markdown."""
        t = str(text or "").strip()
        if not t:
            return ""
        t = t.splitlines()[0].strip()
        t = t.strip("`*_# ").strip()
        if len(t) >= 2 and t[0] in "\"'“”‘’" and t[-1] in "\"'“”‘’":
            t = t[1:-1].strip()
        t = t.rstrip("。.,;；:：!！?？")
        t = t.strip()
        if len(t) > 60:
            t = t[:60].rstrip()
        return t

    def _maybe_auto_title(self, sid: str) -> None:
        """Summarize the first round into the session title (once, detached).

        Never blocks or breaks a task: it claims the session up-front, runs the
        one-off model call on its own daemon thread, and silently no-ops when the
        session is gone, is not on its first round, or was already titled.
        """
        if not sid:
            return
        with self._lock:
            if sid in self._auto_titled_sids:
                return
        agent = self._agent
        if agent is None:
            return
        sm = getattr(agent, "session_manager", None)
        if sm is None:
            return
        try:
            history = list(sm.history(sid))
        except Exception:  # noqa: BLE001
            return
        user_msgs = [m for m in history
                     if (getattr(m, "role", "") or "") == "user"]
        if len(user_msgs) != 1:
            return  # only the first round is summarized
        first_user = str(getattr(user_msgs[0], "content", "") or "").strip()
        if not first_user:
            return
        first_assistant = ""
        for m in history:
            if (getattr(m, "role", "") or "") == "assistant":
                c = str(getattr(m, "content", "") or "").strip()
                if c:
                    first_assistant = c
                    break
        with self._lock:
            if sid in self._auto_titled_sids:
                return
            self._auto_titled_sids.add(sid)

        def gen() -> None:
            title = ""
            try:
                provider = self._title_provider(agent)
                if provider is not None:
                    title = self._run_title_call(
                        provider, first_user, first_assistant)
            except Exception:  # noqa: BLE001
                title = ""
            if not title:
                title = first_user.replace("\n", " ")[:24]
            if not title:
                return
            try:
                self.set_session_title(sid, title)
            except Exception:  # noqa: BLE001
                return
            self._publish({
                "type": "on_session_title",
                "sid": sid,
                "title": title,
                "ts": time.time(),
            })

        threading.Thread(target=gen, daemon=True,
                         name=f"norpagent-title-{sid[:8]}").start()

    def set_session_title(self, sid: str, title: str) -> Dict[str, Any]:
        """Rename a session (persisted through the session store; 2026-09-12 round 9).

        Previously the title only lived in the in-memory meta map / a transient
        Session object, so a rename was lost after a restart for SQLite sessions.
        """
        title = str(title or "").strip()
        with self._lock:
            meta = self._session_meta.setdefault(sid, {})
            meta["title"] = title
        self._save_session_meta()
        persisted = False
        try:
            sm = self._session_manager()
            setter = getattr(sm, "set_title", None)
            if callable(setter):
                persisted = bool(setter(sid, title))
            else:
                sess = sm.get_session(sid)
                if sess is not None:
                    sess.title = title
        except Exception:  # noqa: BLE001 — rename must not break the HTTP server
            pass
        return {"ok": True, "session_id": sid, "title": title,
                "persisted": persisted}

    def set_session_pinned(self, sid: str, pinned: bool) -> Dict[str, Any]:
        """Pin / unpin a session to the top of the list (persisted; 2026-09-12 round 9)."""
        pinned = bool(pinned)
        with self._lock:
            meta = self._session_meta.setdefault(sid, {})
            meta["pinned"] = pinned
        self._save_session_meta()
        persisted = False
        try:
            sm = self._session_manager()
            setter = getattr(sm, "set_pinned", None)
            if callable(setter):
                persisted = bool(setter(sid, pinned))
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "session_id": sid, "pinned": pinned,
                "persisted": persisted}

    def set_session_workspace(self, sid: str, workspace: str) -> None:
        with self._lock:
            meta = self._session_meta.setdefault(sid, {})
            meta["workspace"] = workspace
        self._save_session_meta()

    # ── per-session meta persistence (2026-09-14) ─────────
    # 每会话元数据（工作区 / 标题 / 置顶）此前只存在内存字典 self._session_meta 里，
    # 引擎重启即清零，会话工作区随之静默回退全局 project_root。以下把 meta 落盘并
    # 在启动时读回，修复「重启后每会话工作区丢失」的缺陷。

    def _session_meta_file(self) -> str:
        """会话元数据文件：与 webui 配置同目录。

        未配置磁盘路径（``config_path=""``，嵌入式 / 无持久化场景）时返回空串，
        调用方据此跳过读写——与 ``_save_config_to_disk`` 口径一致：**没有配置路径
        就不落盘**。绝不能悄悄写进用户家目录，也不该给会话操作平白增加磁盘延迟
        （曾因此让自动标题的竞态必输）。
        """
        cfg_path = str(getattr(self, "_config_path", "") or "").strip()
        if not cfg_path:
            return ""
        return os.path.join(os.path.dirname(os.path.abspath(cfg_path)),
                            "sessions_meta.json")

    def _save_session_meta(self) -> None:
        """原子落盘会话元数据（尽力而为：失败只记录，绝不拖垮请求）。"""
        path = self._session_meta_file()
        if not path:
            return          # 未配置磁盘路径：不落盘（内存态照常工作）
        try:
            with self._lock:
                sessions = {k: dict(v) for k, v in self._session_meta.items()
                            if isinstance(v, dict)}
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            payload = {"format": "norpagent-sessions-meta/1",
                       "updated_at": time.time(), "sessions": sessions}
            tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:  # noqa: BLE001 — 元数据落盘失败不影响会话功能
            _logger.debug("session meta save skipped", exc_info=True)

    def _load_session_meta(self) -> None:
        """启动时读回会话元数据；随后修补「meta 丢失但会话目录仍在」的历史会话。"""
        path = self._session_meta_file()
        if not path:
            self._heal_session_workspaces()
            return
        data = None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = None
        except Exception:  # noqa: BLE001 — 文件损坏不阻塞启动
            _logger.debug("session meta load skipped", exc_info=True)
            data = None
        if isinstance(data, dict) and isinstance(data.get("sessions"), dict):
            for sid, meta in data["sessions"].items():
                if isinstance(meta, dict):
                    self._session_meta[str(sid)] = dict(meta)
        self._heal_session_workspaces()

    def _heal_session_workspaces(self) -> None:
        """修补历史会话：会话存在、但 meta 完全缺失时，若其默认会话目录仍在，
        回填为该目录——否则会静默回退全局工作区（即本次修复的缺陷现象）。"""
        try:
            root = str(self._config.get("project_root") or "").strip()
            if not root:
                return
            sm = self._session_manager()
            sessions = sm.list_sessions()
        except Exception:  # noqa: BLE001 — 运行态未绑定时跳过
            return
        changed = False
        with self._lock:
            for sess in sessions:
                sid = str(getattr(sess, "id", "") or "")
                if not sid or sid in self._session_meta:
                    continue
                candidate = os.path.join(root, "sessions", sid)
                if os.path.isdir(candidate):
                    self._session_meta[sid] = {"workspace": candidate}
                    changed = True
        if changed:
            self._save_session_meta()

    def truncate_session(self, sid: str, keep: int) -> Dict[str, Any]:
        """Rewind a session to its first ``keep`` messages (regenerate / edit a turn).

        Drops the trailing messages from the session store so the edited / regenerated
        turn is submitted as the current message instead of piling up as history.
        """
        try:
            sm = self._session_manager()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "dropped": 0}
        fn = getattr(sm, "truncate", None)
        if not callable(fn):
            return {"ok": False, "error": "session store does not support truncate",
                    "dropped": 0, "session_id": sid}
        try:
            dropped = int(fn(sid, max(0, int(keep))) or 0)
        except Exception as exc:  # noqa: BLE001 — report honestly instead of faking success
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "dropped": 0, "session_id": sid}
        return {"ok": True, "session_id": sid, "keep": max(0, int(keep)),
                "dropped": dropped}

    def rewind_turn(self, sid: str, turn: int, snapshot: bool = True) -> Dict[str, Any]:
        """Rewind a session to the start of its ``turn``-th user message (0-based).

        The truncation point is resolved **on the server** by counting the
        session's own user messages — the caller never has to pass a raw index
        (``ridx``) that a locally-appended, not-yet-persisted message can
        invalidate. That fragile index was the cause of the regenerate / edit
        failure "cannot locate message" (无法定位该消息).

        When ``snapshot`` is true, the turn being replaced (its previous reply and
        its then-downstream) is first saved into the per-turn version store, so the
        ``< n/N >`` switcher can restore it. Returns the resolved ``keep`` plus the
        original user text, so the caller can resubmit even without its local copy.
        """
        try:
            sm = self._session_manager()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        try:
            turn = int(turn)
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad turn"}
        if turn < 0:
            return {"ok": False, "error": "turn out of range", "turn": turn}
        try:
            hist = list(sm.history(sid))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        seen = -1
        keep = None
        prompt = ""
        for i, m in enumerate(hist):
            if (getattr(m, "role", "") or "") == "user":
                seen += 1
                if seen == turn:
                    keep = i
                    prompt = str(getattr(m, "content", "") or "")
                    break
        if keep is None:
            return {"ok": False, "error": "turn out of range", "turn": turn,
                    "history": len(hist)}
        out: Dict[str, Any] = {"ok": True, "session_id": sid, "turn": turn,
                               "keep": keep, "prompt": prompt, "dropped": 0,
                               "count": 0, "active": -1}
        # remember the version being replaced BEFORE dropping it (best-effort)
        if snapshot and self._variants_supported():
            try:
                snap = self.variant_snapshot(sid, turn, keep)
                if isinstance(snap, dict):
                    out["count"] = int(snap.get("count", 0) or 0)
                    out["active"] = int(snap.get("active", -1))
            except Exception:  # noqa: BLE001 — a failed snapshot must not block the rewind
                pass
        fn = getattr(sm, "truncate", None)
        if not callable(fn):
            return {"ok": False, "error": "session store does not support truncate",
                    "turn": turn}
        try:
            out["dropped"] = int(fn(sid, keep) or 0)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "turn": turn}
        return out

    # ── branch / version store (regenerate version switching) ─────

    def _variants_supported(self) -> bool:
        try:
            sm = self._session_manager()
        except Exception:  # noqa: BLE001
            return False
        return callable(getattr(sm, "get_variants", None)) and \
            callable(getattr(sm, "set_variants", None))

    def session_variants(self, sid: str) -> Dict[str, Any]:
        """Per-turn branch / version metadata (count + active index) of a session.

        Persisted in the session store (2026-09-13) so the switcher survives a
        reload / restart. ``active == -1`` means the live store is the active view.
        """
        try:
            sm = self._session_manager()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "turns": {}}
        fn = getattr(sm, "get_variants", None)
        data = fn(sid) if callable(fn) else {}
        turns = data.get("turns") if isinstance(data, dict) else {}
        out: Dict[str, Any] = {}
        if isinstance(turns, dict):
            for key, entry in turns.items():
                if not isinstance(entry, dict):
                    continue
                versions = entry.get("versions") or []
                active = int(entry.get("active", -1))
                count = len(versions) + (1 if active == -1 else 0)
                out[str(key)] = {
                    "count": count,
                    "active": active,
                    "keep": int(entry.get("keep", 0) or 0),
                }
        return {"ok": True, "turns": out}

    def variant_snapshot(self, sid: str, turn: int, keep: int) -> Dict[str, Any]:
        """Snapshot the live tail (from ``keep``) as a new version of ``turn``.

        Called before regenerating / editing a turn: the previous output (and its
        then-downstream) is preserved so the switcher can bring it back.
        """
        if not self._variants_supported():
            return {"ok": False, "error": "session store does not support variants"}
        sm = self._session_manager()
        hist = list(sm.history(sid))
        keep = max(0, int(keep))
        snapshot = [m.to_dict() for m in hist[keep:]]
        data = sm.get_variants(sid) or {}
        turns = data.setdefault("turns", {})
        key = str(int(turn))
        entry = turns.setdefault(key, {"keep": keep, "versions": [], "active": -1})
        entry["keep"] = keep
        versions = entry.setdefault("versions", [])
        if not versions or versions[-1].get("messages") != snapshot:
            versions.append({"messages": snapshot})
        # a freshly snapshotted branch becomes the "previous" one; the live store
        # is the active view from now on (active = -1)
        entry["active"] = -1
        sm.set_variants(sid, data)
        count = len(versions) + 1
        return {"ok": True, "turn": int(turn), "count": count, "active": -1}

    def variant_restore(self, sid: str, turn: int, index: int) -> Dict[str, Any]:
        """Switch a turn to a stored version (replaces the live tail)."""
        if not self._variants_supported():
            return {"ok": False, "error": "session store does not support variants"}
        sm = self._session_manager()
        data = sm.get_variants(sid) or {}
        turns = data.get("turns") or {}
        key = str(int(turn))
        entry = turns.get(key)
        if not isinstance(entry, dict):
            return {"ok": False, "error": "no variants for this turn"}
        versions = entry.get("versions") or []
        index = int(index)
        if index < 0 or index >= len(versions):
            return {"ok": False, "error": "version index out of range", "count": len(versions)}
        keep = int(entry.get("keep", 0) or 0)
        if int(entry.get("active", -1)) == -1:
            # preserve the live tail before switching away from it
            hist = list(sm.history(sid))
            snapshot = [m.to_dict() for m in hist[keep:]]
            if not versions or versions[-1].get("messages") != snapshot:
                versions.append({"messages": snapshot})
        from norpagent.protocols.model import ChatMessage

        target = versions[index].get("messages") or []
        msgs = [ChatMessage.from_dict(d) for d in target]
        sm.replace_tail(sid, keep, msgs)
        entry["active"] = index
        sm.set_variants(sid, data)
        return {"ok": True, "turn": int(turn), "index": index,
                "active": index, "count": len(versions)}

    # ── config ───────────────────────────────────────────

    def _needs_key(self) -> bool:
        model = str(self._config.get("model") or "")
        return model in ("openai_compat", "anthropic")

    def first_run(self) -> bool:
        with self._lock:
            initialized = bool(self._config.get("_initialized"))
            has_key = bool(self._config.get("api_key"))
            needs = self._needs_key()
        return (not initialized) and needs and (not has_key)

    def list_presets(self) -> List[Dict[str, Any]]:
        """All registry presets (the data source of the front "mode" selector).

        Returns [{name, description, mode, model}]: name is the identifier passed
        back on switching; mode is single / ptc / custom (for display labels).
        ``*_arch`` derived presets (internal implementations rebuilt by the
        assembly layer on slot overrides) are not shown — they are implementation
        details; the base presets are the user-selectable modes.
        """
        reg = self._registry()
        if reg is None:
            return []
        out: List[Dict[str, Any]] = []
        for name in reg.list_presets():
            if name.endswith("_arch"):
                continue
            try:
                p = reg.resolve_preset(name)
            except Exception:  # noqa: BLE001 — preset resolution failures skip the item
                continue
            out.append({
                "name": str(getattr(p, "name", "") or name),
                "description": str(getattr(p, "description", "") or ""),
                "mode": str(getattr(p, "mode", "") or ""),
                "model": str(getattr(p, "model", "") or ""),
            })
        return out

    @staticmethod
    def _base_preset_name(name: str) -> str:
        """Derived preset name ``{base}_arch`` → base name (for front display and comparison)."""
        name = str(name or "")
        return name[:-5] if name.endswith("_arch") else name

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            cfg = dict(self._config)
        # never send the raw API key back to the page: only the has_api_key flag.
        # (the settings form does not display the key; it is re-sent only when
        # the user types a new one via /api/key)
        cfg.pop("api_key", None)
        cfg["has_api_key"] = bool(self._config.get("api_key")) or not self._needs_key()
        cfg["first_run"] = self.first_run()
        # the preset "actually effective" on the engine (the front "mode" selector's
        # initial display; the agent's held state is authoritative — the
        # preset_name in config may hold an invalid value (when a hot switch
        # failed); the agent state is the real result; derived names become base names)
        agent = self._agent
        preset = getattr(agent, "preset", None) if agent is not None else None
        raw = getattr(preset, "name", "") or ""
        if raw:
            cfg["current_preset"] = self._base_preset_name(raw)
        else:
            cfg["current_preset"] = self._base_preset_name(
                str(cfg.get("preset_name") or "")
            )
        # tool-mounting info: all registry tools (native / module) + the agent's
        # currently effective set + the preset default set
        cfg["tools_info"] = self.tools_info()
        cfg["agent_effective_tools"] = self.agent_effective_tools()
        cfg["agent_base_tools"] = list(self._agent_base_tools)
        return cfg

    def config_for_apply(self) -> Dict[str, Any]:
        """Full runtime config **including secrets** — for the local apply pipeline.

        The HTTP-facing :meth:`get_config` strips ``api_key``; the in-process
        startup restore (WebFrontend.restore_startup_config / CLI web runner)
        needs the plaintext key to register the model provider. Never serialize
        this dict into an HTTP response (2026-09-12 round 9).
        """
        with self._lock:
            return dict(self._config)

    # ── agent tool mounting (file-as-module → front auto-invocation) ──

    def agent_effective_tools(self) -> List[str]:
        """The front agent's currently effective tool set (preset.tools has been rewritten by config apply)."""
        agent = self._agent
        preset = getattr(agent, "preset", None) if agent is not None else None
        tools = getattr(preset, "tools", None) if preset is not None else None
        if tools is None:
            tools = list(self._agent_base_tools)
        return [str(t) for t in tools]

    def tools_info(self) -> List[Dict[str, Any]]:
        """Full registry tool list: {name, description, source, plugin}.

        source = native (built-in native tools) / plugin (tools registered by
        plugins and "file-as-module", both entering the registry via PluginLoader).
        """
        reg = self._registry()
        if reg is None:
            return []
        tool_plugin: Dict[str, str] = {}
        try:
            plugins = getattr(reg, "_plugins", {}) or {}
            for pname, p in plugins.items():
                get_tools = getattr(p, "get_tools", None)
                for t in (get_tools() if callable(get_tools) else ()) or ():
                    name = getattr(t, "name", "") or ""
                    if name:
                        tool_plugin[name] = pname
        except Exception:  # noqa: BLE001 — the list must never raise
            pass
        out: List[Dict[str, Any]] = []
        for name in reg.list_tools():
            desc = ""
            try:
                schema = reg.resolve_tool(name).schema() or {}
                func = schema.get("function", schema) if isinstance(schema, dict) else {}
                desc = str(func.get("description", "") or "").strip()
            except Exception:  # noqa: BLE001
                pass
            out.append({
                "name": str(name),
                "description": desc[:200],
                "source": "plugin" if name in tool_plugin else "native",
                "plugin": tool_plugin.get(name, ""),
            })
        return out

    def set_agent_tools(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Set the front agent's available tool set (the mount/unmount entry of file-as-module tools).

        ``tools`` = the explicit full tool set; when identical to the preset
        default set, it automatically falls back to non-explicit (following preset
        evolution). Hot-applied to the running agent via _apply_config; the next
        front chat takes effect (model tool calling works directly).
        """
        tools = data.get("tools") if isinstance(data, dict) else None
        if not isinstance(tools, list):
            return {"ok": False, "error": "tools must be a list of strings"}
        explicit = bool(data.get("explicit", True))
        reg = self._registry()
        valid = set(reg.list_tools()) if reg is not None else set()
        cleaned = sorted({str(t) for t in tools if str(t) in valid})
        with self._lock:
            base_sorted = sorted(self._agent_base_tools)
            if cleaned == base_sorted and not data.get("force_explicit"):
                # identical to the preset default: fall back to non-explicit so the
                # tool set follows preset evolution
                explicit = False
                cleaned = []
            self._config["agent_tools"] = cleaned
            self._config["agent_tools_explicit"] = bool(explicit)
            cfg = dict(self._config)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
        return {
            "ok": True,
            "agent_tools": self.agent_effective_tools(),
            "explicit": bool(explicit),
            "dropped": sorted(
                {str(t) for t in tools if str(t) not in valid}),
        }

    def save_config(self, incoming: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            for key, value in (incoming or {}).items():
                if key == "_initialized":
                    continue
                # Security master switches are honored, not forced: turning them
                # off is allowed, but the frontend gates it behind an explicit,
                # non-dismissable confirmation before it reaches this endpoint.
                if key in _SECRET_KEYS:
                    # accept plaintext or an already-encrypted (marker) value
                    self._config[key] = _decrypt_api_key(value)
                else:
                    self._config[key] = value
            self._config["_initialized"] = True
            cfg = dict(self._config)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
        # 设置事实源镜像（§5.3）：运行态配置 → 设置库
        self._mirror_settings_to_store(cfg)
        return self.get_config()

    def reset_config(self) -> Dict[str, Any]:
        with self._lock:
            model = self._config.get("model") or ""
            language = self._language
            self._config = dict(DEFAULT_CONFIG)
            self._config["language"] = language
            if model:
                self._config["model"] = model
            cfg = dict(self._config)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
        self._mirror_settings_to_store(cfg)
        return self.get_config()

    def set_api_key(self, api_key: str) -> Dict[str, Any]:
        with self._lock:
            self._config["api_key"] = _decrypt_api_key(api_key or "")
            self._config["_initialized"] = True
            cfg = dict(self._config)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
        self._mirror_settings_to_store(cfg)
        return {"ok": True, "config": self.get_config()}

    def validate_api_key(self, api_key: str, base_url: str = "") -> Dict[str, Any]:
        if not api_key:
            return {"ok": False, "error": "API key is empty"}
        try:
            import openai  # noqa: F401  optional dependency
        except ImportError:
            return {"ok": False, "error": "openai SDK not installed (pip install norpagent[openai]); cannot validate online"}
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=base_url or self._config.get("api_base")
                or "https://api.deepseek.com",
                api_key=api_key,
                timeout=15,
            )
            client.models.list()
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"invalid api key: {exc}"}

    def _apply_config(self, cfg: Dict[str, Any]) -> None:
        cb = self._config_apply
        if cb is not None:
            try:
                cb(cfg)
            except Exception:  # noqa: BLE001 — config-apply failures must not break the HTTP server
                _logger.exception("config apply failed")

    # ── config persistence (browser-frontend settings / API key kept across processes) ──

    def _load_config_from_disk(self) -> None:
        """Load the last-saved config from disk at startup (silently ignore missing / corrupt files).

        Only accepts keys declared in DEFAULT_CONFIG plus ``_initialized``;
        unknown keys are always discarded (preventing external writes from
        injecting unfamiliar config items). The persisted API key is decrypted
        (Windows DPAPI) into memory for direct use.
        """
        path = self._config_path
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        allowed = set(DEFAULT_CONFIG) | {"_initialized"}
        for key, value in data.items():
            if key in allowed:
                self._config[key] = value
        for secret in _SECRET_KEYS:
            if secret in self._config:
                self._config[secret] = _decrypt_api_key(
                    self._config.get(secret) or ""
                )
        # 设置事实源镜像（§5.3，2026-09-12）：运行态配置 → 设置库（失败不阻塞）
        self._mirror_settings_to_store()

    def _mirror_settings_to_store(self,
                                  cfg: Optional[Dict[str, Any]] = None) -> None:
        """运行态配置 → 设置库镜像（非密键；失败只记录，不拖垮请求 / 启动）。"""
        try:
            from norpagent.settings import ensure_schema, mirror_config_to_store

            mirror_config_to_store(
                cfg if isinstance(cfg, dict) else dict(self._config),
                store=ensure_schema(),
            )
        except Exception:  # noqa: BLE001 — 镜像尽力而为
            _logger.debug("settings mirror skipped", exc_info=True)

    def _save_config_to_disk(self, cfg: Dict[str, Any]) -> None:
        """Atomically write the config to disk (failures only log; never break the save flow).

        - only keys in DEFAULT_CONFIG plus ``_initialized`` are persisted;
        - temp file + os.replace atomic replacement, avoiding half-written corruption;
        - under POSIX, tighten permissions to 0600 (contains the API key);
        - the API key is encrypted before writing (Windows DPAPI; elsewhere kept
          as-is in the 0600 file), so the key is never stored in plaintext.
        """
        path = self._config_path
        if not path:
            return
        try:
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
            allowed = set(DEFAULT_CONFIG) | {"_initialized"}
            data = {k: v for k, v in cfg.items() if k in allowed}
            for secret in _SECRET_KEYS:
                if secret in data:
                    data[secret] = _encrypt_api_key(
                        str(data.get(secret) or "")
                    )
            tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(tmp, 0o600)
            except OSError:  # Windows has limited permission bits; ignore
                pass
            # on Windows the target file may be transiently locked (antivirus
            # scans etc.); retry on failure
            last_exc: Optional[OSError] = None
            for _ in range(3):
                try:
                    os.replace(tmp, path)
                    break
                except OSError as exc:  # noqa: BLE001
                    last_exc = exc
                    time.sleep(0.05)
            else:
                raise last_exc  # type: ignore[misc]
        except OSError as exc:  # noqa: BLE001
            _logger.warning("webui config write to %s failed: %s", path, exc)

    # ── models / plugins / security / stats ───────────────

    def _registry(self) -> Any:
        if self._agent is None:
            return None
        return getattr(self._agent, "registry", None)

    def list_models(self, base_url: str = "",
                    api_key: Optional[str] = None) -> Dict[str, Any]:
        """List models: registry models + remote models (when a base URL + key are available).

        Robustness (2026-09-12, 面板抓取修复):
        - **不读写 / 不清空密钥**——表单里刚输入的 key 直接用于抓取（无需先保存）；
        - base URL 容错：去尾斜杠、缺协议自动补 https://、空值回落到已保存 api_base；
        - 双路抓取：openai SDK 优先，失败自动回退 `GET {base}/models`（Bearer）；
        - 错误信息明确（缺 key / SDK 缺失 / 端点错误分别说明）；
        - 返回 registry / remote / models 三份列表：远端失败时下拉仍可用注册表模型。
        成功后把远端模型列表缓存进配置（remote_models）。
        """
        reg = self._registry()
        registry = sorted(reg.list_models()) if reg is not None else []
        remote: List[str] = []
        error: Optional[str] = None
        base = str(base_url or "").strip().rstrip("/")
        if not base:
            base = str(self._config.get("api_base") or "").strip().rstrip("/")
        if base and not re.match(r"^https?://", base, re.IGNORECASE):
            base = "https://" + base
        used_key = (str(api_key or "").strip()
                    or str(self._config.get("api_key") or "").strip())
        if base and not used_key:
            error = ("API key is empty: type it in the API key field "
                     "(no save needed before fetching).")
        elif base:
            sdk_error = ""
            try:
                from openai import OpenAI

                client = OpenAI(base_url=base, api_key=used_key, timeout=20)
                remote = [m.id for m in client.models.list()][:200]
            except ImportError:
                sdk_error = "openai SDK not installed (pip install norpagent[openai])"
                remote = []
            except Exception as exc:  # noqa: BLE001 — 回退到纯 HTTP
                sdk_error = f"{type(exc).__name__}: {exc}"
                remote = []
            if not remote:
                try:
                    req = urllib.request.Request(
                        base + "/models",
                        headers={"Authorization": f"Bearer {used_key}",
                                 "Accept": "application/json"})
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        payload = json.loads(
                            resp.read().decode("utf-8", errors="replace"))
                    data = payload.get("data") if isinstance(payload, dict) else None
                    if isinstance(data, list):
                        remote = [str(m.get("id")) for m in data
                                  if isinstance(m, dict) and m.get("id")][:200]
                except Exception as exc:  # noqa: BLE001 — 两路都失败：如实报错
                    if not sdk_error:
                        sdk_error = f"{type(exc).__name__}: {exc}"
            if remote:
                remote = filter_remote_models(remote)
                error = None
            else:
                error = sdk_error or "the endpoint returned no models"
        if remote:
            # remote model list cache: update memory + persist the config (failures do not block)
            with self._lock:
                self._config["remote_models"] = list(remote)
                cfg = dict(self._config)
            self._save_config_to_disk(cfg)
        models = list(dict.fromkeys(list(registry) + list(remote)))
        return {"models": models, "registry": registry, "remote": remote,
                "error": error, "base_url": base}

    def get_plugin_dirs(self) -> List[str]:
        with self._lock:
            dirs = self._config.get("plugin_dirs") or []
        return list(dirs)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List plugins.

        2026-09-11: prefers the loader's full record — failed / disabled / blocked
        plugins are included together with signature status, isolation mode,
        warnings, approval hints, audit issues, diagnostics and call counters.
        Falls back to the registered plugin objects when no loader is recorded.
        """
        reg = self._registry()
        if reg is None:
            return []
        loader = getattr(reg, "plugin_loader", None)
        if loader is not None:
            with self._lock:
                disabled_cfg = {str(n) for n in (self._config.get("plugin_disabled") or [])}
            out: List[Dict[str, Any]] = []
            for info in list(getattr(loader, "plugins", ()) or ()):
                rec = info.to_dict() if hasattr(info, "to_dict") else {}
                name = str(rec.get("name") or "")
                rec["disabled_in_config"] = name in disabled_cfg
                rec.setdefault("isolation", "inproc")
                # audit counters for the existing panels (derived from audit_issues)
                issues = rec.get("audit_issues") or []
                crit = sum(1 for i in issues
                           if str((i or {}).get("severity", "")).lower() == "critical")
                warn_cnt = sum(1 for i in issues
                               if str((i or {}).get("severity", "")).lower() == "warning")
                rec["audit_critical"] = crit
                rec["audit_warning"] = warn_cnt
                rec["audit_info"] = max(len(issues) - crit - warn_cnt, 0)
                rec["source"] = "loader"
                out.append(rec)
            if out:
                return out
        # fallback: registry-registered plugin objects (no loader record)
        plugins = getattr(reg, "_plugins", {}) or {}
        out = []
        for name in sorted(plugins):
            p = plugins[name]
            tools = []
            try:
                tools = [getattr(t, "name", "") or "" for t in p.get_tools()]
            except Exception:  # noqa: BLE001
                tools = []
            hooks = []
            try:
                hooks = list((p.get_hooks() or {}).keys())
            except Exception:  # noqa: BLE001
                hooks = []
            out.append({
                "name": name,
                "version": str(getattr(p, "version", "") or ""),
                "publisher": str(getattr(p, "publisher", "") or ""),
                "description": str(getattr(p, "description", "") or ""),
                "enabled": True,
                "error": "",
                "tools": tools,
                "hooks": hooks,
                "tool_count": len(tools),
                "hook_count": len(hooks),
                "audit_critical": 0,
                "audit_warning": 0,
                "audit_info": 0,
                "signature_status": "unknown",
                "isolation": "inproc",
                "source": "registry",
            })
        return out

    def set_plugin_enabled(self, name: str, enabled: bool) -> List[Dict[str, Any]]:
        """Enable / disable one plugin: persisted in the config (plugin_disabled) and reloaded."""
        name = (name or "").strip()
        if name:
            with self._lock:
                disabled = [str(n) for n in (self._config.get("plugin_disabled") or [])]
                if enabled:
                    disabled = [n for n in disabled if n != name]
                else:
                    if name not in disabled:
                        disabled.append(name)
                self._config["plugin_disabled"] = disabled
                self._config["_initialized"] = True
                cfg = dict(self._config)
            self._save_config_to_disk(cfg)
            self._apply_config(cfg)
        return self.list_plugins()

    def delete_plugin(self, name: str) -> Dict[str, Any]:
        """Uninstall one plugin: delete its file (or package directory) and reload.

        The path must live inside one of the configured plugin directories.
        """
        name = (name or "").strip()
        info = self._find_plugin_info(name)
        if info is None:
            return {"ok": False, "error": f"plugin not found: {name}"}
        path = str(getattr(info, "path", "") or "")
        ok, message = _safe_delete_plugin_path(path, self.get_plugin_dirs())
        if not ok:
            return {"ok": False, "error": message}
        with self._lock:
            disabled = [n for n in (self._config.get("plugin_disabled") or []) if n != name]
            self._config["plugin_disabled"] = disabled
            self._config["_initialized"] = True
            cfg = dict(self._config)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
        return {"ok": True, "removed": message, "plugins": self.list_plugins()}

    def install_plugin_file(self, filename: str, content: str,
                            encoded: bool = True) -> Dict[str, Any]:
        """Install a single-file .py plugin into the first configured plugin directory."""
        import base64 as _b64

        base_name = os.path.basename((filename or "").strip())
        if not base_name or not base_name.endswith(".py"):
            return {"ok": False, "error": "only single-file .py plugins can be installed here"}
        target_dir = ""
        for d in self.get_plugin_dirs():
            if d and os.path.isdir(d):
                target_dir = d
                break
        if not target_dir:
            return {"ok": False, "error": "no plugin directory configured; add one first"}
        try:
            data = _b64.b64decode(content or "", validate=True) if encoded \
                else (content or "").encode("utf-8")
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": "invalid base64 content"}
        if len(data) > 2 * 1024 * 1024:
            return {"ok": False, "error": "plugin file too large (2 MB limit)"}
        stem, ext = os.path.splitext(base_name)
        target = os.path.join(target_dir, base_name)
        index = 1
        while os.path.exists(target):
            target = os.path.join(target_dir, f"{stem}_{index}{ext}")
            index += 1
        try:
            with open(target, "wb") as fh:
                fh.write(data)
        except OSError as exc:
            return {"ok": False, "error": f"write failed: {exc}"}
        with self._lock:
            self._config["_initialized"] = True
            cfg = dict(self._config)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
        return {"ok": True, "installed": target, "plugins": self.list_plugins()}

    def _find_plugin_info(self, name: str) -> Any:
        reg = self._registry()
        loader = getattr(reg, "plugin_loader", None) if reg is not None else None
        for info in list(getattr(loader, "plugins", ()) or ()):
            if str(getattr(info, "name", "")) == name:
                return info
        return None

    def add_plugin_dir(self, path: str) -> List[str]:
        path = (path or "").strip()
        with self._lock:
            dirs = list(self._config.get("plugin_dirs") or [])
            if path and path not in dirs:
                dirs.append(path)
                self._config["plugin_dirs"] = dirs
                cfg = dict(self._config)
        self._apply_config(cfg)
        return dirs

    def remove_plugin_dir(self, path: str) -> List[str]:
        path = (path or "").strip()
        with self._lock:
            dirs = [d for d in (self._config.get("plugin_dirs") or []) if d != path]
            self._config["plugin_dirs"] = dirs
            cfg = dict(self._config)
        self._apply_config(cfg)
        return dirs

    def reload_plugins(self) -> List[Dict[str, Any]]:
        with self._lock:
            cfg = dict(self._config)
        self._apply_config(cfg)
        return self.list_plugins()

    def get_security(self) -> Dict[str, Any]:
        with self._lock:
            cfg = dict(self._config)
        # aligned with the flat structure the desktop frontend's openPluginPanel expects
        return {
            "norp_safe_enabled": cfg.get("norp_safe_enabled", True),
            "security_enabled": cfg.get("security_enabled", True),
            "plugins_enabled": cfg.get("plugins_enabled", True),
            "audit": cfg.get("plugin_security_audit", "warn"),
            "import_restrict": cfg.get("plugin_security_import_restrict", "soft"),
            "require_permissions": cfg.get("plugin_security_require_permissions", True),
            "resource_limit": cfg.get("plugin_security_resource_limit", False),
            "signature_verify": cfg.get("plugin_signature_verify", True),
            "trusted_keys": list(cfg.get("plugin_trusted_keys") or []),
            "isolation": cfg.get("plugin_isolation", "auto"),
            "network_policy": cfg.get("plugin_network_policy", "deny"),
            "network_url_allowlist": list(cfg.get("plugin_network_url_allowlist") or []),
            "network_domain_allowlist": list(cfg.get("plugin_network_domain_allowlist") or []),
            "approval_enabled": cfg.get("approval_enabled", True),
        }

    # the desktop frontend's set_plugin_security_config has 12 positional parameters
    _SECURITY_ARG_KEYS = (
        "plugin_security_audit",            # 0
        "plugin_security_import_restrict",  # 1
        "plugin_security_require_permissions",  # 2
        "plugin_security_resource_limit",   # 3
        "plugin_isolation",                 # 4
        "plugin_signature_verify",          # 5
        "plugin_trusted_keys",              # 6
        "plugin_network_policy",            # 7
        "plugin_network_url_allowlist",     # 8
        "plugin_network_domain_allowlist",  # 9
        "approval_enabled",                 # 10
        "plugins_enabled",                  # 11
    )

    def set_security(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if "norp_safe_enabled" in data:
                self._config["norp_safe_enabled"] = bool(data["norp_safe_enabled"])
            if "security_enabled" in data:
                self._config["security_enabled"] = bool(data["security_enabled"])
            sec = data.get("security")
            if isinstance(sec, dict):
                for key, value in sec.items():
                    if key.startswith("plugin_") or key in (
                            "norp_safe_enabled", "security_enabled"):
                        self._config[key] = value
            args = data.get("security_args")
            if isinstance(args, list):
                for idx, value in enumerate(args):
                    if idx < len(self._SECURITY_ARG_KEYS):
                        self._config[self._SECURITY_ARG_KEYS[idx]] = value
            cfg = dict(self._config)
        self._apply_config(cfg)
        return self.get_security()

    def health(self) -> Dict[str, Any]:
        state = "unknown"
        if self._engine_state_fn is not None:
            try:
                state = self._engine_state_fn() or "unknown"
            except Exception:  # noqa: BLE001
                pass
        engine_ok = state in ("running", "starting")
        running = len(self._running_sessions)
        checks = [
            {
                "name": "HTTP Service",
                "passed": True,
                "severity": "info",
                "message": f"listening on http://{self.host}:{self.port}/",
            },
            {
                "name": "Engine",
                "passed": engine_ok,
                "severity": "info" if engine_ok else "error",
                "message": f"engine state: {state}",
            },
            {
                "name": "Running Tasks",
                "passed": True,
                "severity": "info",
                "message": f"{running} task(s) running",
            },
            {
                "name": "SSE Subscribers",
                "passed": True,
                "severity": "info",
                "message": f"{len(self._subscribers)} subscriber(s)",
            },
        ]
        fatal = 0 if engine_ok else 1
        return {
            "ok": engine_ok,
            "status": "healthy" if engine_ok else "degraded",
            "overall_healthy": engine_ok,
            "fatal_count": fatal,
            "error_count": 0 if engine_ok else 1,
            "warning_count": 0,
            "environment_type": "normal",
            "engine_state": state,
            "tasks_running": running,
            "subscribers": len(self._subscribers),
            "uptime": round(time.time() - self._start_ts, 1),
            "checks": checks,
        }

    def usage(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._usage)

    def debug_info(self) -> Dict[str, Any]:
        reg = self._registry()
        return {
            "version": _package_version(),
            "frontend": "web",
            "language": self._config.get("language", "en"),
            "presets": sorted(reg.list_presets()) if reg is not None else [],
            "models": sorted(reg.list_models()) if reg is not None else [],
            "tools": sorted(reg.list_tools()) if reg is not None else [],
            "plugins": sorted(reg.list_plugins()) if reg is not None else [],
            "sessions": len(self.list_sessions()) if self._agent is not None else 0,
            "tasks_total": len(self._tasks),
        }

    # ── 进化面板数据面（勾选制 导出 导入） ──
    # 进化底座（norpagent.evolution）为可选能力：不可用时面板如实降级为空。

    def evolution_points(self) -> Dict[str, Any]:
        """全部可进化点 + 当前勾选裁决（设置面板数据源）。"""
        try:
            from norpagent.evolution import ApprovalPolicy, get_store

            store = get_store()
            policy = ApprovalPolicy(store)
            return {
                "ok": True,
                "enabled": bool(store.get("evolution.enabled", True)),
                "points": policy.decisions(),
            }
        except Exception as exc:  # noqa: BLE001 — 面板降级不拖垮 WebUI
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "points": []}

    def evolution_log(self, n: int = 50) -> Dict[str, Any]:
        """进化日志尾部（热重载 / 进化包导入记录）。"""
        try:
            from norpagent.evolution import read_log

            return {"ok": True, "log": read_log(int(n))}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "log": []}

    def evolution_set_point(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """改一个点的勾选/分类（勾了=人工、不勾=自动；变更入审计）。"""
        try:
            from norpagent.evolution import ApprovalPolicy, get_store

            data = dict(data or {})
            point = str(data.get("point") or "").strip()
            policy = ApprovalPolicy(get_store())
            if data.get("reset"):
                policy.clear_manual(point)
            elif "category" in data:
                policy.set_category(point, str(data.get("category")))
            else:
                policy.set_manual(point, bool(data.get("manual")))
            return {"ok": True, "points": policy.decisions()}
        except Exception as exc:  # noqa: BLE001 — 如实报错
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # ── 提案引擎 / 熔断（§7.1 进化环；面板「提案中心」数据面） ──

    def _evolution_board(self):
        from norpagent.evolution import ProposalBoard

        return ProposalBoard(notifier=self._evolution_notify)

    def _evolution_notify(self, payload: Dict[str, Any]) -> None:
        """进化通知 → SSE（熔断打开 / 提案状态变化；失败不阻塞）。"""
        try:
            self._publish({
                "type": "notify",
                "level": "warn" if payload.get("kind") == "breaker" else "info",
                "message": str(payload.get("message") or ""),
                "ts": time.time(),
                "channel": "evolution",
            })
        except Exception:  # noqa: BLE001
            pass

    def evolution_proposals(self, status: Optional[str] = None) -> Dict[str, Any]:
        """提案列表 + 熔断状态（提案中心数据源）。"""
        try:
            board = self._evolution_board()
            items = board.list(status=status or None, limit=200)
            pending = [p for p in items if p.get("status") == "awaiting"]
            return {"ok": True, "proposals": items, "pending": pending,
                    "breakers": board.breaker.all_states()}
        except Exception as exc:  # noqa: BLE001 — 面板降级不拖垮 WebUI
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "proposals": [], "pending": [], "breakers": []}

    def evolution_proposals_action(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """提案中心动作面（run / decide / execute / breaker_resume /
        memory_plan / memory_apply / skill_candidates / skill_apply / config_tune）。"""
        data = dict(data or {})
        action = str(data.get("action") or "").strip()
        try:
            from norpagent.evolution import (
                ConfigEvolver, MemoryEvolver, ProposalBoard, SkillEvolver,
                UsageTracker,
            )

            board = self._evolution_board()
            if action == "run":
                # 一键：创建 → 勾选制裁决 →（批准即）执行
                rec = board.create(
                    str(data.get("point") or "kernel.agent"),
                    str(data.get("kind") or "config"),
                    str(data.get("title") or "evolution proposal"),
                    summary=str(data.get("summary") or ""),
                    payload=dict(data.get("payload") or {}),
                    reason=str(data.get("reason") or ""),
                    impact=str(data.get("impact") or ""),
                    risk=str(data.get("risk") or "medium"),
                    diff=str(data.get("diff") or ""),
                )
                rec = board.decide(rec["id"])
                if rec.get("status") == "approved":
                    rec = board.execute(rec["id"])
                return {"ok": True, "proposal": rec,
                        "proposals": board.list(limit=200),
                        "breakers": board.breaker.all_states()}
            if action == "decide":
                rec = board.decide(str(data.get("id") or ""),
                                   approve=(bool(data["approve"])
                                            if "approve" in data else None))
                return {"ok": True, "proposal": rec,
                        "proposals": board.list(limit=200),
                        "breakers": board.breaker.all_states()}
            if action == "execute":
                rec = board.execute(str(data.get("id") or ""))
                return {"ok": True, "proposal": rec,
                        "proposals": board.list(limit=200),
                        "breakers": board.breaker.all_states()}
            if action == "breaker_resume":
                state = board.breaker.resume(str(data.get("point") or ""))
                return {"ok": True, "breaker": state,
                        "breakers": board.breaker.all_states()}
            if action == "memory_plan":
                plan = MemoryEvolver().plan()
                return {"ok": True, "plan": plan}
            if action == "memory_apply":
                ids = [int(i) for i in (data.get("ids") or [])]
                rec = board.propose_memory(
                    "forget", ids, reason=str(data.get("reason") or "memory plan"))
                rec = board.decide(rec["id"])
                if rec.get("status") == "approved":
                    rec = board.execute(rec["id"])
                return {"ok": True, "proposal": rec,
                        "proposals": board.list(limit=200),
                        "breakers": board.breaker.all_states()}
            if action == "memory_restore":
                result = MemoryEvolver().restore(int(data.get("origin_id") or 0))
                return {"ok": bool(result.get("ok")), "result": result}
            if action == "memory_forgotten":
                return {"ok": True, "forgotten": MemoryEvolver().forgotten()}
            if action == "skill_candidates":
                tracker = UsageTracker(board.store)
                cands = SkillEvolver(board.store).candidate_payloads(tracker)
                return {"ok": True, "candidates": cands}
            if action == "skill_apply":
                rec = board.propose_skill(
                    str(data.get("name") or ""),
                    dict(data.get("artifact") or {}),
                    reason=str(data.get("reason") or "skill candidate"))
                rec = board.decide(rec["id"])
                if rec.get("status") == "approved":
                    rec = board.execute(rec["id"])
                return {"ok": True, "proposal": rec,
                        "proposals": board.list(limit=200),
                        "breakers": board.breaker.all_states()}
            if action == "config_tune":
                ce = ConfigEvolver(board.store, board=board)
                rec = ce.propose(str(data.get("key") or ""),
                                 data.get("value"),
                                 reason=str(data.get("reason") or "config tune"))
                rec = board.decide(rec["id"])
                if rec.get("status") == "approved":
                    rec = board.execute(rec["id"])
                return {"ok": True, "proposal": rec,
                        "proposals": board.list(limit=200),
                        "breakers": board.breaker.all_states()}
            return {"ok": False, "error": f"unknown action: {action!r}"}
        except Exception as exc:  # noqa: BLE001 — 如实报错（面板显示原因）
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def evolution_export(self, kind: str = "settings", author: str = ""):
        """导出（返回 (bytes, filename, mime)）。

        - kind="fspack"：进化状态打包为 .fspack（含作者署名）；
        - kind="settings"（默认 设置事实源 JSON 快照。
        """
        import json as _json

        from norpagent.evolution import (
            ApprovalPolicy, build_fspack, get_store, read_log,
        )

        store = get_store()
        if str(kind) == "fspack":
            item = {
                "kind": "evolution-state",
                "settings": store.all(include_schema_defaults=True),
                "approvals": ApprovalPolicy(store).decisions(),
                "log_tail": read_log(100),
            }
            payload = build_fspack(item, author=str(author or "user"))
            body = _json.dumps(payload, ensure_ascii=False, indent=2,
                               default=str).encode("utf-8")
            return body, "farstars-evolution.fspack", "application/json"
        snap = store.export_json()
        body = _json.dumps(snap, ensure_ascii=False, indent=2,
                           default=str).encode("utf-8")
        return body, "farstars-settings.json", "application/json"

    def evolution_import(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """导入进化包（.fspack/.json/.py）或整合包（.zip）。

        失败项不阻塞其余（整合包逐条语义）；失败逻辑完全不使用并如实报错。
        """
        import base64
        import json as _json
        import os as _os
        import tempfile

        from norpagent.evolution import get_store, import_bundle, import_fspack

        data = dict(data or {})
        name = str(data.get("name") or "import.bin")
        try:
            blob = base64.b64decode(str(data.get("data") or ""))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"invalid base64 payload: {exc}"}
        suffix = _os.path.splitext(name)[1].lower()
        store = get_store()

        def apply_fn(item: Any) -> None:
            if isinstance(item, dict) and isinstance(item.get("settings"), dict):
                # 快照导入是「用户导入」行为（非进化器自写）：actor 不以
                # "evolution" 开头，因此不受「进化器写锁定/非可进化项拒绝」
                # 守卫限制（/§7.6 守卫只拦进化器自身的写入；用户经面板
                # / CLI / 导入恢复快照属用户级操作，入审计）。
                store.set_many(item["settings"], actor="settings-import",
                               reason=f"import {name}")

        tmp_dir = tempfile.mkdtemp(prefix="np_evo_import_")
        tmp_path = _os.path.join(tmp_dir, _os.path.basename(name) or "import.bin")
        with open(tmp_path, "wb") as fh:
            fh.write(blob)
        try:
            if suffix == ".zip":
                report = import_bundle(tmp_path, apply_fn=apply_fn)
                return {"ok": True, "report": report}
            if suffix == ".py":
                import_fspack(tmp_path, apply_fn=apply_fn)
                return {"ok": True, "report": {"total": 1, "ok": 1,
                                               "failed": 0,
                                               "applied": [{"entry": name}]}}
            if suffix in (".fspack", ".json"):
                try:
                    payload = _json.loads(blob.decode("utf-8", errors="replace"))
                except Exception:
                    payload = None
                if isinstance(payload, dict) and payload.get("format") == "fspack/1":
                    import_fspack(tmp_path, apply_fn=apply_fn)
                    return {"ok": True, "report": {"total": 1, "ok": 1,
                                                   "failed": 0,
                                                   "applied": [{"entry": name}]}}
                if isinstance(payload, dict) and (
                        "values" in payload or "schema" in payload):
                    n = store.import_json(payload, actor="user",
                                          reason=f"import {name}")
                    return {"ok": True, "report": {"total": 1, "ok": 1,
                                                   "failed": 0, "imported": n}}
                return {"ok": False, "error": "unrecognized package format"}
            return {"ok": False, "error": f"unsupported suffix: {suffix}"}
        except Exception as exc:  # noqa: BLE001 — 导入失败如实报错
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            try:
                _os.remove(tmp_path)
                _os.rmdir(tmp_dir)
            except Exception:  # noqa: BLE001
                pass

    # ── 设置事实源（§5 / §6.3：Web 面板 / CLI / REST 三通道同源） ──

    def _settings_store(self):
        """确保 schema 注册并返回设置事实源（懒加载；测试可经环境变量隔离）。"""
        from norpagent.settings import ensure_schema

        return ensure_schema()

    def settings_schema(self, category: Optional[str] = None,
                        view: Optional[str] = None) -> Dict[str, Any]:
        """注册表合并视图（可按 category / 三视角过滤）。"""
        try:
            from norpagent.settings import schema_view

            rows = schema_view(self._settings_store())
            if category:
                rows = [r for r in rows if r.get("category") == category]
            if view:
                rows = [r for r in rows if view in (r.get("views") or [])]
            # 密钥项不返回默认值之外的信息（面板仍可见字段位，值由配置链路管理）
            return {"ok": True, "schema": rows, "count": len(rows)}
        except Exception as exc:  # noqa: BLE001 — 面板降级不拖垮 WebUI
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "schema": []}

    def settings_values(self) -> Dict[str, Any]:
        """全部设置项的解析视图（值 + 来源 + 三态：默认 / 继承 / 显式）。"""
        try:
            store = self._settings_store()
            return {"ok": True, "values": store.all_resolved(),
                    "scopes": dict(_SCOPE_TITLES_CACHE)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "values": {}}

    def settings_set(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """写入一个设置项（schema 校验 + 分层作用域 + 桥接热应用）。

        - ``reset=True``：删除显式值（恢复上级继承 / 默认）；
        - ``scope``：global（默认）/ profile / session / temp；
        - 桥接热应用仅针对**全局层**的非密键（config_key）：合并进运行态配置并
          立即生效（与既有面板同一链路）；作用域层保持设置库内部语义；密钥类
          项仅在配置链路处理（不落设置库）。
        """
        data = dict(data or {})
        key = str(data.get("key") or "").strip()
        scope = str(data.get("scope") or "global").strip().lower()
        try:
            from norpagent.settings_cli import _validate_value

            store = self._settings_store()
            if data.get("reset"):
                ok = store.delete(key, scope=scope, actor="user",
                                  reason="settings panel reset")
                if not ok:
                    return {"ok": False, "error": f"no explicit value for {key!r} at scope {scope}"}
            else:
                value = data.get("value")
                err = _validate_value(key, value)
                if err:
                    return {"ok": False, "error": err}
                if scope == "global":
                    store.set(key, value, actor="user",
                              reason="settings panel")
                else:
                    store.set_scoped(key, value, scope, actor="user",
                                     reason="settings panel")
            # 桥接热应用（§5.3）：仅全局层的非密键 → 运行态配置（保存 + 立即应用）；
            # 作用域层（profile/session/temp）保持设置库内部语义，不污染运行态配置。
            from norpagent.settings import config_patch_for_key

            patch = config_patch_for_key(key) if scope == "global" else {}
            if patch:
                self.save_config(patch)
            return {"ok": True, "key": key, "scope": scope,
                    "resolved": store.resolve(key),
                    "applied_to_config": bool(patch)}
        except Exception as exc:  # noqa: BLE001 — 如实报错
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def settings_audit(self, n: int = 50) -> Dict[str, Any]:
        """设置审计尾部（谁在何时改了什么；含被拒绝的写入）。"""
        try:
            store = self._settings_store()
            return {"ok": True, "audit": store.audit_tail(int(n))}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "audit": []}

    def frontend_log(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """前端日志上报（``POST /api/log``）。

        无结构（只有 message）时按原样写进程日志；带 ``kind`` 的结构化事件
        （渲染降级 / CDN 回退等）额外**计入审计**——写入设置库的同一审计环
        （``norpagent settings audit`` / ``/api/settings/audit`` 可查），
        记录失败不影响上报本身（审计尽力而为，前端永远静默）。
        """
        data = dict(data or {})
        message = str(data.get("message") or "")[:2000]
        _logger.info("frontend: %s", message)
        kind = str(data.get("kind") or "").strip()[:64]
        audited = False
        if kind:
            try:
                store = self._settings_store()
                record = getattr(store, "record_event", None)
                if callable(record):
                    detail = data.get("detail")
                    if not isinstance(detail, (dict, list)):
                        detail = {"detail": detail} if detail is not None else None
                    record(
                        "frontend." + kind,
                        key=kind,
                        new=detail,
                        actor="frontend",
                        reason=message[:500],
                    )
                    audited = True
            except Exception:  # noqa: BLE001 — 审计尽力而为
                audited = False
        return {"ok": True, "audited": audited}

    def settings_export(self):
        """导出设置库快照（返回 (bytes, filename, mime)）。"""
        import json as _json

        store = self._settings_store()
        snap = store.export_json()
        body = _json.dumps(snap, ensure_ascii=False, indent=2,
                           default=str).encode("utf-8")
        return body, "farstars-settings-v2.json", "application/json"

    def settings_import(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """导入设置库快照（JSON；支持版本 1/2 格式）。"""
        import base64
        import json as _json

        data = dict(data or {})
        name = str(data.get("name") or "settings.json")
        try:
            blob = base64.b64decode(str(data.get("data") or ""))
            payload = _json.loads(blob.decode("utf-8", errors="replace"))
            store = self._settings_store()
            n = store.import_json(payload, actor="user",
                                  reason=f"settings import {name}")
            return {"ok": True, "imported": n}
        except Exception as exc:  # noqa: BLE001 — 导入失败如实报错
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def whitebox_overview(self) -> Dict[str, Any]:
        """白盒总览（§4）：按环节树统一遍历「可看 / 可测 / 可改 / 可设」。"""
        try:
            from norpagent.whitebox import overview

            engine = None
            try:
                import norpagent as np

                engine = np.current()
            except Exception:  # noqa: BLE001
                engine = None
            if engine is None:
                engine = getattr(self, "_engine", None)  # 兼容注入
            return overview(engine)
        except Exception as exc:  # noqa: BLE001 — 面板降级不拖垮 WebUI
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                    "sections": []}

    # ── CNB cortex loopback proxy (FarStars console data plane) ──
    # 星轨控制台（norp-farstars.html）通过本同源代理访问真实 CNB 中枢总线：
    #   GET  /api/cnb/health?base=http://127.0.0.1:17800
    #   POST /api/cnb/ctrl?base=...   body = /cnb/ctrl 请求原样
    # 目标仅允许 http://127.0.0.1:<port> 与 http://localhost:<port>
    # （本机回环，拒绝任意内网/外网目标，防止代理被用作 SSRF 跳板）。

    _CNB_LOOPBACK_RE = re.compile(
        r"^http://(127\.0\.0\.1|localhost)(?::[0-9]{1,5})?$")

    def _cnb_base_ok(self, base: str) -> bool:
        return bool(base) and bool(self._CNB_LOOPBACK_RE.match(base))

    def cnb_proxy(self, method: str, base: str,
                  ctrl: Optional[Dict] = None,
                  timeout: float = 8.0) -> Dict[str, Any]:
        """转发中枢总线请求（GET /cnb/health 或 POST /cnb/ctrl）。

        失败不抛异常——统一返回 {"ok": False, "error": ...}，前端据此显示
        连接错误（中枢未启动 / 地址不可达 / 非回环目标被拒）。
        """
        base = (base or "").strip()
        if not self._cnb_base_ok(base):
            return {"ok": False,
                    "error": "cortex base only allows loopback http://127.0.0.1:<port> / http://localhost:<port>"}
        try:
            if method == "GET":
                url = base.rstrip("/") + "/cnb/health"
                req = urllib.request.Request(url, method="GET")
            else:
                url = base.rstrip("/") + "/cnb/ctrl"
                body = json.dumps(ctrl or {}, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(
                    url, data=body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data) if data.strip() else {"ok": True}
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                detail = {}
            return {"ok": False, "error": f"cortex http {exc.code}",
                    "detail": detail}
        except Exception as exc:  # noqa: BLE001 — 网络/超时/拒绝统一收敛
            return {"ok": False,
                    "error": f"{type(exc).__name__}: {exc}".split(": ")[-1][:200]}

    # ── CNB hosted launch (FarStars console one-click start) ──
    # 星轨控制台「一键拉起 CNB」：在 WebUI 进程内托管启动中枢（cortex）或
    # 节点（node）总线服务（start_bus 非阻塞），并提供停止 / 实例清单。
    # 监听地址仅允许回环（与总线本机定位一致，拒绝把总线开到公网）。

    def cnb_launch(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """启动一个 CNB 中枢或节点（托管在 WebUI 进程内）。

        data 字段：role("cortex"/"node")、node_id、kind、host、port、
        parent、level、heartbeat、desc。返回实例信息（含 base_url）。
        """
        data = dict(data or {})
        role = str(data.get("role") or "cortex").strip().lower()
        if role not in ("cortex", "node"):
            return {"ok": False, "error": f"unknown role: {role!r} (use cortex / node)"}
        host = str(data.get("host") or "127.0.0.1").strip() or "127.0.0.1"
        if host not in ("127.0.0.1", "localhost", "::1"):
            return {"ok": False,
                    "error": "host must be loopback (127.0.0.1 / localhost)"}

        def _int(v: Any, default: int, lo: int, hi: int) -> int:
            try:
                n = int(v)
            except (TypeError, ValueError):
                return default
            return max(lo, min(n, hi))

        node_id = str(data.get("node_id") or "").strip()
        desc = str(data.get("desc") or "FarStars console start")
        meta = {"desc": desc, "engine": "webui"}
        if role == "cortex":
            node_id = node_id or "cortex"
            port = _int(data.get("port"), 17800, 1, 65535)
            from norpagent.cnb.cortex import Cortex

            with self._lock:
                if node_id in self._cnb_hosted:
                    return {"ok": False, "error": f"node_id already hosted: {node_id}"}
                if any(v.get("port") == port for v in self._cnb_hosted.values()):
                    return {"ok": False, "error": f"port already hosted: {port}"}
            try:
                inst = Cortex(node_id=node_id, host=host, port=port, meta=meta)
                inst.start()
            except Exception as exc:  # noqa: BLE001 — 端口占用 / 启动失败如实报错
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            entry = {
                "role": "cortex", "node_id": node_id, "kind": "cortex",
                "host": host, "port": port, "base_url": getattr(inst, "base_url", f"http://{host}:{port}"),
                "level": 0, "parent": "", "started_at": time.time(), "desc": desc,
            }
            with self._lock:
                self._cnb_hosted[node_id] = {"instance": inst, **entry}
            return {"ok": True, "instance": dict(entry)}

        # role == "node"
        node_id = node_id or ("node-" + os.urandom(4).hex())
        port = _int(data.get("port"), 17801, 1, 65535)
        kind = str(data.get("kind") or "agent").strip() or "agent"
        parent = str(data.get("parent") or "http://127.0.0.1:17800").strip()
        level = _int(data.get("level"), 3, 1, 63)
        try:
            heartbeat = float(data.get("heartbeat") or 5.0)
        except (TypeError, ValueError):
            heartbeat = 5.0
        heartbeat = max(0.5, min(heartbeat, 3600.0))
        from norpagent.cnb.node import NervousNode

        with self._lock:
            if node_id in self._cnb_hosted:
                return {"ok": False, "error": f"node_id already hosted: {node_id}"}
            if any(v.get("port") == port for v in self._cnb_hosted.values()):
                return {"ok": False, "error": f"port already hosted: {port}"}
        try:
            inst = NervousNode(node_id=node_id, kind=kind, level=level,
                               parent_url=parent, host=host, port=port,
                               meta=meta, heartbeat_interval=heartbeat)
            inst.start()
        except Exception as exc:  # noqa: BLE001 — 端口占用 / 启动失败如实报错
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        entry = {
            "role": "node", "node_id": node_id, "kind": kind,
            "host": host, "port": port, "base_url": getattr(inst, "base_url", f"http://{host}:{port}"),
            "level": level, "parent": parent, "started_at": time.time(),
            "heartbeat": heartbeat, "desc": desc,
        }
        with self._lock:
            self._cnb_hosted[node_id] = {"instance": inst, **entry}
        return {"ok": True, "instance": dict(entry)}

    def cnb_stop(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """停止托管中的 CNB 实例（node_id 省略 = 停止全部）。"""
        data = dict(data or {})
        node_id = str(data.get("node_id") or "").strip()
        with self._lock:
            if node_id:
                entry = self._cnb_hosted.pop(node_id, None)
                entries = [entry] if entry else []
            else:
                entries = list(self._cnb_hosted.values())
                self._cnb_hosted.clear()
        if not entries:
            return {"ok": False, "error": f"not hosted: {node_id or '(all)'}"}
        # 停止顺序：先子后父——按等级从高到低停（level 越大 = 越深的下级），
        # 中枢（level 0）最后停。若反过来先停中枢，子节点注销会打到已关闭
        # 的父端口（WinError 10061 连接被拒），既刺眼又掩盖真实故障。
        # 单个指定 node_id 时 entries 只有一项，此排序无副作用。
        entries.sort(key=lambda e: int(e.get("level") or 0), reverse=True)
        stopped: List[str] = []
        for entry in entries:
            try:
                entry["instance"].stop()
                stopped.append(str(entry.get("node_id") or ""))
            except Exception:  # noqa: BLE001 — 单个停止失败不阻塞其余
                pass
        return {"ok": True, "stopped": stopped, "count": len(stopped)}

    def cnb_instances(self) -> Dict[str, Any]:
        """本 WebUI 托管的 CNB 实例清单（不含内部对象，仅展示字段）。"""
        with self._lock:
            rows = [
                {k: v for k, v in entry.items() if k != "instance"}
                for entry in self._cnb_hosted.values()
            ]
        return {"ok": True, "instances": rows}

    # ── filesystem browsing (the browser host's "directory/file picker") ──

    def list_fs(self, path: str = "", include_files: bool = False) -> Dict[str, Any]:
        """List a directory's subdirectories (optionally files) for the browser-side directory picker.

        An empty path returns the home directory; Windows also lists drives.
        This is a pure local-UI capability: the service only listens on
        127.0.0.1 and only does read-only listing.
        """
        import sys as _sys

        home = os.path.expanduser("~") or ""
        raw = (path or "").strip()
        target = os.path.abspath(os.path.expanduser(raw or home))
        result: Dict[str, Any] = {
            "ok": True,
            "path": target,
            "parent": "",
            "dirs": [],
            "files": [],
            "home": home,
        }
        if _sys.platform == "win32" and not raw:
            drives: List[Dict[str, str]] = []
            try:
                import string as _string

                for letter in _string.ascii_uppercase:
                    root = f"{letter}:\\"
                    if os.path.exists(root):
                        drives.append({"name": root, "path": root})
            except OSError:  # pragma: no cover — defensive
                pass
            result["drives"] = drives
        try:
            entries = sorted(os.scandir(target), key=lambda e: e.name.lower())
        except OSError as exc:
            if not os.path.exists(target):
                # the directory does not exist yet (e.g. the platform default
                # workspace): fall back to the nearest existing ancestor
                ancestor = target
                while ancestor and not os.path.exists(ancestor):
                    parent = os.path.dirname(ancestor)
                    if parent == ancestor:
                        break
                    ancestor = parent
                if ancestor and os.path.isdir(ancestor) and ancestor != target:
                    return self.list_fs(ancestor, include_files=include_files)
            result["ok"] = False
            result["error"] = str(exc)
            return result
        dirs: List[Dict[str, str]] = []
        files: List[Dict[str, str]] = []
        for entry in entries:
            if entry.name.startswith("."):
                continue  # hidden entries do not enter the picker
            try:
                if entry.is_dir():
                    dirs.append({"name": entry.name, "path": entry.path})
                elif include_files and entry.is_file():
                    files.append({"name": entry.name, "path": entry.path})
            except OSError:
                continue
            if len(dirs) + len(files) >= 500:
                break
        parent = os.path.dirname(target)
        if parent and parent != target:
            result["parent"] = parent
        result["dirs"] = dirs
        result["files"] = files
        return result

    def make_fs_dir(self, parent: str = "", name: str = "") -> Dict[str, Any]:
        """Create a subdirectory under ``parent`` (the picker's "New Folder").

        Pure local-UI capability: 127.0.0.1 only; creates a single new folder
        from a plain name (no path separators / drive colons — prevents
        traversal). Returns the new absolute path on success.
        """
        name = (name or "").strip()
        if not name or name in (".", "..") or any(
                c in name for c in ("/", "\\", ":", "\x00")):
            return {"ok": False, "error": "invalid folder name"}
        base = os.path.abspath(os.path.expanduser(
            (parent or "").strip() or (os.path.expanduser("~") or "")))
        target = os.path.join(base, name)
        try:
            os.makedirs(target, exist_ok=False)
        except FileExistsError:
            return {"ok": False, "error": "folder already exists"}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": target}

    def read_fs_file(self, path: str) -> Dict[str, Any]:
        """Read a local text file (the companion capability of the browser host's pick_file)."""
        p = os.path.abspath(os.path.expanduser(path or ""))
        try:
            if os.path.isdir(p):
                return {"ok": False, "error": "the target is a directory"}
            if os.path.getsize(p) > 2 * 1024 * 1024:
                return {"ok": False, "error": "file too large (max 2MB)"}
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                return {"ok": True, "content": f.read()}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    # ── file upload ─────────────────────────────────────

    _IMAGE_EXTS = {
        "png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "ico", "tiff", "tif",
    }
    _AUDIO_EXTS = {
        "mp3", "wav", "m4a", "flac", "aac", "ogg", "opus", "weba", "amr",
    }
    _VIDEO_EXTS = {
        "mp4", "m4v", "webm", "mov", "avi", "mkv", "flv", "wmv",
    }
    # per-modality attachment size caps for native passthrough (bytes)
    _MM_MAX_BYTES = {
        "image": 10 * 1024 * 1024,
        "audio": 20 * 1024 * 1024,
        "video": 32 * 1024 * 1024,
    }

    def _prepare_chat_attachments(
        self, raw: Any
    ) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
        """Route and convert chat attachments before the task executes.

        Per-modality routing (native passthrough): each attachment goes either

        - ``direct``: kept as a native multimodal part (base64 data passed to
          the model — image_url / input_audio / video_url); or
        - ``service``: sent to the configured external service (vision / audio /
          video URL) and merged into the prompt as text.

        Text-ish files (upload or pasted content) are decoded and kept as
        ``route="service"`` text attachments so the model reads the whole body
        while the visible user message stays clean; their length is capped by the
        ``attachment_text_max_chars`` / ``attachment_text_unlimited`` settings.
        Returns ``(extra_text, media)`` or None when there is nothing to do:
        ``extra_text`` is appended to the prompt; ``media`` holds direct-route
        attachments for the model (may be empty).
        """
        if not isinstance(raw, list) or not raw:
            return None
        with self._lock:
            cfg = dict(self._config)
        extra_parts: List[str] = []
        media: List[Dict[str, Any]] = []
        timeout = float(cfg.get("api_request_timeout") or 180)
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "file")
            mime = str(item.get("type") or item.get("mime") or "")
            data = str(item.get("data") or "")
            if data.strip().startswith("data:"):
                head, _, rest = data.partition(",")
                data = rest
                if not mime and head.startswith("data:"):
                    mime = head[5:].split(";")[0]
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if mime.startswith("image/") or ext in self._IMAGE_EXTS:
                kind = "image"
            elif mime.startswith("audio/") or ext in self._AUDIO_EXTS:
                kind = "audio"
            elif mime.startswith("video/") or ext in self._VIDEO_EXTS:
                kind = "video"
            else:
                kind = "text"
            try:
                raw_len = len(base64.b64decode(data)) if data else 0
            except Exception:  # noqa: BLE001
                raw_len = 0
            if kind == "text":
                try:
                    text = base64.b64decode(data).decode("utf-8")
                except Exception:  # noqa: BLE001 — binary or non-utf8: note, no raw bytes
                    text = "(binary file, not included)"
                # Text files are kept as attachments (route="service") instead of
                # being inlined into the prompt: the model still reads the content
                # through the multimodal text part, but the user message content
                # stays clean, so the file body is never shown in the chat bubble
                # or persisted as the visible message text.
                #
                # Length cap (2026-09-13): the old hard-coded `text[:20000]` silently
                # truncated any upload / paste longer than 20000 characters (the model
                # only ever "read" that prefix). It is now driven by settings:
                #   * attachment_text_unlimited = True  → whole body, no cap;
                #   * otherwise attachment_text_max_chars (512~2147483647, 0 = no cap).
                raw_limit = cfg.get("attachment_text_max_chars")
                if raw_limit is None:
                    raw_limit = _DEFAULT_TEXT_ATTACHMENT_MAX
                try:
                    text_limit = int(raw_limit)
                except (TypeError, ValueError):
                    text_limit = _DEFAULT_TEXT_ATTACHMENT_MAX
                if cfg.get("attachment_text_unlimited") or text_limit <= 0:
                    kept_text = text
                else:
                    kept_text = text[:text_limit]
                media.append({
                    "kind": "text", "name": name, "mime": mime or "text/plain",
                    "ext": ext, "route": "service", "text": kept_text,
                })
                continue
            limit = self._MM_MAX_BYTES.get(kind, _MAX_UPLOAD_FILE)
            if raw_len > limit:
                extra_parts.append(
                    f"[{name}] skipped: {kind} exceeds the "
                    f"{limit // (1024 * 1024)}MB limit"
                )
                continue
            route = str(cfg.get(f"mm_{kind}_route") or "direct").strip().lower()
            if route == "service":
                try:
                    mm = self._mm()
                    if kind == "image":
                        desc = mm.describe_image(
                            data, ext, mime or "image/png",
                            str(cfg.get("vision_service_url") or ""), "",
                            timeout=timeout,
                            api_key=str(cfg.get("vision_service_api_key") or ""),
                        )
                    else:
                        desc = mm.media_describe(
                            kind, data, ext, mime or f"{kind}/*",
                            str(cfg.get(f"{kind}_service_url") or ""), "",
                            api_key=str(cfg.get(f"{kind}_service_api_key") or ""),
                            timeout=timeout,
                        )
                    extra_parts.append(f"[{kind}: {name}]\n{desc}")
                except Exception as exc:  # noqa: BLE001 — the task proceeds with a note
                    extra_parts.append(f"[{kind}: {name}] service failed: {exc}")
            else:
                media.append({
                    "kind": kind, "name": name, "mime": mime, "ext": ext,
                    "route": "direct", "data": data,
                })
        return "\n\n".join(p for p in extra_parts if p), media

    def upload_files(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Decode frontend dataURL files: text → content; images → base64 (vision).

        v0.9.9: image files (mime ``image/*`` or a known image extension) are
        returned with ``kind="image"`` and their raw base64 payload so the
        frontend can feed them to ``/api/vision``; other binaries are still
        rejected.
        """
        out: List[Dict[str, Any]] = []
        for f in files or []:
            name = str(f.get("name") or "file")
            ftype = str(f.get("type") or "")
            data = str(f.get("data") or "")
            try:
                if "," in data:
                    data = data.split(",", 1)[1]
                raw = base64.b64decode(data)
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                is_image = ftype.startswith("image/") or ext in self._IMAGE_EXTS
                is_video = ftype.startswith("video/") or ext in self._VIDEO_EXTS
                limit = _MAX_VIDEO_UPLOAD_FILE if is_video else _MAX_UPLOAD_FILE
                if len(raw) > limit:
                    out.append({"name": name, "type": ftype,
                                "error": f"file too large (max {limit // (1024 * 1024)}MB)"})
                    continue
                if is_image or is_video:
                    out.append({"name": name,
                                "type": ftype or ("image/png" if is_image else "video/mp4"),
                                "kind": "image" if is_image else "video",
                                "data": data})
                    continue
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    out.append({"name": name, "type": ftype,
                                "error": "binary file not supported"})
                    continue
                out.append({"name": name, "type": ftype, "kind": "text",
                            "content": text})
            except Exception as exc:  # noqa: BLE001
                out.append({"name": name, "type": ftype, "error": str(exc)})
        return out

    # ── multimodal (v0.9.9): vision + sound ───────────────────────────────

    def _mm(self) -> Any:
        """Lazily import the stdlib-only multimodal backend."""
        from norpagent.builtin.ui import multimodal

        return multimodal

    def vision_describe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/vision: describe images with the configured vision service.

        body: {"images": [{"name","type","data"(base64)}], "prompt": "..."}
        → {"ok": true, "descriptions": [{"name","description"}]}
        """
        with self._lock:
            cfg = dict(self._config)
        if not cfg.get("vision_enabled"):
            return {"ok": False,
                    "error": "Vision API is not enabled (Settings → Vision API → Enable vision API)"}
        service_url = str(cfg.get("vision_service_url") or "").strip()
        if not service_url:
            return {"ok": False, "error": "vision service URL is not configured (Settings → Vision API)"}
        images = data.get("images")
        if not isinstance(images, list) or not images:
            return {"ok": False, "error": "images must be a non-empty list"}
        prompt = str(data.get("prompt") or "").strip() or "Please describe the content of this image in detail."
        mm = self._mm()
        out: List[Dict[str, Any]] = []
        for img in images:
            name = str(img.get("name") or "image")
            ftype = str(img.get("type") or "image/png")
            payload = str(img.get("data") or "")
            try:
                if "," in payload:
                    payload = payload.split(",", 1)[1]
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                desc = mm.describe_image(
                    payload, ext, ftype, service_url, prompt,
                    timeout=float(cfg.get("api_request_timeout") or 180),
                    api_key=str(cfg.get("vision_service_api_key") or ""),
                )
                out.append({"name": name, "description": desc})
            except Exception as exc:  # noqa: BLE001
                out.append({"name": name, "error": str(exc)})
        return {"ok": True, "descriptions": out}

    def tts_speak(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/tts: text → speech audio (base64 in the JSON reply).

        body: {"text": "...", "voice": "...", "rate": 1.0}
        → {"ok": true, "audio_base64": "...", "mime": "audio/wav"}
        Native (offline) TTS on Windows / macOS / Linux; optional
        OpenAI-compatible /audio/speech service when tts_service_url is set.
        """
        with self._lock:
            cfg = dict(self._config)
        if not cfg.get("tts_enabled", True):
            return {"ok": False, "error": "voice playback is not enabled (Settings → Sound)"}
        text = str(data.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "text is empty"}
        voice = str(data.get("voice") or cfg.get("tts_voice") or "").strip()
        try:
            rate = float(data.get("rate") if data.get("rate") is not None
                         else cfg.get("tts_rate") or 1.0)
        except (TypeError, ValueError):
            rate = 1.0
        rate = max(0.5, min(2.0, rate))
        mm = self._mm()
        try:
            audio, mime = mm.text_to_speech(
                text,
                service_url=str(cfg.get("tts_service_url") or ""),
                api_key=str(cfg.get("tts_service_api_key") or ""),
                voice=voice,
                rate=rate,
                timeout=float(cfg.get("api_request_timeout") or 180),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"TTS failed: {exc}"}
        return {
            "ok": True,
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "mime": mime,
        }

    def stt_transcribe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/stt: speech audio → text.

        body: {"audio": "<base64 wav>", "mime": "audio/wav"}
        → {"ok": true, "text": "..."}
        Windows native recognizer by default; optional OpenAI-compatible
        /audio/transcriptions service when stt_service_url is set.
        """
        with self._lock:
            cfg = dict(self._config)
        payload = str(data.get("audio") or "")
        if not payload:
            return {"ok": False, "error": "audio is empty"}
        try:
            if "," in payload:
                payload = payload.split(",", 1)[1]
            audio = base64.b64decode(payload)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"audio base64 decode failed: {exc}"}
        if len(audio) > _MAX_UPLOAD_FILE:
            return {"ok": False, "error": "audio too large (max 10MB)"}
        mime = str(data.get("mime") or "audio/wav")
        mm = self._mm()
        try:
            text = mm.speech_to_text(
                audio,
                mime,
                service_url=str(cfg.get("stt_service_url") or ""),
                api_key=str(cfg.get("stt_service_api_key") or ""),
                language=str(cfg.get("stt_language") or ""),
                timeout=float(cfg.get("api_request_timeout") or 180),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"STT failed: {exc}"}
        if not text.strip():
            return {"ok": False, "error": "no speech content recognized"}
        return {"ok": True, "text": text.strip()}

    def beep_notify(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/beep: generate the new-message notification tone (WAV, base64)."""
        with self._lock:
            cfg = dict(self._config)
        if not cfg.get("sound_notify_enabled", True):
            return {"ok": False, "error": "sound effects are not enabled"}
        mm = self._mm()
        audio = mm.beep_wav()
        return {"ok": True, "audio_base64": base64.b64encode(audio).decode("ascii"),
                "mime": "audio/wav"}

    # ── module flow (FLOW: the real backend of the /flow page) ─────────────

    def _flow_workspace(self) -> Any:
        """Flow module workspace (lazily created; reuses the plugin security config)."""
        if self._flow_ws is None:
            from norpagent.flows import ModuleWorkspace, default_modules_dir

            with self._lock:
                cfg = dict(self._config)
            module_dir = str(cfg.get("flow_modules_dir") or "") or None
            self._flow_ws = ModuleWorkspace(
                module_dir or default_modules_dir(),
                config={
                    "plugin_security_audit": cfg.get("plugin_security_audit", "warn"),
                    "plugin_security_import_restrict":
                        cfg.get("plugin_security_import_restrict", "soft"),
                    "plugin_security_require_permissions":
                        cfg.get("plugin_security_require_permissions", True),
                    "plugin_signature_verify":
                        cfg.get("plugin_signature_verify", True),
                    "plugin_trusted_keys":
                        list(cfg.get("plugin_trusted_keys") or []),
                    "plugin_isolation": cfg.get("plugin_isolation", "auto"),
                    "plugin_network_policy":
                        cfg.get("plugin_network_policy", "deny"),
                    "approval_enabled": cfg.get("approval_enabled", True),
                },
            )
        return self._flow_ws

    def flow_snapshot(self) -> Dict[str, Any]:
        """Registry snapshot: drives the /flow page's module dock and instance selection."""
        try:
            from norpagent.flows import build_snapshot

            reg = self._registry()
            if reg is None:
                return {"ok": False, "error": "runtime not bound (attach_runtime)"}
            state = "unknown"
            if self._engine_state_fn is not None:
                try:
                    state = self._engine_state_fn() or "unknown"
                except Exception:  # noqa: BLE001
                    pass
            snap = build_snapshot(reg, self._agent, engine_state=state)
            # remote model list (the cache of the last "fetch model list") and FE frontend modules
            self._scan_fe_modules()
            with self._lock:
                # drop retired model names (adapter-owned list; see filter_remote_models)
                remote = filter_remote_models(self._config.get("remote_models"))
                fe_mods = [dict(v) for v in self._frontend_modules.values()]
            groups = snap.get("groups") or {}
            groups["remote_models"] = remote
            groups["frontends"] = fe_mods
            snap["groups"] = groups
            # agent tool mounting: the preset default set (fallback base) + the currently effective set
            snap["agent_base_tools"] = list(self._agent_base_tools)
            snap["agent_tools"] = self.agent_effective_tools()
            return snap
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def flow_run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Start a canvas-graph execution (background thread; progress pushed via SSE).

        graph = {nodes: [...], links: [...], prompt: "..."},
        nodes carry config (instance selection) and inputs (input-panel content).
        """
        try:
            from norpagent.flows import FlowRunner, normalize_graph

            reg = self._registry()
            if reg is None:
                return {"ok": False, "error": "runtime not bound (attach_runtime)"}
            graph = data.get("graph")
            if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
                return {"ok": False, "error": "invalid graph format (missing nodes list)"}
            prompt = str(data.get("prompt") or graph.get("prompt") or "")
            graph = normalize_graph(graph)
            graph["prompt"] = prompt

            runner = FlowRunner(reg, self._agent, publish=self._publish)
            flow_id = runner.flow_id
            with self._lock:
                self._flow_runs[flow_id] = runner
            self._publish({
                "type": "notify", "level": "info",
                "message": f"Flow {flow_id} submitted",
                "ts": time.time(), "sid": None,
            })

            def worker() -> None:
                try:
                    result = runner.run(graph)
                    self._publish({
                        "type": "flow.log",
                        "payload": {"flow_id": flow_id, "level": "info",
                                    "message": f"flow finished status={result.get('status')} "
                                               f"errors={result.get('errors')}"},
                        "ts": time.time(),
                    })
                except Exception as exc:  # noqa: BLE001
                    self._publish({
                        "type": "flow.done",
                        "payload": {"flow_id": flow_id, "status": "error",
                                    "error": f"{type(exc).__name__}: {exc}"},
                        "ts": time.time(),
                    })
                finally:
                    with self._lock:
                        self._flow_runs.pop(flow_id, None)

            threading.Thread(
                target=worker, daemon=True,
                name=f"norpagent-flow-{flow_id[:8]}",
            ).start()
            return {"ok": True, "flow_id": flow_id}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def flow_stop(self, flow_id: str) -> Dict[str, Any]:
        """Stop a running flow (takes effect at node boundaries)."""
        with self._lock:
            runner = self._flow_runs.get(flow_id)
        if runner is None:
            return {"ok": False, "error": "flow does not exist or has finished"}
        try:
            runner.request_stop()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def flow_register(self, name: str, content: str) -> Dict[str, Any]:
        """True registration of "file-as-module" (.py plugin security pipeline /
        .json/.yaml descriptions / .html/.js/.ts frontend modules FE)."""
        try:
            reg = self._registry()
            if reg is None:
                return {"ok": False, "error": "runtime not bound (attach_runtime)"}
            if not name:
                return {"ok": False, "error": "missing file name"}
            result = self._flow_workspace().register(reg, name, content)
            module = result.get("module") if isinstance(result, dict) else None
            if module and module.get("kind") == "frontend":
                # frontend module registration: the flow snapshot's frontends
                # group + /fe/<name> hosting
                fname = os.path.basename(str(module.get("url") or f"/fe/{name}"))
                with self._lock:
                    self._frontend_modules[fname] = {
                        "name": str(module.get("name") or ""),
                        "format": str(module.get("format") or "html"),
                        "url": str(module.get("url") or f"/fe/{fname}"),
                        "desc": str(module.get("desc") or ""),
                    }
            return result
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def fe_read_file(self, fname: str) -> Tuple[Optional[bytes], str]:
        """Read an FE frontend module file (.html/.js/.ts); returns (bytes, mime)."""
        safe = re.sub(r"[^\w.\-]", "", fname or "")
        if not safe or os.path.basename(safe) != safe:
            return None, "text/plain"
        ws = self._flow_workspace()
        path = os.path.join(str(getattr(ws, "directory", "")), safe)
        if not os.path.isfile(path):
            return None, "text/plain"
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        mime = {"html": "text/html", "htm": "text/html",
                "js": "application/javascript", "ts": "text/plain"}.get(ext, "text/plain")
        try:
            with open(path, "rb") as f:
                return f.read(), mime
        except OSError:
            return None, "text/plain"

    def _scan_fe_modules(self) -> None:
        """Scan the flow module directory after startup to restore the frontend module list (survives restarts)."""
        if self._fe_scanned:
            return
        self._fe_scanned = True
        try:
            ws = self._flow_workspace()
            directory = str(getattr(ws, "directory", "") or "")
            if not directory or not os.path.isdir(directory):
                return
            for fname in os.listdir(directory):
                ext = os.path.splitext(fname)[1].lstrip(".").lower()
                if ext not in ("html", "htm", "js", "ts"):
                    continue
                with self._lock:
                    if fname in self._frontend_modules:
                        continue
                    self._frontend_modules[fname] = {
                        "name": os.path.splitext(fname)[0],
                        "format": ext,
                        "url": f"/fe/{fname}",
                        "desc": f"frontend module · {os.path.splitext(fname)[0]} (.{ext})",
                    }
        except OSError:  # noqa: BLE001
            pass

    # ── FE independent config (one scope per FE; mutually isolated) ──

    @staticmethod
    def _safe_fe_id(fe_id: str) -> str:
        stem = re.sub(r"[^\w\u4e00-\u9fa5-]", "_", str(fe_id or "fe"))[:64].strip("_")
        return stem or "fe"

    def _fe_config_path(self, fe_id: str) -> str:
        return os.path.join(self._fe_config_dir, f"{self._safe_fe_id(fe_id)}.json")

    def _load_fe_configs(self) -> None:
        try:
            if not os.path.isdir(self._fe_config_dir):
                return
            for fname in os.listdir(self._fe_config_dir):
                if not fname.endswith(".json"):
                    continue
                fe_id = fname[:-5]
                try:
                    with open(os.path.join(self._fe_config_dir, fname),
                              "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._fe_configs[fe_id] = data
                except (OSError, ValueError):
                    continue
        except OSError:  # noqa: BLE001
            pass

    def fe_load_config(self, fe_id: str) -> Dict[str, Any]:
        """Read an FE's independent config; when none is recorded, return a copy of the global config (default source)."""
        key = self._safe_fe_id(fe_id)
        with self._lock:
            saved = self._fe_configs.get(key)
            if saved is None:
                saved = dict(self._config)
        return {"ok": True, "fe_id": key, "config": json_safe(saved)}

    def fe_save_config(self, fe_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Save an FE's independent config (atomic persistence; mutually isolated)."""
        key = self._safe_fe_id(fe_id)
        clean = {str(k): v for k, v in (config or {}).items()}
        with self._lock:
            self._fe_configs[key] = clean
        try:
            os.makedirs(self._fe_config_dir, exist_ok=True)
            path = self._fe_config_path(key)
            tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(clean, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError as exc:  # noqa: BLE001
            _logger.warning("FE config write for %s failed: %s", key, exc)
        return {"ok": True, "fe_id": key, "config": json_safe(clean)}

    # ── flow auto-save / apply to agent ──────────────────

    def flow_save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save the canvas graph (auto-save entry); optionally activate "apply to agent".

        Request body ``{graph, active}``:
        - graph = {nodes, links, prompt, ...} (frontend export format);
        - active = True: the front main page's (/chat) tasks execute per this
          flow — the graph is the agent's behavior definition; False only persists.
        """
        graph = data.get("graph") if isinstance(data, dict) else None
        if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
            return {"ok": False, "error": "invalid graph format (missing nodes list)"}
        active = bool(data.get("active"))
        nodes_n = len(graph.get("nodes") or [])
        beams_n = len(graph.get("links") or [])
        with self._lock:
            self._flow_graph = dict(graph)
            self._flow_active = active
        self._save_flow_graph_to_disk()
        self._publish({
            "type": "notify", "level": "info",
            "message": ("Flow saved and activated for the agent · "
                        f"{nodes_n} nodes / {beams_n} beams"
                        if active else
                        f"Flow saved · {nodes_n} nodes / {beams_n} beams"),
            "ts": time.time(), "sid": None,
        })
        return {"ok": True, "active": active,
                "nodes": nodes_n, "beams": beams_n}

    def flow_load(self) -> Dict[str, Any]:
        """Return the last auto-saved canvas graph and its activation state (restored after a page refresh)."""
        with self._lock:
            graph = dict(self._flow_graph) if self._flow_graph else None
            active = self._flow_active
        return {"ok": True, "active": active, "graph": graph}

    def _load_flow_graph_from_disk(self) -> None:
        """Restore the last-saved flow at startup (silently ignore missing / corrupt files)."""
        path = self._flow_graph_path
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        graph = data.get("graph")
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
            self._flow_graph = dict(graph)
            self._flow_active = bool(data.get("active"))
            _logger.info("flow graph restored (active=%s, nodes=%s)",
                         self._flow_active, len(graph["nodes"]))

    def _save_flow_graph_to_disk(self) -> None:
        """Atomically write the current flow to disk (failures only log; never break the save flow)."""
        path = self._flow_graph_path
        if not path:
            return
        try:
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
            with self._lock:
                payload = {
                    "active": self._flow_active,
                    "graph": self._flow_graph,
                    "saved_at": time.time(),
                }
            tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(tmp, 0o600)
            except OSError:  # Windows has limited permission bits; ignore
                pass
            os.replace(tmp, path)
        except OSError as exc:  # noqa: BLE001
            _logger.warning("flow graph write to %s failed: %s", path, exc)

    # ── chat tasks executing per the active flow (behavior hot-switch) ──

    def _active_chat_flow(self) -> Optional[Dict[str, Any]]:
        """The currently "apply to agent"-activated flow (None when not active)."""
        with self._lock:
            if not self._flow_active or not self._flow_graph:
                return None
            return dict(self._flow_graph)

    def _run_flow_task(self, graph: Dict[str, Any], prompt: str,
                       sid: Optional[str], task_id: str) -> Any:
        """Execute the front main page's chat task per the activated flow.

        The flow's final output is published as the assistant reply (on_content);
        node-level progress pushes synchronously as flow.* events (visible in real
        time on the /flow page); after completion this round's conversation is
        written to the session history, keeping context continuity.
        """
        from norpagent.flows import FlowRunner, normalize_graph
        from norpagent.kernel.agent import RunResult

        key = sid or task_id
        try:
            reg = self._registry()
            if reg is None:
                raise RuntimeError("runtime not bound (attach_runtime)")
            g = normalize_graph(graph)
            g["prompt"] = prompt
            runner = FlowRunner(reg, self._agent, publish=self._publish)
            with self._lock:
                self._chat_flow_runs[key] = runner
            self._publish({
                "type": "notify", "level": "info",
                "message": f"FLOW mode execution · {len(g.get('nodes') or [])} nodes",
                "ts": time.time(), "sid": sid or None,
            })
            result = runner.run(g)
            status = str(result.get("status") or "done")
            content = str(result.get("final_output") or "").strip()
            error = ""
            if status == "stopped":
                error = "flow stopped"
            elif result.get("errors"):
                error = f"flow finished · {result.get('errors')} node error(s)"
            self._publish({
                "type": "on_content", "content": content, "stream": False,
                "ts": time.time(), "sid": sid or None,
            })
            self._publish({
                "type": "on_task_done", "ts": time.time(), "sid": sid or None,
            })
            self._append_flow_history(sid, prompt, content)
            return RunResult(
                task_id=task_id, session_id=sid or "", preset_name="flow",
                status="done" if status == "done" else status,
                final_content=content, error=error,
            )
        except Exception as exc:  # noqa: BLE001 — flow exceptions are handled as task errors
            self._publish({
                "type": "on_task_error", "error": f"{type(exc).__name__}: {exc}",
                "ts": time.time(), "sid": sid or None,
            })
            return RunResult(
                task_id=task_id, session_id=sid or "", preset_name="flow",
                status="error", final_content="",
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            with self._lock:
                self._chat_flow_runs.pop(key, None)

    def _append_flow_history(self, sid: Optional[str], prompt: str,
                             content: str) -> None:
        """Write this flow round's conversation into the session history (consistent with normal tasks)."""
        if not sid:
            return
        agent = self._agent
        sm = getattr(agent, "session_manager", None) if agent is not None else None
        if sm is None:
            return
        try:
            sess = sm.get_session(sid)
            if sess is None:
                return
            from norpagent.protocols.model import ChatMessage

            sm.append_message(sess.id, ChatMessage(role="user", content=prompt))
            if content:
                sm.append_message(
                    sess.id, ChatMessage(role="assistant", content=content))
        except Exception:  # noqa: BLE001 — history-write failures do not affect the task result
            pass

    # ── internals ───────────────────────────────────────

    def _publish(self, item: dict) -> None:
        """Push one event to all SSE subscribers (publisher cost O(subscriber count); no list copies).

        The subscriber table uses the same copy-on-write as the EventBus: only a
        reference is taken under the lock here; each subscriber's push is a
        "bounded deque append + one notify on empty→non-empty", amortized O(1) —
        under extreme-concurrency pushes, lock contention does not scale with the
        subscriber count.
        """
        with self._lock:
            self._history.append(item)
            if len(self._history) > self.history_limit:
                self._history = self._history[-self.history_limit:]
            subscribers = self._subscribers
        for sub in subscribers:
            sub.push(item)

    def _new_subscriber(self) -> _SSESubscriber:
        """Create a bounded-buffer subscriber for one SSE connection (current backpressure config)."""
        with self._lock:
            size = self._sse_queue_size
            policy = self._sse_queue_policy
        sub = _SSESubscriber(size, policy)
        with self._lock:
            self._subscribers = self._subscribers + [sub]
        return sub

    def _drop_subscriber(self, sub: _SSESubscriber) -> None:
        """Remove one SSE subscriber (called when a connection closes; copy-on-write replacement)."""
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s is not sub]

    def _recent_history(self) -> List[dict]:
        with self._lock:
            return list(self._history[-200:])

    # ── SSE backpressure (extreme-concurrency ops: startup config + runtime hot change) ──

    def set_sse_queue(self, sse_queue_size: Optional[int] = None,
                      sse_queue_policy: Optional[str] = None) -> Dict[str, Any]:
        """Hot-change the SSE backpressure config at runtime (no restart; effective immediately on existing connections).

        - ``sse_queue_size``: per-connection buffer cap (0 = unlimited);
        - ``sse_queue_policy``: drop_oldest (default; slow clients drop the
          oldest) / drop_newest / unlimited.

        Returns the applied config and subscriber stats. Equivalent REST entry:
        POST /api/streams.
        """
        with self._lock:
            if sse_queue_size is not None:
                try:
                    self._sse_queue_size = max(0, int(sse_queue_size))
                except (TypeError, ValueError):
                    pass
            if isinstance(sse_queue_policy, str) and sse_queue_policy in _SSE_POLICIES:
                self._sse_queue_policy = sse_queue_policy
            size = self._sse_queue_size
            policy = self._sse_queue_policy
            subscribers = self._subscribers
        for sub in subscribers:
            sub.resize(size, policy)
        return {
            "ok": True,
            "sse_queue_size": size,
            "sse_queue_policy": policy,
            "subscribers": len(subscribers),
        }

    def streams_info(self) -> Dict[str, Any]:
        """SSE backpressure state and stats (shared by GET /api/streams / stats / health)."""
        with self._lock:
            subscribers = self._subscribers
            size = self._sse_queue_size
            policy = self._sse_queue_policy
            batch = self._sse_batch
            interval = self._sse_batch_interval
        per_sub = [s.stats() for s in subscribers]
        return {
            "sse_queue_size": size,
            "sse_queue_policy": policy,
            "sse_batch": batch,
            "sse_batch_interval": interval,
            "subscribers": len(subscribers),
            "dropped_total": sum(s["dropped"] for s in per_sub),
            "max_buffered": max((s["buffered"] for s in per_sub), default=0),
            "subscriber_stats": per_sub,
        }

    def shutdown(self) -> None:
        """Stop the HTTP service and disconnect all subscribers (idempotent; callable across threads)."""
        # hosted CNB instances (FarStars console one-click launch): stop with the service
        try:
            self.cnb_stop({})
        except Exception:  # noqa: BLE001 — best effort
            pass
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for sub in self._subscribers:
                sub.push({"type": "notify", "message": "server closed",
                          "ts": time.time(), "sid": None})
            self._subscribers = []
            server = self._server
            self._server = None
        if server is None:
            return
        # server.shutdown() must be called outside the serve_forever thread,
        # otherwise it deadlocks (defensive: same thread only closes the underlying socket).
        if self._thread is not None and threading.current_thread() is self._thread:
            try:
                server.server_close()
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            server.shutdown()
        except Exception:  # noqa: BLE001 — may already have been closed by the service thread
            pass
        try:
            server.server_close()
        except Exception:  # noqa: BLE001
            pass


def _package_version() -> str:
    try:
        import norpagent

        return getattr(norpagent, "__version__", "?")
    except Exception:  # noqa: BLE001
        return "?"


__all__ = ["WebUI", "json_safe"]
