"""
Output console panel for displaying print statements and stdout from scripts.

This module provides a console panel widget that captures and displays
print statements, stdout/stderr output, and execution information from
running visual Python scripts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QLabel,
)

if TYPE_CHECKING:
    pass


class OutputConsoleWidget(QWidget):
    """
    Console panel widget for displaying script output.

    The OutputConsoleWidget provides a read-only text display that shows:
    - Print statements from executed code
    - stdout and stderr output
    - Execution status messages
    - Error messages with syntax highlighting

    Signals:
        cleared: Emitted when the console is cleared.
    """

    cleared = pyqtSignal()

    # Color scheme for different output types
    COLOR_STDOUT = QColor("#D4D4D4")  # Light gray for normal output
    COLOR_STDERR = QColor("#F44747")  # Red for errors
    COLOR_INFO = QColor("#569CD6")    # Blue for info messages
    COLOR_SUCCESS = QColor("#4EC9B0") # Teal for success messages
    COLOR_WARNING = QColor("#DCDCAA") # Yellow for warnings
    COLOR_TIMESTAMP = QColor("#808080") # Gray for timestamps

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the output console widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget's UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with title and clear button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        header_label = QLabel("Output")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Clear button
        self._clear_button = QPushButton("Clear")
        self._clear_button.setMaximumWidth(60)
        self._clear_button.setToolTip("Clear console output")
        self._clear_button.clicked.connect(self.clear)
        header_layout.addWidget(self._clear_button)

        layout.addLayout(header_layout)

        # Console text display
        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        # Set up monospace font for console
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._console.setFont(font)

        # Dark theme styling for the console
        self._console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                padding: 4px;
            }
            QScrollBar:vertical {
                background-color: #1E1E1E;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #5A5A5A;
                min-height: 20px;
                border-radius: 6px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #787878;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        layout.addWidget(self._console)

        # Set minimum size
        self.setMinimumHeight(150)

    def _format_timestamp(self) -> str:
        """
        Get a formatted timestamp string.

        Returns:
            Formatted timestamp string.
        """
        return datetime.now().strftime("[%H:%M:%S]")

    def _append_text(self, text: str, color: QColor, include_timestamp: bool = False) -> None:
        """
        Append text to the console with the specified color.

        Args:
            text: The text to append.
            color: The color for the text.
            include_timestamp: Whether to include a timestamp prefix.
        """
        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        if include_timestamp:
            # Add timestamp with its own color
            timestamp_format = QTextCharFormat()
            timestamp_format.setForeground(self.COLOR_TIMESTAMP)
            cursor.setCharFormat(timestamp_format)
            cursor.insertText(f"{self._format_timestamp()} ")

        # Add the main text
        text_format = QTextCharFormat()
        text_format.setForeground(color)
        cursor.setCharFormat(text_format)
        cursor.insertText(text)

        # Ensure newline
        if not text.endswith("\n"):
            cursor.insertText("\n")

        # Scroll to bottom
        self._console.setTextCursor(cursor)
        self._console.ensureCursorVisible()

    @pyqtSlot(str)
    def write_stdout(self, text: str) -> None:
        """
        Write stdout text to the console.

        Args:
            text: The stdout text to display.
        """
        if text.strip():  # Only write non-empty lines
            self._append_text(text.rstrip("\n"), self.COLOR_STDOUT, include_timestamp=False)

    @pyqtSlot(str)
    def write_stderr(self, text: str) -> None:
        """
        Write stderr text to the console (displayed in red).

        Args:
            text: The stderr text to display.
        """
        if text.strip():  # Only write non-empty lines
            self._append_text(text.rstrip("\n"), self.COLOR_STDERR, include_timestamp=False)

    @pyqtSlot(str)
    def write_info(self, message: str) -> None:
        """
        Write an info message to the console.

        Args:
            message: The info message to display.
        """
        self._append_text(message, self.COLOR_INFO, include_timestamp=True)

    @pyqtSlot(str)
    def write_success(self, message: str) -> None:
        """
        Write a success message to the console.

        Args:
            message: The success message to display.
        """
        self._append_text(message, self.COLOR_SUCCESS, include_timestamp=True)

    @pyqtSlot(str)
    def write_warning(self, message: str) -> None:
        """
        Write a warning message to the console.

        Args:
            message: The warning message to display.
        """
        self._append_text(message, self.COLOR_WARNING, include_timestamp=True)

    @pyqtSlot(str)
    def write_error(self, message: str) -> None:
        """
        Write an error message to the console.

        Args:
            message: The error message to display.
        """
        self._append_text(message, self.COLOR_STDERR, include_timestamp=True)

    @pyqtSlot()
    def clear(self) -> None:
        """Clear all console output."""
        self._console.clear()
        self.cleared.emit()

    def get_text(self) -> str:
        """
        Get all text content from the console.

        Returns:
            The full text content of the console.
        """
        return self._console.toPlainText()

    def execution_started(self) -> None:
        """Called when script execution starts."""
        self._append_text("=" * 50, self.COLOR_INFO, include_timestamp=False)
        self.write_info("Execution started")

    def execution_finished(self, success: bool, message: str = "") -> None:
        """
        Called when script execution finishes.

        Args:
            success: Whether execution was successful.
            message: Optional status message.
        """
        if success:
            self.write_success(f"Execution completed{': ' + message if message else ''}")
        else:
            self.write_error(f"Execution failed{': ' + message if message else ''}")
