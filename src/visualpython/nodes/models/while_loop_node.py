"""
While Loop node model for condition-based iteration in VisualPython.

This module defines the WhileLoopNode class, which enables condition-based
iteration where the loop continues as long as a condition evaluates to True.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, TYPE_CHECKING

from visualpython.compiler.ast_validator import validate_condition_code
from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class WhileLoopNode(BaseNode):
    """
    A node that iterates while a condition remains true.

    The WhileLoopNode enables visual iteration similar to Python's while loop.
    It evaluates a condition before each iteration and continues executing the
    loop body as long as the condition is True.

    The node supports two modes of condition evaluation:
    1. Direct boolean input: A boolean value is passed to the 'condition' port
    2. Code-based evaluation: Python code that evaluates to a boolean is stored
       in the condition_code property and executed each iteration

    The node has:
    - An execution flow input to start the loop
    - A condition input for direct boolean values
    - A loop_body flow output for each iteration
    - A completed flow output when the loop finishes
    - An iteration_count output showing the current iteration number

    Attributes:
        condition_code: Optional Python code string for complex condition evaluation.
        max_iterations: Safety limit to prevent infinite loops (0 = no limit).
        current_iteration: The current iteration count during execution.
        is_iterating: Whether the loop is currently mid-iteration.

    Example:
        >>> node = WhileLoopNode(condition_code="count < 10")
        >>> # Loop executes while count < 10
    """

    # Class-level metadata
    node_type: str = "while_loop"
    """Unique identifier for while loop nodes."""

    node_category: str = "Control Flow"
    """Category for organizing in the UI."""

    node_color: str = "#FF9800"
    """Orange color to distinguish loop nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        condition_code: str = "",
        max_iterations: int = 10000,
    ) -> None:
        """
        Initialize a new WhileLoopNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'While Loop'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            condition_code: Optional Python code for evaluating the loop condition.
                           If empty, the 'condition' input port value is used directly.
            max_iterations: Safety limit to prevent infinite loops. Default is 10000.
                           Set to 0 for no limit (use with caution).
        """
        self._condition_code: str = condition_code
        self._max_iterations: int = max_iterations
        self._current_iteration: int = 0
        self._is_iterating: bool = False
        self._last_condition_result: Optional[bool] = None
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the while loop node.

        The while loop node has:
        - exec_in: Execution flow input to start the loop
        - condition: Boolean condition input (used if condition_code is empty)
        - loop_body: Execution flow output for each iteration (loop body)
        - completed: Execution flow output when loop finishes (condition becomes False)
        - iteration_count: Current iteration number output
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input - triggers the loop to start",
            required=False,
        ))

        # Condition input - the boolean value to evaluate each iteration
        self.add_input_port(InputPort(
            name="condition",
            port_type=PortType.BOOLEAN,
            description="Boolean condition to evaluate (used if condition_code is empty)",
            required=False,
            default_value=False,
        ))

        # Additional value input for use in condition_code evaluation
        self.add_input_port(InputPort(
            name="value",
            port_type=PortType.ANY,
            description="Optional value input accessible in condition_code as 'value'",
            required=False,
        ))

        # Execution flow output for loop body - triggered for each iteration
        self.add_output_port(OutputPort(
            name="loop_body",
            port_type=PortType.FLOW,
            description="Execution flow for loop body - triggered while condition is True",
        ))

        # Execution flow output when loop completes
        self.add_output_port(OutputPort(
            name="completed",
            port_type=PortType.FLOW,
            description="Execution flow when loop finishes (condition becomes False)",
        ))

        # Current iteration count output
        self.add_output_port(OutputPort(
            name="iteration_count",
            port_type=PortType.INTEGER,
            description="The current iteration count (0-based)",
        ))

    @property
    def condition_code(self) -> str:
        """Get the condition code string."""
        return self._condition_code

    @condition_code.setter
    def condition_code(self, value: str) -> None:
        """
        Set the condition code string.

        Args:
            value: Python code that evaluates to a boolean.
        """
        self._condition_code = value

    @property
    def max_iterations(self) -> int:
        """Get the maximum iterations limit."""
        return self._max_iterations

    @max_iterations.setter
    def max_iterations(self, value: int) -> None:
        """
        Set the maximum iterations limit.

        Args:
            value: Maximum number of iterations (0 = no limit).
        """
        self._max_iterations = max(0, value)

    @property
    def current_iteration(self) -> int:
        """Get the current iteration count."""
        return self._current_iteration

    @property
    def is_iterating(self) -> bool:
        """Check if the loop is currently iterating."""
        return self._is_iterating

    @property
    def last_condition_result(self) -> Optional[bool]:
        """Get the result of the last condition evaluation."""
        return self._last_condition_result

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Uses AST validation to check condition code syntax before execution.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # If condition_code is provided, validate it's valid Python expression
        if self._condition_code:
            result = validate_condition_code(self._condition_code)
            if not result.valid:
                for error in result.error_messages:
                    errors.append(f"Invalid condition code: {error}")

        # Validate max_iterations is non-negative
        if self._max_iterations < 0:
            errors.append("max_iterations must be non-negative")

        return errors

    def _evaluate_condition(self, inputs: Dict[str, Any]) -> bool:
        """
        Evaluate the loop condition.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            The boolean result of the condition evaluation.

        Raises:
            ValueError: If condition evaluation fails.
        """
        if self._condition_code:
            # Validate condition code syntax before execution
            validation_result = validate_condition_code(self._condition_code)
            if not validation_result.valid:
                error_msg = "; ".join(validation_result.error_messages)
                raise SyntaxError(f"Invalid condition code: {error_msg}")

            # Execute condition code with access to inputs and iteration state
            namespace: Dict[str, Any] = {
                "inputs": inputs,
                "value": inputs.get("value"),
                "condition": inputs.get("condition", False),
                "iteration": self._current_iteration,
            }

            try:
                result = eval(self._condition_code, {"__builtins__": {}}, namespace)
            except Exception as e:
                raise ValueError(f"Failed to evaluate condition code: {e}")

            # Ensure result is boolean
            if not isinstance(result, bool):
                result = bool(result)

            return result
        else:
            # Use direct condition input
            condition_value = inputs.get("condition")

            if condition_value is None:
                return False
            elif isinstance(condition_value, bool):
                return condition_value
            else:
                return bool(condition_value)

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the while loop node.

        This method prepares the loop for iteration. The actual iteration
        is handled by the execution engine which calls iterate() repeatedly.

        For data model purposes, this returns the initial state of the loop.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'condition' (boolean) and optionally 'value' (any).

        Returns:
            Dictionary with 'iteration_count' for the first iteration.

        Raises:
            ValueError: If condition evaluation fails.
        """
        # Reset iteration state
        self._current_iteration = 0
        self._is_iterating = False
        self._last_condition_result = None

        # Evaluate initial condition
        try:
            condition_result = self._evaluate_condition(inputs)
            self._last_condition_result = condition_result
        except Exception:
            # If condition evaluation fails, don't iterate
            self._is_iterating = False
            raise

        if condition_result:
            self._is_iterating = True

        return {
            "iteration_count": self._current_iteration,
        }

    def iterate(self, inputs: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """
        Generator that yields outputs for each iteration.

        This method is used by the execution engine to iterate through
        the loop, yielding the current iteration count while the condition
        remains True.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   The condition may be re-evaluated each iteration if using
                   condition_code.

        Yields:
            Dictionary with 'iteration_count' for each iteration.

        Raises:
            RuntimeError: If max_iterations is exceeded.
        """
        self._is_iterating = True
        self._current_iteration = 0

        try:
            while True:
                # Check max iterations safety limit
                if self._max_iterations > 0 and self._current_iteration >= self._max_iterations:
                    raise RuntimeError(
                        f"While loop exceeded maximum iterations ({self._max_iterations}). "
                        "Consider increasing max_iterations or fixing the loop condition."
                    )

                # Evaluate condition
                condition_result = self._evaluate_condition(inputs)
                self._last_condition_result = condition_result

                if not condition_result:
                    break

                # Yield current iteration state
                yield {
                    "iteration_count": self._current_iteration,
                }

                self._current_iteration += 1
        finally:
            self._is_iterating = False

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        super().reset_state()
        self._current_iteration = 0
        self._is_iterating = False
        self._last_condition_result = None

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get while loop node specific properties for serialization.

        Returns:
            Dictionary containing the condition code and max_iterations.
        """
        return {
            "condition_code": self._condition_code,
            "max_iterations": self._max_iterations,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load while loop node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._condition_code = properties.get("condition_code", "")
        self._max_iterations = properties.get("max_iterations", 10000)

    def __repr__(self) -> str:
        """Get a detailed string representation of the while loop node."""
        code_preview = self._condition_code[:20] + "..." if len(self._condition_code) > 20 else self._condition_code
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"condition_code='{code_preview}', "
            f"max_iterations={self._max_iterations}, "
            f"iterating={self._is_iterating}, "
            f"iteration={self._current_iteration}, "
            f"state={self._execution_state.name})"
        )
