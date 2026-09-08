# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Model protocol: the "brain" abstraction of an Agent.

The framework is decoupled from any concrete model SDK. To connect a new model,
implement :class:`ModelProvider` (it is recommended to also implement
:meth:`ModelProvider.stream` for streaming output and event broadcasting).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Protocol, runtime_checkable


@dataclass
class ToolCallSpec:
    """One tool call requested by the model."""

    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatMessage:
    """A chat message. Roles follow OpenAI semantics: system / user / assistant / tool."""

    role: str
    content: str = ""
    tool_calls: Optional[List[ToolCallSpec]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    reasoning: str = ""  # chain-of-thought text (a separate field streamed by reasoning models)
    has_reasoning: bool = False  # whether the model response actually carried a reasoning field (distinguishes "empty-string field" from "no field")

    def to_openai(self) -> Dict[str, Any]:
        """Convert to an OpenAI-protocol message dict (tool role carries tool_call_id).

        DeepSeek V4 and other reasoning endpoints contract: in turns where a tool
        call happened, the assistant message's ``reasoning_content`` must be passed
        back verbatim (the field must be preserved even when empty); otherwise the
        next request returns 400. Turns without tool calls do not pass it back
        (the official docs state the field is ignored there).
        """
        msg: Dict[str, Any] = {"role": self.role, "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": _dump_args(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
            if self.has_reasoning:
                msg["reasoning_content"] = self.reasoning
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


def _dump_args(arguments: Dict[str, Any]) -> str:
    import json

    return json.dumps(arguments, ensure_ascii=False)


@dataclass
class ModelUsage:
    """Token usage of one model call."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ModelOutput:
    """Complete result of one model call."""

    content: str = ""
    reasoning: str = ""  # chain of thought / reasoning process (reasoning models)
    tool_calls: Optional[List[ToolCallSpec]] = None
    usage: Optional[ModelUsage] = None
    finish_reason: str = "stop"  # stop | tool_calls | length
    has_reasoning: bool = False  # whether the response actually carried a reasoning field (used to decide tool-turn echo)


@dataclass
class ModelStreamChunk:
    """Streaming output delta. reasoning / delta_content / tool_call_delta may coexist."""

    reasoning: str = ""  # chain-of-thought delta (streamed by reasoning models)
    delta_content: str = ""
    tool_call_delta: Optional[ToolCallSpec] = None  # each occurrence carries the complete merged result of that tool call
    usage: Optional[ModelUsage] = None
    finish_reason: str = ""
    has_reasoning: bool = False  # this delta carried a reasoning field (even an empty string)


@runtime_checkable
class ModelProvider(Protocol):
    """Model provider interface.

    ``params`` is a runtime parameter dict (temperature / max_tokens / top_p etc.),
    merged from the preset's ``params`` and the caller's parameters; implementations
    may read whatever they need.
    """

    model_id: str

    def generate(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]],
        params: Dict[str, Any],
    ) -> ModelOutput:
        """Non-streaming generation. ``tools`` is a list of OpenAI function schemas."""
        ...

    def stream(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]],
        params: Dict[str, Any],
    ) -> Iterator[ModelStreamChunk]:
        """Streaming generation (optional). The runtime prefers the streaming interface to broadcast events."""
        raise NotImplementedError(f"{self.model_id} does not support streaming")
