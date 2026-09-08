# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Run context: the full environment tools and hooks can access during one task execution.

``RunContext`` is passed to outer components through the ctx parameter of
``tool.run(args, ctx)`` and the ``context`` field in event payloads. It is the
single coupling surface between the agent kernel and outer components: components
depend only on the capabilities the context provides, never on concrete classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:  # type-checking-only references, avoiding circular imports
    from norpagent.kernel.registry import Registry
    from norpagent.protocols.sandbox import Sandbox
    from norpagent.protocols.scheduler import TaskScheduler
    from norpagent.protocols.session import SessionManager
    from norpagent.protocols.ui import UIAdapter


@dataclass
class RunContext:
    """Environment handle of one task run.

    Attributes:
        registry: component registry (can resolve other tools / models)
        session_manager / session_id: session read/write
        sandbox: current task sandbox (command execution, code execution)
        scheduler: task scheduler (can submit subtasks; entry point for multi-agent cooperation)
        ui: UI adapter (ask_user for human interaction)
        components: generic component instances declared by the preset ({kind: instance})
        params: merged result of preset params and task-level params
        task_id: task id
    """

    registry: Any = None
    session_manager: Any = None
    session_id: Optional[str] = None
    sandbox: Any = None
    scheduler: Any = None
    ui: Any = None
    params: Dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    preset_name: str = ""
    components: Dict[str, Any] = field(default_factory=dict)
    # task-level slot injection (3.9): the snapshot layer and raw override dict of
    # submit(slot_overrides=...). Tools and hooks may read this field to know which
    # task-level overrides this task used, but **must not modify** it — the kernel
    # manages the lifecycle of the override layer.
    task_slot_layer: Any = None
    slot_overrides: Dict[str, Any] = field(default_factory=dict)

    def component(self, kind: str, default: Any = None) -> Any:
        """Get a generic component by kind (e.g. "context_store" / "project_manager")."""
        return self.components.get(kind, default)

    @property
    def context_store(self) -> Any:
        """Context store component (used by context_add / context_search tools)."""
        return self.components.get("context_store")

    @property
    def project_manager(self) -> Any:
        """Project management component (used by project_status tool)."""
        return self.components.get("project_manager")

    @property
    def task_store(self) -> Any:
        """Task store component (used by task_* tools; may be None when the persistent scheduler carries its own)."""
        return self.components.get("task_store")

    def ask_user(self, question: str, default: str = "") -> str:
        """Ask the user a question (returns default when the UI provides no interaction)."""
        if self.ui is not None:
            try:
                return self.ui.ask_user(question, default)
            except Exception:
                return default
        return default
