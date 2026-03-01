"""
Print node model for outputting messages to the console.

This module defines the PrintNode class, which prints messages to the
console output with optional formatting options.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class PrintNode(BaseNode):
    """
    A node that prints messages to the console output.

    The PrintNode provides a clean interface for outputting messages
    to the console with optional formatting. It is simpler and more
    user-friendly than using print() in code nodes.

    The message can be:
    - Configured directly on the node (via the message property)
    - Provided dynamically through the message input port

    Formatting options include:
    - Optional prefix text prepended to messages
    - Optional timestamp showing when the message was printed
    - Optional newline control

    Attributes:
        message: The default message to print.
        prefix: Optional prefix text to prepend to the message.
        add_timestamp: Whether to include a timestamp with the message.
        add_newline: Whether to add a newline after the message.

    Example:
        >>> node = PrintNode(message="Hello, World!")
        >>> result = node.execute({})
        >>> # Prints: Hello, World!
        >>> result['printed_message']
        'Hello, World!'
    """

    # Class-level metadata
    node_type: str = "print"
    """Unique identifier for print nodes."""

    node_category: str = "Input/Output"
    """Category for organizing in the UI."""

    node_color: str = "#4CAF50"
    """Green color to indicate output operation."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        message: str = "",
        prefix: str = "",
        add_timestamp: bool = False,
        add_newline: bool = True,
    ) -> None:
        """
        Initialize a new PrintNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Print'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            message: The default message to print.
            prefix: Optional prefix text to prepend to the message.
            add_timestamp: Whether to include a timestamp with the message.
            add_newline: Whether to add a newline after the message.
        """
        self._message: str = message
        self._prefix: str = prefix
        self._add_timestamp: bool = add_timestamp
        self._add_newline: bool = add_newline
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the print node.

        The print node has:
        - An execution flow input port (for controlling execution order)
        - A message input port (for dynamic messages)
        - A prefix input port (optional, for dynamic prefix)
        - An add_timestamp input port (optional, for dynamic timestamp control)
        - An execution flow output port (for chaining execution)
        - A printed_message output port (the formatted message that was printed)
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

        # Message input (accepts any type, will be converted to string)
        self.add_input_port(InputPort(
            name="message",
            port_type=PortType.ANY,
            description="The message to print (overrides configured message)",
            required=False,
            display_hint=self._message,
        ))

        # Prefix input (optional - allows dynamic prefix)
        self.add_input_port(InputPort(
            name="prefix",
            port_type=PortType.STRING,
            description="Prefix text to prepend to the message",
            required=False,
            display_hint=self._prefix,
        ))

        # Timestamp control input (optional)
        self.add_input_port(InputPort(
            name="add_timestamp",
            port_type=PortType.BOOLEAN,
            description="Whether to include a timestamp with the message",
            required=False,
            display_hint=self._add_timestamp,
        ))

        # Output port for the formatted message
        self.add_output_port(OutputPort(
            name="printed_message",
            port_type=PortType.STRING,
            description="The formatted message that was printed",
        ))

    @property
    def message(self) -> str:
        """Get the configured message."""
        return self._message

    @message.setter
    def message(self, value: str) -> None:
        """
        Set the message to print.

        Args:
            value: The message text.
        """
        self._message = value

    @property
    def prefix(self) -> str:
        """Get the configured prefix."""
        return self._prefix

    @prefix.setter
    def prefix(self, value: str) -> None:
        """
        Set the prefix text.

        Args:
            value: The prefix to prepend to messages.
        """
        self._prefix = value

    @property
    def add_timestamp(self) -> bool:
        """Get whether timestamps are enabled."""
        return self._add_timestamp

    @add_timestamp.setter
    def add_timestamp(self, value: bool) -> None:
        """
        Set whether to add timestamps.

        Args:
            value: True to add timestamps, False otherwise.
        """
        self._add_timestamp = value

    @property
    def add_newline(self) -> bool:
        """Get whether newline is added after message."""
        return self._add_newline

    @add_newline.setter
    def add_newline(self, value: bool) -> None:
        """
        Set whether to add a newline after the message.

        Args:
            value: True to add newline, False otherwise.
        """
        self._add_newline = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        The print node is always valid as an empty message is acceptable.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        # Print node accepts empty messages, so always valid
        return []

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the print node by outputting a formatted message.

        The message is determined by:
        1. The 'message' input port value (if provided)
        2. The configured message property

        Formatting is applied based on:
        1. Prefix (from input port or configured property)
        2. Timestamp (if enabled via input port or configured property)

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'printed_message': The formatted message that was printed
        """
        # Determine the message to print
        msg = inputs.get("message", self._message)

        # Convert to string if necessary
        if msg is None:
            msg = ""
        elif not isinstance(msg, str):
            msg = str(msg)

        # Determine prefix
        prefix = inputs.get("prefix", self._prefix)
        if prefix is None:
            prefix = ""

        # Determine timestamp setting
        use_timestamp = inputs.get("add_timestamp", self._add_timestamp)
        if use_timestamp is None:
            use_timestamp = self._add_timestamp

        # Build the formatted message
        parts = []

        # Add timestamp if enabled
        if use_timestamp:
            timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
            parts.append(timestamp)

        # Add prefix if configured
        if prefix:
            parts.append(prefix)

        # Add the message
        parts.append(msg)

        # Join parts with spaces
        formatted_message = " ".join(parts)

        # Print the message
        end_char = "\n" if self._add_newline else ""
        print(formatted_message, end=end_char)

        return {
            "printed_message": formatted_message,
        }

    def get_code_preview(self) -> Optional[str]:
        """
        Get a preview of the Python code this print node would generate.

        Returns a formatted print() statement based on the node's current
        configuration, showing the message and any formatting options.

        Returns:
            A string containing the Python code preview.

        Example:
            For a PrintNode with message="Hello", prefix=">>", this returns:
            'print(">> " + "Hello")'
        """
        # Build the argument parts for the print statement
        parts = []

        # Add prefix if configured
        if self._prefix:
            parts.append(repr(self._prefix + " "))

        # Add timestamp placeholder if enabled
        if self._add_timestamp:
            parts.append('f"[{datetime.now():%Y-%m-%d %H:%M:%S}]"')

        # Add the message
        if self._message:
            parts.append(repr(self._message))
        else:
            parts.append('message')  # Placeholder for input port value

        # Build the print argument
        if len(parts) == 1:
            print_arg = parts[0]
        else:
            print_arg = " + ".join(parts)

        # Build the print statement with end parameter if newline is disabled
        if self._add_newline:
            return f"print({print_arg})"
        else:
            return f'print({print_arg}, end="")'

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get print node specific properties for serialization.

        Returns:
            Dictionary containing the message, prefix, and formatting options.
        """
        return {
            "message": self._message,
            "prefix": self._prefix,
            "add_timestamp": self._add_timestamp,
            "add_newline": self._add_newline,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load print node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._message = properties.get("message", "")
        self._prefix = properties.get("prefix", "")
        self._add_timestamp = properties.get("add_timestamp", False)
        self._add_newline = properties.get("add_newline", True)

    def __repr__(self) -> str:
        """Get a detailed string representation of the print node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"message='{self._message[:20]}{'...' if len(self._message) > 20 else ''}', "
            f"prefix='{self._prefix}', "
            f"add_timestamp={self._add_timestamp}, "
            f"state={self._execution_state.name})"
        )
