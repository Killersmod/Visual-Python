"""
Data aggregation node model for combining data from multiple sources in VisualPython.

This module defines the DataAggregationNode class, which provides flexible strategies
for combining data from multiple input paths including collecting into lists,
merging dictionaries, concatenating strings, and summing numbers.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class AggregationStrategy(Enum):
    """Available strategies for aggregating data from multiple inputs."""

    COLLECT_LIST = "collect_list"
    """Collect all non-None inputs into a list."""

    MERGE_DICTS = "merge_dicts"
    """Merge multiple dictionaries (later values override earlier ones)."""

    MERGE_DICTS_DEEP = "merge_dicts_deep"
    """Deep merge multiple dictionaries (recursively merge nested dicts)."""

    CONCATENATE_STRINGS = "concatenate_strings"
    """Concatenate string inputs with an optional separator."""

    SUM_NUMBERS = "sum_numbers"
    """Sum all numeric inputs."""

    FIRST_NON_NULL = "first_non_null"
    """Return the first non-None input value."""

    LAST_NON_NULL = "last_non_null"
    """Return the last non-None input value."""


class DataAggregationNode(BaseNode):
    """
    A node that combines data from multiple input sources using flexible strategies.

    The DataAggregationNode provides various strategies for merging data:
    - collect_list: Gather all inputs into a list
    - merge_dicts: Merge multiple dictionaries (shallow merge, last wins)
    - merge_dicts_deep: Deep merge dictionaries (recursively merge nested dicts)
    - concatenate_strings: Join strings with a configurable separator
    - sum_numbers: Sum numeric values
    - first_non_null: Return the first non-None value
    - last_non_null: Return the last non-None value

    The node has:
    - Single execution flow input and output
    - Configurable number of data inputs (2-8)
    - Optional separator for string concatenation
    - Result output with the aggregated data
    - Count output indicating how many inputs were aggregated

    Attributes:
        aggregation_strategy: The strategy to use for combining inputs.
        num_inputs: Number of data input ports (2-8).
        separator: Separator string for concatenate_strings strategy.
        skip_none: Whether to skip None values when aggregating.

    Example:
        >>> node = DataAggregationNode(aggregation_strategy="collect_list")
        >>> result = node.execute({"data_in_1": "a", "data_in_2": "b"})
        >>> result["result"]
        ['a', 'b']
    """

    # Class-level metadata
    node_type: str = "data_aggregation"
    """Unique identifier for data aggregation nodes."""

    node_category: str = "Data Processing"
    """Category for organizing in the UI."""

    node_color: str = "#9C27B0"
    """Purple color to distinguish data processing nodes."""

    # Input limits
    MIN_INPUTS: int = 2
    MAX_INPUTS: int = 8

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        aggregation_strategy: str = "collect_list",
        num_inputs: int = 2,
        separator: str = "",
        skip_none: bool = True,
    ) -> None:
        """
        Initialize a new DataAggregationNode instance.

        Args:
            node_id: Optional unique identifier.
            name: Optional display name.
            position: Optional initial position.
            aggregation_strategy: Strategy for combining inputs (default: "collect_list").
            num_inputs: Number of data input ports (2-8, default: 2).
            separator: Separator for string concatenation (default: "").
            skip_none: Whether to skip None values (default: True).
        """
        self._aggregation_strategy: str = aggregation_strategy
        self._num_inputs: int = max(self.MIN_INPUTS, min(self.MAX_INPUTS, num_inputs))
        self._separator: str = separator
        self._skip_none: bool = skip_none
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the data aggregation node.

        The node has:
        - exec_in: Execution flow input
        - data_in_1 through data_in_N: Data inputs to aggregate
        - separator: Optional separator for string concatenation
        - exec_out: Execution flow output
        - result: The aggregated result
        - count: Number of inputs that were aggregated
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))

        # Data input ports based on num_inputs
        for i in range(1, self._num_inputs + 1):
            self.add_input_port(InputPort(
                name=f"data_in_{i}",
                port_type=PortType.ANY,
                description=f"Data input {i} to aggregate",
                required=False,
            ))

        # Optional separator input for string concatenation
        self.add_input_port(InputPort(
            name="separator",
            port_type=PortType.STRING,
            description="Separator for string concatenation (optional)",
            required=False,
            default_value="",
        ))

        # Execution flow output
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Result output - type depends on strategy but defaults to ANY
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.ANY,
            description="The aggregated result",
        ))

        # Count output - number of inputs aggregated
        self.add_output_port(OutputPort(
            name="count",
            port_type=PortType.INTEGER,
            description="Number of inputs that were aggregated",
        ))

    @property
    def aggregation_strategy(self) -> str:
        """Get the current aggregation strategy."""
        return self._aggregation_strategy

    @aggregation_strategy.setter
    def aggregation_strategy(self, value: str) -> None:
        """
        Set the aggregation strategy.

        Args:
            value: One of the valid AggregationStrategy values.

        Raises:
            ValueError: If the strategy is not valid.
        """
        valid_strategies = [s.value for s in AggregationStrategy]
        if value not in valid_strategies:
            raise ValueError(
                f"Invalid aggregation strategy: {value}. "
                f"Must be one of: {', '.join(valid_strategies)}"
            )
        self._aggregation_strategy = value

    @property
    def num_inputs(self) -> int:
        """Get the number of data input ports."""
        return self._num_inputs

    @property
    def separator(self) -> str:
        """Get the separator for string concatenation."""
        return self._separator

    @separator.setter
    def separator(self, value: str) -> None:
        """Set the separator for string concatenation."""
        self._separator = value

    @property
    def skip_none(self) -> bool:
        """Get whether to skip None values."""
        return self._skip_none

    @skip_none.setter
    def skip_none(self, value: bool) -> None:
        """Set whether to skip None values."""
        self._skip_none = value

    def add_input_slot(self) -> bool:
        """
        Add an additional data input slot if below maximum.

        Returns:
            True if a new input was added, False if at maximum.
        """
        if self._num_inputs >= self.MAX_INPUTS:
            return False

        self._num_inputs += 1
        new_idx = self._num_inputs

        self.add_input_port(InputPort(
            name=f"data_in_{new_idx}",
            port_type=PortType.ANY,
            description=f"Data input {new_idx} to aggregate",
            required=False,
        ))

        return True

    def remove_input_slot(self) -> bool:
        """
        Remove the last data input slot if above minimum.

        Returns:
            True if an input was removed, False if at minimum.
        """
        if self._num_inputs <= self.MIN_INPUTS:
            return False

        idx = self._num_inputs
        self.remove_input_port(f"data_in_{idx}")
        self._num_inputs -= 1

        return True

    def _collect_inputs(self, inputs: Dict[str, Any]) -> List[Any]:
        """
        Collect all data inputs into a list.

        Args:
            inputs: Dictionary of input values.

        Returns:
            List of input values (optionally excluding None values).
        """
        values = []
        for i in range(1, self._num_inputs + 1):
            port_name = f"data_in_{i}"
            if port_name in inputs:
                value = inputs[port_name]
                if not self._skip_none or value is not None:
                    values.append(value)
        return values

    def _deep_merge_dicts(self, base: Dict, update: Dict) -> Dict:
        """
        Deep merge two dictionaries.

        Args:
            base: The base dictionary.
            update: The dictionary to merge into base.

        Returns:
            A new dictionary with deeply merged values.
        """
        result = base.copy()
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge_dicts(result[key], value)
            else:
                result[key] = value
        return result

    def _aggregate_collect_list(self, values: List[Any]) -> List[Any]:
        """Collect all values into a list."""
        return values

    def _aggregate_merge_dicts(self, values: List[Any], deep: bool = False) -> Dict:
        """
        Merge multiple dictionaries.

        Args:
            values: List of dictionaries to merge.
            deep: Whether to perform deep merge.

        Returns:
            Merged dictionary.

        Raises:
            TypeError: If any value is not a dictionary.
        """
        result: Dict = {}
        for value in values:
            if value is None:
                continue
            if not isinstance(value, dict):
                raise TypeError(
                    f"merge_dicts strategy requires dictionary inputs, got {type(value).__name__}"
                )
            if deep:
                result = self._deep_merge_dicts(result, value)
            else:
                result.update(value)
        return result

    def _aggregate_concatenate_strings(
        self, values: List[Any], separator: str
    ) -> str:
        """
        Concatenate values as strings.

        Args:
            values: List of values to concatenate.
            separator: String to use between values.

        Returns:
            Concatenated string.
        """
        string_values = [str(v) for v in values if v is not None]
        return separator.join(string_values)

    def _aggregate_sum_numbers(self, values: List[Any]) -> float:
        """
        Sum numeric values.

        Args:
            values: List of numeric values to sum.

        Returns:
            Sum of all values.

        Raises:
            TypeError: If any value is not numeric.
        """
        total = 0.0
        for value in values:
            if value is None:
                continue
            if not isinstance(value, (int, float)):
                raise TypeError(
                    f"sum_numbers strategy requires numeric inputs, got {type(value).__name__}"
                )
            total += value
        return total

    def _aggregate_first_non_null(self, values: List[Any]) -> Any:
        """Return the first non-None value."""
        for value in values:
            if value is not None:
                return value
        return None

    def _aggregate_last_non_null(self, values: List[Any]) -> Any:
        """Return the last non-None value."""
        result = None
        for value in values:
            if value is not None:
                result = value
        return result

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate strategy
        valid_strategies = [s.value for s in AggregationStrategy]
        if self._aggregation_strategy not in valid_strategies:
            errors.append(
                f"Invalid aggregation strategy: {self._aggregation_strategy}. "
                f"Must be one of: {', '.join(valid_strategies)}"
            )

        # Validate num_inputs range
        if self._num_inputs < self.MIN_INPUTS or self._num_inputs > self.MAX_INPUTS:
            errors.append(
                f"Number of inputs must be between {self.MIN_INPUTS} and {self.MAX_INPUTS}"
            )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the data aggregation with the configured strategy.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary with:
            - result: The aggregated result
            - count: Number of inputs that were aggregated

        Raises:
            TypeError: If input types don't match the strategy requirements.
            ValueError: If the aggregation strategy is invalid.
        """
        # Collect all input values
        values = self._collect_inputs(inputs)

        # Get separator from inputs or use configured value
        separator = inputs.get("separator", self._separator)
        if separator is None:
            separator = ""

        # Apply the aggregation strategy
        strategy = self._aggregation_strategy
        result: Any = None
        count = len(values)

        if strategy == AggregationStrategy.COLLECT_LIST.value:
            result = self._aggregate_collect_list(values)

        elif strategy == AggregationStrategy.MERGE_DICTS.value:
            result = self._aggregate_merge_dicts(values, deep=False)

        elif strategy == AggregationStrategy.MERGE_DICTS_DEEP.value:
            result = self._aggregate_merge_dicts(values, deep=True)

        elif strategy == AggregationStrategy.CONCATENATE_STRINGS.value:
            result = self._aggregate_concatenate_strings(values, separator)

        elif strategy == AggregationStrategy.SUM_NUMBERS.value:
            result = self._aggregate_sum_numbers(values)

        elif strategy == AggregationStrategy.FIRST_NON_NULL.value:
            result = self._aggregate_first_non_null(values)
            count = 1 if result is not None else 0

        elif strategy == AggregationStrategy.LAST_NON_NULL.value:
            result = self._aggregate_last_non_null(values)
            count = 1 if result is not None else 0

        else:
            raise ValueError(f"Unknown aggregation strategy: {strategy}")

        return {
            "result": result,
            "count": count,
        }

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        super().reset_state()

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get data aggregation node specific properties for serialization.

        Returns:
            Dictionary containing strategy, num_inputs, separator, and skip_none.
        """
        return {
            "aggregation_strategy": self._aggregation_strategy,
            "num_inputs": self._num_inputs,
            "separator": self._separator,
            "skip_none": self._skip_none,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load data aggregation node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._aggregation_strategy = properties.get("aggregation_strategy", "collect_list")
        self._separator = properties.get("separator", "")
        self._skip_none = properties.get("skip_none", True)

        new_num_inputs = properties.get("num_inputs", 2)

        # Adjust number of input ports if different
        while self._num_inputs < new_num_inputs and self._num_inputs < self.MAX_INPUTS:
            self.add_input_slot()
        while self._num_inputs > new_num_inputs and self._num_inputs > self.MIN_INPUTS:
            self.remove_input_slot()

    def __repr__(self) -> str:
        """Get a detailed string representation of the data aggregation node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"strategy='{self._aggregation_strategy}', "
            f"num_inputs={self._num_inputs}, "
            f"skip_none={self._skip_none}, "
            f"state={self._execution_state.name})"
        )
