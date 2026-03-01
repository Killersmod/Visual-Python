"""
File read node model for reading data from files.

This module defines the FileReadNode class, which reads content
from a file at a specified path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class FileReadNode(BaseNode):
    """
    A node that reads content from a file.

    The FileReadNode reads string content from a file at the specified path.
    It supports configurable encoding and provides both the content and
    status information.

    The file path can be:
    - Configured directly on the node (via the file_path property)
    - Provided dynamically through the file_path input port

    Attributes:
        file_path: The path to the file to read from.
        encoding: The encoding to use when reading the file.

    Example:
        >>> node = FileReadNode(file_path="input.txt")
        >>> result = node.execute({})
        >>> result['success']
        True
        >>> result['content']
        'File contents here...'
    """

    # Class-level metadata
    node_type: str = "file_read"
    """Unique identifier for file read nodes."""

    node_category: str = "File I/O"
    """Category for organizing in the UI."""

    node_color: str = "#4CAF50"
    """Green color for file read operations (distinct from write's orange)."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        file_path: str = "",
        encoding: str = "utf-8",
    ) -> None:
        """
        Initialize a new FileReadNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'File Read'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            file_path: The path to the file to read from.
            encoding: The encoding to use when reading the file.
        """
        self._file_path: str = file_path
        self._encoding: str = encoding
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the file read node.

        The file read node has:
        - An execution flow input port (for controlling execution order)
        - A file_path input port (optional, for dynamic file paths)
        - An encoding input port (optional, for dynamic encoding)
        - An execution flow output port (for chaining execution)
        - A content output port with the file contents
        - A success output port indicating whether the operation succeeded
        - A bytes_read output port with the number of characters read
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

        # File path input (optional - allows dynamic file paths)
        self.add_input_port(InputPort(
            name="file_path",
            port_type=PortType.STRING,
            description="Path to the file to read (overrides configured path)",
            required=False,
            display_hint=self._file_path,
        ))

        # Encoding input (optional - allows dynamic encoding)
        self.add_input_port(InputPort(
            name="encoding",
            port_type=PortType.STRING,
            description="Encoding to use when reading the file (overrides configured encoding)",
            required=False,
            display_hint=self._encoding,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="content",
            port_type=PortType.STRING,
            description="The content read from the file",
        ))
        self.add_output_port(OutputPort(
            name="success",
            port_type=PortType.BOOLEAN,
            description="Whether the file was successfully read",
        ))
        self.add_output_port(OutputPort(
            name="bytes_read",
            port_type=PortType.INTEGER,
            description="Number of characters read from the file",
        ))
        self.add_output_port(OutputPort(
            name="error_message",
            port_type=PortType.STRING,
            description="Error message if the read operation failed",
        ))

    @property
    def file_path(self) -> str:
        """Get the configured file path."""
        return self._file_path

    @file_path.setter
    def file_path(self, value: str) -> None:
        """
        Set the file path to read from.

        Args:
            value: The path to the file.
        """
        self._file_path = value

    @property
    def encoding(self) -> str:
        """Get the configured encoding."""
        return self._encoding

    @encoding.setter
    def encoding(self, value: str) -> None:
        """
        Set the encoding to use when reading.

        Args:
            value: The encoding name (e.g., 'utf-8').
        """
        self._encoding = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # File path is required (either configured or via input port)
        if not self._file_path:
            # Check if file_path input port is connected
            file_path_port = self.get_input_port("file_path")
            if file_path_port and not file_path_port.is_connected():
                errors.append(
                    "File path must be configured or provided via input port"
                )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read content from the file.

        The file path is determined by:
        1. The 'file_path' input port value (if provided)
        2. The configured file_path property

        The encoding is determined by:
        1. The 'encoding' input port value (if provided)
        2. The configured encoding property

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'content': The file content (empty string if failed)
                - 'success': Boolean indicating if the file was read
                - 'bytes_read': Number of characters read
                - 'error_message': Error message if failed (empty string if success)

        Raises:
            ValueError: If no file path is specified.
        """
        # Determine the file path to use
        path = inputs.get("file_path", self._file_path)

        if not path:
            raise ValueError("No file path specified")

        # Determine encoding
        encoding = inputs.get("encoding", self._encoding)
        if not encoding:
            encoding = "utf-8"

        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()

            return {
                "content": content,
                "success": True,
                "bytes_read": len(content),
                "error_message": "",
            }
        except Exception as e:
            logger.error("File read failed: %s", e, exc_info=True)
            return {
                "content": "",
                "success": False,
                "bytes_read": 0,
                "error_message": str(e),
            }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get file read node specific properties for serialization.

        Returns:
            Dictionary containing the file path and encoding.
        """
        return {
            "file_path": self._file_path,
            "encoding": self._encoding,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load file read node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._file_path = properties.get("file_path", "")
        self._encoding = properties.get("encoding", "utf-8")

    def __repr__(self) -> str:
        """Get a detailed string representation of the file read node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"file_path='{self._file_path}', "
            f"encoding='{self._encoding}', "
            f"state={self._execution_state.name})"
        )
