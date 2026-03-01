"""
Inline error popup for displaying node execution errors.

This module provides a lightweight popup widget that appears when clicking on a
node's error indicator button, showing error details without opening a modal dialog.
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject, QRectF
from PyQt6.QtGui import (
    QColor,
    QPen,
    QPainter,
    QBrush,
    QFont,
    QFontMetrics,
    QPainterPath,
    QCursor,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QApplication,
    QGraphicsProxyWidget,
)

if TYPE_CHECKING:
    from visualpython.execution.error_report import ErrorReport, ErrorCategory
    from visualpython.nodes.models.base_node import BaseNode


class NodeErrorPopupSignals(QObject):
    """Signals for the node error popup widget."""

    # Emitted when the popup requests to navigate to the error details dialog
    details_requested = pyqtSignal(str)  # node_id

    # Emitted when the popup is closed
    closed = pyqtSignal()

    # Emitted when copy to clipboard is requested
    copy_requested = pyqtSignal(str)  # error text


class ErrorEntryWidget(QFrame):
    """
    A single error entry widget for displaying one error in the popup.

    Shows the error category, message, and provides quick actions like
    copy and view details.
    """

    # Category colors matching the application's dark theme
    CATEGORY_COLORS = {
        "SYNTAX": "#F44747",      # Red
        "RUNTIME": "#F44747",     # Red
        "VALIDATION": "#DCDCAA",  # Yellow
        "DATA_FLOW": "#569CD6",   # Blue
        "GRAPH_STRUCTURE": "#CE9178",  # Orange
        "INTERNAL": "#F44747",    # Red
        "UNKNOWN": "#808080",     # Gray
    }

    def __init__(
        self,
        error_report: ErrorReport,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize an error entry widget.

        Args:
            error_report: The error report to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._error_report = error_report
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components for the error entry."""
        self.setObjectName("errorEntry")

        # Get category color
        category_name = self._error_report.category.name
        category_color = self.CATEGORY_COLORS.get(category_name, "#F44747")

        self.setStyleSheet(f"""
            QFrame#errorEntry {{
                background-color: #2D2D2D;
                border-left: 3px solid {category_color};
                border-radius: 4px;
                padding: 4px;
                margin: 2px 0px;
            }}
            QFrame#errorEntry:hover {{
                background-color: #363636;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header row with category badge and exception type
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        # Category badge
        category_label = QLabel(category_name)
        category_label.setStyleSheet(f"""
            QLabel {{
                background-color: {category_color};
                color: #1E1E1E;
                font-size: 9pt;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 3px;
            }}
        """)
        category_label.setFixedHeight(18)
        header_layout.addWidget(category_label)

        # Exception type
        if self._error_report.original_exception_type:
            type_label = QLabel(self._error_report.original_exception_type)
            type_label.setStyleSheet("""
                QLabel {
                    color: #D4D4D4;
                    font-size: 9pt;
                    font-family: Consolas, monospace;
                }
            """)
            header_layout.addWidget(type_label)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Error message
        message_label = QLabel(self._truncate_message(self._error_report.message))
        message_label.setWordWrap(True)
        message_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 10pt;
            }
        """)
        message_label.setToolTip(self._error_report.message)
        layout.addWidget(message_label)

        # Suggestions (if any, show first one)
        if self._error_report.suggestions:
            suggestion = self._error_report.suggestions[0]
            suggestion_label = QLabel(f"Tip: {suggestion}")
            suggestion_label.setWordWrap(True)
            suggestion_label.setStyleSheet("""
                QLabel {
                    color: #4EC9B0;
                    font-size: 9pt;
                    font-style: italic;
                }
            """)
            layout.addWidget(suggestion_label)

    def _truncate_message(self, message: str, max_length: int = 150) -> str:
        """Truncate a message to a maximum length with ellipsis."""
        if len(message) > max_length:
            return message[:max_length - 3] + "..."
        return message

    @property
    def error_report(self) -> ErrorReport:
        """Get the error report for this entry."""
        return self._error_report


class NodeErrorPopup(QFrame):
    """
    Inline popup widget for displaying node execution errors.

    This widget appears near the node when clicking on the error indicator,
    providing a quick view of all errors without opening a modal dialog.
    It supports multiple errors and provides actions for copying and viewing
    full details.

    Attributes:
        MAX_WIDTH: Maximum width of the popup.
        MAX_HEIGHT: Maximum height of the popup.
        ARROW_SIZE: Size of the connection arrow pointing to the node.
    """

    MAX_WIDTH = 350
    MAX_HEIGHT = 300
    MIN_WIDTH = 280
    ARROW_SIZE = 10

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the node error popup.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.signals = NodeErrorPopupSignals()
        self._node_id: Optional[str] = None
        self._errors: List[ErrorReport] = []
        self._auto_close_timer: Optional[QTimer] = None

        self._setup_ui()
        self._setup_style()

    def _setup_ui(self) -> None:
        """Set up the popup's UI components."""
        self.setWindowFlags(
            Qt.WindowType.Popup |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Header with title and close button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self._title_label = QLabel("Execution Errors")
        self._title_label.setStyleSheet("""
            QLabel {
                color: #F44747;
                font-size: 11pt;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        # Close button
        close_button = QPushButton("\u00D7")  # Unicode multiplication sign (X)
        close_button.setFixedSize(20, 20)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #808080;
                font-size: 14pt;
                font-weight: bold;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #3C3C3C;
                color: #FFFFFF;
            }
        """)
        close_button.clicked.connect(self.hide)
        header_layout.addWidget(close_button)

        main_layout.addLayout(header_layout)

        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #3C3C3C;")
        separator.setFixedHeight(1)
        main_layout.addWidget(separator)

        # Scroll area for error entries
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #2D2D2D;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #5A5A5A;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #6A6A6A;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Container for error entries
        self._errors_container = QWidget()
        self._errors_layout = QVBoxLayout(self._errors_container)
        self._errors_layout.setContentsMargins(0, 0, 0, 0)
        self._errors_layout.setSpacing(4)
        self._errors_layout.addStretch()

        scroll_area.setWidget(self._errors_container)
        main_layout.addWidget(scroll_area, 1)

        # Action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        # Copy all button
        copy_button = QPushButton("Copy All")
        copy_button.setStyleSheet("""
            QPushButton {
                background-color: #3C3C3C;
                color: #D4D4D4;
                font-size: 9pt;
                border: 1px solid #5A5A5A;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #4A4A4A;
            }
            QPushButton:pressed {
                background-color: #5A5A5A;
            }
        """)
        copy_button.clicked.connect(self._copy_all_errors)
        actions_layout.addWidget(copy_button)

        actions_layout.addStretch()

        # View details button
        details_button = QPushButton("View Details...")
        details_button.setStyleSheet("""
            QPushButton {
                background-color: #0E639C;
                color: #FFFFFF;
                font-size: 9pt;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #0D5289;
            }
        """)
        details_button.clicked.connect(self._show_details)
        actions_layout.addWidget(details_button)

        main_layout.addLayout(actions_layout)

    def _setup_style(self) -> None:
        """Set up the popup's style."""
        self.setStyleSheet("""
            NodeErrorPopup {
                background-color: #252526;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
            }
        """)
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)
        self.setMaximumHeight(self.MAX_HEIGHT)

    def show_for_node(
        self,
        node: BaseNode,
        anchor_point: QPoint,
    ) -> None:
        """
        Show the popup for a node at the specified anchor point.

        Args:
            node: The node whose errors to display.
            anchor_point: The screen position to anchor the popup to.
        """
        self._node_id = node.id
        self._errors = node.execution_errors

        # Update title with error count
        error_count = len(self._errors)
        if error_count == 1:
            self._title_label.setText("1 Execution Error")
        else:
            self._title_label.setText(f"{error_count} Execution Errors")

        # Clear existing error entries
        self._clear_error_entries()

        # Add error entries
        for error in self._errors:
            entry = ErrorEntryWidget(error, self._errors_container)
            # Insert before the stretch
            self._errors_layout.insertWidget(
                self._errors_layout.count() - 1,
                entry
            )

        # Adjust size based on content
        self.adjustSize()

        # Position the popup near the anchor point
        self._position_popup(anchor_point)

        self.show()
        self.raise_()
        self.activateWindow()

    def _clear_error_entries(self) -> None:
        """Clear all error entry widgets from the container."""
        # Remove all widgets except the stretch at the end
        while self._errors_layout.count() > 1:
            item = self._errors_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _position_popup(self, anchor_point: QPoint) -> None:
        """
        Position the popup near the anchor point.

        The popup is positioned to avoid going off-screen and to appear
        next to the node's error indicator.

        Args:
            anchor_point: The screen position to anchor the popup to.
        """
        # Get screen geometry
        screen = QApplication.screenAt(anchor_point)
        if screen is None:
            screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()

        popup_width = self.sizeHint().width()
        popup_height = self.sizeHint().height()

        # Try to position to the right of the anchor point
        x = anchor_point.x() + 10
        y = anchor_point.y() - popup_height // 2

        # Adjust if going off the right edge
        if x + popup_width > screen_geometry.right():
            # Position to the left of the anchor instead
            x = anchor_point.x() - popup_width - 10

        # Adjust if going off the left edge
        if x < screen_geometry.left():
            x = screen_geometry.left() + 10

        # Adjust if going off the bottom edge
        if y + popup_height > screen_geometry.bottom():
            y = screen_geometry.bottom() - popup_height - 10

        # Adjust if going off the top edge
        if y < screen_geometry.top():
            y = screen_geometry.top() + 10

        self.move(x, y)

    def _copy_all_errors(self) -> None:
        """Copy all error details to the clipboard."""
        if not self._errors:
            return

        lines: List[str] = []
        for i, error in enumerate(self._errors, 1):
            lines.append(f"Error {i}: {error.category.name}")
            if error.original_exception_type:
                lines.append(f"  Type: {error.original_exception_type}")
            lines.append(f"  Message: {error.message}")
            if error.suggestions:
                lines.append(f"  Suggestions:")
                for suggestion in error.suggestions:
                    lines.append(f"    - {suggestion}")
            lines.append("")

        text = "\n".join(lines)

        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            self.signals.copy_requested.emit(text)

    def _show_details(self) -> None:
        """Emit signal to show full error details dialog."""
        if self._node_id:
            self.signals.details_requested.emit(self._node_id)
        self.hide()

    def hideEvent(self, event) -> None:
        """Handle hide event to emit closed signal."""
        super().hideEvent(event)
        self.signals.closed.emit()


class NodeErrorPopupManager:
    """
    Manager for showing error popups for nodes in a graphics view.

    This class handles the creation and positioning of error popups
    when users click on node error indicators in the graphics scene.
    """

    def __init__(self, parent_widget: Optional[QWidget] = None) -> None:
        """
        Initialize the popup manager.

        Args:
            parent_widget: The parent widget (usually the main window or view).
        """
        self._parent_widget = parent_widget
        self._current_popup: Optional[NodeErrorPopup] = None
        self._popup_signals = NodeErrorPopupSignals()

    @property
    def signals(self) -> NodeErrorPopupSignals:
        """Get the signals object for connecting to popup events."""
        return self._popup_signals

    def show_popup_for_node(
        self,
        node: BaseNode,
        screen_position: QPoint,
    ) -> None:
        """
        Show an error popup for the specified node.

        Args:
            node: The node whose errors to display.
            screen_position: The screen position to anchor the popup to.
        """
        if not node.has_execution_errors():
            return

        # Close existing popup if open
        self.close_popup()

        # Create new popup
        self._current_popup = NodeErrorPopup(self._parent_widget)

        # Connect signals
        self._current_popup.signals.details_requested.connect(
            self._popup_signals.details_requested.emit
        )
        self._current_popup.signals.copy_requested.connect(
            self._popup_signals.copy_requested.emit
        )
        self._current_popup.signals.closed.connect(self._on_popup_closed)

        # Show popup
        self._current_popup.show_for_node(node, screen_position)

    def close_popup(self) -> None:
        """Close the current popup if open."""
        if self._current_popup is not None:
            self._current_popup.hide()
            self._current_popup.deleteLater()
            self._current_popup = None

    def _on_popup_closed(self) -> None:
        """Handle popup closed event."""
        self._current_popup = None
        self._popup_signals.closed.emit()

    def is_popup_visible(self) -> bool:
        """Check if a popup is currently visible."""
        return (
            self._current_popup is not None
            and self._current_popup.isVisible()
        )
