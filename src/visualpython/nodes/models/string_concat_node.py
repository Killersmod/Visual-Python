"""
String concatenation node model for combining strings in VisualPython.

This module defines the StringConcatNode class, which concatenates multiple
strings together with an optional separator.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class StringConcatNode(BaseNode):
    """
    A node that concatenates multiple strings together.

    The StringConcatNode provides a visual way to combine strings with an
    optional separator. It supports multiple input strings and converts
    non-string values to strings automatically.

    Attributes:
        separator: String to insert between concatenated values.

    Example:
        >>> node = StringConcatNode(separator=", ")
        >>> result = node.execute({"str1": "Hello", "str2": "World"})
        >>> result["result"]  # "Hello, World"
    """

    # Class-level metadata
    node_type: str = "string_concat"
    """Unique identifier for string concat nodes."""

    node_category: str = "String Operations"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to indicate string operation."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        separator: str = "",
    ) -> None:
        """
        Initialize a new StringConcatNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'String Concat'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            separator: String to insert between concatenated values (default: empty).
        """
        self._separator: str = separator
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the string concat node.

        The string concat node has:
        - exec_in: Execution flow input (optional)
        - str1: First string to concatenate
        - str2: Second string to concatenate
        - str3: Third string to concatenate (optional)
        - str4: Fourth string to concatenate (optional)
        - separator: Separator to use between strings
        - exec_out: Execution flow output
        - result: The concatenated string
        - length: Length of the result string
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # String inputs
        self.add_input_port(InputPort(
            name="str1",
            port_type=PortType.STRING,
            description="First string to concatenate",
            required=False,
            default_value="",
        ))

        self.add_input_port(InputPort(
            name="str2",
            port_type=PortType.STRING,
            description="Second string to concatenate",
            required=False,
            default_value="",
        ))

        self.add_input_port(InputPort(
            name="str3",
            port_type=PortType.STRING,
            description="Third string to concatenate (optional)",
            required=False,
            default_value="",
        ))

        self.add_input_port(InputPort(
            name="str4",
            port_type=PortType.STRING,
            description="Fourth string to concatenate (optional)",
            required=False,
            default_value="",
        ))

        # Separator input
        self.add_input_port(InputPort(
            name="separator",
            port_type=PortType.STRING,
            description="Separator to insert between strings",
            required=False,
            default_value=self._separator,
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
            port_type=PortType.STRING,
            description="The concatenated string",
        ))

        # Length output
        self.add_output_port(OutputPort(
            name="length",
            port_type=PortType.INTEGER,
            description="Length of the result string",
        ))

    @property
    def separator(self) -> str:
        """Get the separator string."""
        return self._separator

    @separator.setter
    def separator(self, value: str) -> None:
        """Set the separator string."""
        self._separator = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate that separator is a string
        if not isinstance(self._separator, str):
            errors.append(f"Separator must be a string, got {type(self._separator).__name__}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the string concatenation operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'str1', 'str2', 'str3', 'str4', and 'separator'.

        Returns:
            Dictionary with 'result' and 'length'.
        """
        # Get separator from input or use default
        separator = inputs.get("separator", self._separator)
        if separator is None:
            separator = self._separator

        # Collect non-empty string values
        strings: List[str] = []
        for key in ["str1", "str2", "str3", "str4"]:
            value = inputs.get(key, "")
            if value is None:
                value = ""
            # Convert to string if not already
            if not isinstance(value, str):
                value = str(value)
            # Only add non-empty strings
            if value:
                strings.append(value)

        # Concatenate with separator
        result = separator.join(strings)

        return {
            "result": result,
            "length": len(result),
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get string concat node specific properties for serialization.

        Returns:
            Dictionary containing the separator value.
        """
        return {
            "separator": self._separator,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load string concat node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._separator = properties.get("separator", "")

    def __repr__(self) -> str:
        """Get a detailed string representation of the string concat node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"separator='{self._separator}', "
            f"state={self._execution_state.name})"
        )
