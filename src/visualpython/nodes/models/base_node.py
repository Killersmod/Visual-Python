"""
Base node class providing the foundation for all node types in VisualPython.

This module defines the abstract base class that all specialized node implementations
inherit from, providing common properties like ID, position, connections, and execution state.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from visualpython.nodes.models.port import InputPort, OutputPort
    from visualpython.execution.error_report import ErrorReport


class ExecutionState(Enum):
    """Represents the current execution state of a node."""

    IDLE = auto()
    """Node is not currently executing and hasn't been executed."""

    PENDING = auto()
    """Node is queued for execution, waiting for inputs."""

    RUNNING = auto()
    """Node is currently executing."""

    COMPLETED = auto()
    """Node has finished executing successfully."""

    ERROR = auto()
    """Node encountered an error during execution."""

    SKIPPED = auto()
    """Node was skipped (e.g., due to conditional branching)."""


@dataclass
class Position:
    """Represents a 2D position on the node canvas."""

    x: float = 0.0
    y: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Convert position to dictionary for serialization."""
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> Position:
        """Create a Position from a dictionary."""
        return cls(x=data.get("x", 0.0), y=data.get("y", 0.0))


class BaseNode(ABC):
    """
    Abstract base class for all node types in the VisualPython visual scripting system.

    This class provides the common interface and properties that all nodes must implement,
    including:
    - Unique identification
    - Position on the canvas
    - Input and output ports for connections
    - Execution state tracking
    - Serialization support

    Subclasses must implement the abstract methods to define node-specific behavior.

    Attributes:
        id: Unique identifier for this node instance.
        name: Display name shown on the node.
        position: The (x, y) position of the node on the canvas.
        execution_state: Current state of node execution.
        execution_errors: List of ErrorReport objects for errors that occurred during execution.
        input_ports: List of input ports that can receive connections.
        output_ports: List of output ports that can send connections.
        comment: Optional comment/note for documentation purposes.
    """

    # Class-level attributes for node metadata
    node_type: str = "base"
    """Unique identifier for this node type (e.g., 'code', 'if', 'for_loop')."""

    node_category: str = "General"
    """Category for organizing nodes in the UI (e.g., 'Control Flow', 'Variables')."""

    node_color: str = "#808080"
    """Default color for this node type in hex format."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
    ) -> None:
        """
        Initialize a new node instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to the node type.
            position: Optional initial position. If not provided, defaults to (0, 0).
        """
        self._id: str = node_id or str(uuid.uuid4())
        self._name: str = name or self._get_default_name()
        self._position: Position = position or Position()
        self._execution_state: ExecutionState = ExecutionState.IDLE
        self._error_message: Optional[str] = None

        # Execution errors list to store multiple errors (e.g., validation + runtime)
        self._execution_errors: List[ErrorReport] = []

        # Custom color for visual organization (None = use class default)
        self._custom_color: Optional[str] = None

        # Comment/note field for documentation purposes
        self._comment: str = ""

        # Port collections - initialized by subclasses
        self._input_ports: List[InputPort] = []
        self._output_ports: List[OutputPort] = []

        # Execution data
        self._input_data: Dict[str, Any] = {}
        self._output_data: Dict[str, Any] = {}

        # Initialize ports defined by the subclass
        self._setup_ports()

    def _get_default_name(self) -> str:
        """Get the default display name for this node type."""
        # Use display_name class attribute if set, otherwise derive from node_type
        display_name = getattr(self, 'display_name', None)
        if display_name:
            return display_name
        # Convert node_type like 'for_loop' to 'For Loop'
        return self.node_type.replace("_", " ").title()

    @abstractmethod
    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for this node.

        Subclasses must implement this method to define their specific ports.
        This is called during initialization.
        """
        pass

    @abstractmethod
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the node's logic with the given inputs.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary mapping output port names to their values.

        Raises:
            NodeExecutionError: If execution fails.
        """
        pass

    @abstractmethod
    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        pass

    # Properties
    @property
    def id(self) -> str:
        """Get the unique identifier for this node."""
        return self._id

    @property
    def name(self) -> str:
        """Get the display name of this node."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set the display name of this node."""
        self._name = value

    @property
    def position(self) -> Position:
        """Get the position of this node on the canvas."""
        return self._position

    @position.setter
    def position(self, value: Position) -> None:
        """Set the position of this node on the canvas."""
        self._position = value

    @property
    def execution_state(self) -> ExecutionState:
        """Get the current execution state of this node."""
        return self._execution_state

    @execution_state.setter
    def execution_state(self, value: ExecutionState) -> None:
        """Set the execution state of this node."""
        self._execution_state = value
        # Clear error message and execution errors when state changes (unless setting to ERROR)
        if value != ExecutionState.ERROR:
            self._error_message = None
            self._execution_errors.clear()

    @property
    def error_message(self) -> Optional[str]:
        """Get the error message if the node is in ERROR state."""
        return self._error_message

    @error_message.setter
    def error_message(self, value: Optional[str]) -> None:
        """Set the error message for this node."""
        self._error_message = value

    @property
    def execution_errors(self) -> List[ErrorReport]:
        """Get the list of execution errors for this node.

        Returns a copy of the internal list to prevent external modification.
        Use add_execution_error() and clear_execution_errors() to modify.

        Returns:
            List of ErrorReport objects representing errors that occurred
            during this node's execution (may include validation, runtime,
            and other error types).
        """
        return self._execution_errors.copy()

    def add_execution_error(self, error: ErrorReport) -> None:
        """Add an execution error to this node's error list.

        Args:
            error: The ErrorReport to add to the node's error collection.
        """
        self._execution_errors.append(error)

    def clear_execution_errors(self) -> None:
        """Clear all execution errors from this node."""
        self._execution_errors.clear()

    def has_execution_errors(self) -> bool:
        """Check if this node has any execution errors.

        Returns:
            True if the node has one or more execution errors, False otherwise.
        """
        return len(self._execution_errors) > 0

    @property
    def custom_color(self) -> Optional[str]:
        """Get the custom color for this node instance, if set."""
        return self._custom_color

    @custom_color.setter
    def custom_color(self, value: Optional[str]) -> None:
        """Set a custom color for this node instance.

        Args:
            value: Hex color string (e.g., '#FF5722') or None to use class default.
        """
        self._custom_color = value

    @property
    def display_color(self) -> str:
        """Get the color to display for this node.

        Returns the custom color if set, otherwise falls back to the
        class-level node_color for this node type.
        """
        return self._custom_color if self._custom_color else self.node_color

    @property
    def comment(self) -> str:
        """Get the comment/note for this node."""
        return self._comment

    @comment.setter
    def comment(self, value: str) -> None:
        """Set the comment/note for this node.

        Args:
            value: The comment text for documentation purposes.
        """
        self._comment = value if value else ""

    @property
    def input_ports(self) -> List[InputPort]:
        """Get the list of input ports."""
        return self._input_ports.copy()

    @property
    def output_ports(self) -> List[OutputPort]:
        """Get the list of output ports."""
        return self._output_ports.copy()

    @property
    def input_data(self) -> Dict[str, Any]:
        """Get the current input data dictionary."""
        return self._input_data.copy()

    @property
    def output_data(self) -> Dict[str, Any]:
        """Get the current output data dictionary."""
        return self._output_data.copy()

    # Port management methods
    def add_input_port(self, port: InputPort) -> None:
        """
        Add an input port to this node.

        Args:
            port: The input port to add.
        """
        port.node = self
        self._input_ports.append(port)

    def add_output_port(self, port: OutputPort) -> None:
        """
        Add an output port to this node.

        Args:
            port: The output port to add.
        """
        port.node = self
        self._output_ports.append(port)

    def get_input_port(self, name: str) -> Optional[InputPort]:
        """
        Get an input port by name.

        Args:
            name: The name of the port to find.

        Returns:
            The input port if found, None otherwise.
        """
        for port in self._input_ports:
            if port.name == name:
                return port
        return None

    def get_output_port(self, name: str) -> Optional[OutputPort]:
        """
        Get an output port by name.

        Args:
            name: The name of the port to find.

        Returns:
            The output port if found, None otherwise.
        """
        for port in self._output_ports:
            if port.name == name:
                return port
        return None

    def remove_input_port(self, name: str) -> bool:
        """
        Remove an input port by name.

        Args:
            name: The name of the port to remove.

        Returns:
            True if the port was removed, False if not found.
        """
        for i, port in enumerate(self._input_ports):
            if port.name == name:
                self._input_ports.pop(i)
                return True
        return False

    def remove_output_port(self, name: str) -> bool:
        """
        Remove an output port by name.

        Args:
            name: The name of the port to remove.

        Returns:
            True if the port was removed, False if not found.
        """
        for i, port in enumerate(self._output_ports):
            if port.name == name:
                self._output_ports.pop(i)
                return True
        return False

    # Execution methods
    def set_input(self, port_name: str, value: Any) -> None:
        """
        Set the input value for a specific port.

        Args:
            port_name: The name of the input port.
            value: The value to set.
        """
        self._input_data[port_name] = value

    def get_output(self, port_name: str) -> Any:
        """
        Get the output value from a specific port.

        Args:
            port_name: The name of the output port.

        Returns:
            The output value, or None if not set.
        """
        return self._output_data.get(port_name)

    def clear_execution_data(self) -> None:
        """Clear all input and output data from the last execution."""
        self._input_data.clear()
        self._output_data.clear()

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        self._execution_state = ExecutionState.IDLE
        self._error_message = None
        self.clear_execution_errors()
        self.clear_execution_data()

    def run(self) -> None:
        """
        Run the node execution with current input data.

        This method manages the execution state transitions and error handling.
        """
        try:
            self._execution_state = ExecutionState.RUNNING
            self._output_data = self.execute(self._input_data)
            self._execution_state = ExecutionState.COMPLETED
        except Exception as e:
            self._execution_state = ExecutionState.ERROR
            self._error_message = str(e)
            raise

    # Connection status methods
    def has_all_required_inputs(self) -> bool:
        """
        Check if all required input ports have connections or data.

        Returns:
            True if all required inputs are satisfied.
        """
        for port in self._input_ports:
            if port.required and port.name not in self._input_data:
                if not port.is_connected():
                    return False
        return True

    def get_connected_input_ports(self) -> List[InputPort]:
        """Get all input ports that have connections."""
        return [port for port in self._input_ports if port.is_connected()]

    def get_connected_output_ports(self) -> List[OutputPort]:
        """Get all output ports that have connections."""
        return [port for port in self._output_ports if port.is_connected()]

    # Code preview method
    def get_code_preview(self) -> Optional[str]:
        """
        Get a preview of the Python code this node would generate.

        This method returns a string representation of the equivalent Python code
        that this node represents. It is used for displaying a read-only code preview
        in the node widget, helping users understand what each node does.

        Subclasses should override this method to return their specific code representation.
        The returned code should be a valid Python snippet that reflects the node's
        current configuration (e.g., property values, connected inputs).

        Returns:
            A string containing the Python code preview, or None if this node type
            does not support code preview.

        Example:
            For a PrintNode with message="Hello", this might return:
            'print("Hello")'
        """
        return None

    # Serialization methods
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the node to a dictionary for JSON storage.

        Returns:
            Dictionary representation of the node.
        """
        data = {
            "id": self._id,
            "type": self.node_type,
            "name": self._name,
            "position": self._position.to_dict(),
            "input_ports": [port.to_dict() for port in self._input_ports],
            "output_ports": [port.to_dict() for port in self._output_ports],
            "properties": self._get_serializable_properties(),
        }
        # Only include custom_color if set (to keep files clean)
        if self._custom_color:
            data["custom_color"] = self._custom_color
        # Only include comment if set (to keep files clean)
        if self._comment:
            data["comment"] = self._comment
        return data

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get node-specific properties for serialization.

        Subclasses should override this to include their custom properties.

        Returns:
            Dictionary of serializable properties.
        """
        return {}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaseNode:
        """
        Deserialize a node from a dictionary.

        Args:
            data: Dictionary containing node data.

        Returns:
            A new node instance.

        Note:
            This is typically called by a NodeFactory that knows the correct
            subclass to instantiate based on the 'type' field.
        """
        position = Position.from_dict(data.get("position", {}))
        node = cls(
            node_id=data.get("id"),
            name=data.get("name"),
            position=position,
        )
        node._load_serializable_properties(data.get("properties", {}))
        # Restore port inline values from serialized data
        for port_data in data.get("input_ports", []):
            port_name = port_data.get("name")
            inline_value = port_data.get("inline_value")
            if port_name and inline_value is not None:
                port = node.get_input_port(port_name)
                if port:
                    port.inline_value = inline_value
        # Restore custom color if saved
        if "custom_color" in data:
            node._custom_color = data["custom_color"]
        # Restore comment if saved
        if "comment" in data:
            node._comment = data["comment"]
        return node

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load node-specific properties from serialized data.

        Subclasses should override this to restore their custom properties.

        Args:
            properties: Dictionary of serialized properties.
        """
        pass

    # String representations
    def __repr__(self) -> str:
        """Get a detailed string representation of the node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"type='{self.node_type}', "
            f"position=({self._position.x}, {self._position.y}), "
            f"state={self._execution_state.name})"
        )

    def __str__(self) -> str:
        """Get a simple string representation of the node."""
        return f"{self._name} ({self.node_type})"

    def __eq__(self, other: object) -> bool:
        """Check equality based on node ID."""
        if not isinstance(other, BaseNode):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        """Hash based on node ID."""
        return hash(self._id)
