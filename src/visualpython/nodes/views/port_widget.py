"""
Port visual widgets for node connections.

This module provides the QGraphicsItem-based visual representation of input
and output ports on nodes, including their appearance and interaction behavior.
It also supports embedding inline value widgets for input ports.

Classes:
    PortWidgetSignals: Signals for port widget events.
    PortWidget: Visual representation of a node port.
    PortLabelWidget: Text label displayed next to a port.

Functions:
    create_inline_widget_for_port: Factory method to create appropriate
        inline widget based on PortType.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPen, QPainter, QBrush, QFont
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsEllipseItem,
    QGraphicsTextItem,
    QGraphicsProxyWidget,
    QStyleOptionGraphicsItem,
    QWidget,
)

if TYPE_CHECKING:
    from visualpython.nodes.models.port import BasePort, InputPort, OutputPort, PortType
    from visualpython.nodes.views.node_widget import NodeWidget
    from visualpython.nodes.views.inline_value_widget import InlineValueWidget

from visualpython.nodes.models.port import PortType as PortTypeEnum


# Port type color mapping
PORT_TYPE_COLORS: dict[str, str] = {
    "ANY": "#FFFFFF",
    "FLOW": "#E91E63",  # Pink for flow
    "STRING": "#4CAF50",  # Green
    "INTEGER": "#2196F3",  # Blue
    "FLOAT": "#03A9F4",  # Light blue
    "BOOLEAN": "#FF5722",  # Deep orange
    "LIST": "#9C27B0",  # Purple
    "DICT": "#FF9800",  # Orange
    "OBJECT": "#795548",  # Brown
}


class PortWidgetSignals(QObject):
    """Signals for port widget events."""

    connection_started = pyqtSignal(object)  # Emits PortWidget
    connection_ended = pyqtSignal(object)  # Emits PortWidget
    hovered = pyqtSignal(bool)  # Emits hover state


class PortWidget(QGraphicsEllipseItem):
    """
    Visual representation of a node port.

    Ports are displayed as small circles on the sides of nodes that can be
    clicked to create connections. Input ports appear on the left, output
    ports on the right.

    For input ports (non-FLOW type), an inline value widget can be embedded
    to allow users to enter literal values directly when the port is not
    connected.

    Attributes:
        PORT_RADIUS: The radius of the port circle in pixels.
        HOVER_RADIUS: The radius when hovered.
        INLINE_WIDGET_OFFSET: Horizontal offset from port to inline widget.
    """

    PORT_RADIUS = 6
    HOVER_RADIUS = 8
    INLINE_WIDGET_OFFSET = 8  # Gap between port circle and inline widget

    def __init__(
        self,
        port: BasePort,
        is_input: bool,
        parent_node: NodeWidget,
    ) -> None:
        """
        Initialize a port widget.

        Args:
            port: The port model this widget represents.
            is_input: True if this is an input port, False for output.
            parent_node: The parent node widget.
        """
        # Create circle centered at (0, 0)
        super().__init__(
            -self.PORT_RADIUS,
            -self.PORT_RADIUS,
            self.PORT_RADIUS * 2,
            self.PORT_RADIUS * 2,
            parent_node,
        )

        self._port = port
        self._is_input = is_input
        self._parent_node = parent_node
        self._is_hovered = False
        self._is_connected = False
        self._highlight_state: Optional[str] = None  # None, "compatible", "incompatible"

        # Inline value widget support (for input ports only)
        self._inline_widget: Optional[InlineValueWidget] = None
        self._inline_proxy: Optional[QGraphicsProxyWidget] = None

        # Signals
        self.signals = PortWidgetSignals()

        # Set up appearance
        self._setup_appearance()

        # Enable interaction
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Set tooltip
        tooltip = f"{port.name} ({port.port_type.name})"
        if port.description:
            tooltip += f"\n{port.description}"
        self.setToolTip(tooltip)

    def _setup_appearance(self) -> None:
        """Configure the visual appearance of the port."""
        # Get color based on port type
        port_type_name = self._port.port_type.name
        color_hex = PORT_TYPE_COLORS.get(port_type_name, "#FFFFFF")
        color = QColor(color_hex)

        # Set up pen and brush
        self._default_pen = QPen(color.darker(120), 2)
        self._hover_pen = QPen(color, 3)
        self._connected_pen = QPen(color, 2)

        self._default_brush = QBrush(color.darker(150))
        self._hover_brush = QBrush(color)
        self._connected_brush = QBrush(color)

        # Highlight colors for connection compatibility feedback
        self._compatible_pen = QPen(QColor("#00FF00"), 3)  # Green for compatible
        self._compatible_brush = QBrush(QColor("#00FF00").darker(150))
        self._incompatible_pen = QPen(QColor("#FF4444"), 3)  # Red for incompatible
        self._incompatible_brush = QBrush(QColor("#FF4444").darker(150))

        # Apply default appearance
        self._update_appearance()

    def _update_appearance(self) -> None:
        """Update the port appearance based on current state."""
        # Highlight state takes priority during connection dragging
        if self._highlight_state == "compatible":
            self.setPen(self._compatible_pen)
            self.setBrush(self._compatible_brush)
            self.setRect(
                -self.HOVER_RADIUS,
                -self.HOVER_RADIUS,
                self.HOVER_RADIUS * 2,
                self.HOVER_RADIUS * 2,
            )
        elif self._highlight_state == "incompatible":
            self.setPen(self._incompatible_pen)
            self.setBrush(self._incompatible_brush)
            self.setRect(
                -self.HOVER_RADIUS,
                -self.HOVER_RADIUS,
                self.HOVER_RADIUS * 2,
                self.HOVER_RADIUS * 2,
            )
        elif self._is_hovered:
            self.setPen(self._hover_pen)
            self.setBrush(self._hover_brush)
            # Expand size when hovered
            self.setRect(
                -self.HOVER_RADIUS,
                -self.HOVER_RADIUS,
                self.HOVER_RADIUS * 2,
                self.HOVER_RADIUS * 2,
            )
        elif self._is_connected:
            self.setPen(self._connected_pen)
            self.setBrush(self._connected_brush)
            self.setRect(
                -self.PORT_RADIUS,
                -self.PORT_RADIUS,
                self.PORT_RADIUS * 2,
                self.PORT_RADIUS * 2,
            )
        else:
            self.setPen(self._default_pen)
            self.setBrush(self._default_brush)
            self.setRect(
                -self.PORT_RADIUS,
                -self.PORT_RADIUS,
                self.PORT_RADIUS * 2,
                self.PORT_RADIUS * 2,
            )

    @property
    def port(self) -> BasePort:
        """Get the port model."""
        return self._port

    @property
    def is_input(self) -> bool:
        """Check if this is an input port."""
        return self._is_input

    @property
    def is_output(self) -> bool:
        """Check if this is an output port."""
        return not self._is_input

    @property
    def parent_node(self) -> NodeWidget:
        """Get the parent node widget."""
        return self._parent_node

    @property
    def is_connected(self) -> bool:
        """Check if this port has connections."""
        return self._is_connected

    @is_connected.setter
    def is_connected(self, value: bool) -> None:
        """Set the connection state and update inline widget visibility."""
        self._is_connected = value
        self._update_appearance()
        # Update inline widget state based on connection
        self._update_inline_widget_state()

    @property
    def inline_widget(self) -> Optional[InlineValueWidget]:
        """Get the inline value widget, if any."""
        return self._inline_widget

    @property
    def inline_proxy(self) -> Optional[QGraphicsProxyWidget]:
        """Get the inline widget's graphics proxy, if any."""
        return self._inline_proxy

    @property
    def has_inline_widget(self) -> bool:
        """Check if this port has an inline value widget."""
        return self._inline_widget is not None

    def set_inline_widget(self, widget: Optional[InlineValueWidget]) -> None:
        """
        Set the inline value widget for this port.

        This method attaches an InlineValueWidget to the port, creating
        a QGraphicsProxyWidget to display it in the scene. The inline
        widget is only supported for input ports.

        Args:
            widget: The inline value widget to attach, or None to remove.

        Raises:
            ValueError: If attempting to set an inline widget on an output port.
        """
        if widget is not None and not self._is_input:
            raise ValueError("Inline widgets can only be attached to input ports")

        # Clean up existing inline widget
        self._cleanup_inline_widget()

        if widget is None:
            return

        # Store the widget reference
        self._inline_widget = widget

        # Create graphics proxy for scene embedding
        self._inline_proxy = widget.create_graphics_proxy()

        # Set the proxy's parent to this port's parent node
        self._inline_proxy.setParentItem(self._parent_node)

        # Position the inline widget
        self._position_inline_widget()

        # Update visibility based on connection state
        self._update_inline_widget_state()

    def _cleanup_inline_widget(self) -> None:
        """Clean up and remove the current inline widget."""
        if self._inline_widget is not None:
            # Cleanup the widget resources
            self._inline_widget.cleanup()
            self._inline_widget = None

        if self._inline_proxy is not None:
            # Remove proxy from scene
            if self._inline_proxy.scene() is not None:
                self._inline_proxy.scene().removeItem(self._inline_proxy)
            self._inline_proxy = None

    def _position_inline_widget(self) -> None:
        """
        Position the inline widget relative to the port.

        The inline widget is positioned to the right of the port circle
        for input ports, with proper vertical centering.
        """
        if self._inline_proxy is None or self._inline_widget is None:
            return

        # Get the port position relative to the parent node
        port_pos = self.pos()

        # Calculate inline widget position
        # For input ports: position to the right of the port
        widget_height = self._inline_widget.get_height()

        # X position: port circle edge + offset
        x = port_pos.x() + self.PORT_RADIUS + self.INLINE_WIDGET_OFFSET

        # Y position: centered vertically with the port
        y = port_pos.y() - widget_height / 2

        self._inline_proxy.setPos(x, y)

    def _update_inline_widget_state(self) -> None:
        """
        Update the inline widget's enabled/visible state based on port connection.

        When the port is connected, the inline widget is disabled (dimmed)
        because the connected value takes precedence.
        When the port is not connected, the inline widget is enabled.
        """
        if self._inline_widget is None:
            return

        # Check if this is a FLOW type port (should not have inline widget)
        from visualpython.nodes.models.port import PortType
        if self._port.port_type == PortType.FLOW:
            self._inline_widget.set_visible(False)
            return

        # Show the widget
        self._inline_widget.set_visible(True)

        # Enable/disable based on connection state
        # When connected, disable the inline widget (value comes from connection)
        self._inline_widget.set_enabled(not self._is_connected)

    def update_inline_widget_position(self) -> None:
        """
        Update the inline widget position.

        Call this method after the port position has changed to
        reposition the inline widget accordingly.
        """
        self._position_inline_widget()

    def sync_inline_widget_from_port(self) -> None:
        """
        Synchronize the inline widget value from the port's inline_value.

        Call this after the port's inline_value has been changed externally
        (e.g., from deserialization) to update the widget display.
        """
        if self._inline_widget is not None:
            self._inline_widget.sync_from_port()

    def get_inline_widget_width(self) -> float:
        """
        Get the width required for the inline widget.

        Returns:
            The preferred width of the inline widget, or 0 if no widget.
        """
        if self._inline_widget is not None:
            return self._inline_widget.get_preferred_width() + self.INLINE_WIDGET_OFFSET
        return 0

    def remove_inline_widget(self) -> None:
        """
        Remove the inline widget from this port.

        This is a convenience method that calls set_inline_widget(None).
        """
        self.set_inline_widget(None)

    def set_inline_widget_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the inline widget.

        Args:
            enabled: Whether the inline widget should be enabled.
        """
        if self._inline_widget is not None:
            self._inline_widget.set_enabled(enabled)

    def set_highlight_state(self, state: Optional[str]) -> None:
        """
        Set the highlight state for connection compatibility feedback.

        Args:
            state: None for no highlight, "compatible" for green,
                   "incompatible" for red.
        """
        if self._highlight_state != state:
            self._highlight_state = state
            self._update_appearance()

    @property
    def highlight_state(self) -> Optional[str]:
        """Get the current highlight state."""
        return self._highlight_state

    def get_scene_center(self) -> QPointF:
        """Get the center position in scene coordinates."""
        return self.mapToScene(QPointF(0, 0))

    def hoverEnterEvent(self, event: object) -> None:
        """Handle mouse hover enter."""
        self._is_hovered = True
        self._update_appearance()
        self.signals.hovered.emit(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: object) -> None:
        """Handle mouse hover leave."""
        self._is_hovered = False
        self._update_appearance()
        self.signals.hovered.emit(False)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: object) -> None:
        """Handle mouse press to start connection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.signals.connection_started.emit(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        """Handle mouse release to complete connection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.signals.connection_ended.emit(self)
        super().mouseReleaseEvent(event)


class PortLabelWidget(QGraphicsTextItem):
    """
    Text label displayed next to a port.

    Shows the port name in a readable format, positioned appropriately
    for input (right-aligned) or output (left-aligned) ports.
    """

    def __init__(
        self,
        port: BasePort,
        is_input: bool,
        parent: QGraphicsItem,
    ) -> None:
        """
        Initialize a port label.

        Args:
            port: The port model this label represents.
            is_input: True if this is for an input port.
            parent: Parent graphics item.
        """
        super().__init__(parent)

        self._port = port
        self._is_input = is_input

        # Set up appearance
        self.setDefaultTextColor(QColor("#CCCCCC"))
        font = QFont("Segoe UI", 9)
        self.setFont(font)

        # Set text (capitalize first letter, replace underscores)
        display_name = port.name.replace("_", " ").title()
        self.setPlainText(display_name)

        # Disable interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)

    @property
    def port(self) -> BasePort:
        """Get the port model."""
        return self._port

    @property
    def is_input(self) -> bool:
        """Check if this is for an input port."""
        return self._is_input

    def adjust_position(
        self,
        port_widget: PortWidget,
        node_width: float,
        has_inline_widget: bool = False,
        inline_widget_width: float = 0,
    ) -> None:
        """
        Adjust label position relative to its port widget.

        For input ports with inline widgets, the label is positioned after
        the inline widget. For output ports, positioning is unchanged.

        Args:
            port_widget: The associated port widget.
            node_width: Width of the parent node.
            has_inline_widget: Whether the port has an inline value widget.
            inline_widget_width: Width of the inline widget (including offset).
        """
        port_pos = port_widget.pos()
        text_width = self.boundingRect().width()
        text_height = self.boundingRect().height()

        if self._is_input:
            # Position to the right of the port (and inline widget if present)
            base_offset = PortWidget.PORT_RADIUS + 4
            if has_inline_widget:
                # Position after the inline widget
                x = port_pos.x() + base_offset + inline_widget_width + 4
            else:
                x = port_pos.x() + base_offset
            y = port_pos.y() - text_height / 2
        else:
            # Position to the left of the port (output ports don't have inline widgets)
            x = port_pos.x() - PortWidget.PORT_RADIUS - text_width - 4
            y = port_pos.y() - text_height / 2

        self.setPos(x, y)


def create_inline_widget_for_port(port: InputPort) -> Optional[InlineValueWidget]:
    """
    Factory method to create the appropriate inline widget based on port type.

    This function creates an InlineValueWidget subclass instance that is
    appropriate for the given input port's data type. It returns None for
    port types that should not have inline widgets (e.g., FLOW, OBJECT).

    Args:
        port: The InputPort to create an inline widget for.

    Returns:
        An InlineValueWidget instance appropriate for the port type,
        or None if the port type doesn't support inline editing.

    Examples:
        >>> port = InputPort("message", PortType.STRING)
        >>> widget = create_inline_widget_for_port(port)
        >>> isinstance(widget, StringInlineWidget)
        True

        >>> port = InputPort("count", PortType.INTEGER)
        >>> widget = create_inline_widget_for_port(port)
        >>> isinstance(widget, NumberInlineWidget)
        True

        >>> port = InputPort("flow_in", PortType.FLOW)
        >>> widget = create_inline_widget_for_port(port)
        >>> widget is None
        True

    Port Type to Widget Mapping:
        - STRING -> StringInlineWidget
        - INTEGER -> NumberInlineWidget (integer mode)
        - FLOAT -> NumberInlineWidget (float mode)
        - BOOLEAN -> BooleanInlineWidget
        - ANY -> GenericInlineWidget
        - LIST -> GenericInlineWidget (strict JSON array mode)
        - DICT -> GenericInlineWidget (strict JSON object mode)
        - FLOW -> None (no inline widget for execution flow)
        - OBJECT -> None (complex objects not editable inline)
    """
    from visualpython.nodes.views.inline_value_widget import (
        StringInlineWidget,
        NumberInlineWidget,
        BooleanInlineWidget,
        GenericInlineWidget,
    )

    port_type = port.port_type

    # FLOW and OBJECT types don't get inline widgets
    if port_type == PortTypeEnum.FLOW:
        return None
    if port_type == PortTypeEnum.OBJECT:
        return None

    # STRING type -> StringInlineWidget
    if port_type == PortTypeEnum.STRING:
        return StringInlineWidget(port)

    # INTEGER type -> NumberInlineWidget in integer mode
    if port_type == PortTypeEnum.INTEGER:
        return NumberInlineWidget(port)

    # FLOAT type -> NumberInlineWidget in float mode
    if port_type == PortTypeEnum.FLOAT:
        return NumberInlineWidget(port)

    # BOOLEAN type -> BooleanInlineWidget
    if port_type == PortTypeEnum.BOOLEAN:
        return BooleanInlineWidget(port)

    # ANY, LIST, DICT types -> GenericInlineWidget
    if port_type in (PortTypeEnum.ANY, PortTypeEnum.LIST, PortTypeEnum.DICT):
        return GenericInlineWidget(port)

    # Fallback: Unknown port types don't get inline widgets
    return None
