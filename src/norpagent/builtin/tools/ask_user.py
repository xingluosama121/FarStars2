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
                    "(use a '##' heading to highlight the key point). "
                    "IMPORTANT: the user only sees the 'question' argument of this "
                    "call. Put the entire question there -- heading, context, options, "
                    "everything. Text you write in your ordinary reply is NOT shown to "
                    "the user while the question is pending, so the question must never "
                    "live in your message body with an empty or partial argument."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "The complete question to ask the user: heading, "
                                "context, options, everything the user needs in order "
                                "to answer. Markdown is supported; use a '##' heading "
                                "to highlight the key point. This argument is the only "
                                "thing the user sees -- your assistant text output is "
                                "not shown while the question is pending."
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
        if not question:
            return ToolResult(
                output="ask_user requires a non-empty 'question' argument.",
                success=False,
                error="invalid_args",
            )
        try:
            # kind="clarify": this is an open question, so the UI keeps its text box
            # (only approval prompts switch to reject/approve buttons).
            answer = ctx.ask_user(question, kind="clarify")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                output=(
                    "ask_user failed: no interactive UI could be reached "
                    "(%s: %s). NO answer was obtained, so do NOT invent one and do "
                    "NOT treat this as a decision. Re-ask later, pick an option you "
                    "explicitly label as your own fallback, or stop and report the "
                    "blockage." % (type(exc).__name__, exc)
                ),
                success=False,
                error="no_ui",
            )
        answer = str(answer if answer is not None else "").strip()
        if not answer:
            return ToolResult(
                output=(
                    "the user did not answer (no interactive UI available, or no "
                    "reply before the timeout). NO answer was obtained, so do NOT "
                    "invent one and do NOT treat this as a decision. Re-ask later, "
                    "pick an option you explicitly label as your own fallback, or "
                    "stop and report the blockage."
                ),
                success=False,
                error="no_answer",
            )
        return ToolResult(output="user answer: %s" % answer)
