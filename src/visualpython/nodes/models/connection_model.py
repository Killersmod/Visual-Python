"""
Connection model for managing node connections in VisualPython.

This module provides the ConnectionModel class that manages connections at the graph level,
enabling connection validation, graph traversal, cycle detection, and data flow tracking
between connected nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, TYPE_CHECKING

from visualpython.nodes.models.port import Connection, InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode
    from visualpython.execution.type_info import TypeInfo

logger = get_logger(__name__)


class ConnectionError(Exception):
    """Exception raised when a connection operation fails."""

    pass


class ConnectionValidationError(ConnectionError):
    """Exception raised when a connection fails validation."""

    pass


class CycleDetectedError(ConnectionError):
    """Exception raised when adding a connection would create a cycle."""

    pass


class DataFlowDirection(Enum):
    """Defines the direction of data flow analysis."""

    UPSTREAM = auto()
    """Follow connections from outputs back to inputs (toward data sources)."""

    DOWNSTREAM = auto()
    """Follow connections from inputs to outputs (toward data consumers)."""


class TraversalStrategy(Enum):
    """Defines the traversal strategy for walking the node graph."""

    DEPTH_FIRST = auto()
    """Depth-first search - explores as far as possible along each branch before backtracking."""

    BREADTH_FIRST = auto()
    """Breadth-first search - explores all neighbors at the current depth before moving deeper."""


@dataclass
class ConnectionInfo:
    """
    Extended information about a connection including node references.

    This provides a richer view of a connection that includes actual node
    and port references, not just IDs.

    Attributes:
        connection: The underlying Connection object.
        source_node: Reference to the source node.
        source_port: Reference to the source output port.
        target_node: Reference to the target node.
        target_port: Reference to the target input port.
    """

    connection: Connection
    source_node: BaseNode
    source_port: OutputPort
    target_node: BaseNode
    target_port: InputPort

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the connection info to a dictionary."""
        return {
            "connection": self.connection.to_dict(),
            "source_node_id": self.source_node.id,
            "source_port_name": self.source_port.name,
            "target_node_id": self.target_node.id,
            "target_port_name": self.target_port.name,
        }


@dataclass
class DataFlowPath:
    """
    Represents a path of data flow through connected nodes.

    Attributes:
        nodes: Ordered list of nodes in the path.
        connections: Ordered list of connections between nodes.
    """

    nodes: List[BaseNode] = field(default_factory=list)
    connections: List[Connection] = field(default_factory=list)

    def __len__(self) -> int:
        """Return the number of nodes in the path."""
        return len(self.nodes)

    def __iter__(self) -> Iterator[BaseNode]:
        """Iterate over nodes in the path."""
        return iter(self.nodes)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the data flow path to a dictionary."""
        return {
            "node_ids": [node.id for node in self.nodes],
            "connections": [conn.to_dict() for conn in self.connections],
        }


@dataclass
class TopologicalSortResult:
    """
    Result of a topological sort operation for execution ordering.

    This provides comprehensive information about the topological ordering of nodes,
    including execution levels for parallel execution support during script generation.

    Attributes:
        nodes: Ordered list of nodes in topological order (execution order).
        levels: Dictionary mapping execution level (0-indexed) to list of nodes at that level.
                Nodes at the same level have no dependencies between them and can execute in parallel.
        node_level_map: Dictionary mapping node IDs to their execution level.
        is_valid: True if the sort completed successfully (no cycles detected).
        critical_path: List of node IDs representing the longest dependency chain.
        independent_groups: List of groups of node IDs that have no dependencies between them.
    """

    nodes: List[BaseNode] = field(default_factory=list)
    levels: Dict[int, List[BaseNode]] = field(default_factory=dict)
    node_level_map: Dict[str, int] = field(default_factory=dict)
    is_valid: bool = True
    critical_path: List[str] = field(default_factory=list)
    independent_groups: List[List[str]] = field(default_factory=list)

    def __len__(self) -> int:
        """Return the number of nodes in the sorted order."""
        return len(self.nodes)

    def __iter__(self) -> Iterator[BaseNode]:
        """Iterate over nodes in topological order."""
        return iter(self.nodes)

    def get_level(self, node_id: str) -> int:
        """Get the execution level of a node. Returns -1 if not found."""
        return self.node_level_map.get(node_id, -1)

    def get_nodes_at_level(self, level: int) -> List[BaseNode]:
        """Get all nodes at a specific execution level."""
        return self.levels.get(level, [])

    def get_max_level(self) -> int:
        """Get the maximum execution level (depth of the graph)."""
        return max(self.levels.keys()) if self.levels else -1

    def get_parallel_groups(self) -> List[List[BaseNode]]:
        """
        Get groups of nodes that can be executed in parallel.

        Returns:
            List of node groups, where each group represents nodes at the same level.
        """
        return [self.levels[level] for level in sorted(self.levels.keys())]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the topological sort result to a dictionary."""
        return {
            "node_ids": [node.id for node in self.nodes],
            "levels": {
                level: [node.id for node in nodes]
                for level, nodes in self.levels.items()
            },
            "node_level_map": self.node_level_map.copy(),
            "is_valid": self.is_valid,
            "critical_path": self.critical_path.copy(),
            "independent_groups": [group.copy() for group in self.independent_groups],
        }


@dataclass
class TraversalResult:
    """
    Result of a graph traversal operation.

    Attributes:
        nodes: Ordered list of nodes in traversal order.
        connections: List of connections traversed.
        visit_order: Dictionary mapping node IDs to their visit order (0-indexed).
        depth_map: Dictionary mapping node IDs to their depth from start nodes.
    """

    nodes: List[BaseNode] = field(default_factory=list)
    connections: List[Connection] = field(default_factory=list)
    visit_order: Dict[str, int] = field(default_factory=dict)
    depth_map: Dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        """Return the number of nodes traversed."""
        return len(self.nodes)

    def __iter__(self) -> Iterator[BaseNode]:
        """Iterate over nodes in traversal order."""
        return iter(self.nodes)

    def get_node_at_order(self, order: int) -> Optional[BaseNode]:
        """Get the node at a specific visit order."""
        if 0 <= order < len(self.nodes):
            return self.nodes[order]
        return None

    def get_depth(self, node_id: str) -> int:
        """Get the depth of a node from start. Returns -1 if not found."""
        return self.depth_map.get(node_id, -1)

    def get_visit_order(self, node_id: str) -> int:
        """Get the visit order of a node. Returns -1 if not found."""
        return self.visit_order.get(node_id, -1)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the traversal result to a dictionary."""
        return {
            "node_ids": [node.id for node in self.nodes],
            "connections": [conn.to_dict() for conn in self.connections],
            "visit_order": self.visit_order.copy(),
            "depth_map": self.depth_map.copy(),
        }


class ConnectionModel:
    """
    Manages connections between nodes at the graph level.

    The ConnectionModel provides a centralized way to:
    - Create and remove connections between nodes
    - Validate connection compatibility
    - Detect cycles in the graph
    - Traverse the graph following data flow
    - Track and query relationships between nodes

    Example:
        >>> model = ConnectionModel()
        >>> model.add_node(code_node)
        >>> model.add_node(print_node)
        >>> model.connect(code_node.id, "result", print_node.id, "value")
        >>> paths = model.get_data_flow_paths(code_node)
        >>> model.has_cycle()
        False
    """

    def __init__(self) -> None:
        """Initialize an empty connection model."""
        # Node registry: maps node IDs to node instances
        self._nodes: Dict[str, BaseNode] = {}

        # Connection index for fast lookups
        # Maps (source_node_id, source_port_name) -> list of connections
        self._outgoing_connections: Dict[Tuple[str, str], List[Connection]] = {}

        # Maps (target_node_id, target_port_name) -> connection (single connection per input)
        self._incoming_connections: Dict[Tuple[str, str], Connection] = {}

        # All connections as a flat list for iteration
        self._connections: List[Connection] = []

    # Node Management

    def add_node(self, node: BaseNode) -> None:
        """
        Register a node with the connection model.

        Args:
            node: The node to add.

        Raises:
            ValueError: If a node with the same ID already exists.
        """
        if node.id in self._nodes:
            raise ValueError(f"Node with ID '{node.id}' already exists in the model")
        self._nodes[node.id] = node

    def remove_node(self, node_id: str) -> Optional[BaseNode]:
        """
        Remove a node and all its connections from the model.

        Args:
            node_id: The ID of the node to remove.

        Returns:
            The removed node, or None if not found.
        """
        if node_id not in self._nodes:
            return None

        node = self._nodes[node_id]

        # Remove all connections involving this node
        self.disconnect_all(node_id)

        # Remove from node registry
        del self._nodes[node_id]
        return node

    def get_node(self, node_id: str) -> Optional[BaseNode]:
        """
        Get a node by its ID.

        Args:
            node_id: The ID of the node to find.

        Returns:
            The node if found, None otherwise.
        """
        return self._nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        """Check if a node is registered in the model."""
        return node_id in self._nodes

    @property
    def nodes(self) -> List[BaseNode]:
        """Get a list of all registered nodes."""
        return list(self._nodes.values())

    @property
    def node_count(self) -> int:
        """Get the number of registered nodes."""
        return len(self._nodes)

    # Connection Management

    def connect(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
        validate: bool = True,
    ) -> Connection:
        """
        Create a connection between two ports.

        Args:
            source_node_id: ID of the source node.
            source_port_name: Name of the source output port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target input port.
            validate: Whether to validate the connection before creating it.

        Returns:
            The created Connection object.

        Raises:
            ConnectionValidationError: If validation fails.
            CycleDetectedError: If the connection would create a cycle.
            ValueError: If nodes or ports are not found.
        """
        # Get nodes
        source_node = self._nodes.get(source_node_id)
        target_node = self._nodes.get(target_node_id)

        if source_node is None:
            raise ValueError(f"Source node '{source_node_id}' not found in model")
        if target_node is None:
            raise ValueError(f"Target node '{target_node_id}' not found in model")

        # Get ports
        source_port = source_node.get_output_port(source_port_name)
        target_port = target_node.get_input_port(target_port_name)

        if source_port is None:
            raise ValueError(
                f"Output port '{source_port_name}' not found on node '{source_node_id}'"
            )
        if target_port is None:
            raise ValueError(
                f"Input port '{target_port_name}' not found on node '{target_node_id}'"
            )

        # Validate if requested
        if validate:
            self._validate_connection(source_node, source_port, target_node, target_port)

        # Create the connection
        connection = Connection(
            source_node_id=source_node_id,
            source_port_name=source_port_name,
            target_node_id=target_node_id,
            target_port_name=target_port_name,
        )

        # Check for existing connection on input port and disconnect if present
        existing = self._incoming_connections.get((target_node_id, target_port_name))
        if existing:
            self.disconnect(
                existing.source_node_id,
                existing.source_port_name,
                existing.target_node_id,
                existing.target_port_name,
            )

        # Register the connection in indexes
        outgoing_key = (source_node_id, source_port_name)
        if outgoing_key not in self._outgoing_connections:
            self._outgoing_connections[outgoing_key] = []
        self._outgoing_connections[outgoing_key].append(connection)

        incoming_key = (target_node_id, target_port_name)
        self._incoming_connections[incoming_key] = connection

        self._connections.append(connection)

        # Update ports
        source_port.connect(connection)
        target_port.connect(connection)

        return connection

    def disconnect(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> Optional[Connection]:
        """
        Remove a connection between two ports.

        Args:
            source_node_id: ID of the source node.
            source_port_name: Name of the source output port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target input port.

        Returns:
            The removed Connection, or None if not found.
        """
        # Find and remove from outgoing index
        outgoing_key = (source_node_id, source_port_name)
        outgoing_list = self._outgoing_connections.get(outgoing_key, [])
        removed_connection = None

        for i, conn in enumerate(outgoing_list):
            if conn.target_node_id == target_node_id and conn.target_port_name == target_port_name:
                removed_connection = outgoing_list.pop(i)
                if not outgoing_list:
                    del self._outgoing_connections[outgoing_key]
                break

        if removed_connection is None:
            return None

        # Remove from incoming index
        incoming_key = (target_node_id, target_port_name)
        if incoming_key in self._incoming_connections:
            del self._incoming_connections[incoming_key]

        # Remove from flat list
        self._connections.remove(removed_connection)

        # Update ports
        source_node = self._nodes.get(source_node_id)
        target_node = self._nodes.get(target_node_id)

        if source_node:
            source_port = source_node.get_output_port(source_port_name)
            if source_port:
                source_port.disconnect(target_node_id, target_port_name)

        if target_node:
            target_port = target_node.get_input_port(target_port_name)
            if target_port:
                target_port.disconnect()

        return removed_connection

    def disconnect_all(self, node_id: str) -> List[Connection]:
        """
        Remove all connections involving a node.

        Args:
            node_id: The ID of the node.

        Returns:
            List of removed connections.
        """
        removed: List[Connection] = []

        # Find all connections involving this node
        connections_to_remove = [
            conn for conn in self._connections
            if conn.source_node_id == node_id or conn.target_node_id == node_id
        ]

        for conn in connections_to_remove:
            result = self.disconnect(
                conn.source_node_id,
                conn.source_port_name,
                conn.target_node_id,
                conn.target_port_name,
            )
            if result:
                removed.append(result)

        return removed

    def disconnect_port(
        self,
        node_id: str,
        port_name: str,
        is_input: bool,
    ) -> List[Connection]:
        """
        Remove all connections from a specific port.

        Args:
            node_id: The ID of the node.
            port_name: The name of the port.
            is_input: True if this is an input port, False for output.

        Returns:
            List of removed connections.
        """
        removed: List[Connection] = []

        if is_input:
            # Input ports have at most one connection
            incoming_key = (node_id, port_name)
            if incoming_key in self._incoming_connections:
                conn = self._incoming_connections[incoming_key]
                result = self.disconnect(
                    conn.source_node_id,
                    conn.source_port_name,
                    conn.target_node_id,
                    conn.target_port_name,
                )
                if result:
                    removed.append(result)
        else:
            # Output ports can have multiple connections
            outgoing_key = (node_id, port_name)
            connections_to_remove = self._outgoing_connections.get(outgoing_key, []).copy()
            for conn in connections_to_remove:
                result = self.disconnect(
                    conn.source_node_id,
                    conn.source_port_name,
                    conn.target_node_id,
                    conn.target_port_name,
                )
                if result:
                    removed.append(result)

        return removed

    @property
    def connections(self) -> List[Connection]:
        """Get a list of all connections."""
        return self._connections.copy()

    @property
    def connection_count(self) -> int:
        """Get the number of connections."""
        return len(self._connections)

    def get_connection(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> Optional[Connection]:
        """
        Get a specific connection by its endpoints.

        Returns:
            The connection if found, None otherwise.
        """
        outgoing_key = (source_node_id, source_port_name)
        for conn in self._outgoing_connections.get(outgoing_key, []):
            if conn.target_node_id == target_node_id and conn.target_port_name == target_port_name:
                return conn
        return None

    def get_connection_info(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> Optional[ConnectionInfo]:
        """
        Get extended information about a connection.

        Returns:
            ConnectionInfo if found, None otherwise.
        """
        conn = self.get_connection(
            source_node_id, source_port_name, target_node_id, target_port_name
        )
        if conn is None:
            return None

        source_node = self._nodes.get(source_node_id)
        target_node = self._nodes.get(target_node_id)
        if source_node is None or target_node is None:
            return None

        source_port = source_node.get_output_port(source_port_name)
        target_port = target_node.get_input_port(target_port_name)
        if source_port is None or target_port is None:
            return None

        return ConnectionInfo(
            connection=conn,
            source_node=source_node,
            source_port=source_port,
            target_node=target_node,
            target_port=target_port,
        )

    def has_connection(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> bool:
        """Check if a specific connection exists."""
        return self.get_connection(
            source_node_id, source_port_name, target_node_id, target_port_name
        ) is not None

    # Connection Queries

    def get_outgoing_connections(self, node_id: str) -> List[Connection]:
        """Get all connections where this node is the source."""
        result: List[Connection] = []
        for key, connections in self._outgoing_connections.items():
            if key[0] == node_id:
                result.extend(connections)
        return result

    def get_incoming_connections(self, node_id: str) -> List[Connection]:
        """Get all connections where this node is the target."""
        result: List[Connection] = []
        for key, connection in self._incoming_connections.items():
            if key[0] == node_id:
                result.append(connection)
        return result

    def get_connections_for_port(
        self,
        node_id: str,
        port_name: str,
        is_input: bool,
    ) -> List[Connection]:
        """
        Get all connections for a specific port.

        Args:
            node_id: The ID of the node.
            port_name: The name of the port.
            is_input: True if this is an input port, False for output.

        Returns:
            List of connections (single item for input ports, multiple for output).
        """
        if is_input:
            incoming_key = (node_id, port_name)
            conn = self._incoming_connections.get(incoming_key)
            return [conn] if conn else []
        else:
            outgoing_key = (node_id, port_name)
            return self._outgoing_connections.get(outgoing_key, []).copy()

    def get_connected_nodes(
        self,
        node_id: str,
        direction: DataFlowDirection = DataFlowDirection.DOWNSTREAM,
    ) -> List[BaseNode]:
        """
        Get all nodes directly connected to a node.

        Args:
            node_id: The ID of the node.
            direction: Which direction to look for connections.

        Returns:
            List of connected nodes.
        """
        connected_ids: Set[str] = set()

        if direction == DataFlowDirection.DOWNSTREAM:
            for conn in self.get_outgoing_connections(node_id):
                connected_ids.add(conn.target_node_id)
        else:
            for conn in self.get_incoming_connections(node_id):
                connected_ids.add(conn.source_node_id)

        return [self._nodes[nid] for nid in connected_ids if nid in self._nodes]

    # Validation

    def _validate_connection(
        self,
        source_node: BaseNode,
        source_port: OutputPort,
        target_node: BaseNode,
        target_port: InputPort,
    ) -> None:
        """
        Validate that a connection can be made.

        Raises:
            ConnectionValidationError: If validation fails.
            CycleDetectedError: If the connection would create a cycle.
        """
        # Check self-connection
        if source_node.id == target_node.id:
            raise ConnectionValidationError("Cannot connect a node to itself")

        # Check type compatibility
        if not target_port.can_accept_type(source_port.port_type):
            raise ConnectionValidationError(
                f"Type mismatch: cannot connect {source_port.port_type.name} "
                f"to {target_port.port_type.name}"
            )

        # Check for cycles (only for FLOW connections or if we want strict acyclic)
        if self._would_create_cycle(source_node.id, target_node.id):
            raise CycleDetectedError(
                f"Connection would create a cycle: {source_node.name} -> {target_node.name}"
            )

    def can_connect(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a connection can be made without creating it.

        Returns:
            Tuple of (can_connect, error_message).
            If can_connect is True, error_message is None.
        """
        try:
            source_node = self._nodes.get(source_node_id)
            target_node = self._nodes.get(target_node_id)

            if source_node is None:
                return False, f"Source node '{source_node_id}' not found"
            if target_node is None:
                return False, f"Target node '{target_node_id}' not found"

            source_port = source_node.get_output_port(source_port_name)
            target_port = target_node.get_input_port(target_port_name)

            if source_port is None:
                return False, f"Output port '{source_port_name}' not found"
            if target_port is None:
                return False, f"Input port '{target_port_name}' not found"

            self._validate_connection(source_node, source_port, target_node, target_port)
            return True, None

        except ConnectionError as e:
            logger.debug("Connection validation failed: %s", e)
            return False, str(e)

    def validate_all_connections(self) -> List[str]:
        """
        Validate all connections in the model.

        Returns:
            List of validation error messages. Empty if all valid.
        """
        errors: List[str] = []

        for conn in self._connections:
            source_node = self._nodes.get(conn.source_node_id)
            target_node = self._nodes.get(conn.target_node_id)

            if source_node is None:
                errors.append(f"Connection references missing source node: {conn.source_node_id}")
                continue
            if target_node is None:
                errors.append(f"Connection references missing target node: {conn.target_node_id}")
                continue

            source_port = source_node.get_output_port(conn.source_port_name)
            target_port = target_node.get_input_port(conn.target_port_name)

            if source_port is None:
                errors.append(
                    f"Connection references missing source port: "
                    f"{conn.source_node_id}.{conn.source_port_name}"
                )
                continue
            if target_port is None:
                errors.append(
                    f"Connection references missing target port: "
                    f"{conn.target_node_id}.{conn.target_port_name}"
                )
                continue

            # Check type compatibility
            if not target_port.can_accept_type(source_port.port_type):
                errors.append(
                    f"Type mismatch in connection {source_node.name}.{source_port.name} -> "
                    f"{target_node.name}.{target_port.name}: "
                    f"{source_port.port_type.name} to {target_port.port_type.name}"
                )

        return errors

    def validate_connection_with_inferred_types(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate a connection using inferred types when available.

        This method provides enhanced type checking by using runtime
        inferred types from the source port if available, falling back
        to declared types otherwise.

        Args:
            source_node_id: ID of the source node.
            source_port_name: Name of the source output port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target input port.

        Returns:
            Tuple of (is_valid, error_message, warning_message).
            is_valid: True if the connection is valid.
            error_message: Error message if connection is invalid, None otherwise.
            warning_message: Warning about type coercion if applicable, None otherwise.
        """
        source_node = self._nodes.get(source_node_id)
        target_node = self._nodes.get(target_node_id)

        if source_node is None:
            return False, f"Source node '{source_node_id}' not found", None
        if target_node is None:
            return False, f"Target node '{target_node_id}' not found", None

        source_port = source_node.get_output_port(source_port_name)
        target_port = target_node.get_input_port(target_port_name)

        if source_port is None:
            return False, f"Output port '{source_port_name}' not found", None
        if target_port is None:
            return False, f"Input port '{target_port_name}' not found", None

        # Get effective types (inferred if available, else declared)
        source_type_name = source_port.get_effective_type_name()
        target_type_name = target_port.get_effective_type_name()

        # Check using inferred types if available
        source_inferred = source_port.inferred_type
        target_declared_type = target_port.port_type

        if source_inferred:
            # Use inferred type for validation
            if target_declared_type == PortType.ANY:
                return True, None, None

            if source_inferred.is_compatible_with_port_type(target_declared_type):
                # Check if there's implicit conversion
                if source_inferred.port_type != target_declared_type:
                    warning = (
                        f"Implicit type conversion: {source_type_name} -> "
                        f"{target_declared_type.name}"
                    )
                    return True, None, warning
                return True, None, None
            else:
                error = (
                    f"Type mismatch: {source_type_name} cannot connect to "
                    f"{target_declared_type.name}"
                )
                return False, error, None

        # Fall back to declared type compatibility
        if not target_port.can_accept_type(source_port.port_type):
            error = (
                f"Type mismatch: {source_port.port_type.name} cannot connect to "
                f"{target_port.port_type.name}"
            )
            return False, error, None

        return True, None, None

    def get_connection_type_info(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> Dict[str, Any]:
        """
        Get type information for a connection, including inferred types.

        This is useful for UI display to show users what types are
        flowing through connections.

        Args:
            source_node_id: ID of the source node.
            source_port_name: Name of the source output port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target input port.

        Returns:
            Dictionary with type information for the connection.
        """
        source_node = self._nodes.get(source_node_id)
        target_node = self._nodes.get(target_node_id)

        result: Dict[str, Any] = {
            "source_declared_type": None,
            "source_inferred_type": None,
            "target_declared_type": None,
            "target_inferred_type": None,
            "is_compatible": False,
            "has_inferred_types": False,
        }

        if source_node:
            source_port = source_node.get_output_port(source_port_name)
            if source_port:
                result["source_declared_type"] = source_port.port_type.name
                if source_port.inferred_type:
                    result["source_inferred_type"] = source_port.inferred_type.type_name
                    result["has_inferred_types"] = True

        if target_node:
            target_port = target_node.get_input_port(target_port_name)
            if target_port:
                result["target_declared_type"] = target_port.port_type.name
                if target_port.inferred_type:
                    result["target_inferred_type"] = target_port.inferred_type.type_name
                    result["has_inferred_types"] = True

        # Check compatibility
        is_valid, _, _ = self.validate_connection_with_inferred_types(
            source_node_id, source_port_name, target_node_id, target_port_name
        )
        result["is_compatible"] = is_valid

        return result

    # Cycle Detection

    def _would_create_cycle(self, source_node_id: str, target_node_id: str) -> bool:
        """
        Check if adding a connection would create a cycle.

        Uses DFS to check if there's already a path from target to source.
        """
        # If there's a path from target to source, adding source->target creates a cycle
        visited: Set[str] = set()
        stack: List[str] = [target_node_id]

        while stack:
            current = stack.pop()
            if current == source_node_id:
                return True

            if current in visited:
                continue
            visited.add(current)

            # Follow outgoing connections
            for conn in self.get_outgoing_connections(current):
                if conn.target_node_id not in visited:
                    stack.append(conn.target_node_id)

        return False

    def has_cycle(self) -> bool:
        """
        Check if the graph contains any cycles.

        Returns:
            True if a cycle exists, False otherwise.
        """
        # Use DFS with three-color marking
        # WHITE = not visited, GRAY = in current path, BLACK = fully processed
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {nid: WHITE for nid in self._nodes}

        def dfs(node_id: str) -> bool:
            color[node_id] = GRAY

            for conn in self.get_outgoing_connections(node_id):
                neighbor = conn.target_node_id
                if color.get(neighbor, WHITE) == GRAY:
                    return True  # Back edge found - cycle!
                if color.get(neighbor, WHITE) == WHITE:
                    if dfs(neighbor):
                        return True

            color[node_id] = BLACK
            return False

        for node_id in self._nodes:
            if color[node_id] == WHITE:
                if dfs(node_id):
                    return True

        return False

    def find_cycles(self) -> List[List[str]]:
        """
        Find all cycles in the graph.

        Returns:
            List of cycles, where each cycle is a list of node IDs.
        """
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for conn in self.get_outgoing_connections(node_id):
                neighbor = conn.target_node_id
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found a cycle - extract it from path
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node_id)

        for node_id in self._nodes:
            if node_id not in visited:
                dfs(node_id)

        return cycles

    # Graph Traversal

    def get_topological_order(self) -> Optional[List[BaseNode]]:
        """
        Get nodes in topological order (execution order).

        Returns:
            List of nodes in order, or None if graph has cycles.
        """
        if self.has_cycle():
            return None

        # Kahn's algorithm
        in_degree: Dict[str, int] = {nid: 0 for nid in self._nodes}

        for conn in self._connections:
            in_degree[conn.target_node_id] += 1

        # Start with nodes that have no incoming connections
        queue: List[str] = [nid for nid, deg in in_degree.items() if deg == 0]
        result: List[BaseNode] = []

        while queue:
            node_id = queue.pop(0)
            node = self._nodes.get(node_id)
            if node:
                result.append(node)

            for conn in self.get_outgoing_connections(node_id):
                in_degree[conn.target_node_id] -= 1
                if in_degree[conn.target_node_id] == 0:
                    queue.append(conn.target_node_id)

        return result if len(result) == len(self._nodes) else None

    def topological_sort(self) -> TopologicalSortResult:
        """
        Perform comprehensive topological sort with execution level information.

        This method provides a complete topological ordering suitable for script
        generation, including execution levels that indicate which nodes can be
        executed in parallel.

        Uses a modified Kahn's algorithm that tracks execution levels - nodes at
        the same level have all their dependencies satisfied at the same time and
        can theoretically execute in parallel.

        Returns:
            TopologicalSortResult containing:
            - nodes: Ordered list in valid execution order
            - levels: Mapping of level number to nodes at that level
            - node_level_map: Mapping of node ID to its execution level
            - is_valid: False if graph has cycles
            - critical_path: The longest dependency chain
            - independent_groups: Groups of nodes with no inter-dependencies

        Example:
            >>> result = model.topological_sort()
            >>> if result.is_valid:
            ...     for level in range(result.get_max_level() + 1):
            ...         parallel_nodes = result.get_nodes_at_level(level)
            ...         # These nodes can execute in parallel
            ...         for node in parallel_nodes:
            ...             node.execute(inputs)
        """
        result = TopologicalSortResult()

        # Check for cycles first
        if self.has_cycle():
            result.is_valid = False
            return result

        # Calculate in-degrees for all nodes
        in_degree: Dict[str, int] = {nid: 0 for nid in self._nodes}
        for conn in self._connections:
            in_degree[conn.target_node_id] += 1

        # Initialize queue with nodes that have no incoming connections (level 0)
        current_level_ids: List[str] = [nid for nid, deg in in_degree.items() if deg == 0]
        level = 0

        while current_level_ids:
            # Process all nodes at the current level
            next_level_ids: List[str] = []
            level_nodes: List[BaseNode] = []

            for node_id in current_level_ids:
                node = self._nodes.get(node_id)
                if node:
                    result.nodes.append(node)
                    level_nodes.append(node)
                    result.node_level_map[node_id] = level

                    # Decrement in-degrees for successors
                    for conn in self.get_outgoing_connections(node_id):
                        target_id = conn.target_node_id
                        in_degree[target_id] -= 1
                        if in_degree[target_id] == 0:
                            next_level_ids.append(target_id)

            # Store nodes at this level
            if level_nodes:
                result.levels[level] = level_nodes

            current_level_ids = next_level_ids
            level += 1

        # Verify all nodes were processed (should be True if no cycles)
        result.is_valid = len(result.nodes) == len(self._nodes)

        # Calculate critical path and independent groups
        if result.is_valid:
            result.critical_path = self._find_critical_path()
            result.independent_groups = self._find_independent_groups()

        return result

    def _find_critical_path(self) -> List[str]:
        """
        Find the critical path (longest dependency chain) in the graph.

        The critical path represents the sequence of nodes that determines
        the minimum execution time if nodes could execute in parallel.

        Returns:
            List of node IDs representing the critical path.
        """
        if not self._nodes:
            return []

        # Calculate longest path to each node using dynamic programming
        longest_path: Dict[str, int] = {}
        predecessor: Dict[str, Optional[str]] = {}

        # Get topological order first
        topo_order = self.get_topological_order()
        if topo_order is None:
            return []

        # Initialize
        for node in topo_order:
            longest_path[node.id] = 0
            predecessor[node.id] = None

        # For each node in topological order
        for node in topo_order:
            node_id = node.id
            # Update successors
            for conn in self.get_outgoing_connections(node_id):
                target_id = conn.target_node_id
                new_path_length = longest_path[node_id] + 1
                if new_path_length > longest_path.get(target_id, 0):
                    longest_path[target_id] = new_path_length
                    predecessor[target_id] = node_id

        # Find the node with the longest path
        if not longest_path:
            return []

        end_node_id = max(longest_path.keys(), key=lambda x: longest_path[x])

        # Reconstruct the path
        path: List[str] = []
        current: Optional[str] = end_node_id
        while current is not None:
            path.append(current)
            current = predecessor.get(current)

        path.reverse()
        return path

    def _find_independent_groups(self) -> List[List[str]]:
        """
        Find groups of nodes that have no dependencies between them.

        Independent groups can be scheduled separately without affecting correctness.
        This is useful for optimizing execution or identifying separate "pipelines"
        within the graph.

        Returns:
            List of node ID lists, where each inner list is an independent group.
        """
        if not self._nodes:
            return []

        # Use Union-Find to group connected components
        parent: Dict[str, str] = {nid: nid for nid in self._nodes}

        def find(x: str) -> str:
            if parent[x] != x:
                parent[x] = find(parent[x])  # Path compression
            return parent[x]

        def union(x: str, y: str) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Union nodes that are connected
        for conn in self._connections:
            union(conn.source_node_id, conn.target_node_id)

        # Group nodes by their root
        groups: Dict[str, List[str]] = {}
        for node_id in self._nodes:
            root = find(node_id)
            if root not in groups:
                groups[root] = []
            groups[root].append(node_id)

        return list(groups.values())

    def get_execution_levels(self) -> Dict[int, List[BaseNode]]:
        """
        Get nodes grouped by their execution level.

        Execution levels indicate the order in which nodes should execute,
        where all nodes at level N must complete before any node at level N+1
        can start. Nodes at the same level have no dependencies between them.

        Returns:
            Dictionary mapping level number (0-indexed) to list of nodes at that level.
            Returns empty dict if graph has cycles.

        Example:
            >>> levels = model.get_execution_levels()
            >>> for level_num in sorted(levels.keys()):
            ...     print(f"Level {level_num}: {[n.name for n in levels[level_num]]}")
        """
        result = self.topological_sort()
        return result.levels if result.is_valid else {}

    def get_critical_path_nodes(self) -> List[BaseNode]:
        """
        Get nodes that form the critical path (longest dependency chain).

        The critical path determines the minimum execution time when nodes
        can execute in parallel - it's the sequence of dependent nodes that
        cannot be parallelized.

        Returns:
            List of nodes in the critical path, or empty list if graph has cycles.
        """
        path_ids = self._find_critical_path()
        return [self._nodes[nid] for nid in path_ids if nid in self._nodes]

    def validate_execution_order(self, node_order: List[str]) -> Tuple[bool, List[str]]:
        """
        Validate that a given execution order respects all dependencies.

        This is useful for verifying that a custom execution order is valid,
        or for debugging execution issues.

        Args:
            node_order: List of node IDs in the proposed execution order.

        Returns:
            Tuple of (is_valid, error_messages).
            is_valid is True if the order respects all dependencies.
            error_messages contains details of any violations.

        Example:
            >>> is_valid, errors = model.validate_execution_order(["node1", "node2", "node3"])
            >>> if not is_valid:
            ...     for error in errors:
            ...         print(f"Violation: {error}")
        """
        errors: List[str] = []

        # Build position map for quick lookups
        position: Dict[str, int] = {nid: idx for idx, nid in enumerate(node_order)}

        # Check that all nodes are included
        missing = set(self._nodes.keys()) - set(node_order)
        if missing:
            errors.append(f"Missing nodes from order: {missing}")

        extra = set(node_order) - set(self._nodes.keys())
        if extra:
            errors.append(f"Unknown nodes in order: {extra}")

        # Check dependency order
        for conn in self._connections:
            source_pos = position.get(conn.source_node_id)
            target_pos = position.get(conn.target_node_id)

            if source_pos is not None and target_pos is not None:
                if source_pos >= target_pos:
                    source_node = self._nodes.get(conn.source_node_id)
                    target_node = self._nodes.get(conn.target_node_id)
                    source_name = source_node.name if source_node else conn.source_node_id
                    target_name = target_node.name if target_node else conn.target_node_id
                    errors.append(
                        f"Dependency violation: '{source_name}' (position {source_pos}) "
                        f"must execute before '{target_name}' (position {target_pos})"
                    )

        return len(errors) == 0, errors

    def get_execution_order(self) -> List[BaseNode]:
        """
        Get nodes in execution order, handling FLOW connections specially.

        For FLOW-based execution, follows FLOW connections to determine order.
        Falls back to topological order if no FLOW connections exist.

        Returns:
            List of nodes in execution order.
        """
        order = self.get_topological_order()
        return order if order is not None else []

    def get_source_nodes(self) -> List[BaseNode]:
        """Get all nodes that have no incoming connections (data sources)."""
        node_ids_with_incoming = {
            conn.target_node_id for conn in self._connections
        }
        return [
            node for node in self._nodes.values()
            if node.id not in node_ids_with_incoming
        ]

    def get_sink_nodes(self) -> List[BaseNode]:
        """Get all nodes that have no outgoing connections (data sinks)."""
        node_ids_with_outgoing = {
            conn.source_node_id for conn in self._connections
        }
        return [
            node for node in self._nodes.values()
            if node.id not in node_ids_with_outgoing
        ]

    # Data Flow Analysis

    def get_data_flow_paths(
        self,
        start_node: BaseNode,
        direction: DataFlowDirection = DataFlowDirection.DOWNSTREAM,
        max_depth: int = 100,
    ) -> List[DataFlowPath]:
        """
        Get all data flow paths starting from a node.

        Args:
            start_node: The node to start from.
            direction: Direction to follow connections.
            max_depth: Maximum depth to prevent infinite loops.

        Returns:
            List of DataFlowPath objects representing all paths.
        """
        paths: List[DataFlowPath] = []
        self._explore_paths(start_node, direction, max_depth, DataFlowPath(), paths, set())
        return paths

    def _explore_paths(
        self,
        current_node: BaseNode,
        direction: DataFlowDirection,
        remaining_depth: int,
        current_path: DataFlowPath,
        all_paths: List[DataFlowPath],
        visited: Set[str],
    ) -> None:
        """Recursively explore data flow paths."""
        if remaining_depth <= 0 or current_node.id in visited:
            return

        # Add current node to path
        new_path = DataFlowPath(
            nodes=current_path.nodes + [current_node],
            connections=current_path.connections.copy(),
        )
        visited = visited | {current_node.id}

        # Get next connections
        if direction == DataFlowDirection.DOWNSTREAM:
            next_connections = self.get_outgoing_connections(current_node.id)
        else:
            next_connections = self.get_incoming_connections(current_node.id)

        if not next_connections:
            # End of path - save it
            all_paths.append(new_path)
            return

        for conn in next_connections:
            next_node_id = (
                conn.target_node_id
                if direction == DataFlowDirection.DOWNSTREAM
                else conn.source_node_id
            )
            next_node = self._nodes.get(next_node_id)
            if next_node and next_node_id not in visited:
                path_with_conn = DataFlowPath(
                    nodes=new_path.nodes.copy(),
                    connections=new_path.connections + [conn],
                )
                self._explore_paths(
                    next_node,
                    direction,
                    remaining_depth - 1,
                    path_with_conn,
                    all_paths,
                    visited,
                )

        # If we explored children but found none valid, this is an end
        if not any(
            self._nodes.get(
                c.target_node_id if direction == DataFlowDirection.DOWNSTREAM else c.source_node_id
            )
            for c in next_connections
        ):
            all_paths.append(new_path)

    def get_upstream_nodes(self, node_id: str) -> List[BaseNode]:
        """
        Get all nodes that feed data into a node (recursively).

        Args:
            node_id: The ID of the node.

        Returns:
            List of upstream nodes in traversal order.
        """
        upstream: List[BaseNode] = []
        visited: Set[str] = set()
        stack: List[str] = [node_id]

        while stack:
            current = stack.pop()
            for conn in self.get_incoming_connections(current):
                source_id = conn.source_node_id
                if source_id not in visited:
                    visited.add(source_id)
                    node = self._nodes.get(source_id)
                    if node:
                        upstream.append(node)
                        stack.append(source_id)

        return upstream

    def get_downstream_nodes(self, node_id: str) -> List[BaseNode]:
        """
        Get all nodes that receive data from a node (recursively).

        Args:
            node_id: The ID of the node.

        Returns:
            List of downstream nodes in traversal order.
        """
        downstream: List[BaseNode] = []
        visited: Set[str] = set()
        stack: List[str] = [node_id]

        while stack:
            current = stack.pop()
            for conn in self.get_outgoing_connections(current):
                target_id = conn.target_node_id
                if target_id not in visited:
                    visited.add(target_id)
                    node = self._nodes.get(target_id)
                    if node:
                        downstream.append(node)
                        stack.append(target_id)

        return downstream

    def get_dependencies(self, node_id: str) -> Set[str]:
        """
        Get IDs of all nodes that must execute before this node.

        This is the transitive closure of all upstream nodes.
        """
        return {node.id for node in self.get_upstream_nodes(node_id)}

    def get_dependents(self, node_id: str) -> Set[str]:
        """
        Get IDs of all nodes that depend on this node.

        This is the transitive closure of all downstream nodes.
        """
        return {node.id for node in self.get_downstream_nodes(node_id)}

    # Traversal Utilities

    def traverse(
        self,
        start_node_id: str,
        direction: DataFlowDirection,
        visitor: Callable[[BaseNode, int], bool],
        max_depth: int = 100,
    ) -> None:
        """
        Traverse the graph from a starting node, calling visitor for each node.

        Args:
            start_node_id: The ID of the node to start from.
            direction: Direction to traverse.
            visitor: Callback function(node, depth) -> continue_traversal.
            max_depth: Maximum traversal depth.
        """
        visited: Set[str] = set()

        def dfs(node_id: str, depth: int) -> None:
            if depth > max_depth or node_id in visited:
                return

            visited.add(node_id)
            node = self._nodes.get(node_id)
            if node is None:
                return

            if not visitor(node, depth):
                return

            if direction == DataFlowDirection.DOWNSTREAM:
                next_ids = [c.target_node_id for c in self.get_outgoing_connections(node_id)]
            else:
                next_ids = [c.source_node_id for c in self.get_incoming_connections(node_id)]

            for next_id in next_ids:
                dfs(next_id, depth + 1)

        dfs(start_node_id, 0)

    def traverse_dfs(
        self,
        start_node_ids: Optional[List[str]] = None,
        direction: DataFlowDirection = DataFlowDirection.DOWNSTREAM,
        max_depth: int = 100,
    ) -> TraversalResult:
        """
        Perform depth-first traversal of the graph.

        Depth-first search explores as far as possible along each branch before
        backtracking. This is useful for finding complete paths through the graph
        and for execution scenarios where you want to complete one branch before
        starting another.

        Args:
            start_node_ids: Optional list of node IDs to start from.
                           If None, starts from all source nodes (nodes with no incoming connections).
            direction: Direction to traverse (DOWNSTREAM follows outgoing connections,
                      UPSTREAM follows incoming connections).
            max_depth: Maximum depth to traverse to prevent infinite loops.

        Returns:
            TraversalResult containing nodes in DFS order with visit order and depth info.

        Example:
            >>> # Traverse from all source nodes
            >>> result = model.traverse_dfs()
            >>> for node in result:
            ...     print(f"{node.name} at depth {result.get_depth(node.id)}")
            >>>
            >>> # Traverse from specific start node
            >>> result = model.traverse_dfs(start_node_ids=["node_123"])
        """
        result = TraversalResult()
        visited: Set[str] = set()
        order_counter = 0

        # Determine starting nodes
        if start_node_ids is None:
            start_nodes = self.get_source_nodes()
            start_node_ids = [n.id for n in start_nodes]
        else:
            # Validate all start node IDs exist
            start_node_ids = [nid for nid in start_node_ids if nid in self._nodes]

        if not start_node_ids:
            return result

        def dfs_visit(node_id: str, depth: int) -> None:
            nonlocal order_counter

            if depth > max_depth or node_id in visited:
                return

            visited.add(node_id)
            node = self._nodes.get(node_id)
            if node is None:
                return

            # Record visit
            result.nodes.append(node)
            result.visit_order[node_id] = order_counter
            result.depth_map[node_id] = depth
            order_counter += 1

            # Get connections and traverse
            if direction == DataFlowDirection.DOWNSTREAM:
                connections = self.get_outgoing_connections(node_id)
                for conn in connections:
                    if conn.target_node_id not in visited:
                        result.connections.append(conn)
                        dfs_visit(conn.target_node_id, depth + 1)
            else:
                connections = self.get_incoming_connections(node_id)
                for conn in connections:
                    if conn.source_node_id not in visited:
                        result.connections.append(conn)
                        dfs_visit(conn.source_node_id, depth + 1)

        # Start traversal from each start node
        for start_id in start_node_ids:
            if start_id not in visited:
                dfs_visit(start_id, 0)

        return result

    def traverse_bfs(
        self,
        start_node_ids: Optional[List[str]] = None,
        direction: DataFlowDirection = DataFlowDirection.DOWNSTREAM,
        max_depth: int = 100,
    ) -> TraversalResult:
        """
        Perform breadth-first traversal of the graph.

        Breadth-first search explores all neighbors at the current depth level
        before moving to nodes at the next depth level. This is useful for
        finding shortest paths and for execution scenarios where you want to
        process nodes level by level.

        Args:
            start_node_ids: Optional list of node IDs to start from.
                           If None, starts from all source nodes (nodes with no incoming connections).
            direction: Direction to traverse (DOWNSTREAM follows outgoing connections,
                      UPSTREAM follows incoming connections).
            max_depth: Maximum depth to traverse to prevent infinite loops.

        Returns:
            TraversalResult containing nodes in BFS order with visit order and depth info.

        Example:
            >>> # Traverse from all source nodes
            >>> result = model.traverse_bfs()
            >>> for node in result:
            ...     print(f"{node.name} at depth {result.get_depth(node.id)}")
            >>>
            >>> # Traverse from specific start node
            >>> result = model.traverse_bfs(start_node_ids=["node_123"])
        """
        from collections import deque

        result = TraversalResult()
        visited: Set[str] = set()
        order_counter = 0

        # Determine starting nodes
        if start_node_ids is None:
            start_nodes = self.get_source_nodes()
            start_node_ids = [n.id for n in start_nodes]
        else:
            # Validate all start node IDs exist
            start_node_ids = [nid for nid in start_node_ids if nid in self._nodes]

        if not start_node_ids:
            return result

        # Initialize queue with start nodes (node_id, depth)
        queue: deque[Tuple[str, int]] = deque()
        for start_id in start_node_ids:
            if start_id in self._nodes and start_id not in visited:
                queue.append((start_id, 0))
                visited.add(start_id)

        while queue:
            node_id, depth = queue.popleft()

            if depth > max_depth:
                continue

            node = self._nodes.get(node_id)
            if node is None:
                continue

            # Record visit
            result.nodes.append(node)
            result.visit_order[node_id] = order_counter
            result.depth_map[node_id] = depth
            order_counter += 1

            # Get connections and enqueue neighbors
            if direction == DataFlowDirection.DOWNSTREAM:
                connections = self.get_outgoing_connections(node_id)
                for conn in connections:
                    if conn.target_node_id not in visited:
                        visited.add(conn.target_node_id)
                        result.connections.append(conn)
                        queue.append((conn.target_node_id, depth + 1))
            else:
                connections = self.get_incoming_connections(node_id)
                for conn in connections:
                    if conn.source_node_id not in visited:
                        visited.add(conn.source_node_id)
                        result.connections.append(conn)
                        queue.append((conn.source_node_id, depth + 1))

        return result

    def walk_from_start_nodes(
        self,
        strategy: TraversalStrategy = TraversalStrategy.DEPTH_FIRST,
        max_depth: int = 100,
    ) -> TraversalResult:
        """
        Walk the graph starting from all source nodes (entry points).

        This method identifies all source nodes (nodes with no incoming connections)
        and traverses the graph downstream using the specified strategy. This is
        critical for determining execution order during compilation.

        Args:
            strategy: The traversal strategy to use (DEPTH_FIRST or BREADTH_FIRST).
            max_depth: Maximum depth to traverse.

        Returns:
            TraversalResult containing nodes in traversal order.

        Example:
            >>> # Walk using depth-first strategy
            >>> result = model.walk_from_start_nodes(TraversalStrategy.DEPTH_FIRST)
            >>> execution_order = list(result)
            >>>
            >>> # Walk using breadth-first strategy (level-by-level)
            >>> result = model.walk_from_start_nodes(TraversalStrategy.BREADTH_FIRST)
        """
        if strategy == TraversalStrategy.DEPTH_FIRST:
            return self.traverse_dfs(direction=DataFlowDirection.DOWNSTREAM, max_depth=max_depth)
        else:
            return self.traverse_bfs(direction=DataFlowDirection.DOWNSTREAM, max_depth=max_depth)

    def get_execution_order_from_start(
        self,
        start_node_ids: Optional[List[str]] = None,
        strategy: TraversalStrategy = TraversalStrategy.BREADTH_FIRST,
    ) -> List[BaseNode]:
        """
        Get nodes in execution order starting from specified nodes or source nodes.

        This method is designed specifically for compilation and execution planning.
        It traverses the graph from start nodes and returns nodes in an order
        suitable for execution, respecting dependencies.

        For execution order, BREADTH_FIRST is typically preferred as it processes
        nodes level by level, ensuring all dependencies at a given level are
        processed before moving to dependent nodes.

        Args:
            start_node_ids: Optional list of specific start node IDs.
                           If None, uses all source nodes (nodes with no incoming connections).
            strategy: The traversal strategy to use. BREADTH_FIRST is recommended
                     for execution order as it respects dependency levels.

        Returns:
            List of nodes in execution order.

        Example:
            >>> # Get execution order for the entire graph
            >>> order = model.get_execution_order_from_start()
            >>> for node in order:
            ...     node.execute(inputs)
            >>>
            >>> # Get execution order from a specific start point
            >>> order = model.get_execution_order_from_start(["start_node_id"])
        """
        if strategy == TraversalStrategy.DEPTH_FIRST:
            result = self.traverse_dfs(
                start_node_ids=start_node_ids,
                direction=DataFlowDirection.DOWNSTREAM,
            )
        else:
            result = self.traverse_bfs(
                start_node_ids=start_node_ids,
                direction=DataFlowDirection.DOWNSTREAM,
            )
        return result.nodes

    def get_flow_execution_order(
        self,
        start_node_ids: Optional[List[str]] = None,
        strategy: TraversalStrategy = TraversalStrategy.DEPTH_FIRST,
    ) -> List[BaseNode]:
        """
        Get nodes in execution order following FLOW connections specifically.

        This method is optimized for visual programming execution where FLOW
        connections (execution control connections) determine the order of
        node execution. Unlike data dependencies, FLOW connections represent
        explicit sequencing.

        For FLOW-based execution, DEPTH_FIRST is typically preferred as it
        follows complete execution paths before branching.

        Args:
            start_node_ids: Optional list of specific start node IDs.
                           If None, uses source nodes that have FLOW output ports.
            strategy: The traversal strategy. DEPTH_FIRST is recommended for
                     following execution flow paths.

        Returns:
            List of nodes in FLOW execution order.

        Example:
            >>> # Get FLOW-based execution order
            >>> order = model.get_flow_execution_order()
            >>> for node in order:
            ...     result = node.execute(inputs)
            ...     # Handle branching based on result
        """
        from visualpython.nodes.models.port import PortType

        result_nodes: List[BaseNode] = []
        visited: Set[str] = set()

        # Determine starting nodes - prefer nodes with FLOW outputs and no FLOW inputs
        if start_node_ids is None:
            start_nodes = []
            for node in self.get_source_nodes():
                # Check if this node has FLOW output ports (makes it a potential start)
                has_flow_output = any(
                    port.port_type == PortType.FLOW for port in node.output_ports
                )
                if has_flow_output or len(node.output_ports) > 0:
                    start_nodes.append(node)
            # If no nodes with FLOW outputs, fall back to all source nodes
            if not start_nodes:
                start_nodes = self.get_source_nodes()
            start_node_ids = [n.id for n in start_nodes]
        else:
            start_node_ids = [nid for nid in start_node_ids if nid in self._nodes]

        def get_flow_connections(node_id: str) -> List[Connection]:
            """Get only FLOW-type outgoing connections."""
            connections = self.get_outgoing_connections(node_id)
            flow_connections = []
            node = self._nodes.get(node_id)
            if node:
                for conn in connections:
                    source_port = node.get_output_port(conn.source_port_name)
                    if source_port and source_port.port_type == PortType.FLOW:
                        flow_connections.append(conn)
            return flow_connections if flow_connections else connections

        if strategy == TraversalStrategy.DEPTH_FIRST:
            # DFS for FLOW execution
            def dfs_flow(node_id: str) -> None:
                if node_id in visited:
                    return
                visited.add(node_id)
                node = self._nodes.get(node_id)
                if node:
                    result_nodes.append(node)
                    for conn in get_flow_connections(node_id):
                        dfs_flow(conn.target_node_id)

            for start_id in start_node_ids:
                dfs_flow(start_id)
        else:
            # BFS for FLOW execution
            from collections import deque
            queue: deque[str] = deque()
            for start_id in start_node_ids:
                if start_id not in visited:
                    queue.append(start_id)
                    visited.add(start_id)

            while queue:
                node_id = queue.popleft()
                node = self._nodes.get(node_id)
                if node:
                    result_nodes.append(node)
                    for conn in get_flow_connections(node_id):
                        if conn.target_node_id not in visited:
                            visited.add(conn.target_node_id)
                            queue.append(conn.target_node_id)

        return result_nodes

    # Serialization

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the connection model to a dictionary.

        Returns:
            Dictionary representation of the model.
        """
        return {
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "connections": [conn.to_dict() for conn in self._connections],
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        node_factory: Callable[[Dict[str, Any]], BaseNode],
    ) -> ConnectionModel:
        """
        Deserialize a connection model from a dictionary.

        Args:
            data: Dictionary containing serialized model data.
            node_factory: Function to create nodes from dictionaries.

        Returns:
            A new ConnectionModel instance.
        """
        model = cls()

        # Restore nodes
        for node_data in data.get("nodes", []):
            node = node_factory(node_data)
            model.add_node(node)

        # Restore connections
        for conn_data in data.get("connections", []):
            model.connect(
                source_node_id=conn_data["source_node_id"],
                source_port_name=conn_data["source_port_name"],
                target_node_id=conn_data["target_node_id"],
                target_port_name=conn_data["target_port_name"],
                validate=False,  # Skip validation during restore
            )

        return model

    def clear(self) -> None:
        """Remove all nodes and connections from the model."""
        self._nodes.clear()
        self._outgoing_connections.clear()
        self._incoming_connections.clear()
        self._connections.clear()

    # String representation

    def __repr__(self) -> str:
        """Get a detailed string representation."""
        return (
            f"ConnectionModel(nodes={len(self._nodes)}, "
            f"connections={len(self._connections)})"
        )

    def __str__(self) -> str:
        """Get a simple string representation."""
        return f"ConnectionModel with {len(self._nodes)} nodes and {len(self._connections)} connections"
