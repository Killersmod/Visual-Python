"""
If/Else node visual widget with custom visual representation.

This module provides a specialized NodeWidget for IfNode that displays
the condition field and highlights the True/False branch output ports
to make conditional branching visible in the graph.
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
    from visualpython.nodes.models.if_node import IfNode


class IfNodeWidget(NodeWidget):
    """
    Specialized visual representation of an IfNode.

    Extends the base NodeWidget to provide:
    - Display of the condition code/expression in a configuration section
    - Visual distinction for True/False branch output ports
    - Clear labeling of the branching paths (True → and False →)

    The widget renders an additional configuration section showing the
    condition expression, making the conditional branching more visible.
    """

    # Additional height for the configuration section
    CONDITION_SECTION_HEIGHT = 28
    BRANCH_SECTION_HEIGHT = 20

    def __init__(
        self,
        node: IfNode,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """
        Initialize an if node widget.

        Args:
            node: The IfNode model this widget represents.
            parent: Optional parent graphics item.
        """
        super().__init__(node, parent)

        # Store typed reference to the if node
        self._if_node: IfNode = node

    def _calculate_size(self) -> None:
        """Calculate the required size including the condition section."""
        # Call base calculation first
        super()._calculate_size()

        # Add extra height for the condition section and branch label section
        self._height += self.CONDITION_SECTION_HEIGHT + self.BRANCH_SECTION_HEIGHT

        # Ensure minimum width for condition display
        self._width = max(self._width, 180)

        # Reposition ports to account for extra sections
        self._position_ports()

    def _position_ports(self) -> None:
        """Position all port widgets accounting for the condition section."""
        # Input ports on the left - below condition section
        y_offset = (
            self.TITLE_HEIGHT
            + self.CONDITION_SECTION_HEIGHT
            + self.PADDING
            + self.PORT_SPACING / 2
        )
        for i, (name, port_widget) in enumerate(self._input_port_widgets.items()):
            x = 0  # Left edge
            y = y_offset + i * self.PORT_SPACING
            port_widget.setPos(x, y)

        # Output ports on the right
        # Position with offset for the branch section label
        output_port_names = list(self._output_port_widgets.keys())
        y_offset = (
            self.TITLE_HEIGHT
            + self.CONDITION_SECTION_HEIGHT
            + self.BRANCH_SECTION_HEIGHT
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
        """Paint the if node widget with custom sections."""
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

        # Draw condition section background (darker to distinguish)
        condition_rect = QRectF(
            0, self.TITLE_HEIGHT, self._width, self.CONDITION_SECTION_HEIGHT
        )
        condition_color = QColor("#252525")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(condition_color))
        painter.drawRect(condition_rect)

        # Draw condition expression label
        painter.setPen(QPen(QColor("#AAAAAA")))
        condition_font = QFont("Segoe UI", 9)
        painter.setFont(condition_font)

        # Get condition display text
        condition_text = self._get_condition_display_text()
        condition_text_rect = QRectF(
            self.PADDING,
            self.TITLE_HEIGHT,
            self._width - self.PADDING * 2,
            self.CONDITION_SECTION_HEIGHT,
        )
        painter.drawText(
            condition_text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            condition_text,
        )

        # Draw separator below condition section
        condition_bottom_y = self.TITLE_HEIGHT + self.CONDITION_SECTION_HEIGHT
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(
            QPointF(0, condition_bottom_y), QPointF(self._width, condition_bottom_y)
        )

        # Draw branch section with True/False indicators
        branch_rect = QRectF(
            0, condition_bottom_y, self._width, self.BRANCH_SECTION_HEIGHT
        )
        branch_bg = QColor("#1a1a2a")  # Slightly purple to match node color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(branch_bg))
        painter.drawRect(branch_rect)

        # Draw branch labels on the right side
        branch_label_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(branch_label_font)

        # Draw "True →" in green and "False →" in red
        branch_text = "True → / False →"

        # Calculate positions for each part
        true_color = QColor("#4CAF50")  # Green for True
        false_color = QColor("#F44336")  # Red for False

        # Draw combined label on right
        branch_label_rect = QRectF(
            self.PADDING,
            condition_bottom_y,
            self._width - self.PADDING * 2,
            self.BRANCH_SECTION_HEIGHT,
        )

        # Draw "True →" in green
        painter.setPen(QPen(true_color))
        true_text = "True →"
        font_metrics = QFontMetrics(branch_label_font)
        true_width = font_metrics.horizontalAdvance(true_text)
        separator_width = font_metrics.horizontalAdvance(" / ")
        false_width = font_metrics.horizontalAdvance("False →")

        total_width = true_width + separator_width + false_width
        start_x = self._width - self.PADDING - total_width

        painter.drawText(
            QRectF(start_x, condition_bottom_y, true_width, self.BRANCH_SECTION_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            true_text,
        )

        # Draw separator
        painter.setPen(QPen(QColor("#666666")))
        painter.drawText(
            QRectF(start_x + true_width, condition_bottom_y, separator_width, self.BRANCH_SECTION_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            " / ",
        )

        # Draw "False →" in red
        painter.setPen(QPen(false_color))
        painter.drawText(
            QRectF(start_x + true_width + separator_width, condition_bottom_y, false_width, self.BRANCH_SECTION_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "False →",
        )

        # Draw separator below branch section
        branch_bottom_y = condition_bottom_y + self.BRANCH_SECTION_HEIGHT
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(
            QPointF(0, branch_bottom_y), QPointF(self._width, branch_bottom_y)
        )

        # Draw border around entire node
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

    def _get_condition_display_text(self) -> str:
        """Get the condition text to display in the condition section."""
        if self._if_node.condition_code:
            # Truncate long condition code
            code = self._if_node.condition_code
            if len(code) > 25:
                code = code[:22] + "..."
            return f"if {code}:"
        else:
            return "if condition:"

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
        # Force redraw to update condition display
        self.update()
