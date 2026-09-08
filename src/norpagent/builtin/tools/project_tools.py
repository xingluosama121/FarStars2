# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Project management tool: project_status.

Summarizes the workspace project state: metadata, file statistics, recent
modifications, git branch and changes. The component is accessed via
``ctx.project_manager`` (injected by the runtime when the preset declares
``components={"project_manager": "basic"}``).
"""

from __future__ import annotations

from typing import Any, Dict

from norpagent.protocols.tool import Tool, ToolResult


def _fmt_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{n}B"


class ProjectStatusTool:
    name = "project_status"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Shows the state of the current workspace project: project metadata, file count and size, "
                    "extension distribution, recently modified files, git branch and uncommitted changes. "
                    "Useful for understanding the whole project before making changes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "recent_files": {
                            "type": "integer",
                            "description": "Number of recently modified files to show (default 10)",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        manager = ctx.project_manager
        if manager is None:
            return ToolResult(
                output=(
                    "The current mode has no project management component assembled. "
                    "Declare components={\"project_manager\": \"basic\"} in the preset "
                    "(the standard preset has it built in)."
                ),
                success=False,
                error="project_manager component not assembled",
            )
        try:
            recent_n = max(1, min(int(args.get("recent_files") or 10), 50))
            status = manager.status()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"failed to read project status: {exc}", success=False, error=str(exc))

        meta = status.get("meta") or {}
        scan = status.get("scan") or {}
        lines = ["[project status]", ""]
        lines.append(f"Project: {meta.get('name', '?')} ({scan.get('root', '?')})")
        if meta.get("description"):
            lines.append(f"Description: {meta['description']}")
        lines.append(
            f"Task statistics: {meta.get('tasks_total', 0)} total / {meta.get('tasks_success', 0)} succeeded"
        )
        lines.append("")
        if scan.get("exists"):
            lines.append("── workspace ──")
            lines.append(
                f"Files: {scan['files']:,} / dirs: {scan['dirs']:,} / "
                f"total size: {_fmt_bytes(scan['total_bytes'])}"
            )
            exts = scan.get("extensions") or {}
            if exts:
                lines.append(
                    "Extensions: " + ", ".join(f"{e}×{n}" for e, n in exts.items())
                )
            recent = scan.get("recent_files") or []
            if recent:
                lines.append(f"Recently modified (top {recent_n}):")
                for item in recent[:recent_n]:
                    age = item.get("age_seconds", 0)
                    if age < 60:
                        age_s = f"{int(age)}s"
                    elif age < 3600:
                        age_s = f"{int(age // 60)}min"
                    elif age < 86400:
                        age_s = f"{age / 3600:.1f}h"
                    else:
                        age_s = f"{age / 86400:.1f}d"
                    lines.append(
                        f"  {item['path']} ({_fmt_bytes(item['size'])}, {age_s} ago)"
                    )
        else:
            lines.append(f"Workspace directory does not exist: {scan.get('root')}")
        git = status.get("git")
        lines.append("")
        if git:
            lines.append("── git ──")
            lines.append(
                f"Branch: {git.get('branch') or '(detached)'} / "
                f"changes: {git.get('changes', 0)} (staged {git.get('staged', 0)}, "
                f"untracked {git.get('untracked', 0)})"
            )
            commits = git.get("recent_commits") or []
            if commits:
                lines.append("Recent commits:")
                lines.extend(f"  {c}" for c in commits)
        else:
            lines.append("── git ──")
            lines.append("(the current workspace is not a git repository)")
        return ToolResult(output="\n".join(lines))
