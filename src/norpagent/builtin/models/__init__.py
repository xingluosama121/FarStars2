# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Built-in model adapters.

- mock: deterministic scripted model (benchmarks), zero dependencies;
- openai_compat: OpenAI-compatible services (OpenAI / DeepSeek / Qwen / vLLM /
  Ollama, etc.), requires norpagent[openai], SDK lazily loaded;
- anthropic: Claude family, requires norpagent[anthropic], SDK lazily loaded.
"""

from norpagent.builtin.models.mock import MockModelProvider
from norpagent.builtin.models.openai_compat import OpenAICompatProvider
from norpagent.builtin.models.anthropic import AnthropicProvider

__all__ = ["MockModelProvider", "OpenAICompatProvider", "AnthropicProvider"]
