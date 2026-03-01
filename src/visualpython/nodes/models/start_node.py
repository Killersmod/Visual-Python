"""
Start node model that marks the entry point of script execution.

This module defines the StartNode class, which represents the starting point
of execution in a visual script. Every valid graph must have exactly one
Start node as the execution origin.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import OutputPort, PortType

if TYPE_CHECKING:
    pass


class StartNode(BaseNode):
    """
    A node that marks the entry point of script execution.

    The StartNode represents the beginning of execution in the visual script.
    When execution starts, it begins from the StartNode and follows the
    execution flow through connected nodes. A valid graph must have exactly
    one StartNode as the execution origin.

    The StartNode has no input ports since it is the origin of execution.
    It has an execution flow output port to connect to the first node(s)
    to be executed.

    Example:
        >>> node = StartNode()
        >>> node.run()
        >>> node.execution_state
        ExecutionState.COMPLETED
    """

    # Class-level metadata
    node_type: str = "start"
    """Unique identifier for start nodes."""

    node_category: str = "Control Flow"
    """Category for organizing in the UI."""

    node_color: str = "#00BCD4"
    """Cyan color to clearly distinguish start nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
    ) -> None:
        """
        Initialize a new StartNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Start'.
            position: Optional initial position. If not provided, defaults to (0, 0).
        """
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the output ports for the start node.

        The start node has:
        - An execution flow output port (to begin execution flow)

        Start nodes have no input ports since they are the execution origin.
        """
        # Execution flow output - execution begins from this port
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output - start of script execution",
        ))

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        The StartNode is always valid as long as it exists - it requires no
        specific configuration. Graph-level validation ensures exactly one
        StartNode exists.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        # StartNode has no required configuration to validate
        return []

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the start node, initiating script execution.

        When executed, the StartNode signals the beginning of execution.
        Since it has no inputs to process, it simply returns an output
        indicating execution should proceed.

        Args:
            inputs: Dictionary mapping input port names to their values.
                   This will be empty for StartNode since it has no inputs.

        Returns:
            Dictionary containing exec_out signaling execution can proceed.
        """
        # StartNode has no inputs to process - it just signals execution start
        return {"exec_out": None}

    def __repr__(self) -> str:
        """Get a detailed string representation of the start node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"state={self._execution_state.name})"
        )
