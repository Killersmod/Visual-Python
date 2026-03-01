"""
JSON parse node model for parsing JSON strings into Python objects.

This module defines the JSONParseNode class, which parses JSON strings
and converts them to Python dictionaries, lists, or other JSON-compatible types.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class JSONParseNode(BaseNode):
    """
    A node that parses JSON strings into Python objects.

    The JSONParseNode takes a JSON-formatted string and converts it to
    its Python equivalent (dict, list, str, int, float, bool, or None).
    It provides error handling for malformed JSON.

    The JSON string can be:
    - Configured directly on the node (via the json_string property)
    - Provided dynamically through the json_string input port

    Attributes:
        json_string: The JSON string to parse.

    Example:
        >>> node = JSONParseNode()
        >>> result = node.execute({"json_string": '{"name": "John", "age": 30}'})
        >>> result['success']
        True
        >>> result['data']
        {'name': 'John', 'age': 30}
    """

    # Class-level metadata
    node_type: str = "json_parse"
    """Unique identifier for JSON parse nodes."""

    node_category: str = "Data Processing"
    """Category for organizing in the UI."""

    node_color: str = "#FF6B00"
    """Orange color for data processing operations."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        json_string: str = "",
    ) -> None:
        """
        Initialize a new JSONParseNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Json Parse'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            json_string: The JSON string to parse.
        """
        self._json_string: str = json_string
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the JSON parse node.

        The JSON parse node has:
        - An execution flow input port (for controlling execution order)
        - A json_string input port (for the JSON string to parse)
        - An execution flow output port (for chaining execution)
        - A data output port with the parsed Python object
        - A success output port indicating whether the parsing succeeded
        - An error_message output port with error details if failed
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

        # JSON string input
        self.add_input_port(InputPort(
            name="json_string",
            port_type=PortType.STRING,
            description="JSON string to parse",
            required=False,
            display_hint=self._json_string,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="data",
            port_type=PortType.ANY,
            description="Parsed Python object (dict, list, str, int, float, bool, or None)",
        ))
        self.add_output_port(OutputPort(
            name="success",
            port_type=PortType.BOOLEAN,
            description="Whether the JSON was successfully parsed",
        ))
        self.add_output_port(OutputPort(
            name="error_message",
            port_type=PortType.STRING,
            description="Error message if parsing failed",
        ))

    @property
    def json_string(self) -> str:
        """Get the configured JSON string."""
        return self._json_string

    @json_string.setter
    def json_string(self, value: str) -> None:
        """
        Set the JSON string to parse.

        Args:
            value: The JSON string.
        """
        self._json_string = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # JSON string is required (either configured or via input port)
        if not self._json_string:
            # Check if json_string input port is connected
            json_port = self.get_input_port("json_string")
            if json_port and not json_port.is_connected():
                errors.append(
                    "JSON string must be configured or provided via input port"
                )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse the JSON string into a Python object.

        The JSON string is determined by:
        1. The 'json_string' input port value (if provided)
        2. The configured json_string property

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'data': The parsed Python object (None if failed)
                - 'success': Boolean indicating if the JSON was parsed
                - 'error_message': Error message if failed (empty string if success)
        """
        # Determine the JSON string to use
        json_str = inputs.get("json_string", self._json_string)

        if json_str is None:
            json_str = ""

        try:
            data = json.loads(json_str)
            return {
                "data": data,
                "success": True,
                "error_message": "",
            }
        except json.JSONDecodeError as e:
            logger.error("JSON parse failed: %s", e, exc_info=True)
            return {
                "data": None,
                "success": False,
                "error_message": f"JSON parsing error: {e}",
            }
        except Exception as e:
            logger.error("JSON parse failed: %s", e, exc_info=True)
            return {
                "data": None,
                "success": False,
                "error_message": str(e),
            }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get JSON parse node specific properties for serialization.

        Returns:
            Dictionary containing the JSON string.
        """
        return {
            "json_string": self._json_string,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load JSON parse node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._json_string = properties.get("json_string", "")

    def __repr__(self) -> str:
        """Get a detailed string representation of the JSON parse node."""
        json_preview = self._json_string[:30] + "..." if len(self._json_string) > 30 else self._json_string
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"json_string='{json_preview}', "
            f"state={self._execution_state.name})"
        )
