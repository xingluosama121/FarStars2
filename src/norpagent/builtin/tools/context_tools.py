# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Context management tools: context_add / context_search / context_list / context_delete.

Lets the Agent write intermediate conclusions, external materials and code
snippets from long-run tasks into a searchable context store, reusable across
sessions and tasks — solving the "limited context window" problem:

- context_add: write one context entry (with source and optional metadata);
- context_search: BM25 relevance retrieval (mixed Chinese/English tokenization);
- context_list / context_delete: browse and clean up.

The component is accessed via ``ctx.context_store`` (injected by the runtime when
the preset declares ``components={"context_store": "fts5"}``; tools return a clear
error when it is not assembled).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from norpagent.protocols.tool import Tool, ToolResult


def _store(ctx: Any) -> Optional[Any]:
    return getattr(ctx, "context_store", None)


def _missing() -> ToolResult:
    return ToolResult(
        output=(
            "The current mode has no context store component assembled. "
            "Declare components={\"context_store\": \"fts5\"} in the preset "
            "(the standard preset has it built in), or "
            "registry.register_component(\"context_store\", \"fts5\", ...)."
        ),
        success=False,
        error="context_store component not assembled",
    )


def _fmt_entry(entry: Dict[str, Any]) -> str:
    text = entry.get("text", "")
    if len(text) > 300:
        text = text[:300] + "..."
    head = f"#{entry.get('id')} [{entry.get('source')}] {entry.get('title') or ''}".strip()
    lines = [head, text]
    if entry.get("metadata"):
        lines.append(f"metadata: {json.dumps(entry['metadata'], ensure_ascii=False)}")
    return "\n".join(lines)


class ContextAddTool:
    name = "context_add"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Writes a piece of text into the searchable context store (persistent). "
                    "Suitable for conclusions, external materials, code snippets and memos "
                    "from long-run tasks; retrieve them later with context_search to reuse, "
                    "breaking through the model's context window limit."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The text content to save"},
                        "source": {"type": "string", "description": "Source tag, e.g. task_plan / research / code_snippet (default manual)"},
                        "title": {"type": "string", "description": "Short title for browsing (optional)"},
                        "metadata": {"type": "object", "description": "Extra metadata, e.g. {topic: networking module} (optional)"},
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        store = _store(ctx)
        if store is None:
            return _missing()
        text = str(args.get("text") or "")
        if not text.strip():
            return ToolResult(output="text parameter is empty.", success=False, error="empty_text")
        try:
            doc_id = store.add(
                text=text,
                source=str(args.get("source") or "manual"),
                title=str(args.get("title") or ""),
                metadata=args.get("metadata") if isinstance(args.get("metadata"), dict) else None,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"write failed: {exc}", success=False, error=str(exc))
        return ToolResult(output=f"saved to the context store, entry id={doc_id}. Use context_search to retrieve.")


class ContextSearchTool:
    name = "context_search"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Full-text relevance search in the context store (BM25 ranking, "
                    "mixed Chinese/English tokenization). Suitable for finding materials, "
                    "conclusions and code snippets previously saved with context_add."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Keywords or a natural-language description"},
                        "top_k": {"type": "integer", "description": "Number of results (default 5, max 50)"},
                        "source": {"type": "string", "description": "Filter by source (optional)"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        store = _store(ctx)
        if store is None:
            return _missing()
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult(output="query parameter is empty.", success=False, error="empty_query")
        try:
            results = store.search(
                query,
                top_k=int(args.get("top_k") or 5),
                source=str(args.get("source") or "") or None,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"search failed: {exc}", success=False, error=str(exc))
        if not results:
            return ToolResult(output=f"no content found for \"{query}\".")
        lines = ["[context search results]", "", f"query: {query}", f"hits: {len(results)}", ""]
        for i, entry in enumerate(results, 1):
            lines.append(f"── {i}. (score={entry['score']}) ──")
            lines.append(_fmt_entry(entry))
            lines.append("")
        return ToolResult(output="\n".join(lines).rstrip())


class ContextListTool:
    name = "context_list"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Lists entries in the context store (newest first by write time); filterable by source.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Filter by source (optional)"},
                        "limit": {"type": "integer", "description": "Max entries to return (default 20, max 200)"},
                    },
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        store = _store(ctx)
        if store is None:
            return _missing()
        try:
            entries = store.list(
                source=str(args.get("source") or "") or None,
                limit=int(args.get("limit") or 20),
            )
            stats = store.stats()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"read failed: {exc}", success=False, error=str(exc))
        lines = [
            "[context store]", "",
            f"total entries: {stats.get('total', '?')}",
            f"source distribution: {json.dumps(stats.get('sources', {}), ensure_ascii=False)}",
            "",
        ]
        if not entries:
            lines.append("(empty)")
        for entry in entries:
            lines.append(_fmt_entry(entry))
            lines.append("")
        return ToolResult(output="\n".join(lines).rstrip())


class ContextDeleteTool:
    name = "context_delete"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Deletes one record from the context store by entry id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "Entry id (returned by context_list / context_search)"},
                    },
                    "required": ["id"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        store = _store(ctx)
        if store is None:
            return _missing()
        try:
            doc_id = int(args.get("id"))
        except (TypeError, ValueError):
            return ToolResult(output="id parameter is invalid.", success=False, error="bad_id")
        try:
            ok = store.delete(doc_id)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"delete failed: {exc}", success=False, error=str(exc))
        if not ok:
            return ToolResult(output=f"entry id={doc_id} does not exist.", success=False, error="not_found")
        return ToolResult(output=f"deleted entry id={doc_id}.")
