"""
Try/Catch node model for exception handling in VisualPython.

This module defines the TryCatchNode class, which enables exception handling
with try/except paths in visual scripts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class TryCatchNode(BaseNode):
    """
    A node that provides exception handling with try/except paths.

    The TryCatchNode enables visual exception handling similar to Python's try/except
    statement. It executes the try_body branch and if an exception occurs,
    routes execution to the except_path branch.

    The node supports:
    1. Specifying exception types to catch (e.g., "ValueError, TypeError")
    2. Catching all exceptions with a catch-all mode
    3. Optional finally block execution
    4. Access to the caught exception object and its type name

    The node has:
    - An execution flow input to trigger the try block
    - A try_body flow output for code that may raise exceptions
    - An except_path flow output executed when an exception is caught
    - A finally_path flow output that always executes (optional)
    - Output ports for the caught exception and exception type name

    Attributes:
        exception_types: Comma-separated list of exception type names to catch.
        catch_all: If True, catches all exceptions (bare except).
        exception_variable: Variable name for the caught exception (default: 'e').

    Example:
        >>> node = TryCatchNode()
        >>> node.exception_types = "ValueError, TypeError"
        >>> # try_body executes, if exception -> except_path executes
    """

    # Class-level metadata
    node_type: str = "try_catch"
    """Unique identifier for try/catch nodes."""

    node_category: str = "Control Flow"
    """Category for organizing in the UI."""

    node_color: str = "#E91E63"
    """Pink color to distinguish exception handling nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        exception_types: str = "Exception",
        catch_all: bool = False,
        exception_variable: str = "e",
    ) -> None:
        """
        Initialize a new TryCatchNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Try Catch'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            exception_types: Comma-separated exception type names to catch.
                            If empty and catch_all is False, defaults to "Exception".
            catch_all: If True, catches all exceptions regardless of exception_types.
            exception_variable: Variable name to use for the caught exception (default: 'e').
        """
        self._exception_types: str = exception_types
        self._catch_all: bool = catch_all
        self._exception_variable: str = exception_variable
        self._last_exception: Optional[BaseException] = None
        self._last_exception_type: Optional[str] = None
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the try/catch node.

        The try/catch node has:
        - exec_in: Execution flow input to trigger the try block
        - try_body: Execution flow output for code that may raise exceptions
        - except_path: Execution flow output when exception is caught
        - finally_path: Execution flow output that always runs (optional)
        - caught_exception: The exception object that was caught
        - exception_type_name: The name of the caught exception type
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input - triggers the try block",
            required=False,
        ))

        # Execution flow output for try body
        self.add_output_port(OutputPort(
            name="try_body",
            port_type=PortType.FLOW,
            description="Execution flow for code that may raise exceptions",
        ))

        # Execution flow output for except path
        self.add_output_port(OutputPort(
            name="except_path",
            port_type=PortType.FLOW,
            description="Execution flow when an exception is caught",
        ))

        # Execution flow output for finally path (optional)
        self.add_output_port(OutputPort(
            name="finally_path",
            port_type=PortType.FLOW,
            description="Execution flow that always runs (optional)",
        ))

        # The caught exception object
        self.add_output_port(OutputPort(
            name="caught_exception",
            port_type=PortType.ANY,
            description="The exception object that was caught",
        ))

        # The exception type name as a string
        self.add_output_port(OutputPort(
            name="exception_type_name",
            port_type=PortType.STRING,
            description="The name of the caught exception type",
        ))

    @property
    def exception_types(self) -> str:
        """Get the exception types string."""
        return self._exception_types

    @exception_types.setter
    def exception_types(self, value: str) -> None:
        """
        Set the exception types string.

        Args:
            value: Comma-separated exception type names (e.g., "ValueError, TypeError").
        """
        self._exception_types = value

    @property
    def catch_all(self) -> bool:
        """Get whether to catch all exceptions."""
        return self._catch_all

    @catch_all.setter
    def catch_all(self, value: bool) -> None:
        """
        Set whether to catch all exceptions.

        Args:
            value: If True, catches all exceptions regardless of exception_types.
        """
        self._catch_all = value

    @property
    def exception_variable(self) -> str:
        """Get the exception variable name."""
        return self._exception_variable

    @exception_variable.setter
    def exception_variable(self, value: str) -> None:
        """
        Set the exception variable name.

        Args:
            value: Variable name to use for the caught exception.
        """
        self._exception_variable = value if value else "e"

    @property
    def last_exception(self) -> Optional[BaseException]:
        """Get the last caught exception."""
        return self._last_exception

    @property
    def last_exception_type(self) -> Optional[str]:
        """Get the type name of the last caught exception."""
        return self._last_exception_type

    def get_exception_type_list(self) -> List[str]:
        """
        Parse the exception_types string into a list of type names.

        Returns:
            List of exception type names, stripped of whitespace.
        """
        if not self._exception_types:
            return ["Exception"]

        types = [t.strip() for t in self._exception_types.split(",") if t.strip()]
        return types if types else ["Exception"]

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Validates that exception type names are valid Python identifiers.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate exception types are valid Python identifiers
        if not self._catch_all and self._exception_types:
            for exc_type in self.get_exception_type_list():
                # Check if it's a valid Python identifier (simplified check)
                if not exc_type.isidentifier():
                    errors.append(f"Invalid exception type name: {exc_type}")

        # Validate exception variable name
        if self._exception_variable and not self._exception_variable.isidentifier():
            errors.append(f"Invalid exception variable name: {self._exception_variable}")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the try/catch node.

        Note: The actual try/except handling is done by the code generator.
        This method is primarily for runtime state tracking.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary with output values.
        """
        # Reset exception tracking
        self._last_exception = None
        self._last_exception_type = None

        return {
            "caught_exception": None,
            "exception_type_name": None,
        }

    def set_caught_exception(self, exception: BaseException) -> None:
        """
        Record a caught exception.

        Called by the execution engine when an exception is caught.

        Args:
            exception: The exception that was caught.
        """
        self._last_exception = exception
        self._last_exception_type = type(exception).__name__

    def get_active_branch(self) -> Optional[str]:
        """
        Get the name of the active branch based on the last execution.

        Returns:
            'except_path' if an exception was caught,
            'try_body' if no exception occurred,
            None if the node hasn't been executed yet.
        """
        if self._last_exception is not None:
            return "except_path"
        return "try_body"

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        super().reset_state()
        self._last_exception = None
        self._last_exception_type = None

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get try/catch node specific properties for serialization.

        Returns:
            Dictionary containing the exception handling configuration.
        """
        return {
            "exception_types": self._exception_types,
            "catch_all": self._catch_all,
            "exception_variable": self._exception_variable,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load try/catch node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._exception_types = properties.get("exception_types", "Exception")
        self._catch_all = properties.get("catch_all", False)
        self._exception_variable = properties.get("exception_variable", "e")

    def __repr__(self) -> str:
        """Get a detailed string representation of the try/catch node."""
        exc_types = self._exception_types[:20] + "..." if len(self._exception_types) > 20 else self._exception_types
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"exception_types='{exc_types}', "
            f"catch_all={self._catch_all}, "
            f"state={self._execution_state.name})"
        )
