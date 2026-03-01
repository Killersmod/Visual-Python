"""
Breakpoint node model for pausing execution during debugging.

This module defines the BreakpointNode class, which pauses script execution
at a specified point to enable step-through debugging and variable inspection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType


class BreakpointNode(BaseNode):
    """
    A node that pauses execution for debugging purposes.

    The BreakpointNode provides a debugging mechanism that allows users to:
    - Pause execution at specific points in the visual script
    - Optionally pause only when a condition is true
    - Inspect variables and state when paused
    - Resume execution after inspection

    The breakpoint can be:
    - Unconditional: Always pauses when reached
    - Conditional: Only pauses when the condition input evaluates to True
    - Disabled: Passes through without pausing (via the enabled property)

    Attributes:
        enabled: Whether the breakpoint is active.
        message: A debug message to display when the breakpoint is hit.

    Example:
        >>> node = BreakpointNode(message="Check loop state")
        >>> # When execution reaches this node, it will pause
        >>> # and allow inspection of the current execution state
    """

    # Class-level metadata
    node_type: str = "breakpoint"
    """Unique identifier for breakpoint nodes."""

    node_category: str = "Debugging"
    """Category for organizing in the UI."""

    node_color: str = "#FF5722"
    """Orange-red color to indicate debugging/breakpoint."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        enabled: bool = True,
        message: str = "",
    ) -> None:
        """
        Initialize a new BreakpointNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Breakpoint'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            enabled: Whether the breakpoint is active. Defaults to True.
            message: A debug message to display when the breakpoint is hit.
        """
        self._enabled: bool = enabled
        self._message: str = message
        self._is_paused: bool = False
        self._captured_data: Dict[str, Any] = {}
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the breakpoint node.

        The breakpoint node has:
        - An execution flow input port (for controlling execution order)
        - A condition input port (optional, for conditional breakpoints)
        - A data input port (optional, for inspecting values)
        - An execution flow output port (for continuing execution)
        - A data output port (passes through the input data)
        - A paused output port (indicates whether execution was paused)
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
            description="Execution flow output (continues after resume)",
        ))

        # Conditional breakpoint input
        self.add_input_port(InputPort(
            name="condition",
            port_type=PortType.BOOLEAN,
            description="If connected, only pause when condition is True",
            required=False,
            default_value=True,
        ))

        # Data inspection port (for debugging values)
        self.add_input_port(InputPort(
            name="inspect_data",
            port_type=PortType.ANY,
            description="Data to inspect when paused",
            required=False,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="data_out",
            port_type=PortType.ANY,
            description="Passes through the inspect_data value",
        ))

        self.add_output_port(OutputPort(
            name="was_paused",
            port_type=PortType.BOOLEAN,
            description="True if execution was paused at this breakpoint",
        ))

    @property
    def enabled(self) -> bool:
        """Get whether the breakpoint is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """
        Set whether the breakpoint is enabled.

        Args:
            value: True to enable the breakpoint, False to disable.
        """
        self._enabled = value

    @property
    def message(self) -> str:
        """Get the debug message."""
        return self._message

    @message.setter
    def message(self, value: str) -> None:
        """
        Set the debug message.

        Args:
            value: The message to display when the breakpoint is hit.
        """
        self._message = value

    @property
    def is_paused(self) -> bool:
        """Get whether execution is currently paused at this breakpoint."""
        return self._is_paused

    @property
    def captured_data(self) -> Dict[str, Any]:
        """Get the data captured when the breakpoint was hit."""
        return self._captured_data.copy()

    def should_pause(self, condition: bool = True) -> bool:
        """
        Determine if execution should pause at this breakpoint.

        Args:
            condition: The condition value from the input port.

        Returns:
            True if execution should pause, False otherwise.
        """
        return self._enabled and condition

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        The breakpoint node is always valid.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        return []

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the breakpoint node.

        When executed, the node:
        1. Checks if the breakpoint should pause (based on enabled and condition)
        2. Captures any input data for inspection
        3. Signals that a pause is requested (via the was_paused output)
        4. Passes through the input data

        The actual pausing mechanism is handled by the ExecutionEngine,
        which checks for breakpoint nodes and respects the pause request.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'data_out': The passed-through inspect_data value
                - 'was_paused': True if the breakpoint triggered a pause
        """
        # Get the condition value (defaults to True if not connected)
        condition = inputs.get("condition", True)
        if condition is None:
            condition = True

        # Get the data to inspect
        inspect_data = inputs.get("inspect_data")

        # Determine if we should pause
        should_pause = self.should_pause(condition)

        # Capture data for inspection
        self._captured_data = {
            "message": self._message,
            "condition": condition,
            "inspect_data": inspect_data,
            "inputs": inputs.copy(),
        }

        # Set pause state - this will be read by the execution engine
        self._is_paused = should_pause

        return {
            "data_out": inspect_data,
            "was_paused": should_pause,
        }

    def resume(self) -> None:
        """
        Resume execution after being paused.

        This method is called by the execution engine or UI when
        the user wants to continue execution from this breakpoint.
        """
        self._is_paused = False

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        super().reset_state()
        self._is_paused = False
        self._captured_data.clear()

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get breakpoint node specific properties for serialization.

        Returns:
            Dictionary containing the enabled state and message.
        """
        return {
            "enabled": self._enabled,
            "message": self._message,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load breakpoint node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._enabled = properties.get("enabled", True)
        self._message = properties.get("message", "")

    def __repr__(self) -> str:
        """Get a detailed string representation of the breakpoint node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"enabled={self._enabled}, "
            f"message='{self._message[:20]}{'...' if len(self._message) > 20 else ''}', "
            f"is_paused={self._is_paused}, "
            f"state={self._execution_state.name})"
        )
