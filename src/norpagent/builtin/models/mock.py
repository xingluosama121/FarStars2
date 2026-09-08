# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Mock model: deterministic scripted responses, designed for benchmarks and framework debugging.

No network or SDK dependencies. ``script`` is a list of response entries consumed
in call order; the last entry repeats:

    MockModelProvider(script=[
        {"tool_call": {"name": "echo", "args": {"text": "hi"}}},  # round 1: issue a tool call
        {"reasoning": "think first, then answer", "content": "done"},  # round 2: chain of thought + final answer
    ])

Entry fields:
- ``content``: body reply;
- ``tool_call``: tool call ({name, args});
- ``reasoning``: chain-of-thought text (streamed in small pieces, returned together with content);
- ``has_reasoning``: whether the simulated response carries a reasoning field (default True when
  reasoning is non-empty; used to verify the DeepSeek V4 tool-turn reasoning_content echo contract,
  including the keep-empty-string-field case).

When no script is configured, a guidance reply is returned (explaining how to
connect a real model), so first-time users understand that "the mock model is not
configured" instead of failing silently.

Benchmark scenarios: assemble a fixed script for the agent under test and compare
behavioral differences and resource consumption of different implementations
(models / tools / sessions) on the same input.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

from norpagent.protocols.model import (
    ChatMessage,
    ModelOutput,
    ModelStreamChunk,
    ModelUsage,
    ToolCallSpec,
)

# guidance reply when no script is configured (keep the "mock:" prefix for log/test identification)
_MOCK_GUIDANCE = (
    "mock: no response script configured (script parameter); this reply comes from "
    "the built-in mock model and only verifies link connectivity.\n\n"
    "To connect a real model:\n"
    "1. pick a model in the frontend Settings and fill in the API key; or\n"
    "2. in code: np(model=\"openai_compat\", model_name=\"deepseek-v4-flash\", api_key=\"...\"); or\n"
    "3. give mock a script: MockModelProvider(script=[{\"content\": \"...\"}]).\n\n"
    "The tool set is registered with the preset (echo / file_read / exec_cmd / web_search etc.); "
    "once a real model is connected, they can be called normally."
)


class MockModelProvider:
    """Scripted deterministic model."""

    model_id = "mock"

    def __init__(self, script: Optional[List[Dict[str, Any]]] = None) -> None:
        self.script = script or [{"content": _MOCK_GUIDANCE}]
        self._call_count = 0

    def _next_entry(self) -> Dict[str, Any]:
        idx = min(self._call_count, len(self.script) - 1)
        self._call_count += 1
        return self.script[idx]

    def _entry_to_output(self, entry: Dict[str, Any]) -> ModelOutput:
        reasoning = str(entry.get("reasoning") or "")
        has_reasoning = bool(entry.get("has_reasoning", bool(reasoning)))
        if "tool_call" in entry:
            spec = entry["tool_call"]
            if isinstance(spec, dict):
                args = spec.get("args") or spec.get("arguments") or {}
                if isinstance(args, str):
                    args = json.loads(args)
                call = ToolCallSpec(
                    id=spec.get("id") or f"mock_call_{self._call_count}",
                    name=spec["name"],
                    arguments=args,
                )
            else:
                raise ValueError(f"invalid tool_call entry in mock script: {spec!r}")
            return ModelOutput(
                reasoning=reasoning,
                has_reasoning=has_reasoning,
                tool_calls=[call],
                finish_reason="tool_calls",
            )
        if "content" in entry or reasoning or has_reasoning:
            return ModelOutput(
                content=str(entry.get("content") or ""),
                reasoning=reasoning,
                has_reasoning=has_reasoning,
                finish_reason="stop",
            )
        raise ValueError(f"invalid mock script entry (must contain content / tool_call / reasoning): {entry!r}")

    def generate(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]],
        params: Dict[str, Any],
    ) -> ModelOutput:
        # task-level script override (params["mock_script"])
        override = params.get("mock_script")
        if isinstance(override, list):
            entry = override[min(self._call_count, len(override) - 1)]
            self._call_count += 1
        else:
            entry = self._next_entry()
        output = self._entry_to_output(entry)
        output.usage = ModelUsage(
            input_tokens=sum(len(m.content) // 3 + 1 for m in messages),
            output_tokens=max(1, len(output.content) // 3),
        )
        output.usage.total_tokens = output.usage.input_tokens + output.usage.output_tokens
        return output

    def stream(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]],
        params: Dict[str, Any],
    ) -> Iterator[ModelStreamChunk]:
        output = self.generate(messages, tools, params)
        # tool calls are given at once; chain of thought and body stream in small pieces
        for spec in output.tool_calls or []:
            yield ModelStreamChunk(
                tool_call_delta=spec, has_reasoning=output.has_reasoning
            )
        step = 8
        pieces: List[tuple] = (
            [("reasoning", output.reasoning)] if output.reasoning else []
        ) + ([("content", output.content)] if output.content else [])
        for kind, text in pieces:
            for i in range(0, len(text), step):
                piece = text[i : i + step]
                is_last = i + step >= len(text)
                kwargs: Dict[str, Any] = {}
                if kind == "reasoning":
                    kwargs["reasoning"] = piece
                    kwargs["has_reasoning"] = output.has_reasoning
                else:
                    kwargs["delta_content"] = piece
                if is_last:
                    kwargs["finish_reason"] = output.finish_reason
                    kwargs["usage"] = output.usage
                yield ModelStreamChunk(**kwargs)
        if not output.content and not output.reasoning and output.usage:
            yield ModelStreamChunk(
                usage=output.usage, finish_reason=output.finish_reason,
                has_reasoning=output.has_reasoning,
            )
