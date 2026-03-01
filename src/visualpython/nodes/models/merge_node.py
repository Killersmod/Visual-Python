"""
Merge node model for converging multiple execution paths in VisualPython.

This module defines the MergeNode class, which enables multiple execution
paths to converge into a single continuation point in visual scripts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class MergeNode(BaseNode):
    """
    A node that converges multiple execution paths into a single continuation point.

    The MergeNode enables path convergence after branching operations like if/else
    statements. It accepts multiple incoming execution flows and continues execution
    through a single output path when any of the inputs are triggered.

    The node supports configurable merge strategies:
    1. First-in: Execute immediately when the first input path arrives (default)
    2. Wait-for-all: Wait until all connected inputs have been triggered before
       continuing (useful for synchronizing parallel paths)

    The node has:
    - Multiple execution flow inputs (exec_in_1, exec_in_2, exec_in_3)
    - A single execution flow output for continuing after merge
    - Optional data inputs that can be consolidated into the output

    Attributes:
        merge_strategy: The strategy used for merging paths ("first_in" or "wait_all").
        num_inputs: Number of active input ports (2-8).
        triggered_inputs: Set of input port names that have been triggered.

    Example:
        >>> node = MergeNode()
        >>> # After if/else, both branches connect to this merge node
        >>> # Execution continues on exec_out when any branch arrives
    """

    # Class-level metadata
    node_type: str = "merge"
    """Unique identifier for merge nodes."""

    node_category: str = "Control Flow"
    """Category for organizing in the UI."""

    node_color: str = "#607D8B"
    """Blue-grey color to distinguish merge nodes from branch nodes."""

    # Minimum and maximum number of input ports
    MIN_INPUTS: int = 2
    MAX_INPUTS: int = 8

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        merge_strategy: str = "first_in",
        num_inputs: int = 2,
    ) -> None:
        """
        Initialize a new MergeNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Merge'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            merge_strategy: Strategy for merging paths - "first_in" (default) or "wait_all".
            num_inputs: Number of input ports to create (2-8, default 2).
        """
        self._merge_strategy: str = merge_strategy
        self._num_inputs: int = max(self.MIN_INPUTS, min(self.MAX_INPUTS, num_inputs))
        self._triggered_inputs: set = set()
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the merge node.

        The merge node has:
        - Multiple exec_in_N ports for receiving execution flow from different paths
        - exec_out: Single execution flow output after merge
        - Optional data_in ports for consolidating data from different paths
        - merged_data: Output containing data from the triggered input path
        """
        # Create execution flow input ports based on num_inputs
        for i in range(1, self._num_inputs + 1):
            self.add_input_port(InputPort(
                name=f"exec_in_{i}",
                port_type=PortType.FLOW,
                description=f"Execution flow input {i} - connect from branch {i}",
                required=False,
            ))

        # Optional data input ports corresponding to each execution input
        for i in range(1, self._num_inputs + 1):
            self.add_input_port(InputPort(
                name=f"data_in_{i}",
                port_type=PortType.ANY,
                description=f"Optional data input from path {i}",
                required=False,
            ))

        # Single execution flow output - triggered after merge
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output - continues after paths merge",
        ))

        # Optional merged data output
        self.add_output_port(OutputPort(
            name="merged_data",
            port_type=PortType.ANY,
            description="Data from the triggered input path",
        ))

        # Output indicating which path was taken (useful for debugging)
        self.add_output_port(OutputPort(
            name="triggered_path",
            port_type=PortType.INTEGER,
            description="Index of the path that triggered execution (1-based)",
        ))

    @property
    def merge_strategy(self) -> str:
        """Get the merge strategy."""
        return self._merge_strategy

    @merge_strategy.setter
    def merge_strategy(self, value: str) -> None:
        """
        Set the merge strategy.

        Args:
            value: "first_in" or "wait_all"
        """
        if value not in ("first_in", "wait_all"):
            raise ValueError(f"Invalid merge strategy: {value}. Must be 'first_in' or 'wait_all'.")
        self._merge_strategy = value

    @property
    def num_inputs(self) -> int:
        """Get the number of input ports."""
        return self._num_inputs

    @property
    def triggered_inputs(self) -> set:
        """Get the set of triggered input port names."""
        return self._triggered_inputs.copy()

    def add_input_path(self) -> bool:
        """
        Add an additional input path if below maximum.

        Returns:
            True if a new input was added, False if at maximum.
        """
        if self._num_inputs >= self.MAX_INPUTS:
            return False

        self._num_inputs += 1
        new_idx = self._num_inputs

        # Add the new execution input port
        self.add_input_port(InputPort(
            name=f"exec_in_{new_idx}",
            port_type=PortType.FLOW,
            description=f"Execution flow input {new_idx} - connect from branch {new_idx}",
            required=False,
        ))

        # Add corresponding data input port
        self.add_input_port(InputPort(
            name=f"data_in_{new_idx}",
            port_type=PortType.ANY,
            description=f"Optional data input from path {new_idx}",
            required=False,
        ))

        return True

    def remove_input_path(self) -> bool:
        """
        Remove the last input path if above minimum.

        Returns:
            True if an input was removed, False if at minimum.
        """
        if self._num_inputs <= self.MIN_INPUTS:
            return False

        idx = self._num_inputs
        self.remove_input_port(f"exec_in_{idx}")
        self.remove_input_port(f"data_in_{idx}")
        self._num_inputs -= 1

        return True

    def get_connected_input_count(self) -> int:
        """
        Get the number of execution input ports that have connections.

        Returns:
            Count of connected execution input ports.
        """
        count = 0
        for i in range(1, self._num_inputs + 1):
            port = self.get_input_port(f"exec_in_{i}")
            if port and port.is_connected():
                count += 1
        return count

    def trigger_input(self, input_name: str) -> None:
        """
        Mark an input as triggered.

        Args:
            input_name: The name of the triggered input port.
        """
        if input_name.startswith("exec_in_"):
            self._triggered_inputs.add(input_name)

    def is_ready_to_execute(self) -> bool:
        """
        Check if the node is ready to execute based on merge strategy.

        For "first_in" strategy: Returns True if any input is triggered.
        For "wait_all" strategy: Returns True if all connected inputs are triggered.

        Returns:
            True if ready to execute, False otherwise.
        """
        if self._merge_strategy == "first_in":
            return len(self._triggered_inputs) > 0
        else:  # wait_all
            # Check if all connected inputs have been triggered
            for i in range(1, self._num_inputs + 1):
                port = self.get_input_port(f"exec_in_{i}")
                if port and port.is_connected():
                    if f"exec_in_{i}" not in self._triggered_inputs:
                        return False
            return len(self._triggered_inputs) > 0

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate merge strategy
        if self._merge_strategy not in ("first_in", "wait_all"):
            errors.append(f"Invalid merge strategy: {self._merge_strategy}")

        # Validate num_inputs range
        if self._num_inputs < self.MIN_INPUTS or self._num_inputs > self.MAX_INPUTS:
            errors.append(f"Number of inputs must be between {self.MIN_INPUTS} and {self.MAX_INPUTS}")

        # Warn if no inputs are connected (not an error, just informational)
        # This is handled during execution, not validation

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the merge node - consolidate inputs and continue execution.

        The merge node determines which input path triggered the execution
        and passes through any associated data.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary with merged outputs:
            - merged_data: Data from the triggered input path
            - triggered_path: Index of the path that triggered (1-based)
        """
        merged_data: Any = None
        triggered_path: int = 0

        # Determine which path triggered and get its data
        for i in range(1, self._num_inputs + 1):
            exec_port_name = f"exec_in_{i}"
            data_port_name = f"data_in_{i}"

            # Check if this input was part of the execution
            if exec_port_name in self._triggered_inputs:
                triggered_path = i
                merged_data = inputs.get(data_port_name)
                # For first_in strategy, take the first triggered
                if self._merge_strategy == "first_in":
                    break
                # For wait_all, could potentially merge data from all paths
                # For now, take the last one in order

        return {
            "merged_data": merged_data,
            "triggered_path": triggered_path,
        }

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        super().reset_state()
        self._triggered_inputs.clear()

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get merge node specific properties for serialization.

        Returns:
            Dictionary containing the merge strategy and number of inputs.
        """
        return {
            "merge_strategy": self._merge_strategy,
            "num_inputs": self._num_inputs,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load merge node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._merge_strategy = properties.get("merge_strategy", "first_in")
        new_num_inputs = properties.get("num_inputs", 2)

        # Adjust number of input ports if different
        while self._num_inputs < new_num_inputs and self._num_inputs < self.MAX_INPUTS:
            self.add_input_path()
        while self._num_inputs > new_num_inputs and self._num_inputs > self.MIN_INPUTS:
            self.remove_input_path()

    def __repr__(self) -> str:
        """Get a detailed string representation of the merge node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"strategy='{self._merge_strategy}', "
            f"num_inputs={self._num_inputs}, "
            f"triggered={len(self._triggered_inputs)}, "
            f"state={self._execution_state.name})"
        )
