"""
End node model that marks the termination point of script execution.

This module defines the EndNode class, which represents the final node in
an execution path. Graphs can have multiple End nodes for different
execution paths (e.g., different branches of conditional logic).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, PortType

if TYPE_CHECKING:
    pass


class EndNode(BaseNode):
    """
    A node that marks the termination point of script execution.

    The EndNode represents the end of an execution path in the visual script.
    When execution reaches an EndNode, that particular path is considered
    complete. A graph can have multiple EndNodes to handle different
    execution paths (e.g., different branches of if/else statements).

    The EndNode has an optional result input that can capture a final value
    from the execution path, which can be useful for returning values from
    the script or for debugging purposes.

    Attributes:
        result_value: The captured result value from the execution path.

    Example:
        >>> node = EndNode()
        >>> node.set_input("result", 42)
        >>> node.run()
        >>> node.result_value
        42
    """

    # Class-level metadata
    node_type: str = "end"
    """Unique identifier for end nodes."""

    node_category: str = "Control Flow"
    """Category for organizing in the UI."""

    node_color: str = "#E91E63"
    """Pink/magenta color to clearly distinguish end nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
    ) -> None:
        """
        Initialize a new EndNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'End'.
            position: Optional initial position. If not provided, defaults to (0, 0).
        """
        self._result_value: Any = None
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input ports for the end node.

        The end node has:
        - An execution flow input port (required for execution to reach this node)
        - An optional result input port to capture a final value

        End nodes have no output ports since they terminate execution.
        """
        # Execution flow input - execution must reach this node
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input - terminates this execution path",
            required=False,
        ))

        # Optional result input - captures a final value from the execution path
        self.add_input_port(InputPort(
            name="result",
            port_type=PortType.ANY,
            description="Optional result value to capture from this execution path",
            required=False,
        ))

    @property
    def result_value(self) -> Any:
        """Get the captured result value from execution."""
        return self._result_value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        The EndNode is always valid as long as it exists - it requires no
        specific configuration. The execution flow connection is validated
        at the graph level.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        # EndNode has no required configuration to validate
        return []

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the end node, capturing any provided result value.

        When executed, the EndNode captures the result input (if provided)
        and signals the end of this execution path.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   May contain 'result' with a value to capture.

        Returns:
            Empty dictionary since EndNode has no outputs.
        """
        # Capture the result value if provided
        self._result_value = inputs.get("result")

        # EndNode has no outputs - it terminates execution
        return {}

    def reset_state(self) -> None:
        """Reset the node to its initial state, clearing the result value."""
        super().reset_state()
        self._result_value = None

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get end node specific properties for serialization.

        Returns:
            Dictionary containing the result value (for state preservation).
        """
        return {
            "result_value": self._result_value,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load end node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._result_value = properties.get("result_value")

    def __repr__(self) -> str:
        """Get a detailed string representation of the end node."""
        result_preview = repr(self._result_value)
        if len(result_preview) > 30:
            result_preview = result_preview[:27] + "..."
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"result={result_preview}, "
            f"state={self._execution_state.name})"
        )
