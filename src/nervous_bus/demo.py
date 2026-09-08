# -*- coding: utf-8 -*-
"""nervous_bus.demo — v1.0.7 兼容 shim（实现已内核化迁入 norpagent.cnb.demo）。"""

from norpagent.cnb.demo import *  # noqa: F401,F403
from norpagent.cnb import demo as _impl

if __name__ == "__main__":
    _impl.main()
