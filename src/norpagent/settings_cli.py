# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.settings_cli — `norpagent settings` 命令行（设置事实源三通道之一）。

架构书 §6.3「三通道同源」：本 CLI 与 Web 面板 / REST API 读写同一设置事实源
（settings store），复用同一套 schema 校验与分层继承语义。桥接键
（``config_key``）的写入同时合并进运行态配置文件（下一次启动生效；运行中的
应用经面板 / API 即时生效）。

用法::

    norpagent settings list [--category C] [--view user|frame|meta] [--explicit]
    norpagent settings get KEY
    norpagent settings set KEY VALUE [--scope global|profile|session|temp]
                                   [--string] [--no-apply]
    norpagent settings reset KEY [--scope ...]
    norpagent settings export [PATH]
    norpagent settings import PATH
    norpagent settings audit [N]
    norpagent settings schema [--category C]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional


def _store():
    from norpagent.settings import ensure_schema

    return ensure_schema()


def _emit(obj: Any) -> None:
    text = obj if isinstance(obj, str) else json.dumps(
        obj, ensure_ascii=False, indent=2, default=str)
    try:
        print(text)
    except UnicodeEncodeError:  # 极端控制台编码兜底：降级为可打印形式
        print(text.encode("utf-8", errors="replace").decode("ascii", "replace"))


def _apply_to_config_file(key: str) -> Optional[Dict[str, Any]]:
    """把桥接键的解析值合并进运行态配置文件（非密键；失败不阻塞并如实报告）。"""
    from norpagent.settings import config_patch_for_key

    patch = config_patch_for_key(key)
    if not patch:
        return None
    try:
        from norpagent.builtin.ui.web import DEFAULT_CONFIG

        allowed = set(DEFAULT_CONFIG) | {"_initialized"}
    except Exception:  # noqa: BLE001 — web 模块不可用时不做过滤
        allowed = None
    env = os.environ.get("NORPAGENT_WEBUI_CONFIG")
    path = env or os.path.join(os.path.expanduser("~"), ".norpagent",
                               "webui_config.json")
    data: Dict[str, Any] = {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
    except Exception:  # noqa: BLE001 — 坏文件：重建（不阻塞写入）
        data = {}
    for k, v in patch.items():
        if allowed is None or k in allowed:
            data[k] = v
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return {"config_file": path, "patch": patch}
    except Exception as exc:  # noqa: BLE001 — 写失败如实报告
        return {"config_file": path, "patch": patch, "error": str(exc)}


def _parse_value(key: str, raw: str, force_string: bool) -> Any:
    from norpagent.settings import schema_item

    item = schema_item(key) or {}
    if force_string or item.get("type") in ("text", "textarea", "password",
                                            "path"):
        return raw
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001 — 非 JSON 输入按字符串处理
        return raw


def _validate_value(key: str, value: Any) -> Optional[str]:
    """schema 校验（枚举 / 数值范围 / 布尔）；返回错误信息（None = 通过）。"""
    from norpagent.settings import schema_item

    item = schema_item(key)
    if item is None:
        return f"unknown setting key: {key!r} (see `norpagent settings schema`)"
    t = item.get("type")
    if t == "switch" and not isinstance(value, bool):
        return f"{key} expects a bool (true/false)"
    if t in ("number",) and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return f"{key} expects a number"
    if t == "enum":
        options = item.get("options") or []
        if options and value not in options:
            return f"{key} must be one of {options} (got {value!r})"
    if t == "number":
        lo, hi = item.get("minimum"), item.get("maximum")
        if isinstance(value, (int, float)):
            if lo is not None and value < lo:
                return f"{key} below minimum {lo} (got {value})"
            if hi is not None and value > hi:
                return f"{key} above maximum {hi} (got {value})"
    return None


# ── 子命令实现 ───────────────────────────────────────────

def _cmd_list(args: argparse.Namespace) -> int:
    from norpagent.settings import schema_view

    store = _store()
    rows = schema_view(store)
    out = []
    for row in rows:
        if args.category and row.get("category") != args.category:
            continue
        if args.view and args.view not in (row.get("views") or []):
            continue
        resolved = store.resolve(row["key"])
        if args.explicit and not resolved.get("explicit"):
            continue
        out.append({
            "key": row["key"],
            "value": resolved.get("value"),
            "source": resolved.get("source"),
            "category": row.get("category"),
            "title": row.get("title"),
        })
    for o in out:
        try:
            val = json.dumps(o["value"], ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            val = str(o["value"])
        if len(val) > 120:
            val = val[:117] + "..."
        print(f"{o['key']} = {val}  [{o['source']}] ({o['category']}) {o['title']}")
    print(f"# {len(out)} setting(s)")
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    store = _store()
    resolved = store.resolve(args.key)
    from norpagent.settings import schema_item

    item = schema_item(args.key)
    resolved["schema"] = item
    resolved["titles"] = store_scope_titles()
    _emit(resolved)
    return 0


def store_scope_titles() -> Dict[str, str]:
    from norpagent.evolution.store import SCOPE_TITLES

    return dict(SCOPE_TITLES)


def _cmd_set(args: argparse.Namespace) -> int:
    store = _store()
    value = _parse_value(args.key, args.value, args.force_string)
    err = _validate_value(args.key, value)
    if err:
        print(f"[settings][error] {err}", file=sys.stderr)
        return 2
    scope = (args.scope or "global").strip().lower()
    if scope == "global":
        store.set(args.key, value, actor=args.actor or "user",
                  reason="settings CLI")
    else:
        store.set_scoped(args.key, value, scope, actor=args.actor or "user",
                         reason="settings CLI")
    result: Dict[str, Any] = {
        "key": args.key, "value": value, "scope": scope,
        "resolved": store.resolve(args.key),
    }
    if not args.no_apply and scope == "global":
        applied = _apply_to_config_file(args.key)
        if applied:
            result["config_apply"] = applied
    _emit(result)
    return 0


def _cmd_reset(args: argparse.Namespace) -> int:
    store = _store()
    scope = (args.scope or "global").strip().lower()
    ok = store.delete(args.key, scope=scope, actor=args.actor or "user",
                      reason="settings CLI reset")
    result: Dict[str, Any] = {"key": args.key, "scope": scope, "deleted": ok,
                              "resolved": store.resolve(args.key)}
    if not args.no_apply and scope == "global":
        applied = _apply_to_config_file(args.key)
        if applied:
            result["config_apply"] = applied
    _emit(result)
    return 0 if ok else 1


def _cmd_export(args: argparse.Namespace) -> int:
    store = _store()
    snap = store.export_json(args.path or None)
    if args.path:
        print(f"# exported to {args.path}")
    else:
        _emit(snap)
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    store = _store()
    try:
        n = store.import_json(args.path, actor=args.actor or "user",
                              reason="settings CLI import")
    except Exception as exc:  # noqa: BLE001
        print(f"[settings][error] import failed: {exc}", file=sys.stderr)
        return 1
    print(f"# imported {n} value(s) from {args.path}")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    store = _store()
    _emit(store.audit_tail(args.n))
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    from norpagent.settings import schema_view

    store = _store()
    for row in schema_view(store):
        if args.category and row.get("category") != args.category:
            continue
        print(f"{row['key']}  ({row.get('category')})  {row.get('title')}"
              + (f"  -> config:{row['config_key']}" if row.get("config_key") else ""))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="norpagent settings",
        description="settings store CLI (same source and validation as the web panel / REST API)",
    )
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="list settings entries and resolved values")
    p.add_argument("--category", default=None)
    p.add_argument("--view", default=None, choices=["user", "frame", "meta"])
    p.add_argument("--explicit", action="store_true", help="list only explicitly written entries")
    p.set_defaults(fn=_cmd_list)

    p = sub.add_parser("get", help="show one setting's resolution details (tri-state + scopes)")
    p.add_argument("key")
    p.set_defaults(fn=_cmd_get)

    p = sub.add_parser("set", help="write a setting value (with schema validation and bridge apply)")
    p.add_argument("key")
    p.add_argument("value")
    p.add_argument("--scope", default="global",
                   choices=["global", "profile", "session", "temp"])
    p.add_argument("--string", dest="force_string", action="store_true",
                   help="treat the value as a plain string (no JSON parsing)")
    p.add_argument("--no-apply", action="store_true",
                   help="do not merge into the runtime config file")
    p.add_argument("--actor", default=None)
    p.set_defaults(fn=_cmd_set)

    p = sub.add_parser("reset", help="delete the explicit value (restore inherited / default)")
    p.add_argument("key")
    p.add_argument("--scope", default="global",
                   choices=["global", "profile", "session", "temp"])
    p.add_argument("--no-apply", action="store_true")
    p.add_argument("--actor", default=None)
    p.set_defaults(fn=_cmd_reset)

    p = sub.add_parser("export", help="export the settings store JSON (omit PATH to print to stdout)")
    p.add_argument("path", nargs="?", default=None)
    p.set_defaults(fn=_cmd_export)

    p = sub.add_parser("import", help="import a settings store JSON")
    p.add_argument("path")
    p.add_argument("--actor", default=None)
    p.set_defaults(fn=_cmd_import)

    p = sub.add_parser("audit", help="show the audit tail (who changed what, when)")
    p.add_argument("n", nargs="?", type=int, default=20)
    p.set_defaults(fn=_cmd_audit)

    p = sub.add_parser("schema", help="list settings entries in the registry")
    p.add_argument("--category", default=None)
    p.set_defaults(fn=_cmd_schema)

    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        return 1
    return int(args.fn(args))


__all__ = ["main"]
