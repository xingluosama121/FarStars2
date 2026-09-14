# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.farstars_app.entry — 成品发行版入口实现（R-006 / R-014 / R-023 / R-025 / R-007）。

架构书 §3.1（拍板 3A / O5）：成品态入口的本体位于独立入口模块
``norpagent.farstars_app``，与 frame 基座分离，避免未来拆分伤筋动骨。
``norpagent.unbox`` 保留为兼容转发层（同名导出）。

``norpagent unbox`` 一键拉起「开箱即用的自进化用户软件」（架构书 §8.1）：

    中枢（可选）       CNB level 0 中枢进程（含引擎，非裸壳）；默认不携带，
                       显式 --cnb 启用（R-023）；启用时端口必须手动配置
                       （R-025：缺端口即抛错）。
    核心智能体         单个功能强大的智能体（R-014：不设默认原子集），
                       由引擎 + 成品档案装配（默认 standard 预设 + 全量工具面）。
    控制台             Web 前端（对话 / 设置 / 回退 / 插件 / 控制台页），
                       浏览器打开即用。
    进化器             自进化回路设置底座（R-004/R-005：热重载 + 勾选审批制），
                       档案中可开关，默认开启（重大人工、普通自动）。
    成品档案           ``~/.norpagent/unbox.json``：装配清单 + 默认设置 +
                       视角（声明式数据，可读可改）。

用户三不原则（R-007）：不需要看开发手册、不需要知道怎么开发、不需要知道
运行过程；但控制台常驻「运行过程可查、可干预」通道（白盒默认不打扰）。

用户态全量工具：成品态启动默认**全量装配全部内置工具**（档案 ``tools``
字段，默认 ``"all"``；可给显式工具名列表裁剪）。

用法::

    norpagent unbox                        # 浏览器打开即用（默认端口 8890）
    norpagent unbox --port 8890 --no-browser
    norpagent unbox --smoke                # 自检：装配 → 健康检查 → 退出（CI/测试）
    norpagent unbox --cnb --cnb-port 17811 # 显式启用 CNB（端口必配，R-025）
    norpagent unbox --cnb-parent http://127.0.0.1:17800 --cnb-port 17811
                                           # 以节点身份加入既有神经树
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_PORT = 8890

# 成品档案默认装配（声明式；用户可改，改动即时生效）
DEFAULT_PROFILE: Dict[str, Any] = {
    "format": "farstars-unbox/1",
    "name": "FarStars Unbox",
    "preset": "standard",          # 单个功能强大的智能体（全工具面）
    "tools": "all",                # 用户态全量工具：默认装配全部内置工具（可给显式列表裁剪）
    "model": None,                 # None = 引擎默认；可填 openai_compat 等
    "ui": "web",
    "port": DEFAULT_PORT,
    "console": True,               # 星轨控制台 / 内置控制台页
    "evolution": {                 # 自进化（R-004 / R-005 底座设置）
        "enabled": True,
        "approval": "major-manual",  # 默认：重大人工批准、普通自动批准
        "idle_policy": "reduced",    # 闲时减少或不进化（R-011）
    },
    "cnb": {                       # CNB（R-023：默认关闭；启用时端口必配 R-025）
        "enabled": False,
        "node_id": None,
        "parent": None,
        "port": None,
        # 神经树显式定义（2026-09-12 反馈轮）：JSON / PY 文件路径或 JSON 文本；
        # 给出后整树按定义装配（端口由定义携带，不必再配 cnb.port）。
        "tree": None,
    },
}


class UnboxError(RuntimeError):
    """成品启动错误（档案非法 / 端口缺失等；信息明确、直接给用户看）。"""


def unbox_home() -> str:
    """成品档案目录（默认 ~/.norpagent；可用 NORPAGENT_UNBOX_HOME 覆盖）。"""
    override = (os.environ.get("NORPAGENT_UNBOX_HOME") or "").strip()
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".norpagent")


def profile_path() -> str:
    return os.path.join(unbox_home(), "unbox.json")


def load_profile(path: Optional[str] = None) -> Dict[str, Any]:
    """读取成品档案；不存在则以默认档案创建（首次运行开箱即用）。"""
    p = path or profile_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise UnboxError(f"profile file is not a JSON object: {p}")
            merged = json.loads(json.dumps(DEFAULT_PROFILE))
            _deep_merge(merged, data)
            return merged
        except UnboxError:
            raise
        except Exception as exc:  # noqa: BLE001 — 档案损坏：信息明确，不静默
            raise UnboxError(f"failed to read profile file: {p}: {exc}") from exc
    profile = json.loads(json.dumps(DEFAULT_PROFILE))
    save_profile(profile, p)
    return profile


def save_profile(profile: Dict[str, Any], path: Optional[str] = None) -> str:
    p = path or profile_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, ensure_ascii=False, indent=2)
    return p


def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def all_builtin_tools() -> List[str]:
    """全部内置工具名（用户态默认全量装配；按注册表默认装配枚举）。

    失败时返回空列表——调用方回落到预设自带工具面（不阻塞启动）。
    """
    try:
        from norpagent.builtin import install_defaults
        from norpagent.kernel import Registry

        reg = Registry()
        install_defaults(reg)
        return sorted(str(t) for t in reg.list_tools())
    except Exception:  # noqa: BLE001 — 枚举失败不阻塞成品启动
        return []


def _resolve_tools(profile: Dict[str, Any]) -> Optional[List[str]]:
    """解析成品档案的 tools 字段：'all' = 全量内置工具；列表 = 显式裁剪；空 = 预设默认。"""
    spec = profile.get("tools", "all")
    if isinstance(spec, str) and spec.strip().lower() == "all":
        tools = all_builtin_tools()
        return tools or None
    if isinstance(spec, (list, tuple)):
        tools = [str(t) for t in spec if str(t).strip()]
        return tools or None
    return None


def _http_json(url: str, timeout: float = 3.0) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 — loopback
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def run_unbox(args: argparse.Namespace) -> int:
    profile = load_profile(getattr(args, "profile", None))
    port = int(args.port or profile.get("port") or DEFAULT_PORT)
    preset = str(profile.get("preset") or "standard")
    model = profile.get("model") or None

    # CNB：默认关闭；--cnb / --cnb-parent / --cnb-tree 显式启用；
    # 启用时端口必配（R-025）；2026-09-12 反馈轮（错误语义）：配置错误显式
    # 报错但不阻塞成品启动——成品照常运行、神经树不加载（错误信息明确）。
    cnb_cfg = dict(profile.get("cnb") or {})
    if getattr(args, "cnb", False):
        cnb_cfg["enabled"] = True
    if getattr(args, "cnb_node_id", None):
        cnb_cfg["node_id"] = args.cnb_node_id
    if getattr(args, "cnb_parent", None):
        cnb_cfg["parent"] = args.cnb_parent
    if getattr(args, "cnb_port", None):
        cnb_cfg["port"] = int(args.cnb_port)
    if getattr(args, "cnb_tree", None):
        cnb_cfg["tree"] = args.cnb_tree
        cnb_cfg["enabled"] = True
    cnb_tree = cnb_cfg.get("tree")
    cnb_enabled = bool(cnb_cfg.get("enabled"))
    cnb_note = ""
    if cnb_enabled:
        if cnb_tree and cnb_cfg.get("parent"):
            cnb_enabled = False
            cnb_note = ("CNB config error (does not block startup; neural tree not loaded): "
                        "tree (full-tree definition) and parent (join an existing tree) "
                        "cannot both be given.")
            print(f"[unbox][cnb][error] {cnb_note}")
        elif not cnb_tree and not cnb_cfg.get("port"):
            cnb_enabled = False
            cnb_note = ("CNB config error (does not block startup; neural tree not loaded): "
                        "the port is never hardcoded and must be set manually. Use "
                        "--cnb-port <1-65535>, or set cnb.port in the profile; you may "
                        "also pass --cnb-tree with a neural-tree definition (the port "
                        "is carried by it).")
            print(f"[unbox][cnb][error] {cnb_note}")
        elif not cnb_tree and not cnb_cfg.get("node_id"):
            cnb_cfg["node_id"] = f"unbox-{os.getpid()}"

    kwargs: Dict[str, Any] = {
        "preset": preset,
        "ui": "web",
        "port": port,
    }
    if model:
        kwargs["model"] = model
    # 用户态全量工具：默认装配全部内置工具（档案 tools 字段可裁剪）
    tools = _resolve_tools(profile)
    if tools:
        kwargs["tools"] = tools
    # CNB 装配（R-023：默认关闭）：
    #  - 神经树模式（tree 给出）：整树按显式定义装配（np 路径内建），宿主引擎
    #    绑定为根节点（中枢）模块；端口由定义携带（2026-09-12 反馈轮）。
    #  - 独立模式（无 parent）：本进程内含一个 level 0 中枢（树根），引擎经
    #    CnbAdapter 绑定为中枢的引擎槽——完整 norpagent 实例同时成为中枢节点
    #    的一个标准模块（R-024 修订：实例可插入 CNB 节点）。
    #  - 入树模式（给了 parent）：引擎以节点身份自动挂载到既有神经树。
    cnb_standalone = cnb_enabled and not cnb_cfg.get("parent") and not cnb_tree
    if cnb_enabled and cnb_tree:
        kwargs["cnb"] = {"cnb": True, "tree": cnb_tree}
    elif cnb_enabled and not cnb_standalone:
        kwargs["cnb"] = {
            "cnb": True,
            "node_id": cnb_cfg["node_id"],
            "port": cnb_cfg["port"],
            "parent": cnb_cfg["parent"],
        }

    # 进化底座：档案开关 + 默认审批策略（写入设置事实源；失败不阻塞成品启动）
    try:
        from norpagent.evolution import bootstrap as evolution_bootstrap

        evolution_bootstrap(profile.get("evolution") or {})
    except Exception as exc:  # noqa: BLE001 — 进化底座尽力而为
        print(f"[unbox] evolution bootstrap skipped: {exc}")

    import norpagent as np

    engine = np(**kwargs)

    cortex = None
    if cnb_standalone:
        # 独立成品：中枢（树根）+ 引擎槽（完整实例模块挂入中枢节点槽位）
        from norpagent.cnb import Cortex
        from norpagent.cnb.engine import CnbAdapter

        cortex = Cortex(node_id="cortex", host="127.0.0.1",
                        port=int(cnb_cfg["port"]),
                        meta={"desc": "FarStars unbox cortex",
                              "engine": "norpagent", "unbox": True})
        adapter = CnbAdapter(engine, cortex, {})
        with engine._cnb_lock:
            engine._cnb = adapter
        cortex.start()

    import webbrowser

    url = f"http://127.0.0.1:{port}/"
    console_url = f"http://127.0.0.1:{port}/farstars"
    print("FarStars out-of-the-box software is online")
    print(f"  entry       {url}")
    print(f"  console     {console_url}")
    print(f"  agent       single powerful agent (preset={preset})")
    print(f"  tools       full assembly ({len(tools) if tools else 'preset default'} items)")
    print(f"  profile     {profile_path()}")
    if cnb_enabled and cnb_tree:
        print(f"  CNB         neural tree (explicit definition, no preset shape)  "
              f"tree={_tree_brief(cnb_tree)}")
    elif cnb_enabled:
        mode_text = "standalone cortex (tree root, with full instance slot modules)" if cnb_standalone \
            else f"tree node (parent={cnb_cfg.get('parent')})"
        print(f"  CNB         {mode_text}  node={cnb_cfg.get('node_id')} "
              f"port={cnb_cfg.get('port')}")
    elif cnb_note:
        print("  CNB         not loaded (config error reported; does not block running)")
    else:
        print("  CNB         not carried (off by default, R-023)")
    print("  exit        Ctrl+C (or quit from the console)")

    if getattr(args, "smoke", False):
        cnb_port_arg = int(cnb_cfg["port"]) if (cnb_enabled and cnb_cfg.get("port")) else None
        return _smoke(engine, port, cnb_enabled, cortex, cnb_port_arg,
                      cnb_tree=cnb_tree)

    if not getattr(args, "no_browser", False):
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 — 打不开浏览器不影响服务
            pass
    try:
        while True:
            if np.stop():
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
    finally:
        if cortex is not None:
            try:
                cortex.stop()
            except Exception:  # noqa: BLE001
                pass
        try:
            engine.request_stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            np.shutdown()
        except Exception:  # noqa: BLE001
            pass
    print("[unbox] offline")
    return 0


def _tree_brief(tree_spec: Any) -> str:
    """神经树定义来源的简要展示摘要（仅展示，不解析）。"""
    if isinstance(tree_spec, dict):
        levels = tree_spec.get("levels")
        n = len(levels) if isinstance(levels, list) else "?"
        return f"dict ({n} level blocks)"
    text = str(tree_spec or "")
    if text.startswith("{"):
        return "JSON text"
    return text


def _smoke(engine: Any, port: int, cnb_enabled: bool,
           cortex: Any = None, cnb_port: Optional[int] = None,
           cnb_tree: Any = None) -> int:
    """自检：引擎 RUNNING + Web 健康 + （可选）CNB 树就绪 → 退出。

    错误语义（2026-09-12 反馈轮）：CNB 配置错误不阻塞成品启动（显式报错、
    神经树不加载），自检按「产品健康」口径通过并如实打印 config-error。
    """
    deadline = time.time() + 15.0
    health: Dict[str, Any] = {}
    while time.time() < deadline:
        try:
            health = _http_json(f"http://127.0.0.1:{port}/api/health")
            break
        except Exception:  # noqa: BLE001 — 启动窗口内重试
            time.sleep(0.3)
    ok = bool(health) and engine.is_running()
    if cnb_enabled:
        if cnb_tree is not None:
            # 神经树模式：等待引擎挂载状态（mounted / failed / config-error）
            cnb_status = None
            deadline = time.time() + 20.0
            while time.time() < deadline:
                cnb_status = getattr(engine, "cnb_status", None)
                if cnb_status in ("mounted", "failed", "stopped", "config-error"):
                    break
                time.sleep(0.3)
            ok = ok and cnb_status == "mounted"
            print(f"[unbox] smoke: cnb_tree_status={cnb_status}")
        elif cortex is not None and cnb_port:
            # 独立模式：检查中枢总线健康 + 中枢节点上的实例槽位模块
            cnb_ok = False
            deadline = time.time() + 15.0
            while time.time() < deadline:
                try:
                    cnb_ok = bool(_http_json(
                        f"http://127.0.0.1:{cnb_port}/cnb/health"))
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.3)
            slot = cortex.slots.get("norpagent")
            slot_ok = slot is not None and \
                slot.module.kind == "norpagent-instance"
            ok = ok and cnb_ok and slot_ok
            print(f"[unbox] smoke: cortex_health={cnb_ok} "
                  f"instance_module_mounted={slot_ok}")
        else:
            # 入树模式：等待引擎挂载状态；config-error 属「显式报错、不阻塞
            # 启动」的既定语义，按产品健康口径容忍（不视为失败）。
            cnb_status = None
            deadline = time.time() + 20.0
            while time.time() < deadline:
                cnb_status = getattr(engine, "cnb_status", None)
                if cnb_status in ("mounted", "failed", "stopped",
                                  "config-error"):
                    break
                time.sleep(0.3)
            if cnb_status == "config-error":
                print(f"[unbox] smoke: cnb_status=config-error "
                      f"(non-blocking; neural tree not loaded) error="
                      f"{getattr(engine, 'cnb_error', None)}")
            else:
                ok = ok and cnb_status == "mounted"
                print(f"[unbox] smoke: cnb_status={cnb_status}")
    print(f"[unbox] smoke: health={bool(health)} engine_running={engine.is_running()}")
    if cortex is not None:
        try:
            cortex.stop()
        except Exception:  # noqa: BLE001
            pass
    try:
        engine.request_stop()
    except Exception:  # noqa: BLE001
        pass
    import norpagent as np

    try:
        np.shutdown()
    except Exception:  # noqa: BLE001
        pass
    if ok:
        print("SMOKE OK")
        return 0
    print("SMOKE FAILED", file=sys.stderr)
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="norpagent unbox",
        description="Launch the out-of-the-box self-evolving user software (product distribution entry)",
    )
    parser.add_argument("--port", type=int, default=None,
                        help=f"Web entry port (default from profile; first run {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open the browser automatically")
    parser.add_argument("--smoke", action="store_true",
                        help="self-check mode: assemble -> health check -> exit (for tests/CI)")
    parser.add_argument("--cnb", action="store_true",
                        help="explicitly enable CNB (off by default, R-023; the port must be set manually, R-025)")
    parser.add_argument("--cnb-node-id", default=None, help="CNB node id")
    parser.add_argument("--cnb-parent", default=None,
                        help="join an existing neural tree as a node (parent bus address)")
    parser.add_argument("--cnb-port", type=int, default=None,
                        help="CNB node port (required when enabled; missing -> explicit error, does not block startup)")
    parser.add_argument("--cnb-tree", default=None,
                        help="neural tree explicit definition (JSON / PY file path or JSON text; "
                             "the port is carried by the definition; no tree shape is preset)")
    parser.add_argument("--profile", default=None, help="override the profile file path")
    args = parser.parse_args(argv)

    try:
        return run_unbox(args)
    except UnboxError as exc:
        print(f"[unbox][error] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — 启动失败给出救援提示
        print(f"[unbox][error] startup failed: {exc}", file=sys.stderr)
        print("  safe mode (minimal kernel): norpagent --safe-mode", file=sys.stderr)
        print("  crash rescue rollback: norpagent-rescue rollback --last-good", file=sys.stderr)
        return 1


__all__ = [
    "DEFAULT_PORT",
    "DEFAULT_PROFILE",
    "UnboxError",
    "unbox_home",
    "profile_path",
    "load_profile",
    "save_profile",
    "all_builtin_tools",
    "run_unbox",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
