"""
Error display dialog for showing execution errors with detailed context.

This module provides a user-friendly dialog for displaying execution errors
with stack traces, node context, and debugging suggestions.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QFrame,
    QWidget,
    QScrollArea,
    QSizePolicy,
)

if TYPE_CHECKING:
    from visualpython.execution.error_report import ErrorReport, ErrorCategory


class CollapsibleSection(QWidget):
    """A collapsible section widget with a toggle button and content area."""

    def __init__(
        self,
        title: str,
        parent: Optional[QWidget] = None,
        initially_expanded: bool = False,
    ) -> None:
        """
        Initialize the collapsible section.

        Args:
            title: The section title.
            parent: Optional parent widget.
            initially_expanded: Whether to start expanded.
        """
        super().__init__(parent)
        self._is_expanded = initially_expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header with toggle button
        self._toggle_button = QPushButton(self._get_toggle_text(title))
        self._toggle_button.setFlat(True)
        self._toggle_button.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 4px 8px;
                font-weight: bold;
                color: #D4D4D4;
                background-color: #2D2D2D;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3C3C3C;
            }
        """)
        self._toggle_button.clicked.connect(self._toggle)
        self._title = title
        layout.addWidget(self._toggle_button)

        # Content area
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 4, 0, 4)
        self._content_layout.setSpacing(4)
        self._content.setVisible(initially_expanded)
        layout.addWidget(self._content)

    def _get_toggle_text(self, title: str) -> str:
        """Get the toggle button text with arrow indicator."""
        arrow = "▼" if self._is_expanded else "▶"
        return f"{arrow} {title}"

    def _toggle(self) -> None:
        """Toggle the expanded state."""
        self._is_expanded = not self._is_expanded
        self._content.setVisible(self._is_expanded)
        self._toggle_button.setText(self._get_toggle_text(self._title))

    def add_widget(self, widget: QWidget) -> None:
        """Add a widget to the content area."""
        self._content_layout.addWidget(widget)

    def set_content_widget(self, widget: QWidget) -> None:
        """Replace content with a single widget."""
        # Clear existing widgets
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._content_layout.addWidget(widget)


class ExecutionErrorDialog(QDialog):
    """
    A dialog for displaying execution errors with detailed context.

    This dialog shows:
    - Error type and category with color-coded header
    - Node context (name, type, position)
    - Error message
    - Collapsible stack trace
    - Execution path
    - Input values
    - Debugging suggestions
    """

    # Color scheme matching the application's dark theme
    COLOR_ERROR = QColor("#F44747")
    COLOR_WARNING = QColor("#DCDCAA")
    COLOR_INFO = QColor("#569CD6")
    COLOR_SUCCESS = QColor("#4EC9B0")
    COLOR_TEXT = QColor("#D4D4D4")
    COLOR_MUTED = QColor("#808080")

    # Category colors
    CATEGORY_COLORS = {
        "SYNTAX": "#F44747",      # Red
        "RUNTIME": "#F44747",     # Red
        "VALIDATION": "#DCDCAA",  # Yellow
        "DATA_FLOW": "#569CD6",   # Blue
        "GRAPH_STRUCTURE": "#CE9178",  # Orange
        "INTERNAL": "#F44747",    # Red
        "UNKNOWN": "#808080",     # Gray
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the error display dialog.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._error_report: Optional[ErrorReport] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog's UI components."""
        self.setWindowTitle("Execution Error")
        self.setMinimumSize(600, 400)
        self.resize(700, 500)
        self.setModal(True)

        # Apply dark theme styling
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QLabel {
                color: #D4D4D4;
            }
            QScrollArea {
                border: none;
                background-color: #1E1E1E;
            }
            QPlainTextEdit {
                background-color: #252526;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 10pt;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Content widget
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(12)

        # Error header section
        self._header_frame = QFrame()
        self._header_frame.setStyleSheet("""
            QFrame {
                background-color: #3C1E1E;
                border: 1px solid #F44747;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        header_layout = QVBoxLayout(self._header_frame)
        header_layout.setContentsMargins(12, 12, 12, 12)
        header_layout.setSpacing(8)

        # Error category label
        self._category_label = QLabel()
        self._category_label.setStyleSheet("""
            QLabel {
                font-size: 11pt;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(self._category_label)

        # Error message
        self._error_message_label = QLabel()
        self._error_message_label.setWordWrap(True)
        self._error_message_label.setStyleSheet("""
            QLabel {
                font-size: 12pt;
                color: #FFFFFF;
            }
        """)
        header_layout.addWidget(self._error_message_label)

        content_layout.addWidget(self._header_frame)

        # Node context section
        self._node_context_section = CollapsibleSection(
            "Node Context", initially_expanded=True
        )
        self._node_info_label = QLabel()
        self._node_info_label.setWordWrap(True)
        self._node_info_label.setStyleSheet("""
            QLabel {
                background-color: #252526;
                padding: 8px;
                border-radius: 4px;
                font-family: Consolas, monospace;
            }
        """)
        self._node_context_section.add_widget(self._node_info_label)
        content_layout.addWidget(self._node_context_section)

        # Stack trace section (collapsible, collapsed by default)
        self._stack_trace_section = CollapsibleSection(
            "Stack Trace", initially_expanded=False
        )
        self._stack_trace_text = QPlainTextEdit()
        self._stack_trace_text.setReadOnly(True)
        self._stack_trace_text.setMinimumHeight(150)
        self._stack_trace_text.setMaximumHeight(300)
        self._stack_trace_section.add_widget(self._stack_trace_text)
        content_layout.addWidget(self._stack_trace_section)

        # Execution path section (collapsible)
        self._execution_path_section = CollapsibleSection(
            "Execution Path", initially_expanded=False
        )
        self._execution_path_label = QLabel()
        self._execution_path_label.setWordWrap(True)
        self._execution_path_label.setStyleSheet("""
            QLabel {
                background-color: #252526;
                padding: 8px;
                border-radius: 4px;
                font-family: Consolas, monospace;
            }
        """)
        self._execution_path_section.add_widget(self._execution_path_label)
        content_layout.addWidget(self._execution_path_section)

        # Input values section (collapsible)
        self._input_values_section = CollapsibleSection(
            "Input Values", initially_expanded=False
        )
        self._input_values_text = QPlainTextEdit()
        self._input_values_text.setReadOnly(True)
        self._input_values_text.setMinimumHeight(80)
        self._input_values_text.setMaximumHeight(150)
        self._input_values_section.add_widget(self._input_values_text)
        content_layout.addWidget(self._input_values_section)

        # Suggestions section
        self._suggestions_section = CollapsibleSection(
            "Suggestions", initially_expanded=True
        )
        self._suggestions_label = QLabel()
        self._suggestions_label.setWordWrap(True)
        self._suggestions_label.setStyleSheet("""
            QLabel {
                background-color: #1E3A2F;
                padding: 8px;
                border-radius: 4px;
                border: 1px solid #4EC9B0;
            }
        """)
        self._suggestions_section.add_widget(self._suggestions_label)
        content_layout.addWidget(self._suggestions_section)

        # Add stretch at the end
        content_layout.addStretch()

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        # Button bar
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Copy to Clipboard button
        copy_button = QPushButton("Copy Details")
        copy_button.setToolTip("Copy error details to clipboard")
        copy_button.setStyleSheet("""
            QPushButton {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #5A5A5A;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #4A4A4A;
            }
            QPushButton:pressed {
                background-color: #5A5A5A;
            }
        """)
        copy_button.clicked.connect(self._copy_to_clipboard)
        button_layout.addWidget(copy_button)

        # OK button
        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #0E639C;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 8px 24px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #0D5289;
            }
        """)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)

        main_layout.addLayout(button_layout)

    def set_error_report(self, error_report: ErrorReport) -> None:
        """
        Set the error report to display.

        Args:
            error_report: The error report containing all error context.
        """
        self._error_report = error_report
        self._update_display()

    def set_error_message(self, message: str, exception_type: str = "Error") -> None:
        """
        Set a simple error message without a full error report.

        Args:
            message: The error message to display.
            exception_type: The type of exception.
        """
        self._error_report = None
        self._category_label.setText(f"⚠ {exception_type}")
        self._category_label.setStyleSheet(f"""
            QLabel {{
                font-size: 11pt;
                font-weight: bold;
                color: {self.CATEGORY_COLORS.get('RUNTIME', '#F44747')};
            }}
        """)
        self._error_message_label.setText(message)

        # Hide sections that require error report
        self._node_context_section.setVisible(False)
        self._stack_trace_section.setVisible(False)
        self._execution_path_section.setVisible(False)
        self._input_values_section.setVisible(False)
        self._suggestions_section.setVisible(False)

    def _update_display(self) -> None:
        """Update the dialog display with the current error report."""
        if not self._error_report:
            return

        report = self._error_report

        # Update category label with color
        category_name = report.category.name
        category_color = self.CATEGORY_COLORS.get(category_name, "#F44747")
        exception_type = report.original_exception_type or "Error"

        self._category_label.setText(f"⚠ {category_name} - {exception_type}")
        self._category_label.setStyleSheet(f"""
            QLabel {{
                font-size: 11pt;
                font-weight: bold;
                color: {category_color};
            }}
        """)

        # Update header frame border color to match category
        self._header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #3C1E1E;
                border: 1px solid {category_color};
                border-radius: 6px;
                padding: 8px;
            }}
        """)

        # Update error message
        self._error_message_label.setText(report.message)

        # Update node context
        if report.location:
            loc = report.location
            node_info = (
                f"<b>Node:</b> {loc.node_name}<br>"
                f"<b>Type:</b> {loc.node_type}<br>"
                f"<b>ID:</b> <code>{loc.node_id}</code><br>"
                f"<b>Position:</b> ({loc.x:.1f}, {loc.y:.1f})"
            )
            self._node_info_label.setText(node_info)
            self._node_context_section.setVisible(True)
        else:
            self._node_context_section.setVisible(False)

        # Update stack trace
        if report.stack_trace:
            self._stack_trace_text.setPlainText(report.stack_trace)
            self._stack_trace_section.setVisible(True)
        else:
            self._stack_trace_section.setVisible(False)

        # Update execution path
        if report.execution_path:
            # Show the path with arrows, limiting to last 10 nodes
            path = report.execution_path[-10:]
            if len(report.execution_path) > 10:
                path_text = f"... ({len(report.execution_path) - 10} more) → " + " → ".join(path)
            else:
                path_text = " → ".join(path)
            self._execution_path_label.setText(path_text)
            self._execution_path_section.setVisible(True)
        else:
            self._execution_path_section.setVisible(False)

        # Update input values
        if report.input_values:
            input_text = ""
            for key, value in report.input_values.items():
                # Truncate long values
                value_str = repr(value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                input_text += f"{key}: {value_str}\n"
            self._input_values_text.setPlainText(input_text.strip())
            self._input_values_section.setVisible(True)
        else:
            self._input_values_section.setVisible(False)

        # Update suggestions
        if report.suggestions:
            suggestions_html = "<ul style='margin: 0; padding-left: 20px;'>"
            for suggestion in report.suggestions:
                suggestions_html += f"<li>{suggestion}</li>"
            suggestions_html += "</ul>"
            self._suggestions_label.setText(suggestions_html)
            self._suggestions_section.setVisible(True)
        else:
            self._suggestions_section.setVisible(False)

    def _copy_to_clipboard(self) -> None:
        """Copy error details to clipboard."""
        from PyQt6.QtWidgets import QApplication

        if self._error_report:
            text = self._error_report.format_user_message()
            if self._error_report.stack_trace:
                text += f"\n\nStack Trace:\n{self._error_report.stack_trace}"
        else:
            text = self._error_message_label.text()

        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    @staticmethod
    def show_error(
        parent: Optional[QWidget],
        error_report: Optional[ErrorReport] = None,
        message: str = "",
        exception_type: str = "Error",
    ) -> None:
        """
        Static method to show an error dialog.

        Args:
            parent: Parent widget for the dialog.
            error_report: Optional error report with full context.
            message: Simple error message (used if error_report is None).
            exception_type: Type of exception (used if error_report is None).
        """
        dialog = ExecutionErrorDialog(parent)
        if error_report:
            dialog.set_error_report(error_report)
        else:
            dialog.set_error_message(message, exception_type)
        dialog.exec()
