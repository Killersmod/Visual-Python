"""
Variable panel for displaying global variables with their values and types.

This module provides a panel widget that displays all global variables
from the GlobalVariableStore, showing their names, current values, and
Python types. It provides visibility into shared state during execution.
"""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QAbstractItemView,
)

from visualpython.variables.global_store import GlobalVariableStore
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class VariablePanelWidget(QWidget):
    """
    Panel widget for displaying global variables.

    The VariablePanelWidget displays all variables stored in the
    GlobalVariableStore, showing:
    - Variable name
    - Variable type (e.g., int, str, list)
    - Current value (with truncation for long values)

    The panel can be refreshed manually or automatically after
    script execution completes.

    Signals:
        variable_selected: Emitted when a variable is selected.
                          Parameters: (name: str, value: Any)
        cleared: Emitted when the store is cleared.
    """

    variable_selected = pyqtSignal(str, object)  # name, value
    cleared = pyqtSignal()
    save_requested = pyqtSignal()  # Request to save variables
    load_requested = pyqtSignal()  # Request to load variables

    # Constants for display
    MAX_VALUE_LENGTH = 100  # Maximum characters to display for a value
    REFRESH_INTERVAL_MS = 500  # Auto-refresh interval during execution

    # Color scheme for different types
    TYPE_COLORS = {
        "int": QColor("#B5CEA8"),      # Light green for numbers
        "float": QColor("#B5CEA8"),
        "str": QColor("#CE9178"),       # Orange for strings
        "bool": QColor("#569CD6"),      # Blue for booleans
        "list": QColor("#DCDCAA"),      # Yellow for collections
        "dict": QColor("#DCDCAA"),
        "tuple": QColor("#DCDCAA"),
        "set": QColor("#DCDCAA"),
        "NoneType": QColor("#808080"),  # Gray for None
        "default": QColor("#D4D4D4"),   # Light gray default
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the variable panel widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._store = GlobalVariableStore.get_instance()
        self._auto_refresh_enabled = False
        self._refresh_timer: Optional[QTimer] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget's UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with title and buttons
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        header_label = QLabel("Variables")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)

        # Variable count label
        self._count_label = QLabel("(0)")
        self._count_label.setStyleSheet("color: #888; font-size: 11px;")
        header_layout.addWidget(self._count_label)

        header_layout.addStretch()

        # Save button
        self._save_button = QPushButton("Save")
        self._save_button.setMaximumWidth(50)
        self._save_button.setToolTip("Save variables to file")
        self._save_button.clicked.connect(self._on_save_clicked)
        header_layout.addWidget(self._save_button)

        # Load button
        self._load_button = QPushButton("Load")
        self._load_button.setMaximumWidth(50)
        self._load_button.setToolTip("Load variables from file")
        self._load_button.clicked.connect(self._on_load_clicked)
        header_layout.addWidget(self._load_button)

        # Refresh button
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.setMaximumWidth(60)
        self._refresh_button.setToolTip("Refresh variable list")
        self._refresh_button.clicked.connect(self.refresh)
        header_layout.addWidget(self._refresh_button)

        # Clear button
        self._clear_button = QPushButton("Clear")
        self._clear_button.setMaximumWidth(60)
        self._clear_button.setToolTip("Clear all variables")
        self._clear_button.clicked.connect(self._on_clear_clicked)
        header_layout.addWidget(self._clear_button)

        layout.addLayout(header_layout)

        # Tree widget for displaying variables
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Type", "Value"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Configure header
        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        # Set column widths
        self._tree.setColumnWidth(0, 100)  # Name column
        self._tree.setColumnWidth(1, 60)   # Type column

        # Set up monospace font for values
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._tree.setFont(font)

        # Style the tree widget
        self._tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
            }
            QTreeWidget::item {
                padding: 4px 2px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
            }
            QTreeWidget::item:hover {
                background-color: #2A2D2E;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: #D4D4D4;
                padding: 4px 8px;
                border: none;
                border-right: 1px solid #3C3C3C;
                border-bottom: 1px solid #3C3C3C;
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

        layout.addWidget(self._tree)

        # Empty state label
        self._empty_label = QLabel("No variables defined")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888; font-style: italic; padding: 20px;")
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

        # Set minimum size
        self.setMinimumWidth(200)
        self.setMinimumHeight(150)

    def _format_value(self, value: Any) -> str:
        """
        Format a value for display, truncating if necessary.

        Args:
            value: The value to format.

        Returns:
            A formatted string representation of the value.
        """
        try:
            if isinstance(value, str):
                # Show strings with quotes
                formatted = repr(value)
            elif isinstance(value, (list, dict, tuple, set)):
                # Show collections with their type and length
                formatted = repr(value)
            else:
                formatted = str(value)

            # Truncate long values
            if len(formatted) > self.MAX_VALUE_LENGTH:
                formatted = formatted[:self.MAX_VALUE_LENGTH - 3] + "..."

            # Replace newlines for single-line display
            formatted = formatted.replace("\n", "\\n")

            return formatted
        except Exception:
            logger.debug("Error formatting variable value", exc_info=True)
            return "<error displaying value>"

    def _get_type_name(self, value: Any) -> str:
        """
        Get a human-readable type name for a value.

        Args:
            value: The value to get the type of.

        Returns:
            The type name as a string.
        """
        return type(value).__name__

    def _get_type_color(self, type_name: str) -> QColor:
        """
        Get the display color for a type.

        Args:
            type_name: The type name.

        Returns:
            The color for displaying that type.
        """
        return self.TYPE_COLORS.get(type_name, self.TYPE_COLORS["default"])

    @pyqtSlot()
    def refresh(self) -> None:
        """Refresh the variable list from the GlobalVariableStore."""
        # Clear current items
        self._tree.clear()

        # Get all variables
        variables = self._store.list_all()
        count = len(variables)

        # Update count label
        self._count_label.setText(f"({count})")

        if count == 0:
            self._tree.hide()
            self._empty_label.show()
            return

        self._empty_label.hide()
        self._tree.show()

        # Add each variable
        for name, value in sorted(variables.items()):
            type_name = self._get_type_name(value)
            formatted_value = self._format_value(value)

            item = QTreeWidgetItem([name, type_name, formatted_value])

            # Store the actual value for selection
            item.setData(0, Qt.ItemDataRole.UserRole, value)

            # Set tooltip with full value
            try:
                full_value = repr(value)
                if len(full_value) > 500:
                    full_value = full_value[:500] + "..."
                item.setToolTip(2, full_value)
            except Exception:
                item.setToolTip(2, "<error displaying value>")

            # Color the type column
            type_color = self._get_type_color(type_name)
            item.setForeground(1, type_color)

            self._tree.addTopLevelItem(item)

    def _on_selection_changed(self) -> None:
        """Handle variable selection change."""
        selected_items = self._tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            name = item.text(0)
            value = item.data(0, Qt.ItemDataRole.UserRole)
            self.variable_selected.emit(name, value)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """
        Handle double-click on a variable item.

        Currently just selects the item, but could be extended to
        open a detailed view or editor.

        Args:
            item: The clicked item.
            column: The clicked column.
        """
        name = item.text(0)
        value = item.data(0, Qt.ItemDataRole.UserRole)
        self.variable_selected.emit(name, value)

    def _on_clear_clicked(self) -> None:
        """Handle clear button click."""
        self._store.clear()
        self.refresh()
        self.cleared.emit()

    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        self.save_requested.emit()

    def _on_load_clicked(self) -> None:
        """Handle load button click."""
        self.load_requested.emit()

    def start_auto_refresh(self) -> None:
        """Start automatic refresh during execution."""
        if self._refresh_timer is None:
            self._refresh_timer = QTimer(self)
            self._refresh_timer.timeout.connect(self.refresh)

        self._auto_refresh_enabled = True
        self._refresh_timer.start(self.REFRESH_INTERVAL_MS)

    def stop_auto_refresh(self) -> None:
        """Stop automatic refresh."""
        self._auto_refresh_enabled = False
        if self._refresh_timer is not None:
            self._refresh_timer.stop()

    @pyqtSlot()
    def execution_started(self) -> None:
        """Called when script execution starts."""
        self.start_auto_refresh()

    @pyqtSlot()
    def execution_finished(self) -> None:
        """Called when script execution finishes."""
        self.stop_auto_refresh()
        # Do a final refresh to show final state
        self.refresh()

    def get_selected_variable(self) -> Optional[tuple[str, Any]]:
        """
        Get the currently selected variable.

        Returns:
            A tuple of (name, value) or None if nothing is selected.
        """
        selected_items = self._tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            name = item.text(0)
            value = item.data(0, Qt.ItemDataRole.UserRole)
            return (name, value)
        return None

    def set_store(self, store: GlobalVariableStore) -> None:
        """
        Set the variable store to display.

        Args:
            store: The GlobalVariableStore instance to use.
        """
        self._store = store
        self.refresh()


class VariableAndDependencyContainer(QWidget):
    """
    Container widget that wraps VariablePanelWidget and DependencyPanelWidget
    in a QTabWidget for display inside a single QDockWidget.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        from PyQt6.QtWidgets import QTabWidget
        from visualpython.ui.panels.dependency_panel import DependencyPanelWidget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_widget = QTabWidget()

        # Tab 0: Variables (existing panel)
        self._variable_panel = VariablePanelWidget()
        self._tab_widget.addTab(self._variable_panel, "Variables")

        # Tab 1: Dependencies (new panel)
        self._dependency_panel = DependencyPanelWidget()
        self._tab_widget.addTab(self._dependency_panel, "Dependencies")

        # Style the tab bar to match dark theme
        self._tab_widget.setStyleSheet("""
            QTabBar::tab {
                background-color: #2D2D2D;
                color: #D4D4D4;
                padding: 6px 12px;
                border: 1px solid #3C3C3C;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1E1E1E;
                border-bottom: 2px solid #569CD6;
            }
            QTabBar::tab:hover:!selected {
                background-color: #2A2D2E;
            }
            QTabWidget::pane {
                border: 1px solid #3C3C3C;
                background-color: #1E1E1E;
            }
        """)

        layout.addWidget(self._tab_widget)

    @property
    def variable_panel(self) -> VariablePanelWidget:
        """Get the variable panel widget."""
        return self._variable_panel

    @property
    def dependency_panel(self) -> "DependencyPanelWidget":
        """Get the dependency panel widget."""
        return self._dependency_panel
