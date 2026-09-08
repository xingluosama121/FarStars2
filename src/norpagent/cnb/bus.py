# -*- coding: utf-8 -*-
"""
norpagent.cnb.bus — 中枢神经总线传输层

零依赖实现（仅标准库）：每个 CNB 节点起一个 ThreadingHTTPServer 作为
总线接入点，客户端用 urllib 投递消息。

端点：
  POST /cnb/msg     投递 CNB 消息信封（JSON）
  GET  /cnb/health  健康检查（返回节点身份与等级）

安全约束（传输层强制）：
  - 默认只绑定 127.0.0.1（跨机部署需显式配置 host，并自行保证网络可信）。
  - 上行消息（kind=uplink）在投递前剥离全部控制字段（protocol.sanitize_uplink_payload）。
  - 下行消息（kind=downlink）必须由接收方校验发送方是自己的祖先，否则拒绝。
"""

import json
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional

from . import protocol


# ----------------------------------------------------------------------
# 服务端
# ----------------------------------------------------------------------

class BusServer(ThreadingHTTPServer):
    """节点总线服务端。daemon_threads 防止阻塞线程堆积。"""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, node_ctx: Dict[str, Any]):
        self.node_ctx = node_ctx  # 由节点注入的上下文（身份 + 处理器）
        super().__init__(addr, handler)


class _BusHandler(BaseHTTPRequestHandler):
    """HTTP 消息处理：/cnb/msg 与 /cnb/health。"""

    protocol_version = "HTTP/1.1"

    # -- 工具方法 ------------------------------------------------------

    def _send_json(self, code: int, obj: Dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 静默访问日志（节点日志由 node 层负责）
        pass

    # -- 白盒：被拒消息留痕（bad json / 404 / 处理异常） ----------------

    def _note_reject(self, reason: str):
        """把总线层拒绝/异常事件交给节点审计（取证链可见协议层故障）。

        只记错误路径（坏 JSON、未知路径、处理器异常），正常消息由
        node.on_message 自身审计，不在此重复。
        """
        try:
            on_audit = self.server.node_ctx.get("on_audit")
            if on_audit is not None:
                on_audit(f"总线拒绝消息: {reason}")
        except Exception:  # noqa: BLE001 — 审计失败不影响应答
            pass

    # -- 路由 ----------------------------------------------------------

    def do_GET(self):
        path = self.path.rstrip("/")
        if path == "/cnb/health":
            ctx = self.server.node_ctx
            self._send_json(200, {
                "ok": True,
                "node_id": ctx.get("node_id"),
                "kind": ctx.get("kind"),
                "level": ctx.get("level"),
                "proto": protocol.PROTO_VERSION,
            })
        elif path == "/cnb/reports":
            # 查看本节点接收到的上报记录（皮层控制台 / CLI 用）
            on_reports = self.server.node_ctx.get("on_reports")
            if on_reports is None:
                self._note_reject("GET /cnb/reports 不受支持")
                self._send_json(404, {"ok": False, "error": "reports not supported"})
                return
            try:
                self._send_json(200, {"ok": True, "reports": on_reports()})
            except Exception as e:
                self._note_reject(f"GET /cnb/reports 异常: {e}")
                self._send_json(500, {"ok": False, "error": f"reports error: {e}"})
        else:
            self._note_reject(f"GET 未知路径 {self.path}")
            self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.rstrip("/")
        if path not in ("/cnb/msg", "/cnb/ctrl"):
            self._note_reject(f"POST 未知路径 {self.path}")
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            envelope = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._note_reject(f"坏 JSON: {type(e).__name__}: {e}")
            self._send_json(400, {"ok": False, "error": f"bad json: {e}"})
            return

        # 皮层控制端点：/cnb/ctrl（仅根节点/皮层提供；CLI 与 REPL 通过它指挥皮层）
        if path == "/cnb/ctrl":
            on_ctrl = self.server.node_ctx.get("on_ctrl")
            if on_ctrl is None:
                self._note_reject("POST /cnb/ctrl 不受支持")
                self._send_json(404, {"ok": False, "error": "ctrl not supported"})
                return
            try:
                reply = on_ctrl(envelope)
                self._send_json(200, reply if isinstance(reply, dict) else {"ok": True})
                return
            except Exception as e:
                self._note_reject(f"ctrl 处理异常: {type(e).__name__}: {e}")
                self._send_json(500, {"ok": False, "error": f"ctrl error: {e}"})
                return

        handler: Optional[Callable] = self.server.node_ctx.get("on_message")
        if handler is None:
            self._note_reject("无消息处理器")
            self._send_json(500, {"ok": False, "error": "no message handler"})
            return

        try:
            reply = handler(envelope)
            self._send_json(200, reply if isinstance(reply, dict) else {"ok": True})
        except Exception as e:
            self._note_reject(f"消息处理异常: {type(e).__name__}: {e}")
            self._send_json(500, {"ok": False, "error": f"handler error: {e}"})


def start_bus(host: str, port: int, node_ctx: Dict[str, Any]) -> BusServer:
    """在指定端口启动总线服务端（不阻塞，返回 server 对象）。"""
    server = BusServer((host, port), _BusHandler, node_ctx)
    t = threading.Thread(target=server.serve_forever, daemon=True,
                         name=f"cnb-bus-{port}")
    t.start()
    return server


# ----------------------------------------------------------------------
# 客户端
# ----------------------------------------------------------------------

class BusClient:
    """总线客户端：向指定节点的总线端点投递消息（urllib，零依赖）。"""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def post_msg(self, base_url: str, envelope: Dict) -> Dict:
        """投递一条消息，返回接收方的应答。"""
        url = base_url.rstrip("/") + "/cnb/msg"
        data = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post_ctrl(self, base_url: str, req: Dict) -> Dict:
        """调用皮层控制端点 /cnb/ctrl（拓扑/指令/权限/上报查询）。"""
        url = base_url.rstrip("/") + "/cnb/ctrl"
        data = json.dumps(req, ensure_ascii=False).encode("utf-8")
        r = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST")
        with urllib.request.urlopen(r, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health(self, base_url: str) -> Dict:
        """健康检查。"""
        url = base_url.rstrip("/") + "/cnb/health"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def try_post_msg(self, base_url: str, envelope: Dict) -> Dict:
        """容错投递：网络失败时返回 {"ok": False, "error": ...}，不抛异常。"""
        try:
            return self.post_msg(base_url, envelope)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
