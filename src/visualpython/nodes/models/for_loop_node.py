"""
For Loop node model for iterating over collections in VisualPython.

This module defines the ForLoopNode class, which enables iteration over
iterable objects (lists, tuples, ranges, etc.) in visual scripts.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class ForLoopNode(BaseNode):
    """
    A node that iterates over an iterable collection.

    The ForLoopNode enables visual iteration similar to Python's for loop.
    It takes an iterable as input and executes the loop body for each element,
    providing the current element and iteration index to connected nodes.

    The node has:
    - An input for the iterable collection to iterate over
    - An output for the current iteration item (available to loop body nodes)
    - An output for the current iteration index
    - Flow connections for loop body execution and completion

    Attributes:
        iteration_variable: Name of the iteration variable (for display/code generation).
        current_index: The current iteration index during execution.
        current_item: The current item being iterated during execution.
        is_iterating: Whether the loop is currently mid-iteration.

    Example:
        >>> node = ForLoopNode(iteration_variable="item")
        >>> node.set_input("iterable", [1, 2, 3])
        >>> # During execution, outputs 'item' and 'index' for each iteration
    """

    # Class-level metadata
    node_type: str = "for_loop"
    """Unique identifier for for loop nodes."""

    node_category: str = "Control Flow"
    """Category for organizing in the UI."""

    node_color: str = "#FF9800"
    """Orange color to distinguish loop nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        iteration_variable: str = "item",
    ) -> None:
        """
        Initialize a new ForLoopNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'For Loop'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            iteration_variable: The name of the iteration variable (default: "item").
        """
        self._iteration_variable: str = iteration_variable
        self._current_index: int = 0
        self._current_item: Any = None
        self._is_iterating: bool = False
        self._iteration_count: int = 0
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the for loop node.

        The for loop node has:
        - exec_in: Execution flow input to start the loop
        - iterable: The collection to iterate over
        - loop_body: Execution flow output for each iteration (loop body)
        - completed: Execution flow output when loop finishes all iterations
        - item: Current iteration item output
        - index: Current iteration index output
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input - triggers the loop to start",
            required=False,
        ))

        # Iterable input - the collection to iterate over
        self.add_input_port(InputPort(
            name="iterable",
            port_type=PortType.ANY,
            description="The iterable collection to loop over (list, tuple, range, etc.)",
            required=True,
        ))

        # Execution flow output for loop body - triggered for each iteration
        self.add_output_port(OutputPort(
            name="loop_body",
            port_type=PortType.FLOW,
            description="Execution flow for loop body - triggered for each iteration",
        ))

        # Execution flow output when loop completes
        self.add_output_port(OutputPort(
            name="completed",
            port_type=PortType.FLOW,
            description="Execution flow when loop finishes all iterations",
        ))

        # Current item output - the value of the current iteration
        self.add_output_port(OutputPort(
            name="item",
            port_type=PortType.ANY,
            description="The current item in the iteration",
        ))

        # Current index output - the index of the current iteration (0-based)
        self.add_output_port(OutputPort(
            name="index",
            port_type=PortType.INTEGER,
            description="The current iteration index (0-based)",
        ))

    @property
    def iteration_variable(self) -> str:
        """Get the iteration variable name."""
        return self._iteration_variable

    @iteration_variable.setter
    def iteration_variable(self, value: str) -> None:
        """
        Set the iteration variable name.

        Args:
            value: The name for the iteration variable.
        """
        self._iteration_variable = value

    @property
    def current_index(self) -> int:
        """Get the current iteration index."""
        return self._current_index

    @property
    def current_item(self) -> Any:
        """Get the current iteration item."""
        return self._current_item

    @property
    def is_iterating(self) -> bool:
        """Check if the loop is currently iterating."""
        return self._is_iterating

    @property
    def iteration_count(self) -> int:
        """Get the total number of iterations completed."""
        return self._iteration_count

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate iteration variable name
        if not self._iteration_variable:
            errors.append("Iteration variable name cannot be empty")
        elif not self._iteration_variable.isidentifier():
            errors.append(
                f"Iteration variable '{self._iteration_variable}' is not a valid Python identifier"
            )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the for loop node.

        This method prepares the loop for iteration. The actual iteration
        is handled by the execution engine which calls iterate() repeatedly.

        For data model purposes, this returns the initial state of the loop
        with the first iteration's values (or empty if the iterable is empty).

        Args:
            inputs: Dictionary mapping input port names to their values.
                   Must contain 'iterable' with an iterable object.

        Returns:
            Dictionary with 'item' and 'index' for the first iteration,
            or empty outputs if the iterable is empty.

        Raises:
            TypeError: If the input is not iterable.
            ValueError: If no iterable is provided.
        """
        iterable = inputs.get("iterable")

        if iterable is None:
            raise ValueError("No iterable provided to for loop")

        # Verify the input is iterable
        try:
            iterator = iter(iterable)
        except TypeError:
            raise TypeError(
                f"For loop input must be iterable, got {type(iterable).__name__}"
            )

        # Reset iteration state
        self._current_index = 0
        self._current_item = None
        self._is_iterating = False
        self._iteration_count = 0

        # Try to get the first item
        try:
            self._current_item = next(iterator)
            self._is_iterating = True
            return {
                "item": self._current_item,
                "index": self._current_index,
            }
        except StopIteration:
            # Empty iterable - loop completes immediately
            self._is_iterating = False
            return {
                "item": None,
                "index": 0,
            }

    def iterate(self, iterable: Any) -> Iterator[Dict[str, Any]]:
        """
        Generator that yields outputs for each iteration.

        This method is used by the execution engine to iterate through
        all elements of the iterable, yielding the current item and index
        for each iteration.

        Args:
            iterable: The iterable collection to loop over.

        Yields:
            Dictionary with 'item' (current element) and 'index' (iteration index).

        Raises:
            TypeError: If the input is not iterable.
        """
        self._is_iterating = True
        self._iteration_count = 0

        try:
            for index, item in enumerate(iterable):
                self._current_index = index
                self._current_item = item
                self._iteration_count = index + 1
                yield {
                    "item": item,
                    "index": index,
                }
        finally:
            self._is_iterating = False

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        super().reset_state()
        self._current_index = 0
        self._current_item = None
        self._is_iterating = False
        self._iteration_count = 0

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get for loop node specific properties for serialization.

        Returns:
            Dictionary containing the iteration variable name.
        """
        return {
            "iteration_variable": self._iteration_variable,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load for loop node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._iteration_variable = properties.get("iteration_variable", "item")

    def __repr__(self) -> str:
        """Get a detailed string representation of the for loop node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"iteration_var='{self._iteration_variable}', "
            f"iterating={self._is_iterating}, "
            f"index={self._current_index}, "
            f"state={self._execution_state.name})"
        )
