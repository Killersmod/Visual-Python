"""
Divide node model for division operations in VisualPython.

This module defines the DivideNode class, which performs division of two numeric values.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class DivideNode(BaseNode):
    """
    A node that divides one numeric value by another.

    The DivideNode provides a visual way to perform division without writing code.
    It accepts two numeric inputs and outputs the quotient (a / b).

    The inputs can be:
    - Provided dynamically through the input ports
    - Configured with default values on the node

    Features:
    - Division by zero protection (raises ZeroDivisionError)
    - Optional integer division mode

    Attributes:
        default_a: Default value for the dividend.
        default_b: Default value for the divisor.
        integer_division: Whether to perform integer (floor) division.

    Example:
        >>> node = DivideNode()
        >>> result = node.execute({"a": 10, "b": 3})
        >>> result["result"]  # 3.333...
    """

    # Class-level metadata
    node_type: str = "divide"
    """Unique identifier for divide nodes."""

    node_category: str = "Math Operations"
    """Category for organizing in the UI."""

    node_color: str = "#FF9800"
    """Orange color to indicate math operation."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        default_a: Union[int, float] = 0,
        default_b: Union[int, float] = 1,
        integer_division: bool = False,
    ) -> None:
        """
        Initialize a new DivideNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Divide'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            default_a: Default value for the dividend.
            default_b: Default value for the divisor.
            integer_division: Whether to perform integer (floor) division.
        """
        self._default_a: Union[int, float] = default_a
        self._default_b: Union[int, float] = default_b
        self._integer_division: bool = integer_division
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the divide node.

        The divide node has:
        - exec_in: Execution flow input (optional)
        - a: Dividend (number to be divided)
        - b: Divisor (number to divide by)
        - exec_out: Execution flow output
        - result: The quotient of a / b
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # Dividend
        self.add_input_port(InputPort(
            name="a",
            port_type=PortType.FLOAT,
            description="Dividend (number to be divided)",
            required=False,
            default_value=self._default_a,
        ))

        # Divisor
        self.add_input_port(InputPort(
            name="b",
            port_type=PortType.FLOAT,
            description="Divisor (number to divide by)",
            required=False,
            default_value=self._default_b,
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Result output
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.FLOAT,
            description="The quotient (a / b)",
        ))

    @property
    def default_a(self) -> Union[int, float]:
        """Get the default value for operand a."""
        return self._default_a

    @default_a.setter
    def default_a(self, value: Union[int, float]) -> None:
        """Set the default value for operand a."""
        self._default_a = value

    @property
    def default_b(self) -> Union[int, float]:
        """Get the default value for operand b."""
        return self._default_b

    @default_b.setter
    def default_b(self, value: Union[int, float]) -> None:
        """Set the default value for operand b."""
        self._default_b = value

    @property
    def integer_division(self) -> bool:
        """Get whether integer division is enabled."""
        return self._integer_division

    @integer_division.setter
    def integer_division(self, value: bool) -> None:
        """Set whether to use integer division."""
        self._integer_division = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate that defaults are numeric
        if not isinstance(self._default_a, (int, float)):
            errors.append(f"Default value 'a' must be numeric, got {type(self._default_a).__name__}")
        if not isinstance(self._default_b, (int, float)):
            errors.append(f"Default value 'b' must be numeric, got {type(self._default_b).__name__}")

        # Warn about division by zero in defaults
        if self._default_b == 0:
            errors.append("Default divisor 'b' is zero, which will cause division by zero")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the division operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'a' and 'b' for the operands.

        Returns:
            Dictionary with 'result' containing the quotient.

        Raises:
            TypeError: If inputs are not numeric.
            ZeroDivisionError: If divisor is zero.
        """
        # Get operands from inputs or use defaults
        a = inputs.get("a", self._default_a)
        b = inputs.get("b", self._default_b)

        # Convert to numeric if necessary
        if a is None:
            a = self._default_a
        if b is None:
            b = self._default_b

        # Validate types
        if not isinstance(a, (int, float)):
            try:
                a = float(a)
            except (ValueError, TypeError):
                raise TypeError(f"Operand 'a' must be numeric, got {type(a).__name__}")

        if not isinstance(b, (int, float)):
            try:
                b = float(b)
            except (ValueError, TypeError):
                raise TypeError(f"Operand 'b' must be numeric, got {type(b).__name__}")

        # Check for division by zero
        if b == 0:
            raise ZeroDivisionError("Cannot divide by zero")

        # Perform division
        if self._integer_division:
            result = a // b
        else:
            result = a / b

        return {
            "result": result,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get divide node specific properties for serialization.

        Returns:
            Dictionary containing the default values and settings.
        """
        return {
            "default_a": self._default_a,
            "default_b": self._default_b,
            "integer_division": self._integer_division,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load divide node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._default_a = properties.get("default_a", 0)
        self._default_b = properties.get("default_b", 1)
        self._integer_division = properties.get("integer_division", False)

    def __repr__(self) -> str:
        """Get a detailed string representation of the divide node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"default_a={self._default_a}, "
            f"default_b={self._default_b}, "
            f"integer_division={self._integer_division}, "
            f"state={self._execution_state.name})"
        )
