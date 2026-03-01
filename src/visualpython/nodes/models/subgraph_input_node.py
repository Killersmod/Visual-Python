"""
Subgraph input node model that defines an input interface for a subgraph.

This module defines the SubgraphInputNode class, which represents an input
parameter within a subgraph. When a subgraph is used, this node provides
the value passed in from the external caller.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class SubgraphInputNode(BaseNode):
    """
    A node that defines an input parameter for a subgraph.

    The SubgraphInputNode represents an input interface point within a subgraph.
    When the parent subgraph is called, the value provided to the corresponding
    input port is made available through this node's output.

    Each SubgraphInputNode defines one input parameter for the subgraph, with
    configurable name, type, description, and default value.

    Attributes:
        port_name: The name of this input as seen on the parent SubgraphNode.
        port_type_setting: The data type this input expects.
        description: Human-readable description of this input.
        default_value: Default value if the input is not connected.

    Example:
        >>> node = SubgraphInputNode(name="value_input")
        >>> node.port_name = "value"
        >>> node.port_type_setting = PortType.INTEGER
        >>> node.default_value = 0
    """

    # Class-level metadata
    node_type: str = "subgraph_input"
    """Unique identifier for subgraph input nodes."""

    node_category: str = "Subgraphs"
    """Category for organizing in the UI."""

    node_color: str = "#4CAF50"
    """Green color to indicate inputs/entry points."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        port_name: Optional[str] = None,
        port_type_setting: PortType = PortType.ANY,
        default_value: Any = None,
    ) -> None:
        """
        Initialize a new SubgraphInputNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Subgraph Input'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            port_name: The name of this input parameter.
            port_type_setting: The expected data type for this input.
            default_value: Default value if input is not provided.
        """
        # Initialize subgraph input-specific attributes before calling super().__init__
        self._port_name: str = port_name or "input"
        self._port_type_setting: PortType = port_type_setting
        self._description: str = ""
        self._default_value: Any = default_value

        super().__init__(node_id, name or "Subgraph Input", position)

    def _setup_ports(self) -> None:
        """
        Set up the output ports for the subgraph input node.

        The subgraph input node has:
        - An execution flow output port (exec_out) for control flow
        - A data output port (value) that provides the input value

        Subgraph input nodes have no data input ports since they receive
        their value from the parent subgraph's input.
        """
        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Value output - provides the input value to downstream nodes
        self.add_output_port(OutputPort(
            name="value",
            port_type=self._port_type_setting,
            description=f"Value received from subgraph input '{self._port_name}'",
        ))

    # Properties
    @property
    def port_name(self) -> str:
        """Get the name of this input parameter."""
        return self._port_name

    @port_name.setter
    def port_name(self, value: str) -> None:
        """Set the name of this input parameter."""
        self._port_name = value

    @property
    def port_type_setting(self) -> PortType:
        """Get the expected data type for this input."""
        return self._port_type_setting

    @port_type_setting.setter
    def port_type_setting(self, value: PortType) -> None:
        """
        Set the expected data type for this input.

        This also updates the value output port's type.
        """
        self._port_type_setting = value
        # Update the output port type
        value_port = self.get_output_port("value")
        if value_port:
            value_port._port_type = value

    @property
    def input_description(self) -> str:
        """Get the description of this input parameter."""
        return self._description

    @input_description.setter
    def input_description(self, value: str) -> None:
        """Set the description of this input parameter."""
        self._description = value

    @property
    def default_value(self) -> Any:
        """Get the default value for this input."""
        return self._default_value

    @default_value.setter
    def default_value(self, value: Any) -> None:
        """Set the default value for this input."""
        self._default_value = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Port name must be non-empty
        if not self._port_name or not self._port_name.strip():
            errors.append("Input port name cannot be empty")

        # Port name should be a valid Python identifier
        if self._port_name and not self._port_name.isidentifier():
            errors.append(
                f"Input port name '{self._port_name}' is not a valid identifier. "
                "Use only letters, numbers, and underscores, starting with a letter."
            )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the subgraph input node.

        During execution, this node receives its value from the subgraph
        execution context and outputs it for downstream nodes.

        Args:
            inputs: Dictionary containing the input value (set by execution engine).

        Returns:
            Dictionary containing the value output and exec_out signal.
        """
        # The value is provided by the subgraph execution context
        # via the _subgraph_input key
        value = inputs.get("_subgraph_input", self._default_value)

        return {
            "exec_out": None,
            "value": value,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get subgraph input-specific properties for serialization.

        Returns:
            Dictionary of serializable properties.
        """
        return {
            "port_name": self._port_name,
            "port_type": self._port_type_setting.name,
            "description": self._description,
            "default_value": self._default_value,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load subgraph input-specific properties from serialized data.

        Args:
            properties: Dictionary of serialized properties.
        """
        self._port_name = properties.get("port_name", "input")
        self._description = properties.get("description", "")
        self._default_value = properties.get("default_value")

        # Parse port type
        port_type_str = properties.get("port_type", "ANY")
        try:
            self._port_type_setting = PortType[port_type_str]
        except KeyError:
            self._port_type_setting = PortType.ANY

        # Update output port type
        value_port = self.get_output_port("value")
        if value_port:
            value_port._port_type = self._port_type_setting

    def __repr__(self) -> str:
        """Get a detailed string representation of the subgraph input node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"port_name='{self._port_name}', "
            f"type={self._port_type_setting.name}, "
            f"state={self._execution_state.name})"
        )
