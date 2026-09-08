# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Built-in tool set.

P1: echo / get_time / run_python (PTC prototype).
P2: file_read / file_write / file_list / file_delete (workspace safety constraints),
    file_surgeon (surgical line-level edits, streaming) / search_in_file
    (in-file keyword search with line numbers and context),
    exec_cmd (sandbox protocol), web_search / web_fetch / web_extract_links
    (SSRF protection + usable with zero dependencies).
P3: context_add / context_search / context_list / context_delete (context management),
    project_status (project management),
    task_submit / task_list / task_status / task_cancel (long-running task cooperation).
"""

from norpagent.builtin.tools.echo import EchoTool
from norpagent.builtin.tools.clock import GetTimeTool
from norpagent.builtin.tools.run_python import RunPythonTool
from norpagent.builtin.tools.file_io import (
    FileReadTool,
    FileWriteTool,
    FileListTool,
    FileDeleteTool,
)
from norpagent.builtin.tools.file_surgeon import FileSurgeonTool
from norpagent.builtin.tools.search_in_file import SearchInFileTool
from norpagent.builtin.tools.exec_cmd import ExecCmdTool
from norpagent.builtin.tools.web import (
    WebSearchTool,
    WebFetchTool,
    WebExtractLinksTool,
    is_private_url,
)
from norpagent.builtin.tools.context_tools import (
    ContextAddTool,
    ContextSearchTool,
    ContextListTool,
    ContextDeleteTool,
)
from norpagent.builtin.tools.project_tools import ProjectStatusTool
from norpagent.builtin.tools.task_tools import (
    TaskSubmitTool,
    TaskListTool,
    TaskStatusTool,
    TaskCancelTool,
)

__all__ = [
    "EchoTool",
    "GetTimeTool",
    "RunPythonTool",
    "FileReadTool",
    "FileWriteTool",
    "FileListTool",
    "FileDeleteTool",
    "FileSurgeonTool",
    "SearchInFileTool",
    "ExecCmdTool",
    "WebSearchTool",
    "WebFetchTool",
    "WebExtractLinksTool",
    "is_private_url",
    "ContextAddTool",
    "ContextSearchTool",
    "ContextListTool",
    "ContextDeleteTool",
    "ProjectStatusTool",
    "TaskSubmitTool",
    "TaskListTool",
    "TaskStatusTool",
    "TaskCancelTool",
]
