"""
List Reduce node model for reducing lists to single values in VisualPython.

This module defines the ListReduceNode class, which enables reducing
a list to a single value using a predefined or custom reducer function.
"""

from __future__ import annotations

from enum import Enum
from functools import reduce
from typing import Any, Callable, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class ReduceOperation(Enum):
    """Predefined reduce operations for common use cases."""

    SUM = "sum"
    """Sum all numeric elements."""

    PRODUCT = "product"
    """Multiply all numeric elements."""

    MIN = "min"
    """Find the minimum value."""

    MAX = "max"
    """Find the maximum value."""

    COUNT = "count"
    """Count the number of elements."""

    AVERAGE = "average"
    """Calculate the average of numeric elements."""

    JOIN = "join"
    """Join string elements with a separator."""

    FIRST = "first"
    """Get the first element."""

    LAST = "last"
    """Get the last element."""

    ALL = "all"
    """Check if all elements are truthy."""

    ANY = "any"
    """Check if any element is truthy."""

    CONCAT = "concat"
    """Concatenate all elements into a single list (flatten one level)."""

    CUSTOM = "custom"
    """Use a custom reduce expression."""


class ListReduceNode(BaseNode):
    """
    A node that reduces a list to a single value.

    The ListReduceNode enables visual list reduction by applying a predefined
    or custom reduction operation to accumulate elements into a single result.

    The node has:
    - An input for the source list
    - An optional initial value input
    - An output for the reduced result

    Attributes:
        reduce_operation: The predefined operation to use for reduction.
        custom_expression: Custom Python expression for reduction (when CUSTOM).
        accumulator_name: Variable name for the accumulator in custom expressions.
        element_name: Variable name for the current element in custom expressions.
        initial_value: Initial value for the reduction (optional).
        join_separator: Separator for join operations.

    Example:
        >>> node = ListReduceNode(reduce_operation="sum")
        >>> result = node.execute({"list": [1, 2, 3, 4]})
        >>> result["result"]  # 10
    """

    # Class-level metadata
    node_type: str = "list_reduce"
    """Unique identifier for list reduce nodes."""

    node_category: str = "List Operations"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to distinguish list operation nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        reduce_operation: str = "sum",
        custom_expression: str = "",
        accumulator_name: str = "acc",
        element_name: str = "x",
        initial_value: Optional[Any] = None,
        join_separator: str = "",
    ) -> None:
        """
        Initialize a new ListReduceNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'List Reduce'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            reduce_operation: The reduce operation to use (from ReduceOperation enum values).
            custom_expression: Custom Python expression when operation is 'custom'.
            accumulator_name: Variable name for accumulator in custom expressions.
            element_name: Variable name for current element in custom expressions.
            initial_value: Initial value for reduction (optional).
            join_separator: Separator string for join operations.
        """
        self._reduce_operation: str = reduce_operation
        self._custom_expression: str = custom_expression
        self._accumulator_name: str = accumulator_name
        self._element_name: str = element_name
        self._initial_value: Optional[Any] = initial_value
        self._join_separator: str = join_separator
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the list reduce node.

        The list reduce node has:
        - exec_in: Execution flow input
        - list: The source list to reduce
        - initial: Optional initial value for the reduction
        - exec_out: Execution flow output
        - result: The reduced result
        - count: The number of elements processed
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
            description="The source list to reduce",
            required=True,
        ))

        # Optional initial value input
        self.add_input_port(InputPort(
            name="initial",
            port_type=PortType.ANY,
            description="Optional initial value for the reduction",
            required=False,
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Reduced result output
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.ANY,
            description="The reduced result",
        ))

        # Count of processed elements
        self.add_output_port(OutputPort(
            name="count",
            port_type=PortType.INTEGER,
            description="The number of elements processed",
        ))

    @property
    def reduce_operation(self) -> str:
        """Get the reduce operation type."""
        return self._reduce_operation

    @reduce_operation.setter
    def reduce_operation(self, value: str) -> None:
        """Set the reduce operation type."""
        self._reduce_operation = value

    @property
    def custom_expression(self) -> str:
        """Get the custom expression."""
        return self._custom_expression

    @custom_expression.setter
    def custom_expression(self, value: str) -> None:
        """Set the custom expression."""
        self._custom_expression = value

    @property
    def accumulator_name(self) -> str:
        """Get the accumulator variable name."""
        return self._accumulator_name

    @accumulator_name.setter
    def accumulator_name(self, value: str) -> None:
        """Set the accumulator variable name."""
        self._accumulator_name = value

    @property
    def element_name(self) -> str:
        """Get the element variable name."""
        return self._element_name

    @element_name.setter
    def element_name(self, value: str) -> None:
        """Set the element variable name."""
        self._element_name = value

    @property
    def initial_value(self) -> Optional[Any]:
        """Get the initial value."""
        return self._initial_value

    @initial_value.setter
    def initial_value(self, value: Optional[Any]) -> None:
        """Set the initial value."""
        self._initial_value = value

    @property
    def join_separator(self) -> str:
        """Get the join separator."""
        return self._join_separator

    @join_separator.setter
    def join_separator(self, value: str) -> None:
        """Set the join separator."""
        self._join_separator = value

    def _execute_reduction(
        self, source_list: List[Any], initial: Optional[Any]
    ) -> Any:
        """
        Execute the reduction operation.

        Args:
            source_list: The list to reduce.
            initial: Optional initial value.

        Returns:
            The reduced result.
        """
        operation = self._reduce_operation

        if operation == ReduceOperation.SUM.value:
            if initial is not None:
                return sum(source_list, initial)
            return sum(source_list)

        elif operation == ReduceOperation.PRODUCT.value:
            if not source_list:
                return initial if initial is not None else 1
            result = initial if initial is not None else 1
            for item in source_list:
                result *= item
            return result

        elif operation == ReduceOperation.MIN.value:
            if not source_list:
                return initial
            return min(source_list)

        elif operation == ReduceOperation.MAX.value:
            if not source_list:
                return initial
            return max(source_list)

        elif operation == ReduceOperation.COUNT.value:
            return len(source_list)

        elif operation == ReduceOperation.AVERAGE.value:
            if not source_list:
                return initial if initial is not None else 0
            return sum(source_list) / len(source_list)

        elif operation == ReduceOperation.JOIN.value:
            str_list = [str(item) for item in source_list]
            return self._join_separator.join(str_list)

        elif operation == ReduceOperation.FIRST.value:
            if not source_list:
                return initial
            return source_list[0]

        elif operation == ReduceOperation.LAST.value:
            if not source_list:
                return initial
            return source_list[-1]

        elif operation == ReduceOperation.ALL.value:
            return all(source_list)

        elif operation == ReduceOperation.ANY.value:
            return any(source_list)

        elif operation == ReduceOperation.CONCAT.value:
            result: List[Any] = []
            if initial is not None and isinstance(initial, list):
                result = initial.copy()
            for item in source_list:
                if isinstance(item, list):
                    result.extend(item)
                else:
                    result.append(item)
            return result

        elif operation == ReduceOperation.CUSTOM.value:
            if not self._custom_expression:
                return initial if initial is not None else (source_list[0] if source_list else None)

            try:
                compiled = compile(self._custom_expression, "<reduce>", "eval")

                def reducer(acc: Any, x: Any) -> Any:
                    return eval(
                        compiled,
                        {"__builtins__": {}},
                        {self._accumulator_name: acc, self._element_name: x}
                    )

                if initial is not None:
                    return reduce(reducer, source_list, initial)
                elif source_list:
                    return reduce(reducer, source_list)
                else:
                    return None

            except (SyntaxError, TypeError):
                logger.debug("Reduce expression error", exc_info=True)
                return initial

        else:
            # Default to sum
            return sum(source_list) if source_list else (initial if initial is not None else 0)

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate reduce operation
        valid_operations = [op.value for op in ReduceOperation]
        if self._reduce_operation not in valid_operations:
            errors.append(f"Invalid reduce operation: {self._reduce_operation}")

        # Validate custom expression if in custom mode
        if self._reduce_operation == ReduceOperation.CUSTOM.value:
            if self._custom_expression:
                try:
                    compile(self._custom_expression, "<reduce>", "eval")
                except SyntaxError as e:
                    errors.append(f"Invalid custom expression: {e}")

        # Validate variable names
        if not self._accumulator_name.isidentifier():
            errors.append(f"Invalid accumulator name: {self._accumulator_name}")
        if not self._element_name.isidentifier():
            errors.append(f"Invalid element name: {self._element_name}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the list reduce operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   Must contain 'list'. Optionally contains 'initial'.

        Returns:
            Dictionary with 'result' containing the reduced value and 'count'.

        Raises:
            ValueError: If required inputs are missing or reduction fails.
            TypeError: If the list input is not a list.
        """
        source_list = inputs.get("list")
        initial = inputs.get("initial", self._initial_value)

        if source_list is None:
            raise ValueError("No list provided to list reduce node")

        if not isinstance(source_list, list):
            raise TypeError(
                f"List reduce requires a list, got {type(source_list).__name__}"
            )

        result = self._execute_reduction(source_list, initial)

        return {
            "result": result,
            "count": len(source_list),
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get list reduce node specific properties for serialization.

        Returns:
            Dictionary containing the node's configuration.
        """
        return {
            "reduce_operation": self._reduce_operation,
            "custom_expression": self._custom_expression,
            "accumulator_name": self._accumulator_name,
            "element_name": self._element_name,
            "initial_value": self._initial_value,
            "join_separator": self._join_separator,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load list reduce node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._reduce_operation = properties.get("reduce_operation", "sum")
        self._custom_expression = properties.get("custom_expression", "")
        self._accumulator_name = properties.get("accumulator_name", "acc")
        self._element_name = properties.get("element_name", "x")
        self._initial_value = properties.get("initial_value")
        self._join_separator = properties.get("join_separator", "")

    def __repr__(self) -> str:
        """Get a detailed string representation of the list reduce node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"operation={self._reduce_operation}, "
            f"state={self._execution_state.name})"
        )
