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
    # multimodal attachments (native passthrough): a list of dicts, one per attachment.
    # shape: {"kind": "image"|"audio"|"video", "name", "mime", "ext",
    #         "route": "direct" (data carries base64, passed to the model) |
    #                  "service" (text carries the service transcription/description)}
    # ``route="service"`` items are rendered as text parts; ``direct`` items become
    # native multimodal content parts (image_url / input_audio / video_url).
    attachments: Optional[List[Dict[str, Any]]] = None
    # per-message generation stats for the frontend (token speed / total tokens /
    # generation time). Written by the kernel on final assistant replies; shape:
    # {"gen_seconds": float, "speed": float|None, "output_tokens": int,
    #  "input_tokens": int, "total_tokens": int, "ts": float}
    stats: Optional[Dict[str, Any]] = None
    # ordered display segments of one work (task) — 2026-09-12 round 9.
    # One work may contain many output blocks and thinking processes (interleaved
    # with tool calls); each segment is a dict:
    #   {"type": "think",  "text": str}                       — chain-of-thought block
    #   {"type": "output", "text": str}                       — reply text block
    #   {"type": "tool", "id": str, "name": str,
    #    "args": dict, "status": "running"|"ok"|"fail",
    #    "result": str}                                       — tool call card
    # The kernel attaches only the segments produced since the previous appended
    # message; the front merges consecutive assistant messages of the same task
    # so the interleaved order is preserved across reloads.
    segments: Optional[List[Dict[str, Any]]] = None

    def _multimodal_parts(self) -> List[Dict[str, Any]]:
        """Assemble OpenAI-compatible multimodal content parts for this message."""
        parts: List[Dict[str, Any]] = []
        if self.content:
            parts.append({"type": "text", "text": self.content})
        for item in self.attachments or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            name = str(item.get("name") or "")
            if item.get("route") == "service":
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(
                        {"type": "text",
                         "text": f"[{kind or 'media'}: {name}]\n{text}".strip()}
                    )
                continue
            data = str(item.get("data") or "")
            if not data:
                continue
            mime = str(item.get("mime") or "")
            ext = str(item.get("ext") or "")
            if kind == "image":
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime or 'image/png'};base64,{data}"},
                })
            elif kind == "audio":
                parts.append({
                    "type": "input_audio",
                    "input_audio": {"data": data, "format": ext or "wav"},
                })
            elif kind == "video":
                # video_url is the OpenAI-compatible extension used by video-capable
                # compatible endpoints (Qwen / GLM style providers); plain text-only
                # endpoints may reject it - that is a model capability question.
                parts.append({
                    "type": "video_url",
                    "video_url": {"url": f"data:{mime or 'video/mp4'};base64,{data}"},
                })
            else:
                parts.append({"type": "text", "text": f"[attachment: {name}]"})
        return parts

    def to_dict(self) -> Dict[str, Any]:
        """Lossless JSON-serializable snapshot of this message.

        Used by the session stores to persist branch / version snapshots
        (regenerate + version switching) without depending on sqlite row shape.
        """
        return {
            "role": self.role,
            "content": self.content or "",
            "tool_calls": (
                [{"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                 for tc in self.tool_calls]
                if self.tool_calls else None
            ),
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "reasoning": self.reasoning or "",
            "has_reasoning": bool(self.has_reasoning),
            "attachments": list(self.attachments) if self.attachments else None,
            "stats": dict(self.stats) if self.stats else None,
            "segments": list(self.segments) if self.segments else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        """Rebuild a message from :meth:`to_dict` output (best-effort)."""
        data = data or {}
        tool_calls = None
        raw_tc = data.get("tool_calls")
        if raw_tc:
            tool_calls = [
                ToolCallSpec(
                    id=str(item.get("id") or f"call_{i}"),
                    name=str(item.get("name") or ""),
                    arguments=item.get("arguments") or {},
                )
                for i, item in enumerate(raw_tc)
                if isinstance(item, dict)
            ]
        attachments = data.get("attachments")
        stats = data.get("stats")
        segments = data.get("segments")
        return cls(
            role=str(data.get("role") or ""),
            content=str(data.get("content") or ""),
            tool_calls=tool_calls,
            tool_call_id=(str(data["tool_call_id"])
                          if data.get("tool_call_id") else None),
            name=(str(data["name"]) if data.get("name") else None),
            reasoning=str(data.get("reasoning") or ""),
            has_reasoning=bool(data.get("has_reasoning")),
            attachments=list(attachments) if isinstance(attachments, list) else None,
            stats=dict(stats) if isinstance(stats, dict) else None,
            segments=list(segments) if isinstance(segments, list) else None,
        )

    def to_openai(self) -> Dict[str, Any]:
        """Convert to an OpenAI-protocol message dict (tool role carries tool_call_id).

        DeepSeek V4 and other reasoning endpoints contract: in turns where a tool
        call happened, the assistant message's ``reasoning_content`` must be passed
        back verbatim (the field must be preserved even when empty); otherwise the
        next request returns 400. Turns without tool calls do not pass it back
        (the official docs state the field is ignored there).

        Messages carrying multimodal attachments use the array content form
        (``[{"type": "text"}, {"type": "image_url"}, ...]``); plain messages keep
        the simple string form for maximum endpoint compatibility.
        """
        msg: Dict[str, Any] = {"role": self.role}
        if self.attachments:
            msg["content"] = self._multimodal_parts()
        else:
            msg["content"] = self.content or ""
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
    # True when the numbers are a local raw-text estimate because the endpoint
    # returned no usage (e.g. no stream_options.include_usage support). Lets the
    # UI mark the value as approximate instead of presenting it as exact.
    estimated: bool = False


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
