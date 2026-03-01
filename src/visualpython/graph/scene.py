"""
Node graph scene for rendering the node graph canvas.

This module provides the QGraphicsScene subclass that manages all visual
elements of the node graph including nodes, connections, and the background grid.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPen, QPainter, QBrush
from PyQt6.QtWidgets import QGraphicsScene
from visualpython.utils.logging import get_logger

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QGraphicsSceneMouseEvent
    from visualpython.nodes.models.base_node import BaseNode
    from visualpython.nodes.views.node_widget import NodeWidget
    from visualpython.nodes.views.port_widget import PortWidget
    from visualpython.nodes.models.port import Connection
    from visualpython.graph.connection_widget import ConnectionWidget, TemporaryConnectionWidget
    from visualpython.nodes.models.node_group import NodeGroup
    from visualpython.nodes.views.group_widget import GroupWidget

logger = get_logger(__name__)


class NodeGraphScene(QGraphicsScene):
    """
    Graphics scene for the node graph editor.

    Provides the canvas where nodes and connections are rendered, including
    a customizable grid background and coordinate system management.

    Signals:
        scene_modified: Emitted when the scene content is modified.
        selection_changed_custom: Emitted when selection changes (with selected items).

    Attributes:
        GRID_SIZE: Size of the small grid squares in pixels.
        GRID_SIZE_LARGE: Size of the large grid squares in pixels.
        SCENE_WIDTH: Default scene width in pixels.
        SCENE_HEIGHT: Default scene height in pixels.
    """

    GRID_SIZE = 20
    GRID_SIZE_LARGE = 100
    SCENE_WIDTH = 64000
    SCENE_HEIGHT = 64000

    scene_modified = pyqtSignal()
    selection_changed_custom = pyqtSignal(list)
    node_widget_added = pyqtSignal(str)  # node_id
    node_widget_removed = pyqtSignal(str)  # node_id
    node_delete_requested = pyqtSignal(str)  # node_id
    node_name_changed = pyqtSignal(str, str, str)  # node_id, old_name, new_name
    connection_widget_added = pyqtSignal(str)  # connection_key
    connection_widget_removed = pyqtSignal(str)  # connection_key
    connection_delete_requested = pyqtSignal(object)  # Connection model object
    group_widget_added = pyqtSignal(str)  # group_id
    group_widget_removed = pyqtSignal(str)  # group_id
    group_delete_requested = pyqtSignal(str)  # group_id
    group_collapsed_changed = pyqtSignal(str, bool)  # group_id, collapsed
    open_subgraph_requested = pyqtSignal(str)  # node_id - emitted when user double-clicks a subgraph node
    node_inline_value_changed = pyqtSignal(str, str, object, object)  # node_id, port_name, old_value, new_value
    node_move_finished = pyqtSignal(str, float, float, float, float)  # node_id, old_x, old_y, new_x, new_y

    def __init__(self, parent: Optional[object] = None) -> None:
        """
        Initialize the node graph scene.

        Args:
            parent: Optional parent object.
        """
        super().__init__(parent)

        # Colors for the grid
        self._background_color = QColor("#1e1e1e")
        self._grid_color_light = QColor("#2a2a2a")
        self._grid_color_dark = QColor("#333333")

        # Grid visibility
        self._show_grid = True

        # Grid snapping
        self._snap_to_grid_enabled = False

        # Node widget tracking
        self._node_widgets: Dict[str, "NodeWidget"] = {}

        # Connection widget tracking
        self._connection_widgets: Dict[str, "ConnectionWidget"] = {}

        # Group widget tracking
        self._group_widgets: Dict[str, "GroupWidget"] = {}

        # Temporary connection for dragging
        self._temp_connection: Optional["TemporaryConnectionWidget"] = None

        # Set up scene
        self._setup_scene()

        # Connect internal signals
        self.selectionChanged.connect(self._on_selection_changed)

    def _setup_scene(self) -> None:
        """Configure the scene dimensions and background."""
        # Set scene rectangle centered at origin
        self.setSceneRect(
            -self.SCENE_WIDTH // 2,
            -self.SCENE_HEIGHT // 2,
            self.SCENE_WIDTH,
            self.SCENE_HEIGHT,
        )

        # Set background brush
        self.setBackgroundBrush(QBrush(self._background_color))

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """
        Draw the grid background.

        Args:
            painter: The QPainter to use for drawing.
            rect: The rectangle area to draw.
        """
        super().drawBackground(painter, rect)

        if not self._show_grid:
            return

        # Get the visible area
        left = int(rect.left())
        right = int(rect.right())
        top = int(rect.top())
        bottom = int(rect.bottom())

        # Calculate grid line positions
        first_left = left - (left % self.GRID_SIZE)
        first_top = top - (top % self.GRID_SIZE)

        # Prepare pens for grid lines
        pen_light = QPen(self._grid_color_light)
        pen_light.setWidth(1)

        pen_dark = QPen(self._grid_color_dark)
        pen_dark.setWidth(2)

        # Draw small grid lines
        lines_light = []
        lines_dark = []

        # Vertical lines
        for x in range(first_left, right, self.GRID_SIZE):
            if x % self.GRID_SIZE_LARGE == 0:
                lines_dark.append((x, top, x, bottom))
            else:
                lines_light.append((x, top, x, bottom))

        # Horizontal lines
        for y in range(first_top, bottom, self.GRID_SIZE):
            if y % self.GRID_SIZE_LARGE == 0:
                lines_dark.append((left, y, right, y))
            else:
                lines_light.append((left, y, right, y))

        # Draw light grid lines
        painter.setPen(pen_light)
        for x1, y1, x2, y2 in lines_light:
            painter.drawLine(x1, y1, x2, y2)

        # Draw dark grid lines
        painter.setPen(pen_dark)
        for x1, y1, x2, y2 in lines_dark:
            painter.drawLine(x1, y1, x2, y2)

    def _on_selection_changed(self) -> None:
        """Handle selection changes and emit custom signal with items."""
        # Check if this scene's C++ object has been deleted
        if sip.isdeleted(self):
            return

        try:
            selected_items = self.selectedItems()
            self.selection_changed_custom.emit(selected_items)
        except RuntimeError:
            # Handle case where scene is deleted during the call
            logger.debug("Scene C++ object deleted during selection change", exc_info=True)
            return

    # Public API

    @property
    def show_grid(self) -> bool:
        """Check if the grid is visible."""
        return self._show_grid

    @show_grid.setter
    def show_grid(self, visible: bool) -> None:
        """
        Set grid visibility.

        Args:
            visible: Whether the grid should be visible.
        """
        self._show_grid = visible
        self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.BackgroundLayer)

    @property
    def background_color(self) -> QColor:
        """Get the background color."""
        return self._background_color

    @background_color.setter
    def background_color(self, color: QColor) -> None:
        """
        Set the background color.

        Args:
            color: The new background color.
        """
        self._background_color = color
        self.setBackgroundBrush(QBrush(color))
        self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.BackgroundLayer)

    @property
    def grid_color_light(self) -> QColor:
        """Get the light grid line color."""
        return self._grid_color_light

    @grid_color_light.setter
    def grid_color_light(self, color: QColor) -> None:
        """
        Set the light grid line color.

        Args:
            color: The new color for light grid lines.
        """
        self._grid_color_light = color
        self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.BackgroundLayer)

    @property
    def grid_color_dark(self) -> QColor:
        """Get the dark grid line color."""
        return self._grid_color_dark

    @grid_color_dark.setter
    def grid_color_dark(self, color: QColor) -> None:
        """
        Set the dark grid line color.

        Args:
            color: The new color for dark grid lines.
        """
        self._grid_color_dark = color
        self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.BackgroundLayer)

    def clear_scene(self) -> None:
        """Clear all items from the scene."""
        self.clear()
        self.scene_modified.emit()

    def get_items_at(self, x: float, y: float) -> list:
        """
        Get all items at a specific scene coordinate.

        Args:
            x: X coordinate in scene space.
            y: Y coordinate in scene space.

        Returns:
            List of items at the specified position.
        """
        from PyQt6.QtCore import QPointF
        return self.items(QPointF(x, y))

    def get_items_in_rect(self, rect: QRectF) -> list:
        """
        Get all items within a rectangle.

        Args:
            rect: Rectangle in scene coordinates.

        Returns:
            List of items within the rectangle.
        """
        return self.items(rect)

    @property
    def snap_to_grid_enabled(self) -> bool:
        """Check if grid snapping is enabled."""
        return self._snap_to_grid_enabled

    @snap_to_grid_enabled.setter
    def snap_to_grid_enabled(self, enabled: bool) -> None:
        """
        Enable or disable grid snapping.

        Args:
            enabled: Whether grid snapping should be enabled.
        """
        self._snap_to_grid_enabled = enabled

    def snap_to_grid(self, x: float, y: float) -> tuple[float, float]:
        """
        Snap coordinates to the nearest grid point.

        Args:
            x: X coordinate.
            y: Y coordinate.

        Returns:
            Tuple of (snapped_x, snapped_y) coordinates.
        """
        snapped_x = round(x / self.GRID_SIZE) * self.GRID_SIZE
        snapped_y = round(y / self.GRID_SIZE) * self.GRID_SIZE
        return (snapped_x, snapped_y)

    # Node Widget Management

    def add_node_widget(self, node: "BaseNode") -> "NodeWidget":
        """
        Create and add a node widget for the given node model.

        Args:
            node: The node model to create a widget for.

        Returns:
            The created NodeWidget.

        Raises:
            ValueError: If a widget for this node already exists.
        """
        if node.id in self._node_widgets:
            raise ValueError(f"Node widget already exists for node {node.id}")

        # Create the appropriate widget based on node type
        widget = self._create_widget_for_node(node)

        # Add to scene and tracking
        self.addItem(widget)
        self._node_widgets[node.id] = widget

        # Connect widget signals
        widget.signals.position_changed.connect(self._on_node_position_changed)
        widget.signals.move_finished.connect(self._on_node_move_finished)
        widget.signals.delete_requested.connect(self._on_node_delete_requested)
        widget.signals.name_changed.connect(self._on_node_name_changed)
        widget.signals.inline_value_changed.connect(self._on_node_inline_value_changed)

        # Connect subgraph-specific signals if this is a SubgraphNodeWidget
        if hasattr(widget.signals, 'open_subgraph_requested'):
            widget.signals.open_subgraph_requested.connect(
                self._on_open_subgraph_requested
            )

        # Emit signal
        self.node_widget_added.emit(node.id)
        self.scene_modified.emit()

        return widget

    def _create_widget_for_node(self, node: "BaseNode") -> "NodeWidget":
        """
        Create the appropriate widget type for a given node.

        This factory method selects specialized widget classes for nodes that
        require custom visual representations (like ForLoopNode).

        Args:
            node: The node model to create a widget for.

        Returns:
            The appropriate NodeWidget subclass instance.
        """
        from visualpython.nodes.views.node_widget import NodeWidget

        # Check for specialized widget types based on node_type
        if node.node_type == "for_loop":
            from visualpython.nodes.views.for_loop_widget import ForLoopNodeWidget
            return ForLoopNodeWidget(node)

        if node.node_type == "if":
            from visualpython.nodes.views.if_node_widget import IfNodeWidget
            return IfNodeWidget(node)

        if node.node_type == "while_loop":
            from visualpython.nodes.views.while_loop_widget import WhileLoopNodeWidget
            return WhileLoopNodeWidget(node)

        if node.node_type == "subgraph":
            from visualpython.nodes.views.subgraph_widget import SubgraphNodeWidget
            return SubgraphNodeWidget(node)

        if node.node_type == "code":
            from visualpython.nodes.views.code_node_widget import CodeNodeWidget
            return CodeNodeWidget(node)

        # Default to standard NodeWidget
        return NodeWidget(node)

    def remove_node_widget(self, node_id: str) -> bool:
        """
        Remove a node widget from the scene.

        Args:
            node_id: The ID of the node whose widget to remove.

        Returns:
            True if the widget was removed, False if not found.
        """
        widget = self._node_widgets.pop(node_id, None)
        if widget:
            self.removeItem(widget)
            self.node_widget_removed.emit(node_id)
            self.scene_modified.emit()
            return True
        return False

    def get_node_widget(self, node_id: str) -> Optional["NodeWidget"]:
        """
        Get a node widget by node ID.

        Args:
            node_id: The ID of the node.

        Returns:
            The NodeWidget if found, None otherwise.
        """
        return self._node_widgets.get(node_id)

    def get_all_node_widgets(self) -> List["NodeWidget"]:
        """
        Get all node widgets in the scene.

        Returns:
            List of all NodeWidget instances.
        """
        return list(self._node_widgets.values())

    def get_selected_node_widgets(self) -> List["NodeWidget"]:
        """
        Get all currently selected node widgets.

        Returns:
            List of selected NodeWidget instances.
        """
        from visualpython.nodes.views.node_widget import NodeWidget

        # Check if this scene's C++ object has been deleted
        if sip.isdeleted(self):
            return []

        try:
            return [
                item for item in self.selectedItems()
                if isinstance(item, NodeWidget)
            ]
        except RuntimeError:
            # Handle case where scene is deleted during the call
            logger.debug("Scene C++ object deleted while getting selected nodes", exc_info=True)
            return []

    def clear_node_widgets(self) -> None:
        """Remove all node widgets from the scene."""
        for node_id in list(self._node_widgets.keys()):
            self.remove_node_widget(node_id)

    def update_all_node_widgets(self) -> None:
        """Update all node widgets to reflect their model state."""
        for widget in self._node_widgets.values():
            widget.sync_from_model()

    def _on_node_position_changed(
        self, node_id: str, x: float, y: float
    ) -> None:
        """
        Handle node position change from widget.

        Args:
            node_id: The ID of the node.
            x: New X position.
            y: New Y position.
        """
        # Update connection paths when node moves
        self.update_connections_for_node(node_id)
        self.scene_modified.emit()

    def _on_node_move_finished(
        self, node_id: str, old_x: float, old_y: float, new_x: float, new_y: float
    ) -> None:
        """Forward node move finished to controller for undo/redo."""
        self.node_move_finished.emit(node_id, old_x, old_y, new_x, new_y)

    def _on_node_delete_requested(self, node_id: str) -> None:
        """
        Handle delete request from node widget.

        Args:
            node_id: The ID of the node to delete.
        """
        # Emit signal to notify controller to remove from data model
        self.node_delete_requested.emit(node_id)

    def _on_node_name_changed(
        self, node_id: str, old_name: str, new_name: str
    ) -> None:
        """
        Handle node name change from widget.

        Args:
            node_id: The ID of the node.
            old_name: The previous name.
            new_name: The new name.
        """
        # Emit signal to notify controller about name change
        self.node_name_changed.emit(node_id, old_name, new_name)
        self.scene_modified.emit()

    def _on_node_inline_value_changed(
        self, node_id: str, port_name: str, old_value: object, new_value: object
    ) -> None:
        """Forward inline value change to controller for undo/redo."""
        self.node_inline_value_changed.emit(node_id, port_name, old_value, new_value)
        self.scene_modified.emit()

    def _on_open_subgraph_requested(self, node_id: str) -> None:
        """
        Handle request to open a subgraph for editing.

        This is triggered when the user double-clicks a SubgraphNodeWidget.
        The signal is forwarded to the controller which will open the
        subgraph in a new tab.

        Args:
            node_id: The ID of the subgraph node to open.
        """
        self.open_subgraph_requested.emit(node_id)

    # Connection Widget Management

    def add_connection_widget(
        self, connection: "Connection"
    ) -> Optional["ConnectionWidget"]:
        """
        Create and add a connection widget for the given connection model.

        Args:
            connection: The connection model to create a widget for.

        Returns:
            The created ConnectionWidget, or None if ports not found.

        Raises:
            ValueError: If a widget for this connection already exists.
        """
        from visualpython.graph.connection_widget import ConnectionWidget

        # Create connection key
        connection_key = (
            f"{connection.source_node_id}:"
            f"{connection.source_port_name}:"
            f"{connection.target_node_id}:"
            f"{connection.target_port_name}"
        )

        if connection_key in self._connection_widgets:
            raise ValueError(f"Connection widget already exists for {connection_key}")

        # Find source and target port widgets
        source_node_widget = self._node_widgets.get(connection.source_node_id)
        target_node_widget = self._node_widgets.get(connection.target_node_id)

        if not source_node_widget or not target_node_widget:
            return None

        source_port_widget = source_node_widget.get_output_port_widget(
            connection.source_port_name
        )
        target_port_widget = target_node_widget.get_input_port_widget(
            connection.target_port_name
        )

        if not source_port_widget or not target_port_widget:
            return None

        # Create the widget
        widget = ConnectionWidget(
            connection=connection,
            source_port_widget=source_port_widget,
            target_port_widget=target_port_widget,
        )

        # Add to scene and tracking
        self.addItem(widget)
        self._connection_widgets[connection_key] = widget

        # Connect widget signals
        widget.signals.delete_requested.connect(self._on_connection_delete_requested)

        # Emit signal
        self.connection_widget_added.emit(connection_key)
        self.scene_modified.emit()

        return widget

    def remove_connection_widget(self, connection_key: str) -> bool:
        """
        Remove a connection widget from the scene.

        This method notifies the connection widget that it's being disconnected,
        which allows it to update the port widgets' connection states. This is
        important for re-enabling inline value widgets when connections are removed.

        Args:
            connection_key: The unique key identifying the connection.

        Returns:
            True if the widget was removed, False if not found.
        """
        widget = self._connection_widgets.pop(connection_key, None)
        if widget:
            # Notify the connection widget so it can update port states
            # This re-enables inline value widgets on input ports
            widget.notify_disconnected()
            self.removeItem(widget)
            self.connection_widget_removed.emit(connection_key)
            self.scene_modified.emit()
            return True
        return False

    def remove_connection_widget_by_connection(
        self, connection: "Connection"
    ) -> bool:
        """
        Remove a connection widget by its connection model.

        Args:
            connection: The connection model.

        Returns:
            True if the widget was removed, False if not found.
        """
        connection_key = (
            f"{connection.source_node_id}:"
            f"{connection.source_port_name}:"
            f"{connection.target_node_id}:"
            f"{connection.target_port_name}"
        )
        return self.remove_connection_widget(connection_key)

    def get_connection_widget(
        self, connection_key: str
    ) -> Optional["ConnectionWidget"]:
        """
        Get a connection widget by connection key.

        Args:
            connection_key: The unique key identifying the connection.

        Returns:
            The ConnectionWidget if found, None otherwise.
        """
        return self._connection_widgets.get(connection_key)

    def get_all_connection_widgets(self) -> List["ConnectionWidget"]:
        """
        Get all connection widgets in the scene.

        Returns:
            List of all ConnectionWidget instances.
        """
        return list(self._connection_widgets.values())

    def get_selected_connection_widgets(self) -> List["ConnectionWidget"]:
        """
        Get all currently selected connection widgets.

        Returns:
            List of selected ConnectionWidget instances.
        """
        from visualpython.graph.connection_widget import ConnectionWidget

        # Check if this scene's C++ object has been deleted
        if sip.isdeleted(self):
            return []

        try:
            return [
                item for item in self.selectedItems()
                if isinstance(item, ConnectionWidget)
            ]
        except RuntimeError:
            # Handle case where scene is deleted during the call
            logger.debug("Scene C++ object deleted while getting selected connections", exc_info=True)
            return []

    def get_connections_for_node(
        self, node_id: str
    ) -> List["ConnectionWidget"]:
        """
        Get all connection widgets connected to a specific node.

        Args:
            node_id: The ID of the node.

        Returns:
            List of ConnectionWidget instances connected to the node.
        """
        result = []
        for widget in self._connection_widgets.values():
            conn = widget.connection
            if conn.source_node_id == node_id or conn.target_node_id == node_id:
                result.append(widget)
        return result

    def update_connections_for_node(self, node_id: str) -> None:
        """
        Update the visual paths of all connections attached to a node.

        This should be called when a node moves to update the bezier curves.

        Args:
            node_id: The ID of the node that moved.
        """
        for widget in self.get_connections_for_node(node_id):
            widget.update_path()

    def clear_connection_widgets(self) -> None:
        """Remove all connection widgets from the scene."""
        for connection_key in list(self._connection_widgets.keys()):
            self.remove_connection_widget(connection_key)

    def _on_connection_delete_requested(
        self, widget: "ConnectionWidget"
    ) -> None:
        """
        Handle delete request from connection widget.

        Args:
            widget: The connection widget requesting deletion.
        """
        # Get the connection model before removing the widget
        connection = widget.connection

        # Emit signal to notify controller to remove from data model
        self.connection_delete_requested.emit(connection)

        # Remove the widget from the scene
        self.remove_connection_widget(widget.connection_key)

    # Group Widget Management

    def add_group_widget(self, group: "NodeGroup") -> "GroupWidget":
        """
        Create and add a group widget for the given group model.

        Args:
            group: The node group model to create a widget for.

        Returns:
            The created GroupWidget.

        Raises:
            ValueError: If a widget for this group already exists.
        """
        from visualpython.nodes.views.group_widget import GroupWidget

        if group.id in self._group_widgets:
            raise ValueError(f"Group widget already exists for group {group.id}")

        # Create the widget
        widget = GroupWidget(group)

        # Add to scene and tracking (set lower z-value so groups are below nodes)
        self.addItem(widget)
        self._group_widgets[group.id] = widget

        # Connect widget signals
        widget.signals.position_changed.connect(self._on_group_position_changed)
        widget.signals.collapsed_changed.connect(self._on_group_collapsed_changed)
        widget.signals.delete_requested.connect(self._on_group_delete_requested)

        # Emit signal
        self.group_widget_added.emit(group.id)
        self.scene_modified.emit()

        return widget

    def remove_group_widget(self, group_id: str) -> bool:
        """
        Remove a group widget from the scene.

        Args:
            group_id: The ID of the group whose widget to remove.

        Returns:
            True if the widget was removed, False if not found.
        """
        widget = self._group_widgets.pop(group_id, None)
        if widget:
            self.removeItem(widget)
            self.group_widget_removed.emit(group_id)
            self.scene_modified.emit()
            return True
        return False

    def get_group_widget(self, group_id: str) -> Optional["GroupWidget"]:
        """
        Get a group widget by group ID.

        Args:
            group_id: The ID of the group.

        Returns:
            The GroupWidget if found, None otherwise.
        """
        return self._group_widgets.get(group_id)

    def get_all_group_widgets(self) -> List["GroupWidget"]:
        """
        Get all group widgets in the scene.

        Returns:
            List of all GroupWidget instances.
        """
        return list(self._group_widgets.values())

    def get_selected_group_widgets(self) -> List["GroupWidget"]:
        """
        Get all currently selected group widgets.

        Returns:
            List of selected GroupWidget instances.
        """
        from visualpython.nodes.views.group_widget import GroupWidget

        # Check if this scene's C++ object has been deleted
        if sip.isdeleted(self):
            return []

        try:
            return [
                item for item in self.selectedItems()
                if isinstance(item, GroupWidget)
            ]
        except RuntimeError:
            # Handle case where scene is deleted during the call
            logger.debug("Scene C++ object deleted while getting selected groups", exc_info=True)
            return []

    def clear_group_widgets(self) -> None:
        """Remove all group widgets from the scene."""
        for group_id in list(self._group_widgets.keys()):
            self.remove_group_widget(group_id)

    def update_group_widget(self, group_id: str) -> None:
        """
        Update a group widget to reflect its model state.

        Args:
            group_id: The ID of the group to update.
        """
        widget = self._group_widgets.get(group_id)
        if widget:
            widget.sync_from_model()

    def update_group_bounds(self, group_id: str) -> None:
        """
        Update a group's bounds based on its contained nodes.

        Args:
            group_id: The ID of the group to update.
        """
        widget = self._group_widgets.get(group_id)
        if widget:
            # Collect positions of nodes in this group
            node_positions = {}
            for node_id in widget.group.node_ids:
                node_widget = self._node_widgets.get(node_id)
                if node_widget:
                    pos = node_widget.pos()
                    node_positions[node_id] = (
                        pos.x(),
                        pos.y(),
                        node_widget.width,
                        node_widget.height,
                    )
            widget.update_bounds_from_nodes(node_positions)

    def set_nodes_visibility_for_group(
        self, group_id: str, visible: bool
    ) -> None:
        """
        Show or hide nodes belonging to a group.

        Used when collapsing/expanding groups.

        Args:
            group_id: The ID of the group.
            visible: Whether the nodes should be visible.
        """
        widget = self._group_widgets.get(group_id)
        if widget:
            for node_id in widget.group.node_ids:
                node_widget = self._node_widgets.get(node_id)
                if node_widget:
                    node_widget.setVisible(visible)
                    # Also hide/show connections for this node
                    for conn_widget in self.get_connections_for_node(node_id):
                        conn_widget.setVisible(visible)

    def _on_group_position_changed(
        self, group_id: str, x: float, y: float
    ) -> None:
        """
        Handle group position change from widget.

        Args:
            group_id: The ID of the group.
            x: New X position.
            y: New Y position.
        """
        self.scene_modified.emit()

    def _on_group_collapsed_changed(
        self, group_id: str, collapsed: bool
    ) -> None:
        """
        Handle group collapsed state change.

        Args:
            group_id: The ID of the group.
            collapsed: Whether the group is now collapsed.
        """
        # Hide/show nodes in the group
        self.set_nodes_visibility_for_group(group_id, not collapsed)
        self.group_collapsed_changed.emit(group_id, collapsed)
        self.scene_modified.emit()

    def _on_group_delete_requested(self, group_id: str) -> None:
        """
        Handle delete request from group widget.

        Args:
            group_id: The ID of the group to delete.
        """
        self.group_delete_requested.emit(group_id)

    def calculate_bounds_for_nodes(self, node_ids: List[str]) -> tuple:
        """
        Calculate bounding box for a set of nodes.

        Args:
            node_ids: List of node IDs.

        Returns:
            Tuple of (x, y, width, height) for the bounding box.
        """
        from visualpython.nodes.models.node_group import GroupBounds

        if not node_ids:
            return GroupBounds()

        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        for node_id in node_ids:
            widget = self._node_widgets.get(node_id)
            if widget:
                pos = widget.pos()
                min_x = min(min_x, pos.x())
                min_y = min(min_y, pos.y())
                max_x = max(max_x, pos.x() + widget.width)
                max_y = max(max_y, pos.y() + widget.height)

        if min_x == float("inf"):
            return GroupBounds()

        padding = 30.0
        header_height = 32.0
        return GroupBounds(
            x=min_x - padding,
            y=min_y - padding - header_height,
            width=max_x - min_x + padding * 2,
            height=max_y - min_y + padding * 2 + header_height,
        )

    # Temporary Connection Management (for dragging)

    def start_temp_connection(
        self, port_widget: "PortWidget", is_from_output: bool = True
    ) -> "TemporaryConnectionWidget":
        """
        Start a temporary connection for dragging.

        Args:
            port_widget: The port widget where the drag started.
            is_from_output: True if dragging from output, False if from input.

        Returns:
            The created TemporaryConnectionWidget.
        """
        from visualpython.graph.connection_widget import TemporaryConnectionWidget
        from visualpython.nodes.views.port_widget import PortWidget

        # Remove any existing temp connection
        self.cancel_temp_connection()

        # Create new temp connection
        self._temp_connection = TemporaryConnectionWidget(
            source_port_widget=port_widget,
            is_from_output=is_from_output,
        )
        self.addItem(self._temp_connection)

        return self._temp_connection

    def update_temp_connection(self, scene_pos: "QPointF") -> None:
        """
        Update the temporary connection's end position.

        Args:
            scene_pos: The current mouse position in scene coordinates.
        """
        from PyQt6.QtCore import QPointF

        if self._temp_connection:
            self._temp_connection.update_path(scene_pos)

    def finish_temp_connection(
        self, target_port_widget: Optional["PortWidget"] = None
    ) -> Optional["TemporaryConnectionWidget"]:
        """
        Finish and remove the temporary connection.

        Args:
            target_port_widget: The target port widget, if connection was made.

        Returns:
            The temp connection widget (for extracting data) before removal.
        """
        temp = self._temp_connection
        if self._temp_connection:
            self.removeItem(self._temp_connection)
            self._temp_connection = None
        return temp

    def cancel_temp_connection(self) -> None:
        """Cancel and remove the temporary connection."""
        if self._temp_connection:
            self.removeItem(self._temp_connection)
            self._temp_connection = None

    @property
    def has_temp_connection(self) -> bool:
        """Check if there's an active temporary connection."""
        return self._temp_connection is not None

    @property
    def temp_connection(self) -> Optional["TemporaryConnectionWidget"]:
        """Get the current temporary connection widget."""
        return self._temp_connection

    # View Mode Support

    def set_view_mode_edit(self) -> None:
        """
        Set the scene to edit mode.

        In edit mode, all nodes are fully visible and interactive.
        This is the standard editing mode.
        """
        # Show all nodes fully
        for widget in self._node_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(1.0)
            widget.set_edit_mode(True)

        # Show all connections
        for widget in self._connection_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(1.0)

        # Show all groups
        for widget in self._group_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(1.0)

    def set_view_mode_run(self) -> None:
        """
        Set the scene to run/debug mode.

        In run mode, nodes show execution state highlighting.
        The view is optimized for watching execution progress.
        """
        # Show all nodes with execution state highlighting
        for widget in self._node_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(1.0)
            widget.set_run_mode(True)

        # Show all connections with flow highlighting
        for widget in self._connection_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(1.0)

        # Show groups
        for widget in self._group_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(0.5)  # Dim groups in run mode

    def set_view_mode_collapsed(self) -> None:
        """
        Set the scene to collapsed view mode.

        In collapsed mode, subgraph nodes are shown as compact boxes
        without expanding their internal content. This shows the
        high-level workflow structure.
        """
        # Process nodes based on type
        for widget in self._node_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(1.0)
            widget.set_edit_mode(True)

            # Collapse subgraph nodes
            if hasattr(widget, 'set_collapsed_view'):
                widget.set_collapsed_view(True)

        # Show all connections
        for widget in self._connection_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(1.0)

        # Collapse all groups
        for widget in self._group_widgets.values():
            widget.setVisible(True)
            if not widget.group.collapsed:
                widget.toggle_collapsed()

    def set_view_mode_expanded(self) -> None:
        """
        Set the scene to expanded view mode.

        In expanded mode, all nested workflows and subgraphs are
        visually expanded to show the complete execution flow.
        This is useful for understanding the full workflow.
        """
        # Expand all nodes
        for widget in self._node_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(1.0)
            widget.set_edit_mode(True)

            # Expand subgraph nodes
            if hasattr(widget, 'set_collapsed_view'):
                widget.set_collapsed_view(False)

        # Show all connections
        for widget in self._connection_widgets.values():
            widget.setVisible(True)
            widget.setOpacity(1.0)

        # Expand all groups
        for widget in self._group_widgets.values():
            widget.setVisible(True)
            if widget.group.collapsed:
                widget.toggle_collapsed()

    def highlight_execution_path(self, node_ids: List[str]) -> None:
        """
        Highlight a sequence of nodes as the execution path.

        Args:
            node_ids: List of node IDs in execution order.
        """
        # Dim all nodes first
        for widget in self._node_widgets.values():
            widget.setOpacity(0.3)

        # Highlight execution path nodes
        for node_id in node_ids:
            widget = self._node_widgets.get(node_id)
            if widget:
                widget.setOpacity(1.0)

        # Highlight connections between path nodes
        path_set = set(node_ids)
        for conn_widget in self._connection_widgets.values():
            conn = conn_widget.connection
            if conn.source_node_id in path_set and conn.target_node_id in path_set:
                conn_widget.setOpacity(1.0)
                conn_widget.highlight(True)
            else:
                conn_widget.setOpacity(0.3)
                conn_widget.highlight(False)

    def clear_execution_highlight(self) -> None:
        """Clear all execution path highlighting."""
        for widget in self._node_widgets.values():
            widget.setOpacity(1.0)

        for conn_widget in self._connection_widgets.values():
            conn_widget.setOpacity(1.0)
            conn_widget.highlight(False)
