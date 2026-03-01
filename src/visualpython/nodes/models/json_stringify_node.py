"""
JSON stringify node model for converting Python objects to JSON strings.

This module defines the JSONStringifyNode class, which converts Python objects
(dictionaries, lists, etc.) to JSON-formatted strings.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class JSONStringifyNode(BaseNode):
    """
    A node that converts Python objects to JSON strings.

    The JSONStringifyNode takes Python objects (dict, list, str, int, float,
    bool, or None) and converts them to JSON-formatted strings. It supports
    formatting options like indentation and key sorting.

    The data can be:
    - Provided dynamically through the data input port
    - Configured directly on the node (via the default_data property)

    Attributes:
        indent: Number of spaces for indentation (None for compact output).
        sort_keys: Whether to sort dictionary keys alphabetically.
        default_data: Default data to stringify if no input is provided.

    Example:
        >>> node = JSONStringifyNode(indent=2)
        >>> result = node.execute({"data": {"name": "John", "age": 30}})
        >>> result['success']
        True
        >>> result['json_string']
        '{\\n  "age": 30,\\n  "name": "John"\\n}'
    """

    # Class-level metadata
    node_type: str = "json_stringify"
    """Unique identifier for JSON stringify nodes."""

    node_category: str = "Data Processing"
    """Category for organizing in the UI."""

    node_color: str = "#FF6B00"
    """Orange color for data processing operations."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        indent: Optional[int] = None,
        sort_keys: bool = False,
        default_data: Any = None,
    ) -> None:
        """
        Initialize a new JSONStringifyNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Json Stringify'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            indent: Number of spaces for indentation (None for compact output).
            sort_keys: Whether to sort dictionary keys alphabetically.
            default_data: Default data to stringify if no input is provided.
        """
        self._indent: Optional[int] = indent
        self._sort_keys: bool = sort_keys
        self._default_data: Any = default_data
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the JSON stringify node.

        The JSON stringify node has:
        - An execution flow input port (for controlling execution order)
        - A data input port (for the Python object to stringify)
        - An indent input port (optional, for dynamic indentation)
        - A sort_keys input port (optional, for dynamic key sorting)
        - An execution flow output port (for chaining execution)
        - A json_string output port with the resulting JSON string
        - A success output port indicating whether the operation succeeded
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

        # Data input
        self.add_input_port(InputPort(
            name="data",
            port_type=PortType.ANY,
            description="Python object to convert to JSON (dict, list, str, int, float, bool, or None)",
            required=False,
        ))

        # Formatting options inputs
        self.add_input_port(InputPort(
            name="indent",
            port_type=PortType.INTEGER,
            description="Number of spaces for indentation (overrides configured indent)",
            required=False,
        ))
        self.add_input_port(InputPort(
            name="sort_keys",
            port_type=PortType.BOOLEAN,
            description="Whether to sort dictionary keys (overrides configured sort_keys)",
            required=False,
            display_hint=self._sort_keys,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="json_string",
            port_type=PortType.STRING,
            description="The resulting JSON string",
        ))
        self.add_output_port(OutputPort(
            name="success",
            port_type=PortType.BOOLEAN,
            description="Whether the conversion was successful",
        ))
        self.add_output_port(OutputPort(
            name="error_message",
            port_type=PortType.STRING,
            description="Error message if conversion failed",
        ))

    @property
    def indent(self) -> Optional[int]:
        """Get the configured indentation level."""
        return self._indent

    @indent.setter
    def indent(self, value: Optional[int]) -> None:
        """
        Set the indentation level.

        Args:
            value: Number of spaces for indentation (None for compact output).
        """
        self._indent = value

    @property
    def sort_keys(self) -> bool:
        """Get the configured sort_keys setting."""
        return self._sort_keys

    @sort_keys.setter
    def sort_keys(self, value: bool) -> None:
        """
        Set whether to sort dictionary keys.

        Args:
            value: True to sort keys alphabetically.
        """
        self._sort_keys = value

    @property
    def default_data(self) -> Any:
        """Get the default data to stringify."""
        return self._default_data

    @default_data.setter
    def default_data(self, value: Any) -> None:
        """
        Set the default data to stringify.

        Args:
            value: The default data.
        """
        self._default_data = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Data is required (either configured or via input port)
        if self._default_data is None:
            # Check if data input port is connected
            data_port = self.get_input_port("data")
            if data_port and not data_port.is_connected():
                errors.append(
                    "Data must be configured or provided via input port"
                )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert the Python object to a JSON string.

        The data is determined by:
        1. The 'data' input port value (if provided)
        2. The configured default_data property

        The formatting options are determined by:
        1. The input port values (if provided)
        2. The configured properties

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'json_string': The resulting JSON string (empty string if failed)
                - 'success': Boolean indicating if the conversion was successful
                - 'error_message': Error message if failed (empty string if success)
        """
        # Determine the data to stringify
        data = inputs.get("data", self._default_data)

        # Determine formatting options
        indent = inputs.get("indent", self._indent)
        sort_keys = inputs.get("sort_keys", self._sort_keys)

        try:
            json_string = json.dumps(
                data,
                indent=indent,
                sort_keys=sort_keys,
                ensure_ascii=False,
            )
            return {
                "json_string": json_string,
                "success": True,
                "error_message": "",
            }
        except TypeError as e:
            logger.error("JSON stringify failed: %s", e, exc_info=True)
            return {
                "json_string": "",
                "success": False,
                "error_message": f"Object not JSON serializable: {e}",
            }
        except Exception as e:
            logger.error("JSON stringify failed: %s", e, exc_info=True)
            return {
                "json_string": "",
                "success": False,
                "error_message": str(e),
            }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get JSON stringify node specific properties for serialization.

        Returns:
            Dictionary containing the formatting options and default data.
        """
        return {
            "indent": self._indent,
            "sort_keys": self._sort_keys,
            "default_data": self._default_data,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load JSON stringify node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._indent = properties.get("indent")
        self._sort_keys = properties.get("sort_keys", False)
        self._default_data = properties.get("default_data")

    def __repr__(self) -> str:
        """Get a detailed string representation of the JSON stringify node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"indent={self._indent}, "
            f"sort_keys={self._sort_keys}, "
            f"state={self._execution_state.name})"
        )
