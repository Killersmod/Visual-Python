"""
For Loop node visual widget with custom visual representation.

This module provides a specialized NodeWidget for ForLoopNode that displays
loop configuration fields (iteration variable) and highlights the body
connection port to make the iteration structure visible in the graph.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QColor,
    QPen,
    QPainter,
    QBrush,
    QFont,
    QFontMetrics,
    QPainterPath,
    QLinearGradient,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from visualpython.nodes.views.node_widget import NodeWidget, EXECUTION_STATE_COLORS
from visualpython.nodes.views.port_widget import PortWidget, PORT_TYPE_COLORS

if TYPE_CHECKING:
    from visualpython.nodes.models.for_loop_node import ForLoopNode


class ForLoopNodeWidget(NodeWidget):
    """
    Specialized visual representation of a ForLoopNode.

    Extends the base NodeWidget to provide:
    - Display of the iteration variable name in a configuration section
    - Visual distinction for the loop_body port (body connection port)
    - Clear separation between loop control flow (loop_body, completed)
      and data outputs (item, index)

    The widget renders an additional configuration section showing the
    iteration variable name, making the loop structure more visible.
    """

    # Additional height for the configuration section
    CONFIG_SECTION_HEIGHT = 28
    LOOP_BODY_SECTION_HEIGHT = 20

    def __init__(
        self,
        node: ForLoopNode,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """
        Initialize a for loop node widget.

        Args:
            node: The ForLoopNode model this widget represents.
            parent: Optional parent graphics item.
        """
        super().__init__(node, parent)

        # Store typed reference to the for loop node
        self._for_loop_node: ForLoopNode = node

    def _calculate_size(self) -> None:
        """Calculate the required size including the configuration section."""
        # Call base calculation first
        super()._calculate_size()

        # Add extra height for the configuration section
        self._height += self.CONFIG_SECTION_HEIGHT + self.LOOP_BODY_SECTION_HEIGHT

        # Reposition ports to account for extra sections
        self._position_ports()

    def _position_ports(self) -> None:
        """Position all port widgets accounting for the configuration section."""
        # Input ports on the left - below config section
        y_offset = (
            self.TITLE_HEIGHT
            + self.CONFIG_SECTION_HEIGHT
            + self.PADDING
            + self.PORT_SPACING / 2
        )
        for i, (name, port_widget) in enumerate(self._input_port_widgets.items()):
            x = 0  # Left edge
            y = y_offset + i * self.PORT_SPACING
            port_widget.setPos(x, y)

        # Output ports on the right
        # Position loop_body first with special offset for the loop body section label
        output_port_names = list(self._output_port_widgets.keys())
        y_offset = (
            self.TITLE_HEIGHT
            + self.CONFIG_SECTION_HEIGHT
            + self.LOOP_BODY_SECTION_HEIGHT
            + self.PADDING
            + self.PORT_SPACING / 2
        )

        for i, (name, port_widget) in enumerate(self._output_port_widgets.items()):
            x = self._width  # Right edge
            y = y_offset + i * self.PORT_SPACING
            port_widget.setPos(x, y)

        # Position labels
        for label in self._port_labels:
            port_name = label.port.name
            if label.is_input and port_name in self._input_port_widgets:
                label.adjust_position(self._input_port_widgets[port_name], self._width)
            elif not label.is_input and port_name in self._output_port_widgets:
                label.adjust_position(self._output_port_widgets[port_name], self._width)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the for loop node widget with custom sections."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Determine colors based on selection state
        is_selected = self.isSelected()
        body_color = self._body_color_selected if is_selected else self._body_color
        border_color = self._border_color_selected if is_selected else self._border_color
        border_width = 2 if is_selected else 1

        # Draw body background
        body_rect = QRectF(0, 0, self._width, self._height)
        body_path = QPainterPath()
        body_path.addRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(body_color))
        painter.drawPath(body_path)

        # Draw title bar with gradient
        title_path = self._create_title_path()
        gradient = QLinearGradient(0, 0, 0, self.TITLE_HEIGHT)
        gradient.setColorAt(0, self._title_color)
        gradient.setColorAt(1, self._title_color_dark)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(title_path)

        # Draw title text
        painter.setPen(QPen(self._title_text_color))
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font)
        text_rect = QRectF(self.PADDING, 0, self._width - self.PADDING * 2, self.TITLE_HEIGHT)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._node.name,
        )

        # Draw execution state indicator (small circle in title bar)
        indicator_radius = 5
        indicator_x = self._width - self.PADDING - indicator_radius
        indicator_y = self.TITLE_HEIGHT / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._execution_state_color))
        painter.drawEllipse(
            QPointF(indicator_x, indicator_y), indicator_radius, indicator_radius
        )

        # Draw separator line below title
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(
            QPointF(0, self.TITLE_HEIGHT), QPointF(self._width, self.TITLE_HEIGHT)
        )

        # Draw configuration section background (darker to distinguish)
        config_rect = QRectF(
            0, self.TITLE_HEIGHT, self._width, self.CONFIG_SECTION_HEIGHT
        )
        config_color = QColor("#252525")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(config_color))
        painter.drawRect(config_rect)

        # Draw iteration variable label
        painter.setPen(QPen(QColor("#AAAAAA")))
        config_font = QFont("Segoe UI", 9)
        painter.setFont(config_font)
        var_text = f"for {self._for_loop_node.iteration_variable} in iterable:"
        config_text_rect = QRectF(
            self.PADDING,
            self.TITLE_HEIGHT,
            self._width - self.PADDING * 2,
            self.CONFIG_SECTION_HEIGHT,
        )
        painter.drawText(
            config_text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            var_text,
        )

        # Draw separator below configuration
        config_bottom_y = self.TITLE_HEIGHT + self.CONFIG_SECTION_HEIGHT
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(
            QPointF(0, config_bottom_y), QPointF(self._width, config_bottom_y)
        )

        # Draw "Loop Body" section header
        loop_body_rect = QRectF(
            0, config_bottom_y, self._width, self.LOOP_BODY_SECTION_HEIGHT
        )
        loop_body_bg = QColor("#1a2a1a")  # Slightly greenish to indicate active loop area
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(loop_body_bg))
        painter.drawRect(loop_body_rect)

        # Draw "LOOP BODY" label on the right side
        painter.setPen(QPen(QColor("#66BB6A")))  # Green text for loop body
        loop_label_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(loop_label_font)
        loop_label_rect = QRectF(
            self.PADDING,
            config_bottom_y,
            self._width - self.PADDING * 2,
            self.LOOP_BODY_SECTION_HEIGHT,
        )
        painter.drawText(
            loop_label_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            "LOOP BODY →",
        )

        # Draw separator below loop body section
        loop_body_bottom_y = config_bottom_y + self.LOOP_BODY_SECTION_HEIGHT
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(
            QPointF(0, loop_body_bottom_y), QPointF(self._width, loop_body_bottom_y)
        )

        # Draw border around entire node
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

    def _create_title_path(self) -> QPainterPath:
        """Create the path for the title bar with rounded top corners."""
        title_path = QPainterPath()
        # Create rounded rect for top only
        title_path.moveTo(self.CORNER_RADIUS, 0)
        title_path.lineTo(self._width - self.CORNER_RADIUS, 0)
        title_path.arcTo(
            self._width - self.CORNER_RADIUS * 2,
            0,
            self.CORNER_RADIUS * 2,
            self.CORNER_RADIUS * 2,
            90,
            -90,
        )
        title_path.lineTo(self._width, self.TITLE_HEIGHT)
        title_path.lineTo(0, self.TITLE_HEIGHT)
        title_path.lineTo(0, self.CORNER_RADIUS)
        title_path.arcTo(0, 0, self.CORNER_RADIUS * 2, self.CORNER_RADIUS * 2, 180, -90)
        title_path.closeSubpath()
        return title_path

    def sync_from_model(self) -> None:
        """Synchronize the widget state from the node model."""
        super().sync_from_model()
        # Force redraw to update iteration variable display
        self.update()
