"""
Regex match node model for pattern matching operations in VisualPython.

This module defines the RegexMatchNode class, which performs regular expression
pattern matching on text strings.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class RegexMatchNode(BaseNode):
    """
    A node that performs regular expression pattern matching on text.

    The RegexMatchNode provides a visual way to find patterns in text using
    regular expressions. It can find all matches, return match groups, and
    indicate whether a pattern was found.

    Attributes:
        default_pattern: Default regex pattern to match.
        case_insensitive: Whether to ignore case when matching.
        multiline: Whether to enable multiline mode.
        dot_all: Whether dot matches newlines.

    Example:
        >>> node = RegexMatchNode(default_pattern=r"\\d+")
        >>> result = node.execute({"text": "abc123def456"})
        >>> result["matches"]  # ["123", "456"]
        >>> result["match_found"]  # True
    """

    # Class-level metadata
    node_type: str = "regex_match"
    """Unique identifier for regex match nodes."""

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
        case_insensitive: bool = False,
        multiline: bool = False,
        dot_all: bool = False,
    ) -> None:
        """
        Initialize a new RegexMatchNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Regex Match'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            default_pattern: Default regex pattern to match.
            case_insensitive: Whether to ignore case when matching.
            multiline: Whether to enable multiline mode (^ and $ match line boundaries).
            dot_all: Whether dot (.) matches newlines.
        """
        self._default_pattern: str = default_pattern
        self._case_insensitive: bool = case_insensitive
        self._multiline: bool = multiline
        self._dot_all: bool = dot_all
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the regex match node.

        The regex match node has:
        - exec_in: Execution flow input (optional)
        - text: Text to search in
        - pattern: Regex pattern to match
        - exec_out: Execution flow output
        - matches: List of all matches found
        - match_found: Boolean indicating if pattern was found
        - first_match: First match found (or empty string)
        - match_count: Number of matches found
        - groups: List of match groups from first match
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
            description="Text to search for pattern matches",
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

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # All matches
        self.add_output_port(OutputPort(
            name="matches",
            port_type=PortType.LIST,
            description="List of all matches found",
        ))

        # Match found flag
        self.add_output_port(OutputPort(
            name="match_found",
            port_type=PortType.BOOLEAN,
            description="True if at least one match was found",
        ))

        # First match
        self.add_output_port(OutputPort(
            name="first_match",
            port_type=PortType.STRING,
            description="First match found (empty string if none)",
        ))

        # Match count
        self.add_output_port(OutputPort(
            name="match_count",
            port_type=PortType.INTEGER,
            description="Number of matches found",
        ))

        # Groups from first match
        self.add_output_port(OutputPort(
            name="groups",
            port_type=PortType.LIST,
            description="Capture groups from first match",
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

        # Try to compile the default pattern if provided
        if self._default_pattern:
            try:
                re.compile(self._default_pattern)
            except re.error as e:
                errors.append(f"Invalid default regex pattern: {e}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the regex match operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'text' and 'pattern'.

        Returns:
            Dictionary with 'matches', 'match_found', 'first_match',
            'match_count', 'groups', and 'error_message'.
        """
        # Get inputs with defaults
        text = inputs.get("text", "")
        pattern = inputs.get("pattern", self._default_pattern)

        # Handle None values
        if text is None:
            text = ""
        if pattern is None:
            pattern = self._default_pattern

        # Ensure text is string
        if not isinstance(text, str):
            text = str(text)

        # Initialize outputs
        matches: List[str] = []
        match_found = False
        first_match = ""
        match_count = 0
        groups: List[str] = []
        error_message = ""

        # Execute regex matching
        try:
            flags = self._get_regex_flags()
            compiled_pattern = re.compile(pattern, flags)

            # Find all matches
            all_matches = compiled_pattern.findall(text)

            # Handle groups - findall returns tuples if pattern has groups
            if all_matches:
                if isinstance(all_matches[0], tuple):
                    # Pattern has groups - flatten to full matches
                    matches = [m[0] if m else "" for m in all_matches]
                else:
                    matches = list(all_matches)

                match_found = True
                first_match = matches[0] if matches else ""
                match_count = len(matches)

                # Get groups from first match using search
                first_match_obj = compiled_pattern.search(text)
                if first_match_obj:
                    groups = list(first_match_obj.groups()) if first_match_obj.groups() else []

        except re.error as e:
            error_message = f"Regex error: {e}"
        except Exception as e:
            error_message = f"Error: {e}"

        return {
            "matches": matches,
            "match_found": match_found,
            "first_match": first_match,
            "match_count": match_count,
            "groups": groups,
            "error_message": error_message,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get regex match node specific properties for serialization.

        Returns:
            Dictionary containing the configuration values.
        """
        return {
            "default_pattern": self._default_pattern,
            "case_insensitive": self._case_insensitive,
            "multiline": self._multiline,
            "dot_all": self._dot_all,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load regex match node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._default_pattern = properties.get("default_pattern", "")
        self._case_insensitive = properties.get("case_insensitive", False)
        self._multiline = properties.get("multiline", False)
        self._dot_all = properties.get("dot_all", False)

    def __repr__(self) -> str:
        """Get a detailed string representation of the regex match node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"pattern='{self._default_pattern}', "
            f"case_insensitive={self._case_insensitive}, "
            f"state={self._execution_state.name})"
        )
