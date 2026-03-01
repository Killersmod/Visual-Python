"""
Output capture utilities for capturing stdout and stderr during script execution.

This module provides classes for redirecting and capturing stdout/stderr output
from executed Python code, enabling the output to be displayed in the UI console.
"""

from __future__ import annotations

import sys
from io import StringIO
from typing import Callable, Optional, TextIO


class OutputCapture:
    """
    Context manager for capturing stdout and stderr output.

    This class redirects stdout and stderr to internal buffers and optionally
    calls callback functions when output is written. This enables real-time
    streaming of output to a UI console.

    Example:
        >>> def on_stdout(text):
        ...     print(f"Captured: {text}", file=sys.__stdout__)
        >>> with OutputCapture(on_stdout=on_stdout) as capture:
        ...     print("Hello, World!")
        Captured: Hello, World!

        >>> capture.stdout_content
        'Hello, World!\\n'
    """

    def __init__(
        self,
        on_stdout: Optional[Callable[[str], None]] = None,
        on_stderr: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize the output capture.

        Args:
            on_stdout: Optional callback called when stdout output is written.
            on_stderr: Optional callback called when stderr output is written.
        """
        self._on_stdout = on_stdout
        self._on_stderr = on_stderr
        self._stdout_buffer = StringIO()
        self._stderr_buffer = StringIO()
        self._original_stdout: Optional[TextIO] = None
        self._original_stderr: Optional[TextIO] = None
        self._stdout_wrapper: Optional[_StreamWrapper] = None
        self._stderr_wrapper: Optional[_StreamWrapper] = None

    def __enter__(self) -> "OutputCapture":
        """Start capturing output."""
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr

        self._stdout_wrapper = _StreamWrapper(
            self._stdout_buffer,
            self._on_stdout,
        )
        self._stderr_wrapper = _StreamWrapper(
            self._stderr_buffer,
            self._on_stderr,
        )

        sys.stdout = self._stdout_wrapper  # type: ignore
        sys.stderr = self._stderr_wrapper  # type: ignore

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop capturing and restore original streams."""
        if self._original_stdout is not None:
            sys.stdout = self._original_stdout
        if self._original_stderr is not None:
            sys.stderr = self._original_stderr

    @property
    def stdout_content(self) -> str:
        """Get all captured stdout content."""
        return self._stdout_buffer.getvalue()

    @property
    def stderr_content(self) -> str:
        """Get all captured stderr content."""
        return self._stderr_buffer.getvalue()

    def clear(self) -> None:
        """Clear the captured content."""
        self._stdout_buffer.truncate(0)
        self._stdout_buffer.seek(0)
        self._stderr_buffer.truncate(0)
        self._stderr_buffer.seek(0)


class _StreamWrapper:
    """
    A wrapper around a stream that also calls a callback on write.

    This class wraps a StringIO buffer and calls an optional callback
    whenever data is written, enabling real-time streaming of output.
    """

    def __init__(
        self,
        buffer: StringIO,
        callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize the stream wrapper.

        Args:
            buffer: The StringIO buffer to write to.
            callback: Optional callback called with each write.
        """
        self._buffer = buffer
        self._callback = callback

    def write(self, text: str) -> int:
        """
        Write text to the buffer and call the callback.

        Args:
            text: The text to write.

        Returns:
            The number of characters written.
        """
        # Write to buffer
        result = self._buffer.write(text)

        # Call callback if provided and text is not empty
        if self._callback and text:
            self._callback(text)

        return result

    def flush(self) -> None:
        """Flush the buffer (no-op for StringIO but required for stream interface)."""
        self._buffer.flush()

    def fileno(self) -> int:
        """Return file descriptor (raises error as StringIO doesn't have one)."""
        raise OSError("StringIO stream has no file descriptor")

    @property
    def encoding(self) -> str:
        """Return the encoding (utf-8 for compatibility)."""
        return "utf-8"

    def isatty(self) -> bool:
        """Return False as this is not a TTY."""
        return False


class OutputCaptureManager:
    """
    Manager for output capture that can be used across multiple executions.

    This provides a higher-level interface for capturing output with
    callbacks, suitable for integration with UI components.
    """

    def __init__(self) -> None:
        """Initialize the output capture manager."""
        self._stdout_callback: Optional[Callable[[str], None]] = None
        self._stderr_callback: Optional[Callable[[str], None]] = None
        self._capture: Optional[OutputCapture] = None

    def set_stdout_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """
        Set the callback for stdout output.

        Args:
            callback: The callback function, or None to disable.
        """
        self._stdout_callback = callback

    def set_stderr_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """
        Set the callback for stderr output.

        Args:
            callback: The callback function, or None to disable.
        """
        self._stderr_callback = callback

    def start_capture(self) -> None:
        """Start capturing output."""
        if self._capture is not None:
            self.stop_capture()

        self._capture = OutputCapture(
            on_stdout=self._stdout_callback,
            on_stderr=self._stderr_callback,
        )
        self._capture.__enter__()

    def stop_capture(self) -> tuple[str, str]:
        """
        Stop capturing and return captured content.

        Returns:
            Tuple of (stdout_content, stderr_content).
        """
        if self._capture is None:
            return "", ""

        stdout = self._capture.stdout_content
        stderr = self._capture.stderr_content
        self._capture.__exit__(None, None, None)
        self._capture = None

        return stdout, stderr

    @property
    def is_capturing(self) -> bool:
        """Check if currently capturing output."""
        return self._capture is not None
