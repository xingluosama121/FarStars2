# -*- coding: utf-8 -*-
"""
norpagent.cnb.topology — 神经树拓扑（树状拓扑链）

维护 CNB 树状拓扑：

- 每个节点有且仅有一个父节点；根节点（大脑皮层，level 0）无父。
- 节点注册时声明 parent_id，总线做无环校验（父链不得回到自身）。
- 等级约束：子节点 level 必须大于父节点 level（数字越大等级越低）。
- 提供祖先/后代判定：下行指令只允许「祖先 -> 后代」；上行上报只允许
  「后代 -> 祖先」。
"""

import threading
import time
from typing import Dict, List, Optional

from .protocol import LEVEL_CORTEX, LEVEL_MAX


class NodeInfo:
    """拓扑中的一个节点。"""

    def __init__(self, node_id: str, level: int, kind: str = "node",
                 parent_id: Optional[str] = None, meta: Optional[Dict] = None):
        self.node_id = node_id
        self.level = int(level)
        self.kind = kind
        self.parent_id = parent_id          # None 表示根（大脑皮层）
        self.meta = dict(meta or {})        # 附加信息（host、port、描述等）
        self.registered_at = time.time()
        self.last_seen = time.time()        # 最近心跳时间
        self.alive = True
        self.children: List[str] = []       # 直接子节点 id 列表

    def touch(self):
        self.last_seen = time.time()
        self.alive = True

    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id,
            "level": self.level,
            "kind": self.kind,
            "parent_id": self.parent_id,
            "meta": self.meta,
            "registered_at": self.registered_at,
            "last_seen": self.last_seen,
            "alive": self.alive,
            "children": list(self.children),
        }


class Topology:
    """树状拓扑链管理器（线程安全）。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._nodes: Dict[str, NodeInfo] = {}

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------

    def get(self, node_id: str) -> Optional[NodeInfo]:
        with self._lock:
            return self._nodes.get(node_id)

    def all(self) -> List[NodeInfo]:
        with self._lock:
            return list(self._nodes.values())

    def root(self) -> Optional[NodeInfo]:
        """返回根节点（大脑皮层，parent_id 为 None 且 level 最低）。"""
        with self._lock:
            candidates = [n for n in self._nodes.values() if n.parent_id is None]
            if not candidates:
                return None
            return min(candidates, key=lambda n: n.level)

    def size(self) -> int:
        with self._lock:
            return len(self._nodes)

    # ------------------------------------------------------------------
    # 注册 / 注销
    # ------------------------------------------------------------------

    def register(self, node_id: str, level: int, kind: str = "node",
                 parent_id: Optional[str] = None,
                 meta: Optional[Dict] = None) -> NodeInfo:
        """注册节点（或更新已有节点信息）。执行无环与等级校验。

        Raises:
            ValueError: 校验失败（环 / 等级非法 / 父节点不存在）
        """
        level = int(level)
        if level < LEVEL_CORTEX or level > LEVEL_MAX:
            raise ValueError(f"非法等级 {level}，允许范围 {LEVEL_CORTEX}~{LEVEL_MAX}")

        with self._lock:
            # 父节点必须存在于本地拓扑（直接注册时父即本节点；转发注册时
            # via 链上的父必须已注册）。父缺失说明视图过期或注册次序异常，
            # 显式拒绝而不是等到维护 children 时 KeyError。
            if parent_id is not None and parent_id != node_id \
                    and parent_id not in self._nodes:
                raise ValueError(
                    f"父节点不存在于本地拓扑：{parent_id}（视图过期或注册次序异常）")
            # 环检测：沿 parent 链向上，不得出现 node_id 自身。
            # 父链上某节点不在本地拓扑中 => 位于本地视图之外（祖先方向），
            # 视为链的合法终点（本地拓扑是子树视图，祖先天然不在其中）。
            cur = parent_id
            guard = 0
            while cur is not None:
                if cur == node_id:
                    raise ValueError(f"拓扑环拒绝：{node_id} 的父链出现自身")
                parent = self._nodes.get(cur)
                if parent is None:
                    break  # 本地视图之外的祖先，合法终点
                if parent.level >= level:
                    raise ValueError(
                        f"等级约束拒绝：子节点 {node_id}(level {level}) 的等级必须"
                        f"大于父节点 {cur}(level {parent.level})")
                cur = parent.parent_id
                guard += 1
                if guard > LEVEL_MAX + 1:
                    raise ValueError("拓扑链过长，疑似环")

            node = self._nodes.get(node_id)
            if node is None:
                node = NodeInfo(node_id, level, kind, parent_id, meta)
                self._nodes[node_id] = node
            else:
                # 防改写：已注册节点的等级 / 类型 / 父节点一律不允许变更
                # （低等级不允许改写高等级；树状拓扑链一经建立保持稳定）
                if level != node.level:
                    raise ValueError(
                        f"等级篡改拒绝：{node_id} 已注册为 level {node.level}，"
                        f"不允许改为 {level}")
                if kind and kind != node.kind:
                    raise ValueError(
                        f"类型篡改拒绝：{node_id} 已注册为 kind {node.kind}，"
                        f"不允许改为 {kind}")
                if parent_id != node.parent_id:
                    raise ValueError(
                        f"父节点篡改拒绝：{node_id} 的父节点是 {node.parent_id}，"
                        f"不允许改为 {parent_id}")
                node.meta.update(meta or {})
                node.touch()

            # 维护父节点的 children 列表
            if parent_id is not None:
                parent = self._nodes[parent_id]
                if node_id not in parent.children:
                    parent.children.append(node_id)

            return node

    def unregister(self, node_id: str):
        """注销节点（级联注销其全部后代，保证树结构完整）。"""
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return
            # 先收集全部后代（DFS）
            doomed = []
            stack = [node_id]
            while stack:
                cur = stack.pop()
                doomed.append(cur)
                cur_node = self._nodes.get(cur)
                if cur_node:
                    stack.extend(cur_node.children)
            # 从父节点 children 中摘除
            if node.parent_id:
                parent = self._nodes.get(node.parent_id)
                if parent and node_id in parent.children:
                    parent.children.remove(node_id)
            for did in doomed:
                self._nodes.pop(did, None)

    # ------------------------------------------------------------------
    # 祖先 / 后代判定（核心安全判定）
    # ------------------------------------------------------------------

    def is_ancestor(self, ancestor_id: str, node_id: str) -> bool:
        """ancestor_id 是否为 node_id 的祖先（沿 node_id 的父链可达）。"""
        if ancestor_id == node_id:
            return False  # 自身不算祖先（同级不可互控）
        with self._lock:
            cur = self._nodes.get(node_id)
            guard = 0
            while cur is not None and cur.parent_id is not None:
                if cur.parent_id == ancestor_id:
                    return True
                cur = self._nodes.get(cur.parent_id)
                guard += 1
                if guard > LEVEL_MAX + 1:
                    return False
            return False

    def is_descendant(self, descendant_id: str, node_id: str) -> bool:
        """descendant_id 是否为 node_id 的后代。"""
        return self.is_ancestor(node_id, descendant_id)

    def ancestor_chain(self, node_id: str) -> List[str]:
        """返回 node_id 的祖先链（从父节点到根，含父不含自身）。"""
        chain = []
        with self._lock:
            cur = self._nodes.get(node_id)
            guard = 0
            while cur is not None and cur.parent_id is not None:
                chain.append(cur.parent_id)
                cur = self._nodes.get(cur.parent_id)
                guard += 1
                if guard > LEVEL_MAX + 1:
                    break
        return chain

    def subtree(self, node_id: str) -> List[str]:
        """返回 node_id 及其全部后代 id 列表（DFS，含自身）。"""
        with self._lock:
            result = []
            stack = [node_id]
            while stack:
                cur = stack.pop()
                result.append(cur)
                cur_node = self._nodes.get(cur)
                if cur_node:
                    stack.extend(cur_node.children)
            return result

    # ------------------------------------------------------------------
    # 拓扑视图
    # ------------------------------------------------------------------

    def render_tree(self) -> List[Dict]:
        """输出整棵树的可读视图（用于皮层控制台 / CLI）。"""
        with self._lock:
            view = []
            for node in self._nodes.values():
                view.append(node.to_dict())
            return view

    def render_ascii(self) -> str:
        """以缩进树的形式渲染拓扑（调试/控制台展示）。"""
        with self._lock:
            roots = [n for n in self._nodes.values() if n.parent_id is None]
            roots.sort(key=lambda n: n.level)
            lines = []
            drawn = set()

            def walk(node: NodeInfo, depth: int):
                prefix = "  " * depth
                lines.append(
                    f"{prefix}[{node.level}] {node.node_id} ({node.kind})"
                    f" {'alive' if node.alive else 'DEAD'}")
                drawn.add(node.node_id)
                for cid in node.children:
                    child = self._nodes.get(cid)
                    if child:
                        walk(child, depth + 1)

            for r in roots:
                walk(r, 0)
            # 孤儿节点（父节点不在本地视图，如本节点自身挂在外层祖先下）
            for node in self._nodes.values():
                if node.node_id not in drawn:
                    lines.append(
                        f"  (orphan, parent={node.parent_id}) [{node.level}] "
                        f"{node.node_id} ({node.kind})")
                    drawn.add(node.node_id)
                    for cid in node.children:
                        child = self._nodes.get(cid)
                        if child:
                            walk(child, 2)
            return "\n".join(lines) if lines else "(empty topology)"

    def heartbeat(self, node_id: str) -> bool:
        """节点心跳：更新 last_seen / alive。返回节点是否存在。"""
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            node.touch()
            return True

    def set_parent(self, node_id: str, parent_id: Optional[str]) -> bool:
        """更新节点的父指针（双向维护 children 列表）。

        用于：
          - 节点收到父节点注册确认（cmd.hello / cmd.reroot）后，把本地拓扑
            中自己的 parent_id 从占位值更新为真实父节点 id；
          - 救树（rescue）：节点下线/失联时，把其直接子改挂到本节点下。
        调用方必须已通过祖先校验 / 处于受控的拓扑管理路径。

        注意：旧父的 children 列表必须同步摘除，否则旧父注销（级联 DFS）
        会把已改挂的子节点一并误删。
        """
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            if parent_id is not None and parent_id == node_id:
                return False  # 不能做自己的父
            old_parent_id = node.parent_id
            node.parent_id = parent_id
            # 从旧父 children 摘除（若旧父在本地视图中）
            if old_parent_id is not None and old_parent_id != parent_id:
                old = self._nodes.get(old_parent_id)
                if old is not None and node_id in old.children:
                    old.children.remove(node_id)
            # 挂到新父 children（若新父在本地视图中）
            if parent_id is not None:
                parent = self._nodes.get(parent_id)
                if parent is not None and node_id not in parent.children:
                    parent.children.append(node_id)
            return True

    def mark_dead(self, node_id: str):
        with self._lock:
            node = self._nodes.get(node_id)
            if node:
                node.alive = False

    def sweep_dead(self, timeout: float = 30.0) -> List[str]:
        """清扫超时未心跳的节点（标记 dead，不注销，供皮层处置）。"""
        now = time.time()
        dead = []
        with self._lock:
            for node in self._nodes.values():
                if node.alive and now - node.last_seen > timeout:
                    node.alive = False
                    dead.append(node.node_id)
        return dead
