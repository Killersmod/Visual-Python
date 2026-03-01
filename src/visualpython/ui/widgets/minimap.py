"""
Minimap widget for VisualPython.

This module provides a minimap widget that displays an overview of the entire
node graph, allowing quick navigation in large complex graphs.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QMouseEvent
from PyQt6.QtWidgets import QWidget, QSizePolicy

if TYPE_CHECKING:
    from visualpython.graph.view import NodeGraphView
    from visualpython.graph.scene import NodeGraphScene


class MinimapWidget(QWidget):
    """
    A minimap widget that displays an overview of the entire node graph.

    The widget shows:
    - A scaled-down view of all nodes in the graph
    - A highlighted rectangle representing the current viewport
    - Click-to-navigate functionality for quick panning

    Signals:
        navigation_requested: Emitted when user clicks to navigate (scene_x, scene_y).

    Example:
        >>> minimap = MinimapWidget()
        >>> minimap.set_graph_view(graph_view)
        >>> # Minimap now shows overview and tracks viewport changes
    """

    # Minimap appearance settings
    BACKGROUND_COLOR = QColor("#1a1a1a")
    NODE_COLOR = QColor("#3d5a80")
    NODE_BORDER_COLOR = QColor("#5a7a9a")
    CONNECTION_COLOR = QColor("#4a4a4a")
    VIEWPORT_COLOR = QColor("#00AAFF")
    VIEWPORT_FILL_COLOR = QColor(0, 170, 255, 40)  # Semi-transparent blue
    MIN_NODE_SIZE = 4  # Minimum node size in minimap pixels
    PADDING = 10  # Padding around the content in minimap

    # Signal emitted when user clicks to navigate
    navigation_requested = pyqtSignal(float, float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the minimap widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._graph_view: Optional["NodeGraphView"] = None
        self._content_rect: QRectF = QRectF()  # Bounding rect of all nodes in scene coords
        self._viewport_rect: QRectF = QRectF()  # Current viewport in scene coords
        self._scale: float = 1.0  # Scale factor from scene to minimap
        self._offset: QPointF = QPointF()  # Offset for centering content
        self._is_dragging: bool = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        self.setMinimumSize(150, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Set tooltip
        self.setToolTip("Click to navigate to that position in the graph")

    def set_graph_view(self, graph_view: "NodeGraphView") -> None:
        """
        Set the graph view to display in the minimap.

        This connects the minimap to the graph view for tracking changes.

        Args:
            graph_view: The NodeGraphView to display.
        """
        self._graph_view = graph_view

        # Connect to view signals for updates
        graph_view.zoom_changed.connect(self._on_view_changed)
        graph_view.view_panned.connect(self._on_view_changed)

        # Connect to scene signals for content changes
        scene = graph_view.graph_scene
        scene.scene_modified.connect(self._on_scene_modified)
        scene.node_widget_added.connect(lambda _: self._on_scene_modified())
        scene.node_widget_removed.connect(lambda _: self._on_scene_modified())

        # Initial update
        self._update_content_rect()
        self._update_viewport_rect()
        self.update()

    def _on_view_changed(self, *args) -> None:
        """Handle view changes (zoom or pan)."""
        self._update_viewport_rect()
        self.update()

    def _on_scene_modified(self) -> None:
        """Handle scene content modifications."""
        self._update_content_rect()
        self._update_viewport_rect()
        self.update()

    def _update_content_rect(self) -> None:
        """Update the content bounding rectangle from the scene."""
        if not self._graph_view:
            self._content_rect = QRectF()
            return

        scene = self._graph_view.graph_scene
        node_widgets = scene.get_all_node_widgets()

        if not node_widgets:
            self._content_rect = QRectF(-500, -500, 1000, 1000)  # Default centered rect
            return

        # Calculate bounding rect of all nodes
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')

        for widget in node_widgets:
            rect = widget.sceneBoundingRect()
            min_x = min(min_x, rect.left())
            min_y = min(min_y, rect.top())
            max_x = max(max_x, rect.right())
            max_y = max(max_y, rect.bottom())

        # Add some padding
        padding = 100
        self._content_rect = QRectF(
            min_x - padding,
            min_y - padding,
            (max_x - min_x) + 2 * padding,
            (max_y - min_y) + 2 * padding
        )

    def _update_viewport_rect(self) -> None:
        """Update the viewport rectangle from the view."""
        if not self._graph_view:
            self._viewport_rect = QRectF()
            return

        visible = self._graph_view.get_visible_rect()
        self._viewport_rect = QRectF(visible[0], visible[1], visible[2], visible[3])

    def _calculate_transform(self) -> None:
        """Calculate the scale and offset for drawing."""
        if self._content_rect.isEmpty():
            self._scale = 1.0
            self._offset = QPointF()
            return

        # Available space in minimap (with padding)
        available_width = self.width() - 2 * self.PADDING
        available_height = self.height() - 2 * self.PADDING

        if available_width <= 0 or available_height <= 0:
            self._scale = 1.0
            self._offset = QPointF()
            return

        # Calculate scale to fit content
        scale_x = available_width / self._content_rect.width()
        scale_y = available_height / self._content_rect.height()
        self._scale = min(scale_x, scale_y)

        # Calculate offset to center content
        scaled_width = self._content_rect.width() * self._scale
        scaled_height = self._content_rect.height() * self._scale
        self._offset = QPointF(
            self.PADDING + (available_width - scaled_width) / 2,
            self.PADDING + (available_height - scaled_height) / 2
        )

    def _scene_to_minimap(self, scene_pos: QPointF) -> QPointF:
        """
        Convert scene coordinates to minimap coordinates.

        Args:
            scene_pos: Position in scene coordinates.

        Returns:
            Position in minimap widget coordinates.
        """
        return QPointF(
            self._offset.x() + (scene_pos.x() - self._content_rect.left()) * self._scale,
            self._offset.y() + (scene_pos.y() - self._content_rect.top()) * self._scale
        )

    def _minimap_to_scene(self, minimap_pos: QPointF) -> QPointF:
        """
        Convert minimap coordinates to scene coordinates.

        Args:
            minimap_pos: Position in minimap widget coordinates.

        Returns:
            Position in scene coordinates.
        """
        if self._scale == 0:
            return QPointF()

        return QPointF(
            self._content_rect.left() + (minimap_pos.x() - self._offset.x()) / self._scale,
            self._content_rect.top() + (minimap_pos.y() - self._offset.y()) / self._scale
        )

    def _scene_rect_to_minimap(self, scene_rect: QRectF) -> QRectF:
        """
        Convert a scene rectangle to minimap coordinates.

        Args:
            scene_rect: Rectangle in scene coordinates.

        Returns:
            Rectangle in minimap widget coordinates.
        """
        top_left = self._scene_to_minimap(scene_rect.topLeft())
        return QRectF(
            top_left.x(),
            top_left.y(),
            scene_rect.width() * self._scale,
            scene_rect.height() * self._scale
        )

    def paintEvent(self, event) -> None:
        """Paint the minimap."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw background
        painter.fillRect(self.rect(), self.BACKGROUND_COLOR)

        if not self._graph_view:
            # Draw placeholder text
            painter.setPen(QPen(QColor("#666666")))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No graph connected"
            )
            return

        # Calculate transform
        self._calculate_transform()

        # Draw connections
        self._draw_connections(painter)

        # Draw nodes
        self._draw_nodes(painter)

        # Draw viewport rectangle
        self._draw_viewport(painter)

    def _draw_nodes(self, painter: QPainter) -> None:
        """
        Draw all nodes as small rectangles.

        Args:
            painter: The QPainter to use.
        """
        if not self._graph_view:
            return

        scene = self._graph_view.graph_scene
        node_widgets = scene.get_all_node_widgets()

        painter.setPen(QPen(self.NODE_BORDER_COLOR, 1))
        painter.setBrush(QBrush(self.NODE_COLOR))

        for widget in node_widgets:
            scene_rect = widget.sceneBoundingRect()
            minimap_rect = self._scene_rect_to_minimap(scene_rect)

            # Ensure minimum size for visibility
            if minimap_rect.width() < self.MIN_NODE_SIZE:
                minimap_rect.setWidth(self.MIN_NODE_SIZE)
            if minimap_rect.height() < self.MIN_NODE_SIZE:
                minimap_rect.setHeight(self.MIN_NODE_SIZE)

            painter.drawRoundedRect(minimap_rect, 2, 2)

    def _draw_connections(self, painter: QPainter) -> None:
        """
        Draw all connections as lines.

        Args:
            painter: The QPainter to use.
        """
        if not self._graph_view:
            return

        scene = self._graph_view.graph_scene
        connection_widgets = scene.get_all_connection_widgets()

        painter.setPen(QPen(self.CONNECTION_COLOR, 1))

        for widget in connection_widgets:
            # Get connection endpoints from the widget's path
            path = widget.path()
            if not path.isEmpty():
                # Get start and end points
                start = path.elementAt(0)
                end = path.elementAt(path.elementCount() - 1)

                start_pos = self._scene_to_minimap(QPointF(start.x, start.y))
                end_pos = self._scene_to_minimap(QPointF(end.x, end.y))

                painter.drawLine(start_pos, end_pos)

    def _draw_viewport(self, painter: QPainter) -> None:
        """
        Draw the current viewport rectangle.

        Args:
            painter: The QPainter to use.
        """
        if self._viewport_rect.isEmpty():
            return

        minimap_viewport = self._scene_rect_to_minimap(self._viewport_rect)

        # Draw filled rectangle
        painter.fillRect(minimap_viewport, self.VIEWPORT_FILL_COLOR)

        # Draw border
        painter.setPen(QPen(self.VIEWPORT_COLOR, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(minimap_viewport)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press for navigation.

        Args:
            event: The mouse event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._navigate_to(event.position())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse move for drag navigation.

        Args:
            event: The mouse event.
        """
        if self._is_dragging:
            self._navigate_to(event.position())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse release.

        Args:
            event: The mouse event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _navigate_to(self, minimap_pos: QPointF) -> None:
        """
        Navigate the graph view to the clicked position.

        Args:
            minimap_pos: Position clicked in minimap coordinates.
        """
        if not self._graph_view:
            return

        # Convert minimap position to scene coordinates
        scene_pos = self._minimap_to_scene(minimap_pos)

        # Center the view on this position
        self._graph_view.centerOn(scene_pos)

        # Emit signal for external handlers
        self.navigation_requested.emit(scene_pos.x(), scene_pos.y())

        # Update display
        self._update_viewport_rect()
        self.update()

    def refresh(self) -> None:
        """Refresh the minimap display."""
        self._update_content_rect()
        self._update_viewport_rect()
        self.update()
