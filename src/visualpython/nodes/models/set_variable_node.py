"""
Set variable node model for storing values in global variables.

This module defines the SetVariableNode class, which sets a value to
a named global variable in the GlobalVariableStore.

Type Validation:
    The SetVariableNode supports optional type validation. When a variable
    has a type annotation defined in the VariableTypeRegistry, the node
    can validate values before storing them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.variables import GlobalVariableStore
from visualpython.variables.type_registry import (
    TypeValidationError,
    TypeValidationSeverity,
    VariableTypeRegistry,
)


class SetVariableNode(BaseNode):
    """
    A node that sets a value to a named global variable.

    The SetVariableNode writes values to the GlobalVariableStore, enabling
    nodes to store shared state that can be accessed by other nodes
    (e.g., using a GetVariableNode or CodeNode).

    The variable name can be:
    - Configured directly on the node (via the variable_name property)
    - Provided dynamically through the variable_name input port

    The value to set can be:
    - Provided through the value input port
    - If no value is provided, the variable will be set to None

    Attributes:
        variable_name: The name of the global variable to set.

    Example:
        >>> node = SetVariableNode(variable_name="counter")
        >>> result = node.execute({"value": 42})
        >>> result['success']
        True
        >>> # Now 'counter' is set to 42 in GlobalVariableStore
    """

    # Class-level metadata
    node_type: str = "set_variable"
    """Unique identifier for set variable nodes."""

    display_name: str = "Set Global Variable"
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
        validate_type: bool = True,
        expected_type: Optional[PortType] = None,
    ) -> None:
        """
        Initialize a new SetVariableNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Set Variable'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            variable_name: The name of the global variable to set.
            validate_type: Whether to validate values against type annotations.
            expected_type: Optional expected type for the variable. If provided,
                          a type annotation will be created.
        """
        self._variable_name: str = variable_name
        self._validate_type: bool = validate_type
        self._expected_type: Optional[PortType] = expected_type
        self._last_validation_error: Optional[TypeValidationError] = None
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the set variable node.

        The set variable node has:
        - An execution flow input port (for controlling execution order)
        - A variable_name input port (optional, for dynamic variable names)
        - A value input port (for the value to store)
        - An execution flow output port (for chaining execution)
        - A success output port indicating whether the operation succeeded
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
            description="Name of the variable to set (overrides configured name)",
            required=False,
        ))

        # Value input
        self.add_input_port(InputPort(
            name="value",
            port_type=PortType.ANY,
            description="The value to store in the variable",
            required=False,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="success",
            port_type=PortType.BOOLEAN,
            description="Whether the variable was successfully set",
        ))

    @property
    def variable_name(self) -> str:
        """Get the configured variable name."""
        return self._variable_name

    @variable_name.setter
    def variable_name(self, value: str) -> None:
        """
        Set the variable name to store to.

        Args:
            value: The name of the global variable.
        """
        self._variable_name = value

    @property
    def validate_type(self) -> bool:
        """Get whether type validation is enabled for this node."""
        return self._validate_type

    @validate_type.setter
    def validate_type(self, value: bool) -> None:
        """Set whether type validation is enabled for this node."""
        self._validate_type = value

    @property
    def expected_type(self) -> Optional[PortType]:
        """Get the expected type for this variable."""
        return self._expected_type

    @expected_type.setter
    def expected_type(self, value: Optional[PortType]) -> None:
        """
        Set the expected type for this variable.

        Setting this will create or update a type annotation in the
        VariableTypeRegistry.
        """
        self._expected_type = value
        if value is not None and self._variable_name:
            registry = VariableTypeRegistry.get_instance()
            registry.set_annotation(self._variable_name, value)

    @property
    def last_validation_error(self) -> Optional[TypeValidationError]:
        """Get the last type validation error, if any."""
        return self._last_validation_error

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
        Set the value of the global variable.

        The variable name is determined by:
        1. The 'variable_name' input port value (if provided)
        2. The configured variable_name property

        If type validation is enabled and the variable has a type annotation,
        the value will be validated before being stored.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'success': Boolean indicating if the variable was set
                - 'type_error': Optional TypeValidationError if validation failed

        Raises:
            ValueError: If no variable name is specified.
            ValueError: If type validation fails in strict mode.
        """
        # Clear previous validation error
        self._last_validation_error = None

        # Determine the variable name to use
        var_name = inputs.get("variable_name", self._variable_name)

        if not var_name:
            raise ValueError("No variable name specified")

        # Get the value to set (defaults to None if not provided)
        value = inputs.get("value", None)

        # Get the global variable store
        global_store = GlobalVariableStore.get_instance()

        # If we have an expected_type and the registry doesn't have an annotation,
        # create one now
        if self._expected_type is not None:
            registry = VariableTypeRegistry.get_instance()
            if not registry.has_annotation(var_name):
                registry.set_annotation(var_name, self._expected_type)

        # Validate type if enabled
        type_error: Optional[TypeValidationError] = None
        if self._validate_type:
            type_error = global_store.validate_type(var_name, value)
            self._last_validation_error = type_error

            if type_error is not None:
                # Check if we should raise or just log
                if type_error.severity == TypeValidationSeverity.ERROR:
                    if global_store.strict_validation:
                        raise ValueError(type_error.message)

        # Set the value (pass validate=False since we already validated)
        global_store.set(var_name, value, validate=False)

        result: Dict[str, Any] = {
            "success": type_error is None,
        }
        if type_error is not None:
            result["type_error"] = type_error

        return result

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get set variable node specific properties for serialization.

        Returns:
            Dictionary containing the variable name and type settings.
        """
        result: Dict[str, Any] = {
            "variable_name": self._variable_name,
            "validate_type": self._validate_type,
        }
        if self._expected_type is not None:
            result["expected_type"] = self._expected_type.name
        return result

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load set variable node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._variable_name = properties.get("variable_name", "")
        self._validate_type = properties.get("validate_type", True)
        expected_type_name = properties.get("expected_type")
        if expected_type_name:
            self._expected_type = PortType[expected_type_name]
        else:
            self._expected_type = None

    def __repr__(self) -> str:
        """Get a detailed string representation of the set variable node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"variable_name='{self._variable_name}', "
            f"state={self._execution_state.name})"
        )
