"""
Node-related commands for undo/redo functionality.

This module provides commands for adding, removing, moving, and renaming nodes.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from visualpython.commands.command import Command
from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph
    from visualpython.nodes.registry import NodeRegistry
    from visualpython.nodes.models.port import Connection


class AddNodeCommand(Command):
    """
    Command to add a node to the graph.

    Stores the node data for undo/redo, using the node registry to recreate nodes.
    """

    def __init__(
        self,
        graph: "Graph",
        node_type: str,
        x: float,
        y: float,
        registry: "NodeRegistry",
        name: Optional[str] = None,
        add_widget_callback: Optional[Callable[[BaseNode], None]] = None,
        remove_widget_callback: Optional[Callable[[str], None]] = None,
        **node_kwargs: Any,
    ) -> None:
        """
        Initialize the add node command.

        Args:
            graph: The graph to add the node to.
            node_type: The type of node to create.
            x: X position for the node.
            y: Y position for the node.
            registry: Node registry for creating nodes.
            name: Optional custom name for the node.
            add_widget_callback: Callback to create the visual widget.
            remove_widget_callback: Callback to remove the visual widget.
            **node_kwargs: Additional keyword arguments to pass to the node constructor.
                           For example, 'code' for CodeNode default template.
        """
        super().__init__(graph)
        self._node_type = node_type
        self._x = x
        self._y = y
        self._registry = registry
        self._name = name
        self._add_widget_callback = add_widget_callback
        self._remove_widget_callback = remove_widget_callback
        self._node_kwargs = node_kwargs
        self._node_id: Optional[str] = None
        self._node_data: Optional[Dict[str, Any]] = None

    def execute(self) -> bool:
        """Add the node to the graph."""
        try:
            node = self._registry.create_node(
                node_type=self._node_type,
                name=self._name,
                position=Position(self._x, self._y),
                **self._node_kwargs,
            )

            if node is None:
                return False

            # If we have stored node data from a previous undo, restore the ID
            if self._node_id:
                node._id = self._node_id

            self._graph.add_node(node)
            self._node_id = node.id
            self._node_data = node.to_dict()

            # Create visual widget
            if self._add_widget_callback:
                self._add_widget_callback(node)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute AddNodeCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Remove the node from the graph."""
        if not self._node_id:
            return False

        try:
            # Remove visual widget first
            if self._remove_widget_callback:
                self._remove_widget_callback(self._node_id)

            # Remove from graph
            node = self._graph.remove_node(self._node_id)
            if node:
                # Store the node data for potential redo
                self._node_data = node.to_dict()
            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo AddNodeCommand", exc_info=True)
            return False

    def redo(self) -> bool:
        """Re-add the node using stored data."""
        return self.execute()

    @property
    def description(self) -> str:
        """Get command description."""
        return "Add Node"

    @property
    def node_id(self) -> Optional[str]:
        """Get the ID of the added node."""
        return self._node_id


class RemoveNodeCommand(Command):
    """
    Command to remove a node from the graph.

    Stores complete node data and connections for restoration on undo.
    """

    def __init__(
        self,
        graph: "Graph",
        node_id: str,
        registry: "NodeRegistry",
        add_widget_callback: Optional[Callable[[BaseNode], None]] = None,
        remove_widget_callback: Optional[Callable[[str], None]] = None,
        add_connection_callback: Optional[Callable[..., None]] = None,
        remove_connection_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        """
        Initialize the remove node command.

        Args:
            graph: The graph to remove the node from.
            node_id: ID of the node to remove.
            registry: Node registry for recreating nodes.
            add_widget_callback: Callback to create visual widget.
            remove_widget_callback: Callback to remove visual widget.
            add_connection_callback: Callback to add connection widget.
            remove_connection_callback: Callback to remove connection widget.
        """
        super().__init__(graph)
        self._node_id = node_id
        self._registry = registry
        self._add_widget_callback = add_widget_callback
        self._remove_widget_callback = remove_widget_callback
        self._add_connection_callback = add_connection_callback
        self._remove_connection_callback = remove_connection_callback
        self._node_data: Optional[Dict[str, Any]] = None
        self._connections_data: List[Dict[str, str]] = []

    def execute(self) -> bool:
        """Remove the node from the graph."""
        try:
            node = self._graph.get_node(self._node_id)
            if not node:
                return False

            # Store node data for undo
            self._node_data = node.to_dict()

            # Store and remove all connections involving this node
            self._connections_data = []
            incoming = self._graph.get_incoming_connections(self._node_id)
            outgoing = self._graph.get_outgoing_connections(self._node_id)

            for conn in incoming + outgoing:
                self._connections_data.append(conn.to_dict())
                # Remove connection widget
                if self._remove_connection_callback:
                    self._remove_connection_callback(conn)

            # Remove visual widget
            if self._remove_widget_callback:
                self._remove_widget_callback(self._node_id)

            # Remove from graph (this also removes connections)
            self._graph.remove_node(self._node_id)
            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute RemoveNodeCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Restore the node and its connections."""
        if not self._node_data:
            return False

        try:
            # Recreate the node
            node = self._registry.create_node_from_dict(self._node_data)
            if not node:
                return False

            self._graph.add_node(node)

            # Create visual widget
            if self._add_widget_callback:
                self._add_widget_callback(node)

            # Restore connections
            for conn_data in self._connections_data:
                try:
                    connection = self._graph.connect(
                        source_node_id=conn_data["source_node_id"],
                        source_port_name=conn_data["source_port_name"],
                        target_node_id=conn_data["target_node_id"],
                        target_port_name=conn_data["target_port_name"],
                        validate=False,
                    )
                    if self._add_connection_callback and connection:
                        self._add_connection_callback(connection)
                except Exception:
                    logger.debug("Failed to restore connection during undo", exc_info=True)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo RemoveNodeCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        return "Delete Node"


class MoveNodeCommand(Command):
    """
    Command to move a node to a new position.

    Supports merging consecutive moves of the same node.
    """

    def __init__(
        self,
        graph: "Graph",
        node_id: str,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
        update_widget_callback: Optional[Callable[[str, float, float], None]] = None,
    ) -> None:
        """
        Initialize the move node command.

        Args:
            graph: The graph containing the node.
            node_id: ID of the node to move.
            old_x: Original X position.
            old_y: Original Y position.
            new_x: New X position.
            new_y: New Y position.
            update_widget_callback: Callback to update visual widget position.
        """
        super().__init__(graph)
        self._node_id = node_id
        self._old_x = old_x
        self._old_y = old_y
        self._new_x = new_x
        self._new_y = new_y
        self._update_widget_callback = update_widget_callback

    def execute(self) -> bool:
        """Move the node to the new position."""
        try:
            node = self._graph.get_node(self._node_id)
            if not node:
                return False

            node.position = Position(self._new_x, self._new_y)

            if self._update_widget_callback:
                self._update_widget_callback(self._node_id, self._new_x, self._new_y)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute MoveNodeCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Move the node back to the original position."""
        try:
            node = self._graph.get_node(self._node_id)
            if not node:
                return False

            node.position = Position(self._old_x, self._old_y)

            if self._update_widget_callback:
                self._update_widget_callback(self._node_id, self._old_x, self._old_y)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo MoveNodeCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        return "Move Node"

    def can_merge(self, other: Command) -> bool:
        """Check if we can merge with another move command for the same node."""
        if not isinstance(other, MoveNodeCommand):
            return False
        return other._node_id == self._node_id

    def merge(self, other: Command) -> bool:
        """Merge another move command, keeping original position and taking new end position."""
        if not isinstance(other, MoveNodeCommand):
            return False
        if other._node_id != self._node_id:
            return False

        # Keep our original position, update to the new end position
        self._new_x = other._new_x
        self._new_y = other._new_y
        return True


class RenameNodeCommand(Command):
    """
    Command to rename a node.
    """

    def __init__(
        self,
        graph: "Graph",
        node_id: str,
        old_name: str,
        new_name: str,
        update_widget_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize the rename node command.

        Args:
            graph: The graph containing the node.
            node_id: ID of the node to rename.
            old_name: Original name.
            new_name: New name.
            update_widget_callback: Callback to update visual widget.
        """
        super().__init__(graph)
        self._node_id = node_id
        self._old_name = old_name
        self._new_name = new_name
        self._update_widget_callback = update_widget_callback

    def execute(self) -> bool:
        """Rename the node."""
        try:
            node = self._graph.get_node(self._node_id)
            if not node:
                return False

            node.name = self._new_name

            if self._update_widget_callback:
                self._update_widget_callback(self._node_id)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute RenameNodeCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Restore the original name."""
        try:
            node = self._graph.get_node(self._node_id)
            if not node:
                return False

            node.name = self._old_name

            if self._update_widget_callback:
                self._update_widget_callback(self._node_id)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo RenameNodeCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        return "Rename Node"


class DuplicateNodesCommand(Command):
    """
    Command to duplicate selected nodes and their internal connections.

    Creates copies of the selected nodes with new IDs at an offset position,
    preserving connections between the duplicated nodes.
    """

    # Offset for duplicated nodes (slightly to the right and down)
    DUPLICATE_OFFSET_X = 50
    DUPLICATE_OFFSET_Y = 50

    def __init__(
        self,
        graph: "Graph",
        node_ids: List[str],
        registry: "NodeRegistry",
        add_node_callback: Optional[Callable[[BaseNode], None]] = None,
        remove_node_callback: Optional[Callable[[str], None]] = None,
        add_connection_callback: Optional[Callable[["Connection"], None]] = None,
        remove_connection_callback: Optional[Callable[["Connection"], None]] = None,
    ) -> None:
        """
        Initialize the duplicate nodes command.

        Args:
            graph: The graph containing the nodes.
            node_ids: List of node IDs to duplicate.
            registry: Node registry for creating nodes.
            add_node_callback: Callback to create visual widget for a node.
            remove_node_callback: Callback to remove visual widget for a node.
            add_connection_callback: Callback to create visual widget for a connection.
            remove_connection_callback: Callback to remove visual widget for a connection.
        """
        super().__init__(graph)
        self._source_node_ids = node_ids
        self._registry = registry
        self._add_node_callback = add_node_callback
        self._remove_node_callback = remove_node_callback
        self._add_connection_callback = add_connection_callback
        self._remove_connection_callback = remove_connection_callback
        self._new_node_ids: List[str] = []
        self._id_mapping: Dict[str, str] = {}
        self._created_connections: List[Dict[str, str]] = []

    def execute(self) -> bool:
        """Duplicate the selected nodes and their internal connections."""
        try:
            self._new_node_ids = []
            self._id_mapping = {}
            self._created_connections = []

            source_ids_set = set(self._source_node_ids)

            # First pass: create all duplicate nodes
            for old_id in self._source_node_ids:
                node = self._graph.get_node(old_id)
                if not node:
                    continue

                # Generate new ID
                new_id = str(uuid.uuid4())
                self._id_mapping[old_id] = new_id

                # Get serialized node data and modify it
                node_data = node.to_dict()
                node_data["id"] = new_id

                # Offset position
                if "position" in node_data:
                    node_data["position"]["x"] += self.DUPLICATE_OFFSET_X
                    node_data["position"]["y"] += self.DUPLICATE_OFFSET_Y

                # Clear port connections (we'll recreate internal ones)
                for port_data in node_data.get("input_ports", []):
                    port_data["connection"] = None
                for port_data in node_data.get("output_ports", []):
                    port_data["connections"] = []

                # Create the new node
                new_node = self._registry.create_node_from_dict(node_data)
                if new_node:
                    self._graph.add_node(new_node)
                    self._new_node_ids.append(new_id)

                    if self._add_node_callback:
                        self._add_node_callback(new_node)

            # Second pass: recreate internal connections
            for old_id in self._source_node_ids:
                outgoing = self._graph.get_outgoing_connections(old_id)

                for conn in outgoing:
                    # Only duplicate connections where both source and target are in selection
                    if conn.target_node_id in source_ids_set:
                        new_source_id = self._id_mapping.get(old_id)
                        new_target_id = self._id_mapping.get(conn.target_node_id)

                        if new_source_id and new_target_id:
                            try:
                                new_connection = self._graph.connect(
                                    source_node_id=new_source_id,
                                    source_port_name=conn.source_port_name,
                                    target_node_id=new_target_id,
                                    target_port_name=conn.target_port_name,
                                    validate=False,
                                )
                                if new_connection:
                                    self._created_connections.append({
                                        "source_node_id": new_source_id,
                                        "source_port_name": conn.source_port_name,
                                        "target_node_id": new_target_id,
                                        "target_port_name": conn.target_port_name,
                                    })
                                    if self._add_connection_callback:
                                        self._add_connection_callback(new_connection)
                            except Exception:
                                logger.debug("Failed to duplicate connection", exc_info=True)

            self._executed = True
            return len(self._new_node_ids) > 0
        except Exception:
            logger.debug("Failed to execute DuplicateNodesCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Remove all duplicated nodes and connections."""
        try:
            # Remove connections first
            for conn_data in self._created_connections:
                connection = self._graph.get_connection(
                    conn_data["source_node_id"],
                    conn_data["source_port_name"],
                    conn_data["target_node_id"],
                    conn_data["target_port_name"],
                )
                if connection:
                    if self._remove_connection_callback:
                        self._remove_connection_callback(connection)
                    self._graph.disconnect(
                        conn_data["source_node_id"],
                        conn_data["source_port_name"],
                        conn_data["target_node_id"],
                        conn_data["target_port_name"],
                    )

            # Remove the duplicated nodes
            for node_id in self._new_node_ids:
                if self._remove_node_callback:
                    self._remove_node_callback(node_id)
                self._graph.remove_node(node_id)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo DuplicateNodesCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        count = len(self._source_node_ids)
        return f"Duplicate {count} Node{'s' if count != 1 else ''}"

    @property
    def new_node_ids(self) -> List[str]:
        """Get the IDs of the duplicated nodes."""
        return self._new_node_ids
