"""
Multiply node model for multiplication operations in VisualPython.

This module defines the MultiplyNode class, which performs multiplication of two numeric values.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class MultiplyNode(BaseNode):
    """
    A node that multiplies two numeric values together.

    The MultiplyNode provides a visual way to perform multiplication without writing code.
    It accepts two numeric inputs and outputs their product.

    The inputs can be:
    - Provided dynamically through the input ports
    - Configured with default values on the node

    Attributes:
        default_a: Default value for the first operand.
        default_b: Default value for the second operand.

    Example:
        >>> node = MultiplyNode()
        >>> result = node.execute({"a": 4, "b": 5})
        >>> result["result"]  # 20
    """

    # Class-level metadata
    node_type: str = "multiply"
    """Unique identifier for multiply nodes."""

    node_category: str = "Math Operations"
    """Category for organizing in the UI."""

    node_color: str = "#FF9800"
    """Orange color to indicate math operation."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        default_a: Union[int, float] = 1,
        default_b: Union[int, float] = 1,
    ) -> None:
        """
        Initialize a new MultiplyNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Multiply'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            default_a: Default value for the first operand.
            default_b: Default value for the second operand.
        """
        self._default_a: Union[int, float] = default_a
        self._default_b: Union[int, float] = default_b
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the multiply node.

        The multiply node has:
        - exec_in: Execution flow input (optional)
        - a: First numeric operand
        - b: Second numeric operand
        - exec_out: Execution flow output
        - result: The product of a and b
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # First operand
        self.add_input_port(InputPort(
            name="a",
            port_type=PortType.FLOAT,
            description="First number to multiply",
            required=False,
            default_value=self._default_a,
        ))

        # Second operand
        self.add_input_port(InputPort(
            name="b",
            port_type=PortType.FLOAT,
            description="Second number to multiply",
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
            description="The product of a and b",
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

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the multiplication operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'a' and 'b' for the operands.

        Returns:
            Dictionary with 'result' containing the product.

        Raises:
            TypeError: If inputs are not numeric.
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

        # Perform multiplication
        result = a * b

        return {
            "result": result,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get multiply node specific properties for serialization.

        Returns:
            Dictionary containing the default values.
        """
        return {
            "default_a": self._default_a,
            "default_b": self._default_b,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load multiply node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._default_a = properties.get("default_a", 1)
        self._default_b = properties.get("default_b", 1)

    def __repr__(self) -> str:
        """Get a detailed string representation of the multiply node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"default_a={self._default_a}, "
            f"default_b={self._default_b}, "
            f"state={self._execution_state.name})"
        )
