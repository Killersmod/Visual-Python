"""
String split node model for splitting strings in VisualPython.

This module defines the StringSplitNode class, which splits a string into
a list of substrings based on a delimiter.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class StringSplitNode(BaseNode):
    """
    A node that splits a string into a list of substrings.

    The StringSplitNode provides a visual way to split strings using a
    delimiter. It supports limiting the number of splits and provides
    useful output information.

    Attributes:
        default_delimiter: Default delimiter to split on.
        max_splits: Maximum number of splits (-1 for unlimited).

    Example:
        >>> node = StringSplitNode(default_delimiter=",")
        >>> result = node.execute({"text": "a,b,c,d"})
        >>> result["parts"]  # ["a", "b", "c", "d"]
        >>> result["count"]  # 4
    """

    # Class-level metadata
    node_type: str = "string_split"
    """Unique identifier for string split nodes."""

    node_category: str = "String Operations"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to indicate string operation."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        default_delimiter: str = ",",
        max_splits: int = -1,
    ) -> None:
        """
        Initialize a new StringSplitNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'String Split'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            default_delimiter: Default delimiter to split on (default: comma).
            max_splits: Maximum number of splits, -1 for unlimited (default: -1).
        """
        self._default_delimiter: str = default_delimiter
        self._max_splits: int = max_splits
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the string split node.

        The string split node has:
        - exec_in: Execution flow input (optional)
        - text: The string to split
        - delimiter: The delimiter to split on
        - exec_out: Execution flow output
        - parts: List of split substrings
        - count: Number of parts
        - first: First element of the split
        - last: Last element of the split
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # Text input
        self.add_input_port(InputPort(
            name="text",
            port_type=PortType.STRING,
            description="The string to split",
            required=False,
            default_value="",
        ))

        # Delimiter input
        self.add_input_port(InputPort(
            name="delimiter",
            port_type=PortType.STRING,
            description="The delimiter to split on",
            required=False,
            default_value=self._default_delimiter,
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Parts list output
        self.add_output_port(OutputPort(
            name="parts",
            port_type=PortType.LIST,
            description="List of split substrings",
        ))

        # Count output
        self.add_output_port(OutputPort(
            name="count",
            port_type=PortType.INTEGER,
            description="Number of parts",
        ))

        # First element output
        self.add_output_port(OutputPort(
            name="first",
            port_type=PortType.STRING,
            description="First element of the split",
        ))

        # Last element output
        self.add_output_port(OutputPort(
            name="last",
            port_type=PortType.STRING,
            description="Last element of the split",
        ))

    @property
    def default_delimiter(self) -> str:
        """Get the default delimiter."""
        return self._default_delimiter

    @default_delimiter.setter
    def default_delimiter(self, value: str) -> None:
        """Set the default delimiter."""
        self._default_delimiter = value

    @property
    def max_splits(self) -> int:
        """Get the maximum number of splits."""
        return self._max_splits

    @max_splits.setter
    def max_splits(self, value: int) -> None:
        """Set the maximum number of splits."""
        self._max_splits = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate that default delimiter is a string
        if not isinstance(self._default_delimiter, str):
            errors.append(f"Default delimiter must be a string, got {type(self._default_delimiter).__name__}")

        # Validate max_splits is an integer
        if not isinstance(self._max_splits, int):
            errors.append(f"Max splits must be an integer, got {type(self._max_splits).__name__}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the string split operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'text' and 'delimiter'.

        Returns:
            Dictionary with 'parts', 'count', 'first', and 'last'.
        """
        # Get inputs with defaults
        text = inputs.get("text", "")
        delimiter = inputs.get("delimiter", self._default_delimiter)

        # Handle None values
        if text is None:
            text = ""
        if delimiter is None:
            delimiter = self._default_delimiter

        # Ensure text is string
        if not isinstance(text, str):
            text = str(text)

        # Perform split
        if delimiter == "":
            # Split into individual characters if delimiter is empty
            parts = list(text)
        elif self._max_splits > 0:
            parts = text.split(delimiter, self._max_splits)
        else:
            parts = text.split(delimiter)

        # Get first and last elements
        first = parts[0] if parts else ""
        last = parts[-1] if parts else ""

        return {
            "parts": parts,
            "count": len(parts),
            "first": first,
            "last": last,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get string split node specific properties for serialization.

        Returns:
            Dictionary containing the configuration values.
        """
        return {
            "default_delimiter": self._default_delimiter,
            "max_splits": self._max_splits,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load string split node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._default_delimiter = properties.get("default_delimiter", ",")
        self._max_splits = properties.get("max_splits", -1)

    def __repr__(self) -> str:
        """Get a detailed string representation of the string split node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"delimiter='{self._default_delimiter}', "
            f"state={self._execution_state.name})"
        )
