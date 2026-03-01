"""
Variable inspector panel for inspecting runtime state during paused execution.

This module provides an advanced panel widget that displays all global variables
and their values when execution is paused (at breakpoints or during step-through),
enabling deep inspection of runtime state for debugging purposes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QSplitter,
    QTextEdit,
    QFrame,
    QGroupBox,
)

from visualpython.variables.global_store import GlobalVariableStore
from visualpython.execution.state_manager import ExecutionState, ExecutionStateManager
from visualpython.execution.context import NodeExecutionRecord
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class VariableInspectorWidget(QWidget):
    """
    Advanced panel widget for inspecting variables during paused execution.

    The VariableInspectorWidget provides detailed inspection of runtime state
    when execution is paused at a breakpoint or during step-through debugging.
    It displays:
    - All global variables with their names, types, and values
    - Expandable tree view for complex data structures (lists, dicts, objects)
    - Detailed value preview for selected variables
    - Current execution context information (paused node, execution path)

    This differs from the basic VariablePanelWidget by providing:
    - Hierarchical view for nested data structures
    - Detailed value inspection pane
    - Execution context information
    - Optimized for debugging use cases

    Signals:
        variable_selected: Emitted when a variable is selected (name, value).
        refresh_requested: Emitted when user requests a manual refresh.
    """

    variable_selected = pyqtSignal(str, object)  # name, value
    refresh_requested = pyqtSignal()

    # Constants for display
    MAX_VALUE_PREVIEW_LENGTH = 200
    MAX_INLINE_VALUE_LENGTH = 80
    MAX_DETAIL_LENGTH = 10000
    MAX_CHILDREN = 100  # Max children to show for containers

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
        Initialize the variable inspector widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._store = GlobalVariableStore.get_instance()
        self._execution_state_manager: Optional[ExecutionStateManager] = None
        self._current_paused_node_id: Optional[str] = None
        self._current_paused_node_name: Optional[str] = None
        self._is_paused = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget's UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with title and controls
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        header_label = QLabel("Variable Inspector")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)

        # Status indicator
        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        header_layout.addWidget(self._status_label)

        header_layout.addStretch()

        # Refresh button
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.setMaximumWidth(60)
        self._refresh_button.setToolTip("Refresh variable list")
        self._refresh_button.clicked.connect(self.refresh)
        header_layout.addWidget(self._refresh_button)

        # Expand all button
        self._expand_all_button = QPushButton("Expand")
        self._expand_all_button.setMaximumWidth(60)
        self._expand_all_button.setToolTip("Expand all items")
        self._expand_all_button.clicked.connect(self._expand_all)
        header_layout.addWidget(self._expand_all_button)

        # Collapse all button
        self._collapse_all_button = QPushButton("Collapse")
        self._collapse_all_button.setMaximumWidth(60)
        self._collapse_all_button.setToolTip("Collapse all items")
        self._collapse_all_button.clicked.connect(self._collapse_all)
        header_layout.addWidget(self._collapse_all_button)

        layout.addLayout(header_layout)

        # Execution context info (shown when paused)
        self._context_group = QGroupBox("Execution Context")
        self._context_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """)
        context_layout = QVBoxLayout(self._context_group)
        context_layout.setContentsMargins(8, 4, 8, 4)
        context_layout.setSpacing(2)

        self._paused_node_label = QLabel("Paused at: -")
        self._paused_node_label.setStyleSheet("color: #DCDCAA; font-size: 11px;")
        context_layout.addWidget(self._paused_node_label)

        self._execution_state_label = QLabel("State: Idle")
        self._execution_state_label.setStyleSheet("color: #888; font-size: 11px;")
        context_layout.addWidget(self._execution_state_label)

        self._context_group.hide()  # Hidden until paused
        layout.addWidget(self._context_group)

        # Create splitter for tree and detail view
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # Variables tree widget
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Type", "Value"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemExpanded.connect(self._on_item_expanded)

        # Configure header
        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        # Set column widths
        self._tree.setColumnWidth(0, 150)  # Name column
        self._tree.setColumnWidth(1, 80)   # Type column

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
            QTreeWidget::branch {
                background-color: #1E1E1E;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                image: url(none);
                border-image: none;
            }
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                image: url(none);
                border-image: none;
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

        tree_layout.addWidget(self._tree)
        splitter.addWidget(tree_container)

        # Detail view for selected variable
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(4)

        detail_header = QLabel("Value Details")
        detail_header.setStyleSheet("font-weight: bold; font-size: 11px; color: #888;")
        detail_layout.addWidget(detail_header)

        self._detail_view = QTextEdit()
        self._detail_view.setReadOnly(True)
        self._detail_view.setFont(font)
        self._detail_view.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self._detail_view.setPlaceholderText("Select a variable to see its full value...")
        self._detail_view.setMinimumHeight(100)
        self._detail_view.setMaximumHeight(200)
        detail_layout.addWidget(self._detail_view)

        splitter.addWidget(detail_container)

        # Set splitter proportions
        splitter.setSizes([300, 150])

        layout.addWidget(splitter, 1)

        # Empty state label
        self._empty_label = QLabel("No variables to inspect\n\nVariables will appear here when execution is paused")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888; font-style: italic; padding: 20px;")
        self._empty_label.setWordWrap(True)
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

        # Set minimum size
        self.setMinimumWidth(250)
        self.setMinimumHeight(200)

    def connect_to_state_manager(self, manager: ExecutionStateManager) -> None:
        """
        Connect to an execution state manager to receive state updates.

        Args:
            manager: The ExecutionStateManager to connect to.
        """
        self._execution_state_manager = manager

        # Connect signals
        manager.state_changed.connect(self._on_state_changed)
        manager.step_paused.connect(self._on_step_paused)
        manager.execution_started.connect(self._on_execution_started)
        manager.execution_finished.connect(self._on_execution_finished)

    def _on_state_changed(self, state: ExecutionState) -> None:
        """
        Handle execution state changes.

        Args:
            state: The new execution state.
        """
        state_names = {
            ExecutionState.IDLE: "Idle",
            ExecutionState.RUNNING: "Running",
            ExecutionState.PAUSED: "Paused",
            ExecutionState.ERROR: "Error",
        }
        state_name = state_names.get(state, "Unknown")
        self._execution_state_label.setText(f"State: {state_name}")

        if state == ExecutionState.PAUSED:
            self._is_paused = True
            self._status_label.setText("Paused - Inspecting")
            self._status_label.setStyleSheet("color: #DCDCAA; font-size: 11px;")
            self._context_group.show()
            self.refresh()
        elif state == ExecutionState.RUNNING:
            self._is_paused = False
            self._status_label.setText("Running...")
            self._status_label.setStyleSheet("color: #4EC9B0; font-size: 11px;")
            self._context_group.show()
        elif state == ExecutionState.IDLE:
            self._is_paused = False
            self._status_label.setText("Ready")
            self._status_label.setStyleSheet("color: #888; font-size: 11px;")
            self._context_group.hide()
            self._current_paused_node_id = None
            self._current_paused_node_name = None
            self._paused_node_label.setText("Paused at: -")
        elif state == ExecutionState.ERROR:
            self._is_paused = False
            self._status_label.setText("Error")
            self._status_label.setStyleSheet("color: #F44747; font-size: 11px;")
            self.refresh()  # Show variables at error state

    def _on_step_paused(self, node_id: str, node_name: str) -> None:
        """
        Handle step pause events when execution pauses at a node.

        Args:
            node_id: ID of the node where execution paused.
            node_name: Name of the node.
        """
        self._current_paused_node_id = node_id
        self._current_paused_node_name = node_name
        self._paused_node_label.setText(f"Paused at: {node_name}")
        self._paused_node_label.setStyleSheet("color: #DCDCAA; font-size: 11px; font-weight: bold;")
        self.refresh()

    def _on_execution_started(self) -> None:
        """Handle execution start event."""
        self._status_label.setText("Running...")
        self._status_label.setStyleSheet("color: #4EC9B0; font-size: 11px;")
        self._context_group.show()
        # Clear the tree but keep detail view content
        self._tree.clear()

    def _on_execution_finished(self, success: bool) -> None:
        """
        Handle execution finish event.

        Args:
            success: Whether execution completed successfully.
        """
        if success:
            self._status_label.setText("Completed")
            self._status_label.setStyleSheet("color: #4EC9B0; font-size: 11px;")
        else:
            self._status_label.setText("Failed")
            self._status_label.setStyleSheet("color: #F44747; font-size: 11px;")
        # Refresh to show final state
        self.refresh()

    def _format_value(self, value: Any, max_length: int = 80) -> str:
        """
        Format a value for display, truncating if necessary.

        Args:
            value: The value to format.
            max_length: Maximum characters to display.

        Returns:
            A formatted string representation of the value.
        """
        try:
            if isinstance(value, str):
                formatted = repr(value)
            elif isinstance(value, (list, dict, tuple, set)):
                formatted = repr(value)
            else:
                formatted = str(value)

            # Truncate long values
            if len(formatted) > max_length:
                formatted = formatted[:max_length - 3] + "..."

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

    def _is_expandable(self, value: Any) -> bool:
        """
        Check if a value can be expanded to show children.

        Args:
            value: The value to check.

        Returns:
            True if the value has children that can be displayed.
        """
        if isinstance(value, (dict, list, tuple, set)):
            return len(value) > 0
        if hasattr(value, "__dict__") and not isinstance(value, type):
            return len(value.__dict__) > 0
        return False

    def _create_tree_item(
        self,
        name: str,
        value: Any,
        parent: Optional[QTreeWidgetItem] = None,
    ) -> QTreeWidgetItem:
        """
        Create a tree item for a variable or child value.

        Args:
            name: Display name for the item.
            value: The value to display.
            parent: Optional parent tree item.

        Returns:
            The created QTreeWidgetItem.
        """
        type_name = self._get_type_name(value)
        formatted_value = self._format_value(value, self.MAX_INLINE_VALUE_LENGTH)

        if parent:
            item = QTreeWidgetItem(parent, [name, type_name, formatted_value])
        else:
            item = QTreeWidgetItem([name, type_name, formatted_value])

        # Store the actual value for selection and expansion
        item.setData(0, Qt.ItemDataRole.UserRole, value)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, name)  # Store the name

        # Set tooltip with more info
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

        # Add placeholder child if expandable (for lazy loading)
        if self._is_expandable(value):
            # Add a placeholder that will be replaced when expanded
            placeholder = QTreeWidgetItem(item, ["<loading...>", "", ""])
            placeholder.setData(0, Qt.ItemDataRole.UserRole, "__placeholder__")

        return item

    def _populate_children(self, item: QTreeWidgetItem) -> None:
        """
        Populate children for an expanded tree item.

        Args:
            item: The tree item to populate children for.
        """
        value = item.data(0, Qt.ItemDataRole.UserRole)

        # Remove placeholder
        while item.childCount() > 0:
            item.removeChild(item.child(0))

        # Add children based on type
        children_added = 0

        if isinstance(value, dict):
            for key, val in value.items():
                if children_added >= self.MAX_CHILDREN:
                    more_item = QTreeWidgetItem(
                        item, [f"... ({len(value) - children_added} more)", "", ""]
                    )
                    more_item.setForeground(0, QColor("#888"))
                    break
                key_str = repr(key) if not isinstance(key, str) else key
                self._create_tree_item(f"[{key_str}]", val, item)
                children_added += 1

        elif isinstance(value, (list, tuple)):
            for idx, val in enumerate(value):
                if children_added >= self.MAX_CHILDREN:
                    more_item = QTreeWidgetItem(
                        item, [f"... ({len(value) - children_added} more)", "", ""]
                    )
                    more_item.setForeground(0, QColor("#888"))
                    break
                self._create_tree_item(f"[{idx}]", val, item)
                children_added += 1

        elif isinstance(value, set):
            for idx, val in enumerate(value):
                if children_added >= self.MAX_CHILDREN:
                    more_item = QTreeWidgetItem(
                        item, [f"... ({len(value) - children_added} more)", "", ""]
                    )
                    more_item.setForeground(0, QColor("#888"))
                    break
                self._create_tree_item(f"<{idx}>", val, item)
                children_added += 1

        elif hasattr(value, "__dict__"):
            for attr_name, attr_value in value.__dict__.items():
                if children_added >= self.MAX_CHILDREN:
                    more_item = QTreeWidgetItem(
                        item, [f"... ({len(value.__dict__) - children_added} more)", "", ""]
                    )
                    more_item.setForeground(0, QColor("#888"))
                    break
                self._create_tree_item(f".{attr_name}", attr_value, item)
                children_added += 1

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """
        Handle tree item expansion to load children.

        Args:
            item: The expanded tree item.
        """
        # Check if it has the placeholder child
        if item.childCount() == 1:
            child = item.child(0)
            if child and child.data(0, Qt.ItemDataRole.UserRole) == "__placeholder__":
                self._populate_children(item)

    @pyqtSlot()
    def refresh(self) -> None:
        """Refresh the variable list from the GlobalVariableStore."""
        # Preserve expansion state
        expanded_items = set()
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item and item.isExpanded():
                expanded_items.add(item.text(0))

        # Clear current items
        self._tree.clear()

        # Get all variables
        variables = self._store.list_all()
        count = len(variables)

        if count == 0:
            self._tree.hide()
            self._empty_label.show()
            self._detail_view.clear()
            return

        self._empty_label.hide()
        self._tree.show()

        # Add each variable
        for name, value in sorted(variables.items()):
            item = self._create_tree_item(name, value)
            self._tree.addTopLevelItem(item)

            # Restore expansion state
            if name in expanded_items:
                item.setExpanded(True)

    def _on_selection_changed(self) -> None:
        """Handle variable selection change."""
        selected_items = self._tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            value = item.data(0, Qt.ItemDataRole.UserRole)
            name = item.data(0, Qt.ItemDataRole.UserRole + 1)

            # Update detail view with full value
            try:
                if isinstance(value, str):
                    # Show strings with proper formatting
                    detail_text = f'"{value}"'
                else:
                    # Use pprint for complex objects
                    import pprint
                    detail_text = pprint.pformat(value, indent=2, width=80)

                if len(detail_text) > self.MAX_DETAIL_LENGTH:
                    detail_text = detail_text[:self.MAX_DETAIL_LENGTH] + "\n\n... (truncated)"

                self._detail_view.setPlainText(detail_text)
            except Exception as e:
                self._detail_view.setPlainText(f"<error displaying value: {e}>")

            # Emit signal
            if name:
                self.variable_selected.emit(name, value)
        else:
            self._detail_view.clear()

    def _expand_all(self) -> None:
        """Expand all tree items."""
        self._tree.expandAll()

    def _collapse_all(self) -> None:
        """Collapse all tree items."""
        self._tree.collapseAll()

    def get_selected_variable(self) -> Optional[tuple[str, Any]]:
        """
        Get the currently selected variable.

        Returns:
            A tuple of (name, value) or None if nothing is selected.
        """
        selected_items = self._tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            value = item.data(0, Qt.ItemDataRole.UserRole)
            if name:
                return (name, value)
        return None

    @property
    def is_paused(self) -> bool:
        """Check if execution is currently paused."""
        return self._is_paused

    @property
    def current_paused_node_id(self) -> Optional[str]:
        """Get the ID of the node where execution is paused."""
        return self._current_paused_node_id

    @property
    def current_paused_node_name(self) -> Optional[str]:
        """Get the name of the node where execution is paused."""
        return self._current_paused_node_name
