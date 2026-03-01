"""
List Map node model for transforming list elements in VisualPython.

This module defines the ListMapNode class, which enables transforming
each element of a list using a predefined or custom transformation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class MapTransformation(Enum):
    """Predefined transformations for common use cases."""

    TO_STRING = "to_string"
    """Convert each element to a string."""

    TO_INT = "to_int"
    """Convert each element to an integer."""

    TO_FLOAT = "to_float"
    """Convert each element to a float."""

    TO_BOOL = "to_bool"
    """Convert each element to a boolean."""

    TO_UPPER = "to_upper"
    """Convert string elements to uppercase."""

    TO_LOWER = "to_lower"
    """Convert string elements to lowercase."""

    STRIP = "strip"
    """Strip whitespace from string elements."""

    ABS = "abs"
    """Get absolute value of numeric elements."""

    NEGATE = "negate"
    """Negate numeric elements."""

    DOUBLE = "double"
    """Double numeric elements."""

    SQUARE = "square"
    """Square numeric elements."""

    LENGTH = "length"
    """Get length of iterable elements."""

    CUSTOM = "custom"
    """Use a custom transformation expression."""


class ListMapNode(BaseNode):
    """
    A node that transforms each element of a list.

    The ListMapNode enables visual list transformation by applying a predefined
    or custom transformation to each element, producing a new list with the
    transformed values.

    The node has:
    - An input for the source list
    - An output for the transformed list

    Attributes:
        transformation: The predefined transformation to use.
        custom_expression: Custom Python expression for transformation (when CUSTOM).
        variable_name: The variable name used in custom expressions (default: "x").
        skip_errors: If True, skip elements that cause errors during transformation.

    Example:
        >>> node = ListMapNode(transformation="double")
        >>> result = node.execute({"list": [1, 2, 3]})
        >>> result["result"]  # [2, 4, 6]
    """

    # Class-level metadata
    node_type: str = "list_map"
    """Unique identifier for list map nodes."""

    node_category: str = "List Operations"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color to distinguish list operation nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        transformation: str = "to_string",
        custom_expression: str = "",
        variable_name: str = "x",
        skip_errors: bool = False,
    ) -> None:
        """
        Initialize a new ListMapNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'List Map'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            transformation: The transformation to apply (from MapTransformation enum values).
            custom_expression: Custom Python expression when transformation is 'custom'.
            variable_name: Variable name for custom expressions.
            skip_errors: If True, skip elements that cause errors during transformation.
        """
        self._transformation: str = transformation
        self._custom_expression: str = custom_expression
        self._variable_name: str = variable_name
        self._skip_errors: bool = skip_errors
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the list map node.

        The list map node has:
        - exec_in: Execution flow input
        - list: The source list to transform
        - exec_out: Execution flow output
        - result: The transformed list
        - errors: List of elements that failed to transform (if skip_errors is True)
        - count: The number of successfully transformed elements
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
            description="The source list to transform",
            required=True,
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Transformed result list output
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.LIST,
            description="The transformed list",
        ))

        # Error elements output
        self.add_output_port(OutputPort(
            name="errors",
            port_type=PortType.LIST,
            description="Elements that failed to transform (when skip_errors is True)",
        ))

        # Count of transformed elements
        self.add_output_port(OutputPort(
            name="count",
            port_type=PortType.INTEGER,
            description="The number of successfully transformed elements",
        ))

    @property
    def transformation(self) -> str:
        """Get the transformation type."""
        return self._transformation

    @transformation.setter
    def transformation(self, value: str) -> None:
        """Set the transformation type."""
        self._transformation = value

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

    @property
    def skip_errors(self) -> bool:
        """Get whether errors should be skipped."""
        return self._skip_errors

    @skip_errors.setter
    def skip_errors(self, value: bool) -> None:
        """Set whether errors should be skipped."""
        self._skip_errors = value

    def _get_transform_function(self) -> Callable[[Any], Any]:
        """
        Get the transformation function based on the current setting.

        Returns:
            A callable that takes an element and returns the transformed value.
        """
        transformation = self._transformation

        if transformation == MapTransformation.TO_STRING.value:
            return str
        elif transformation == MapTransformation.TO_INT.value:
            return int
        elif transformation == MapTransformation.TO_FLOAT.value:
            return float
        elif transformation == MapTransformation.TO_BOOL.value:
            return bool
        elif transformation == MapTransformation.TO_UPPER.value:
            return lambda x: str(x).upper()
        elif transformation == MapTransformation.TO_LOWER.value:
            return lambda x: str(x).lower()
        elif transformation == MapTransformation.STRIP.value:
            return lambda x: str(x).strip()
        elif transformation == MapTransformation.ABS.value:
            return abs
        elif transformation == MapTransformation.NEGATE.value:
            return lambda x: -x
        elif transformation == MapTransformation.DOUBLE.value:
            return lambda x: x * 2
        elif transformation == MapTransformation.SQUARE.value:
            return lambda x: x * x
        elif transformation == MapTransformation.LENGTH.value:
            return len
        elif transformation == MapTransformation.CUSTOM.value:
            # Create a function from the custom expression
            if not self._custom_expression:
                return lambda x: x
            try:
                # Compile the expression for safe evaluation
                compiled = compile(self._custom_expression, "<map>", "eval")

                def custom_transform(x: Any) -> Any:
                    return eval(compiled, {"__builtins__": {}}, {self._variable_name: x})

                return custom_transform
            except SyntaxError:
                logger.debug("Map expression syntax error", exc_info=True)
                return lambda x: x
        else:
            # Default to identity
            return lambda x: x

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate transformation
        valid_transformations = [t.value for t in MapTransformation]
        if self._transformation not in valid_transformations:
            errors.append(f"Invalid transformation: {self._transformation}")

        # Validate custom expression if in custom mode
        if self._transformation == MapTransformation.CUSTOM.value:
            if self._custom_expression:
                try:
                    compile(self._custom_expression, "<map>", "eval")
                except SyntaxError as e:
                    errors.append(f"Invalid custom expression: {e}")

        # Validate variable name
        if not self._variable_name.isidentifier():
            errors.append(f"Invalid variable name: {self._variable_name}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the list map operation.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   Must contain 'list'.

        Returns:
            Dictionary with 'result' containing the transformed list,
            'errors' containing failed elements, and 'count'.

        Raises:
            ValueError: If required inputs are missing.
            TypeError: If the list input is not a list.
        """
        source_list = inputs.get("list")

        if source_list is None:
            raise ValueError("No list provided to list map node")

        if not isinstance(source_list, list):
            raise TypeError(
                f"List map requires a list, got {type(source_list).__name__}"
            )

        transform_func = self._get_transform_function()

        result_list: List[Any] = []
        error_list: List[Any] = []

        for item in source_list:
            try:
                transformed = transform_func(item)
                result_list.append(transformed)
            except Exception as e:
                if self._skip_errors:
                    error_list.append(item)
                else:
                    raise ValueError(
                        f"Failed to transform element '{item}': {e}"
                    ) from e

        return {
            "result": result_list,
            "errors": error_list,
            "count": len(result_list),
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get list map node specific properties for serialization.

        Returns:
            Dictionary containing the node's configuration.
        """
        return {
            "transformation": self._transformation,
            "custom_expression": self._custom_expression,
            "variable_name": self._variable_name,
            "skip_errors": self._skip_errors,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load list map node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._transformation = properties.get("transformation", "to_string")
        self._custom_expression = properties.get("custom_expression", "")
        self._variable_name = properties.get("variable_name", "x")
        self._skip_errors = properties.get("skip_errors", False)

    def __repr__(self) -> str:
        """Get a detailed string representation of the list map node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"transformation={self._transformation}, "
            f"skip_errors={self._skip_errors}, "
            f"state={self._execution_state.name})"
        )
