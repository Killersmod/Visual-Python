"""
Input node model for prompting user input during execution.

This module defines the InputNode class, which prompts the user for input
during graph execution, storing the result in a variable for use by other nodes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtWidgets import QInputDialog, QApplication

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.variables import GlobalVariableStore


class InputNode(BaseNode):
    """
    A node that prompts the user for input during execution.

    The InputNode displays a dialog to collect user input and stores the
    result in a global variable (if specified) and outputs it for use
    by connected nodes. This enables interactive scripts that can respond
    to user input at runtime.

    The prompt text can be:
    - Configured directly on the node (via the prompt_text property)
    - Provided dynamically through the prompt_text input port

    The variable name is optional:
    - If specified, the input value will be stored in GlobalVariableStore
    - The value is always available via the 'value' output port

    Attributes:
        prompt_text: The text to display when prompting for input.
        variable_name: Optional name of the global variable to store the input.
        default_value: Default value to show in the input dialog.

    Example:
        >>> node = InputNode(prompt_text="Enter your name:")
        >>> result = node.execute({})
        >>> # User enters "Alice" in the dialog
        >>> result['value']
        'Alice'
    """

    # Class-level metadata
    node_type: str = "input"
    """Unique identifier for input nodes."""

    node_category: str = "Input/Output"
    """Category for organizing in the UI."""

    node_color: str = "#FF6B6B"
    """Red-ish color to indicate user interaction."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        prompt_text: str = "Enter value:",
        variable_name: str = "",
        default_value: str = "",
    ) -> None:
        """
        Initialize a new InputNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Input'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            prompt_text: The text to display when prompting for input.
            variable_name: Optional name of the global variable to store the input.
            default_value: Default value to show in the input dialog.
        """
        self._prompt_text: str = prompt_text
        self._variable_name: str = variable_name
        self._default_value: str = default_value
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the input node.

        The input node has:
        - An execution flow input port (for controlling execution order)
        - A prompt_text input port (optional, for dynamic prompt text)
        - A default_value input port (optional, for dynamic default value)
        - An execution flow output port (for chaining execution)
        - A value output port (the user input)
        - A cancelled output port indicating whether the user cancelled
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

        # Prompt text input (optional - allows dynamic prompts)
        self.add_input_port(InputPort(
            name="prompt_text",
            port_type=PortType.STRING,
            description="Text to display when prompting for input (overrides configured text)",
            required=False,
            display_hint=self._prompt_text,
        ))

        # Default value input (optional - allows dynamic default values)
        self.add_input_port(InputPort(
            name="default_value",
            port_type=PortType.STRING,
            description="Default value to show in the input dialog",
            required=False,
            display_hint=self._default_value,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="value",
            port_type=PortType.STRING,
            description="The user input value",
        ))

        self.add_output_port(OutputPort(
            name="cancelled",
            port_type=PortType.BOOLEAN,
            description="Whether the user cancelled the input dialog",
        ))

    @property
    def prompt_text(self) -> str:
        """Get the configured prompt text."""
        return self._prompt_text

    @prompt_text.setter
    def prompt_text(self, value: str) -> None:
        """
        Set the prompt text.

        Args:
            value: The text to display when prompting for input.
        """
        self._prompt_text = value

    @property
    def variable_name(self) -> str:
        """Get the configured variable name."""
        return self._variable_name

    @variable_name.setter
    def variable_name(self, value: str) -> None:
        """
        Set the variable name to store the input to.

        Args:
            value: The name of the global variable.
        """
        self._variable_name = value

    @property
    def default_value(self) -> str:
        """Get the configured default value."""
        return self._default_value

    @default_value.setter
    def default_value(self, value: str) -> None:
        """
        Set the default value for the input dialog.

        Args:
            value: The default value to show.
        """
        self._default_value = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Prompt text is required (either configured or via input port)
        if not self._prompt_text:
            prompt_port = self.get_input_port("prompt_text")
            if prompt_port and not prompt_port.is_connected():
                errors.append(
                    "Prompt text must be configured or provided via input port"
                )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the input node by prompting the user for input.

        The prompt text is determined by:
        1. The 'prompt_text' input port value (if provided)
        2. The configured prompt_text property

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'value': The user input string
                - 'cancelled': Boolean indicating if the user cancelled

        Raises:
            RuntimeError: If no Qt application is available.
        """
        # Determine the prompt text to use
        prompt = inputs.get("prompt_text", self._prompt_text)
        if not prompt:
            prompt = "Enter value:"

        # Determine the default value to use
        default = inputs.get("default_value", self._default_value)
        if default is None:
            default = ""

        # Ensure we have a Qt application
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("No Qt application available for input dialog")

        # Show the input dialog
        # QInputDialog.getText returns (text, ok) tuple
        text, ok = QInputDialog.getText(
            None,  # Parent widget (None = no parent)
            "Input Required",  # Dialog title
            prompt,  # Prompt text
            text=str(default),  # Default value
        )

        # Store in global variable if configured
        if ok and self._variable_name:
            global_store = GlobalVariableStore.get_instance()
            global_store.set(self._variable_name, text)

        return {
            "value": text if ok else "",
            "cancelled": not ok,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get input node specific properties for serialization.

        Returns:
            Dictionary containing the prompt text, variable name, and default value.
        """
        return {
            "prompt_text": self._prompt_text,
            "variable_name": self._variable_name,
            "default_value": self._default_value,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load input node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._prompt_text = properties.get("prompt_text", "Enter value:")
        self._variable_name = properties.get("variable_name", "")
        self._default_value = properties.get("default_value", "")

    def __repr__(self) -> str:
        """Get a detailed string representation of the input node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"prompt_text='{self._prompt_text}', "
            f"variable_name='{self._variable_name}', "
            f"state={self._execution_state.name})"
        )
