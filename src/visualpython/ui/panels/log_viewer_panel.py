"""
Log viewer panel for displaying application logs in the UI.

This module provides a panel widget that captures Python logging output
and displays it with color-coded log levels, replacing the need to
alt-tab to the terminal to view logs.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QObject
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QComboBox,
    QLabel,
)


class QtLogHandler(QObject, logging.Handler):
    """
    A logging handler that emits Qt signals for each log record.

    This bridges Python's logging system into Qt's signal/slot mechanism,
    ensuring thread-safe delivery of log messages to the UI.

    Signals:
        log_record_received: Emitted with (formatted_message, level_name).
    """

    log_record_received = pyqtSignal(str, str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        QObject.__init__(self, parent)
        logging.Handler.__init__(self)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_record_received.emit(msg, record.levelname)
        except Exception:
            self.handleError(record)


class _LevelToggleButton(QPushButton):
    """A toggle button for a single log level with colored indicator."""

    def __init__(self, level_name: str, color: QColor, parent: Optional[QWidget] = None) -> None:
        super().__init__(level_name, parent)
        self._level_name = level_name
        self._color = color
        self.setCheckable(True)
        self.setChecked(True)
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()
        self.toggled.connect(lambda: self._update_style())

    def _update_style(self) -> None:
        """Update the button style based on checked state."""
        hex_color = self._color.name()
        if self.isChecked():
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_color}22;
                    color: {hex_color};
                    border: 1px solid {hex_color};
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {hex_color}44;
                }}
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #2D2D2D;
                    color: #606060;
                    border: 1px solid #3C3C3C;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #383838;
                    color: #808080;
                }
            """)


class LogViewerPanel(QWidget):
    """
    Panel widget for displaying application logs.

    Displays Python logging output with color-coded log levels and
    per-level toggle buttons to show/hide individual levels.

    Signals:
        cleared: Emitted when the log display is cleared.
    """

    cleared = pyqtSignal()

    # Color scheme for log levels
    COLOR_DEBUG = QColor("#808080")     # Gray
    COLOR_INFO = QColor("#569CD6")      # Blue
    COLOR_WARNING = QColor("#DCDCAA")   # Yellow
    COLOR_ERROR = QColor("#F44747")     # Red
    COLOR_CRITICAL = QColor("#FF0000")  # Bright red

    _LEVEL_COLORS: Dict[str, QColor] = {
        "DEBUG": COLOR_DEBUG,
        "INFO": COLOR_INFO,
        "WARNING": COLOR_WARNING,
        "ERROR": COLOR_ERROR,
        "CRITICAL": COLOR_CRITICAL,
    }

    _ORDERED_LEVELS: List[str] = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._handler = QtLogHandler(self)
        self._handler.log_record_received.connect(self._on_log_record)
        # Buffer of all records so we can re-render when filters change
        self._record_buffer: List[Tuple[str, str]] = []
        self._max_buffer = 5000
        # Toggle buttons keyed by level name
        self._level_buttons: Dict[str, _LevelToggleButton] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget's UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header row: title + clear button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        header_label = QLabel("Logs")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Log level dropdown — changes the root logger level at runtime
        level_label = QLabel("Level:")
        level_label.setStyleSheet("font-size: 11px; color: #808080;")
        header_layout.addWidget(level_label)

        self._level_combo = QComboBox()
        self._level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self._level_combo.setCurrentText("DEBUG")
        self._level_combo.setMaximumWidth(110)
        self._level_combo.setToolTip("Set the root logger level — controls what gets logged globally")
        self._level_combo.currentTextChanged.connect(self._on_log_level_changed)
        header_layout.addWidget(self._level_combo)

        # Clear button
        self._clear_button = QPushButton("Clear")
        self._clear_button.setMaximumWidth(60)
        self._clear_button.setToolTip("Clear log output")
        self._clear_button.clicked.connect(self.clear)
        header_layout.addWidget(self._clear_button)

        layout.addLayout(header_layout)

        # Filter row: per-level toggle buttons
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(4)

        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("font-size: 11px; color: #808080;")
        filter_layout.addWidget(filter_label)

        for level_name in self._ORDERED_LEVELS:
            color = self._LEVEL_COLORS[level_name]
            btn = _LevelToggleButton(level_name, color)
            btn.toggled.connect(self._on_filter_changed)
            self._level_buttons[level_name] = btn
            filter_layout.addWidget(btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Log text display
        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._console.setMaximumBlockCount(5000)

        # Monospace font
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._console.setFont(font)

        # Dark theme styling matching OutputConsole
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

        self.setMinimumHeight(150)

    def _is_level_visible(self, level_name: str) -> bool:
        """Check whether a level is currently toggled on."""
        btn = self._level_buttons.get(level_name)
        return btn.isChecked() if btn else True

    def _append_text(self, text: str, color: QColor) -> None:
        """Append colored text to the console and auto-scroll."""
        cursor = self._console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.setCharFormat(fmt)
        cursor.insertText(text)

        if not text.endswith("\n"):
            cursor.insertText("\n")

        self._console.setTextCursor(cursor)
        self._console.ensureCursorVisible()

    def _rerender(self) -> None:
        """Re-render the console from the buffer with current filters applied."""
        self._console.setUpdatesEnabled(False)
        self._console.clear()
        for message, level_name in self._record_buffer:
            if self._is_level_visible(level_name):
                color = self._LEVEL_COLORS.get(level_name, self.COLOR_DEBUG)
                self._append_text(message, color)
        self._console.setUpdatesEnabled(True)

    @pyqtSlot(str, str)
    def _on_log_record(self, message: str, level_name: str) -> None:
        """Handle an incoming log record."""
        # Always buffer the record
        self._record_buffer.append((message, level_name))
        if len(self._record_buffer) > self._max_buffer:
            self._record_buffer = self._record_buffer[-self._max_buffer:]

        # Only display if the level is currently visible
        if self._is_level_visible(level_name):
            color = self._LEVEL_COLORS.get(level_name, self.COLOR_DEBUG)
            self._append_text(message, color)

    @pyqtSlot()
    def _on_filter_changed(self) -> None:
        """Handle any level toggle button change — re-render with new filters."""
        self._rerender()

    @pyqtSlot(str)
    def _on_log_level_changed(self, level_text: str) -> None:
        """Change the root logger level at runtime."""
        level = getattr(logging, level_text, logging.DEBUG)
        logging.getLogger().setLevel(level)

    @pyqtSlot()
    def clear(self) -> None:
        """Clear all log output and the buffer."""
        self._record_buffer.clear()
        self._console.clear()
        self.cleared.emit()

    def get_handler(self) -> QtLogHandler:
        """Return the logging handler for installation on a logger."""
        return self._handler
