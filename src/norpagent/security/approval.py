# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Human approval security layer (pure decision-making, zero dependencies).

Migrated from the existing application's plugin_system.approval; responsibilities unchanged:

- native tool confirmation: native_confirm_enabled / write / delete / exec,
  mapped by "tool name → level" (write_file → WRITE, delete_file → DELETE,
  exec_cmd → EXEC, etc., consistent with the existing application's _TOOL_LEVELS);
- plugin tool-call approval: the approval_enabled master switch plus per-plugin
  APPROVAL_HINTS fine-grained control (approval="none" skips approval, otherwise
  the master switch applies).

This module only decides "whether approval is required"; it does not handle UI
interaction: the actual dialog is performed by UI adapters via ``ctx.ask_user``.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional, Tuple


class ApprovalLevel(Enum):
    NONE = "none"
    WRITE = "write"
    DELETE = "delete"
    EXEC = "exec"
    PLUGIN = "plugin"


# native tool → approval level mapping (consistent with the existing application's default policy)
_TOOL_LEVELS: Dict[str, ApprovalLevel] = {
    "file_write": ApprovalLevel.WRITE,
    "file_surgeon": ApprovalLevel.WRITE,
    "file_delete": ApprovalLevel.DELETE,
    "exec_cmd": ApprovalLevel.EXEC,
    # legacy tool names of the existing application (write_file / delete_file / install_dependency, etc.)
    "write_file": ApprovalLevel.WRITE,
    "replace_in_file": ApprovalLevel.WRITE,
    "surgical_replace": ApprovalLevel.WRITE,
    "copy_file": ApprovalLevel.WRITE,
    "move_file": ApprovalLevel.WRITE,
    "init_project": ApprovalLevel.WRITE,
    "delete_file": ApprovalLevel.DELETE,
    "install_dependency": ApprovalLevel.EXEC,
    "git_commit": ApprovalLevel.EXEC,
    "open_file": ApprovalLevel.EXEC,
}


class ApprovalPolicy:
    """Human approval policy (native tool confirmation + plugin tool-call approval)."""

    def __init__(self, config: Optional[dict] = None,
                 tool_hints: Optional[dict] = None) -> None:
        config = config or {}
        legacy = config.get("confirm_write_delete", True)
        self.native_enabled = bool(config.get("native_confirm_enabled", legacy))
        self.native_write = bool(config.get("native_confirm_write", legacy))
        self.native_delete = bool(config.get("native_confirm_delete", legacy))
        self.native_exec = bool(config.get("native_confirm_exec", True))
        self.plugin_enabled = bool(config.get("approval_enabled", True))
        self._tool_hints = tool_hints or {}

    def set_tool_hints(self, tool_hints: Optional[dict]) -> None:
        """Refresh plugin tool approval hints (updated by the caller before each confirmation)."""
        self._tool_hints = tool_hints or {}

    def level_of(self, tool_name: str) -> ApprovalLevel:
        """Return the approval level corresponding to a native tool."""
        return _TOOL_LEVELS.get(tool_name, ApprovalLevel.NONE)

    def requires_approval(self, tool_name: str,
                          is_plugin: bool = False) -> Tuple[bool, ApprovalLevel]:
        """Decide whether a tool call needs human approval.

        Returns (needs approval, approval level).
        """
        if is_plugin:
            hint = self._tool_hints.get(tool_name)
            if isinstance(hint, dict) and hint.get("approval") == "none":
                return False, ApprovalLevel.NONE
            return self.plugin_enabled, ApprovalLevel.PLUGIN

        level = self.level_of(tool_name)
        if level == ApprovalLevel.NONE:
            return False, level
        if not self.native_enabled:
            return False, level
        if level == ApprovalLevel.WRITE:
            return self.native_write, level
        if level == ApprovalLevel.DELETE:
            return self.native_delete, level
        if level == ApprovalLevel.EXEC:
            return self.native_exec, level
        return False, level

    def get_plugin_config(self) -> dict:
        return {"approval_enabled": self.plugin_enabled}

    def get_native_config(self) -> dict:
        return {
            "enabled": self.native_enabled,
            "write": self.native_write,
            "delete": self.native_delete,
            "exec": self.native_exec,
        }
