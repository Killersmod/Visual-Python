"""
String replace node model for text replacement in VisualPython.

This module defines the StringReplaceNode class, which performs simple
text replacement (not regex-based) on strings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class StringReplaceNode(BaseNode):
    """
    A node that performs simple text replacement on strings.

    The StringReplaceNode provides a visual way to find and replace text
    in strings without using regular expressions. For regex-based replacement,
    use the RegexReplaceNode instead.

    Attributes:
        default_search: Default search string.
        default_replacement: Default replacement string.
        max_replacements: Maximum number of replacements (-1 for unlimited).
        case_sensitive: Whether to perform case-sensitive matching.

    Example:
        >>> node = StringReplaceNode(default_search="world", default_replacement="Python")
        >>> result = node.execute({"text": "Hello world!"})
        >>> result["result"]  # "Hello Python!"
        >>> result["replacement_count"]  # 1
    """

    # Class-level metadata
    node_type: str = "string_replace"
    """Unique identifier for string replace nodes."""

    node_category: str = "String Operations"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to indicate string operation."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        default_search: str = "",
        default_replacement: str = "",
        max_replacements: int = -1,
        case_sensitive: bool = True,
    ) -> None:
        """
        Initialize a new StringReplaceNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'String Replace'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            default_search: Default string to search for.
            default_replacement: Default replacement string.
            max_replacements: Maximum number of replacements (-1 for unlimited).
            case_sensitive: Whether to perform case-sensitive matching (default: True).
        """
        self._default_search: str = default_search
        self._default_replacement: str = default_replacement
        self._max_replacements: int = max_replacements
        self._case_sensitive: bool = case_sensitive
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the string replace node.

        The string replace node has:
        - exec_in: Execution flow input (optional)
        - text: Text to perform replacement on
        - search: String to search for
        - replacement: Replacement string
        - exec_out: Execution flow output
        - result: Text after replacements
        - replacement_count: Number of replacements made
        - original_text: Original input text
        - changed: Boolean indicating if any replacements were made
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

        # Search input
        self.add_input_port(InputPort(
            name="search",
            port_type=PortType.STRING,
            description="String to search for",
            required=False,
            default_value=self._default_search,
        ))

        # Replacement input
        self.add_input_port(InputPort(
            name="replacement",
            port_type=PortType.STRING,
            description="Replacement string",
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

    @property
    def default_search(self) -> str:
        """Get the default search string."""
        return self._default_search

    @default_search.setter
    def default_search(self, value: str) -> None:
        """Set the default search string."""
        self._default_search = value

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
    def case_sensitive(self) -> bool:
        """Get whether matching is case sensitive."""
        return self._case_sensitive

    @case_sensitive.setter
    def case_sensitive(self, value: bool) -> None:
        """Set whether matching is case sensitive."""
        self._case_sensitive = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate that default search is a string
        if not isinstance(self._default_search, str):
            errors.append(f"Default search must be a string, got {type(self._default_search).__name__}")

        # Validate that default replacement is a string
        if not isinstance(self._default_replacement, str):
            errors.append(f"Default replacement must be a string, got {type(self._default_replacement).__name__}")

        # Validate max_replacements is an integer
        if not isinstance(self._max_replacements, int):
            errors.append(f"Max replacements must be an integer, got {type(self._max_replacements).__name__}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the string replace operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'text', 'search', and 'replacement'.

        Returns:
            Dictionary with 'result', 'replacement_count', 'original_text',
            and 'changed'.
        """
        # Get inputs with defaults
        text = inputs.get("text", "")
        search = inputs.get("search", self._default_search)
        replacement = inputs.get("replacement", self._default_replacement)

        # Handle None values
        if text is None:
            text = ""
        if search is None:
            search = self._default_search
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

        # Perform replacement
        if search:
            if self._case_sensitive:
                # Count occurrences
                replacement_count = text.count(search)
                # Perform replacement
                if self._max_replacements > 0:
                    result = text.replace(search, replacement, self._max_replacements)
                    replacement_count = min(replacement_count, self._max_replacements)
                else:
                    result = text.replace(search, replacement)
            else:
                # Case-insensitive replacement
                # Count occurrences (case-insensitive)
                replacement_count = text.lower().count(search.lower())

                if self._max_replacements > 0:
                    replacement_count = min(replacement_count, self._max_replacements)

                # Perform case-insensitive replacement
                result = self._case_insensitive_replace(
                    text, search, replacement,
                    self._max_replacements if self._max_replacements > 0 else -1
                )

        changed = result != original_text

        return {
            "result": result,
            "replacement_count": replacement_count,
            "original_text": original_text,
            "changed": changed,
        }

    def _case_insensitive_replace(
        self, text: str, search: str, replacement: str, max_count: int = -1
    ) -> str:
        """
        Perform case-insensitive string replacement.

        Args:
            text: The source text.
            search: The string to search for.
            replacement: The replacement string.
            max_count: Maximum number of replacements (-1 for unlimited).

        Returns:
            The text with replacements made.
        """
        if not search:
            return text

        result = []
        text_lower = text.lower()
        search_lower = search.lower()

        pos = 0
        count = 0

        while True:
            # Find next occurrence
            idx = text_lower.find(search_lower, pos)
            if idx == -1:
                # No more occurrences
                result.append(text[pos:])
                break

            # Add text before match and the replacement
            result.append(text[pos:idx])
            result.append(replacement)

            # Move position past the match
            pos = idx + len(search)
            count += 1

            # Check if we've reached max replacements
            if max_count > 0 and count >= max_count:
                result.append(text[pos:])
                break

        return "".join(result)

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get string replace node specific properties for serialization.

        Returns:
            Dictionary containing the configuration values.
        """
        return {
            "default_search": self._default_search,
            "default_replacement": self._default_replacement,
            "max_replacements": self._max_replacements,
            "case_sensitive": self._case_sensitive,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load string replace node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._default_search = properties.get("default_search", "")
        self._default_replacement = properties.get("default_replacement", "")
        self._max_replacements = properties.get("max_replacements", -1)
        self._case_sensitive = properties.get("case_sensitive", True)

    def __repr__(self) -> str:
        """Get a detailed string representation of the string replace node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"search='{self._default_search}', "
            f"replacement='{self._default_replacement}', "
            f"state={self._execution_state.name})"
        )
