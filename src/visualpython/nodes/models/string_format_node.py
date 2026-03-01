"""
String format node model for string formatting in VisualPython.

This module defines the StringFormatNode class, which provides template-based
string formatting with placeholder substitution.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class StringFormatNode(BaseNode):
    """
    A node that formats strings using template placeholders.

    The StringFormatNode provides a visual way to create formatted strings
    using Python's str.format() syntax. It supports named placeholders and
    provides multiple input values for substitution.

    Attributes:
        template: The format template string with placeholders.

    Example:
        >>> node = StringFormatNode(template="Hello, {name}! You have {count} messages.")
        >>> result = node.execute({"arg1": "World", "arg2": "5"})
        >>> result["result"]  # "Hello, World! You have 5 messages."

    Template Syntax:
        - Use {0}, {1}, {2}, etc. for positional arguments
        - Use {name} for named arguments (mapped from arg1, arg2, etc.)
        - The template "{} {} {}" uses arg1, arg2, arg3 in order
    """

    # Class-level metadata
    node_type: str = "string_format"
    """Unique identifier for string format nodes."""

    node_category: str = "String Operations"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to indicate string operation."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        template: str = "{0} {1}",
    ) -> None:
        """
        Initialize a new StringFormatNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'String Format'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            template: Format template string with placeholders (default: "{0} {1}").
        """
        self._template: str = template
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the string format node.

        The string format node has:
        - exec_in: Execution flow input (optional)
        - template: The format template string
        - arg1 through arg4: Values to substitute into the template
        - exec_out: Execution flow output
        - result: The formatted string
        - success: Boolean indicating if formatting succeeded
        - error_message: Error message if formatting fails
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # Template input
        self.add_input_port(InputPort(
            name="template",
            port_type=PortType.STRING,
            description="Format template string with placeholders like {0}, {1}, or {name}",
            required=False,
            default_value=self._template,
        ))

        # Argument inputs (accepting ANY type for flexibility)
        self.add_input_port(InputPort(
            name="arg1",
            port_type=PortType.ANY,
            description="First value for template substitution (maps to {0} or {arg1})",
            required=False,
            default_value="",
        ))

        self.add_input_port(InputPort(
            name="arg2",
            port_type=PortType.ANY,
            description="Second value for template substitution (maps to {1} or {arg2})",
            required=False,
            default_value="",
        ))

        self.add_input_port(InputPort(
            name="arg3",
            port_type=PortType.ANY,
            description="Third value for template substitution (maps to {2} or {arg3})",
            required=False,
            default_value="",
        ))

        self.add_input_port(InputPort(
            name="arg4",
            port_type=PortType.ANY,
            description="Fourth value for template substitution (maps to {3} or {arg4})",
            required=False,
            default_value="",
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Result string
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.STRING,
            description="The formatted string",
        ))

        # Success flag
        self.add_output_port(OutputPort(
            name="success",
            port_type=PortType.BOOLEAN,
            description="True if formatting succeeded",
        ))

        # Error message
        self.add_output_port(OutputPort(
            name="error_message",
            port_type=PortType.STRING,
            description="Error message if formatting fails",
        ))

    @property
    def template(self) -> str:
        """Get the format template."""
        return self._template

    @template.setter
    def template(self, value: str) -> None:
        """Set the format template."""
        self._template = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate that template is a string
        if not isinstance(self._template, str):
            errors.append(f"Template must be a string, got {type(self._template).__name__}")

        # Try to validate the template syntax (check for unbalanced braces)
        if isinstance(self._template, str):
            try:
                # Count braces - simple validation
                open_braces = self._template.count("{")
                close_braces = self._template.count("}")
                # Account for escaped braces {{ and }}
                escaped_open = self._template.count("{{")
                escaped_close = self._template.count("}}")
                actual_open = open_braces - escaped_open * 2
                actual_close = close_braces - escaped_close * 2
                if actual_open != actual_close:
                    errors.append("Template has unbalanced braces")
            except Exception as e:
                errors.append(f"Template validation error: {e}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the string format operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'template', 'arg1', 'arg2', 'arg3', 'arg4'.

        Returns:
            Dictionary with 'result', 'success', and 'error_message'.
        """
        # Get template from input or use default
        template = inputs.get("template", self._template)
        if template is None:
            template = self._template

        # Ensure template is string
        if not isinstance(template, str):
            template = str(template)

        # Get argument values
        args: List[Any] = []
        kwargs: Dict[str, Any] = {}

        for i, key in enumerate(["arg1", "arg2", "arg3", "arg4"]):
            value = inputs.get(key, "")
            if value is None:
                value = ""
            args.append(value)
            kwargs[key] = value
            # Also add numeric index for {0}, {1}, etc.
            kwargs[str(i)] = value

        # Initialize outputs
        result = template
        success = True
        error_message = ""

        try:
            # Try formatting with both positional and keyword arguments
            result = template.format(*args, **kwargs)
        except (KeyError, IndexError) as e:
            # Handle missing placeholders - try a more flexible approach
            try:
                # Try with just keyword arguments
                result = template.format(**kwargs)
            except (KeyError, IndexError) as e2:
                # If still failing, use safe substitution
                result, error_message = self._safe_format(template, args, kwargs)
                if error_message:
                    success = False
        except ValueError as e:
            error_message = f"Format error: {e}"
            success = False
            result = template
        except Exception as e:
            error_message = f"Unexpected error: {e}"
            success = False
            result = template

        return {
            "result": result,
            "success": success,
            "error_message": error_message,
        }

    def _safe_format(
        self, template: str, args: List[Any], kwargs: Dict[str, Any]
    ) -> tuple[str, str]:
        """
        Attempt safe formatting that handles missing placeholders gracefully.

        Args:
            template: The format template.
            args: Positional arguments.
            kwargs: Keyword arguments.

        Returns:
            Tuple of (formatted_result, error_message).
        """
        error_messages: List[str] = []
        result = template

        # Find all placeholders in the template
        placeholder_pattern = r'\{([^}]*)\}'
        placeholders = re.findall(placeholder_pattern, template)

        for placeholder in placeholders:
            # Skip empty placeholders (auto-numbered)
            if not placeholder:
                continue

            # Check if it's a numeric index
            if placeholder.isdigit():
                idx = int(placeholder)
                if idx < len(args):
                    # Replace this specific placeholder
                    result = result.replace(f"{{{placeholder}}}", str(args[idx]), 1)
                else:
                    error_messages.append(f"Missing argument for index {placeholder}")
            elif placeholder in kwargs:
                result = result.replace(f"{{{placeholder}}}", str(kwargs[placeholder]), 1)
            else:
                error_messages.append(f"Missing argument for key '{placeholder}'")

        # Handle auto-numbered placeholders {}
        auto_idx = 0
        while "{}" in result and auto_idx < len(args):
            result = result.replace("{}", str(args[auto_idx]), 1)
            auto_idx += 1

        error_message = "; ".join(error_messages) if error_messages else ""
        return result, error_message

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get string format node specific properties for serialization.

        Returns:
            Dictionary containing the template value.
        """
        return {
            "template": self._template,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load string format node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._template = properties.get("template", "{0} {1}")

    def __repr__(self) -> str:
        """Get a detailed string representation of the string format node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"template='{self._template[:30]}...', "
            f"state={self._execution_state.name})"
        )
