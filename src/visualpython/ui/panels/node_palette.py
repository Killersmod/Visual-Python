"""
Node palette widget for discovering and adding nodes to the canvas.

This module provides a side panel that displays all available node types
organized by category, allowing users to drag nodes onto the canvas.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QMimeData, pyqtSignal, QSize
from PyQt6.QtGui import QDrag, QColor, QPainter, QPixmap, QFont, QAction
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLineEdit,
    QLabel,
    QAbstractItemView,
    QHeaderView,
    QMenu,
)

if TYPE_CHECKING:
    from PyQt6.QtGui import QMouseEvent, QContextMenuEvent
    from visualpython.nodes.registry import NodeTypeInfo


# MIME type for node drag and drop
NODE_MIME_TYPE = "application/x-visualpython-node-type"


class NodePaletteItem(QTreeWidgetItem):
    """
    A tree widget item representing a draggable node type.

    Attributes:
        node_type: The type identifier of the node.
        node_info: Full information about the node type.
    """

    def __init__(
        self,
        parent: QTreeWidgetItem,
        node_info: NodeTypeInfo,
    ) -> None:
        """
        Initialize a node palette item.

        Args:
            parent: The parent tree item (category).
            node_info: Information about the node type.
        """
        super().__init__(parent)
        self.node_type = node_info.node_type
        self.node_info = node_info

        # Set display text
        self.setText(0, node_info.name)
        self.setToolTip(0, node_info.description or f"Create a {node_info.name} node")

        # Set item flags to enable dragging
        self.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )


class NodePaletteTree(QTreeWidget):
    """
    Tree widget that displays available node types with drag support.

    Signals:
        node_double_clicked: Emitted when a node type is double-clicked.
        node_context_menu_requested: Emitted when context menu is requested on a node item.
            Parameters: node_type (str), node_info (NodeTypeInfo), menu (QMenu)
        edit_node_definition_requested: Emitted when "Edit Node Definition" is clicked for Code nodes.
            Parameters: node_type (str), node_info (NodeTypeInfo)
    """

    node_double_clicked = pyqtSignal(str)  # node_type
    node_context_menu_requested = pyqtSignal(str, object, object)  # node_type, node_info, menu
    edit_node_definition_requested = pyqtSignal(str, object)  # node_type, node_info

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the node palette tree."""
        super().__init__(parent)
        self._setup_tree()
        self._drag_start_position = None

    def _setup_tree(self) -> None:
        """Configure tree widget settings."""
        # Single column for node names
        self.setColumnCount(1)
        self.setHeaderHidden(True)

        # Enable drag operations
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

        # Selection behavior
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        # Expand/collapse behavior
        self.setAnimated(True)
        self.setIndentation(20)

        # Style
        self.setAlternatingRowColors(False)

        # Connect double-click signal
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click on items."""
        if isinstance(item, NodePaletteItem):
            self.node_double_clicked.emit(item.node_type)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Record position for drag detection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Start drag if mouse moved enough after press."""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start_position is None:
            return

        # Check if we've moved enough for a drag
        distance = (event.position().toPoint() - self._drag_start_position).manhattanLength()
        if distance < 10:  # Minimum drag distance
            return

        # Get the item being dragged
        item = self.currentItem()
        if not isinstance(item, NodePaletteItem):
            return

        # Start the drag
        self._start_drag(item)

    def _start_drag(self, item: NodePaletteItem) -> None:
        """
        Start a drag operation for a node palette item.

        Args:
            item: The node palette item being dragged.
        """
        # Create MIME data with the node type
        mime_data = QMimeData()
        mime_data.setData(NODE_MIME_TYPE, item.node_type.encode("utf-8"))

        # Create drag object
        drag = QDrag(self)
        drag.setMimeData(mime_data)

        # Create a pixmap for the drag preview
        pixmap = self._create_drag_pixmap(item)
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        # Execute the drag
        drag.exec(Qt.DropAction.CopyAction)

        # Reset drag start position
        self._drag_start_position = None

    def _create_drag_pixmap(self, item: NodePaletteItem) -> QPixmap:
        """
        Create a pixmap for the drag preview.

        Args:
            item: The node palette item being dragged.

        Returns:
            A pixmap showing the node being dragged.
        """
        # Create pixmap with node info
        width = 140
        height = 40
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded rectangle with node color
        color = QColor(item.node_info.color)
        painter.setBrush(color)
        painter.setPen(color.darker(120))
        painter.drawRoundedRect(2, 2, width - 4, height - 4, 6, 6)

        # Draw text
        painter.setPen(Qt.GlobalColor.white)
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, item.node_info.name)

        painter.end()
        return pixmap

    def contextMenuEvent(self, event: "QContextMenuEvent") -> None:
        """
        Handle right-click context menu events on node items.

        Shows a context menu with actions based on the clicked node type.
        For Code nodes, adds an "Edit Node Definition" action that allows
        users to edit the default code template for new Code nodes.
        Emits node_context_menu_requested signal to allow external handlers
        to add additional actions to the menu.

        Args:
            event: The context menu event.
        """
        # Get the item at the click position
        item = self.itemAt(event.pos())

        # Only show context menu for NodePaletteItem (not category headers)
        if not isinstance(item, NodePaletteItem):
            return

        # Create the context menu
        menu = QMenu(self)

        # Add "Edit Node Definition" action for Code nodes
        if item.node_type == "code":
            edit_action = QAction("Edit Node Definition", self)
            edit_action.setToolTip(
                "Edit the default Python code template for new Code nodes"
            )
            edit_action.triggered.connect(
                lambda: self.edit_node_definition_requested.emit(
                    item.node_type,
                    item.node_info,
                )
            )
            menu.addAction(edit_action)

        # Emit signal to allow external handlers to add additional actions
        self.node_context_menu_requested.emit(
            item.node_type,
            item.node_info,
            menu,
        )

        # Show the menu if it has actions
        if not menu.isEmpty():
            menu.exec(event.globalPos())


class NodePaletteWidget(QWidget):
    """
    Side panel widget displaying available node types for drag-and-drop.

    The NodePaletteWidget provides a searchable, categorized view of all
    available node types. Users can drag nodes from this palette onto
    the canvas to create new node instances.

    Signals:
        node_create_requested: Emitted when a node should be created
                               (e.g., double-click). Parameter is node_type.
        node_context_menu_requested: Emitted when context menu is requested on a node item.
            Parameters: node_type (str), node_info (NodeTypeInfo), menu (QMenu)
        edit_node_definition_requested: Emitted when "Edit Node Definition" is clicked for Code nodes.
            Parameters: node_type (str), node_info (NodeTypeInfo)
    """

    node_create_requested = pyqtSignal(str)  # node_type
    node_context_menu_requested = pyqtSignal(str, object, object)  # node_type, node_info, menu
    edit_node_definition_requested = pyqtSignal(str, object)  # node_type, node_info

    # Class-level storage for the default Code node template
    # This template is used when creating new Code nodes from the palette
    _default_code_template: str = ""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the node palette widget."""
        super().__init__(parent)
        self._setup_ui()
        self._populate_nodes()
        # Connect internal handler for edit node definition
        self._tree.edit_node_definition_requested.connect(
            self._on_edit_node_definition_requested
        )

    def _setup_ui(self) -> None:
        """Set up the widget's UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Nodes")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Search box
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search nodes...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_box)

        # Node tree
        self._tree = NodePaletteTree()
        self._tree.node_double_clicked.connect(self._on_node_double_clicked)
        self._tree.node_context_menu_requested.connect(self.node_context_menu_requested)
        # Note: edit_node_definition_requested is connected in __init__ to the internal handler
        # which shows the dialog and then emits the widget's signal for external handlers
        layout.addWidget(self._tree)

        # Set minimum size
        self.setMinimumWidth(180)

    def _populate_nodes(self) -> None:
        """Populate the tree with available node types."""
        from visualpython.nodes.registry import get_node_registry

        # Get registry and ensure default nodes are registered
        registry = get_node_registry()
        registry.register_default_nodes()

        # Clear existing items
        self._tree.clear()

        # Add nodes by category
        self._category_items: dict[str, QTreeWidgetItem] = {}

        for category, node_infos in registry.get_node_types_by_category().items():
            # Create category item
            category_item = QTreeWidgetItem(self._tree)
            category_item.setText(0, category)
            category_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
            )
            # Style the category header
            font = category_item.font(0)
            font.setBold(True)
            category_item.setFont(0, font)

            self._category_items[category] = category_item

            # Add node items under this category
            for node_info in node_infos:
                NodePaletteItem(category_item, node_info)

            # Expand all categories by default
            category_item.setExpanded(True)

    def _on_search_changed(self, text: str) -> None:
        """
        Filter nodes based on search text.

        Args:
            text: The search text to filter by.
        """
        search_lower = text.lower().strip()

        # Iterate through all items
        for i in range(self._tree.topLevelItemCount()):
            category_item = self._tree.topLevelItem(i)
            if category_item is None:
                continue

            # Track if any child is visible
            has_visible_child = False

            for j in range(category_item.childCount()):
                child = category_item.child(j)
                if not isinstance(child, NodePaletteItem):
                    continue

                # Check if the node matches the search
                matches = (
                    not search_lower
                    or search_lower in child.node_info.name.lower()
                    or search_lower in child.node_info.node_type.lower()
                    or search_lower in (child.node_info.description or "").lower()
                )

                child.setHidden(not matches)
                if matches:
                    has_visible_child = True

            # Hide category if no visible children
            category_item.setHidden(not has_visible_child)

            # Expand category when searching
            if search_lower and has_visible_child:
                category_item.setExpanded(True)

    def _on_node_double_clicked(self, node_type: str) -> None:
        """
        Handle double-click on a node item.

        Args:
            node_type: The type of node that was double-clicked.
        """
        self.node_create_requested.emit(node_type)

    def refresh(self) -> None:
        """Refresh the node list from the registry."""
        self._populate_nodes()
        # Reapply any active search filter
        self._on_search_changed(self._search_box.text())

    def clear_search(self) -> None:
        """Clear the search filter."""
        self._search_box.clear()

    def expand_all(self) -> None:
        """Expand all category items."""
        self._tree.expandAll()

    def collapse_all(self) -> None:
        """Collapse all category items."""
        self._tree.collapseAll()

    def _on_edit_node_definition_requested(
        self, node_type: str, node_info: "NodeTypeInfo"
    ) -> None:
        """
        Handle request to edit the default code template for Code nodes.

        Opens a modal code editor dialog with the current default template.
        If the user saves changes, updates the class-level default template
        that is used when creating new Code nodes.

        Args:
            node_type: The node type identifier (should be "code").
            node_info: Information about the node type.
        """
        if node_type != "code":
            # Only Code nodes support editing the default template
            return

        from visualpython.ui.dialogs.code_edit_dialog import CodeEditDialog

        # Get the current default template
        current_template = NodePaletteWidget._default_code_template

        # Open the code edit dialog
        accepted, new_template = CodeEditDialog.edit_code(
            parent=self,
            title="Edit Code Node Default Template",
            initial_code=current_template,
        )

        if accepted:
            # Update the class-level default template
            NodePaletteWidget._default_code_template = new_template

        # Also emit the signal for any external handlers that want to be notified
        self.edit_node_definition_requested.emit(node_type, node_info)

    @classmethod
    def get_default_code_template(cls) -> str:
        """
        Get the current default code template for new Code nodes.

        Returns:
            The default Python code template string.
        """
        return cls._default_code_template

    @classmethod
    def set_default_code_template(cls, template: str) -> None:
        """
        Set the default code template for new Code nodes.

        Args:
            template: The Python code template to use for new Code nodes.
        """
        cls._default_code_template = template
