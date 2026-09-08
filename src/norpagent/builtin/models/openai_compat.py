# Copyright (c) 2026 xingluosama121, MIT Licensed
"""OpenAI-compatible model adapter: connects to any OpenAI-protocol service.

Covers OpenAI / DeepSeek / Qwen(DashScope) / vLLM / Ollama and other
OpenAI-compatible endpoints. Requires ``openai>=1.40`` (norpagent[openai]);
the client is lazily loaded: registration and configuration do not fail without
the SDK; the first call gives a clear installation hint.

Usage::

    from norpagent.builtin.models.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider(
        model_name="deepseek-v4-flash",           # remote model name
        base_url="https://api.deepseek.com/v1",   # service endpoint
        api_key_env="DEEPSEEK_API_KEY",           # API key environment variable name
    )

    reg.register_model("deepseek", provider)
    agent = AgentRuntime(reg, Preset(name="p", ..., model="deepseek", ...))

Cancellation cooperation: when params["_cancel_event"] (threading.Event, injected
by the kernel) is set, the streaming loop stops as early as possible, in
combination with the kernel's call_timeout hard interrupt.
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Dict, Iterator, List, Optional

from norpagent.protocols.model import (
    ChatMessage,
    ModelOutput,
    ModelStreamChunk,
    ModelUsage,
    ToolCallSpec,
)

# model-name patterns of reasoning series that support the reasoning_effort parameter
# (DeepSeek V4 / GLM / Kimi / Qwen and other compatible endpoints reject the parameter; hard-passing causes 400)
_EFFORT_MODEL_RE = re.compile(
    r"(^|[-_.])(o[0-9]+|gpt-5|deepseek-v4[a-z0-9]*)([-_.]|$)",
    re.IGNORECASE,
)

_DS_V4_RE = re.compile(r"^deepseek-v4([-_.]|$)", re.IGNORECASE)


def model_supports_reasoning_effort(model: str) -> bool:
    """Decide whether the model name belongs to a reasoning series supporting reasoning_effort.

    Covers the OpenAI reasoning series (o1 / o3 / gpt-5 etc.) and DeepSeek V4
    (deepseek-v4-pro / deepseek-v4-flash)."""
    return bool(_EFFORT_MODEL_RE.search(model or ""))


def model_is_deepseek_v4(model: str) -> bool:
    """Decide whether the model name belongs to the DeepSeek V4 series (thinking mode is controlled by the thinking parameter)."""
    return bool(_DS_V4_RE.match((model or "").strip()))


def normalize_effort(effort: str) -> str:
    """Normalize a caller-provided reasoning strength into values accepted by each endpoint.

    DeepSeek V4 accepts only low / high / max; official mapping:
    medium / xhigh → high. All other values (low / high / max / none / empty) pass through unchanged.
    """
    e = str(effort or "").strip().lower()
    if e in ("medium", "xhigh"):
        return "high"
    return e


def _extract_reasoning(message: Any) -> tuple:
    """Extract the chain-of-thought field from a response message / streamed delta.

    Returns ``(text, has_field)``. ``has_field`` means the response actually
    carried a ``reasoning_content`` / ``reasoning`` field (even when the value is
    an empty string).

    The DeepSeek V4 contract requires: in turns where a tool call happened,
    ``reasoning_content`` must be passed back verbatim — the field must be kept
    even when empty — so the two cases "field missing" and "field present but
    empty" must be distinguished.
    """
    fields_set = set(getattr(message, "model_fields_set", None) or ())
    text = (
        getattr(message, "reasoning_content", "")
        or getattr(message, "reasoning", "")
        or ""
    )
    has_field = "reasoning_content" in fields_set or "reasoning" in fields_set
    if not has_field:
        # fallback for non-pydantic response objects (dict / SimpleNamespace etc.)
        has_field = bool(
            getattr(message, "reasoning_content", None)
            or getattr(message, "reasoning", None)
        )
    return text, has_field


class OpenAICompatProvider:
    """OpenAI-compatible service adapter."""

    model_id = "openai_compat"

    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_key_env: str = "OPENAI_API_KEY",
        timeout: Optional[float] = None,
    ) -> None:
        self.model_name = model_name or os.environ.get("NORPAGENT_OPENAI_MODEL", "") or "gpt-4o-mini"
        self.base_url = base_url or os.environ.get("NORPAGENT_OPENAI_BASE_URL", "") or None
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.timeout = timeout or 120.0
        self._client = None

    # ── SDK lazy loading ─────────────────────────────────

    def _get_client(self, params: Optional[Dict[str, Any]] = None) -> Any:
        # params-level overrides: api_key / base_url / model_name can be given
        # dynamically per call (used by the FE frontend node "nearby wiring" to
        # feed config into model nodes).
        p = params or {}
        api_key = p.get("api_key") or self.api_key or os.environ.get(self.api_key_env, "")
        base_url = p.get("base_url") or self.base_url
        if not api_key:
            raise RuntimeError(
                f"No API key found. Set the environment variable {self.api_key_env}, "
                f"or pass one explicitly when constructing OpenAICompatProvider(api_key=...)."
            )
        # rebuild the client when override parameters change (caching the old client would keep the old key active)
        cache_key = f"{api_key}|{base_url or ''}"
        if self._client is None or getattr(self._client, "_norp_cache_key", "") != cache_key:
            try:
                from openai import OpenAI
            except ImportError:
                raise RuntimeError(
                    "openai SDK is not installed. Run: pip install norpagent[openai]"
                    " (or pip install openai>=1.40)"
                )
            kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": self.timeout}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = OpenAI(**kwargs)
            try:
                self._client._norp_cache_key = cache_key  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — ignore the cache key when the SDK refuses attributes
                pass
        return self._client

    # ── protocol conversion ──────────────────────────────

    def _to_messages(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        return [m.to_openai() for m in messages]

    def _to_output(self, message: Any) -> ModelOutput:
        content = message.content or ""
        reasoning, has_reasoning = _extract_reasoning(message)
        tool_calls: Optional[List[ToolCallSpec]] = None
        if getattr(message, "tool_calls", None):
            tool_calls = []
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                tool_calls.append(
                    ToolCallSpec(id=tc.id or f"call_{len(tool_calls)}", name=tc.function.name, arguments=arguments)
                )
        return ModelOutput(
            content=content,
            reasoning=reasoning,
            has_reasoning=has_reasoning,
            tool_calls=tool_calls,
            finish_reason=getattr(message, "finish_reason", None) or ("tool_calls" if tool_calls else "stop"),
        )

    def _check_cancel(self, params: Dict[str, Any]) -> bool:
        event = params.get("_cancel_event")
        return isinstance(event, threading.Event) and event.is_set()

    # ── request parameter assembly ───────────────────────

    def _build_request_kwargs(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]],
        params: Dict[str, Any],
        stream: bool,
    ) -> Dict[str, Any]:
        """Assemble chat.completions request parameters.

        - reasoning_effort: passed through only for supported reasoning-series
          models (other endpoints return 400), with endpoint-compliant strength
          mapping (DeepSeek V4: medium/xhigh → high);
        - DeepSeek V4 thinking mode: explicitly toggled via ``extra_body.thinking``
          (enabled by default; temperature only takes effect when explicitly disabled);
        - OpenAI reasoning series (o*/gpt-5) cannot disable reasoning: do not send
          temperature to avoid 400 (OpenAI forbids sending temperature alongside
          reasoning).
        """
        model = params.get("model_name") or self.model_name
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": self._to_messages(messages),
            "stream": stream,
        }
        effort = normalize_effort(str(params.get("reasoning_effort") or ""))
        supports = model_supports_reasoning_effort(model)
        is_v4 = model_is_deepseek_v4(model)
        if effort and effort != "none":
            if supports:
                kwargs["reasoning_effort"] = effort
                if is_v4:
                    kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            else:
                kwargs["temperature"] = float(params.get("temperature", 1.0))
        else:
            # no strength given / reasoning explicitly disabled
            if is_v4:
                if effort == "none":
                    kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
                # not specified: keep the official default (thinking enabled; temperature ignored but not an error)
                kwargs["temperature"] = float(params.get("temperature", 1.0))
            elif not supports:
                kwargs["temperature"] = float(params.get("temperature", 1.0))
            # supports and not v4 (OpenAI o*/gpt-5): reasoning cannot be disabled; no temperature
        max_tokens = params.get("max_tokens")
        if max_tokens:
            kwargs["max_tokens"] = int(max_tokens)
        if tools:
            kwargs["tools"] = tools
        return kwargs

    # ── generation ───────────────────────────────────────

    def generate(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]],
        params: Dict[str, Any],
    ) -> ModelOutput:
        client = self._get_client(params)
        kwargs = self._build_request_kwargs(messages, tools, params, stream=False)
        resp = client.chat.completions.create(**kwargs)
        usage = None
        if getattr(resp, "usage", None):
            usage = ModelUsage(
                input_tokens=resp.usage.prompt_tokens or 0,
                output_tokens=resp.usage.completion_tokens or 0,
                total_tokens=resp.usage.total_tokens or 0,
            )
        output = self._to_output(resp.choices[0].message)
        output.usage = usage
        return output

    def stream(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]],
        params: Dict[str, Any],
    ) -> Iterator[ModelStreamChunk]:
        client = self._get_client(params)
        kwargs = self._build_request_kwargs(messages, tools, params, stream=True)
        try:
            kwargs["stream_options"] = {"include_usage": True}
        except Exception:  # ignored when older SDK versions do not support it
            pass

        stream_resp = client.chat.completions.create(**kwargs)

        # tool-call delta aggregation (OpenAI streams split by index)
        pending: Dict[int, Dict[str, Any]] = {}
        finish_reason = ""
        for chunk in stream_resp:
            if self._check_cancel(params):
                return
            if not chunk.choices:
                usage = getattr(chunk, "usage", None)
                if usage:
                    yield ModelStreamChunk(
                        usage=ModelUsage(
                            input_tokens=usage.prompt_tokens or 0,
                            output_tokens=usage.completion_tokens or 0,
                            total_tokens=usage.total_tokens or 0,
                        )
                    )
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta is None:
                continue
            # chain-of-thought deltas: DeepSeek V4 (reasoning_content) / OpenAI reasoning series (reasoning)
            # transported as a separate field; even an empty string records has_reasoning,
            # used for the verbatim echo decision in tool-call turns.
            reasoning, has_reasoning = _extract_reasoning(delta)
            if has_reasoning or reasoning:
                yield ModelStreamChunk(reasoning=reasoning, has_reasoning=has_reasoning)
            if getattr(delta, "content", None):
                yield ModelStreamChunk(delta_content=delta.content)
            if getattr(delta, "tool_calls", None):
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    slot = pending.setdefault(idx, {"id": "", "name": "", "args_parts": []})
                    if getattr(tc_delta, "id", None):
                        slot["id"] = tc_delta.id
                    if getattr(tc_delta.function, "name", None):
                        slot["name"] = tc_delta.function.name
                    if getattr(tc_delta.function, "arguments", None):
                        slot["args_parts"].append(tc_delta.function.arguments)
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason

        # stream end: emit complete tool calls
        for idx in sorted(pending):
            slot = pending[idx]
            try:
                arguments = json.loads("".join(slot["args_parts"]) or "{}")
            except json.JSONDecodeError:
                arguments = {}
            yield ModelStreamChunk(
                tool_call_delta=ToolCallSpec(
                    id=slot["id"] or f"call_{idx}",
                    name=slot["name"] or "",
                    arguments=arguments,
                )
            )
        yield ModelStreamChunk(finish_reason=finish_reason or ("tool_calls" if pending else "stop"))
