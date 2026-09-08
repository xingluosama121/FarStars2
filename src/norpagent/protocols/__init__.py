# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Protocol layer: abstract interfaces (Protocols) of all components.

The framework core depends only on the interfaces defined in this package,
never on any concrete implementation. Developers implement these interfaces
to replace any part of an Agent:

- ModelProvider    model (brain)
- Tool             tool (skill)
- SessionManager   session management (memory)
- Sandbox / SandboxProvider  sandbox environment (isolated execution)
- TaskScheduler    task scheduling (orchestration, including future multi-agent)
- UIAdapter        user interface (interaction)
- Plugin           plugin (packaging/distribution unit of tools, may carry lifecycle hooks)
"""

from norpagent.protocols.model import (
    ChatMessage,
    ToolCallSpec,
    ModelUsage,
    ModelOutput,
    ModelStreamChunk,
    ModelProvider,
)
from norpagent.protocols.tool import Tool, ToolResult
from norpagent.protocols.session import Session, SessionManager
from norpagent.protocols.sandbox import Sandbox, SandboxProvider, SandboxResult
from norpagent.protocols.scheduler import AgentTask, TaskResult, TaskScheduler
from norpagent.protocols.ui import UIAdapter
from norpagent.protocols.plugin import Plugin

__all__ = [
    "ChatMessage",
    "ToolCallSpec",
    "ModelUsage",
    "ModelOutput",
    "ModelStreamChunk",
    "ModelProvider",
    "Tool",
    "ToolResult",
    "Session",
    "SessionManager",
    "Sandbox",
    "SandboxProvider",
    "SandboxResult",
    "AgentTask",
    "TaskResult",
    "TaskScheduler",
    "UIAdapter",
    "Plugin",
]
