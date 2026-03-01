"""
Centralized logging for VisualPython.

This module provides a single logging interface that writes to both an
in-memory ring buffer and to disk (rotating log files + crash log).
Every module should obtain its logger through :func:`get_logger` so that
all output is routed through the same pipeline.

Usage in any module::

    from visualpython.utils.logging import get_logger
    logger = get_logger(__name__)
    logger.info("something happened")

One-time setup in ``__main__``::

    from visualpython.utils.logging import setup_logging, get_log_buffer
    setup_logging()           # call once at startup
    logs = get_log_buffer()   # read the in-memory ring buffer
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Deque, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

_initialized: bool = False

# In-memory ring buffer: stores (formatted_message, level_name) tuples
_memory_buffer: Deque[Tuple[str, str]] = deque(maxlen=10_000)


# ---------------------------------------------------------------------------
# In-memory handler
# ---------------------------------------------------------------------------

class MemoryHandler(logging.Handler):
    """A logging handler that keeps the last *maxlen* formatted records in memory.

    Records are stored as ``(formatted_message, level_name)`` tuples so they
    can be easily consumed by UI components (e.g. the log viewer panel).
    """

    def __init__(self, buffer: Deque[Tuple[str, str]]) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._buffer.append((msg, record.levelname))
        except Exception:
            self.handleError(record)

    @property
    def records(self) -> List[Tuple[str, str]]:
        """Return a snapshot of the buffer as a plain list."""
        return list(self._buffer)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``visualpython`` hierarchy.

    This is a thin convenience wrapper around :func:`logging.getLogger`.
    It guarantees that every logger inherits the handlers configured by
    :func:`setup_logging`.
    """
    return logging.getLogger(name)


def get_log_buffer() -> List[Tuple[str, str]]:
    """Return a snapshot of all in-memory log records.

    Each entry is a ``(formatted_message, level_name)`` tuple.
    """
    return list(_memory_buffer)


def get_memory_handler() -> Optional[MemoryHandler]:
    """Return the singleton :class:`MemoryHandler`, or ``None`` if
    :func:`setup_logging` has not been called yet.
    """
    return _memory_handler


# ---------------------------------------------------------------------------
# One-time setup
# ---------------------------------------------------------------------------

_memory_handler: Optional[MemoryHandler] = None


def setup_logging() -> None:
    """Configure the root logger with disk, stderr, and memory handlers.

    Safe to call more than once – subsequent calls are no-ops.

    Handlers installed:

    * **crash.log** – ``FileHandler`` (overwritten each run)
    * **logs/visualpython_<timestamp>.log** – ``RotatingFileHandler``
      (5 MB per file, 10 backups)
    * **stderr** – ``StreamHandler``
    * **memory** – :class:`MemoryHandler` (in-process ring buffer)
    """
    global _initialized, _memory_handler
    if _initialized:
        return
    _initialized = True

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    crash_log = project_root / "crash.log"

    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    session_log = logs_dir / f"visualpython_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    formatter = logging.Formatter(_LOG_FORMAT)

    # --- disk: crash log (overwrite) ---
    crash_handler = logging.FileHandler(crash_log, mode="w")
    crash_handler.setFormatter(formatter)

    # --- disk: rotating session log ---
    rotating_handler = logging.handlers.RotatingFileHandler(
        session_log, maxBytes=5 * 1024 * 1024, backupCount=10,
    )
    rotating_handler.setFormatter(formatter)

    # --- stderr ---
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)

    # --- memory ring buffer ---
    _memory_handler = MemoryHandler(_memory_buffer)
    _memory_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.DEBUG,
        format=_LOG_FORMAT,
        handlers=[crash_handler, stderr_handler, rotating_handler, _memory_handler],
    )
