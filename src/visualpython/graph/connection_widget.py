"""
Connection visual widget for rendering bezier curves between node ports.

This module provides the QGraphicsItem-based visual representation of connections
between node ports, displayed as smooth curved bezier paths.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QObject
from PyQt6.QtGui import (
    QColor,
    QPen,
    QPainter,
    QPainterPath,
    QBrush,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

if TYPE_CHECKING:
    from visualpython.nodes.views.port_widget import PortWidget
    from visualpython.nodes.models.port import Connection


# Port type color mapping (same as port_widget.py for consistency)
CONNECTION_TYPE_COLORS: dict[str, str] = {
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


class ConnectionWidgetSignals(QObject):
    """Signals for connection widget events."""

    selected_changed = pyqtSignal(bool)  # Emits selection state
    delete_requested = pyqtSignal(object)  # Emits ConnectionWidget reference
    hovered = pyqtSignal(bool)  # Emits hover state


class ConnectionWidget(QGraphicsPathItem):
    """
    Visual representation of a connection between two node ports.

    Renders a smooth bezier curve from source port to target port.
    The curve automatically updates when connected nodes move.

    Attributes:
        LINE_WIDTH: Width of the connection line in pixels.
        LINE_WIDTH_SELECTED: Width when selected.
        LINE_WIDTH_HOVERED: Width when hovered.
        CONTROL_POINT_OFFSET_RATIO: Ratio for control point positioning.
    """

    LINE_WIDTH = 2.5
    LINE_WIDTH_SELECTED = 4.0
    LINE_WIDTH_HOVERED = 3.5
    CONTROL_POINT_OFFSET_RATIO = 0.5
    MINIMUM_CONTROL_OFFSET = 50

    def __init__(
        self,
        connection: Connection,
        source_port_widget: Optional[PortWidget] = None,
        target_port_widget: Optional[PortWidget] = None,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """
        Initialize a connection widget.

        Args:
            connection: The connection model this widget represents.
            source_port_widget: The source (output) port widget.
            target_port_widget: The target (input) port widget.
            parent: Optional parent graphics item.
        """
        super().__init__(parent)

        self._connection = connection
        self._source_port_widget = source_port_widget
        self._target_port_widget = target_port_widget

        # Visual state
        self._is_hovered = False
        self._color = QColor("#FFFFFF")

        # Signals
        self.signals = ConnectionWidgetSignals()

        # Configure item
        self._setup_item()
        self._setup_color()

        # Update port widget connection states
        self._update_port_connection_states(connected=True)

        # Initial path update
        self.update_path()

    def _setup_item(self) -> None:
        """Configure the graphics item flags and behavior."""
        # Enable selection
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

        # Enable hover effects
        self.setAcceptHoverEvents(True)

        # Set Z-value (connections below nodes, above grid)
        self.setZValue(0.5)

        # Set cursor
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _setup_color(self) -> None:
        """Set up the connection color based on port type."""
        if self._source_port_widget:
            port_type_name = self._source_port_widget.port.port_type.name
        elif self._target_port_widget:
            port_type_name = self._target_port_widget.port.port_type.name
        else:
            port_type_name = "ANY"

        color_hex = CONNECTION_TYPE_COLORS.get(port_type_name, "#FFFFFF")
        self._color = QColor(color_hex)
        self._update_pen()

    def _update_pen(self) -> None:
        """Update the pen based on current state."""
        if self.isSelected():
            pen = QPen(self._color.lighter(120), self.LINE_WIDTH_SELECTED)
        elif self._is_hovered:
            pen = QPen(self._color.lighter(110), self.LINE_WIDTH_HOVERED)
        else:
            pen = QPen(self._color, self.LINE_WIDTH)

        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

    @property
    def connection(self) -> Connection:
        """Get the connection model."""
        return self._connection

    @property
    def source_port_widget(self) -> Optional[PortWidget]:
        """Get the source port widget."""
        return self._source_port_widget

    @source_port_widget.setter
    def source_port_widget(self, widget: Optional[PortWidget]) -> None:
        """Set the source port widget."""
        self._source_port_widget = widget
        self._setup_color()
        self.update_path()

    @property
    def target_port_widget(self) -> Optional[PortWidget]:
        """Get the target port widget."""
        return self._target_port_widget

    @target_port_widget.setter
    def target_port_widget(self, widget: Optional[PortWidget]) -> None:
        """Set the target port widget."""
        self._target_port_widget = widget
        self.update_path()

    @property
    def connection_key(self) -> str:
        """Get a unique key identifying this connection."""
        return (
            f"{self._connection.source_node_id}:"
            f"{self._connection.source_port_name}:"
            f"{self._connection.target_node_id}:"
            f"{self._connection.target_port_name}"
        )

    def update_path(self, target_pos: Optional[QPointF] = None) -> None:
        """
        Update the bezier path based on current port positions.

        Args:
            target_pos: Optional override for target position (used during dragging).
        """
        # Get source position
        if self._source_port_widget:
            source_pos = self._source_port_widget.get_scene_center()
        else:
            source_pos = QPointF(0, 0)

        # Get target position
        if target_pos is not None:
            end_pos = target_pos
        elif self._target_port_widget:
            end_pos = self._target_port_widget.get_scene_center()
        else:
            end_pos = source_pos

        # Calculate the bezier path
        path = self._calculate_bezier_path(source_pos, end_pos)
        self.setPath(path)

    def _calculate_bezier_path(
        self, start: QPointF, end: QPointF
    ) -> QPainterPath:
        """
        Calculate a smooth cubic bezier path between two points.

        The control points are positioned to create a natural S-curve
        that flows horizontally from output to input ports.

        Args:
            start: Start point (source port center).
            end: End point (target port center).

        Returns:
            A QPainterPath representing the bezier curve.
        """
        path = QPainterPath()
        path.moveTo(start)

        # Calculate horizontal distance
        dx = end.x() - start.x()
        dy = end.y() - start.y()

        # Calculate control point offset
        # Use a minimum offset for very close ports
        control_offset = max(
            abs(dx) * self.CONTROL_POINT_OFFSET_RATIO,
            self.MINIMUM_CONTROL_OFFSET
        )

        # For backwards connections (end before start), adjust control points
        if dx < 0:
            # Connection going backwards - make a wider curve
            control_offset = max(control_offset, abs(dx) + 100)

        # Create control points
        # Control point 1: extends right from source (output port)
        cp1 = QPointF(start.x() + control_offset, start.y())

        # Control point 2: extends left from target (input port)
        cp2 = QPointF(end.x() - control_offset, end.y())

        # Create cubic bezier curve
        path.cubicTo(cp1, cp2, end)

        return path

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the connection."""
        # Update pen based on current state (selection may have changed)
        self._update_pen()

        # Draw the path
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.pen())
        painter.drawPath(self.path())

        # Draw selection indicator (small circles at endpoints)
        if self.isSelected():
            self._draw_endpoint_indicators(painter)

    def _draw_endpoint_indicators(self, painter: QPainter) -> None:
        """Draw small circles at the endpoints when selected."""
        path = self.path()
        if path.isEmpty():
            return

        # Get start and end points
        start = path.pointAtPercent(0)
        end = path.pointAtPercent(1)

        # Draw indicator circles
        indicator_radius = 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color.lighter(130)))

        painter.drawEllipse(start, indicator_radius, indicator_radius)
        painter.drawEllipse(end, indicator_radius, indicator_radius)

    def shape(self) -> QPainterPath:
        """Return a wider shape for easier selection."""
        # Create a stroke around the path for easier clicking
        stroker_path = QPainterPath()

        path = self.path()
        if path.isEmpty():
            return stroker_path

        # Use Qt's path stroker to create a wider selection area
        from PyQt6.QtGui import QPainterPathStroker

        stroker = QPainterPathStroker()
        stroker.setWidth(15)  # Selection tolerance
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        return stroker.createStroke(path)

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle with some padding."""
        rect = super().boundingRect()
        # Add padding for the wider selection shape and endpoint indicators
        padding = 10
        return rect.adjusted(-padding, -padding, padding, padding)

    def hoverEnterEvent(self, event: object) -> None:
        """Handle mouse hover enter."""
        self._is_hovered = True
        self._update_pen()
        self.signals.hovered.emit(True)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: object) -> None:
        """Handle mouse hover leave."""
        self._is_hovered = False
        self._update_pen()
        self.signals.hovered.emit(False)
        self.update()
        super().hoverLeaveEvent(event)

    def itemChange(
        self, change: QGraphicsItem.GraphicsItemChange, value: object
    ) -> object:
        """Handle item changes such as selection."""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.signals.selected_changed.emit(bool(value))
            self._update_pen()
            self.update()

        return super().itemChange(change, value)

    def keyPressEvent(self, event: object) -> None:
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Delete:
            self.signals.delete_requested.emit(self)
        else:
            super().keyPressEvent(event)

    def _update_port_connection_states(self, connected: bool) -> None:
        """
        Update the connection state of the attached port widgets.

        This method is called when the connection is established or removed to
        update the `is_connected` property of the port widgets. This in turn
        controls the visibility/enabled state of inline value widgets.

        For input ports (target), this directly enables/disables the inline widget
        since input ports can only have one connection.

        For output ports (source), we query the port model to determine if there
        are other connections remaining, since output ports can have multiple
        connections.

        Args:
            connected: True if the connection is being established,
                       False if it's being removed.
        """
        # Update source port widget (output port)
        # Output ports can have multiple connections, so we check the model
        if self._source_port_widget is not None:
            if connected:
                self._source_port_widget.is_connected = True
            else:
                # Query the port model to see if there are other connections
                source_port = self._source_port_widget.port
                self._source_port_widget.is_connected = source_port.is_connected()

        # Update target port widget (input port)
        # This is the key for inline widgets - when an input port becomes
        # connected, its inline value widget should be disabled.
        # Input ports can only have one connection, so we can directly set the state.
        if self._target_port_widget is not None:
            if connected:
                self._target_port_widget.is_connected = True
            else:
                # Query the port model to verify connection state
                target_port = self._target_port_widget.port
                self._target_port_widget.is_connected = target_port.is_connected()

    def notify_disconnected(self) -> None:
        """
        Notify the connection widget that it's being disconnected/removed.

        Call this method before removing the connection widget from the scene
        to properly update the port widgets' connection states. This ensures
        that inline value widgets become re-enabled when connections are removed.

        Note:
            This should be called by the scene when removing the connection.
            The port widgets will update their inline widget states accordingly.
        """
        self._update_port_connection_states(connected=False)

    def highlight(self, enabled: bool) -> None:
        """
        Highlight the connection for execution visualization.

        Args:
            enabled: Whether to enable highlight.
        """
        if enabled:
            # Use a brighter, thicker line for highlighted connections
            pen = QPen(self._color.lighter(150), self.LINE_WIDTH_SELECTED + 1)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self.setPen(pen)
        else:
            self._update_pen()

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"ConnectionWidget("
            f"source='{self._connection.source_node_id[:8]}...:{self._connection.source_port_name}', "
            f"target='{self._connection.target_node_id[:8]}...:{self._connection.target_port_name}')"
        )


class TemporaryConnectionWidget(QGraphicsPathItem):
    """
    A temporary connection widget used during connection dragging.

    This widget is shown while the user drags from a port to create
    a new connection. It follows the mouse cursor until released.
    """

    LINE_WIDTH = 2.5

    def __init__(
        self,
        source_port_widget: PortWidget,
        is_from_output: bool = True,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """
        Initialize a temporary connection widget.

        Args:
            source_port_widget: The port widget where the drag started.
            is_from_output: True if dragging from output, False if from input.
            parent: Optional parent graphics item.
        """
        super().__init__(parent)

        self._source_port_widget = source_port_widget
        self._is_from_output = is_from_output
        self._end_pos = source_port_widget.get_scene_center()
        self._is_valid_target = True  # Track if current target is valid

        # Store colors for valid/invalid states
        port_type_name = self._source_port_widget.port.port_type.name
        color_hex = CONNECTION_TYPE_COLORS.get(port_type_name, "#FFFFFF")
        self._valid_color = QColor(color_hex)
        self._invalid_color = QColor("#FF4444")  # Red for invalid

        # Set up appearance
        self._setup_appearance()

        # Set Z-value
        self.setZValue(2)  # Above nodes during dragging

        # Initial path update
        self.update_path(self._end_pos)

    def _setup_appearance(self) -> None:
        """Configure the visual appearance."""
        # Create dashed pen for temporary connection
        pen = QPen(self._valid_color, self.LINE_WIDTH)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)

    def set_valid_target(self, is_valid: bool) -> None:
        """
        Set whether the current target is a valid connection point.

        Args:
            is_valid: True if connection would be valid, False otherwise.
        """
        if self._is_valid_target == is_valid:
            return

        self._is_valid_target = is_valid
        color = self._valid_color if is_valid else self._invalid_color
        pen = QPen(color, self.LINE_WIDTH)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)

    @property
    def is_valid_target(self) -> bool:
        """Check if current target is valid."""
        return self._is_valid_target

    @property
    def source_port_widget(self) -> PortWidget:
        """Get the source port widget."""
        return self._source_port_widget

    @property
    def is_from_output(self) -> bool:
        """Check if dragging from an output port."""
        return self._is_from_output

    def update_path(self, end_pos: QPointF) -> None:
        """
        Update the bezier path to the given end position.

        Args:
            end_pos: The current mouse/end position in scene coordinates.
        """
        self._end_pos = end_pos

        # Get source position
        source_pos = self._source_port_widget.get_scene_center()

        # If dragging from input (reverse direction), swap start/end
        if not self._is_from_output:
            source_pos, end_pos = end_pos, source_pos

        # Calculate the bezier path
        path = self._calculate_bezier_path(source_pos, end_pos)
        self.setPath(path)

    def _calculate_bezier_path(
        self, start: QPointF, end: QPointF
    ) -> QPainterPath:
        """
        Calculate a smooth cubic bezier path between two points.

        Args:
            start: Start point.
            end: End point.

        Returns:
            A QPainterPath representing the bezier curve.
        """
        path = QPainterPath()
        path.moveTo(start)

        # Calculate horizontal distance
        dx = end.x() - start.x()

        # Calculate control point offset
        control_offset = max(
            abs(dx) * ConnectionWidget.CONTROL_POINT_OFFSET_RATIO,
            ConnectionWidget.MINIMUM_CONTROL_OFFSET
        )

        # For backwards connections, adjust control points
        if dx < 0:
            control_offset = max(control_offset, abs(dx) + 100)

        # Create control points
        cp1 = QPointF(start.x() + control_offset, start.y())
        cp2 = QPointF(end.x() - control_offset, end.y())

        # Create cubic bezier curve
        path.cubicTo(cp1, cp2, end)

        return path

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the temporary connection."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.pen())
        painter.drawPath(self.path())
