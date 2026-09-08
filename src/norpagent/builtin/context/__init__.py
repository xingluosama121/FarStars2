# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Context management component package: searchable knowledge base for long contexts.

- ``FTS5ContextStore``: SQLite FTS5 implementation (zero dependencies, default component name "fts5");
- replacement works like any component: implement the same interface then
  ``registry.register_component("context_store", "my implementation", factory)``.

Companion tools live in norpagent.builtin.tools.context_tools.

Embedded optimization (v0.9): the FTS5 implementation is lazily imported on
demand — importing this package alone does not pull in the sqlite3 dependency
(friendly for embedded / diskless environments).
"""

from typing import Any

_LAZY_EXPORTS = {
    "FTS5ContextStore": (
        "norpagent.builtin.context.fts5", "FTS5ContextStore"),
}


def __getattr__(name: str) -> Any:
    entry = _LAZY_EXPORTS.get(name)
    if entry is None:
        raise AttributeError(
            f"module 'norpagent.builtin.context' has no attribute '{name}'")
    import importlib

    module = importlib.import_module(entry[0])
    value = getattr(module, entry[1])
    globals()[name] = value
    return value


__all__ = ["FTS5ContextStore"]
