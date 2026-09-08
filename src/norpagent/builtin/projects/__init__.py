# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Project management component package: workspace metadata / scanning / git status.

- ``BasicProjectManager``: JSON metadata + directory scanning (default component name "basic");
- companion tools live in norpagent.builtin.tools.project_tools.
"""

from norpagent.builtin.projects.basic import BasicProjectManager

__all__ = ["BasicProjectManager"]
