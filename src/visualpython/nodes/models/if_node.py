"""
If/Else node model for conditional branching in VisualPython.

This module defines the IfNode class, which enables conditional execution
paths based on boolean conditions in visual scripts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.compiler.ast_validator import validate_condition_code
from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class IfNode(BaseNode):
    """
    A node that provides conditional branching based on a boolean condition.

    The IfNode enables visual conditional execution similar to Python's if/else
    statement. It evaluates a condition and routes execution to either the
    true_branch or false_branch output depending on the result.

    The node supports two modes of condition evaluation:
    1. Direct boolean input: A boolean value is passed to the 'condition' port
    2. Code-based evaluation: Python code that evaluates to a boolean is stored
       in the condition_code property and executed with access to input values

    The node has:
    - An execution flow input to trigger condition evaluation
    - A condition input for direct boolean values
    - A true_branch flow output executed when condition is True
    - A false_branch flow output executed when condition is False
    - A result output containing the evaluated condition value

    Attributes:
        condition_code: Optional Python code string for complex condition evaluation.
        last_result: The result of the last condition evaluation (True/False/None).

    Example:
        >>> node = IfNode()
        >>> node.set_input("condition", True)
        >>> result = node.execute({"condition": True})
        >>> # Execution continues on true_branch
    """

    # Class-level metadata
    node_type: str = "if"
    """Unique identifier for if nodes."""

    node_category: str = "Control Flow"
    """Category for organizing in the UI."""

    node_color: str = "#9C27B0"
    """Purple color to distinguish conditional nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        condition_code: str = "",
    ) -> None:
        """
        Initialize a new IfNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'If'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            condition_code: Optional Python code for evaluating the condition.
                           If empty, the 'condition' input port value is used directly.
        """
        self._condition_code: str = condition_code
        self._last_result: Optional[bool] = None
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the if node.

        The if node has:
        - exec_in: Execution flow input to trigger condition evaluation
        - condition: Boolean condition input (used if condition_code is empty)
        - true_branch: Execution flow output when condition is True
        - false_branch: Execution flow output when condition is False
        - result: The evaluated boolean result
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input - triggers condition evaluation",
            required=False,
        ))

        # Condition input - the boolean value to evaluate
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

        # Execution flow output for true branch - triggered when condition is True
        self.add_output_port(OutputPort(
            name="true_branch",
            port_type=PortType.FLOW,
            description="Execution flow when condition evaluates to True",
        ))

        # Execution flow output for false branch - triggered when condition is False
        self.add_output_port(OutputPort(
            name="false_branch",
            port_type=PortType.FLOW,
            description="Execution flow when condition evaluates to False",
        ))

        # Result output - the evaluated condition value
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.BOOLEAN,
            description="The evaluated boolean result of the condition",
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
    def last_result(self) -> Optional[bool]:
        """Get the result of the last condition evaluation."""
        return self._last_result

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

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the if node - evaluate the condition and return the result.

        The condition is evaluated in one of two ways:
        1. If condition_code is set, execute it with access to inputs
        2. Otherwise, use the direct 'condition' input value

        The execution flow is determined by the result:
        - If True, the execution engine should follow the true_branch output
        - If False, the execution engine should follow the false_branch output

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'condition' (boolean) and optionally 'value' (any).

        Returns:
            Dictionary with 'result' containing the boolean evaluation result.
            The execution engine uses this to determine which branch to execute.

        Raises:
            ValueError: If condition evaluation fails or doesn't produce a boolean.
        """
        result: bool

        if self._condition_code:
            # Validate condition code syntax before execution
            validation_result = validate_condition_code(self._condition_code)
            if not validation_result.valid:
                error_msg = "; ".join(validation_result.error_messages)
                raise SyntaxError(f"Invalid condition code: {error_msg}")

            # Execute condition code with access to inputs
            namespace: Dict[str, Any] = {
                "inputs": inputs,
                "value": inputs.get("value"),
                "condition": inputs.get("condition", False),
            }

            try:
                result = eval(self._condition_code, {"__builtins__": {}}, namespace)
            except Exception as e:
                raise ValueError(f"Failed to evaluate condition code: {e}")

            # Ensure result is boolean
            if not isinstance(result, bool):
                result = bool(result)
        else:
            # Use direct condition input
            condition_value = inputs.get("condition")

            if condition_value is None:
                # Use default value
                result = False
            elif isinstance(condition_value, bool):
                result = condition_value
            else:
                # Convert to boolean
                result = bool(condition_value)

        self._last_result = result

        return {
            "result": result,
        }

    def get_active_branch(self) -> Optional[str]:
        """
        Get the name of the active branch based on the last execution result.

        Returns:
            'true_branch' if last result was True,
            'false_branch' if last result was False,
            None if the node hasn't been executed yet.
        """
        if self._last_result is None:
            return None
        return "true_branch" if self._last_result else "false_branch"

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        super().reset_state()
        self._last_result = None

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get if node specific properties for serialization.

        Returns:
            Dictionary containing the condition code.
        """
        return {
            "condition_code": self._condition_code,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load if node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._condition_code = properties.get("condition_code", "")

    def __repr__(self) -> str:
        """Get a detailed string representation of the if node."""
        code_preview = self._condition_code[:20] + "..." if len(self._condition_code) > 20 else self._condition_code
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"condition_code='{code_preview}', "
            f"last_result={self._last_result}, "
            f"state={self._execution_state.name})"
        )
