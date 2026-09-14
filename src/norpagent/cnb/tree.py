# -*- coding: utf-8 -*-
# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.cnb.tree — 神经树定义（显式形状）与两种装配形态。

反馈轮（2026-09-12）要求：**CNB 不预设任何神经树形状**——启动时显式传入
整树定义；定义含必要参数（每层 LEVEL、各层个数、低层父级、端口等），
缺一个即显式报错；报错不阻塞主线程启动；运行中可经 remount 改形；
定义来源支持三种：直接参数（dict）、JSON 文件、PY 文件。

本模块提供：

- ``parse_tree_definition(spec)`` —— 三种来源统一解析 + 严格校验，产出
  规范化「树计划」（flattened nodes + 解析后的父级关系）。
  缺必要参数时抛 :class:`TreeDefinitionError`，错误信息逐条列出问题字段
  与示例（不静默、不猜测、不填默认拓扑）。
- ``build_in_process(plan)`` —— 同一进程内装配整棵树（中枢 + 各层节点，
  各自独立总线端口）；返回 :class:`InProcTree` 句柄。
- ``spawn_tree(plan)`` —— 按定义拉起的多进程真进程树（每节点一个
  ``norpagent cortex/node`` 子进程）；返回 :class:`SpawnTree` 句柄。
- 两种句柄共用同一套运行中改形能力：
    * ``apply(plan_or_spec)`` 手动改形（差分：保留未变节点 / 增删变更节点）；
    * ``start_watcher(path)`` 监视定义文件，变更时自动改形（错误保持现形）；
    * ``start_reconciler()`` 自动收敛（节点掉线/进程退出时按定义恢复）。

定义结构（``farstars-cnb-tree/1``）::

    {
      "format": "farstars-cnb-tree/1",
      "host": "127.0.0.1",
      "levels": [
        {"level": 0, "count": 1, "kind": "cortex", "node_id": "cortex",
         "port": 17800},
        {"level": 1, "count": 2, "kind": "agent", "parent": 17800,
         "base_port": 17810},
        {"level": 2, "count": 4, "kind": "worker", "parent": "level:1",
         "ports": [17820, 17821, 17822, 17823]}
      ],
      "auto": {"watch": false, "reconcile": false}
    }

必要参数（缺一即报错）：

- 每层 ``level``（0~63）与 ``count``（个数；level 0 必须为 1）；
- 端口：``port``（count=1）/ ``ports``（长度=count）/ ``base_port`` 三选一；
  不写死默认端口（R-025：端口必须显式配置）；
- 低层 ``parent``：父节点端口号（整型或数字串）、父节点 id、或 ``"level:N"``
  （挂到第 N 层节点，按定义顺序轮转）。

固定格式的 PY 文件支持：模块级 ``TREE`` / ``SPEC`` / ``tree`` / ``spec``
变量（可为返回 dict 的可调用对象），或 ``build()`` / ``build_tree()`` 函数。

装配形态与引擎装配的关系：

- 进程内（inproc）：装配裸神经节点（``NervousNode``）；``engine:true``
  在进程内模式显式拒绝（改用 spawn 模式，或经 ``np(cnb={"tree": ...})``
  由宿主把引擎绑定到根节点）。
- 多进程（spawn）：每个节点经 ``norpagent cortex/node`` 子进程启动；
  ``engine:true`` 节点携带完整内核引擎（等价 CLI 默认），否则 ``--bare``。

运行中的错误语义（反馈轮定稿）：定义错误显式报错；``np()`` 启动路径上
CNB 参数错误不阻塞主线程启动——宿主照常运行、神经树不加载、错误可查。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from importlib.util import module_from_spec, spec_from_file_location
from typing import Any, Callable, Dict, List, Optional

from . import protocol
from .cortex import Cortex
from .node import NervousNode
from .engine import CnbConfigError

# ── 常量 ─────────────────────────────────────────────────────────────

TREE_FORMAT = "farstars-cnb-tree/1"
TREE_MODES = ("inproc", "spawn")

_DEFAULT_HOST = protocol.DEFAULT_HOST
_DEFAULT_HEARTBEAT = 5.0

_ALLOWED_TOP_KEYS = {"format", "host", "name", "desc", "levels", "auto"}
_ALLOWED_BLOCK_KEYS = {
    "level", "count", "kind", "node_id", "id_pattern", "port", "ports",
    "base_port", "parent", "engine", "heartbeat", "desc", "args",
}
_ALLOWED_AUTO_KEYS = {"watch", "watch_interval", "reconcile", "reconcile_interval"}

_EXAMPLE = (
    "定义示例：{\"levels\": ["
    "{\"level\": 0, \"count\": 1, \"node_id\": \"cortex\", \"port\": 17800}, "
    "{\"level\": 1, \"count\": 2, \"kind\": \"agent\", \"parent\": 17800, "
    "\"base_port\": 17810}]}"
)


# ── 异常 ─────────────────────────────────────────────────────────────

class TreeDefinitionError(CnbConfigError):
    """神经树定义非法（缺必要参数 / 字段非法 / 引用无法解析）。

    ``problems`` 逐条列出问题（含字段路径与期望），便于一次修全。
    """

    def __init__(self, message: str, problems: Optional[List[str]] = None):
        self.problems = list(problems or [])
        if self.problems and len(self.problems) > 1:
            detail = "\n".join(f"  - {p}" for p in self.problems)
            message = f"{message}（共 {len(self.problems)} 处）\n{detail}"
        elif self.problems:
            message = f"{message}\n  - {self.problems[0]}"
        super().__init__(message)


class TreeBuildError(RuntimeError):
    """树装配/改形的运行期错误（端口占用 / 子进程启动失败 / 注册超时等）。"""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ── 来源加载 ─────────────────────────────────────────────────────────

def _load_py_definition(path: str) -> Dict[str, Any]:
    """从 PY 文件加载树定义（模块级变量或 build 函数；失败信息明确）。"""
    name = "norp_cnb_tree_" + hashlib.sha1(
        os.path.abspath(path).encode("utf-8")).hexdigest()[:10]
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise TreeDefinitionError(f"cannot load PY file: {path}")
    module = module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 — 加载失败如实报错
        raise TreeDefinitionError(
            f"PY file execution failed: {path}: {type(exc).__name__}: {exc}") from exc
    for attr in ("TREE", "SPEC", "tree", "spec"):
        if hasattr(module, attr):
            value = getattr(module, attr)
            if callable(value):
                try:
                    value = value()
                except Exception as exc:  # noqa: BLE001
                    raise TreeDefinitionError(
                        f"PY file {path}: {attr}() execution failed: "
                        f"{type(exc).__name__}: {exc}") from exc
            if isinstance(value, dict):
                return value
            raise TreeDefinitionError(
                f"PY file {path}: {attr} must be a dict (or a callable returning a dict)")
    for attr in ("build_tree", "build"):
        fn = getattr(module, attr, None)
        if callable(fn):
            try:
                value = fn()
            except Exception as exc:  # noqa: BLE001
                raise TreeDefinitionError(
                    f"PY file {path}: {attr}() execution failed: "
                    f"{type(exc).__name__}: {exc}") from exc
            if isinstance(value, dict):
                return value
            raise TreeDefinitionError(
                f"PY file {path}: {attr}() must return a dict")
    raise TreeDefinitionError(
        f"PY file {path} provides no tree definition: expected a module-level TREE / SPEC / tree / spec "
        f"variable, or a build() / build_tree() function")


def _load_spec(spec: Any, base_dir: Optional[str]) -> (Dict[str, Any], str):
    """把三种来源统一读成 dict；返回 (raw, 来源描述)。"""
    if isinstance(spec, dict):
        try:
            return json.loads(json.dumps(spec, ensure_ascii=False)), "dict"
        except Exception as exc:  # noqa: BLE001 — 不可序列化对象如实报错
            raise TreeDefinitionError(
                f"tree definition dict is not serializable (only JSON-compatible data accepted): {exc}") from exc
    if isinstance(spec, os.PathLike):
        spec = os.fspath(spec)
    if not isinstance(spec, str):
        raise TreeDefinitionError(
            f"unrecognized tree definition source type: {type(spec).__name__} (expected dict / "
            f"JSON file path / PY file path / JSON text)")
    text = spec.strip()
    if not text:
        raise TreeDefinitionError("tree definition is empty: nothing to parse")
    path = text
    if base_dir and not os.path.isabs(path):
        candidate = os.path.join(base_dir, path)
        if os.path.exists(candidate):
            path = candidate
    if os.path.isfile(path):
        low = path.lower()
        if low.endswith(".py"):
            return _load_py_definition(path), f"py:{os.path.abspath(path)}"
        if low.endswith(".json"):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception as exc:  # noqa: BLE001
                raise TreeDefinitionError(
                    f"JSON file parse failed: {path}: {type(exc).__name__}: {exc}") \
                    from exc
            return data, f"json:{os.path.abspath(path)}"
        raise TreeDefinitionError(
            f"unsupported definition file suffix: {path} (supported: .json / .py)")
    if text.startswith("{"):
        try:
            return json.loads(text), "json-text"
        except Exception as exc:  # noqa: BLE001
            raise TreeDefinitionError(
                f"JSON text parse failed: {type(exc).__name__}: {exc}") from exc
    raise TreeDefinitionError(
        "unrecognized tree definition source: expected dict / JSON file path / PY file path / "
        "JSON text (starting with {)." + _EXAMPLE)


# ── 校验 ─────────────────────────────────────────────────────────────

def _validate_block(index: int, block: Any, problems: List[str]) -> List[Dict[str, Any]]:
    """校验单个层块，返回其节点（未解析父级的半成品）。"""
    where = f"levels[{index}]"
    if not isinstance(block, dict):
        problems.append(f"{where}: 必须是对象（给出 level / count / 端口 / parent 等必要参数）")
        return []
    unknown = sorted(set(block) - _ALLOWED_BLOCK_KEYS)
    if unknown:
        problems.append(f"{where}: 未知字段 {unknown}（允许：{sorted(_ALLOWED_BLOCK_KEYS)}）")

    level = block.get("level")
    if not _is_int(level):
        problems.append(f"{where}.level: 缺少或非法的层号（必填，0~63 的整数）")
        level = None
    elif not (0 <= level <= 63):
        problems.append(f"{where}.level: 层号越界 {level}（允许 0~63）")
        level = None

    count = block.get("count")
    if not _is_int(count):
        problems.append(f"{where}.count: 缺少或非法的个数（必填，≥1 的整数）")
        count = None
    elif count < 1:
        problems.append(f"{where}.count: 个数必须 ≥1（当前 {count}）")
        count = None

    if level == 0 and count is not None and count != 1:
        problems.append(
            f"{where}.count: level 0 是中枢（树根），count 必须为 1（当前 {count}）")

    kind = block.get("kind")
    if kind is None:
        kind = "cortex" if level == 0 else "node"
    elif not isinstance(kind, str) or not kind.strip():
        problems.append(f"{where}.kind: 必须为非空字符串")
        kind = "cortex" if level == 0 else "node"
    else:
        kind = kind.strip()
        if level == 0 and kind.lower() != "cortex":
            problems.append(
                f"{where}.kind: 根节点（level 0）必须是中枢（kind=cortex），"
                f"当前 {kind!r}")

    heartbeat = block.get("heartbeat")
    if heartbeat is not None and (not _is_number(heartbeat) or heartbeat <= 0):
        problems.append(f"{where}.heartbeat: 必须为正数（秒）")
        heartbeat = None

    desc = block.get("desc")
    if desc is not None and not isinstance(desc, str):
        problems.append(f"{where}.desc: 必须为字符串")
        desc = None

    engine = block.get("engine", False)
    if not isinstance(engine, bool):
        problems.append(f"{where}.engine: 必须为布尔值（true/false）")
        engine = False

    args = block.get("args")
    if args is not None:
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            problems.append(f"{where}.args: 必须为字符串列表（spawn 模式附加参数）")
            args = None

    # 端口：port / ports / base_port 三选一（必要参数，不写死默认）
    port_keys = [k for k in ("port", "ports", "base_port") if k in block]
    ports: List[Optional[int]] = []
    if not port_keys:
        problems.append(
            f"{where}: 缺少端口配置（port / ports / base_port 三选一，"
            f"必须显式配置；R-025：端口不写死）")
    elif len(port_keys) > 1:
        problems.append(
            f"{where}: 端口配置方式只能三选一，当前同时给出 {port_keys}")
    elif count is not None:
        key = port_keys[0]
        raw = block[key]
        if key == "port":
            if count != 1:
                problems.append(f"{where}.port: count>1 时请用 ports / base_port")
            elif not _is_int(raw):
                problems.append(f"{where}.port: 必须为整数端口号")
            else:
                ports = [raw]
        elif key == "ports":
            if not isinstance(raw, list) or len(raw) != count:
                problems.append(
                    f"{where}.ports: 必须为长度等于 count({count}) 的端口列表")
            elif not all(_is_int(p) for p in raw):
                problems.append(f"{where}.ports: 端口必须均为整数")
            else:
                ports = list(raw)
        else:  # base_port
            if not _is_int(raw):
                problems.append(f"{where}.base_port: 必须为整数起始端口号")
            else:
                ports = [raw + k for k in range(count)]
    for k, p in enumerate(ports):
        if p is not None and not (1 <= p <= 65535):
            problems.append(f"{where}: 端口越界 {p}（允许 1~65535）")
    ports = [None if p is None or not (1 <= p <= 65535) else p for p in ports]

    # 节点 id 模板
    pattern = block.get("node_id", block.get("id_pattern"))
    if pattern is not None and (not isinstance(pattern, str) or not pattern.strip()):
        problems.append(f"{where}.node_id: 必须为非空字符串（模板可含 {{i}} 占位符）")
        pattern = None
    if pattern is None and level is not None:
        pattern = "cortex" if level == 0 else f"{kind}-{{i:02d}}"
    ids: List[str] = []
    if pattern is not None and count is not None:
        if count > 1 and "{i" not in pattern:
            problems.append(
                f"{where}.node_id: count>1 时必须包含 {{i}} 占位符（如 "
                f"{kind}-{{i:02d}}）以保证节点 id 唯一")
        else:
            for k in range(count):
                try:
                    ids.append(pattern.format(i=k + 1))
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{where}.node_id: 模板格式化失败: {exc}")
                    ids = []
                    break

    # 父级（低层必要参数）
    raw_parent = block.get("parent")
    if level == 0:
        if raw_parent is not None:
            problems.append(f"{where}.parent: 根节点（level 0）不应有父级")
        raw_parent = None
    else:
        if raw_parent is None:
            problems.append(
                f"{where}: 缺少必要参数 parent（低层必须指定父级：父节点端口号 / "
                f"父节点 id / \"level:N\"）")
        elif not (_is_int(raw_parent) or isinstance(raw_parent, str)):
            problems.append(
                f"{where}.parent: 非法类型（应为端口号整数 / 节点 id 字符串 / "
                f"\"level:N\"）")

    nodes = []
    if level is not None and count is not None:
        for k in range(len(ids)):
            nodes.append({
                "node_id": ids[k],
                "kind": kind,
                "level": level,
                "port": ports[k] if k < len(ports) else None,
                "parent_raw": raw_parent,
                "engine": bool(engine),
                "heartbeat": float(heartbeat) if heartbeat else None,
                "desc": desc or "",
                "args": list(args or []),
                "block_index": index,
            })
    return nodes


def _validate_tree(raw: Any, source: str) -> Dict[str, Any]:
    """校验并规范化树定义；返回树计划（plan）。"""
    if not isinstance(raw, dict):
        raise TreeDefinitionError(
            "tree definition must be an object (dict / JSON object / dict returned by PY)", [f"actual type: {type(raw).__name__}"])
    problems: List[str] = []
    unknown = sorted(set(raw) - _ALLOWED_TOP_KEYS)
    if unknown:
        problems.append(f"顶层未知字段 {unknown}（允许：{sorted(_ALLOWED_TOP_KEYS)}）")
    fmt = raw.get("format", TREE_FORMAT)
    if fmt != TREE_FORMAT:
        problems.append(f"format: 不支持 {fmt!r}（当前仅支持 {TREE_FORMAT!r}）")
    host = raw.get("host", _DEFAULT_HOST)
    if not isinstance(host, str) or not host.strip():
        problems.append("host: 必须为非空字符串（默认 127.0.0.1）")
        host = _DEFAULT_HOST
    name = raw.get("name", "")
    if not isinstance(name, str):
        problems.append("name: 必须为字符串")
        name = ""
    desc = raw.get("desc", "")
    if not isinstance(desc, str):
        problems.append("desc: 必须为字符串")
        desc = ""

    auto_raw = raw.get("auto", {})
    auto = {"watch": False, "watch_interval": 2.0,
            "reconcile": False, "reconcile_interval": 5.0}
    if auto_raw is not None:
        if not isinstance(auto_raw, dict):
            problems.append("auto: 必须为对象（watch / reconcile 等开关）")
        else:
            unknown_auto = sorted(set(auto_raw) - _ALLOWED_AUTO_KEYS)
            if unknown_auto:
                problems.append(
                    f"auto 未知字段 {unknown_auto}（允许：{sorted(_ALLOWED_AUTO_KEYS)}）")
            for k in ("watch", "reconcile"):
                if k in auto_raw:
                    if not isinstance(auto_raw[k], bool):
                        problems.append(f"auto.{k}: 必须为布尔值")
                    else:
                        auto[k] = auto_raw[k]
            for k in ("watch_interval", "reconcile_interval"):
                if k in auto_raw:
                    v = auto_raw[k]
                    if not _is_number(v) or v <= 0:
                        problems.append(f"auto.{k}: 必须为正数（秒）")
                    else:
                        auto[k] = float(v)

    levels = raw.get("levels")
    nodes: List[Dict[str, Any]] = []
    if not isinstance(levels, list) or not levels:
        problems.append(
            "levels: 缺少层级定义（必填的非空列表；每层给出 level / count / "
            "端口，低层给出 parent）")
    else:
        for i, block in enumerate(levels):
            nodes.extend(_validate_block(i, block, problems))

    # 全局检查：层序（父必须更低层）、id/端口唯一、level 0 树根
    if nodes:
        nodes_sorted = sorted(nodes, key=lambda n: n["level"])
        level0 = [n for n in nodes_sorted if n["level"] == 0]
        if not level0:
            problems.append("levels: 缺少 level 0 根节点（中枢，kind=cortex）")
        elif len(level0) > 1:
            problems.append(
                f"levels: level 0 只能有一个树根节点（当前 {len(level0)} 个）")
        seen_ids: Dict[str, int] = {}
        seen_ports: Dict[int, str] = {}
        for n in nodes_sorted:
            nid = n.get("node_id")
            if nid in seen_ids:
                problems.append(f"节点 id 重复：{nid!r}（各层节点 id 必须唯一）")
            seen_ids[nid] = 1
            p = n.get("port")
            if p is None:
                problems.append(f"节点 {nid}: 端口缺失（port / ports / base_port 必须显式配置）")
            elif p in seen_ports:
                problems.append(
                    f"端口重复：{p}（{seen_ports[p]} 与 {nid} 冲突，各节点端口必须唯一）")
            else:
                seen_ports[p] = nid
        by_port = {n["port"]: n for n in nodes_sorted if n.get("port")}
        by_id = {n["node_id"]: n for n in nodes_sorted}
        rr_counter: Dict[int, int] = {}
        for n in nodes_sorted:
            raw_parent = n.pop("parent_raw", None)
            n["parent_id"] = None
            n["parent_port"] = None
            if n["level"] == 0:
                continue
            parent = None
            if _is_int(raw_parent):
                parent = by_port.get(raw_parent)
                if parent is None:
                    problems.append(
                        f"节点 {n['node_id']}.parent: 端口 {raw_parent} 未在定义中"
                        f"找到对应节点（父级也可用节点 id 或 \"level:N\"）")
            elif isinstance(raw_parent, str):
                token = raw_parent.strip()
                if token.startswith("port:") and token[5:].strip().isdigit():
                    token = token[5:].strip()
                if token.isdigit():
                    parent = by_port.get(int(token))
                    if parent is None:
                        problems.append(
                            f"节点 {n['node_id']}.parent: 端口 {token} 未在定义中"
                            f"找到对应节点")
                elif token.startswith("level:"):
                    lv = token[6:].strip()
                    if not lv.isdigit():
                        problems.append(
                            f"节点 {n['node_id']}.parent: \"level:N\" 的 N 必须是整数")
                    else:
                        want = int(lv)
                        pool = [m for m in nodes_sorted if m["level"] == want]
                        if not pool:
                            problems.append(
                                f"节点 {n['node_id']}.parent: 第 {want} 层没有可挂载的节点")
                        elif want >= n["level"]:
                            problems.append(
                                f"节点 {n['node_id']}.parent: 父层（level {want}）"
                                f"必须低于本节点层级（level {n['level']}）")
                        else:
                            k = rr_counter.get(want, 0)
                            parent = pool[k % len(pool)]
                            rr_counter[want] = k + 1
                else:
                    parent = by_id.get(token)
                    if parent is None:
                        problems.append(
                            f"节点 {n['node_id']}.parent: 节点 {token!r} 不存在")
            if parent is not None:
                if parent["level"] >= n["level"]:
                    problems.append(
                        f"节点 {n['node_id']}.parent: 父节点层级（{parent['level']}）"
                        f"必须低于子节点层级（{n['level']}）")
                    parent = None
                else:
                    n["parent_id"] = parent["node_id"]
                    n["parent_port"] = parent["port"]

    if problems:
        raise TreeDefinitionError("neural tree definition validation failed; fix and retry", problems)

    # 排序：先按层（升序），层内保持定义顺序；父级必然位于子级之前。
    ordered = sorted(range(len(nodes)), key=lambda k: (nodes[k]["level"], k))
    plan_nodes = []
    for k in ordered:
        n = nodes[k]
        plan_nodes.append({
            "node_id": n["node_id"],
            "kind": n["kind"],
            "level": n["level"],
            "port": n["port"],
            "parent_id": n["parent_id"],
            "parent_port": n["parent_port"],
            "engine": n["engine"],
            "heartbeat": n["heartbeat"],
            "desc": n["desc"],
            "args": n["args"],
            "block_index": n["block_index"],
        })
    return {
        "format": TREE_FORMAT,
        "name": name,
        "desc": desc,
        "host": host.strip(),
        "source": source,
        "auto": auto,
        "nodes": plan_nodes,
    }


def parse_tree_definition(spec: Any, *, base_dir: Optional[str] = None) -> Dict[str, Any]:
    """解析并校验神经树定义（三种来源统一入口）。

    Args:
        spec: dict / JSON 文件路径 / PY 文件路径 / JSON 文本。
        base_dir: 相对路径的基准目录（缺省为进程当前目录）。

    Returns:
        树计划 dict（format / host / auto / nodes，父级已解析）。

    Raises:
        TreeDefinitionError: 缺必要参数 / 字段非法 / 引用无法解析（逐条列出）。
    """
    raw, source = _load_spec(spec, base_dir)
    plan = _validate_tree(raw, source)
    # 重定基准：相对路径来源的文件监视等场景由调用方处理
    return plan


def plan_table(plan: Dict[str, Any]) -> str:
    """把树计划渲染为可读表格（CLI show / 日志用）。"""
    lines = [
        f"神经树定义：format={plan.get('format')} host={plan.get('host')} "
        f"source={plan.get('source')}",
        f"{'id':<18} {'level':>5} {'kind':<10} {'port':>6} "
        f"{'parent':<18} {'engine':<6}",
        "-" * 72,
    ]
    for n in plan.get("nodes", []):
        parent = n.get("parent_id")
        if parent and n.get("parent_port") and parent != "<port>":
            parent = f"{parent}:{n['parent_port']}"
        lines.append(
            f"{n['node_id']:<18} {n['level']:>5} {n['kind']:<10} "
            f"{n['port']:>6} {str(parent or '-'):<18} "
            f"{str(bool(n.get('engine'))).lower():<6}")
    auto = plan.get("auto") or {}
    lines.append(
        f"auto: watch={auto.get('watch')} "
        f"reconcile={auto.get('reconcile')}")
    lines.append(f"节点数：{len(plan.get('nodes', []))}")
    return "\n".join(lines)


# ── 公共支撑 ─────────────────────────────────────────────────────────

def _file_sig(path: str) -> Optional[str]:
    """文件签名（mtime+size+sha1 前缀）；不存在返回 None。"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    try:
        with open(path, "rb") as fh:
            digest = hashlib.sha1(fh.read()).hexdigest()[:16]
    except OSError:
        digest = "?"
    return f"{int(st.st_mtime * 1000)}:{st.st_size}:{digest}"


def _wait_health(host: str, port: int, timeout: float = 10.0) -> bool:
    """等待节点总线健康端点就绪。"""
    url = f"http://{host}:{port}/cnb/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:  # noqa: S310 loopback
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001 — 启动窗口内重试
            pass
        time.sleep(0.12)
    return False


def _root_node_ids(host: str, port: int, timeout: float = 3.0) -> set:
    """读取根节点拓扑中的节点 id 集合（失败返回空集）。"""
    try:
        from .bus import BusClient

        r = BusClient(timeout=timeout).post_ctrl(
            f"http://{host}:{port}", {"op": "topo"})
        if r.get("ok"):
            return {str(n.get("node_id")) for n in (r.get("nodes") or [])}
    except Exception:  # noqa: BLE001 — 就绪探测尽力而为
        pass
    return set()


def _coerce_plan(value: Any) -> Dict[str, Any]:
    """接受「定义」或「树计划」，统一返回树计划。"""
    if isinstance(value, dict) and "levels" in value:
        return parse_tree_definition(value)
    if isinstance(value, dict) and "nodes" in value:
        return value
    return parse_tree_definition(value)


class _TreeBase:
    """两种装配形态共用骨架：事件、差分改形、监视、收敛、停止。"""

    mode = "?"

    def __init__(self, plan: Dict[str, Any], *, host: Optional[str] = None,
                 on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.plan = plan
        self.host = host or plan.get("host") or _DEFAULT_HOST
        self.on_event = on_event
        self.status = "created"        # created / running / stopped / failed
        self.error: Optional[str] = None
        self._events: deque = deque(maxlen=200)
        self._stop_evt = threading.Event()
        self._lock = threading.RLock()
        self._watcher_thread: Optional[threading.Thread] = None
        self._recon_thread: Optional[threading.Thread] = None
        self._source_path: Optional[str] = None
        self._last_sig: Optional[str] = None

    # -- 事件 --

    def _emit(self, kind: str, message: str, **fields: Any) -> Dict[str, Any]:
        rec = {"ts": time.time(), "kind": kind, "message": message,
               "mode": self.mode, **fields}
        self._events.append(rec)
        cb = self.on_event
        if cb is not None:
            try:
                cb(rec)
            except Exception:  # noqa: BLE001 — 事件回调失败不影响主流程
                pass
        else:
            print(f"[cnb-tree:{self.mode}] {message}")
        return rec

    def events(self, n: int = 50) -> List[Dict[str, Any]]:
        return list(self._events)[-max(1, n):]

    # -- 差分改形（手动） --

    def apply(self, value: Any, *, wait_timeout: float = 10.0) -> Dict[str, Any]:
        """运行中手动改形：差分应用新定义（保留未变节点）。"""
        with self._lock:
            if self.status != "running":
                raise TreeBuildError(
                    f"neural tree is in state {self.status}; cannot reshape (must be mounted first)")
            plan = _coerce_plan(value)
            old_root = self.plan["nodes"][0]
            new_root = plan["nodes"][0]
            if (old_root["node_id"] != new_root["node_id"]
                    or old_root["port"] != new_root["port"]):
                return self._rebuild(plan, wait_timeout=wait_timeout)
            return self._apply_diff(plan, wait_timeout=wait_timeout)

    def _rebuild(self, plan: Dict[str, Any], *, wait_timeout: float) -> Dict[str, Any]:
        self._emit("reshape", "root node changed: rebuilding the whole tree")
        self._stop_all_nodes()
        self.plan = plan
        self._start_all(wait_timeout=wait_timeout)
        return {"rebuilt": True, "added": [n["node_id"] for n in plan["nodes"]],
                "removed": [], "changed": [], "kept": [], "size": len(plan["nodes"])}

    def _apply_diff(self, plan: Dict[str, Any], *, wait_timeout: float) -> Dict[str, Any]:
        old_nodes = {n["node_id"]: n for n in self.plan["nodes"]}
        new_nodes = {n["node_id"]: n for n in plan["nodes"]}
        removed = [nid for nid in old_nodes if nid not in new_nodes]
        added = [nid for nid in new_nodes if nid not in old_nodes]
        changed = []
        kept = []
        for nid in new_nodes:
            if nid not in old_nodes:
                continue
            if self._differs(old_nodes[nid], new_nodes[nid]):
                changed.append(nid)
            else:
                kept.append(nid)
        leaving = sorted(set(removed) | set(changed),
                         key=lambda nid: -old_nodes[nid]["level"])
        for nid in leaving:
            try:
                self._stop_node(nid, old_nodes[nid])
            except Exception as exc:  # noqa: BLE001 — 单节点失败如实报错并续行
                self._emit("error", f"node {nid} stop failed: {exc}")
        entering = [n for n in plan["nodes"]
                    if n["node_id"] in set(added) | set(changed)]
        for node in entering:
            try:
                self._start_node(node, wait_timeout=wait_timeout)
            except Exception as exc:  # noqa: BLE001
                self._emit("error", f"node {node['node_id']} start failed: {exc}")
        for nid in kept:
            try:
                self._live_update(old_nodes[nid], new_nodes[nid])
            except Exception:  # noqa: BLE001 — 活更新尽力而为
                pass
        self.plan = plan
        summary = {"rebuilt": False, "added": sorted(added),
                   "removed": sorted(removed), "changed": sorted(changed),
                   "kept": sorted(kept), "size": len(new_nodes)}
        self._emit(
            "reshape",
            f"reshape complete: +{len(added)} -{len(removed)} changed {len(changed)} "
            f"kept {len(kept)} ({len(new_nodes)} nodes total)")
        if wait_timeout > 0:
            try:
                self.wait_ready(min(wait_timeout, 5.0))
            except Exception:  # noqa: BLE001
                pass
        return summary

    def _differs(self, old: Dict[str, Any], new: Dict[str, Any]) -> bool:
        fields = ["kind", "level", "port", "parent_id", "parent_port",
                  "engine", "args"]
        fields += list(self._extra_diff_fields())
        return any(old.get(f) != new.get(f) for f in fields)

    def _extra_diff_fields(self):
        return ()

    # -- 监视（自动改形） --

    def start_watcher(self, path: str, interval: Optional[float] = None) -> None:
        """监视定义文件；内容变化时自动改形（失败保持现形并显式报错）。"""
        self._source_path = os.path.abspath(path)
        iv = float(interval if interval is not None
                   else (self.plan.get("auto") or {}).get("watch_interval") or 2.0)

        def _loop() -> None:
            self._last_sig = _file_sig(self._source_path)
            while not self._stop_evt.is_set():
                time.sleep(iv)
                sig = _file_sig(self._source_path)
                if not sig or sig == self._last_sig:
                    continue
                self._last_sig = sig
                try:
                    plan = parse_tree_definition(self._source_path)
                    summary = self.apply(plan)
                    self._emit(
                        "watch",
                        f"definition file changed; auto-reshaped: +{summary['added']} "
                        f"-{summary['removed']}")
                except Exception as exc:  # noqa: BLE001 — 保持现形，显式报错
                    self._emit("error",
                               f"definition file change rejected (keeping current shape): {exc}")

        self._watcher_thread = threading.Thread(
            target=_loop, daemon=True, name=f"cnb-tree-watch-{self.mode}")
        self._watcher_thread.start()
        self._emit("info", f"watching definition file: {self._source_path} (interval {iv}s)")

    # -- 收敛（自动恢复） --

    def start_reconciler(self, interval: Optional[float] = None) -> None:
        """自动收敛：按定义恢复掉线/退出的节点（间隔可配）。"""
        iv = float(interval if interval is not None
                   else (self.plan.get("auto") or {}).get("reconcile_interval") or 5.0)

        def _loop() -> None:
            while not self._stop_evt.is_set():
                time.sleep(iv)
                try:
                    self._reconcile_once()
                except Exception as exc:  # noqa: BLE001
                    self._emit("error", f"auto-reconcile error: {exc}")

        self._recon_thread = threading.Thread(
            target=_loop, daemon=True, name=f"cnb-tree-reconcile-{self.mode}")
        self._recon_thread.start()
        self._emit("info", f"auto-reconcile enabled (interval {iv}s)")

    def _reconcile_once(self) -> None:
        for node in list(self.plan["nodes"]):
            nid = node["node_id"]
            try:
                if not self._is_alive(nid):
                    self._emit("warn", f"node {nid} not running; auto-recovering per definition")
                    self._force_stop(nid)
                    self._start_node(node, wait_timeout=10.0)
                else:
                    self._ensure_registered(nid, node)
            except Exception as exc:  # noqa: BLE001 — 恢复失败如实报告
                self._emit("error", f"node {nid} auto-recovery failed: {exc}")

    def _ensure_registered(self, nid: str, node: Dict[str, Any]) -> None:
        """尽力确保节点仍挂在根拓扑里（失败不抛，交由心跳自愈）。"""
        return None

    # -- 等待就绪 --

    def wait_ready(self, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            have = _root_node_ids(self.host, self._root_port(), timeout=2.0)
            if {n["node_id"] for n in self.plan["nodes"]} <= have:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)

    def missing_nodes(self) -> List[str]:
        have = _root_node_ids(self.host, self._root_port(), timeout=2.0)
        return [n["node_id"] for n in self.plan["nodes"]
                if n["node_id"] not in have]

    def _root_port(self) -> int:
        return int(self.plan["nodes"][0]["port"])

    # -- 停止 --

    def stop(self) -> None:
        if self._stop_evt.is_set():
            return
        self._stop_evt.set()
        for t in (self._watcher_thread, self._recon_thread):
            if t is not None and t.is_alive():
                t.join(timeout=2.0)
        self._stop_all_nodes()
        self.status = "stopped"
        self._emit("info", "neural tree stopped")

    # -- 子类接口 --

    def _start_all(self, *, wait_timeout: float) -> None:
        raise NotImplementedError

    def _start_node(self, node: Dict[str, Any], *, wait_timeout: float) -> None:
        raise NotImplementedError

    def _stop_node(self, nid: str, node: Dict[str, Any]) -> None:
        raise NotImplementedError

    def _force_stop(self, nid: str) -> None:
        raise NotImplementedError

    def _is_alive(self, nid: str) -> bool:
        raise NotImplementedError

    def _stop_all_nodes(self) -> None:
        raise NotImplementedError

    def _live_update(self, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        return None

    def describe(self) -> Dict[str, Any]:
        raise NotImplementedError


# ── 进程内装配 ───────────────────────────────────────────────────────

class InProcTree(_TreeBase):
    """同一进程内装配的神经树（中枢 + 各层裸神经节点，各自独立总线端口）。"""

    mode = "inproc"

    def __init__(self, plan: Dict[str, Any], *, host: Optional[str] = None,
                 on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(plan, host=host, on_event=on_event)
        self._nodes: Dict[str, NervousNode] = {}
        self._root: Optional[Cortex] = None

    @property
    def root(self) -> Optional[Cortex]:
        """树根（中枢）对象；供宿主绑定引擎（np(cnb={"tree": ...})）。"""
        return self._root

    def start(self, wait_timeout: float = 10.0) -> "InProcTree":
        for node in self.plan["nodes"]:
            if node["engine"]:
                raise TreeBuildError(
                    "in-process mode does not support engine:true (it assembles raw neural nodes); "
                    "for a full kernel instance use spawn mode, or let the host bind the engine "
                    "to the root node via np(cnb={\"tree\": ...})")
        if self.status == "running":
            return self
        self._start_all(wait_timeout=wait_timeout)
        return self

    def _start_all(self, *, wait_timeout: float) -> None:
        started: List[str] = []
        try:
            for node in self.plan["nodes"]:
                obj = self._create(node)
                obj.start()
                self._nodes[node["node_id"]] = obj
                started.append(node["node_id"])
        except Exception as exc:  # noqa: BLE001 — 装配失败：回滚已启节点
            for nid in reversed(started):
                try:
                    self._nodes.pop(nid).stop()
                except Exception:  # noqa: BLE001
                    pass
            self.status = "failed"
            self.error = f"{type(exc).__name__}: {exc}"
            raise TreeBuildError(
                f"in-process neural tree assembly failed: {type(exc).__name__}: {exc}") from exc
        self._root = self._nodes[self.plan["nodes"][0]["node_id"]]
        self.status = "running"
        ok = self.wait_ready(wait_timeout) if wait_timeout > 0 else True
        if not ok:
            missing = self.missing_nodes()
            self._emit("warn",
                       f"node registration did not fully converge within {wait_timeout}s: {missing}"
                       f" (heartbeat self-healing will keep retrying)")
        self._emit(
            "info",
            f"in-process neural tree mounted: {len(self._nodes)} nodes, "
            f"root node {self.plan['nodes'][0]['node_id']} "
            f"port {self.plan['nodes'][0]['port']}")

    def _create(self, node: Dict[str, Any]) -> NervousNode:
        if node["level"] == 0:
            return Cortex(
                node_id=node["node_id"], host=self.host, port=int(node["port"]),
                meta={"desc": node.get("desc") or "", "tree": self.plan.get("name") or True,
                      "format": self.plan["format"]})
        return NervousNode(
            node_id=node["node_id"], kind=node["kind"], level=node["level"],
            parent_url=f"http://{self.host}:{node['parent_port']}",
            host=self.host, port=int(node["port"]),
            meta={"desc": node.get("desc") or "", "tree": self.plan.get("name") or True},
            heartbeat_interval=float(node.get("heartbeat") or _DEFAULT_HEARTBEAT))

    def _start_node(self, node: Dict[str, Any], *, wait_timeout: float) -> None:
        self._nodes.pop(node["node_id"], None)
        obj = self._create(node)
        obj.start()
        self._nodes[node["node_id"]] = obj

    def _stop_node(self, nid: str, node: Dict[str, Any]) -> None:
        obj = self._nodes.pop(nid, None)
        if obj is not None:
            try:
                obj.stop()
            finally:
                if self._root is not None and nid != self._root.node_id:
                    try:
                        self._root.topology.unregister(nid)
                    except Exception:  # noqa: BLE001
                        pass

    def _force_stop(self, nid: str) -> None:
        self._stop_node(nid, {"node_id": nid})

    def _is_alive(self, nid: str) -> bool:
        obj = self._nodes.get(nid)
        return obj is not None and bool(getattr(obj, "_running", False))

    def _ensure_registered(self, nid: str, node: Dict[str, Any]) -> None:
        if self._root is None or nid == self._root.node_id:
            return
        have = {n.node_id for n in self._root.topology.all()}
        if nid not in have:
            obj = self._nodes.get(nid)
            if obj is not None:
                try:
                    obj.register()
                except Exception:  # noqa: BLE001 — 下轮收敛再试
                    pass

    def _stop_all_nodes(self) -> None:
        for nid in sorted(self._nodes, key=lambda x: -self._nodes[x].level):
            obj = self._nodes.pop(nid, None)
            if obj is None:
                continue
            try:
                obj.stop()
            except Exception:  # noqa: BLE001
                pass
        self._root = None

    def describe(self) -> Dict[str, Any]:
        rows = []
        for n in self.plan["nodes"]:
            obj = self._nodes.get(n["node_id"])
            rows.append({
                "node_id": n["node_id"], "level": n["level"], "kind": n["kind"],
                "port": n["port"], "parent_id": n["parent_id"],
                "engine": n["engine"], "alive": self._is_alive(n["node_id"]),
                "object": obj is not None,
            })
        return {"mode": self.mode, "status": self.status,
                "root": self.plan["nodes"][0]["node_id"],
                "root_port": self._root_port(), "size": len(self._nodes),
                "nodes": rows}


# ── 多进程装配（真进程树） ───────────────────────────────────────────

class SpawnTree(_TreeBase):
    """按定义拉起的多进程神经树（每节点一个 norpagent 子进程）。"""

    mode = "spawn"

    def __init__(self, plan: Dict[str, Any], *, python: Optional[str] = None,
                 on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
                 log_dir: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None):
        super().__init__(plan, host=plan.get("host"), on_event=on_event)
        self.python = python or sys.executable
        self.log_dir = log_dir
        self._procs: Dict[str, subprocess.Popen] = {}
        self._logs: Dict[str, Any] = {}
        self._env = dict(env) if env else self._build_env()

    @staticmethod
    def _build_env() -> Dict[str, str]:
        env = dict(os.environ)
        # PYTHONPATH：逐段去除空白（外壳 set 可能带尾随空格），并保证源码
        # 运行时子进程可找到 norpagent 包（安装环境为无害冗余）。
        parts = [p.strip() for p in
                 (env.get("PYTHONPATH") or "").split(os.pathsep)]
        try:
            import norpagent as _np

            pkg_parent = os.path.dirname(os.path.dirname(
                os.path.abspath(_np.__file__)))
            if pkg_parent and pkg_parent not in parts:
                parts.insert(0, pkg_parent)
        except Exception:  # noqa: BLE001
            pass
        if parts:
            env["PYTHONPATH"] = os.pathsep.join(parts)
        # 规范化编码相关变量：外壳中的异常值（如尾随空格）会让子解释器在
        # 初始化阶段直接失败（Fatal Python error: invalid PYTHONUTF8 ...），
        # 此处强制标准值，保证子进程启动不受宿主外壳环境影响。
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def start(self, wait_timeout: float = 30.0) -> "SpawnTree":
        if self.status == "running":
            return self
        self._start_all(wait_timeout=wait_timeout)
        return self

    def _argv(self, node: Dict[str, Any]) -> List[str]:
        cmd = [self.python, "-u", "-m", "norpagent"]
        if node["level"] == 0:
            cmd += ["cortex", "--id", node["node_id"],
                    "--host", self.host, "--port", str(node["port"])]
        else:
            cmd += ["node", "--id", node["node_id"], "--kind", node["kind"],
                    "--level", str(node["level"]),
                    "--parent", f"http://{self.host}:{node['parent_port']}",
                    "--host", self.host, "--port", str(node["port"])]
        if node.get("desc"):
            cmd += ["--desc", node["desc"]]
        if node["level"] != 0 and node.get("heartbeat"):
            cmd += ["--heartbeat", str(node["heartbeat"])]
        if not node.get("engine"):
            cmd += ["--bare"]
        cmd += list(node.get("args") or [])
        return cmd

    def _spawn(self, node: Dict[str, Any]) -> subprocess.Popen:
        cmd = self._argv(node)
        out: Any = subprocess.DEVNULL
        err: Any = subprocess.DEVNULL
        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)
            fh = open(os.path.join(self.log_dir, f"{node['node_id']}.log"),
                      "ab", buffering=0)
            self._logs[node["node_id"]] = fh
            out = fh
            err = fh
        try:
            proc = subprocess.Popen(  # noqa: S603 — 本机自装配，参数来自已校验定义
                cmd, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                env=self._env, cwd=os.getcwd())
        except Exception as exc:  # noqa: BLE001
            raise TreeBuildError(
                f"node {node['node_id']} subprocess launch failed: "
                f"{type(exc).__name__}: {exc}") from exc
        return proc

    def _start_all(self, *, wait_timeout: float) -> None:
        started: List[str] = []
        try:
            for node in self.plan["nodes"]:
                self._start_node(node, wait_timeout=wait_timeout)
                started.append(node["node_id"])
        except Exception as exc:  # noqa: BLE001 — 装配失败：回滚已启子进程
            for nid in reversed(started):
                try:
                    self._force_stop(nid)
                except Exception:  # noqa: BLE001
                    pass
            self.status = "failed"
            self.error = f"{type(exc).__name__}: {exc}"
            raise TreeBuildError(
                f"multi-process neural tree assembly failed: {type(exc).__name__}: {exc}") from exc
        self.status = "running"
        ok = self.wait_ready(wait_timeout) if wait_timeout > 0 else True
        if not ok:
            missing = self.missing_nodes()
            self._emit("warn",
                       f"node registration did not fully converge within {wait_timeout}s: {missing}"
                       f" (heartbeat self-healing will keep retrying)")
        self._emit(
            "info",
            f"multi-process neural tree mounted: {len(self._procs)} nodes, "
            f"root node {self.plan['nodes'][0]['node_id']} "
            f"port {self.plan['nodes'][0]['port']}")

    def _start_node(self, node: Dict[str, Any], *, wait_timeout: float) -> None:
        self._force_stop(node["node_id"])
        proc = self._spawn(node)
        self._procs[node["node_id"]] = proc
        per_node = min(max(wait_timeout, 5.0), 20.0)
        if not _wait_health(self.host, int(node["port"]), timeout=per_node):
            self._force_stop(node["node_id"])
            raise TreeBuildError(
                f"node {node['node_id']} bus not ready within {per_node}s"
                f" (port {node['port']}; check logs or port usage)")

    def _stop_node(self, nid: str, node: Dict[str, Any]) -> None:
        proc = self._procs.pop(nid, None)
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception:  # noqa: BLE001
                pass
        fh = self._logs.pop(nid, None)
        if fh is not None:
            try:
                fh.close()
            except Exception:  # noqa: BLE001
                pass

    def _force_stop(self, nid: str) -> None:
        self._stop_node(nid, {"node_id": nid})

    def _is_alive(self, nid: str) -> bool:
        proc = self._procs.get(nid)
        return proc is not None and proc.poll() is None

    def _stop_all_nodes(self) -> None:
        order = sorted(self._procs, key=lambda nid: -self._level_of(nid))
        for nid in order:
            try:
                self._force_stop(nid)
            except Exception:  # noqa: BLE001
                pass

    def _level_of(self, nid: str) -> int:
        for n in self.plan["nodes"]:
            if n["node_id"] == nid:
                return int(n["level"])
        return 0

    def _extra_diff_fields(self):
        return ("heartbeat", "desc")

    def describe(self) -> Dict[str, Any]:
        rows = []
        for n in self.plan["nodes"]:
            proc = self._procs.get(n["node_id"])
            rows.append({
                "node_id": n["node_id"], "level": n["level"], "kind": n["kind"],
                "port": n["port"], "parent_id": n["parent_id"],
                "engine": n["engine"],
                "alive": proc is not None and proc.poll() is None,
                "pid": proc.pid if proc is not None else None,
            })
        return {"mode": self.mode, "status": self.status,
                "root": self.plan["nodes"][0]["node_id"],
                "root_port": self._root_port(), "size": len(self._procs),
                "nodes": rows}


# ── 便捷入口 ─────────────────────────────────────────────────────────

def build_in_process(plan: Any, *, host: Optional[str] = None,
                     on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
                     wait_timeout: float = 10.0) -> InProcTree:
    """按树计划（或定义）在进程内装配并启动整棵树。"""
    tree = InProcTree(_coerce_plan(plan), host=host, on_event=on_event)
    tree.start(wait_timeout=wait_timeout)
    return tree


def spawn_tree(plan: Any, *, python: Optional[str] = None,
               on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
               log_dir: Optional[str] = None,
               env: Optional[Dict[str, str]] = None,
               wait_timeout: float = 30.0) -> SpawnTree:
    """按树计划（或定义）拉起多进程真进程树。"""
    tree = SpawnTree(_coerce_plan(plan), python=python, on_event=on_event,
                     log_dir=log_dir, env=env)
    tree.start(wait_timeout=wait_timeout)
    return tree


# ── 宿主引擎挂载（np(cnb={"tree": ...}) / remount 用） ──────────────

class TreeMount:
    """把一棵进程内神经树挂到宿主引擎：宿主引擎绑定为根节点（中枢）的模块。

    与单节点 ``CnbAdapter`` 相同的生命周期语义：
    ``status``：mounting / mounted / failed / stopped；``error`` 记录显式错误；
    ``shutdown()`` 停止整棵树（引擎保持运行）。装配在后台线程完成，
    永不阻塞主线程启动；失败显式报错并降级（宿主照常运行，树不加载）。
    """

    def __init__(self, engine: Any, plan: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None,
                 *, mode: str = "inproc",
                 on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        if mode not in TREE_MODES:
            raise CnbConfigError(
                f"unknown neural tree assembly mode {mode!r} (supported: {list(TREE_MODES)})")
        self.engine = engine
        self.plan = plan
        self.cfg = dict(cfg or {})
        self.mode = mode
        self.on_event = on_event
        self.status = "mounting"
        self.error: Optional[str] = None
        root = plan["nodes"][0]
        self.node_id = root["node_id"]
        self.port = root["port"]
        self._handle: Optional[_TreeBase] = None
        self._root_adapter: Optional[Any] = None
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._events: deque = deque(maxlen=200)
        self._thread: Optional[threading.Thread] = None

    # -- 事件 --

    def _emit(self, rec: Dict[str, Any]) -> None:
        self._events.append(rec)
        if self.on_event is not None:
            try:
                self.on_event(rec)
                return
            except Exception:  # noqa: BLE001
                pass
        print(f"[cnb-tree:{rec.get('mode', self.mode)}] {rec.get('message')}")

    def events(self, n: int = 50) -> List[Dict[str, Any]]:
        return list(self._events)[-max(1, n):]

    # -- 生命周期 --

    def mount(self) -> "TreeMount":
        self._thread = threading.Thread(
            target=self._run, daemon=True,
            name=f"cnb-tree-mount-{self.node_id}")
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            if self.mode == "spawn":
                handle: _TreeBase = spawn_tree(
                    self.plan, on_event=self._emit, wait_timeout=30.0)
            else:
                handle = build_in_process(
                    self.plan, on_event=self._emit, wait_timeout=10.0)
            if self._stopped.is_set():
                handle.stop()
                return
            self._handle = handle
            if self.mode == "inproc":
                # 宿主引擎绑定到根节点（中枢）：内核动作面 + 实例模块挂入
                # 根节点默认槽位（与 unbox 独立中枢同源语义）。
                from .engine import CnbAdapter

                root = getattr(handle, "root", None)
                if root is not None:
                    self._root_adapter = CnbAdapter(self.engine, root, {})
            self.status = "mounted"
            print(f"[cnb] tree mounted ({self.mode}): root={self.node_id} "
                  f"port={self.port} nodes={len(self.plan['nodes'])}")
        except Exception as exc:  # noqa: BLE001 — 装配失败：显式报错并降级
            self.status = "failed"
            self.error = f"{type(exc).__name__}: {exc}"
            print(f"[cnb] tree mount failed; degrading to a plain instance: "
                  f"{self.error}")

    def reshape(self, value: Any) -> Dict[str, Any]:
        """运行中改形（差分应用新定义 / 新计划）。"""
        handle = self._handle
        if handle is None or self.status != "mounted":
            raise TreeBuildError(
                f"neural tree not mounted (status={self.status}); cannot reshape")
        return handle.apply(value)

    def describe(self) -> Dict[str, Any]:
        base = {"mode": self.mode, "status": self.status,
                "root": self.node_id, "root_port": self.port,
                "error": self.error}
        handle = self._handle
        if handle is not None:
            base["tree"] = handle.describe()
        return base

    def shutdown(self, join_timeout: float = 5.0) -> None:
        with self._lock:
            if self._stopped.is_set():
                return
            self._stopped.set()
        handle = self._handle
        if handle is not None:
            try:
                handle.stop()
            except Exception:  # noqa: BLE001 — 停止尽力而为
                pass
        self.status = "stopped"


__all__ = [
    "TREE_FORMAT",
    "TREE_MODES",
    "TreeDefinitionError",
    "TreeBuildError",
    "parse_tree_definition",
    "plan_table",
    "build_in_process",
    "spawn_tree",
    "InProcTree",
    "SpawnTree",
    "TreeMount",
]
