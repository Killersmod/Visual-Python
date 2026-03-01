"""
List Append node model for adding elements to lists in VisualPython.

This module defines the ListAppendNode class, which enables appending
single or multiple elements to a list without writing code.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class ListAppendNode(BaseNode):
    """
    A node that appends elements to a list.

    The ListAppendNode enables visual list manipulation by appending one or more
    elements to an existing list. It supports appending a single element or
    extending with multiple elements.

    The node has:
    - An input for the source list
    - An input for the element(s) to append
    - An output for the resulting list with appended elements

    Attributes:
        extend_mode: If True, extends the list with multiple elements instead of
                    appending a single element.
        create_new_list: If True, creates a new list instead of modifying in place.

    Example:
        >>> node = ListAppendNode()
        >>> result = node.execute({"list": [1, 2], "element": 3})
        >>> result["result"]  # [1, 2, 3]
    """

    # Class-level metadata
    node_type: str = "list_append"
    """Unique identifier for list append nodes."""

    node_category: str = "List Operations"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to distinguish list operation nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        extend_mode: bool = False,
        create_new_list: bool = True,
    ) -> None:
        """
        Initialize a new ListAppendNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'List Append'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            extend_mode: If True, extends the list with iterable elements.
            create_new_list: If True, creates a copy of the list before modifying.
        """
        self._extend_mode: bool = extend_mode
        self._create_new_list: bool = create_new_list
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the list append node.

        The list append node has:
        - exec_in: Execution flow input
        - list: The source list to append to
        - element: The element(s) to append
        - exec_out: Execution flow output
        - result: The resulting list with appended element(s)
        - length: The new length of the list
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # Source list input
        self.add_input_port(InputPort(
            name="list",
            port_type=PortType.LIST,
            description="The source list to append to",
            required=True,
        ))

        # Element to append
        self.add_input_port(InputPort(
            name="element",
            port_type=PortType.ANY,
            description="The element(s) to append to the list",
            required=True,
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Result list output
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.LIST,
            description="The list with appended element(s)",
        ))

        # New length output
        self.add_output_port(OutputPort(
            name="length",
            port_type=PortType.INTEGER,
            description="The new length of the list",
        ))

    @property
    def extend_mode(self) -> bool:
        """Get whether extend mode is enabled."""
        return self._extend_mode

    @extend_mode.setter
    def extend_mode(self, value: bool) -> None:
        """Set whether extend mode is enabled."""
        self._extend_mode = value

    @property
    def create_new_list(self) -> bool:
        """Get whether a new list is created."""
        return self._create_new_list

    @create_new_list.setter
    def create_new_list(self, value: bool) -> None:
        """Set whether a new list is created."""
        self._create_new_list = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        return []

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the list append operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   Must contain 'list' and 'element'.

        Returns:
            Dictionary with 'result' containing the modified list and
            'length' containing the new list length.

        Raises:
            ValueError: If required inputs are missing.
            TypeError: If the list input is not a list.
        """
        source_list = inputs.get("list")
        element = inputs.get("element")

        if source_list is None:
            raise ValueError("No list provided to list append node")

        if not isinstance(source_list, list):
            raise TypeError(
                f"List append requires a list, got {type(source_list).__name__}"
            )

        # Create a copy or use the original based on settings
        if self._create_new_list:
            result_list = source_list.copy()
        else:
            result_list = source_list

        # Append or extend based on mode
        if self._extend_mode:
            try:
                result_list.extend(element)
            except TypeError:
                # If element is not iterable, append it as a single element
                result_list.append(element)
        else:
            result_list.append(element)

        return {
            "result": result_list,
            "length": len(result_list),
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get list append node specific properties for serialization.

        Returns:
            Dictionary containing the node's configuration.
        """
        return {
            "extend_mode": self._extend_mode,
            "create_new_list": self._create_new_list,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load list append node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._extend_mode = properties.get("extend_mode", False)
        self._create_new_list = properties.get("create_new_list", True)

    def __repr__(self) -> str:
        """Get a detailed string representation of the list append node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"extend_mode={self._extend_mode}, "
            f"create_new_list={self._create_new_list}, "
            f"state={self._execution_state.name})"
        )
