# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Plugin source security audit: AST static analysis (zero third-party dependencies).

Migrated from the existing application's plugin_system.security; features kept
consistent:

- dangerous calls / dangerous imports / reflection-bypass detection (getattr,
  __getattribute__, __dict__ subscripts, introspection-dict indirect access);
- three severity levels: critical (reject) / warning (notice) / info;
- three audit levels: off / warn / block;
- permission declaration validation: manifest.permissions covers the dangerous
  categories found by the audit.

This module is a purely functional auditor: it only detects and decides; it never
loads any code. Import restrictions live in norpagent.plugins.loader (enabled on
demand during the load flow).
"""

from __future__ import annotations

import ast
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

# ── severity / issues ────────────────────────────────────


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SecurityIssue:
    """One audit finding."""

    __slots__ = ("severity", "line", "code", "message", "category")

    def __init__(self, severity: Severity, line: int, code: str,
                 message: str, category: str):
        self.severity = severity
        self.line = line
        self.code = code
        self.message = message
        self.category = category

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "line": self.line,
            "code": self.code,
            "message": self.message,
            "category": self.category,
        }


# ── dangerous pattern registry (consistent with the existing application) ──

# (module, attr) -> (severity, category, message)
DANGEROUS_CALLS: Dict[Tuple[str, ...], Tuple[Severity, str, str]] = {
    # process / shell execution (CRITICAL)
    ("os", "system"): (Severity.CRITICAL, "shell_exec", "os.system() executes arbitrary shell commands"),
    ("os", "popen"): (Severity.CRITICAL, "shell_exec", "os.popen() launches arbitrary processes"),
    ("subprocess", "call"): (Severity.CRITICAL, "shell_exec", "subprocess.call() launches arbitrary processes"),
    ("subprocess", "run"): (Severity.CRITICAL, "shell_exec", "subprocess.run() launches arbitrary processes"),
    ("subprocess", "Popen"): (Severity.CRITICAL, "shell_exec", "subprocess.Popen() launches arbitrary processes"),
    ("subprocess", "check_output"): (Severity.CRITICAL, "shell_exec", "subprocess.check_output() executes commands"),
    ("subprocess", "check_call"): (Severity.CRITICAL, "shell_exec", "subprocess.check_call() executes commands"),
    ("subprocess", "getoutput"): (Severity.CRITICAL, "shell_exec", "subprocess.getoutput() executes commands"),
    ("subprocess", "getstatusoutput"): (Severity.CRITICAL, "shell_exec", "subprocess.getstatusoutput() executes commands"),
    # code execution (CRITICAL)
    ("eval",): (Severity.CRITICAL, "code_exec", "eval() executes arbitrary Python expressions"),
    ("exec",): (Severity.CRITICAL, "code_exec", "exec() executes arbitrary Python code"),
    ("compile",): (Severity.CRITICAL, "code_exec", "compile() with exec mode can execute code"),
    ("__import__",): (Severity.CRITICAL, "import_bypass", "__import__() bypasses import restrictions"),
    ("importlib", "import_module"): (Severity.CRITICAL, "import_bypass", "importlib.import_module() bypasses restrictions"),
    # native code (CRITICAL)
    ("ctypes",): (Severity.CRITICAL, "native_exec", "ctypes can load arbitrary DLLs / native code"),
    ("cffi",): (Severity.CRITICAL, "native_exec", "cffi can load arbitrary native code"),
    ("os", "_exit"): (Severity.CRITICAL, "process_terminate", "os._exit() force-kills the whole process"),
    ("os", "kill"): (Severity.CRITICAL, "process_terminate", "os.kill() can terminate other processes"),
    # file deletion / permission changes (WARNING)
    ("os", "remove"): (Severity.WARNING, "file_delete", "os.remove() deletes files"),
    ("os", "unlink"): (Severity.WARNING, "file_delete", "os.unlink() deletes files"),
    ("shutil", "rmtree"): (Severity.WARNING, "file_delete", "shutil.rmtree() recursively deletes directories"),
    ("shutil", "move"): (Severity.WARNING, "file_move", "shutil.move() moves/renames files"),
    ("os", "rmdir"): (Severity.WARNING, "file_delete", "os.rmdir() deletes directories"),
    ("os", "chmod"): (Severity.WARNING, "file_permission", "os.chmod() changes file permissions"),
    ("os", "chown"): (Severity.WARNING, "file_permission", "os.chown() changes file ownership"),
    # network (WARNING)
    ("socket",): (Severity.WARNING, "network", "socket provides raw TCP/UDP network access"),
    ("http",): (Severity.WARNING, "network", "the http module provides HTTP client/server"),
    ("urllib",): (Severity.WARNING, "network", "urllib makes HTTP requests"),
    ("requests",): (Severity.WARNING, "network", "the requests library makes HTTP requests"),
    ("ftplib",): (Severity.WARNING, "network", "ftplib establishes FTP connections"),
    ("smtplib",): (Severity.WARNING, "network", "smtplib sends email"),
    ("poplib",): (Severity.WARNING, "network", "poplib receives email"),
    ("telnetlib",): (Severity.WARNING, "network", "telnetlib establishes Telnet connections"),
    # deserialization (WARNING)
    ("pickle",): (Severity.WARNING, "deserialization", "pickle deserialization can execute arbitrary code"),
    ("marshal",): (Severity.WARNING, "deserialization", "marshal.loads() can execute code"),
    ("yaml", "unsafe_load"): (Severity.WARNING, "deserialization", "yaml.unsafe_load() can instantiate arbitrary objects"),
    # system manipulation (WARNING)
    ("sys", "modules"): (Severity.WARNING, "sys_manipulation", "modifying sys.modules affects other plugins"),
    ("sys", "setprofile"): (Severity.WARNING, "sys_manipulation", "sys.setprofile() intercepts every function call"),
    ("sys", "settrace"): (Severity.WARNING, "sys_manipulation", "sys.settrace() intercepts all execution"),
    ("builtins",): (Severity.WARNING, "builtin_override", "modifying builtins affects the whole process"),
    ("sys", "exit"): (Severity.WARNING, "sys_manipulation", "sys.exit() terminates the whole process"),
}

DANGEROUS_IMPORTS: Dict[str, Tuple[Severity, str, str]] = {
    "subprocess": (Severity.CRITICAL, "dangerous_import", "subprocess launches arbitrary commands"),
    "ctypes": (Severity.CRITICAL, "dangerous_import", "ctypes loads arbitrary native code"),
    "cffi": (Severity.CRITICAL, "dangerous_import", "cffi loads arbitrary native code"),
    "socket": (Severity.WARNING, "dangerous_import", "socket provides raw network access"),
    "pickle": (Severity.WARNING, "dangerous_import", "pickle deserialization executes code"),
    "marshal": (Severity.WARNING, "dangerous_import", "marshal deserializes untrusted data"),
    "telnetlib": (Severity.WARNING, "dangerous_import", "telnetlib raw TCP connections"),
    "ftplib": (Severity.WARNING, "dangerous_import", "ftplib FTP connections"),
    "smtplib": (Severity.WARNING, "dangerous_import", "smtplib sends email"),
}

# dangerous function names (for dynamic-call bypass detection, consistent with the existing application's DANGEROUS_FUNC_NAMES)
DANGEROUS_FUNC_NAMES: Set[str] = {
    "system", "popen", "run", "Popen", "call", "check_output", "check_call",
    "getoutput", "getstatusoutput",
    "eval", "exec", "compile", "execfile",
    "__import__", "import_module",
    "remove", "unlink", "rmtree", "rmdir",
    "chmod", "chown",
    "kill", "terminate", "_exit", "exit",
    "setprofile", "settrace",
    "loads", "unsafe_load", "load",
    "ShellExecute", "ShellExecuteW", "ShellExecuteA",
    "WriteProcessMemory", "VirtualAllocEx", "CreateRemoteThread",
}

# dangerous modules that may be reached through indirect access
_SUSPICIOUS_BASES = ("os", "subprocess", "builtins", "sys", "ctypes", "cffi", "shutil", "importlib")


# ── auditor ───────────────────────────────────────────────


class SourceAuditor:
    """AST source auditor (purely functional, thread-safe, no global state)."""

    def __init__(self, audit_level: str = "warn") -> None:
        """audit_level: off / warn / block (invalid values fall back to warn)."""
        self.audit_level = audit_level if audit_level in ("off", "warn", "block") else "warn"

    # ── entry ────────────────────────────────────────────

    def audit_file(self, file_path: str,
                   audit_level: Optional[str] = None) -> Tuple[List[SecurityIssue], bool]:
        """Read and audit a source file.

        Returns (issue list, allowed or not). Allowed is False if and only if the
        level is block and critical issues exist.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                source = fh.read()
        except OSError as exc:
            return [SecurityIssue(
                Severity.CRITICAL, 0, "",
                f"cannot read source file: {exc}", "io_error",
            )], False
        return self.audit_source(source, audit_level=audit_level)

    def audit_source(self, source: str,
                     audit_level: Optional[str] = None) -> Tuple[List[SecurityIssue], bool]:
        """Parse the source and walk the AST to detect dangerous patterns."""
        issues: List[SecurityIssue] = []
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            issues.append(SecurityIssue(
                Severity.CRITICAL, getattr(exc, "lineno", 0) or 0, "",
                f"syntax error: {exc.msg}", "syntax_error",
            ))
            return issues, False
        self._walk(tree, issues)
        level = audit_level if audit_level is not None else self.audit_level
        if level == "off":
            return issues, True
        if level == "block" and any(i.severity == Severity.CRITICAL for i in issues):
            return issues, False
        return issues, True

    def check_permissions(self, manifest: Dict[str, Any],
                          issues: List[SecurityIssue]) -> bool:
        """Validate whether manifest.permissions covers the dangerous categories found by the audit.

        Permission values: process / network / file_write / file_read.
        """
        declared = set(manifest.get("permissions", []) or [])
        if not isinstance(declared, set):
            declared = {str(p) for p in declared}
        required: Set[str] = set()
        for issue in issues:
            cat = issue.category
            if cat in ("shell_exec", "code_exec", "native_exec", "process_terminate"):
                required.add("process")
            elif cat == "network":
                required.add("network")
            elif cat in ("file_delete", "file_move"):
                required.add("file_write")
            elif cat == "dangerous_import":
                if "subprocess" in issue.code:
                    required.add("process")
                elif "socket" in issue.code:
                    required.add("network")
        missing = required - declared
        if missing:
            issues.append(SecurityIssue(
                Severity.CRITICAL, 0, "",
                f"missing permission declarations: {', '.join(sorted(missing))}"
                " (manifest.json → permissions)",
                "missing_permissions",
            ))
            return False
        return True

    # ── AST walk ─────────────────────────────────────────

    def _walk(self, tree: ast.AST, issues: List[SecurityIssue]) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_import(alias.name, node.lineno, issues)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    full = f"{mod}.{alias.name}" if mod else alias.name
                    if mod:
                        self._check_import(mod, node.lineno, issues)
                    self._match_dangerous_call(full, node.lineno, issues)
            elif isinstance(node, ast.Call):
                self._check_call(node, issues)
                self._check_dynamic_call(node, issues)
            elif isinstance(node, ast.Attribute):
                self._check_attribute(node, issues)
            elif isinstance(node, ast.Subscript):
                self._check_dynamic_subscript(node, issues)

    def _check_import(self, name: str, lineno: int, issues: List[SecurityIssue]) -> None:
        if name in DANGEROUS_IMPORTS:
            sev, cat, msg = DANGEROUS_IMPORTS[name]
            issues.append(SecurityIssue(sev, lineno, f"import {name}", msg, cat))
            return
        for mod, (sev, cat, msg) in DANGEROUS_IMPORTS.items():
            if name == mod or name.startswith(mod + "."):
                issues.append(SecurityIssue(sev, lineno, f"import {name}", msg, cat))
                return

    def _check_call(self, node: ast.Call, issues: List[SecurityIssue]) -> None:
        name = _resolve_call_name(node.func)
        if name:
            self._match_dangerous_call(name, node.lineno, issues)

    def _match_dangerous_call(self, full_name: str, lineno: int,
                              issues: List[SecurityIssue]) -> None:
        parts = full_name.rsplit(".", 1)
        for pattern, (sev, cat, msg) in DANGEROUS_CALLS.items():
            if len(pattern) == 1:
                if parts[-1] == pattern[0]:
                    issues.append(SecurityIssue(sev, lineno, full_name, msg, cat))
                    return
            elif len(pattern) == 2:
                mod_part, func_part = pattern
                if len(parts) == 2 and parts[0].endswith(mod_part) and parts[1] == func_part:
                    issues.append(SecurityIssue(sev, lineno, full_name, msg, cat))
                    return

    def _check_attribute(self, node: ast.Attribute, issues: List[SecurityIssue]) -> None:
        name = _resolve_attr_name(node)
        if not name:
            return
        for pattern, (sev, cat, msg) in DANGEROUS_CALLS.items():
            if len(pattern) == 2 and name == f"{pattern[0]}.{pattern[1]}":
                if cat in ("sys_manipulation", "process_terminate"):
                    issues.append(SecurityIssue(
                        sev, node.lineno, name,
                        f"accessing {name} is potentially dangerous", cat,
                    ))

    def _check_dynamic_call(self, node: ast.Call, issues: List[SecurityIssue]) -> None:
        """Detect getattr / __getattribute__ dynamic-call bypasses."""
        func = node.func
        callee: Optional[str] = None
        args = list(node.args)
        obj_arg = 0
        name_arg = 1

        if isinstance(func, ast.Name) and func.id == "getattr":
            callee = "getattr"
        elif isinstance(func, ast.Attribute) and func.attr == "__getattribute__":
            callee = "__getattribute__"
            obj_arg = -1  # the object is func.value; prepend it into args[0] below
            if func.value is not None:
                args.insert(0, func.value)
        else:
            return

        if not args:
            return
        name_str = None
        if len(args) > name_arg:
            name_node = args[name_arg]
            if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
                name_str = name_node.value
        obj_str = None
        if obj_arg is not None and len(args) > obj_arg:
            obj_str = _resolve_call_name(args[obj_arg])

        flagged = False
        if name_str and name_str in DANGEROUS_FUNC_NAMES:
            flagged = True
        elif obj_str:
            base = obj_str.split(".")[0]
            if base in _SUSPICIOUS_BASES:
                flagged = True
        if flagged:
            desc = f"{obj_str or '?'}.{name_str or '?'}" if obj_str else f"getattr(..., {name_str!r})"
            issues.append(SecurityIssue(
                Severity.CRITICAL, node.lineno, desc,
                "dynamic call bypasses static audit (getattr/__getattribute__ indirect access to dangerous capabilities)",
                "dynamic_bypass",
            ))

    def _check_dynamic_subscript(self, node: ast.Subscript,
                                 issues: List[SecurityIssue]) -> None:
        """Detect __dict__ / globals() / locals() / vars() subscript indirect access."""
        key_str = None
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            key_str = node.slice.value
        base = _resolve_subscript_base(node.value)
        if base and base.endswith("__dict__") and key_str and key_str in DANGEROUS_FUNC_NAMES:
            issues.append(SecurityIssue(
                Severity.CRITICAL, node.lineno, f"{base}[{key_str!r}]",
                "indirect access to dangerous capabilities via a __dict__ subscript, bypassing static audit",
                "dynamic_bypass",
            ))
            return
        if base in ("globals", "locals", "vars"):
            if key_str and key_str in ("os", "subprocess", "builtins", "sys", "ctypes", "importlib"):
                issues.append(SecurityIssue(
                    Severity.CRITICAL, node.lineno, f"{base}()[{key_str!r}]",
                    "indirect access to dangerous modules via an introspection dict, bypassing static audit",
                    "dynamic_bypass",
                ))


# ── name resolution helpers ──────────────────────────────


def _resolve_call_name(func) -> Optional[str]:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return _resolve_attr_name(func)
    return None


def _resolve_attr_name(node: ast.Attribute) -> Optional[str]:
    parts: List[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        parts.reverse()
        return ".".join(parts)
    return None


def _resolve_subscript_base(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Attribute):
        return _resolve_attr_name(node)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _resolve_call_name(node.func)
    return None


# ── backward-compatible alias ────────────────────────────

PluginSecurity = SourceAuditor  # aligned with the existing application's class name for migration
