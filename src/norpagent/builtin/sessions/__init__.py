# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Built-in session management.

- memory: in-process storage (demo / benchmark / embedded);
- sqlite: SQLite persistent storage (default ~/.norpagent/sessions.db),
  zero third-party dependencies, thread-safe; same replacement approach as memory.

Embedded optimization (v0.9): the SQLite implementation is lazily imported on
demand — importing this package alone (or only the memory submodule) does not
pull in the sqlite3 dependency.
"""

from typing import Any

from norpagent.builtin.sessions.memory import MemorySessionManager

_LAZY_EXPORTS = {
    "SQLiteSessionManager": (
        "norpagent.builtin.sessions.sqlite", "SQLiteSessionManager"),
}


def __getattr__(name: str) -> Any:
    entry = _LAZY_EXPORTS.get(name)
    if entry is None:
        raise AttributeError(
            f"module 'norpagent.builtin.sessions' has no attribute '{name}'")
    import importlib

    module = importlib.import_module(entry[0])
    value = getattr(module, entry[1])
    globals()[name] = value
    return value


__all__ = ["MemorySessionManager", "SQLiteSessionManager"]
