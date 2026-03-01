"""
File write node model for writing data to files.

This module defines the FileWriteNode class, which writes content
to a file at a specified path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class FileWriteNode(BaseNode):
    """
    A node that writes content to a file.

    The FileWriteNode writes string content to a file at the specified path.
    It supports both overwrite and append modes.

    The file path can be:
    - Configured directly on the node (via the file_path property)
    - Provided dynamically through the file_path input port

    The content to write can be:
    - Provided through the content input port

    Attributes:
        file_path: The path to the file to write to.
        append: Whether to append to the file instead of overwriting.
        encoding: The encoding to use when writing the file.

    Example:
        >>> node = FileWriteNode(file_path="output.txt")
        >>> result = node.execute({"content": "Hello, World!"})
        >>> result['success']
        True
    """

    # Class-level metadata
    node_type: str = "file_write"
    """Unique identifier for file write nodes."""

    node_category: str = "File I/O"
    """Category for organizing in the UI."""

    node_color: str = "#FF5722"
    """Deep orange color for file I/O operations."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        file_path: str = "",
        append: bool = False,
        encoding: str = "utf-8",
    ) -> None:
        """
        Initialize a new FileWriteNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'File Write'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            file_path: The path to the file to write to.
            append: Whether to append to the file instead of overwriting.
            encoding: The encoding to use when writing the file.
        """
        self._file_path: str = file_path
        self._append: bool = append
        self._encoding: str = encoding
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the file write node.

        The file write node has:
        - An execution flow input port (for controlling execution order)
        - A file_path input port (optional, for dynamic file paths)
        - A content input port (for the content to write)
        - An append input port (optional, for dynamic append mode)
        - An execution flow output port (for chaining execution)
        - A success output port indicating whether the operation succeeded
        - A bytes_written output port with the number of characters written
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
            description="Path to the file to write (overrides configured path)",
            required=False,
            display_hint=self._file_path,
        ))

        # Content input
        self.add_input_port(InputPort(
            name="content",
            port_type=PortType.STRING,
            description="The content to write to the file",
            required=False,
        ))

        # Append mode input (optional - allows dynamic append mode)
        self.add_input_port(InputPort(
            name="append",
            port_type=PortType.BOOLEAN,
            description="Whether to append to the file instead of overwriting",
            required=False,
            display_hint=self._append,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="success",
            port_type=PortType.BOOLEAN,
            description="Whether the file was successfully written",
        ))
        self.add_output_port(OutputPort(
            name="bytes_written",
            port_type=PortType.INTEGER,
            description="Number of characters written to the file",
        ))
        self.add_output_port(OutputPort(
            name="error_message",
            port_type=PortType.STRING,
            description="Error message if the write operation failed",
        ))

    @property
    def file_path(self) -> str:
        """Get the configured file path."""
        return self._file_path

    @file_path.setter
    def file_path(self, value: str) -> None:
        """
        Set the file path to write to.

        Args:
            value: The path to the file.
        """
        self._file_path = value

    @property
    def append(self) -> bool:
        """Get the configured append mode."""
        return self._append

    @append.setter
    def append(self, value: bool) -> None:
        """
        Set whether to append to the file.

        Args:
            value: True to append, False to overwrite.
        """
        self._append = value

    @property
    def encoding(self) -> str:
        """Get the configured encoding."""
        return self._encoding

    @encoding.setter
    def encoding(self, value: str) -> None:
        """
        Set the encoding to use when writing.

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
        Write content to the file.

        The file path is determined by:
        1. The 'file_path' input port value (if provided)
        2. The configured file_path property

        The append mode is determined by:
        1. The 'append' input port value (if provided)
        2. The configured append property

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'success': Boolean indicating if the file was written
                - 'bytes_written': Number of characters written
                - 'error_message': Error message if failed (empty string if success)

        Raises:
            ValueError: If no file path is specified.
        """
        # Determine the file path to use
        path = inputs.get("file_path", self._file_path)

        if not path:
            raise ValueError("No file path specified")

        # Determine append mode
        append_mode = inputs.get("append", self._append)

        # Get the content to write (defaults to empty string if not provided)
        content = inputs.get("content", "")

        # Convert content to string if necessary
        if not isinstance(content, str):
            content = str(content)

        try:
            mode = "a" if append_mode else "w"
            with open(path, mode, encoding=self._encoding) as f:
                bytes_written = f.write(content)

            return {
                "success": True,
                "bytes_written": bytes_written,
                "error_message": "",
            }
        except Exception as e:
            logger.error("File write failed: %s", e, exc_info=True)
            return {
                "success": False,
                "bytes_written": 0,
                "error_message": str(e),
            }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get file write node specific properties for serialization.

        Returns:
            Dictionary containing the file path, append mode, and encoding.
        """
        return {
            "file_path": self._file_path,
            "append": self._append,
            "encoding": self._encoding,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load file write node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._file_path = properties.get("file_path", "")
        self._append = properties.get("append", False)
        self._encoding = properties.get("encoding", "utf-8")

    def __repr__(self) -> str:
        """Get a detailed string representation of the file write node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"file_path='{self._file_path}', "
            f"append={self._append}, "
            f"state={self._execution_state.name})"
        )
