# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Console frontend: the command-line interactive REPL shell (used when the frontend is explicitly specified).

Two run modes, auto-detected:

- **script mode** (default): a background thread loops reading stdin, submitting
  each line to the engine for execution;
- **REPL synchronous mode** (when np() is called inside the Python interactive
  interpreter): the input loop runs directly in the calling thread (the main
  thread); np() blocks until the user exits.

  The interactive interpreter's (>>> REPL) main thread also reads stdin; a
  background thread would compete with the REPL for input (keystrokes randomly
  stolen by either input side); and Ctrl+C is only delivered to the main thread,
  so a background input() thread could never exit — the process also spams
  "signal wakeup fd / WinError 10038" noise during cleanup. Synchronous mode
  eliminates all of these problems.

Built-in commands:

    /exit  /quit  exit  quit  exit()  quit()   exit the application
    /help                                       show help
    /reset                                      start a new session

Event rendering is delegated to ConsoleUI (replaceable wholesale via the ui slot).
Combined with the main thread's polling loop (see norpagent.runtime), this forms
the command-line shape of an agent application:

    import norpagent as np
    np(frontend="norpagent.frontends.console:ConsoleFrontend")
    while True:
        if np.stop():
            break
"""

from __future__ import annotations

import sys
import threading
from typing import Any, Optional

from norpagent.frontends.base import Frontend


class ConsoleFrontend:
    """stdin input → engine execution → event rendering (explicitly specified; web is the default frontend)."""

    frontend_id = "console"

    #: exit commands (all equivalent to /exit)
    EXIT_COMMANDS = ("/exit", "/quit", "exit", "quit", "exit()", "quit()")

    def __init__(
        self,
        renderer: Optional[Any] = None,
        stream: Any = None,
        **kwargs: Any,
    ) -> None:
        # renderer: event renderer (UIAdapter); defaults to ConsoleUI.
        # stream: render output stream (defaults to sys.stdout).
        self.renderer = renderer
        self._stream = stream
        self._engine: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._running_inline = False
        self._session_id: Optional[str] = None
        self._stop = threading.Event()

    # ── Frontend protocol ────────────────────────────────

    def attach(self, engine: Any) -> None:
        self._engine = engine
        # prefer reusing the engine agent runtime's renderer (avoid rendering the same event twice)
        agent = getattr(engine, "agent", None)
        existing = getattr(agent, "ui", None)
        if existing is not None and hasattr(existing, "on_event"):
            self.renderer = existing
            return
        if self.renderer is None:
            from norpagent.builtin.ui.console import ConsoleUI

            self.renderer = ConsoleUI(stream=self._stream, verbose=True)
        engine.subscribe_ui(self.renderer)

    def start(self) -> None:
        if self._thread is not None or self._running_inline:
            return
        self._stop.clear()
        if self._interactive_shell():
            # REPL synchronous mode: the main thread exclusively owns stdin; the
            # input loop runs in place. np() blocks until the user exits
            # (/exit, exit(), Ctrl+C, EOF).
            self._running_inline = True
            try:
                self._input_loop()
            finally:
                self._running_inline = False
            return
        self._thread = threading.Thread(
            target=self._input_loop, name="norpagent-frontend-console",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # a thread blocked in input() cannot be woken by an event: wait for it to exit on its own.
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def is_alive(self) -> bool:
        return bool(
            self._running_inline
            or (self._thread is not None and self._thread.is_alive())
        )

    # ── mode detection ───────────────────────────────────

    @staticmethod
    def _interactive_shell() -> bool:
        """Whether running inside the Python interactive interpreter (REPL / python -i)."""
        return getattr(sys, "ps1", None) is not None

    # ── input loop ───────────────────────────────────────

    def _input_loop(self) -> None:
        print("norpagent started. Type messages to talk to the Agent; /exit to quit.")
        try:
            while not self._stop.is_set():
                line = self._read_line()
                if line is None:  # EOF (Ctrl+Z) or Ctrl+C: clean exit
                    break
                text = line.strip()
                if not text:
                    continue
                if text in self.EXIT_COMMANDS:
                    print("Goodbye.")
                    break
                if text == "/help":
                    print("  /exit /quit exit quit exit() quit()   exit the application\n"
                          "  /reset                               start a new session")
                    continue
                if text == "/reset":
                    self._session_id = None
                    print("new session started")
                    continue
                engine = self._engine
                if engine is None:
                    continue
                try:
                    result = engine.submit(text, session_id=self._session_id)
                except KeyboardInterrupt:
                    # interrupted by Ctrl+C during task execution: exit cleanly too
                    print("\ntask interrupted (Ctrl+C); exiting.")
                    break
                except RuntimeError:
                    break  # engine already stopped
                self._session_id = getattr(result, "session_id", None)
        finally:
            # input loop ending = user exit = request stopping the whole application
            engine = self._engine
            if engine is not None:
                engine.request_stop()

    def _read_line(self) -> Optional[str]:
        """Read one line of input (None on EOF / Ctrl+C / stdin closed)."""
        try:
            return input("> ")
        except KeyboardInterrupt:
            print("\nCtrl+C received; exiting.")
            return None
        except EOFError:
            print()
            return None
        except (OSError, ValueError):
            # stdin closed (e.g. during host-process exit): treated as EOF
            return None


__all__ = ["ConsoleFrontend"]
