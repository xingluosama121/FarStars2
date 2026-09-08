# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Anthropic protocol model adapter: connects to the Claude family of models.

Requires ``anthropic>=0.34`` (norpagent[anthropic]); the client is lazily loaded:
registration and configuration do not fail without the SDK; the first call gives a
clear installation hint.

Protocol conversion notes:
- system messages are separated into the top-level ``system`` parameter;
- assistant tool_calls map to tool_use content blocks;
- tool messages map to tool_result content blocks inside the immediately following
  user message (consecutive tool messages are merged into one user message to
  satisfy the Anthropic protocol requirements);
- OpenAI function schemas map to Anthropic tool input_schema.

Cancellation cooperation: when params["_cancel_event"] (threading.Event, injected
by the kernel) is set, the streaming loop stops as early as possible, in
combination with the kernel's call_timeout hard interrupt.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Iterator, List, Optional, Tuple

from norpagent.protocols.model import (
    ChatMessage,
    ModelOutput,
    ModelStreamChunk,
    ModelUsage,
    ToolCallSpec,
)


class AnthropicProvider:
    """Anthropic protocol adapter."""

    model_id = "anthropic"

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.model_name = model_name or os.environ.get("NORPAGENT_ANTHROPIC_MODEL", "") or "claude-sonnet-4-5"
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.base_url = base_url
        self.timeout = timeout or 120.0
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise RuntimeError(
                    "anthropic SDK is not installed. Run: pip install norpagent[anthropic]"
                    " (or pip install anthropic>=0.34)"
                )
            api_key = self.api_key or os.environ.get(self.api_key_env, "")
            if not api_key:
                raise RuntimeError(
                    f"No API key found. Set the environment variable {self.api_key_env}, "
                    f"or pass one explicitly when constructing AnthropicProvider(api_key=...)."
                )
            kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": self.timeout}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    # ── protocol conversion (module-level functions for easy unit testing) ──

    def _to_anthropic_messages(
        self, messages: List[ChatMessage]
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Return (system text, Anthropic messages list)."""
        system_parts: List[str] = []
        out: List[Dict[str, Any]] = []

        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.role == "system":
                system_parts.append(msg.content)
                i += 1
                continue

            if msg.role == "tool":
                # merge consecutive tool messages into one user message
                tool_blocks: List[Dict[str, Any]] = []
                while i < len(messages) and messages[i].role == "tool":
                    tmsg = messages[i]
                    tool_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tmsg.tool_call_id or "",
                            "content": tmsg.content or "",
                        }
                    )
                    i += 1
                out.append({"role": "user", "content": tool_blocks})
                continue

            if msg.role == "assistant" and msg.tool_calls:
                blocks: List[Dict[str, Any]] = []
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments or {},
                        }
                    )
                out.append({"role": "assistant", "content": blocks})
                i += 1
                continue

            out.append({"role": msg.role, "content": msg.content or ""})
            i += 1

        system = "\n\n".join(p for p in system_parts if p) or None
        return system, out

    def _to_anthropic_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """OpenAI function schema -> Anthropic tool definitions."""
        if not tools:
            return None
        result: List[Dict[str, Any]] = []
        for tool in tools:
            fn = tool.get("function", tool)
            result.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
                }
            )
        return result

    def _to_output(self, message: Any) -> ModelOutput:
        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_calls: List[ToolCallSpec] = []
        for block in getattr(message, "content", []) or []:
            btype = getattr(block, "type", "")
            if btype == "text":
                content_parts.append(block.text)
            elif btype == "thinking":
                reasoning_parts.append(getattr(block, "thinking", "") or "")
            elif btype == "redacted_thinking":
                reasoning_parts.append("[thinking content redacted]")
            elif btype == "tool_use":
                tool_calls.append(
                    ToolCallSpec(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input or {}),
                    )
                )
        finish = {
            "end_turn": "stop",
            "tool_use": "tool_calls",
            "max_tokens": "length",
        }.get(getattr(message, "stop_reason", None) or "", "stop")
        usage = None
        if getattr(message, "usage", None):
            usage = ModelUsage(
                input_tokens=message.usage.input_tokens or 0,
                output_tokens=message.usage.output_tokens or 0,
                total_tokens=(message.usage.input_tokens or 0) + (message.usage.output_tokens or 0),
            )
        output = ModelOutput(
            content="\n".join(content_parts),
            reasoning="\n".join(reasoning_parts),
            tool_calls=tool_calls or None,
            usage=usage,
            finish_reason=finish,
        )
        return output

    def _check_cancel(self, params: Dict[str, Any]) -> bool:
        event = params.get("_cancel_event")
        return isinstance(event, threading.Event) and event.is_set()

    # ── generation ───────────────────────────────────────

    def generate(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]],
        params: Dict[str, Any],
    ) -> ModelOutput:
        client = self._get_client()
        system, anthropic_messages = self._to_anthropic_messages(messages)
        kwargs: Dict[str, Any] = {
            "model": params.get("model_name") or self.model_name,
            "messages": anthropic_messages,
            "temperature": float(params.get("temperature", 1.0)),
        }
        if system:
            kwargs["system"] = system
        max_tokens = int(params.get("max_tokens") or 4096)
        kwargs["max_tokens"] = max_tokens
        anthropic_tools = self._to_anthropic_tools(tools)
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
        message = client.messages.create(**kwargs)
        return self._to_output(message)

    def stream(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]],
        params: Dict[str, Any],
    ) -> Iterator[ModelStreamChunk]:
        client = self._get_client()
        system, anthropic_messages = self._to_anthropic_messages(messages)
        kwargs: Dict[str, Any] = {
            "model": params.get("model_name") or self.model_name,
            "messages": anthropic_messages,
            "temperature": float(params.get("temperature", 1.0)),
            "max_tokens": int(params.get("max_tokens") or 4096),
            "stream": True,
        }
        if system:
            kwargs["system"] = system
        anthropic_tools = self._to_anthropic_tools(tools)
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        stream = client.messages.create(**kwargs)

        # aggregate tool_use deltas by index
        pending: Dict[int, Dict[str, Any]] = {}
        input_tokens = 0
        output_tokens = 0
        finish_reason = ""

        for event in stream:
            if self._check_cancel(params):
                return
            etype = getattr(event, "type", "")
            if etype == "message_start":
                usage = getattr(event, "message", None)
                usage = getattr(usage, "usage", None) if usage else None
                if usage:
                    input_tokens = getattr(usage, "input_tokens", 0) or 0
            elif etype == "content_block_start":
                block = event.content_block
                if getattr(block, "type", "") == "tool_use":
                    pending[getattr(event, "index", len(pending))] = {
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "args_parts": [],
                    }
            elif etype == "content_block_delta":
                delta = event.delta
                dtype = getattr(delta, "type", "")
                if dtype == "text_delta" and getattr(delta, "text", None):
                    yield ModelStreamChunk(delta_content=delta.text)
                elif dtype == "thinking_delta" and getattr(delta, "thinking", None):
                    # Claude extended thinking: chain-of-thought deltas (absent unless thinking is enabled)
                    yield ModelStreamChunk(reasoning=delta.thinking)
                elif dtype == "input_json_delta" and getattr(delta, "partial_json", None):
                    idx = getattr(event, "index", None)
                    if idx in pending:
                        pending[idx]["args_parts"].append(delta.partial_json)
            elif etype == "message_delta":
                if getattr(event, "delta", None) and getattr(event.delta, "stop_reason", None):
                    finish_reason = {
                        "end_turn": "stop",
                        "tool_use": "tool_calls",
                        "max_tokens": "length",
                    }.get(event.delta.stop_reason, event.delta.stop_reason)
                usage = getattr(event, "usage", None)
                if usage:
                    output_tokens = getattr(usage, "output_tokens", 0) or 0

        for idx in sorted(pending):
            slot = pending[idx]
            try:
                arguments = json.loads("".join(slot["args_parts"]) or "{}")
            except json.JSONDecodeError:
                arguments = {}
            yield ModelStreamChunk(
                tool_call_delta=ToolCallSpec(
                    id=slot["id"] or f"toolu_{idx}",
                    name=slot["name"] or "",
                    arguments=arguments,
                )
            )

        total = input_tokens + output_tokens
        yield ModelStreamChunk(
            usage=ModelUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total,
            ),
            finish_reason=finish_reason or ("tool_calls" if pending else "stop"),
        )
