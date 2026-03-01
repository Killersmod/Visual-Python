"""
Node group visual widget for the visual programming canvas.

This module provides the QGraphicsItem-based visual representation of node groups,
including the header bar, collapse/expand button, and container boundary.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import (
    QColor,
    QPen,
    QPainter,
    QBrush,
    QFont,
    QFontMetrics,
    QPainterPath,
    QLinearGradient,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsDropShadowEffect,
    QStyleOptionGraphicsItem,
    QWidget,
    QGraphicsSceneMouseEvent,
)

if TYPE_CHECKING:
    from visualpython.nodes.models.node_group import NodeGroup


class GroupWidgetSignals(QObject):
    """Signals for group widget events."""

    position_changed = pyqtSignal(str, float, float)  # group_id, x, y
    collapsed_changed = pyqtSignal(str, bool)  # group_id, collapsed
    selected_changed = pyqtSignal(str, bool)  # group_id, selected
    double_clicked = pyqtSignal(str)  # group_id
    delete_requested = pyqtSignal(str)  # group_id
    resize_requested = pyqtSignal(str, float, float, float, float)  # group_id, x, y, w, h
    nodes_added = pyqtSignal(str, list)  # group_id, node_ids
    nodes_removed = pyqtSignal(str, list)  # group_id, node_ids


class GroupWidget(QGraphicsItem):
    """
    Visual representation of a node group on the graph canvas.

    Provides a complete graphical representation of a group including:
    - Header bar with group name and collapse/expand button
    - Semi-transparent body showing contained nodes
    - Visual feedback for selection and hover
    - Drag-to-move functionality that moves all contained nodes
    - Resize handles for adjusting group size

    Attributes:
        HEADER_HEIGHT: Height of the header bar.
        MIN_WIDTH: Minimum group width.
        MIN_HEIGHT: Minimum group height.
        CORNER_RADIUS: Radius of rounded corners.
        PADDING: Internal padding.
    """

    HEADER_HEIGHT = 32
    MIN_WIDTH = 200
    MIN_HEIGHT = 100
    CORNER_RADIUS = 10
    PADDING = 8
    COLLAPSE_BUTTON_SIZE = 20
    COLLAPSED_HEIGHT = 40  # Height when collapsed

    def __init__(
        self,
        group: "NodeGroup",
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """
        Initialize a group widget.

        Args:
            group: The node group model this widget represents.
            parent: Optional parent graphics item.
        """
        super().__init__(parent)

        self._group = group
        self._width = max(self.MIN_WIDTH, group.bounds.width)
        self._height = max(self.MIN_HEIGHT, group.bounds.height)

        # Visual state
        self._is_selected = False
        self._is_hovered = False
        self._collapse_button_hovered = False

        # Drag state for moving
        self._drag_start_pos: Optional[QPointF] = None
        self._drag_start_group_pos: Optional[QPointF] = None

        # Signals
        self.signals = GroupWidgetSignals()

        # Configure item
        self._setup_item()
        self._setup_colors()

        # Set initial position from group model
        self.setPos(group.bounds.x, group.bounds.y)

    def _setup_item(self) -> None:
        """Configure the graphics item flags and behavior."""
        # Enable selection and movement
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

        # Enable hover effects
        self.setAcceptHoverEvents(True)

        # Set cursor
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        # Set Z-value (groups below nodes but above grid)
        self.setZValue(0.5)

        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(4, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

    def _setup_colors(self) -> None:
        """Set up the color scheme based on group color."""
        group_color = QColor(self._group.color)

        # Header gradient colors
        self._header_color = group_color
        self._header_color_dark = group_color.darker(130)

        # Body colors (semi-transparent)
        self._body_color = QColor("#2d2d2d")
        self._body_color.setAlpha(180)
        self._body_color_selected = QColor("#3a3a3a")
        self._body_color_selected.setAlpha(200)

        # Border colors
        self._border_color = QColor("#555555")
        self._border_color_selected = QColor("#00AAFF")
        self._border_color_hover = QColor("#777777")

        # Text colors
        self._header_text_color = QColor("#FFFFFF")
        self._node_count_color = QColor("#AAAAAA")

    @property
    def group(self) -> "NodeGroup":
        """Get the group model."""
        return self._group

    @property
    def group_id(self) -> str:
        """Get the group ID."""
        return self._group.id

    @property
    def width(self) -> float:
        """Get the group width."""
        return self._width

    @property
    def height(self) -> float:
        """Get the current display height (accounts for collapsed state)."""
        if self._group.collapsed:
            return self.COLLAPSED_HEIGHT
        return self._height

    def set_size(self, width: float, height: float) -> None:
        """
        Set the group size.

        Args:
            width: New width.
            height: New height.
        """
        self.prepareGeometryChange()
        self._width = max(self.MIN_WIDTH, width)
        self._height = max(self.MIN_HEIGHT, height)
        self._group.bounds.width = self._width
        self._group.bounds.height = self._height
        self.update()

    def update_bounds_from_nodes(self, node_positions: Dict[str, tuple]) -> None:
        """
        Update the group bounds based on contained node positions.

        Args:
            node_positions: Dictionary mapping node_id to (x, y, width, height).
        """
        if not node_positions:
            return

        # Find bounding box of all nodes
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        for node_id in self._group.node_ids:
            if node_id in node_positions:
                x, y, w, h = node_positions[node_id]
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x + w)
                max_y = max(max_y, y + h)

        if min_x != float("inf"):
            padding = 30.0
            self.prepareGeometryChange()
            self.setPos(min_x - padding, min_y - padding - self.HEADER_HEIGHT)
            self._width = max_x - min_x + padding * 2
            self._height = max_y - min_y + padding * 2 + self.HEADER_HEIGHT
            self._group.bounds.x = min_x - padding
            self._group.bounds.y = min_y - padding - self.HEADER_HEIGHT
            self._group.bounds.width = self._width
            self._group.bounds.height = self._height
            self.update()

    def refresh_colors(self) -> None:
        """Refresh colors from the group model."""
        self._setup_colors()
        self.update()

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle of the group."""
        return QRectF(
            -2,
            -2,
            self._width + 4,
            self.height + 4,
        )

    def shape(self) -> QPainterPath:
        """Return the shape for collision detection."""
        path = QPainterPath()
        path.addRoundedRect(
            0, 0, self._width, self.height,
            self.CORNER_RADIUS, self.CORNER_RADIUS
        )
        return path

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the group widget."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_selected = self.isSelected()
        current_height = self.height

        # Determine colors based on state
        if is_selected:
            body_color = self._body_color_selected
            border_color = self._border_color_selected
            border_width = 2
        elif self._is_hovered:
            body_color = self._body_color
            border_color = self._border_color_hover
            border_width = 1.5
        else:
            body_color = self._body_color
            border_color = self._border_color
            border_width = 1

        # Draw body background
        body_rect = QRectF(0, 0, self._width, current_height)
        body_path = QPainterPath()
        body_path.addRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(body_color))
        painter.drawPath(body_path)

        # Draw header bar with gradient
        header_rect = QRectF(0, 0, self._width, self.HEADER_HEIGHT)
        header_path = QPainterPath()

        # Create rounded rect for top only
        header_path.moveTo(self.CORNER_RADIUS, 0)
        header_path.lineTo(self._width - self.CORNER_RADIUS, 0)
        header_path.arcTo(
            self._width - self.CORNER_RADIUS * 2, 0,
            self.CORNER_RADIUS * 2, self.CORNER_RADIUS * 2,
            90, -90
        )
        header_path.lineTo(self._width, self.HEADER_HEIGHT)
        header_path.lineTo(0, self.HEADER_HEIGHT)
        header_path.lineTo(0, self.CORNER_RADIUS)
        header_path.arcTo(0, 0, self.CORNER_RADIUS * 2, self.CORNER_RADIUS * 2, 180, -90)
        header_path.closeSubpath()

        # Create gradient for header
        gradient = QLinearGradient(0, 0, 0, self.HEADER_HEIGHT)
        gradient.setColorAt(0, self._header_color)
        gradient.setColorAt(1, self._header_color_dark)

        painter.setBrush(QBrush(gradient))
        painter.drawPath(header_path)

        # Draw collapse/expand button
        self._draw_collapse_button(painter)

        # Draw header text (group name)
        painter.setPen(QPen(self._header_text_color))
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font)

        text_x = self.COLLAPSE_BUTTON_SIZE + self.PADDING * 2
        text_rect = QRectF(
            text_x, 0,
            self._width - text_x - self.PADDING * 2,
            self.HEADER_HEIGHT
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._group.name
        )

        # Draw node count badge
        node_count = self._group.node_count
        if node_count > 0:
            count_text = f"({node_count})"
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            painter.setPen(QPen(self._node_count_color))

            count_rect = QRectF(
                self._width - 60, 0,
                50,
                self.HEADER_HEIGHT
            )
            painter.drawText(
                count_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                count_text
            )

        # Draw border
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # Draw separator line below header
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(
            QPointF(0, self.HEADER_HEIGHT),
            QPointF(self._width, self.HEADER_HEIGHT)
        )

        # If collapsed, draw indicator pattern
        if self._group.collapsed:
            self._draw_collapsed_indicator(painter)

    def _draw_collapse_button(self, painter: QPainter) -> None:
        """Draw the collapse/expand button."""
        button_x = self.PADDING
        button_y = (self.HEADER_HEIGHT - self.COLLAPSE_BUTTON_SIZE) / 2
        button_rect = QRectF(
            button_x, button_y,
            self.COLLAPSE_BUTTON_SIZE, self.COLLAPSE_BUTTON_SIZE
        )

        # Button background
        if self._collapse_button_hovered:
            painter.setBrush(QBrush(QColor(255, 255, 255, 50)))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(button_rect, 4, 4)

        # Draw arrow
        painter.setPen(QPen(self._header_text_color, 2))
        center_x = button_x + self.COLLAPSE_BUTTON_SIZE / 2
        center_y = button_y + self.COLLAPSE_BUTTON_SIZE / 2

        if self._group.collapsed:
            # Right-pointing arrow (collapsed)
            arrow = QPolygonF([
                QPointF(center_x - 3, center_y - 5),
                QPointF(center_x + 4, center_y),
                QPointF(center_x - 3, center_y + 5),
            ])
        else:
            # Down-pointing arrow (expanded)
            arrow = QPolygonF([
                QPointF(center_x - 5, center_y - 3),
                QPointF(center_x + 5, center_y - 3),
                QPointF(center_x, center_y + 4),
            ])

        painter.setBrush(QBrush(self._header_text_color))
        painter.drawPolygon(arrow)

    def _draw_collapsed_indicator(self, painter: QPainter) -> None:
        """Draw visual indicator when group is collapsed."""
        # Draw dots pattern to indicate hidden content
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 80)))

        dot_y = self.HEADER_HEIGHT + 6
        dot_spacing = 8
        dot_radius = 2

        start_x = self._width / 2 - dot_spacing
        for i in range(3):
            painter.drawEllipse(
                QPointF(start_x + i * dot_spacing, dot_y),
                dot_radius, dot_radius
            )

    def _get_collapse_button_rect(self) -> QRectF:
        """Get the collapse button rectangle."""
        return QRectF(
            self.PADDING,
            (self.HEADER_HEIGHT - self.COLLAPSE_BUTTON_SIZE) / 2,
            self.COLLAPSE_BUTTON_SIZE,
            self.COLLAPSE_BUTTON_SIZE
        )

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Handle item changes such as position or selection."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Snap to grid if enabled
            pos = value
            scene = self.scene()
            if scene is not None and hasattr(scene, 'snap_to_grid_enabled'):
                if scene.snap_to_grid_enabled:
                    snapped_x, snapped_y = scene.snap_to_grid(pos.x(), pos.y())
                    return QPointF(snapped_x, snapped_y)

        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Update group model position
            pos = value
            self._group.bounds.x = pos.x()
            self._group.bounds.y = pos.y()
            # Emit signal
            self.signals.position_changed.emit(self._group.id, pos.x(), pos.y())

        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._is_selected = bool(value)
            self.signals.selected_changed.emit(self._group.id, self._is_selected)
            self.update()

        return super().itemChange(change, value)

    def hoverEnterEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle hover enter event."""
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle hover leave event."""
        self._is_hovered = False
        self._collapse_button_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle hover move event."""
        # Check if hovering over collapse button
        button_rect = self._get_collapse_button_rect()
        was_hovered = self._collapse_button_hovered
        self._collapse_button_hovered = button_rect.contains(event.pos())

        if was_hovered != self._collapse_button_hovered:
            self.update()

        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking on collapse button
            button_rect = self._get_collapse_button_rect()
            if button_rect.contains(event.pos()):
                self._toggle_collapsed()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle double-click to toggle collapse."""
        # Check if double-clicking on header
        if event.pos().y() <= self.HEADER_HEIGHT:
            self._toggle_collapsed()
            event.accept()
            return

        self.signals.double_clicked.emit(self._group.id)
        super().mouseDoubleClickEvent(event)

    def _toggle_collapsed(self) -> None:
        """Toggle the collapsed state."""
        self.prepareGeometryChange()
        new_state = self._group.toggle_collapsed()
        self.signals.collapsed_changed.emit(self._group.id, new_state)
        self.update()

    def keyPressEvent(self, event) -> None:
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Delete:
            self.signals.delete_requested.emit(self._group.id)
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Handle right-click context menu."""
        from PyQt6.QtWidgets import QMenu, QColorDialog
        from PyQt6.QtGui import QAction

        menu = QMenu()

        # Toggle collapse action
        collapse_text = "Expand" if self._group.collapsed else "Collapse"
        collapse_action = QAction(collapse_text, menu)
        collapse_action.triggered.connect(self._toggle_collapsed)
        menu.addAction(collapse_action)

        menu.addSeparator()

        # Rename action
        rename_action = QAction("Rename...", menu)
        rename_action.triggered.connect(self._show_rename_dialog)
        menu.addAction(rename_action)

        # Change color action
        change_color_action = QAction("Change Color...", menu)
        change_color_action.triggered.connect(self._show_color_picker)
        menu.addAction(change_color_action)

        menu.addSeparator()

        # Ungroup action
        ungroup_action = QAction("Ungroup", menu)
        ungroup_action.triggered.connect(
            lambda: self.signals.delete_requested.emit(self._group.id)
        )
        menu.addAction(ungroup_action)

        # Show menu at cursor position
        menu.exec(event.screenPos())

    def _show_rename_dialog(self) -> None:
        """Show a dialog to rename the group."""
        from PyQt6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(
            None,
            "Rename Group",
            "Enter new name:",
            text=self._group.name
        )

        if ok and new_name:
            self._group.name = new_name
            self.update()

    def _show_color_picker(self) -> None:
        """Show a color picker dialog to change the group's color."""
        from PyQt6.QtWidgets import QColorDialog

        current_color = QColor(self._group.color)
        color = QColorDialog.getColor(
            current_color,
            None,
            f"Choose Color for {self._group.name}"
        )

        if color.isValid():
            self._group.color = color.name()
            self.refresh_colors()

    def sync_from_model(self) -> None:
        """Synchronize the widget state from the group model."""
        self.prepareGeometryChange()
        self.setPos(self._group.bounds.x, self._group.bounds.y)
        self._width = max(self.MIN_WIDTH, self._group.bounds.width)
        self._height = max(self.MIN_HEIGHT, self._group.bounds.height)
        self._setup_colors()
        self.update()

    def __repr__(self) -> str:
        """String representation."""
        return f"GroupWidget(id='{self._group.id[:8]}...', name='{self._group.name}')"
