"""
Subgraph node widget for visualizing nested workflows.

This module provides a specialized NodeWidget for SubgraphNode that supports:
- Collapsed view showing only the subgraph name and ports
- Expanded view showing a preview of the internal workflow
- Double-click to open the subgraph for editing
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import (
    QColor,
    QPen,
    QPainter,
    QBrush,
    QFont,
    QPainterPath,
    QLinearGradient,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from visualpython.nodes.views.node_widget import NodeWidget, NodeWidgetSignals

if TYPE_CHECKING:
    from visualpython.nodes.models.subgraph_node import SubgraphNode


class SubgraphWidgetSignals(NodeWidgetSignals):
    """Extended signals for subgraph widget events."""

    from PyQt6.QtCore import pyqtSignal

    # Emitted when user requests to open the subgraph for editing
    open_subgraph_requested = pyqtSignal(str)  # node_id


class SubgraphNodeWidget(NodeWidget):
    """
    Visual representation of a SubgraphNode on the graph canvas.

    This widget extends NodeWidget with special handling for subgraphs:
    - Special styling to distinguish subgraphs from regular nodes
    - Collapsed/expanded view modes
    - Double-click to open for editing
    - Preview of internal workflow structure

    Attributes:
        SUBGRAPH_ICON_SIZE: Size of the subgraph indicator icon.
        PREVIEW_HEIGHT: Height of the workflow preview area.
    """

    SUBGRAPH_ICON_SIZE = 16
    PREVIEW_HEIGHT = 80

    def __init__(
        self,
        node: "SubgraphNode",
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """
        Initialize a subgraph node widget.

        Args:
            node: The SubgraphNode model this widget represents.
            parent: Optional parent graphics item.
        """
        # Track view mode
        self._is_collapsed_view = False
        self._show_preview = True

        super().__init__(node, parent)

        # Replace signals with extended version (must be after super().__init__)
        self.signals = SubgraphWidgetSignals()

        # Override to use subgraph-specific styling
        self._setup_subgraph_colors()

    def _setup_subgraph_colors(self) -> None:
        """Set up subgraph-specific color scheme."""
        # Use a distinctive purple gradient for subgraphs
        self._title_color = QColor("#9C27B0")  # Purple
        self._title_color_dark = QColor("#7B1FA2")

        # Slightly different body color
        self._body_color = QColor("#2d2d35")
        self._body_color_selected = QColor("#3a3a45")

        # Special border color
        self._border_color = QColor("#9C27B0")
        self._border_color_selected = QColor("#CE93D8")

    @property
    def subgraph_node(self) -> "SubgraphNode":
        """Get the SubgraphNode model."""
        return self._node

    def set_collapsed_view(self, collapsed: bool) -> None:
        """
        Set the collapsed view state.

        In collapsed view, the node shows minimal information.
        In expanded view, it shows a preview of internal structure.

        Args:
            collapsed: Whether to show collapsed view.
        """
        if self._is_collapsed_view != collapsed:
            self._is_collapsed_view = collapsed
            self._calculate_size()
            self.update()

    def _calculate_size(self) -> None:
        """Calculate the node size, accounting for collapsed/expanded state."""
        super()._calculate_size()

        # Add preview area height in expanded view
        if not self._is_collapsed_view and self._show_preview:
            self._height += self.PREVIEW_HEIGHT

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the subgraph node with special styling."""
        # Call parent paint for basic node rendering
        super().paint(painter, option, widget)

        # Draw additional subgraph indicators
        self._draw_subgraph_indicator(painter)

        # Draw preview in expanded view
        if not self._is_collapsed_view and self._show_preview:
            self._draw_workflow_preview(painter)

    def _draw_subgraph_indicator(self, painter: QPainter) -> None:
        """Draw a visual indicator that this is a subgraph node."""
        # Draw a small nested boxes icon in the title bar
        icon_x = self._width - self.SUBGRAPH_ICON_SIZE - 8
        icon_y = 6

        painter.save()

        # Draw nested boxes icon
        pen = QPen(QColor("#FFFFFF"), 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Outer box
        painter.drawRect(
            int(icon_x),
            int(icon_y),
            int(self.SUBGRAPH_ICON_SIZE),
            int(self.SUBGRAPH_ICON_SIZE)
        )

        # Inner box (offset)
        inner_size = self.SUBGRAPH_ICON_SIZE - 6
        painter.drawRect(
            int(icon_x + 3),
            int(icon_y + 3),
            int(inner_size),
            int(inner_size)
        )

        painter.restore()

    def _draw_workflow_preview(self, painter: QPainter) -> None:
        """Draw a miniature preview of the internal workflow structure."""
        # Calculate preview area
        preview_y = self._height - self.PREVIEW_HEIGHT
        preview_rect = QRectF(
            4,
            preview_y + 4,
            self._width - 8,
            self.PREVIEW_HEIGHT - 8,
        )

        painter.save()

        # Draw preview background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#1e1e1e")))
        painter.drawRoundedRect(preview_rect, 4, 4)

        # Draw preview content
        subgraph_node = self._node
        if subgraph_node.embedded_graph_data:
            self._draw_miniature_nodes(painter, preview_rect, subgraph_node.embedded_graph_data)
        else:
            # Draw "no preview" text
            painter.setPen(QPen(QColor("#666666")))
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            painter.drawText(preview_rect, Qt.AlignmentFlag.AlignCenter, "No preview available")

        # Draw border
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#444444"), 1))
        painter.drawRoundedRect(preview_rect, 4, 4)

        painter.restore()

    def _draw_miniature_nodes(
        self,
        painter: QPainter,
        preview_rect: QRectF,
        graph_data: dict,
    ) -> None:
        """Draw miniature representation of nodes in the preview area."""
        nodes = graph_data.get("nodes", [])
        if not nodes:
            return

        # Calculate scaling to fit nodes in preview
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")

        for node_data in nodes:
            pos = node_data.get("position", {})
            x = pos.get("x", 0)
            y = pos.get("y", 0)
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + 100)  # Assume node width
            max_y = max(max_y, y + 50)   # Assume node height

        if min_x == float("inf"):
            return

        # Calculate scale
        graph_width = max_x - min_x
        graph_height = max_y - min_y

        scale_x = (preview_rect.width() - 16) / max(graph_width, 1)
        scale_y = (preview_rect.height() - 16) / max(graph_height, 1)
        scale = min(scale_x, scale_y, 0.3)  # Cap scale at 0.3

        # Draw miniature nodes
        painter.setPen(QPen(QColor("#666666"), 1))

        for node_data in nodes:
            pos = node_data.get("position", {})
            x = pos.get("x", 0)
            y = pos.get("y", 0)

            # Scale and offset
            node_x = preview_rect.x() + 8 + (x - min_x) * scale
            node_y = preview_rect.y() + 8 + (y - min_y) * scale
            node_w = 20 * scale
            node_h = 12 * scale

            # Color based on node type
            node_type = node_data.get("type", "code")
            if node_type == "subgraph":
                color = QColor("#9C27B0")
            elif node_type == "subgraph_input":
                color = QColor("#4CAF50")
            elif node_type == "subgraph_output":
                color = QColor("#FF5722")
            else:
                color = QColor("#5C6BC0")

            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(
                QRectF(node_x, node_y, node_w, node_h),
                2, 2
            )

        # Draw miniature connections
        connections = graph_data.get("connections", [])
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#555555"), 1))

        node_positions = {}
        for node_data in nodes:
            node_id = node_data.get("id")
            pos = node_data.get("position", {})
            node_positions[node_id] = (
                preview_rect.x() + 8 + (pos.get("x", 0) - min_x) * scale + 10 * scale,
                preview_rect.y() + 8 + (pos.get("y", 0) - min_y) * scale + 6 * scale,
            )

        for conn in connections[:10]:  # Limit connections shown
            src_id = conn.get("source_node_id")
            tgt_id = conn.get("target_node_id")

            if src_id in node_positions and tgt_id in node_positions:
                src_pos = node_positions[src_id]
                tgt_pos = node_positions[tgt_id]
                painter.drawLine(
                    int(src_pos[0]), int(src_pos[1]),
                    int(tgt_pos[0]), int(tgt_pos[1])
                )

    def mouseDoubleClickEvent(self, event) -> None:
        """Handle double-click to open subgraph for editing."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Emit signal to request opening the subgraph
            self.signals.open_subgraph_requested.emit(self._node.id)
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Handle context menu with subgraph-specific options."""
        from PyQt6.QtWidgets import QMenu, QAction

        menu = QMenu()

        # Edit subgraph action
        edit_action = QAction("Edit Subgraph", menu)
        edit_action.triggered.connect(
            lambda: self.signals.open_subgraph_requested.emit(self._node.id)
        )
        menu.addAction(edit_action)

        # Toggle preview action
        toggle_preview = QAction(
            "Hide Preview" if self._show_preview else "Show Preview",
            menu
        )
        toggle_preview.triggered.connect(self._toggle_preview)
        menu.addAction(toggle_preview)

        menu.addSeparator()

        # Subgraph info
        subgraph_node = self._node
        info_text = f"Subgraph: {subgraph_node.subgraph_name}"
        if subgraph_node.embedded_graph_data:
            node_count = len(subgraph_node.embedded_graph_data.get("nodes", []))
            info_text += f" ({node_count} nodes)"
        info_action = QAction(info_text, menu)
        info_action.setEnabled(False)
        menu.addAction(info_action)

        menu.addSeparator()

        # Standard node actions (color, delete, etc.)
        super()._add_standard_context_menu_actions(menu)

        menu.exec(event.screenPos())

    def _add_standard_context_menu_actions(self, menu) -> None:
        """Add standard node context menu actions."""
        from PyQt6.QtWidgets import QAction

        menu.addSeparator()

        # Color actions
        color_action = QAction("Change Color...", menu)
        color_action.triggered.connect(self._show_color_picker)
        menu.addAction(color_action)

        if self._node.custom_color:
            reset_color_action = QAction("Reset Color", menu)
            reset_color_action.triggered.connect(self._reset_color)
            menu.addAction(reset_color_action)

        menu.addSeparator()

        # Delete action
        delete_action = QAction("Delete", menu)
        delete_action.setShortcut("Delete")
        delete_action.triggered.connect(
            lambda: self.signals.delete_requested.emit(self._node.id)
        )
        menu.addAction(delete_action)

    def _toggle_preview(self) -> None:
        """Toggle the preview visibility."""
        self._show_preview = not self._show_preview
        self._calculate_size()
        self.update()
