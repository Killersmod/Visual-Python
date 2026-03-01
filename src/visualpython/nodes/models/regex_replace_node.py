"""
Regex replace node model for pattern replacement operations in VisualPython.

This module defines the RegexReplaceNode class, which performs regular expression
pattern replacement on text strings.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class RegexReplaceNode(BaseNode):
    """
    A node that performs regular expression pattern replacement on text.

    The RegexReplaceNode provides a visual way to find and replace patterns
    in text using regular expressions. It supports backreferences in the
    replacement string.

    Attributes:
        default_pattern: Default regex pattern to match.
        default_replacement: Default replacement string.
        max_replacements: Maximum number of replacements (0 = unlimited).
        case_insensitive: Whether to ignore case when matching.
        multiline: Whether to enable multiline mode.
        dot_all: Whether dot matches newlines.

    Example:
        >>> node = RegexReplaceNode(default_pattern=r"\\d+", default_replacement="[NUM]")
        >>> result = node.execute({"text": "abc123def456"})
        >>> result["result"]  # "abc[NUM]def[NUM]"
        >>> result["replacement_count"]  # 2
    """

    # Class-level metadata
    node_type: str = "regex_replace"
    """Unique identifier for regex replace nodes."""

    node_category: str = "String Operations"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to indicate string operation."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        default_pattern: str = "",
        default_replacement: str = "",
        max_replacements: int = 0,
        case_insensitive: bool = False,
        multiline: bool = False,
        dot_all: bool = False,
    ) -> None:
        """
        Initialize a new RegexReplaceNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Regex Replace'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            default_pattern: Default regex pattern to match.
            default_replacement: Default replacement string (supports backreferences).
            max_replacements: Maximum number of replacements (0 = unlimited).
            case_insensitive: Whether to ignore case when matching.
            multiline: Whether to enable multiline mode (^ and $ match line boundaries).
            dot_all: Whether dot (.) matches newlines.
        """
        self._default_pattern: str = default_pattern
        self._default_replacement: str = default_replacement
        self._max_replacements: int = max_replacements
        self._case_insensitive: bool = case_insensitive
        self._multiline: bool = multiline
        self._dot_all: bool = dot_all
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the regex replace node.

        The regex replace node has:
        - exec_in: Execution flow input (optional)
        - text: Text to perform replacement on
        - pattern: Regex pattern to match
        - replacement: Replacement string (supports backreferences)
        - exec_out: Execution flow output
        - result: Text after replacements
        - replacement_count: Number of replacements made
        - original_text: Original input text
        - changed: Boolean indicating if any replacements were made
        - error_message: Error message if regex compilation fails
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
            description="Text to perform replacement on",
            required=False,
            default_value="",
        ))

        # Pattern input
        self.add_input_port(InputPort(
            name="pattern",
            port_type=PortType.STRING,
            description="Regular expression pattern to match",
            required=False,
            default_value=self._default_pattern,
        ))

        # Replacement input
        self.add_input_port(InputPort(
            name="replacement",
            port_type=PortType.STRING,
            description="Replacement string (supports \\1, \\2, etc. for backreferences)",
            required=False,
            default_value=self._default_replacement,
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Result text
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.STRING,
            description="Text after replacements",
        ))

        # Replacement count
        self.add_output_port(OutputPort(
            name="replacement_count",
            port_type=PortType.INTEGER,
            description="Number of replacements made",
        ))

        # Original text
        self.add_output_port(OutputPort(
            name="original_text",
            port_type=PortType.STRING,
            description="Original input text",
        ))

        # Changed flag
        self.add_output_port(OutputPort(
            name="changed",
            port_type=PortType.BOOLEAN,
            description="True if any replacements were made",
        ))

        # Error message
        self.add_output_port(OutputPort(
            name="error_message",
            port_type=PortType.STRING,
            description="Error message if regex compilation fails",
        ))

    @property
    def default_pattern(self) -> str:
        """Get the default regex pattern."""
        return self._default_pattern

    @default_pattern.setter
    def default_pattern(self, value: str) -> None:
        """Set the default regex pattern."""
        self._default_pattern = value

    @property
    def default_replacement(self) -> str:
        """Get the default replacement string."""
        return self._default_replacement

    @default_replacement.setter
    def default_replacement(self, value: str) -> None:
        """Set the default replacement string."""
        self._default_replacement = value

    @property
    def max_replacements(self) -> int:
        """Get the maximum number of replacements."""
        return self._max_replacements

    @max_replacements.setter
    def max_replacements(self, value: int) -> None:
        """Set the maximum number of replacements."""
        self._max_replacements = value

    @property
    def case_insensitive(self) -> bool:
        """Get whether matching is case insensitive."""
        return self._case_insensitive

    @case_insensitive.setter
    def case_insensitive(self, value: bool) -> None:
        """Set whether matching is case insensitive."""
        self._case_insensitive = value

    @property
    def multiline(self) -> bool:
        """Get whether multiline mode is enabled."""
        return self._multiline

    @multiline.setter
    def multiline(self, value: bool) -> None:
        """Set whether multiline mode is enabled."""
        self._multiline = value

    @property
    def dot_all(self) -> bool:
        """Get whether dot matches newlines."""
        return self._dot_all

    @dot_all.setter
    def dot_all(self, value: bool) -> None:
        """Set whether dot matches newlines."""
        self._dot_all = value

    def _get_regex_flags(self) -> int:
        """Get the combined regex flags based on node configuration."""
        flags = 0
        if self._case_insensitive:
            flags |= re.IGNORECASE
        if self._multiline:
            flags |= re.MULTILINE
        if self._dot_all:
            flags |= re.DOTALL
        return flags

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate that default pattern is a string
        if not isinstance(self._default_pattern, str):
            errors.append(f"Default pattern must be a string, got {type(self._default_pattern).__name__}")

        # Validate that default replacement is a string
        if not isinstance(self._default_replacement, str):
            errors.append(f"Default replacement must be a string, got {type(self._default_replacement).__name__}")

        # Validate max_replacements
        if not isinstance(self._max_replacements, int) or self._max_replacements < 0:
            errors.append("Max replacements must be a non-negative integer")

        # Try to compile the default pattern if provided
        if self._default_pattern:
            try:
                re.compile(self._default_pattern)
            except re.error as e:
                errors.append(f"Invalid default regex pattern: {e}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the regex replace operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'text', 'pattern', and 'replacement'.

        Returns:
            Dictionary with 'result', 'replacement_count', 'original_text',
            'changed', and 'error_message'.
        """
        # Get inputs with defaults
        text = inputs.get("text", "")
        pattern = inputs.get("pattern", self._default_pattern)
        replacement = inputs.get("replacement", self._default_replacement)

        # Handle None values
        if text is None:
            text = ""
        if pattern is None:
            pattern = self._default_pattern
        if replacement is None:
            replacement = self._default_replacement

        # Ensure text is string
        if not isinstance(text, str):
            text = str(text)

        # Store original
        original_text = text

        # Initialize outputs
        result = text
        replacement_count = 0
        changed = False
        error_message = ""

        # Execute regex replacement
        try:
            flags = self._get_regex_flags()
            compiled_pattern = re.compile(pattern, flags)

            # Perform replacement with count
            if self._max_replacements > 0:
                result, replacement_count = compiled_pattern.subn(
                    replacement, text, count=self._max_replacements
                )
            else:
                result, replacement_count = compiled_pattern.subn(replacement, text)

            changed = replacement_count > 0

        except re.error as e:
            error_message = f"Regex error: {e}"
            result = text  # Return original on error
        except Exception as e:
            error_message = f"Error: {e}"
            result = text  # Return original on error

        return {
            "result": result,
            "replacement_count": replacement_count,
            "original_text": original_text,
            "changed": changed,
            "error_message": error_message,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get regex replace node specific properties for serialization.

        Returns:
            Dictionary containing the configuration values.
        """
        return {
            "default_pattern": self._default_pattern,
            "default_replacement": self._default_replacement,
            "max_replacements": self._max_replacements,
            "case_insensitive": self._case_insensitive,
            "multiline": self._multiline,
            "dot_all": self._dot_all,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load regex replace node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._default_pattern = properties.get("default_pattern", "")
        self._default_replacement = properties.get("default_replacement", "")
        self._max_replacements = properties.get("max_replacements", 0)
        self._case_insensitive = properties.get("case_insensitive", False)
        self._multiline = properties.get("multiline", False)
        self._dot_all = properties.get("dot_all", False)

    def __repr__(self) -> str:
        """Get a detailed string representation of the regex replace node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"pattern='{self._default_pattern}', "
            f"replacement='{self._default_replacement}', "
            f"state={self._execution_state.name})"
        )
