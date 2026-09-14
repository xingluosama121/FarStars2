# Copyright (c) 2026 xingluosama121, MIT Licensed
"""ask_user tool: lets the agent proactively ask the user to clarify a requirement,
choose between options, or confirm a risky operation.

This restores the original design intent of the kernel (the root-level legacy
code and the UI / approval chain already treated ``ask_user`` as a first-class
interaction), filling the fatal gap where the active tool set exposed no way for
the model itself to ask a question.

The tool is deliberately thin: it delegates to :meth:`RunContext.ask_user`, which
routes to the active UI adapter (web ``question`` modal / console prompt). When no
interactive UI is attached (headless / embedded / automation), the adapter returns
the ``default`` value instead of blocking, so a task never hangs.
"""

from __future__ import annotations

from typing import Any, Dict

from norpagent.protocols.tool import Tool, ToolResult


class AskUserTool:
    name = "ask_user"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Ask the user a question and wait for the answer. Use it when a "
                    "requirement is ambiguous (clarify instead of guessing), when a "
                    "choice must be made, or to confirm a dangerous / irreversible "
                    "operation before carrying it out. Write the question in Markdown "
                    "(use a '##' heading to highlight the key point)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "The question to ask the user. Markdown is supported; "
                                "use a '##' heading to highlight the key point."
                            ),
                        },
                        "default": {
                            "type": "string",
                            "description": (
                                "Value returned when no interactive UI is available "
                                "(headless / automation) or when the user does not "
                                "answer in time. Optional."
                            ),
                        },
                    },
                    "required": ["question"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        question = str((args or {}).get("question") or "").strip()
        default = str((args or {}).get("default") or "")
        if not question:
            return ToolResult(
                output="ask_user requires a non-empty 'question' argument.",
                success=False,
                error="invalid_args",
            )
        answer = ""
        try:
            # kind="clarify": this is an open question, so the UI keeps its text box
            # (only approval prompts switch to reject/approve buttons).
            answer = ctx.ask_user(question, default, kind="clarify")
        except Exception as exc:  # noqa: BLE001 — never let interaction break the task
            return ToolResult(
                output=(
                    "ask_user could not reach an interactive UI "
                    f"({exc}); continue with best judgment."
                ),
                success=True,
            )
        answer = str(answer if answer is not None else "").strip()
        if not answer:
            return ToolResult(
                output=(
                    "the user did not provide an answer (no interactive UI available "
                    "or no reply); continue with best judgment."
                )
            )
        return ToolResult(output=f"user answer: {answer}")
