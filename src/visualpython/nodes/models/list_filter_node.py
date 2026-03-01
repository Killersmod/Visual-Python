"""
List Filter node model for filtering list elements in VisualPython.

This module defines the ListFilterNode class, which enables filtering
list elements based on a condition or predicate without writing code.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class FilterCondition(Enum):
    """Predefined filter conditions for common use cases."""

    TRUTHY = "truthy"
    """Keep elements that are truthy."""

    FALSY = "falsy"
    """Keep elements that are falsy."""

    NOT_NONE = "not_none"
    """Keep elements that are not None."""

    IS_STRING = "is_string"
    """Keep elements that are strings."""

    IS_NUMBER = "is_number"
    """Keep elements that are numbers (int or float)."""

    IS_POSITIVE = "is_positive"
    """Keep elements that are positive numbers."""

    IS_NEGATIVE = "is_negative"
    """Keep elements that are negative numbers."""

    IS_EVEN = "is_even"
    """Keep elements that are even integers."""

    IS_ODD = "is_odd"
    """Keep elements that are odd integers."""

    CUSTOM = "custom"
    """Use a custom filter expression."""


class ListFilterNode(BaseNode):
    """
    A node that filters elements from a list based on a condition.

    The ListFilterNode enables visual list filtering by applying a predefined
    or custom condition to each element, keeping only those that match.

    The node has:
    - An input for the source list
    - An optional condition input for custom filtering
    - An output for the filtered list
    - An output for the rejected elements

    Attributes:
        filter_condition: The predefined condition to use for filtering.
        custom_expression: Custom Python expression for filtering (when condition is CUSTOM).
        variable_name: The variable name used in custom expressions (default: "x").

    Example:
        >>> node = ListFilterNode(filter_condition="is_positive")
        >>> result = node.execute({"list": [-1, 0, 1, 2, -3]})
        >>> result["result"]  # [1, 2]
    """

    # Class-level metadata
    node_type: str = "list_filter"
    """Unique identifier for list filter nodes."""

    node_category: str = "List Operations"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to distinguish list operation nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        filter_condition: str = "truthy",
        custom_expression: str = "",
        variable_name: str = "x",
    ) -> None:
        """
        Initialize a new ListFilterNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'List Filter'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            filter_condition: The filter condition to use (from FilterCondition enum values).
            custom_expression: Custom Python expression when condition is 'custom'.
            variable_name: Variable name for custom expressions.
        """
        self._filter_condition: str = filter_condition
        self._custom_expression: str = custom_expression
        self._variable_name: str = variable_name
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the list filter node.

        The list filter node has:
        - exec_in: Execution flow input
        - list: The source list to filter
        - exec_out: Execution flow output
        - result: The filtered list (elements that passed)
        - rejected: The rejected elements (elements that didn't pass)
        - count: The number of elements that passed
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
            description="The source list to filter",
            required=True,
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Filtered result list output
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.LIST,
            description="The filtered list (elements that passed the condition)",
        ))

        # Rejected elements output
        self.add_output_port(OutputPort(
            name="rejected",
            port_type=PortType.LIST,
            description="The rejected elements (elements that didn't pass)",
        ))

        # Count of passed elements
        self.add_output_port(OutputPort(
            name="count",
            port_type=PortType.INTEGER,
            description="The number of elements that passed the filter",
        ))

    @property
    def filter_condition(self) -> str:
        """Get the filter condition."""
        return self._filter_condition

    @filter_condition.setter
    def filter_condition(self, value: str) -> None:
        """Set the filter condition."""
        self._filter_condition = value

    @property
    def custom_expression(self) -> str:
        """Get the custom expression."""
        return self._custom_expression

    @custom_expression.setter
    def custom_expression(self, value: str) -> None:
        """Set the custom expression."""
        self._custom_expression = value

    @property
    def variable_name(self) -> str:
        """Get the variable name for custom expressions."""
        return self._variable_name

    @variable_name.setter
    def variable_name(self, value: str) -> None:
        """Set the variable name for custom expressions."""
        self._variable_name = value

    def _get_filter_function(self) -> Callable[[Any], bool]:
        """
        Get the filter function based on the current condition.

        Returns:
            A callable that takes an element and returns True if it should be kept.
        """
        condition = self._filter_condition

        if condition == FilterCondition.TRUTHY.value:
            return lambda x: bool(x)
        elif condition == FilterCondition.FALSY.value:
            return lambda x: not bool(x)
        elif condition == FilterCondition.NOT_NONE.value:
            return lambda x: x is not None
        elif condition == FilterCondition.IS_STRING.value:
            return lambda x: isinstance(x, str)
        elif condition == FilterCondition.IS_NUMBER.value:
            return lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
        elif condition == FilterCondition.IS_POSITIVE.value:
            return lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0
        elif condition == FilterCondition.IS_NEGATIVE.value:
            return lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and x < 0
        elif condition == FilterCondition.IS_EVEN.value:
            return lambda x: isinstance(x, int) and not isinstance(x, bool) and x % 2 == 0
        elif condition == FilterCondition.IS_ODD.value:
            return lambda x: isinstance(x, int) and not isinstance(x, bool) and x % 2 != 0
        elif condition == FilterCondition.CUSTOM.value:
            # Create a function from the custom expression
            if not self._custom_expression:
                return lambda x: True
            try:
                # Compile the expression for safe evaluation
                compiled = compile(self._custom_expression, "<filter>", "eval")

                def custom_filter(x: Any) -> bool:
                    try:
                        return bool(eval(compiled, {"__builtins__": {}}, {self._variable_name: x}))
                    except Exception:
                        logger.debug("Filter expression error", exc_info=True)
                        return False

                return custom_filter
            except SyntaxError:
                logger.debug("Filter expression error", exc_info=True)
                return lambda x: False
        else:
            # Default to truthy
            return lambda x: bool(x)

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate filter condition
        valid_conditions = [c.value for c in FilterCondition]
        if self._filter_condition not in valid_conditions:
            errors.append(f"Invalid filter condition: {self._filter_condition}")

        # Validate custom expression if in custom mode
        if self._filter_condition == FilterCondition.CUSTOM.value:
            if self._custom_expression:
                try:
                    compile(self._custom_expression, "<filter>", "eval")
                except SyntaxError as e:
                    errors.append(f"Invalid custom expression: {e}")

        # Validate variable name
        if not self._variable_name.isidentifier():
            errors.append(f"Invalid variable name: {self._variable_name}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the list filter operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   Must contain 'list'.

        Returns:
            Dictionary with 'result' containing the filtered list,
            'rejected' containing rejected elements, and 'count'.

        Raises:
            ValueError: If required inputs are missing.
            TypeError: If the list input is not a list.
        """
        source_list = inputs.get("list")

        if source_list is None:
            raise ValueError("No list provided to list filter node")

        if not isinstance(source_list, list):
            raise TypeError(
                f"List filter requires a list, got {type(source_list).__name__}"
            )

        filter_func = self._get_filter_function()

        result_list: List[Any] = []
        rejected_list: List[Any] = []

        for item in source_list:
            try:
                if filter_func(item):
                    result_list.append(item)
                else:
                    rejected_list.append(item)
            except Exception:
                # If evaluation fails, reject the item
                rejected_list.append(item)

        return {
            "result": result_list,
            "rejected": rejected_list,
            "count": len(result_list),
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get list filter node specific properties for serialization.

        Returns:
            Dictionary containing the node's configuration.
        """
        return {
            "filter_condition": self._filter_condition,
            "custom_expression": self._custom_expression,
            "variable_name": self._variable_name,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load list filter node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._filter_condition = properties.get("filter_condition", "truthy")
        self._custom_expression = properties.get("custom_expression", "")
        self._variable_name = properties.get("variable_name", "x")

    def __repr__(self) -> str:
        """Get a detailed string representation of the list filter node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"condition={self._filter_condition}, "
            f"state={self._execution_state.name})"
        )
