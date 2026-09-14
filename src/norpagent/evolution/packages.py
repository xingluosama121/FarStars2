# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.evolution.packages — 进化包（.fspack）与整合包（.zip）（R-010 / R-012）。

R-010：进化成果以 ``.fspack`` 为后缀；**同时兼容读取 json 和 py 后缀**；
可前端导出、分享、作者署名。
R-012：多个进化包可打为一个整合包（``.zip``）；单整合包最大 **1024 个**
进化包；整批/多包同时导入：任一失败**不阻塞**其余，计入进化包日志，
仅生效导入成功的进化包；导入失败的逻辑**完全不使用**并如实报错、记入日志。

包体为自描述 JSON（sha256 校验）；py 形式为「json 字符串内嵌」的合法
Python 模块（``FSPACK = json.loads(...)``），与 json 形式语义完全一致。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import zipfile
from typing import Any, Callable, Dict, List, Optional, Tuple

from .hotswap import load_module_from_file
from .store import append_log

FSPACK_FORMAT = "fspack/1"
FSPACK_SUFFIXES = (".fspack", ".json", ".py")
BUNDLE_SUFFIX = ".zip"
MAX_BUNDLE_ENTRIES = 1024


class PackageError(RuntimeError):
    """进化包操作错误（格式非法 / 校验失败 / 超容量等）。"""


def _payload_hash(item: Any) -> str:
    data = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def build_fspack(item: Dict[str, Any], author: str = "",
                 meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构建进化包 payload（内存形态）。"""
    if not isinstance(item, dict):
        raise PackageError("fspack item must be a dict (self-describing JSON)")
    return {
        "format": FSPACK_FORMAT,
        "author": str(author or ""),
        "created_at": time.time(),
        "kind": str(item.get("kind") or "evolution"),
        "sha256": _payload_hash(item),
        "meta": dict(meta or {}),
        "item": item,
    }


def write_fspack(payload: Dict[str, Any], path: str) -> str:
    """落盘进化包：按后缀写 .fspack/.json（JSON 文本）或 .py（Python 形式）。"""
    path = str(path)
    suffix = os.path.splitext(path)[1].lower()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if suffix == ".py":
        json_text = json.dumps(payload, ensure_ascii=False, default=str)
        body = (
            "# -*- coding: utf-8 -*-\n"
            "# auto-generated FarStars evolution package (fspack, python form).\n"
            "# The authoritative payload is the embedded JSON; keep it intact.\n"
            "import json as _json\n\n"
            f"FSPACK = _json.loads({json_text!r})\n"
        )
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
    else:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    return path


def export_fspack(item: Dict[str, Any], path: str, author: str = "",
                  meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """导出进化包（R-010：三后缀皆可写；含作者署名元数据）。"""
    payload = build_fspack(item, author=author, meta=meta)
    write_fspack(payload, path)
    append_log({"event": "fspack.export", "path": path, "author": payload["author"],
                "kind": payload["kind"]})
    return payload


def read_fspack(path: str) -> Dict[str, Any]:
    """读取进化包（.fspack / .json / .py 三种后缀；格式与校验如实报错）。"""
    path = str(path)
    suffix = os.path.splitext(path)[1].lower()
    if suffix not in FSPACK_SUFFIXES:
        raise PackageError(
            f"unsupported fspack suffix {suffix!r}; expected one of "
            f"{FSPACK_SUFFIXES}")
    try:
        if suffix == ".py":
            module = load_module_from_file(path)
            payload = getattr(module, "FSPACK", None)
            if not isinstance(payload, dict):
                raise PackageError("python-form fspack has no FSPACK dict")
        else:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
    except PackageError:
        raise
    except Exception as exc:  # noqa: BLE001 — 读取失败如实报错
        raise PackageError(f"cannot read fspack {path}: {exc}") from exc
    return verify_fspack(payload)


def verify_fspack(payload: Any) -> Dict[str, Any]:
    """校验进化包结构 + sha256（防篡改；失败如实报错）。"""
    if not isinstance(payload, dict):
        raise PackageError("fspack payload must be a dict")
    if str(payload.get("format")) != FSPACK_FORMAT:
        raise PackageError(
            f"unsupported fspack format {payload.get('format')!r}; expected "
            f"{FSPACK_FORMAT!r}")
    item = payload.get("item")
    if not isinstance(item, dict):
        raise PackageError("fspack payload.item must be a dict")
    expected = str(payload.get("sha256") or "")
    actual = _payload_hash(item)
    if expected and expected != actual:
        raise PackageError("fspack sha256 mismatch (payload tampered or corrupt)")
    payload["sha256_verified"] = bool(expected)
    return payload


def import_fspack(path: str,
                  apply_fn: Optional[Callable[[Dict[str, Any]], Any]] = None,
                  actor: str = "user") -> Dict[str, Any]:
    """导入单个进化包：校验 → apply_fn（生效）→ 日志；失败不生效、如实报错。"""
    try:
        payload = read_fspack(path)
    except Exception as exc:  # noqa: BLE001 — 失败项如实入日志
        append_log({"event": "fspack.import.failed", "path": str(path),
                    "error": f"{type(exc).__name__}: {exc}"})
        raise
    applied = False
    if apply_fn is not None:
        try:
            apply_fn(payload["item"])
            applied = True
        except Exception as exc:  # noqa: BLE001 — 应用失败 = 不生效
            append_log({"event": "fspack.import.failed", "path": str(path),
                        "error": f"apply: {type(exc).__name__}: {exc}"})
            raise PackageError(f"fspack apply failed (not used): {exc}") from exc
    append_log({"event": "fspack.import", "path": str(path),
                "author": payload.get("author"), "kind": payload.get("kind"),
                "applied": applied, "actor": actor})
    return {"ok": True, "path": str(path), "author": payload.get("author"),
            "kind": payload.get("kind"), "applied": applied}


# ── 整合包（.zip，≤1024 个进化包） ───────────────────────

def export_bundle(entries: List[Tuple[str, str]],
                  zip_path: str) -> Dict[str, Any]:
    """打整合包：entries = [(entry_name, fspack_path), ...]。

    超过 1024 个直接拒绝并提示（R-012）；返回整合包摘要。
    """
    if len(entries) > MAX_BUNDLE_ENTRIES:
        raise PackageError(
            f"bundle exceeds the {MAX_BUNDLE_ENTRIES}-entry limit "
            f"(got {len(entries)}); the bundle was not created")
    zip_path = str(zip_path)
    os.makedirs(os.path.dirname(os.path.abspath(zip_path)), exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, fspack_path in entries:
            safe = str(name).replace("\\", "/").lstrip("/")
            if not safe.lower().endswith(FSPACK_SUFFIXES):
                safe += ".fspack"
            zf.write(fspack_path, arcname=safe)
    append_log({"event": "fspack.bundle.export", "path": zip_path,
                "entries": len(entries)})
    return {"ok": True, "path": zip_path, "entries": len(entries)}


def import_bundle(zip_path: str,
                  apply_fn: Optional[Callable[[Dict[str, Any]], Any]] = None,
                  actor: str = "user") -> Dict[str, Any]:
    """整批导入整合包（R-012）：

    - 超 1024 个条目：整体拒绝并提示（不部分导入）；
    - 任一失败不阻塞其余：逐条校验 + 应用 + 日志；
    - 导入失败的逻辑完全不使用（apply_fn 仅在逐条校验通过后调用一次）。
    返回 {"total","ok","failed","failed_entries","applied"} 全量如实报告。
    """
    zip_path = str(zip_path)
    if not os.path.exists(zip_path):
        raise PackageError(f"bundle not found: {zip_path}")
    report: Dict[str, Any] = {
        "total": 0, "ok": 0, "failed": 0,
        "failed_entries": [], "applied": [],
    }
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) > MAX_BUNDLE_ENTRIES:
            raise PackageError(
                f"bundle exceeds the {MAX_BUNDLE_ENTRIES}-entry limit "
                f"(got {len(names)}); import refused as a whole")
        report["total"] = len(names)
        for name in names:
            try:
                raw = zf.read(name).decode("utf-8")
                payload = verify_fspack(json.loads(raw))
                if apply_fn is not None:
                    apply_fn(payload["item"])
                report["ok"] += 1
                report["applied"].append({
                    "entry": name, "kind": payload.get("kind"),
                    "author": payload.get("author"),
                })
                append_log({"event": "fspack.bundle.import.ok",
                            "bundle": zip_path, "entry": name,
                            "author": payload.get("author"), "actor": actor})
            except Exception as exc:  # noqa: BLE001 — 失败不阻塞其余
                report["failed"] += 1
                entry = {"entry": name, "error": f"{type(exc).__name__}: {exc}"}
                report["failed_entries"].append(entry)
                append_log({"event": "fspack.bundle.import.failed",
                            "bundle": zip_path, **entry})
    append_log({"event": "fspack.bundle.import", "bundle": zip_path,
                "total": report["total"], "ok": report["ok"],
                "failed": report["failed"], "actor": actor})
    return report


__all__ = [
    "FSPACK_FORMAT",
    "FSPACK_SUFFIXES",
    "BUNDLE_SUFFIX",
    "MAX_BUNDLE_ENTRIES",
    "PackageError",
    "build_fspack",
    "write_fspack",
    "export_fspack",
    "read_fspack",
    "verify_fspack",
    "import_fspack",
    "export_bundle",
    "import_bundle",
]
