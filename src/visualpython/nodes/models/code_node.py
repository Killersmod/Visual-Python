"""
Code node model for executing user-written Python code.

This module defines the CodeNode class, which is the primary node type for
executing arbitrary Python logic written by users as code strings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.compiler.ast_validator import validate_user_code
from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.variables import GlobalVariableStore

if TYPE_CHECKING:
    pass


class CodeNode(BaseNode):
    """
    A node that executes user-written Python code.

    The CodeNode allows users to write arbitrary Python code that will be
    executed during graph evaluation. It provides a flexible way to implement
    custom logic that doesn't fit into predefined node types.

    The code is stored as a string and can access input values through a
    predefined 'inputs' dictionary and must set output values in an 'outputs'
    dictionary.

    Attributes:
        code: The Python code string to execute.
        is_code_valid: Whether the current code has valid syntax.
        validation_errors: List of current validation errors.

    Example:
        >>> node = CodeNode()
        >>> node.code = '''
        ... result = inputs.get('value', 0) * 2
        ... outputs['result'] = result
        ... '''

        # Using global variables for shared state:
        >>> node.code = '''
        ... # Set a global variable
        ... globals.set('counter', globals.get('counter', 0) + 1)
        ... outputs['result'] = globals.get('counter')
        ... '''

        # Using case variables for per-execution shared state:
        >>> node.code = '''
        ... # Set a case variable (persists during execution only)
        ... case.counter = case.get('counter', 0) + 1
        ... outputs['result'] = case.counter
        ... '''
    """

    # Class-level metadata
    node_type: str = "code"
    """Unique identifier for Python code nodes."""

    node_category: str = "Custom Code"
    """Category for organizing in the UI."""

    node_color: str = "#4CAF50"
    """Green color to distinguish code nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        code: str = "",
    ) -> None:
        """
        Initialize a new CodeNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Code'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            code: Optional initial Python code string.
        """
        self._code: str = code
        self._is_code_valid: bool = True
        self._validation_errors: List[Any] = []
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the default input and output ports for the code node.

        The code node has:
        - An execution flow input port (for controlling execution order)
        - A generic 'value' input port that can accept any data type
        - An execution flow output port (for chaining execution)
        - A generic 'result' output port for the code's result
        """
        # Execution flow ports
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Data ports - flexible ANY type to allow custom code to work with any data
        self.add_input_port(InputPort(
            name="value",
            port_type=PortType.ANY,
            description="Input value accessible in code as inputs['value']",
            required=False,
        ))
        self.add_output_port(OutputPort(
            name="result",
            port_type=PortType.ANY,
            description="Output value set in code as outputs['result']",
        ))

    @property
    def code(self) -> str:
        """Get the Python code string."""
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        """
        Set the Python code string.

        Args:
            value: The Python code to execute.
        """
        self._code = value

    @property
    def is_code_valid(self) -> bool:
        """Check if the current code has valid syntax."""
        return self._is_code_valid

    @property
    def validation_errors(self) -> List[Any]:
        """Get the list of current validation errors."""
        return self._validation_errors.copy()

    def set_validation_state(self, is_valid: bool, errors: List[Any]) -> None:
        """
        Set the validation state of the code.

        This is called by the CodePropertyEditor when real-time
        syntax checking detects changes.

        Args:
            is_valid: Whether the code passed validation.
            errors: List of validation errors if any.
        """
        self._is_code_valid = is_valid
        self._validation_errors = errors.copy() if errors else []

    def validate(self) -> List[str]:
        """
        Validate the node's configuration, including code syntax.

        Uses Python's AST module to validate syntax before execution,
        catching compilation errors early in the process.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Check if code is empty
        if not self._code or not self._code.strip():
            errors.append("Code cannot be empty")
            return errors

        # Validate Python syntax using AST validator
        result = validate_user_code(self._code)
        if not result.valid:
            errors.extend(result.error_messages)

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the user-written Python code.

        The code has access to:
        - 'inputs': A dictionary containing all input port values
        - 'outputs': A dictionary where the code should set output values
        - 'globals': The GlobalVariableStore instance for shared state
        - 'case': The Case instance for per-execution shared state (if available)

        The 'case' object provides per-execution shared state that is:
        - Accessible from all nodes during a single execution
        - Automatically cleared at the start of each new execution
        - Thread-safe for concurrent access
        - Supports both method calls (case.get('x'), case.set('x', 1))
          and attribute access (case.x = 1, value = case.x)

        Uses AST validation to catch syntax errors before execution.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary mapping output port names to their values.

        Raises:
            ValueError: If the code is empty.
            SyntaxError: If the code has syntax errors.
            Exception: Any exception raised during code execution.
        """
        if not self._code or not self._code.strip():
            raise ValueError("Cannot execute empty code")

        # Validate code syntax using AST before execution
        validation_result = validate_user_code(self._code)
        if not validation_result.valid:
            error_msg = "; ".join(validation_result.error_messages)
            raise SyntaxError(error_msg)

        # Create the execution namespace with access to global variable store
        outputs: Dict[str, Any] = {}
        global_store = GlobalVariableStore.get_instance()
        namespace: Dict[str, Any] = {
            "inputs": inputs,
            "outputs": outputs,
            "globals": global_store,
        }

        # Add the current execution Case instance if available
        # Import lazily to avoid circular import issues
        from visualpython.execution.engine import get_current_case
        current_case = get_current_case()
        if current_case is not None:
            namespace["case"] = current_case

        # Execute the code
        exec(self._code, namespace)

        return outputs

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get code node specific properties for serialization.

        Returns:
            Dictionary containing the code string.
        """
        return {
            "code": self._code,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load code node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._code = properties.get("code", "")

    def __repr__(self) -> str:
        """Get a detailed string representation of the code node."""
        code_preview = self._code[:30] + "..." if len(self._code) > 30 else self._code
        code_preview = code_preview.replace("\n", "\\n")
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"code='{code_preview}', "
            f"state={self._execution_state.name})"
        )
