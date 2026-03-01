"""
Template browser widget for discovering and using pre-built graph templates.

This module provides a side panel that displays available templates
organized by category, allowing users to create new graphs from templates.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QMimeData, pyqtSignal, QSize
from PyQt6.QtGui import QDrag, QColor, QPainter, QPixmap, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLineEdit,
    QLabel,
    QAbstractItemView,
    QPushButton,
    QTextEdit,
    QSplitter,
    QFrame,
)

if TYPE_CHECKING:
    from PyQt6.QtGui import QMouseEvent
    from visualpython.templates.template import GraphTemplate


# MIME type for template drag and drop
TEMPLATE_MIME_TYPE = "application/x-visualpython-template-id"


class TemplatePaletteItem(QTreeWidgetItem):
    """
    A tree widget item representing a selectable template.

    Attributes:
        template_id: The unique identifier of the template.
        template: Full information about the template.
    """

    def __init__(
        self,
        parent: QTreeWidgetItem,
        template: "GraphTemplate",
    ) -> None:
        """
        Initialize a template palette item.

        Args:
            parent: The parent tree item (category).
            template: The GraphTemplate object.
        """
        super().__init__(parent)
        self.template_id = template.template_id
        self.template = template

        # Set display text
        self.setText(0, template.name)
        self.setToolTip(0, template.preview_description or template.description)

        # Set item flags to enable selection and dragging
        self.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )


class TemplatePaletteTree(QTreeWidget):
    """
    Tree widget that displays available templates with drag support.

    Signals:
        template_selected: Emitted when a template is selected (single click).
        template_double_clicked: Emitted when a template is double-clicked.
    """

    template_selected = pyqtSignal(str)  # template_id
    template_double_clicked = pyqtSignal(str)  # template_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the template palette tree."""
        super().__init__(parent)
        self._setup_tree()
        self._drag_start_position = None

    def _setup_tree(self) -> None:
        """Configure tree widget settings."""
        # Single column for template names
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

        # Connect signals
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click on items."""
        if isinstance(item, TemplatePaletteItem):
            self.template_double_clicked.emit(item.template_id)

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        items = self.selectedItems()
        if items and isinstance(items[0], TemplatePaletteItem):
            self.template_selected.emit(items[0].template_id)

    def mousePressEvent(self, event: "QMouseEvent") -> None:
        """Record position for drag detection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: "QMouseEvent") -> None:
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
        if not isinstance(item, TemplatePaletteItem):
            return

        # Start the drag
        self._start_drag(item)

    def _start_drag(self, item: TemplatePaletteItem) -> None:
        """
        Start a drag operation for a template palette item.

        Args:
            item: The template palette item being dragged.
        """
        # Create MIME data with the template ID
        mime_data = QMimeData()
        mime_data.setData(TEMPLATE_MIME_TYPE, item.template_id.encode("utf-8"))

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

    def _create_drag_pixmap(self, item: TemplatePaletteItem) -> QPixmap:
        """
        Create a pixmap for the drag preview.

        Args:
            item: The template palette item being dragged.

        Returns:
            A pixmap showing the template being dragged.
        """
        # Create pixmap with template info
        width = 160
        height = 40
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded rectangle with a gradient color
        color = QColor("#6366F1")  # Indigo color for templates
        painter.setBrush(color)
        painter.setPen(color.darker(120))
        painter.drawRoundedRect(2, 2, width - 4, height - 4, 6, 6)

        # Draw text
        painter.setPen(Qt.GlobalColor.white)
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, item.template.name)

        painter.end()
        return pixmap


class TemplateBrowserWidget(QWidget):
    """
    Side panel widget displaying available templates for selection.

    The TemplateBrowserWidget provides a searchable, categorized view of all
    available graph templates. Users can select templates to view their details
    and create new graphs from them.

    Signals:
        template_create_requested: Emitted when a template should be instantiated.
                                   Parameter is template_id.
    """

    template_create_requested = pyqtSignal(str)  # template_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the template browser widget."""
        super().__init__(parent)
        self._current_template_id: Optional[str] = None
        self._setup_ui()
        self._populate_templates()

    def _setup_ui(self) -> None:
        """Set up the widget's UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Templates")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Search box
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search templates...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_box)

        # Create splitter for tree and details
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Template tree
        self._tree = TemplatePaletteTree()
        self._tree.template_selected.connect(self._on_template_selected)
        self._tree.template_double_clicked.connect(self._on_template_double_clicked)
        splitter.addWidget(self._tree)

        # Details panel
        details_frame = QFrame()
        details_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(8, 8, 8, 8)
        details_layout.setSpacing(4)

        # Template name label
        self._name_label = QLabel("Select a template")
        self._name_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        self._name_label.setWordWrap(True)
        details_layout.addWidget(self._name_label)

        # Template description
        self._description_text = QTextEdit()
        self._description_text.setReadOnly(True)
        self._description_text.setMaximumHeight(80)
        self._description_text.setPlaceholderText("Template description will appear here...")
        details_layout.addWidget(self._description_text)

        # Difficulty and tags
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #666; font-size: 10px;")
        self._info_label.setWordWrap(True)
        details_layout.addWidget(self._info_label)

        # Create button
        self._create_button = QPushButton("Create from Template")
        self._create_button.setEnabled(False)
        self._create_button.clicked.connect(self._on_create_clicked)
        details_layout.addWidget(self._create_button)

        splitter.addWidget(details_frame)

        # Set splitter sizes
        splitter.setSizes([200, 150])

        layout.addWidget(splitter)

        # Set minimum size
        self.setMinimumWidth(200)

    def _populate_templates(self) -> None:
        """Populate the tree with available templates."""
        from visualpython.templates.registry import get_template_registry

        # Get registry and load default templates
        registry = get_template_registry()
        registry.load_default_templates()

        # Clear existing items
        self._tree.clear()

        # Add templates by category
        self._category_items: dict[str, QTreeWidgetItem] = {}

        for category, templates in registry.get_templates_by_category().items():
            # Create category item
            category_item = QTreeWidgetItem(self._tree)
            category_item.setText(0, category.value)
            category_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            # Style the category header
            font = category_item.font(0)
            font.setBold(True)
            category_item.setFont(0, font)

            self._category_items[category.value] = category_item

            # Add template items under this category
            for template in templates:
                TemplatePaletteItem(category_item, template)

            # Expand all categories by default
            category_item.setExpanded(True)

    def _on_search_changed(self, text: str) -> None:
        """
        Filter templates based on search text.

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
                if not isinstance(child, TemplatePaletteItem):
                    continue

                # Check if the template matches the search
                matches = child.template.matches_search(search_lower) if search_lower else True

                child.setHidden(not matches)
                if matches:
                    has_visible_child = True

            # Hide category if no visible children
            category_item.setHidden(not has_visible_child)

            # Expand category when searching
            if search_lower and has_visible_child:
                category_item.setExpanded(True)

    def _on_template_selected(self, template_id: str) -> None:
        """
        Handle template selection.

        Args:
            template_id: The ID of the selected template.
        """
        from visualpython.templates.registry import get_template_registry

        self._current_template_id = template_id
        registry = get_template_registry()
        template = registry.get_template(template_id)

        if template:
            self._name_label.setText(template.name)
            self._description_text.setText(template.description)
            self._info_label.setText(
                f"Difficulty: {template.difficulty.value.title()} | "
                f"Tags: {', '.join(template.tags) if template.tags else 'None'}"
            )
            self._create_button.setEnabled(True)
        else:
            self._clear_details()

    def _on_template_double_clicked(self, template_id: str) -> None:
        """
        Handle double-click on a template item.

        Args:
            template_id: The ID of the template that was double-clicked.
        """
        self.template_create_requested.emit(template_id)

    def _on_create_clicked(self) -> None:
        """Handle create button click."""
        if self._current_template_id:
            self.template_create_requested.emit(self._current_template_id)

    def _clear_details(self) -> None:
        """Clear the details panel."""
        self._current_template_id = None
        self._name_label.setText("Select a template")
        self._description_text.clear()
        self._info_label.setText("")
        self._create_button.setEnabled(False)

    def refresh(self) -> None:
        """Refresh the template list from the registry."""
        self._populate_templates()
        # Reapply any active search filter
        self._on_search_changed(self._search_box.text())
        self._clear_details()

    def clear_search(self) -> None:
        """Clear the search filter."""
        self._search_box.clear()

    def expand_all(self) -> None:
        """Expand all category items."""
        self._tree.expandAll()

    def collapse_all(self) -> None:
        """Collapse all category items."""
        self._tree.collapseAll()
