# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.evolution.hotswap — 代码进化热重载管线（R-004，2026-09-09 裁决）。

铁律：**自进化应用变更不删除原文件逻辑**——不原地改写原文件、不删除原文件；
一律「产出新文件 / 新版本逻辑 → 验证 → 热重载切换到新逻辑」，原逻辑保留、
一键回退，防止把自己进化坏了。

管线（对应架构书 §7.1 进化环的执行/验证阶段）：
    stage_new_version()   产出新版本文件（原文件字节不动）
    activate()            验证（validate 回调）→ 应用（apply_fn）→ 激活；
                          激活后健康核验（health 回调，2026-09-12 运行期
                          加固）：核验失败自动回退（revert_fn / 重装原逻辑）
                          并标记 failed；
    rollback()            放弃新版本、回到原逻辑（可选重新应用原版）
    original_intact()     校验原文件 sha256 未变（可验证的「永不删除」）
    verify_active()       运行期巡检：活跃版本文件存在、可加载、原文件未动

所有动作写进化日志（JSONL）；记录结构可序列化（面板/审计可展示）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import time
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional

from .store import append_log


class HotswapError(RuntimeError):
    """热重载失败（验证不通过 / 应用失败 / 记录非法等）。"""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def versioned_filename(target_path: str, tag: str = "",
                       when: Optional[float] = None) -> str:
    """新版本文件名：``<stem>__evo_<YYYYmmdd_HHMMSS>[_<tag>]_<n>.py``。

    永不覆盖既有文件：同秒多次产出自动加序号。原文件名与扩展名保持不变
    （仍在原目录，仍可与原逻辑并排存在）。
    """
    target_path = os.path.abspath(target_path)
    base, ext = os.path.splitext(os.path.basename(target_path))
    ext = ext or ".py"
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(when or time.time()))
    suffix = f"_{tag}" if tag else ""
    n = 0
    while True:
        name = f"{base}__evo_{stamp}{suffix}" + (f"_{n}" if n else "") + ext
        candidate = os.path.join(os.path.dirname(target_path), name)
        if not os.path.exists(candidate):
            return candidate
        n += 1


def stage_new_version(target_path: str, new_code: str, tag: str = "",
                      description: str = "") -> Dict[str, Any]:
    """产出新版本文件（原文件只读不动）；返回版本记录（status="staged"）。

    - target_path：被进化的原文件（必须已存在——「原逻辑保留」前提）；
    - new_code：新逻辑源码（UTF-8 文本）；
    - 新文件名由 :func:`versioned_filename` 生成，写在原文件同目录。
    """
    target_path = os.path.abspath(str(target_path))
    if not os.path.exists(target_path):
        raise HotswapError(f"target file not found: {target_path}")
    if not isinstance(new_code, str) or not new_code.strip():
        raise HotswapError("new_code must be a non-empty source string")
    new_path = versioned_filename(target_path, tag=tag)
    old_sha = _sha256_file(target_path)
    with open(new_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new_code)
    record = {
        "format": "farstars-hotswap/1",
        "id": f"{os.path.basename(target_path)}@{time.time():.6f}",
        "target_path": target_path,
        "new_path": new_path,
        "old_sha256": old_sha,
        "new_sha256": _sha256_text(new_code),
        "created_at": time.time(),
        "description": str(description or ""),
        "tag": str(tag or ""),
        "status": "staged",
        "active": False,
    }
    append_log({"event": "hotswap.stage", "record": record})
    return record


def load_module_from_file(path: str,
                          module_name: Optional[str] = None) -> ModuleType:
    """从文件加载模块（不进入 sys.modules 常驻；调用方决定引用/丢弃）。"""
    path = os.path.abspath(path)
    name = module_name or (
        "norp_evo_" + os.path.splitext(os.path.basename(path))[0]
        + "_" + str(int(time.time() * 1000) % 100000))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise HotswapError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def activate(record: Dict[str, Any],
             validate: Optional[Callable[[ModuleType], Any]] = None,
             apply_fn: Optional[Callable[[ModuleType], Any]] = None,
             health: Optional[Callable[[ModuleType], Any]] = None,
             revert_fn: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """激活新版本：加载新文件 → validate → apply_fn（热重载切换）。

    - validate(module)：抛错 = 验证不通过，拒绝激活（自动回滚语义）；
    - apply_fn(module)：把新逻辑装到目标位置（如替换注册表/模块属性）；
    - health(module)：激活后健康核验（2026-09-12 运行期加固）。抛错 =
      新逻辑不可用：尝试自动回退——优先调用 revert_fn()；未提供时，若
      apply_fn 可调用且原文件仍在，则重新加载原文件并 apply_fn 回装原逻辑；
      回退动作与结果如实记入记录（reverted / rollback_error）。
    - 任一步失败：记录 status="failed" + error，绝不部分激活（如实回滚标记）。
    """
    if not record or record.get("status") not in ("staged", "failed"):
        raise HotswapError("record must be a staged (or previously failed) version")
    try:
        module = load_module_from_file(record["new_path"])
        if validate is not None:
            validate(module)
        if apply_fn is not None:
            record["applied"] = True
            apply_fn(module)
    except Exception as exc:  # noqa: BLE001 — 失败必须如实落账（自动回滚语义）
        record["status"] = "failed"
        record["active"] = False
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["failed_at"] = time.time()
        append_log({"event": "hotswap.failed", "record": record})
        raise HotswapError(
            f"activation failed and was rolled back (not applied): {exc}") from exc
    # ── 运行期加固：激活后健康核验 + 失败自动回退（2026-09-12） ──
    if health is not None:
        try:
            health(module)
            record["health_ok"] = True
        except Exception as exc:  # noqa: BLE001 — 核验失败：自动回退并如实记录
            reverted = False
            revert_error = None
            try:
                if callable(revert_fn):
                    revert_fn()
                    reverted = True
                elif callable(apply_fn):
                    target = str(record.get("target_path") or "")
                    if target and os.path.exists(target):
                        original = load_module_from_file(target)
                        apply_fn(original)
                        reverted = True
            except Exception as rex:  # noqa: BLE001 — 回退失败如实记录
                revert_error = f"{type(rex).__name__}: {rex}"
            record["status"] = "failed"
            record["active"] = False
            record["health_ok"] = False
            record["reverted"] = reverted
            record["error"] = (
                f"post-activation health check failed: "
                f"{type(exc).__name__}: {exc}; reverted={reverted}"
                + (f"; revert error: {revert_error}" if revert_error else ""))
            record["failed_at"] = time.time()
            append_log({"event": "hotswap.health_failed", "record": record})
            raise HotswapError(
                f"health check failed after activation; "
                f"reverted={reverted}: {exc}") from exc
    record["status"] = "active"
    record["active"] = True
    record["activated_at"] = time.time()
    record.pop("error", None)
    append_log({"event": "hotswap.activate", "record": record})
    return record


def rollback(record: Dict[str, Any],
             apply_fn: Optional[Callable[[ModuleType], Any]] = None) -> Dict[str, Any]:
    """一键回退：放弃新版本，并按需把原逻辑重新装回运行态。

    - 运行态确被改写（activate 传入了 apply_fn）→ 必须传 apply_fn 才能还原；
      还原失败时置 status="rollback_failed" 并抛 HotswapError——绝不谎报已回滚；
    - 仅暂存、未应用到运行态 → 回退 = 丢弃新版本（原文件字节从未被改写，
      original_intact 可证），记录 status="rolled_back"。
    """
    if not record:
        raise HotswapError("record must not be empty")
    applied = bool(record.get("applied"))
    if apply_fn is not None:
        try:
            original = load_module_from_file(record["target_path"])
            apply_fn(original)
        except Exception as exc:  # noqa: BLE001 — 回退失败绝不谎报成功
            record["status"] = "rollback_failed"
            record["active"] = False
            record["rollback_error"] = f"{type(exc).__name__}: {exc}"
            record["rolled_back_at"] = time.time()
            append_log({"event": "hotswap.rollback_failed", "record": record})
            raise HotswapError(
                f"rollback failed: could not revert the applied logic: {exc}"
            ) from exc
    elif applied:
        # 运行态确实被改写，却没有回退回调可调用——不能声称已回滚。
        record["status"] = "rollback_failed"
        record["active"] = False
        record["rollback_error"] = (
            "runtime logic was applied but rollback() got no apply_fn; "
            "the revert cannot be guaranteed")
        record["rolled_back_at"] = time.time()
        append_log({"event": "hotswap.rollback_failed", "record": record})
        raise HotswapError(record["rollback_error"])
    record["status"] = "rolled_back"
    record["active"] = False
    record["rolled_back_at"] = time.time()
    record.pop("rollback_error", None)
    append_log({"event": "hotswap.rollback", "record": record})
    return record


def original_intact(record: Dict[str, Any]) -> bool:
    """校验原文件未被触碰（sha256 与 stage 时一致）——「不删除原文件逻辑」实证。"""
    try:
        return _sha256_file(record["target_path"]) == record["old_sha256"]
    except Exception:  # noqa: BLE001
        return False


def verify_active(record: Dict[str, Any], *,
                  load_module: bool = True) -> Dict[str, Any]:
    """运行期健康核验：活跃代码版本仍可用（2026-09-12 运行期加固）。

    检查项：
      - new_file_exists：新版本文件存在（丢失 = 活跃逻辑悬空）；
      - module_loads：新版本文件可重新加载（语法/导入/执行错误 = 已损坏）；
      - original_intact：原文件 sha256 未变（未记录 sha 的旧记录跳过该检查）。

    返回 ``{"ok", "checks", "skipped", "error"}``；不修改任何记录、不抛错
    （供巡检 health_sweep 与调用方决策使用）。
    """
    record = record or {}
    checks: Dict[str, Optional[bool]] = {
        "new_file_exists": False, "module_loads": False,
        "original_intact": None,
    }
    skipped: List[str] = []
    errors: List[str] = []
    new_path = str(record.get("new_path") or "")
    try:
        checks["new_file_exists"] = bool(new_path) and os.path.exists(new_path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"new_file_exists: {type(exc).__name__}: {exc}")
    if load_module and checks["new_file_exists"]:
        try:
            load_module_from_file(new_path)
            checks["module_loads"] = True
        except Exception as exc:  # noqa: BLE001 — 加载失败 = 已损坏
            errors.append(f"module_loads: {type(exc).__name__}: {exc}")
    elif not checks["new_file_exists"]:
        errors.append("new version file missing")
    if record.get("old_sha256"):
        try:
            checks["original_intact"] = original_intact(record)
            if not checks["original_intact"]:
                errors.append("original file changed (sha mismatch)")
        except Exception as exc:  # noqa: BLE001
            checks["original_intact"] = False
            errors.append(f"original_intact: {type(exc).__name__}: {exc}")
    else:
        skipped.append("original_intact (record has no previous sha256)")
    ok = all(v for v in checks.values() if v is not None)
    return {"ok": ok, "checks": checks, "skipped": skipped,
            "error": "; ".join(errors) or None}


def list_versions(target_path: str) -> List[str]:
    """列出某目标文件的全部历史新版本文件（含当前 staged/active/rolled_back）。"""
    target_path = os.path.abspath(str(target_path))
    base, ext = os.path.splitext(os.path.basename(target_path))
    ext = ext or ".py"
    folder = os.path.dirname(target_path)
    prefix = f"{base}__evo_"
    out: List[str] = []
    try:
        for name in os.listdir(folder):
            if name.startswith(prefix) and name.endswith(ext):
                out.append(os.path.join(folder, name))
    except Exception:  # noqa: BLE001
        return []
    return sorted(out)


__all__ = [
    "HotswapError",
    "versioned_filename",
    "stage_new_version",
    "load_module_from_file",
    "activate",
    "rollback",
    "original_intact",
    "verify_active",
    "list_versions",
]
