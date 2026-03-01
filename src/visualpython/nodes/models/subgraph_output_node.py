"""
Subgraph output node model that defines an output interface for a subgraph.

This module defines the SubgraphOutputNode class, which represents an output
parameter within a subgraph. When a subgraph is used, this node captures
a value to be returned to the external caller.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class SubgraphOutputNode(BaseNode):
    """
    A node that defines an output parameter for a subgraph.

    The SubgraphOutputNode represents an output interface point within a subgraph.
    When the subgraph completes execution, the value provided to this node's input
    is returned through the parent SubgraphNode's corresponding output port.

    Each SubgraphOutputNode defines one output parameter for the subgraph, with
    configurable name, type, and description.

    Attributes:
        port_name: The name of this output as seen on the parent SubgraphNode.
        port_type_setting: The data type this output produces.
        description: Human-readable description of this output.

    Example:
        >>> node = SubgraphOutputNode(name="result_output")
        >>> node.port_name = "result"
        >>> node.port_type_setting = PortType.INTEGER
    """

    # Class-level metadata
    node_type: str = "subgraph_output"
    """Unique identifier for subgraph output nodes."""

    node_category: str = "Subgraphs"
    """Category for organizing in the UI."""

    node_color: str = "#F44336"
    """Red color to indicate outputs/exit points."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        port_name: Optional[str] = None,
        port_type_setting: PortType = PortType.ANY,
    ) -> None:
        """
        Initialize a new SubgraphOutputNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Subgraph Output'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            port_name: The name of this output parameter.
            port_type_setting: The data type for this output.
        """
        # Initialize subgraph output-specific attributes before calling super().__init__
        self._port_name: str = port_name or "output"
        self._port_type_setting: PortType = port_type_setting
        self._description: str = ""

        super().__init__(node_id, name or "Subgraph Output", position)

    def _setup_ports(self) -> None:
        """
        Set up the input ports for the subgraph output node.

        The subgraph output node has:
        - An execution flow input port (exec_in) for control flow
        - A data input port (value) that receives the output value

        Subgraph output nodes have no data output ports since they send
        their value to the parent subgraph's output.
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # Value input - receives the value to output from the subgraph
        self.add_input_port(InputPort(
            name="value",
            port_type=self._port_type_setting,
            description=f"Value to output as subgraph output '{self._port_name}'",
            required=False,
        ))

    # Properties
    @property
    def port_name(self) -> str:
        """Get the name of this output parameter."""
        return self._port_name

    @port_name.setter
    def port_name(self, value: str) -> None:
        """Set the name of this output parameter."""
        self._port_name = value

    @property
    def port_type_setting(self) -> PortType:
        """Get the data type for this output."""
        return self._port_type_setting

    @port_type_setting.setter
    def port_type_setting(self, value: PortType) -> None:
        """
        Set the data type for this output.

        This also updates the value input port's type.
        """
        self._port_type_setting = value
        # Update the input port type
        value_port = self.get_input_port("value")
        if value_port:
            value_port._port_type = value

    @property
    def output_description(self) -> str:
        """Get the description of this output parameter."""
        return self._description

    @output_description.setter
    def output_description(self, value: str) -> None:
        """Set the description of this output parameter."""
        self._description = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Port name must be non-empty
        if not self._port_name or not self._port_name.strip():
            errors.append("Output port name cannot be empty")

        # Port name should be a valid Python identifier
        if self._port_name and not self._port_name.isidentifier():
            errors.append(
                f"Output port name '{self._port_name}' is not a valid identifier. "
                "Use only letters, numbers, and underscores, starting with a letter."
            )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the subgraph output node.

        During execution, this node captures its input value and makes it
        available for the subgraph execution context to return.

        Args:
            inputs: Dictionary containing the value to output.

        Returns:
            Dictionary containing the captured output value with special key.
        """
        # Get the value to output
        value = inputs.get("value")

        # Return the value with a special key that the execution context recognizes
        return {
            "_subgraph_output": value,
            "_port_name": self._port_name,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get subgraph output-specific properties for serialization.

        Returns:
            Dictionary of serializable properties.
        """
        return {
            "port_name": self._port_name,
            "port_type": self._port_type_setting.name,
            "description": self._description,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load subgraph output-specific properties from serialized data.

        Args:
            properties: Dictionary of serialized properties.
        """
        self._port_name = properties.get("port_name", "output")
        self._description = properties.get("description", "")

        # Parse port type
        port_type_str = properties.get("port_type", "ANY")
        try:
            self._port_type_setting = PortType[port_type_str]
        except KeyError:
            self._port_type_setting = PortType.ANY

        # Update input port type
        value_port = self.get_input_port("value")
        if value_port:
            value_port._port_type = self._port_type_setting

    def __repr__(self) -> str:
        """Get a detailed string representation of the subgraph output node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"port_name='{self._port_name}', "
            f"type={self._port_type_setting.name}, "
            f"state={self._execution_state.name})"
        )
