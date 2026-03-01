"""
Case variable nodes for VisualPython.

This module defines nodes for getting and setting case variables during
graph execution. Case variables provide per-execution shared state that
is accessible from all nodes without explicit wiring.

The case system provides a higher-level abstraction over the global variable
store, with automatic clearing between executions and support for both
method-based and attribute-based access in code nodes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.execution.engine import get_current_case
from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class SetCaseVariableNode(BaseNode):
    """
    A node that sets a case variable value.

    The SetCaseVariableNode allows users to set a variable in the per-execution
    Case context. This variable will be accessible from all other nodes during
    the same execution via the Case object (either through GetCaseVariableNode
    or directly in CodeNode as `case.variable_name` or `case.get("variable_name")`).

    The node takes:
    - variable_name: The name of the case variable to set (must be a valid Python identifier)
    - value: The value to store in the case variable (any type)

    After execution, the value is stored in the Case and can be retrieved by
    other nodes during the same graph execution.

    Attributes:
        default_variable_name: Default name for the variable when not connected.

    Example:
        >>> node = SetCaseVariableNode()
        >>> # In a graph execution context with case available:
        >>> result = node.execute({"variable_name": "counter", "value": 42})
        >>> # The case variable "counter" is now set to 42

    Note:
        Case variables are cleared at the start of each new execution.
        For persistent storage across executions, use the GlobalVariableStore instead.
    """

    # Class-level metadata
    node_type: str = "set_case_variable"
    """Unique identifier for set case variable nodes."""

    display_name: str = "Set Variable"
    """Display name shown in the UI and node palette."""

    node_category: str = "Variables"
    """Category for organizing in the UI."""

    node_color: str = "#9C27B0"
    """Purple color to indicate variable operations."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        default_variable_name: str = "",
    ) -> None:
        """
        Initialize a new SetCaseVariableNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Set Case Variable'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            default_variable_name: Default name for the variable when not connected.
        """
        self._default_variable_name: str = default_variable_name
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the set case variable node.

        The node has:
        - exec_in: Execution flow input
        - variable_name: The name of the variable to set (STRING)
        - value: The value to store (ANY type)
        - exec_out: Execution flow output
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # Variable name input
        self.add_input_port(InputPort(
            name="variable_name",
            port_type=PortType.STRING,
            description="Name of the variable to set (must be a valid Python identifier)",
            required=True,
            default_value=self._default_variable_name,
        ))

        # Value input
        self.add_input_port(InputPort(
            name="value",
            port_type=PortType.ANY,
            description="Value to store in the variable",
            required=True,
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

    @property
    def default_variable_name(self) -> str:
        """Get the default variable name."""
        return self._default_variable_name

    @default_variable_name.setter
    def default_variable_name(self, value: str) -> None:
        """Set the default variable name."""
        self._default_variable_name = value
        # Update the port's default value as well
        port = self.get_input_port("variable_name")
        if port:
            port.default_value = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Checks that:
        - If a default variable name is set, it must be a valid Python identifier

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate default variable name if set
        if self._default_variable_name:
            if not self._default_variable_name.isidentifier():
                errors.append(
                    f"Default variable name '{self._default_variable_name}' is not a valid "
                    "Python identifier (must start with letter or underscore, contain only "
                    "letters, numbers, and underscores)"
                )
            # Check for Python keywords
            import keyword
            if keyword.iskeyword(self._default_variable_name):
                errors.append(
                    f"Default variable name '{self._default_variable_name}' is a Python "
                    "keyword and cannot be used as a variable name"
                )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the set case variable operation.

        Sets the specified variable in the current execution's Case context.

        Args:
            inputs: Dictionary containing:
                - variable_name: The name of the variable to set
                - value: The value to store

        Returns:
            Empty dictionary (no data outputs, only flow output).

        Raises:
            ValueError: If no case context is available (not in execution).
            InvalidVariableNameError: If the variable name is not a valid Python identifier.
        """
        # Get the variable name
        variable_name = inputs.get("variable_name", self._default_variable_name)
        if not variable_name:
            raise ValueError("Variable name is required")

        # Get the value to set
        value = inputs.get("value")

        # Get the current case from execution context
        case = get_current_case()
        if case is None:
            raise ValueError(
                "No case context available. SetCaseVariableNode can only be used "
                "during graph execution."
            )

        # Set the variable in the case
        # The Case.set() method will validate the variable name and raise
        # InvalidVariableNameError if it's not valid
        case.set(variable_name, value)

        return {}

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get set case variable node specific properties for serialization.

        Returns:
            Dictionary containing the default variable name.
        """
        return {
            "default_variable_name": self._default_variable_name,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load set case variable node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._default_variable_name = properties.get("default_variable_name", "")

    def __repr__(self) -> str:
        """Get a detailed string representation of the set case variable node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"default_variable_name='{self._default_variable_name}', "
            f"state={self._execution_state.name})"
        )


class GetCaseVariableNode(BaseNode):
    """
    A node that retrieves a case variable value.

    The GetCaseVariableNode allows users to get a variable from the per-execution
    Case context. This variable must have been previously set by SetCaseVariableNode
    or directly in a CodeNode (e.g., `case.variable_name = value`).

    The node takes:
    - variable_name: The name of the case variable to retrieve (STRING)

    The node outputs:
    - value: The retrieved variable value (ANY type)

    If the variable does not exist, the node returns the specified default value
    (which defaults to None).

    Attributes:
        default_variable_name: Default name for the variable when not connected.
        default_value: Default value to return if the variable doesn't exist.

    Example:
        >>> node = GetCaseVariableNode()
        >>> # In a graph execution context with case available:
        >>> # Assuming case.set("counter", 42) was called earlier
        >>> result = node.execute({"variable_name": "counter"})
        >>> result["value"]  # 42

    Note:
        Case variables are cleared at the start of each new execution.
        For persistent storage across executions, use the GlobalVariableStore instead.
    """

    # Class-level metadata
    node_type: str = "get_case_variable"
    """Unique identifier for get case variable nodes."""

    display_name: str = "Get Variable"
    """Display name shown in the UI and node palette."""

    node_category: str = "Variables"
    """Category for organizing in the UI."""

    node_color: str = "#9C27B0"
    """Purple color to indicate variable operations."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        default_variable_name: str = "",
        default_value: Any = None,
    ) -> None:
        """
        Initialize a new GetCaseVariableNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Get Case Variable'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            default_variable_name: Default name for the variable when not connected.
            default_value: Default value to return if the variable doesn't exist.
        """
        self._default_variable_name: str = default_variable_name
        self._default_value: Any = default_value
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the get case variable node.

        The node has:
        - exec_in: Execution flow input
        - variable_name: The name of the variable to retrieve (STRING)
        - exec_out: Execution flow output
        - value: The retrieved variable value (ANY type)
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # Variable name input
        self.add_input_port(InputPort(
            name="variable_name",
            port_type=PortType.STRING,
            description="Name of the variable to retrieve (must be a valid Python identifier)",
            required=True,
            default_value=self._default_variable_name,
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Value output
        self.add_output_port(OutputPort(
            name="value",
            port_type=PortType.ANY,
            description="The retrieved variable value",
        ))

    @property
    def default_variable_name(self) -> str:
        """Get the default variable name."""
        return self._default_variable_name

    @default_variable_name.setter
    def default_variable_name(self, value: str) -> None:
        """Set the default variable name."""
        self._default_variable_name = value
        # Update the port's default value as well
        port = self.get_input_port("variable_name")
        if port:
            port.default_value = value

    @property
    def default_value(self) -> Any:
        """Get the default value returned when variable doesn't exist."""
        return self._default_value

    @default_value.setter
    def default_value(self, value: Any) -> None:
        """Set the default value returned when variable doesn't exist."""
        self._default_value = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Checks that:
        - If a default variable name is set, it must be a valid Python identifier

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate default variable name if set
        if self._default_variable_name:
            if not self._default_variable_name.isidentifier():
                errors.append(
                    f"Default variable name '{self._default_variable_name}' is not a valid "
                    "Python identifier (must start with letter or underscore, contain only "
                    "letters, numbers, and underscores)"
                )
            # Check for Python keywords
            import keyword
            if keyword.iskeyword(self._default_variable_name):
                errors.append(
                    f"Default variable name '{self._default_variable_name}' is a Python "
                    "keyword and cannot be used as a variable name"
                )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the get case variable operation.

        Retrieves the specified variable from the current execution's Case context.

        Args:
            inputs: Dictionary containing:
                - variable_name: The name of the variable to retrieve

        Returns:
            Dictionary with 'value' containing the retrieved value (or default if not found).

        Raises:
            ValueError: If no case context is available (not in execution).
        """
        # Get the variable name
        variable_name = inputs.get("variable_name", self._default_variable_name)
        if not variable_name:
            raise ValueError("Variable name is required")

        # Get the current case from execution context
        case = get_current_case()
        if case is None:
            raise ValueError(
                "No case context available. GetCaseVariableNode can only be used "
                "during graph execution."
            )

        # Get the variable from the case
        # The Case.get() method returns the default value if the variable doesn't exist
        value = case.get(variable_name, self._default_value)

        return {
            "value": value,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get get case variable node specific properties for serialization.

        Returns:
            Dictionary containing the default variable name and default value.
        """
        return {
            "default_variable_name": self._default_variable_name,
            "default_value": self._default_value,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load get case variable node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._default_variable_name = properties.get("default_variable_name", "")
        self._default_value = properties.get("default_value", None)

    def __repr__(self) -> str:
        """Get a detailed string representation of the get case variable node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"default_variable_name='{self._default_variable_name}', "
            f"default_value={self._default_value!r}, "
            f"state={self._execution_state.name})"
        )
