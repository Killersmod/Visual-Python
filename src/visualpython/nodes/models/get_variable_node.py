"""
Get variable node model for retrieving values from global variables.

This module defines the GetVariableNode class, which retrieves a value from
a named global variable in the GlobalVariableStore.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.variables import GlobalVariableStore


class GetVariableNode(BaseNode):
    """
    A node that retrieves a value from a named global variable.

    The GetVariableNode reads values from the GlobalVariableStore, enabling
    nodes to access shared state that was previously set by other nodes
    (e.g., using a SetVariableNode or CodeNode).

    The variable name can be:
    - Configured directly on the node (via the variable_name property)
    - Provided dynamically through the variable_name input port

    If the variable doesn't exist, a configurable default value is returned.

    Attributes:
        variable_name: The name of the global variable to retrieve.
        default_value: The value to return if the variable doesn't exist.

    Example:
        >>> node = GetVariableNode(variable_name="counter")
        >>> # Assuming 'counter' was set to 42 in GlobalVariableStore
        >>> result = node.execute({})
        >>> result['value']
        42
    """

    # Class-level metadata
    node_type: str = "get_variable"
    """Unique identifier for get variable nodes."""

    display_name: str = "Get Global Variable"
    """Display name shown in the UI and node palette."""

    node_category: str = "Variables"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to distinguish global variable nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        variable_name: str = "",
        default_value: Any = None,
    ) -> None:
        """
        Initialize a new GetVariableNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Get Variable'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            variable_name: The name of the global variable to retrieve.
            default_value: The value to return if the variable doesn't exist.
        """
        self._variable_name: str = variable_name
        self._default_value: Any = default_value
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the get variable node.

        The get variable node has:
        - An execution flow input port (for controlling execution order)
        - A variable_name input port (optional, for dynamic variable names)
        - An execution flow output port (for chaining execution)
        - A value output port for the retrieved variable value
        - An exists output port indicating whether the variable exists
        """
        # Execution flow ports
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Variable name input (optional - allows dynamic variable names)
        self.add_input_port(InputPort(
            name="variable_name",
            port_type=PortType.STRING,
            description="Name of the variable to retrieve (overrides configured name)",
            required=False,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="value",
            port_type=PortType.ANY,
            description="The value of the retrieved variable",
        ))
        self.add_output_port(OutputPort(
            name="exists",
            port_type=PortType.BOOLEAN,
            description="Whether the variable exists in the store",
        ))

    @property
    def variable_name(self) -> str:
        """Get the configured variable name."""
        return self._variable_name

    @variable_name.setter
    def variable_name(self, value: str) -> None:
        """
        Set the variable name to retrieve.

        Args:
            value: The name of the global variable.
        """
        self._variable_name = value

    @property
    def default_value(self) -> Any:
        """Get the default value."""
        return self._default_value

    @default_value.setter
    def default_value(self, value: Any) -> None:
        """
        Set the default value to return if the variable doesn't exist.

        Args:
            value: The default value.
        """
        self._default_value = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Variable name is required (either configured or via input port)
        # If no variable name is configured, it must be provided via input
        if not self._variable_name:
            # Check if variable_name input port is connected
            var_name_port = self.get_input_port("variable_name")
            if var_name_port and not var_name_port.is_connected():
                errors.append(
                    "Variable name must be configured or provided via input port"
                )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve the value of the global variable.

        The variable name is determined by:
        1. The 'variable_name' input port value (if provided)
        2. The configured variable_name property

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'value': The variable value (or default_value if not found)
                - 'exists': Boolean indicating if the variable exists

        Raises:
            ValueError: If no variable name is specified.
        """
        # Determine the variable name to use
        var_name = inputs.get("variable_name", self._variable_name)

        if not var_name:
            raise ValueError("No variable name specified")

        # Get the global variable store
        global_store = GlobalVariableStore.get_instance()

        # Check if variable exists and retrieve value
        exists = global_store.exists(var_name)
        value = global_store.get(var_name, self._default_value)

        return {
            "value": value,
            "exists": exists,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get get variable node specific properties for serialization.

        Returns:
            Dictionary containing the variable name and default value.
        """
        return {
            "variable_name": self._variable_name,
            "default_value": self._default_value,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load get variable node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._variable_name = properties.get("variable_name", "")
        self._default_value = properties.get("default_value", None)

    def __repr__(self) -> str:
        """Get a detailed string representation of the get variable node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"variable_name='{self._variable_name}', "
            f"state={self._execution_state.name})"
        )
