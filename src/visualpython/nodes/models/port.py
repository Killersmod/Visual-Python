"""
Port classes for node connections in VisualPython.

This module defines input and output ports that nodes use to connect
and pass data between each other.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode
    from visualpython.execution.type_info import TypeInfo


class PortType(Enum):
    """Defines the type of data a port can accept or produce."""

    ANY = auto()
    """Accepts any data type."""

    FLOW = auto()
    """Execution flow connection (no data, just execution order)."""

    STRING = auto()
    """String data type."""

    INTEGER = auto()
    """Integer data type."""

    FLOAT = auto()
    """Float/decimal data type."""

    BOOLEAN = auto()
    """Boolean data type."""

    LIST = auto()
    """List/array data type."""

    DICT = auto()
    """Dictionary data type."""

    OBJECT = auto()
    """Generic Python object."""


# Type compatibility mapping - source types that can connect to destination types
TYPE_COMPATIBILITY: Dict[PortType, List[PortType]] = {
    PortType.ANY: list(PortType),  # ANY accepts everything
    PortType.FLOW: [PortType.FLOW],  # FLOW only accepts FLOW
    PortType.STRING: [PortType.STRING, PortType.ANY],
    PortType.INTEGER: [PortType.INTEGER, PortType.FLOAT, PortType.ANY],
    PortType.FLOAT: [PortType.FLOAT, PortType.INTEGER, PortType.ANY],
    PortType.BOOLEAN: [PortType.BOOLEAN, PortType.ANY],
    PortType.LIST: [PortType.LIST, PortType.ANY],
    PortType.DICT: [PortType.DICT, PortType.ANY],
    PortType.OBJECT: [PortType.OBJECT, PortType.ANY],
}


def are_types_compatible(source_type: PortType, target_type: PortType) -> bool:
    """
    Check if a source port type can connect to a target port type.

    This is a utility function for quick type compatibility checks
    without needing to create port instances.

    Args:
        source_type: The type of the output/source port.
        target_type: The type of the input/target port.

    Returns:
        True if the types are compatible for connection.
    """
    # ANY accepts everything
    if target_type == PortType.ANY:
        return True

    # ANY can connect to anything
    if source_type == PortType.ANY:
        return True

    # Check compatibility mapping
    compatible_types = TYPE_COMPATIBILITY.get(target_type, [])
    return source_type in compatible_types


@dataclass
class Connection:
    """
    Represents a connection between two ports.

    Attributes:
        source_node_id: ID of the node containing the source port.
        source_port_name: Name of the source (output) port.
        target_node_id: ID of the node containing the target port.
        target_port_name: Name of the target (input) port.
    """

    source_node_id: str
    source_port_name: str
    target_node_id: str
    target_port_name: str

    def to_dict(self) -> Dict[str, str]:
        """Serialize the connection to a dictionary."""
        return {
            "source_node_id": self.source_node_id,
            "source_port_name": self.source_port_name,
            "target_node_id": self.target_node_id,
            "target_port_name": self.target_port_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> Connection:
        """Deserialize a connection from a dictionary."""
        return cls(
            source_node_id=data["source_node_id"],
            source_port_name=data["source_port_name"],
            target_node_id=data["target_node_id"],
            target_port_name=data["target_port_name"],
        )


class BasePort(ABC):
    """
    Abstract base class for node ports.

    Ports are the connection points on nodes through which data flows.
    Each port has a name, type, and optional description.

    Attributes:
        name: Unique name of the port within its node.
        port_type: The data type this port accepts or produces.
        description: Human-readable description of the port's purpose.
        node: Reference to the node this port belongs to.
    """

    def __init__(
        self,
        name: str,
        port_type: PortType = PortType.ANY,
        description: str = "",
    ) -> None:
        """
        Initialize a port.

        Args:
            name: Unique name for this port within its node.
            port_type: The type of data this port handles.
            description: Human-readable description.
        """
        self._name = name
        self._port_type = port_type
        self._description = description
        self._node: Optional[BaseNode] = None
        # Runtime type inference support
        self._inferred_type: Optional[TypeInfo] = None

    @property
    def name(self) -> str:
        """Get the port name."""
        return self._name

    @property
    def port_type(self) -> PortType:
        """Get the port data type."""
        return self._port_type

    @property
    def description(self) -> str:
        """Get the port description."""
        return self._description

    @property
    def node(self) -> Optional[BaseNode]:
        """Get the node this port belongs to."""
        return self._node

    @node.setter
    def node(self, value: Optional[BaseNode]) -> None:
        """Set the node this port belongs to."""
        self._node = value

    @property
    def inferred_type(self) -> Optional[TypeInfo]:
        """Get the inferred runtime type for this port."""
        return self._inferred_type

    @inferred_type.setter
    def inferred_type(self, value: Optional[TypeInfo]) -> None:
        """Set the inferred runtime type for this port."""
        self._inferred_type = value

    def clear_inferred_type(self) -> None:
        """Clear the inferred type information."""
        self._inferred_type = None

    def get_effective_type_name(self) -> str:
        """
        Get the most specific type name available.

        Returns the inferred type name if available, otherwise
        returns the declared port type name.
        """
        if self._inferred_type:
            return self._inferred_type.type_name
        return self._port_type.name

    def is_connected(self) -> bool:
        """Check if this port has any connections."""
        raise NotImplementedError("Subclasses must implement is_connected()")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the port to a dictionary."""
        return {
            "name": self._name,
            "type": self._port_type.name,
            "description": self._description,
        }

    def __repr__(self) -> str:
        """Get a string representation of the port."""
        node_name = self._node.name if self._node else "unattached"
        return f"{self.__class__.__name__}(name='{self._name}', type={self._port_type.name}, node='{node_name}')"

    def __str__(self) -> str:
        """Get a simple string representation."""
        return f"{self._name} ({self._port_type.name})"


class InputPort(BasePort):
    """
    An input port that receives data from output ports.

    Input ports can have at most one incoming connection (single source).
    They can also have default values, inline user-entered values, and be marked as required.

    Attributes:
        required: Whether this input must be connected for the node to execute.
        default_value: Default value if no connection provides data.
        inline_value: User-entered value via inline widget when port is not connected.
        connection: The incoming connection, if any.

    Value Priority (during execution):
        1. Connected value (from another node's output port)
        2. Inline value (user-entered via inline widget)
        3. Default value (defined in node definition)
    """

    def __init__(
        self,
        name: str,
        port_type: PortType = PortType.ANY,
        description: str = "",
        required: bool = True,
        default_value: Any = None,
        inline_value: Any = None,
        display_hint: Any = None,
    ) -> None:
        """
        Initialize an input port.

        Args:
            name: Unique name for this port within its node.
            port_type: The type of data this port accepts.
            description: Human-readable description.
            required: Whether this input must be connected.
            default_value: Default value if not connected.
            inline_value: User-entered value via inline widget.
            display_hint: Display-only value shown in the widget when no
                         inline_value or default_value is set. Does NOT
                         affect execution (get_effective_value ignores it).
        """
        super().__init__(name, port_type, description)
        self._required = required
        self._default_value = default_value
        self._inline_value = inline_value
        self._display_hint = display_hint
        self._connection: Optional[Connection] = None

    @property
    def required(self) -> bool:
        """Check if this input port is required."""
        return self._required

    @property
    def default_value(self) -> Any:
        """Get the default value for this port."""
        return self._default_value

    @default_value.setter
    def default_value(self, value: Any) -> None:
        """Set the default value for this port."""
        self._default_value = value

    @property
    def inline_value(self) -> Any:
        """Get the user-entered inline value for this port."""
        return self._inline_value

    @inline_value.setter
    def inline_value(self, value: Any) -> None:
        """Set the user-entered inline value for this port."""
        self._inline_value = value

    @property
    def display_hint(self) -> Any:
        """Get the display-only hint value for this port's widget."""
        return self._display_hint

    @display_hint.setter
    def display_hint(self, value: Any) -> None:
        """Set the display-only hint value for this port's widget."""
        self._display_hint = value

    def has_inline_value(self) -> bool:
        """
        Check if this port has an inline value set.

        Returns:
            True if inline_value is not None.
        """
        return self._inline_value is not None

    def clear_inline_value(self) -> None:
        """Clear the inline value, resetting it to None."""
        self._inline_value = None

    def get_effective_value(self) -> Any:
        """
        Get the effective value for this port based on priority.

        Returns the value that should be used during execution,
        following the priority: inline_value > default_value.

        Note: This does NOT account for connected values, which take
        highest priority but are resolved by the execution engine.

        Returns:
            The inline value if set, otherwise the default value.
        """
        if self._inline_value is not None:
            return self._inline_value
        return self._default_value

    @property
    def connection(self) -> Optional[Connection]:
        """Get the incoming connection."""
        return self._connection

    def is_connected(self) -> bool:
        """Check if this port has an incoming connection."""
        return self._connection is not None

    def connect(self, connection: Connection) -> None:
        """
        Set the incoming connection.

        Args:
            connection: The connection to set.
        """
        self._connection = connection

    def disconnect(self) -> Optional[Connection]:
        """
        Remove the incoming connection.

        Returns:
            The removed connection, or None if there wasn't one.
        """
        old_connection = self._connection
        self._connection = None
        return old_connection

    def can_accept_type(self, source_type: PortType) -> bool:
        """
        Check if this port can accept a connection from a source of the given type.

        Args:
            source_type: The type of the source port.

        Returns:
            True if the types are compatible.
        """
        # ANY accepts everything
        if self._port_type == PortType.ANY:
            return True

        # Check compatibility mapping
        compatible_types = TYPE_COMPATIBILITY.get(self._port_type, [])
        return source_type in compatible_types or source_type == PortType.ANY

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the input port to a dictionary."""
        data = super().to_dict()
        data.update({
            "required": self._required,
            "default_value": self._default_value,
            "inline_value": self._inline_value,
            "connection": self._connection.to_dict() if self._connection else None,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InputPort:
        """Deserialize an input port from a dictionary."""
        port = cls(
            name=data["name"],
            port_type=PortType[data["type"]],
            description=data.get("description", ""),
            required=data.get("required", True),
            default_value=data.get("default_value"),
            inline_value=data.get("inline_value"),
        )
        if data.get("connection"):
            port._connection = Connection.from_dict(data["connection"])
        return port


class OutputPort(BasePort):
    """
    An output port that sends data to input ports.

    Output ports can have multiple outgoing connections (fan-out).

    Attributes:
        connections: List of outgoing connections.
    """

    def __init__(
        self,
        name: str,
        port_type: PortType = PortType.ANY,
        description: str = "",
    ) -> None:
        """
        Initialize an output port.

        Args:
            name: Unique name for this port within its node.
            port_type: The type of data this port produces.
            description: Human-readable description.
        """
        super().__init__(name, port_type, description)
        self._connections: List[Connection] = []

    @property
    def connections(self) -> List[Connection]:
        """Get a copy of the outgoing connections list."""
        return self._connections.copy()

    def is_connected(self) -> bool:
        """Check if this port has any outgoing connections."""
        return len(self._connections) > 0

    def connect(self, connection: Connection) -> None:
        """
        Add an outgoing connection.

        Args:
            connection: The connection to add.
        """
        # Avoid duplicate connections
        for existing in self._connections:
            if (existing.target_node_id == connection.target_node_id and
                existing.target_port_name == connection.target_port_name):
                return
        self._connections.append(connection)

    def disconnect(self, target_node_id: str, target_port_name: str) -> Optional[Connection]:
        """
        Remove a specific outgoing connection.

        Args:
            target_node_id: ID of the target node.
            target_port_name: Name of the target port.

        Returns:
            The removed connection, or None if not found.
        """
        for i, conn in enumerate(self._connections):
            if conn.target_node_id == target_node_id and conn.target_port_name == target_port_name:
                return self._connections.pop(i)
        return None

    def disconnect_all(self) -> List[Connection]:
        """
        Remove all outgoing connections.

        Returns:
            List of removed connections.
        """
        connections = self._connections.copy()
        self._connections.clear()
        return connections

    def can_connect_to(self, target_type: PortType) -> bool:
        """
        Check if this port can connect to a target of the given type.

        Args:
            target_type: The type of the target port.

        Returns:
            True if the types are compatible.
        """
        # ANY can connect to anything
        if self._port_type == PortType.ANY:
            return True

        # Check if target accepts this type
        compatible_types = TYPE_COMPATIBILITY.get(target_type, [])
        return self._port_type in compatible_types or target_type == PortType.ANY

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the output port to a dictionary."""
        data = super().to_dict()
        data["connections"] = [conn.to_dict() for conn in self._connections]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OutputPort:
        """Deserialize an output port from a dictionary."""
        port = cls(
            name=data["name"],
            port_type=PortType[data["type"]],
            description=data.get("description", ""),
        )
        for conn_data in data.get("connections", []):
            port._connections.append(Connection.from_dict(conn_data))
        return port
