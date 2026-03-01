"""
Power node model for exponentiation operations in VisualPython.

This module defines the PowerNode class, which performs exponentiation of two numeric values.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class PowerNode(BaseNode):
    """
    A node that raises a number to a power (exponentiation).

    The PowerNode provides a visual way to perform exponentiation without writing code.
    It accepts two numeric inputs and outputs base raised to the power of exponent.

    The inputs can be:
    - Provided dynamically through the input ports
    - Configured with default values on the node

    Features:
    - Works with both integers and floats
    - Handles negative exponents
    - Handles fractional exponents (roots)

    Attributes:
        default_base: Default value for the base.
        default_exponent: Default value for the exponent.

    Example:
        >>> node = PowerNode()
        >>> result = node.execute({"base": 2, "exponent": 3})
        >>> result["result"]  # 8
    """

    # Class-level metadata
    node_type: str = "power"
    """Unique identifier for power nodes."""

    node_category: str = "Math Operations"
    """Category for organizing in the UI."""

    node_color: str = "#FF9800"
    """Orange color to indicate math operation."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        default_base: Union[int, float] = 1,
        default_exponent: Union[int, float] = 1,
    ) -> None:
        """
        Initialize a new PowerNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Power'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            default_base: Default value for the base.
            default_exponent: Default value for the exponent.
        """
        self._default_base: Union[int, float] = default_base
        self._default_exponent: Union[int, float] = default_exponent
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the power node.

        The power node has:
        - exec_in: Execution flow input (optional)
        - base: The base number
        - exponent: The exponent (power)
        - exec_out: Execution flow output
        - result: base raised to the power of exponent
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # Base
        self.add_input_port(InputPort(
            name="base",
            port_type=PortType.FLOAT,
            description="The base number",
            required=False,
            default_value=self._default_base,
        ))

        # Exponent
        self.add_input_port(InputPort(
            name="exponent",
            port_type=PortType.FLOAT,
            description="The exponent (power)",
            required=False,
            default_value=self._default_exponent,
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
            description="base raised to the power of exponent",
        ))

    @property
    def default_base(self) -> Union[int, float]:
        """Get the default value for base."""
        return self._default_base

    @default_base.setter
    def default_base(self, value: Union[int, float]) -> None:
        """Set the default value for base."""
        self._default_base = value

    @property
    def default_exponent(self) -> Union[int, float]:
        """Get the default value for exponent."""
        return self._default_exponent

    @default_exponent.setter
    def default_exponent(self, value: Union[int, float]) -> None:
        """Set the default value for exponent."""
        self._default_exponent = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate that defaults are numeric
        if not isinstance(self._default_base, (int, float)):
            errors.append(f"Default value 'base' must be numeric, got {type(self._default_base).__name__}")
        if not isinstance(self._default_exponent, (int, float)):
            errors.append(f"Default value 'exponent' must be numeric, got {type(self._default_exponent).__name__}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the exponentiation operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'base' and 'exponent' for the operands.

        Returns:
            Dictionary with 'result' containing base ** exponent.

        Raises:
            TypeError: If inputs are not numeric.
            ValueError: If the operation results in an undefined value (e.g., 0**-1).
        """
        # Get operands from inputs or use defaults
        base = inputs.get("base", self._default_base)
        exponent = inputs.get("exponent", self._default_exponent)

        # Convert to numeric if necessary
        if base is None:
            base = self._default_base
        if exponent is None:
            exponent = self._default_exponent

        # Validate types
        if not isinstance(base, (int, float)):
            try:
                base = float(base)
            except (ValueError, TypeError):
                raise TypeError(f"Operand 'base' must be numeric, got {type(base).__name__}")

        if not isinstance(exponent, (int, float)):
            try:
                exponent = float(exponent)
            except (ValueError, TypeError):
                raise TypeError(f"Operand 'exponent' must be numeric, got {type(exponent).__name__}")

        # Handle special cases
        if base == 0 and exponent < 0:
            raise ValueError("Cannot raise zero to a negative power")

        if base < 0 and not float(exponent).is_integer():
            raise ValueError("Cannot raise negative number to a fractional power (results in complex number)")

        # Perform exponentiation
        result = base ** exponent

        return {
            "result": result,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get power node specific properties for serialization.

        Returns:
            Dictionary containing the default values.
        """
        return {
            "default_base": self._default_base,
            "default_exponent": self._default_exponent,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load power node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._default_base = properties.get("default_base", 1)
        self._default_exponent = properties.get("default_exponent", 1)

    def __repr__(self) -> str:
        """Get a detailed string representation of the power node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"default_base={self._default_base}, "
            f"default_exponent={self._default_exponent}, "
            f"state={self._execution_state.name})"
        )
