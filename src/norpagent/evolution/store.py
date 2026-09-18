# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.evolution.store — settings store（设置事实源）+ 进化日志底座。

SQLite 存储（审计友好）+ JSON 导出/导入。
本模块是远星「全内核唯一设置读入口」的第一块落地：

- ``SettingsStore``：schema 注册（可进化 / 锁定标记是 schema 一等字段）+
  值读写 + 审计环 + JSON 导出/导入；
- 分层继承（2026-09-12，§5.3）：全局 > 档案（成品/预设）> 会话/任务 > 临时
  四层作用域（``set_scoped`` / ``resolve`` / ``layers``）——「不填 = 用上级」，
  每项设置三态（默认值 / 继承值含来源 / 显式值含时间与行为者）可查；
- 进化器写锁定项 = 内核拒绝 + 审计告警（ / 架构书 §7.6：「可进化标记」
  与「锁定标记」为 schema 一等字段）；
- ``append_log`` / ``read_log``：进化包与热重载共享的 JSONL 进化日志
  （导入失败的逻辑完全不使用并如实记入日志）。

零第三方依赖（标准库 sqlite3 / json）。路径可用环境变量覆盖（测试隔离）：
    NORPAGENT_SETTINGS_DB   设置库路径（默认 ~/.norpagent/settings.db）
    NORPAGENT_EVOLUTION_LOG 进化日志路径（默认 ~/.norpagent/evolution_log.jsonl）
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

DEFAULT_CATEGORY = "general"

# ── 分层继承（架构书 §5.3，2026-09-12） ────────────────────
# 层级：全局 > 档案（成品/预设）> 会话/任务 > 临时（slot_overrides/API 单次覆盖）；
# 「不填 = 用上级」：解析时从最具体的层级向上回退，命中的层即来源；
# 每项设置三态：默认值 / 继承值(含来源) / 显式值(含时间与行为者)。
SCOPE_TEMP = "temp"
SCOPE_SESSION = "session"
SCOPE_PROFILE = "profile"
SCOPE_GLOBAL = "global"
# 优先级（高 → 低）：更具体的层覆盖更上层的层
SCOPE_PRIORITY = (SCOPE_TEMP, SCOPE_SESSION, SCOPE_PROFILE, SCOPE_GLOBAL)
SCOPE_TITLES = {
    SCOPE_GLOBAL: "Global",
    SCOPE_PROFILE: "Profile (product/preset)",
    SCOPE_SESSION: "Session/Task",
    SCOPE_TEMP: "Temp (single override)",
}


class SettingsLockedError(RuntimeError):
    """进化器试图写入锁定项 / 非可进化项（内核拒绝 + 审计告警）。"""


class SettingsError(RuntimeError):
    """设置事实源操作错误。"""


def _default_home() -> str:
    override = (os.environ.get("NORPAGENT_UNBOX_HOME") or "").strip()
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".norpagent")


def default_db_path() -> str:
    override = (os.environ.get("NORPAGENT_SETTINGS_DB") or "").strip()
    if override:
        return override
    return os.path.join(_default_home(), "settings.db")


def evolution_log_path() -> str:
    override = (os.environ.get("NORPAGENT_EVOLUTION_LOG") or "").strip()
    if override:
        return override
    return os.path.join(_default_home(), "evolution_log.jsonl")


def append_log(entry: Dict[str, Any]) -> None:
    """追加一条进化日志（JSONL；失败不抛错——日志尽力而为，如实但不阻塞）。"""
    try:
        path = evolution_log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rec = {"ts": time.time(), **entry}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 — 日志写失败不影响进化动作本身
        pass


def read_log(limit: int = 100) -> List[Dict[str, Any]]:
    """读取进化日志尾部（最近 limit 条；无日志返回空列表）。"""
    path = evolution_log_path()
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001 — 单行损坏跳过
                    continue
    except Exception:  # noqa: BLE001
        return []
    return rows[-limit:]


class SettingsStore:
    """设置事实源：SQLite 键值 + schema + 审计环 + JSON 导入导出。

    - ``register_schema(specs)``：注册设置项（key/title/category/evolvable/
      locked/default/description）；schema 是「可进化 / 锁定」的唯一权威；
    - ``get/set/set_many``：读写；进化器（actor 以 "evolution" 开头）写
      锁定项或非可进化项 => :class:`SettingsLockedError`（拒绝 + 审计）；
    - ``export_json / import_json``：整库快照（含 schema 与审计尾部）；
    - ``audit_tail``：审计查询（谁在何时改了什么）。
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or default_db_path()
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    # ── 建库 ─────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    updated_by TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS schema (
                    key TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'general',
                    evolvable INTEGER NOT NULL DEFAULT 0,
                    locked INTEGER NOT NULL DEFAULT 0,
                    default_json TEXT,
                    description TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    action TEXT NOT NULL,
                    key TEXT NOT NULL DEFAULT '',
                    old_json TEXT,
                    new_json TEXT,
                    actor TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS kv_layers (
                    key TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    updated_by TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (key, scope)
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    point TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    # ── schema ───────────────────────────────────────────

    def register_schema(self, specs: List[Dict[str, Any]]) -> int:
        """注册设置项 schema（幂等：重复注册更新元数据不覆盖现值）。"""
        n = 0
        with self._lock:
            cur = self._conn.cursor()
            for spec in specs:
                key = str(spec.get("key") or "").strip()
                if not key:
                    continue
                cur.execute(
                    """
                    INSERT INTO schema(key, title, category, evolvable, locked,
                                       default_json, description)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(key) DO UPDATE SET
                        title=excluded.title,
                        category=excluded.category,
                        evolvable=excluded.evolvable,
                        locked=excluded.locked,
                        default_json=excluded.default_json,
                        description=excluded.description
                    """,
                    (
                        key,
                        str(spec.get("title") or key),
                        str(spec.get("category") or DEFAULT_CATEGORY),
                        1 if spec.get("evolvable") else 0,
                        1 if spec.get("locked") else 0,
                        json.dumps(spec.get("default"), ensure_ascii=False)
                        if "default" in spec else None,
                        str(spec.get("description") or ""),
                    ),
                )
                n += 1
            self._conn.commit()
        return n

    def schema(self, key: Optional[str] = None) -> Any:
        with self._lock:
            cur = self._conn.cursor()
            if key is not None:
                row = cur.execute("SELECT * FROM schema WHERE key=?",
                                  (key,)).fetchone()
                return dict(row) if row else None
            rows = cur.execute("SELECT * FROM schema ORDER BY key").fetchall()
            return [dict(r) for r in rows]

    def prune_schema(self, keep: Any = None,
                     keep_prefixes: Any = None) -> int:
        """删除 schema 中不再登记的键（保留 ``keep`` 集合与 ``keep_prefixes`` 前缀）。

        用于清单删项后的陈旧行清理：``register_schema`` 只做 upsert，不会移除
        已删除的键；不清理会让面板继续显示已废弃的设置项。
        """
        keep_set = {str(k) for k in (keep or ())}
        prefixes = tuple(str(p) for p in (keep_prefixes or ()))
        removed = 0
        with self._lock:
            cur = self._conn.cursor()
            rows = cur.execute("SELECT key FROM schema").fetchall()
            for r in rows:
                k = str(r["key"])
                if k in keep_set:
                    continue
                if prefixes and k.startswith(prefixes):
                    continue
                cur.execute("DELETE FROM schema WHERE key=?", (k,))
                removed += 1
            if removed:
                self._conn.commit()
        return removed

    # ── 读写 ─────────────────────────────────────────────

    @staticmethod
    def _is_evolution_actor(actor: str) -> bool:
        return str(actor or "").strip().lower().startswith("evolution")

    def _guard_evolution_write(self, key: str, actor: str) -> None:
        spec = self.schema(key)
        if spec is None:
            return
        locked = bool(spec.get("locked"))
        evolvable = bool(spec.get("evolvable"))
        if locked:
            self._audit("evolution.write.rejected", key, None, None, actor,
                        "locked item: any evolution write is refused")
            raise SettingsLockedError(
                f"setting {key!r} is LOCKED: evolution writers are refused "
                f"(kernel refuses + audit warning)")
        if not evolvable:
            self._audit("evolution.write.rejected", key, None, None, actor,
                        "not marked evolvable")
            raise SettingsLockedError(
                f"setting {key!r} is not marked evolvable: evolution writers "
                f"are refused")

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key=?",
                                     (key,)).fetchone()
            if row is not None:
                return json.loads(row["value"])
            spec = self.schema(key)
            if spec and spec.get("default_json") is not None:
                return json.loads(spec["default_json"])
            return default

    def get_raw(self, key: str, default: Any = None) -> Any:
        """只读显式写入的 kv 值（不回落到 schema 默认）。

        用于「显式覆盖 vs 默认值」需要区分的场景（如勾选制的恢复默认语义）。
        """
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key=?",
                                     (key,)).fetchone()
            if row is None:
                return default
            try:
                return json.loads(row["value"])
            except Exception:  # noqa: BLE001
                return row["value"]

    def set(self, key: str, value: Any, actor: str = "user",
            reason: str = "") -> Any:
        """写入设置值（含审计）；进化器写锁定/非可进化项被拒绝。"""
        key = str(key or "").strip()
        if not key:
            raise SettingsError("setting key must be a non-empty string")
        if self._is_evolution_actor(actor):
            self._guard_evolution_write(key, actor)
        old = None
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key=?",
                                     (key,)).fetchone()
            if row is not None:
                try:
                    old = json.loads(row["value"])
                except Exception:  # noqa: BLE001
                    old = row["value"]
            self._conn.execute(
                """
                INSERT INTO kv(key, value, updated_at, updated_by)
                VALUES(?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at,
                    updated_by=excluded.updated_by
                """,
                (key, json.dumps(value, ensure_ascii=False), time.time(),
                 str(actor or "")),
            )
            self._audit("set", key, old, value, actor, reason)
            self._conn.commit()
        return value

    def set_many(self, patch: Dict[str, Any], actor: str = "user",
                 reason: str = "") -> int:
        n = 0
        for key, value in (patch or {}).items():
            self.set(key, value, actor=actor, reason=reason)
            n += 1
        return n

    def delete(self, key: str, scope: str = SCOPE_GLOBAL,
               actor: str = "user", reason: str = "") -> bool:
        """删除设置值（恢复上级继承 / schema 默认；删除亦入审计）。

        scope="global"（默认）删除全局层值（兼容既有语义）；其余层级删除对应
        分层值（恢复「用上级」语义）。
        """
        key = str(key or "").strip()
        scope = str(scope or SCOPE_GLOBAL).strip().lower() or SCOPE_GLOBAL
        if scope != SCOPE_GLOBAL:
            return self.delete_scoped(key, scope, actor=actor, reason=reason)
        old = None
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key=?",
                                     (key,)).fetchone()
            if row is None:
                return False
            try:
                old = json.loads(row["value"])
            except Exception:  # noqa: BLE001
                old = row["value"]
            self._conn.execute("DELETE FROM kv WHERE key=?", (key,))
            self._audit("delete", key, old, None, actor, reason)
            self._conn.commit()
        return True

    # ── 分层继承（§5.3：全局 > 档案 > 会话/任务 > 临时） ──────

    def set_scoped(self, key: str, value: Any, scope: str,
                   actor: str = "user", reason: str = "") -> Any:
        """写入某一分层的显式值（profile / session / temp；global 用 set()）。

        进化器写锁定/非可进化项同样被拒绝（守卫与全局层一致）；入审计。
        """
        key = str(key or "").strip()
        scope = str(scope or "").strip().lower()
        if not key:
            raise SettingsError("setting key must be a non-empty string")
        if scope not in (SCOPE_PROFILE, SCOPE_SESSION, SCOPE_TEMP):
            raise SettingsError(
                f"invalid scope {scope!r}: use {SCOPE_PROFILE!r} / "
                f"{SCOPE_SESSION!r} / {SCOPE_TEMP!r} (global layer uses set())")
        if self._is_evolution_actor(actor):
            self._guard_evolution_write(key, actor)
        old = None
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM kv_layers WHERE key=? AND scope=?",
                (key, scope)).fetchone()
            if row is not None:
                try:
                    old = json.loads(row["value"])
                except Exception:  # noqa: BLE001
                    old = row["value"]
            self._conn.execute(
                """
                INSERT INTO kv_layers(key, scope, value, updated_at, updated_by)
                VALUES(?,?,?,?,?)
                ON CONFLICT(key, scope) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at,
                    updated_by=excluded.updated_by
                """,
                (key, scope, json.dumps(value, ensure_ascii=False), time.time(),
                 str(actor or "")),
            )
            self._audit(f"set:{scope}", key, old, value, actor, reason)
            self._conn.commit()
        return value

    def get_scoped(self, key: str, scope: str, default: Any = None) -> Any:
        """读取某一分层的显式值（无 = default；不回落到其他层与 schema 默认）。"""
        key = str(key or "").strip()
        scope = str(scope or "").strip().lower()
        with self._lock:
            if scope == SCOPE_GLOBAL:
                row = self._conn.execute("SELECT value FROM kv WHERE key=?",
                                         (key,)).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT value FROM kv_layers WHERE key=? AND scope=?",
                    (key, scope)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except Exception:  # noqa: BLE001
            return row["value"]

    def delete_scoped(self, key: str, scope: str,
                      actor: str = "user", reason: str = "") -> bool:
        """删除某一分层的显式值（恢复「用上级」语义；删除亦入审计）。"""
        key = str(key or "").strip()
        scope = str(scope or "").strip().lower()
        if scope == SCOPE_GLOBAL:
            return self.delete(key, actor=actor, reason=reason)
        if scope not in (SCOPE_PROFILE, SCOPE_SESSION, SCOPE_TEMP):
            raise SettingsError(f"invalid scope {scope!r}")
        old = None
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM kv_layers WHERE key=? AND scope=?",
                (key, scope)).fetchone()
            if row is None:
                return False
            try:
                old = json.loads(row["value"])
            except Exception:  # noqa: BLE001
                old = row["value"]
            self._conn.execute(
                "DELETE FROM kv_layers WHERE key=? AND scope=?", (key, scope))
            self._audit(f"delete:{scope}", key, old, None, actor, reason)
            self._conn.commit()
        return True

    def layers(self, key: str) -> Dict[str, Any]:
        """某一设置项的逐层显式值（仅含被显式写入的层）。"""
        key = str(key or "").strip()
        out: Dict[str, Any] = {}
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key=?",
                                     (key,)).fetchone()
            if row is not None:
                try:
                    out[SCOPE_GLOBAL] = json.loads(row["value"])
                except Exception:  # noqa: BLE001
                    out[SCOPE_GLOBAL] = row["value"]
            rows = self._conn.execute(
                "SELECT scope, value FROM kv_layers WHERE key=?",
                (key,)).fetchall()
        for r in rows:
            try:
                out[str(r["scope"])] = json.loads(r["value"])
            except Exception:  # noqa: BLE001
                out[str(r["scope"])] = r["value"]
        return out

    def resolve(self, key: str, default: Any = None) -> Dict[str, Any]:
        """解析设置项的有效值（§5.3 继承语义）。

        回退顺序：临时 > 会话/任务 > 档案 > 全局 > schema 默认。
        返回三态视图：default（默认值）/ 各层显式值 / value+source（继承值含来源）。
        """
        key = str(key or "").strip()
        spec = self.schema(key) or {}
        schema_default = None
        if spec.get("default_json") is not None:
            try:
                schema_default = json.loads(spec["default_json"])
            except Exception:  # noqa: BLE001
                schema_default = spec["default_json"]
        by_layer = self.layers(key)
        for scope in SCOPE_PRIORITY:
            if scope in by_layer:
                return {
                    "key": key, "value": by_layer[scope], "source": scope,
                    "explicit": True, "default": schema_default,
                    "by_layer": by_layer,
                }
        if schema_default is not None:
            return {"key": key, "value": schema_default, "source": "default",
                    "explicit": False, "default": schema_default,
                    "by_layer": by_layer}
        return {"key": key, "value": default, "source": "none",
                "explicit": False, "default": None, "by_layer": by_layer}

    def all_resolved(self) -> Dict[str, Dict[str, Any]]:
        """全部已注册设置项的解析视图（面板数据源：值 + 来源 + 三态）。"""
        return {spec["key"]: self.resolve(spec["key"]) for spec in self.schema()}

    # ── 进化提案（§7.1 进化环：提案 / 裁决 / 执行 / 验证 / 固化） ──

    def proposal_add(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """写入 / 覆盖一条进化提案记录（幂等 upsert）。"""
        rec = dict(record or {})
        pid = str(rec.get("id") or "").strip()
        if not pid:
            raise SettingsError("proposal record needs an id")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO proposals(id, ts, point, kind, status, record_json)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    ts=excluded.ts,
                    point=excluded.point,
                    kind=excluded.kind,
                    status=excluded.status,
                    record_json=excluded.record_json
                """,
                (pid, float(rec.get("created_at") or time.time()),
                 str(rec.get("point") or ""), str(rec.get("kind") or ""),
                 str(rec.get("status") or ""),
                 json.dumps(rec, ensure_ascii=False, default=str)),
            )
            self._conn.commit()
        return rec

    def proposal_update(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """更新一条提案记录（不存在时等价新增）。"""
        return self.proposal_add(record)

    def proposal_get(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT record_json FROM proposals WHERE id=?",
                (str(proposal_id),)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["record_json"])
        except Exception:  # noqa: BLE001
            return None

    def proposal_list(self, status: Optional[str] = None,
                      limit: int = 100) -> List[Dict[str, Any]]:
        """提案列表（按时间倒序；可按状态过滤）。"""
        sql = "SELECT record_json FROM proposals"
        args: List[Any] = []
        if status:
            sql += " WHERE status=?"
            args.append(str(status))
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(max(1, int(limit)))
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                out.append(json.loads(r["record_json"]))
            except Exception:  # noqa: BLE001 — 坏行跳过
                continue
        return out

    def all(self, include_schema_defaults: bool = False) -> Dict[str, Any]:
        """全部设置值（含 schema 默认值填充，便于面板完整呈现）。"""
        out: Dict[str, Any] = {}
        if include_schema_defaults:
            for spec in self.schema():
                if spec.get("default_json") is not None:
                    out[spec["key"]] = json.loads(spec["default_json"])
        with self._lock:
            for row in self._conn.execute("SELECT key, value FROM kv"):
                try:
                    out[row["key"]] = json.loads(row["value"])
                except Exception:  # noqa: BLE001
                    out[row["key"]] = row["value"]
        return out

    # ── 审计 ─────────────────────────────────────────────

    def _audit(self, action: str, key: str, old: Any, new: Any, actor: str,
               reason: str = "") -> None:
        self._conn.execute(
            "INSERT INTO audit(ts, action, key, old_json, new_json, actor, reason)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                time.time(), action, key,
                json.dumps(old, ensure_ascii=False) if old is not None else None,
                json.dumps(new, ensure_ascii=False) if new is not None else None,
                str(actor or ""), str(reason or ""),
            ),
        )
        self._conn.commit()

    def audit_tail(self, n: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (int(n),)
            ).fetchall()
        return [dict(r) for r in rows]

    def record_event(self, action: str, key: str = "", old: Any = None,
                     new: Any = None, actor: str = "system",
                     reason: str = "") -> None:
        """通用审计记录：非设置变更类事件也进同一审计环（尽力而为，绝不抛出）。

        用于前端渲染降级 / CDN 回退等「需要留痕但不改设置」的场景，
        与设置写入共用 :meth:`audit_tail` 查询面。
        """
        try:
            with self._lock:
                self._audit(str(action or "event"), str(key or ""),
                            old, new, actor, reason)
        except Exception:  # noqa: BLE001 — 审计尽力而为，不影响调用方
            pass

    # ── JSON 导出 / 导入 ─────────────────────────────────

    def export_json(self, path: Optional[str] = None) -> Dict[str, Any]:
        """整库快照（schema + values + 审计尾部）；给定 path 时落盘。"""
        snap = {
            "format": "farstars-settings/1",
            "exported_at": time.time(),
            "schema": self.schema(),
            "values": self.all(include_schema_defaults=True),
            "audit_tail": self.audit_tail(200),
        }
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(snap, fh, ensure_ascii=False, indent=2)
        return snap

    def import_json(self, data: Any, actor: str = "user",
                    reason: str = "settings import") -> int:
        """导入快照（接受 dict / JSON 文本 / 文件路径）；返回导入条数。"""
        if isinstance(data, str):
            if os.path.exists(data):
                with open(data, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                data = json.loads(data)
        if not isinstance(data, dict):
            raise SettingsError("settings import payload must be a dict")
        schema_specs = data.get("schema") or []
        if schema_specs:
            self.register_schema(schema_specs)
        values = data.get("values") or {}
        if not isinstance(values, dict):
            raise SettingsError("settings import 'values' must be a dict")
        n = 0
        for key, value in values.items():
            self.set(key, value, actor=actor, reason=reason)
            n += 1
        return n

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass


# ── 单例（进程级） ───────────────────────────────────────

_store: Optional[SettingsStore] = None
_store_lock = threading.Lock()


def get_store(path: Optional[str] = None) -> SettingsStore:
    """进程级设置事实源单例（首次调用时建库）。"""
    global _store
    with _store_lock:
        if _store is None or path is not None:
            _store = SettingsStore(path)
        return _store


def set_store_path(path: str) -> SettingsStore:
    """切换设置库路径（测试隔离 / 多档案场景）。"""
    return get_store(path)


__all__ = [
    "SettingsStore",
    "SettingsError",
    "SettingsLockedError",
    "get_store",
    "set_store_path",
    "default_db_path",
    "evolution_log_path",
    "append_log",
    "read_log",
    # 分层继承（§5.3）
    "SCOPE_GLOBAL",
    "SCOPE_PROFILE",
    "SCOPE_SESSION",
    "SCOPE_TEMP",
    "SCOPE_PRIORITY",
    "SCOPE_TITLES",
]
