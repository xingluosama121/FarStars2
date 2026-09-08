# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Frontend package: console / headless / web and any custom frontend.

Frontends are the implementation family of the frontend slot; all satisfy the same Frontend protocol.
Switching frontend = switching one slot address, zero changes to core code.
"""

from norpagent.frontends.base import Frontend
from norpagent.frontends.console import ConsoleFrontend
from norpagent.frontends.headless import HeadlessFrontend
from norpagent.frontends.web import WebFrontend

__all__ = [
    "Frontend",
    "ConsoleFrontend",
    "HeadlessFrontend",
    "WebFrontend",
]
