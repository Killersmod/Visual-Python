"""
Core graph data model for the VisualPython visual programming system.

This module provides the Graph class that serves as the central data model,
holding collections of nodes and connections with comprehensive query and
manipulation methods for building and executing visual programs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, TYPE_CHECKING

from visualpython.nodes.models.connection_model import (
    ConnectionModel,
    ConnectionError,
    ConnectionValidationError,
    CycleDetectedError,
    DataFlowDirection,
    DataFlowPath,
    ConnectionInfo,
    TraversalResult,
    TraversalStrategy,
    TopologicalSortResult,
)
from visualpython.nodes.models.port import Connection, PortType
from visualpython.nodes.models.node_group import NodeGroup, GroupBounds

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode


class GraphState(Enum):
    """Represents the current state of the graph."""

    IDLE = auto()
    """Graph is not being executed."""

    EXECUTING = auto()
    """Graph is currently executing nodes."""

    PAUSED = auto()
    """Graph execution is paused."""

    COMPLETED = auto()
    """Graph execution has completed."""

    ERROR = auto()
    """Graph execution encountered an error."""


@dataclass
class GraphMetadata:
    """
    Metadata for a graph including name, description, and timestamps.

    Attributes:
        name: Human-readable name for the graph.
        description: Detailed description of what the graph does.
        author: Author of the graph.
        version: Version string for the graph.
        created_at: Timestamp when the graph was created.
        modified_at: Timestamp when the graph was last modified.
        tags: List of tags for categorization.
        flow_entry_points: Entry points for subgraph execution flow.
        flow_exit_points: Exit points for subgraph execution flow.
    """

    name: str = "Untitled Graph"
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    modified_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = field(default_factory=list)
    flow_entry_points: List[Dict[str, str]] = field(default_factory=list)
    flow_exit_points: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata to dictionary."""
        data: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "tags": self.tags.copy(),
        }
        if self.flow_entry_points:
            data["flow_entry_points"] = [ep.copy() for ep in self.flow_entry_points]
        if self.flow_exit_points:
            data["flow_exit_points"] = [ep.copy() for ep in self.flow_exit_points]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GraphMetadata:
        """Deserialize metadata from dictionary."""
        return cls(
            name=data.get("name", "Untitled Graph"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            version=data.get("version", "1.0.0"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            modified_at=data.get("modified_at", datetime.now().isoformat()),
            tags=data.get("tags", []).copy(),
            flow_entry_points=[ep.copy() for ep in data.get("flow_entry_points", [])],
            flow_exit_points=[ep.copy() for ep in data.get("flow_exit_points", [])],
        )


@dataclass
class GraphStatistics:
    """
    Statistics about the graph structure.

    Attributes:
        node_count: Total number of nodes.
        connection_count: Total number of connections.
        source_node_count: Number of nodes with no incoming connections.
        sink_node_count: Number of nodes with no outgoing connections.
        max_depth: Maximum depth of the graph.
        node_types: Count of each node type.
    """

    node_count: int = 0
    connection_count: int = 0
    source_node_count: int = 0
    sink_node_count: int = 0
    max_depth: int = 0
    node_types: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize statistics to dictionary."""
        return {
            "node_count": self.node_count,
            "connection_count": self.connection_count,
            "source_node_count": self.source_node_count,
            "sink_node_count": self.sink_node_count,
            "max_depth": self.max_depth,
            "node_types": self.node_types.copy(),
        }


class Graph:
    """
    Central data model for the visual programming system.

    The Graph class serves as the main container for all nodes and connections,
    providing comprehensive methods for:
    - Adding, removing, and querying nodes
    - Creating and managing connections between nodes
    - Graph traversal and analysis
    - Serialization and deserialization
    - Execution state management

    Example:
        >>> graph = Graph(name="My Program")
        >>> graph.add_node(code_node)
        >>> graph.add_node(print_node)
        >>> graph.connect(code_node.id, "result", print_node.id, "value")
        >>> order = graph.get_execution_order()
        >>> graph.save("my_program.json")
    """

    def __init__(
        self,
        graph_id: Optional[str] = None,
        name: str = "Untitled Graph",
        description: str = "",
    ) -> None:
        """
        Initialize a new graph.

        Args:
            graph_id: Optional unique identifier. If not provided, a UUID is generated.
            name: Human-readable name for the graph.
            description: Description of what the graph does.
        """
        self._id: str = graph_id or str(uuid.uuid4())
        self._metadata: GraphMetadata = GraphMetadata(name=name, description=description)
        self._state: GraphState = GraphState.IDLE
        self._modified: bool = False

        # Core connection model that manages nodes and connections
        self._connection_model: ConnectionModel = ConnectionModel()

        # Node groups for organization
        self._groups: Dict[str, NodeGroup] = {}

        # Selection tracking
        self._selected_node_ids: Set[str] = set()

        # Error tracking
        self._last_error: Optional[str] = None

    # Properties

    @property
    def id(self) -> str:
        """Get the unique identifier for this graph."""
        return self._id

    @property
    def name(self) -> str:
        """Get the graph name."""
        return self._metadata.name

    @name.setter
    def name(self, value: str) -> None:
        """Set the graph name."""
        self._metadata.name = value
        self._mark_modified()

    @property
    def description(self) -> str:
        """Get the graph description."""
        return self._metadata.description

    @description.setter
    def description(self, value: str) -> None:
        """Set the graph description."""
        self._metadata.description = value
        self._mark_modified()

    @property
    def metadata(self) -> GraphMetadata:
        """Get the graph metadata."""
        return self._metadata

    @property
    def state(self) -> GraphState:
        """Get the current execution state."""
        return self._state

    @state.setter
    def state(self, value: GraphState) -> None:
        """Set the execution state."""
        self._state = value

    @property
    def is_modified(self) -> bool:
        """Check if the graph has been modified since last save."""
        return self._modified

    @property
    def last_error(self) -> Optional[str]:
        """Get the last error message, if any."""
        return self._last_error

    @property
    def node_count(self) -> int:
        """Get the number of nodes in the graph."""
        return self._connection_model.node_count

    @property
    def connection_count(self) -> int:
        """Get the number of connections in the graph."""
        return self._connection_model.connection_count

    @property
    def is_empty(self) -> bool:
        """Check if the graph has no nodes."""
        return self._connection_model.node_count == 0

    # Node Management

    def add_node(self, node: BaseNode) -> None:
        """
        Add a node to the graph.

        Args:
            node: The node to add.

        Raises:
            ValueError: If a node with the same ID already exists.
        """
        self._connection_model.add_node(node)
        self._mark_modified()

    def remove_node(self, node_id: str) -> Optional[BaseNode]:
        """
        Remove a node and all its connections from the graph.

        Args:
            node_id: The ID of the node to remove.

        Returns:
            The removed node, or None if not found.
        """
        node = self._connection_model.remove_node(node_id)
        if node:
            self._selected_node_ids.discard(node_id)
            self._mark_modified()
        return node

    def get_node(self, node_id: str) -> Optional[BaseNode]:
        """
        Get a node by its ID.

        Args:
            node_id: The ID of the node to find.

        Returns:
            The node if found, None otherwise.
        """
        return self._connection_model.get_node(node_id)

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists in the graph."""
        return self._connection_model.has_node(node_id)

    @property
    def nodes(self) -> List[BaseNode]:
        """Get a list of all nodes in the graph."""
        return self._connection_model.nodes

    def get_nodes_by_type(self, node_type: str) -> List[BaseNode]:
        """
        Get all nodes of a specific type.

        Args:
            node_type: The node type to filter by.

        Returns:
            List of nodes matching the type.
        """
        return [node for node in self.nodes if node.node_type == node_type]

    def get_nodes_by_name(self, name: str, exact: bool = True) -> List[BaseNode]:
        """
        Get nodes by name.

        Args:
            name: The name to search for.
            exact: If True, match exact name. If False, match partial.

        Returns:
            List of matching nodes.
        """
        if exact:
            return [node for node in self.nodes if node.name == name]
        return [node for node in self.nodes if name.lower() in node.name.lower()]

    def iter_nodes(self) -> Iterator[BaseNode]:
        """Iterate over all nodes in the graph."""
        return iter(self.nodes)

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
        Create a connection between two nodes.

        Args:
            source_node_id: ID of the source node.
            source_port_name: Name of the source output port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target input port.
            validate: Whether to validate the connection.

        Returns:
            The created Connection object.

        Raises:
            ConnectionValidationError: If validation fails.
            CycleDetectedError: If the connection would create a cycle.
            ValueError: If nodes or ports are not found.
        """
        connection = self._connection_model.connect(
            source_node_id,
            source_port_name,
            target_node_id,
            target_port_name,
            validate,
        )
        self._mark_modified()
        return connection

    def disconnect(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> Optional[Connection]:
        """
        Remove a connection between two nodes.

        Args:
            source_node_id: ID of the source node.
            source_port_name: Name of the source output port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target input port.

        Returns:
            The removed Connection, or None if not found.
        """
        connection = self._connection_model.disconnect(
            source_node_id,
            source_port_name,
            target_node_id,
            target_port_name,
        )
        if connection:
            self._mark_modified()
        return connection

    def disconnect_node(self, node_id: str) -> List[Connection]:
        """
        Remove all connections involving a node.

        Args:
            node_id: The ID of the node.

        Returns:
            List of removed connections.
        """
        connections = self._connection_model.disconnect_all(node_id)
        if connections:
            self._mark_modified()
        return connections

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
            is_input: True if this is an input port.

        Returns:
            List of removed connections.
        """
        connections = self._connection_model.disconnect_port(node_id, port_name, is_input)
        if connections:
            self._mark_modified()
        return connections

    @property
    def connections(self) -> List[Connection]:
        """Get a list of all connections in the graph."""
        return self._connection_model.connections

    def get_connection(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> Optional[Connection]:
        """Get a specific connection by its endpoints."""
        return self._connection_model.get_connection(
            source_node_id, source_port_name, target_node_id, target_port_name
        )

    def get_connection_info(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> Optional[ConnectionInfo]:
        """Get extended information about a connection."""
        return self._connection_model.get_connection_info(
            source_node_id, source_port_name, target_node_id, target_port_name
        )

    def has_connection(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> bool:
        """Check if a specific connection exists."""
        return self._connection_model.has_connection(
            source_node_id, source_port_name, target_node_id, target_port_name
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
        """
        return self._connection_model.can_connect(
            source_node_id, source_port_name, target_node_id, target_port_name
        )

    def iter_connections(self) -> Iterator[Connection]:
        """Iterate over all connections in the graph."""
        return iter(self.connections)

    def get_all_connections(self) -> List[Connection]:
        """
        Get all connections in the graph.

        This is a convenience method that returns the same result as the
        `connections` property.

        Returns:
            List of all Connection objects in the graph.
        """
        return self.connections

    # Connection Queries

    def get_outgoing_connections(self, node_id: str) -> List[Connection]:
        """Get all connections where this node is the source."""
        return self._connection_model.get_outgoing_connections(node_id)

    def get_incoming_connections(self, node_id: str) -> List[Connection]:
        """Get all connections where this node is the target."""
        return self._connection_model.get_incoming_connections(node_id)

    def get_connections_for_port(
        self,
        node_id: str,
        port_name: str,
        is_input: bool,
    ) -> List[Connection]:
        """Get all connections for a specific port."""
        return self._connection_model.get_connections_for_port(node_id, port_name, is_input)

    def get_connected_nodes(
        self,
        node_id: str,
        direction: DataFlowDirection = DataFlowDirection.DOWNSTREAM,
    ) -> List[BaseNode]:
        """Get all nodes directly connected to a node."""
        return self._connection_model.get_connected_nodes(node_id, direction)

    # Graph Traversal and Analysis

    def get_source_nodes(self) -> List[BaseNode]:
        """Get all nodes that have no incoming connections (entry points)."""
        return self._connection_model.get_source_nodes()

    def get_sink_nodes(self) -> List[BaseNode]:
        """Get all nodes that have no outgoing connections (exit points)."""
        return self._connection_model.get_sink_nodes()

    def get_topological_order(self) -> Optional[List[BaseNode]]:
        """
        Get nodes in topological order.

        Returns:
            List of nodes in order, or None if graph has cycles.
        """
        return self._connection_model.get_topological_order()

    def get_execution_order(self) -> List[BaseNode]:
        """
        Get nodes in execution order.

        Returns:
            List of nodes in execution order.
        """
        return self._connection_model.get_execution_order()

    def get_data_flow_paths(
        self,
        start_node: BaseNode,
        direction: DataFlowDirection = DataFlowDirection.DOWNSTREAM,
        max_depth: int = 100,
    ) -> List[DataFlowPath]:
        """Get all data flow paths starting from a node."""
        return self._connection_model.get_data_flow_paths(start_node, direction, max_depth)

    def get_upstream_nodes(self, node_id: str) -> List[BaseNode]:
        """Get all nodes that feed data into a node (recursively)."""
        return self._connection_model.get_upstream_nodes(node_id)

    def get_downstream_nodes(self, node_id: str) -> List[BaseNode]:
        """Get all nodes that receive data from a node (recursively)."""
        return self._connection_model.get_downstream_nodes(node_id)

    def get_dependencies(self, node_id: str) -> Set[str]:
        """Get IDs of all nodes that must execute before this node."""
        return self._connection_model.get_dependencies(node_id)

    def get_dependents(self, node_id: str) -> Set[str]:
        """Get IDs of all nodes that depend on this node."""
        return self._connection_model.get_dependents(node_id)

    def traverse(
        self,
        start_node_id: str,
        direction: DataFlowDirection,
        visitor: Callable[[BaseNode, int], bool],
        max_depth: int = 100,
    ) -> None:
        """
        Traverse the graph from a starting node.

        Args:
            start_node_id: The ID of the node to start from.
            direction: Direction to traverse.
            visitor: Callback function(node, depth) -> continue_traversal.
            max_depth: Maximum traversal depth.
        """
        self._connection_model.traverse(start_node_id, direction, visitor, max_depth)

    def traverse_dfs(
        self,
        start_node_ids: Optional[List[str]] = None,
        direction: DataFlowDirection = DataFlowDirection.DOWNSTREAM,
        max_depth: int = 100,
    ) -> TraversalResult:
        """
        Perform depth-first traversal of the graph.

        Args:
            start_node_ids: Optional list of node IDs to start from.
                           If None, starts from all source nodes.
            direction: Direction to traverse.
            max_depth: Maximum depth to traverse.

        Returns:
            TraversalResult containing nodes in DFS order.
        """
        return self._connection_model.traverse_dfs(start_node_ids, direction, max_depth)

    def traverse_bfs(
        self,
        start_node_ids: Optional[List[str]] = None,
        direction: DataFlowDirection = DataFlowDirection.DOWNSTREAM,
        max_depth: int = 100,
    ) -> TraversalResult:
        """
        Perform breadth-first traversal of the graph.

        Args:
            start_node_ids: Optional list of node IDs to start from.
                           If None, starts from all source nodes.
            direction: Direction to traverse.
            max_depth: Maximum depth to traverse.

        Returns:
            TraversalResult containing nodes in BFS order.
        """
        return self._connection_model.traverse_bfs(start_node_ids, direction, max_depth)

    def walk_from_start_nodes(
        self,
        strategy: TraversalStrategy = TraversalStrategy.DEPTH_FIRST,
        max_depth: int = 100,
    ) -> TraversalResult:
        """
        Walk the graph starting from all source nodes (entry points).

        This is critical for determining execution order during compilation.

        Args:
            strategy: The traversal strategy (DEPTH_FIRST or BREADTH_FIRST).
            max_depth: Maximum depth to traverse.

        Returns:
            TraversalResult containing nodes in traversal order.
        """
        return self._connection_model.walk_from_start_nodes(strategy, max_depth)

    def get_execution_order_from_start(
        self,
        start_node_ids: Optional[List[str]] = None,
        strategy: TraversalStrategy = TraversalStrategy.BREADTH_FIRST,
    ) -> List[BaseNode]:
        """
        Get nodes in execution order starting from specified nodes or source nodes.

        Args:
            start_node_ids: Optional list of specific start node IDs.
            strategy: The traversal strategy to use.

        Returns:
            List of nodes in execution order.
        """
        return self._connection_model.get_execution_order_from_start(start_node_ids, strategy)

    def get_flow_execution_order(
        self,
        start_node_ids: Optional[List[str]] = None,
        strategy: TraversalStrategy = TraversalStrategy.DEPTH_FIRST,
    ) -> List[BaseNode]:
        """
        Get nodes in execution order following FLOW connections.

        Args:
            start_node_ids: Optional list of specific start node IDs.
            strategy: The traversal strategy to use.

        Returns:
            List of nodes in FLOW execution order.
        """
        return self._connection_model.get_flow_execution_order(start_node_ids, strategy)

    def topological_sort(self) -> TopologicalSortResult:
        """
        Perform comprehensive topological sort with execution level information.

        This method provides a complete topological ordering suitable for script
        generation, including execution levels that indicate which nodes can be
        executed in parallel.

        Returns:
            TopologicalSortResult containing:
            - nodes: Ordered list in valid execution order
            - levels: Mapping of level number to nodes at that level
            - node_level_map: Mapping of node ID to its execution level
            - is_valid: False if graph has cycles
            - critical_path: The longest dependency chain
            - independent_groups: Groups of nodes with no inter-dependencies

        Example:
            >>> result = graph.topological_sort()
            >>> if result.is_valid:
            ...     for level in range(result.get_max_level() + 1):
            ...         parallel_nodes = result.get_nodes_at_level(level)
            ...         for node in parallel_nodes:
            ...             node.execute(inputs)
        """
        return self._connection_model.topological_sort()

    def get_execution_levels(self) -> Dict[int, List[BaseNode]]:
        """
        Get nodes grouped by their execution level.

        Execution levels indicate the order in which nodes should execute,
        where all nodes at level N must complete before any node at level N+1
        can start. Nodes at the same level have no dependencies between them.

        Returns:
            Dictionary mapping level number (0-indexed) to list of nodes at that level.
            Returns empty dict if graph has cycles.
        """
        return self._connection_model.get_execution_levels()

    def get_critical_path_nodes(self) -> List[BaseNode]:
        """
        Get nodes that form the critical path (longest dependency chain).

        The critical path determines the minimum execution time when nodes
        can execute in parallel.

        Returns:
            List of nodes in the critical path, or empty list if graph has cycles.
        """
        return self._connection_model.get_critical_path_nodes()

    def validate_execution_order(self, node_order: List[str]) -> Tuple[bool, List[str]]:
        """
        Validate that a given execution order respects all dependencies.

        Args:
            node_order: List of node IDs in the proposed execution order.

        Returns:
            Tuple of (is_valid, error_messages).
        """
        return self._connection_model.validate_execution_order(node_order)

    # Cycle Detection

    def has_cycle(self) -> bool:
        """Check if the graph contains any cycles."""
        return self._connection_model.has_cycle()

    def find_cycles(self) -> List[List[str]]:
        """Find all cycles in the graph."""
        return self._connection_model.find_cycles()

    # Validation

    def validate(self) -> List[str]:
        """
        Validate the entire graph.

        Returns:
            List of validation error messages. Empty if valid.
        """
        errors: List[str] = []

        # Validate all connections
        errors.extend(self._connection_model.validate_all_connections())

        # Validate each node
        for node in self.nodes:
            node_errors = node.validate()
            for error in node_errors:
                errors.append(f"{node.name}: {error}")

        # Check for cycles
        if self.has_cycle():
            errors.append("Graph contains cycles which may prevent execution")

        return errors

    def is_valid(self) -> bool:
        """Check if the graph is valid."""
        return len(self.validate()) == 0

    # Group Management

    def add_group(self, group: NodeGroup) -> None:
        """
        Add a node group to the graph.

        Args:
            group: The group to add.

        Raises:
            ValueError: If a group with the same ID already exists.
        """
        if group.id in self._groups:
            raise ValueError(f"Group with ID {group.id} already exists")
        self._groups[group.id] = group
        self._mark_modified()

    def remove_group(self, group_id: str) -> Optional[NodeGroup]:
        """
        Remove a group from the graph.

        The nodes in the group are not removed, only the group container.

        Args:
            group_id: The ID of the group to remove.

        Returns:
            The removed group, or None if not found.
        """
        group = self._groups.pop(group_id, None)
        if group:
            self._mark_modified()
        return group

    def get_group(self, group_id: str) -> Optional[NodeGroup]:
        """
        Get a group by its ID.

        Args:
            group_id: The ID of the group to find.

        Returns:
            The group if found, None otherwise.
        """
        return self._groups.get(group_id)

    def has_group(self, group_id: str) -> bool:
        """Check if a group exists in the graph."""
        return group_id in self._groups

    @property
    def groups(self) -> List[NodeGroup]:
        """Get a list of all groups in the graph."""
        return list(self._groups.values())

    @property
    def group_count(self) -> int:
        """Get the number of groups in the graph."""
        return len(self._groups)

    def get_group_for_node(self, node_id: str) -> Optional[NodeGroup]:
        """
        Get the group that contains a specific node.

        Args:
            node_id: The ID of the node to find.

        Returns:
            The group containing the node, or None if not in any group.
        """
        for group in self._groups.values():
            if group.contains_node(node_id):
                return group
        return None

    def get_groups_for_nodes(self, node_ids: List[str]) -> List[NodeGroup]:
        """
        Get all groups that contain any of the specified nodes.

        Args:
            node_ids: List of node IDs to check.

        Returns:
            List of groups that contain at least one of the nodes.
        """
        node_ids_set = set(node_ids)
        result = []
        for group in self._groups.values():
            if group.node_ids & node_ids_set:
                result.append(group)
        return result

    def create_group_from_selection(
        self,
        node_ids: List[str],
        name: str = "Group",
        color: Optional[str] = None,
    ) -> NodeGroup:
        """
        Create a new group from selected nodes.

        Args:
            node_ids: List of node IDs to include.
            name: Name for the new group.
            color: Optional custom color.

        Returns:
            The created group.
        """
        # Calculate bounds from node positions
        nodes = [self.get_node(nid) for nid in node_ids if self.has_node(nid)]
        nodes = [n for n in nodes if n is not None]

        group = NodeGroup(
            name=name,
            node_ids=set(node_ids),
            color=color,
        )

        if nodes:
            group.calculate_bounds_from_nodes(nodes)

        self.add_group(group)
        return group

    def iter_groups(self) -> Iterator[NodeGroup]:
        """Iterate over all groups in the graph."""
        return iter(self._groups.values())

    # Selection Management

    def select_node(self, node_id: str) -> None:
        """Add a node to the selection."""
        if self.has_node(node_id):
            self._selected_node_ids.add(node_id)

    def deselect_node(self, node_id: str) -> None:
        """Remove a node from the selection."""
        self._selected_node_ids.discard(node_id)

    def clear_selection(self) -> None:
        """Clear all node selections."""
        self._selected_node_ids.clear()

    def select_all(self) -> None:
        """Select all nodes."""
        self._selected_node_ids = {node.id for node in self.nodes}

    def is_selected(self, node_id: str) -> bool:
        """Check if a node is selected."""
        return node_id in self._selected_node_ids

    @property
    def selected_nodes(self) -> List[BaseNode]:
        """Get all selected nodes."""
        return [
            node for node in self.nodes if node.id in self._selected_node_ids
        ]

    @property
    def selected_node_ids(self) -> Set[str]:
        """Get IDs of all selected nodes."""
        return self._selected_node_ids.copy()

    # Statistics

    def get_statistics(self) -> GraphStatistics:
        """
        Calculate and return graph statistics.

        Returns:
            GraphStatistics object with current statistics.
        """
        node_types: Dict[str, int] = {}
        for node in self.nodes:
            node_types[node.node_type] = node_types.get(node.node_type, 0) + 1

        # Calculate max depth
        max_depth = self._calculate_max_depth()

        return GraphStatistics(
            node_count=self.node_count,
            connection_count=self.connection_count,
            source_node_count=len(self.get_source_nodes()),
            sink_node_count=len(self.get_sink_nodes()),
            max_depth=max_depth,
            node_types=node_types,
        )

    def _calculate_max_depth(self) -> int:
        """Calculate the maximum depth of the graph."""
        if self.is_empty:
            return 0

        # Use BFS from source nodes
        source_nodes = self.get_source_nodes()
        if not source_nodes:
            return 0

        max_depth = 0
        for source in source_nodes:
            visited: Set[str] = set()
            queue: List[Tuple[str, int]] = [(source.id, 0)]

            while queue:
                node_id, depth = queue.pop(0)
                if node_id in visited:
                    continue
                visited.add(node_id)
                max_depth = max(max_depth, depth)

                for conn in self.get_outgoing_connections(node_id):
                    if conn.target_node_id not in visited:
                        queue.append((conn.target_node_id, depth + 1))

        return max_depth

    # Serialization

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the graph to a dictionary.

        Returns:
            Dictionary representation of the graph.
        """
        data = {
            "id": self._id,
            "metadata": self._metadata.to_dict(),
            "nodes": [node.to_dict() for node in self.nodes],
            "connections": [conn.to_dict() for conn in self.connections],
        }
        # Only include groups if there are any
        if self._groups:
            data["groups"] = [group.to_dict() for group in self._groups.values()]
        return data

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        node_factory: Callable[[Dict[str, Any]], BaseNode],
    ) -> Graph:
        """
        Deserialize a graph from a dictionary.

        Args:
            data: Dictionary containing serialized graph data.
            node_factory: Function to create nodes from dictionaries.

        Returns:
            A new Graph instance.
        """
        graph = cls(
            graph_id=data.get("id"),
            name=data.get("metadata", {}).get("name", "Untitled Graph"),
            description=data.get("metadata", {}).get("description", ""),
        )

        # Restore full metadata
        if "metadata" in data:
            graph._metadata = GraphMetadata.from_dict(data["metadata"])

        # Restore nodes
        for node_data in data.get("nodes", []):
            node = node_factory(node_data)
            graph.add_node(node)

        # Restore connections
        for conn_data in data.get("connections", []):
            graph.connect(
                source_node_id=conn_data["source_node_id"],
                source_port_name=conn_data["source_port_name"],
                target_node_id=conn_data["target_node_id"],
                target_port_name=conn_data["target_port_name"],
                validate=False,
            )

        # Restore groups
        for group_data in data.get("groups", []):
            group = NodeGroup.from_dict(group_data)
            graph._groups[group.id] = group

        # Reset modified flag after loading
        graph._modified = False

        return graph

    # Graph Operations

    def clear(self) -> None:
        """Remove all nodes, connections, and groups from the graph."""
        self._connection_model.clear()
        self._groups.clear()
        self._selected_node_ids.clear()
        self._mark_modified()

    def reset_execution_state(self) -> None:
        """Reset all nodes to IDLE state."""
        for node in self.nodes:
            node.reset_state()
        self._state = GraphState.IDLE
        self._last_error = None

    def duplicate_node(self, node_id: str) -> Optional[BaseNode]:
        """
        Create a duplicate of a node (without connections).

        Args:
            node_id: The ID of the node to duplicate.

        Returns:
            The new duplicated node, or None if original not found.

        Note:
            The duplicated node will have a new ID and offset position.
            Connections are not duplicated.
        """
        original = self.get_node(node_id)
        if original is None:
            return None

        # Serialize and deserialize to create a copy
        node_data = original.to_dict()

        # Generate new ID
        node_data["id"] = str(uuid.uuid4())

        # Offset position
        if "position" in node_data:
            node_data["position"]["x"] = node_data["position"].get("x", 0) + 50
            node_data["position"]["y"] = node_data["position"].get("y", 0) + 50

        # Clear connections from port data
        for port_data in node_data.get("input_ports", []):
            port_data["connection"] = None
        for port_data in node_data.get("output_ports", []):
            port_data["connections"] = []

        # This would require a node factory to recreate
        # For now, return None as proper implementation needs factory
        return None

    # Internal Methods

    def _mark_modified(self) -> None:
        """Mark the graph as modified and update timestamp."""
        self._modified = True
        self._metadata.modified_at = datetime.now().isoformat()

    def mark_saved(self) -> None:
        """Mark the graph as saved (not modified)."""
        self._modified = False

    # String Representations

    def __repr__(self) -> str:
        """Get a detailed string representation."""
        return (
            f"Graph(id='{self._id[:8]}...', name='{self.name}', "
            f"nodes={self.node_count}, connections={self.connection_count})"
        )

    def __str__(self) -> str:
        """Get a simple string representation."""
        return f"Graph '{self.name}' with {self.node_count} nodes and {self.connection_count} connections"

    def __len__(self) -> int:
        """Return the number of nodes in the graph."""
        return self.node_count

    def __contains__(self, node_or_id: Any) -> bool:
        """Check if a node is in the graph."""
        if isinstance(node_or_id, str):
            return self.has_node(node_or_id)
        if hasattr(node_or_id, "id"):
            return self.has_node(node_or_id.id)
        return False

    def __iter__(self) -> Iterator[BaseNode]:
        """Iterate over nodes in the graph."""
        return iter(self.nodes)
