"""
Layout-related commands for undo/redo functionality.

This module provides commands for applying automatic layout algorithms.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, TYPE_CHECKING

from visualpython.commands.command import Command
from visualpython.nodes.models.base_node import Position
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph
    from visualpython.layout.base_layout import LayoutResult


class ApplyLayoutCommand(Command):
    """
    Command to apply an automatic layout to the graph.

    Stores all node positions before the layout is applied, allowing
    full restoration on undo.
    """

    def __init__(
        self,
        graph: "Graph",
        layout_result: "LayoutResult",
        update_widget_callback: Optional[Callable[[str, float, float], None]] = None,
        update_connections_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Initialize the apply layout command.

        Args:
            graph: The graph to apply the layout to.
            layout_result: The calculated layout result with new positions.
            update_widget_callback: Callback to update a node widget's position.
            update_connections_callback: Callback to update all connection paths.
        """
        super().__init__(graph)
        self._layout_result = layout_result
        self._update_widget_callback = update_widget_callback
        self._update_connections_callback = update_connections_callback

        # Store original positions for undo
        self._original_positions: Dict[str, tuple[float, float]] = {}
        for node in graph.nodes:
            self._original_positions[node.id] = (node.position.x, node.position.y)

    def execute(self) -> bool:
        """Apply the layout to all nodes."""
        try:
            # Apply new positions from layout result
            for node_id, position in self._layout_result.positions.items():
                node = self._graph.get_node(node_id)
                if node:
                    node.position = Position(position.x, position.y)

                    if self._update_widget_callback:
                        self._update_widget_callback(node_id, position.x, position.y)

            # Update all connection paths
            if self._update_connections_callback:
                self._update_connections_callback()

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute ApplyLayoutCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Restore all nodes to their original positions."""
        try:
            for node_id, (x, y) in self._original_positions.items():
                node = self._graph.get_node(node_id)
                if node:
                    node.position = Position(x, y)

                    if self._update_widget_callback:
                        self._update_widget_callback(node_id, x, y)

            # Update all connection paths
            if self._update_connections_callback:
                self._update_connections_callback()

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo ApplyLayoutCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        algorithm_name = self._layout_result.algorithm_name or "Auto"
        return f"Apply {algorithm_name} Layout"
