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
_SECRET_KEYS = ("api_key", "tts_service_api_key", "stt_service_api_key")


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
    "api_base": "https://api.deepseek.com",
    "api_key": "",
    "remote_models": [],                  # remote model list from the last successful fetch (shown in the flow module dock)
    "project_root": default_project_root(),  # default workspace (per the operating system)
    "plugin_dirs": [],
    "norp_safe_enabled": True,
    "plugins_enabled": True,
    "close_button_behavior": "minimize_to_tray",
    "use_responses_api": False,
    "queue_max_size": 200,
    "max_steps": 128,
    "task_timeout": 0,
    "api_request_timeout": 180,
    "enable_web_search": False,
    "native_confirm_enabled": True,
    "native_confirm_write": True,
    "native_confirm_delete": True,
    "native_confirm_exec": True,
    "think_level": "high",
    "temperature": 1.0,
    "max_tokens": 32767,
    "memory": True,
    "memory_mode": "full",
    "max_rounds": 10,
    "custom_system_prompt_enabled": False,
    "custom_system_prompt": "",
    "custom_system_prompt_file": "",
    "jailbreak_guard_enabled": True,
    "jailbreak_guard_action": "block",
    "vision_enabled": False,
    "vision_service_url": "",
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
    "plugin_security_audit": "block",
    "plugin_security_import_restrict": "strict",
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

_MAX_JSON = 1_000_000
_MAX_UPLOAD_JSON = 64_000_000
_MAX_UPLOAD_FILE = 10 * 1024 * 1024

# DeepSeek retired deepseek-chat / deepseek-reasoner on 2026-07-24: when legacy
# fetch caches or third-party mirrors still return these two names, they are
# filtered out of the remote model list.
RETIRED_REMOTE_MODELS = {"deepseek-chat", "deepseek-reasoner"}


def filter_remote_models(models: Any) -> List[str]:
    """Filter retired remote model names (deepseek-chat / deepseek-reasoner etc.)."""
    if not isinstance(models, (list, tuple, set)):
        return []
    return [str(m) for m in models
            if str(m).strip().lower() not in RETIRED_REMOTE_MODELS]


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
        self._session_meta: Dict[str, Dict[str, Any]] = {}
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
                elif path == "/events":
                    self._handle_sse()
                elif path == "/api/status":
                    self._json(200, ui.stats())
                elif path == "/api/cnb/health":
                    # FarStars 星轨控制台：同源皮层总线代理（只允许本机回环
                    # 目标；浏览器侧无法跨源直连 CNB 总线，统一走本代理）。
                    base = str(query.get("base", [""])[0] or "").strip()
                    self._json(200, ui.cnb_proxy("GET", base))
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
                    self._json(200, {"content": None})
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
                    data = self._read_json()
                    prompt = str(data.get("prompt") or "").strip()
                    if not prompt:
                        self._json(400, {"ok": False, "error": "prompt is empty"})
                        return
                    task_id = ui.submit(
                        prompt, str(data.get("session_id") or "") or None
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
                    # FarStars 星轨控制台：同源皮层控制代理（base 仅回环）。
                    # body 原样作为 /cnb/ctrl 请求转发（topo/reports/audit/
                    # behavior/exec/freeze/sweep/config...）。
                    _q = parse_qs(parsed.query)
                    base = str(_q.get("base", [""])[0] or "").strip()
                    body = self._read_json()
                    self._json(200, ui.cnb_proxy("POST", base, ctrl=body))
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
                elif path.startswith("/api/sessions/"):
                    self._handle_session_post(path, data=self._read_json())
                elif path == "/api/config":
                    data = self._read_json()
                    self._json(200, {"ok": True, "config": ui.save_config(
                        data.get("config") or {})})
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
                    data = self._read_json()
                    self._json(200, {"ok": True})
                elif path == "/api/log":
                    data = self._read_json()
                    _logger.info("frontend: %s", str(data.get("message") or "")[:2000])
                    self._json(200, {"ok": True})
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
                else:
                    self._json(404, {"error": "not found"})

            def _handle_session_post(self, path: str, data: dict) -> None:
                rest = path[len("/api/sessions/"):].strip("/")
                parts = rest.split("/")
                sid = parts[0] if parts else ""
                if len(parts) >= 2:
                    if parts[1] == "title":
                        ui.set_session_title(sid, str(data.get("title") or ""))
                        self._json(200, {"ok": True})
                        return
                    if parts[1] == "workspace":
                        ui.set_session_workspace(sid, str(data.get("workspace") or ""))
                        self._json(200, {"ok": True})
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
            max_tokens = self._config.get("max_tokens")
        effort = _THINK_LEVEL_MAP.get(think, "high")
        defaults: Dict[str, Any] = {}
        if effort != "none":
            defaults["reasoning_effort"] = effort
        else:
            try:
                defaults["temperature"] = float(temperature) if temperature is not None else 1.0
            except (TypeError, ValueError):
                defaults["temperature"] = 1.0
        if max_tokens:
            try:
                defaults["max_tokens"] = int(max_tokens)
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
                    tp = dict(task_params or {})
                    # the settings panel's sampling parameters inject into the task
                    # (callers may override explicitly)
                    for key, value in self._task_defaults().items():
                        tp.setdefault(key, value)
                    tp.setdefault("_stop_check", lambda: sid in self._stop_requests)
                    meta = self._session_meta.get(sid)
                    if meta and meta.get("workspace") and "workspace_root" not in tp:
                        tp["workspace_root"] = meta["workspace"]
                    result = self._invoke_handler(self._handler_fn, prompt, sid, tp)
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
                    self._stop_requests.discard(sid)

        threading.Thread(
            target=worker, daemon=True, name=f"norpagent-webui-task-{task_id}"
        ).start()
        return task_id

    def stop_task(self, session_id: Optional[str]) -> None:
        """Request stopping the running task of a session (takes effect at step boundaries)."""
        sid = session_id or ""
        runner = None
        with self._lock:
            if sid and sid in self._running_sessions:
                self._stop_requests.add(sid)
            runner = self._chat_flow_runs.get(sid)
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
                    "reason", "reasoning", "tool_call_tokens"):
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

    def ask_user(self, question: str, default: str = "") -> str:
        """Ask the user (human approval / clarification). Waits for the user to
        answer on the page; on timeout returns default, so automation scenarios
        never hang.
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
        with self._lock:
            self._session_meta[sess.id] = {
                "title": title or sess.title or sess.id[:8],
                "workspace": workspace or "",
                "created_at": getattr(sess, "created_at", time.time()),
            }
        return self.session_info(sess.id)

    def session_info(self, sid: str) -> Dict[str, Any]:
        sm = self._session_manager()
        sess = sm.get_session(sid)
        with self._lock:
            meta = self._session_meta.get(sid) or {}
        if sess is None and not meta:
            return {"id": sid, "exists": False}
        return {
            "id": sid,
            "title": meta.get("title") or (getattr(sess, "title", "") or sid[:8]),
            "workspace": meta.get("workspace") or "",
            "created_at": meta.get("created_at") or getattr(sess, "created_at", 0.0),
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
            out.append({
                "id": sess.id,
                "title": meta.get("title") or getattr(sess, "title", "") or sess.id[:8],
                "workspace": meta.get("workspace") or "",
                "created_at": meta.get("created_at")
                or getattr(sess, "created_at", time.time()),
                # front session-pill state: whether a task is currently running
                "running": sess.id in running,
                "has_task": bool(sess.id in running
                                 or getattr(sess, "message_count", 0)),
            })
        return out

    def session_messages(self, sid: str) -> List[Dict[str, str]]:
        sm = self._session_manager()
        messages = []
        for m in sm.history(sid):
            role = getattr(m, "role", "") or ""
            if role == "tool":
                continue  # tool messages are internal process; not shown in the chat panel
            messages.append({
                "role": role,
                "content": getattr(m, "content", "") or "",
                # 思考过程随历史返回，前端切会话 / 空闲同步重绘后思考块不丢失
                "thinking": getattr(m, "reasoning", "") or "",
            })
        return messages

    def close_session(self, sid: str) -> Dict[str, Any]:
        self.stop_task(sid)
        try:
            sm = self._session_manager()
            sm.delete_session(sid)
        except Exception:  # noqa: BLE001 — runtime not bound etc.
            pass
        with self._lock:
            self._session_meta.pop(sid, None)
        return {"ok": True}

    def set_session_title(self, sid: str, title: str) -> None:
        with self._lock:
            meta = self._session_meta.setdefault(sid, {})
            meta["title"] = title
        try:
            sm = self._session_manager()
            sess = sm.get_session(sid)
            if sess is not None:
                sess.title = title
        except Exception:  # noqa: BLE001
            pass

    def set_session_workspace(self, sid: str, workspace: str) -> None:
        with self._lock:
            meta = self._session_meta.setdefault(sid, {})
            meta["workspace"] = workspace

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
                if key in _SECRET_KEYS:
                    # accept plaintext or an already-encrypted (marker) value
                    self._config[key] = _decrypt_api_key(value)
                else:
                    self._config[key] = value
            self._config["_initialized"] = True
            cfg = dict(self._config)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
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
        return self.get_config()

    def set_api_key(self, api_key: str) -> Dict[str, Any]:
        with self._lock:
            self._config["api_key"] = _decrypt_api_key(api_key or "")
            self._config["_initialized"] = True
            cfg = dict(self._config)
        self._save_config_to_disk(cfg)
        self._apply_config(cfg)
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
        """List models: registry models + (when base_url and a key are provided) remote models.

        An explicit ``api_key`` is preferred when passed (the frontend "fetch model
        list" sends the key currently typed in the input box, no save needed to
        fetch). After a successful fetch, the remote model list is cached in the
        config (``remote_models``), shown in real time by the flow snapshot's
        module-dock "models" group.
        """
        reg = self._registry()
        names = sorted(reg.list_models()) if reg is not None else []
        remote: List[str] = []
        error: Optional[str] = None
        used_key = api_key or self._config.get("api_key")
        if base_url and used_key:
            try:
                from openai import OpenAI  # noqa: F401  optional dependency
            except ImportError:
                error = "openai SDK not installed (pip install norpagent[openai])"
            else:
                try:
                    client = OpenAI(
                        base_url=base_url,
                        api_key=used_key,
                        timeout=15,
                    )
                    remote = [m.id for m in client.models.list()][:200]
                    remote = filter_remote_models(remote)
                except Exception as exc:  # noqa: BLE001
                    error = f"{exc}"
        if remote:
            # remote model list cache: update memory + persist the config (failures do not block)
            with self._lock:
                self._config["remote_models"] = list(remote)
                cfg = dict(self._config)
            self._save_config_to_disk(cfg)
            return {"models": remote, "error": None}
        return {"models": names, "error": error}

    def get_plugin_dirs(self) -> List[str]:
        with self._lock:
            dirs = self._config.get("plugin_dirs") or []
        return list(dirs)

    def list_plugins(self) -> List[Dict[str, Any]]:
        reg = self._registry()
        if reg is None:
            return []
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
            })
        return out

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
            "plugins_enabled": cfg.get("plugins_enabled", True),
            "audit": cfg.get("plugin_security_audit", "block"),
            "import_restrict": cfg.get("plugin_security_import_restrict", "strict"),
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
            sec = data.get("security")
            if isinstance(sec, dict):
                for key, value in sec.items():
                    if key.startswith("plugin_") or key in ("norp_safe_enabled",):
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

    # ── CNB cortex loopback proxy (FarStars console data plane) ──
    # 星轨控制台（norp-farstars.html）通过本同源代理访问真实 CNB 皮层总线：
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
        """转发皮层总线请求（GET /cnb/health 或 POST /cnb/ctrl）。

        失败不抛异常——统一返回 {"ok": False, "error": ...}，前端据此显示
        连接错误（皮层未启动 / 地址不可达 / 非回环目标被拒）。
        """
        base = (base or "").strip()
        if not self._cnb_base_ok(base):
            return {"ok": False,
                    "error": "cortex base 仅允许本机回环 http://127.0.0.1:<port> / http://localhost:<port>"}
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
                if len(raw) > _MAX_UPLOAD_FILE:
                    out.append({"name": name, "type": ftype,
                                "error": "file too large (max 10MB)"})
                    continue
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                is_image = ftype.startswith("image/") or ext in self._IMAGE_EXTS
                if is_image:
                    out.append({"name": name, "type": ftype or "image/png",
                                "kind": "image", "data": data})
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
                    "error": "视觉 API 未启用（设置 → 视觉 API → 启用视觉 API）"}
        service_url = str(cfg.get("vision_service_url") or "").strip()
        if not service_url:
            return {"ok": False, "error": "未配置视觉服务地址（设置 → 视觉 API）"}
        images = data.get("images")
        if not isinstance(images, list) or not images:
            return {"ok": False, "error": "images must be a non-empty list"}
        prompt = str(data.get("prompt") or "").strip() or "请详细描述这张图片的内容。"
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
            return {"ok": False, "error": "语音朗读未启用（设置 → 声音）"}
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
            return {"ok": False, "error": f"TTS 失败: {exc}"}
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
            return {"ok": False, "error": f"audio base64 解码失败: {exc}"}
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
            return {"ok": False, "error": f"STT 失败: {exc}"}
        if not text.strip():
            return {"ok": False, "error": "没有识别到语音内容"}
        return {"ok": True, "text": text.strip()}

    def beep_notify(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/beep: generate the new-message notification tone (WAV, base64)."""
        with self._lock:
            cfg = dict(self._config)
        if not cfg.get("sound_notify_enabled", True):
            return {"ok": False, "error": "提示音未启用"}
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
                    "plugin_security_audit": cfg.get("plugin_security_audit", "block"),
                    "plugin_security_import_restrict":
                        cfg.get("plugin_security_import_restrict", "strict"),
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
                # filter retired model names (deepseek-chat / deepseek-reasoner and other historical caches)
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
