"""
Connection-related commands for undo/redo functionality.

This module provides commands for adding and removing connections between nodes.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, TYPE_CHECKING

from visualpython.commands.command import Command
from visualpython.nodes.models.port import Connection
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph


class AddConnectionCommand(Command):
    """
    Command to add a connection between two nodes.
    """

    def __init__(
        self,
        graph: "Graph",
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
        add_widget_callback: Optional[Callable[[Connection], None]] = None,
        remove_widget_callback: Optional[Callable[[str], None]] = None,
        update_port_state_callback: Optional[Callable[[str, str, bool, bool], None]] = None,
    ) -> None:
        """
        Initialize the add connection command.

        Args:
            graph: The graph to add the connection to.
            source_node_id: ID of the source node.
            source_port_name: Name of the source output port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target input port.
            add_widget_callback: Callback to create visual connection widget.
            remove_widget_callback: Callback to remove visual connection widget by key.
            update_port_state_callback: Callback(node_id, port_name, is_input, is_connected).
        """
        super().__init__(graph)
        self._source_node_id = source_node_id
        self._source_port_name = source_port_name
        self._target_node_id = target_node_id
        self._target_port_name = target_port_name
        self._add_widget_callback = add_widget_callback
        self._remove_widget_callback = remove_widget_callback
        self._update_port_state_callback = update_port_state_callback
        self._connection: Optional[Connection] = None

    def execute(self) -> bool:
        """Create the connection."""
        try:
            # Check if connection already exists
            if self._graph.has_connection(
                self._source_node_id,
                self._source_port_name,
                self._target_node_id,
                self._target_port_name,
            ):
                return False

            # Create the connection
            self._connection = self._graph.connect(
                self._source_node_id,
                self._source_port_name,
                self._target_node_id,
                self._target_port_name,
            )

            # Create visual widget
            if self._add_widget_callback and self._connection:
                self._add_widget_callback(self._connection)

            # Update port visual states
            if self._update_port_state_callback:
                self._update_port_state_callback(
                    self._source_node_id, self._source_port_name, False, True
                )
                self._update_port_state_callback(
                    self._target_node_id, self._target_port_name, True, True
                )

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute AddConnectionCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Remove the connection."""
        try:
            # Remove visual widget first
            if self._remove_widget_callback:
                connection_key = (
                    f"{self._source_node_id}:"
                    f"{self._source_port_name}:"
                    f"{self._target_node_id}:"
                    f"{self._target_port_name}"
                )
                self._remove_widget_callback(connection_key)

            # Remove from graph
            self._graph.disconnect(
                self._source_node_id,
                self._source_port_name,
                self._target_node_id,
                self._target_port_name,
            )

            # Update port visual states - check if ports still have other connections
            if self._update_port_state_callback:
                source_remaining = self._graph.get_connections_for_port(
                    self._source_node_id, self._source_port_name, is_input=False
                )
                target_remaining = self._graph.get_connections_for_port(
                    self._target_node_id, self._target_port_name, is_input=True
                )
                self._update_port_state_callback(
                    self._source_node_id, self._source_port_name, False, len(source_remaining) > 0
                )
                self._update_port_state_callback(
                    self._target_node_id, self._target_port_name, True, len(target_remaining) > 0
                )

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo AddConnectionCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        return "Add Connection"


class RemoveConnectionCommand(Command):
    """
    Command to remove a connection between two nodes.
    """

    def __init__(
        self,
        graph: "Graph",
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
        add_widget_callback: Optional[Callable[[Connection], None]] = None,
        remove_widget_callback: Optional[Callable[[str], None]] = None,
        update_port_state_callback: Optional[Callable[[str, str, bool, bool], None]] = None,
    ) -> None:
        """
        Initialize the remove connection command.

        Args:
            graph: The graph to remove the connection from.
            source_node_id: ID of the source node.
            source_port_name: Name of the source output port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target input port.
            add_widget_callback: Callback to create visual connection widget.
            remove_widget_callback: Callback to remove visual connection widget by key.
            update_port_state_callback: Callback(node_id, port_name, is_input, is_connected).
        """
        super().__init__(graph)
        self._source_node_id = source_node_id
        self._source_port_name = source_port_name
        self._target_node_id = target_node_id
        self._target_port_name = target_port_name
        self._add_widget_callback = add_widget_callback
        self._remove_widget_callback = remove_widget_callback
        self._update_port_state_callback = update_port_state_callback
        self._connection_data: Optional[Dict[str, str]] = None

    def execute(self) -> bool:
        """Remove the connection."""
        try:
            # Get and store connection data for undo
            connection = self._graph.get_connection(
                self._source_node_id,
                self._source_port_name,
                self._target_node_id,
                self._target_port_name,
            )

            if not connection:
                return False

            self._connection_data = connection.to_dict()

            # Remove visual widget first
            if self._remove_widget_callback:
                connection_key = (
                    f"{self._source_node_id}:"
                    f"{self._source_port_name}:"
                    f"{self._target_node_id}:"
                    f"{self._target_port_name}"
                )
                self._remove_widget_callback(connection_key)

            # Remove from graph
            self._graph.disconnect(
                self._source_node_id,
                self._source_port_name,
                self._target_node_id,
                self._target_port_name,
            )

            # Update port visual states
            if self._update_port_state_callback:
                source_remaining = self._graph.get_connections_for_port(
                    self._source_node_id, self._source_port_name, is_input=False
                )
                target_remaining = self._graph.get_connections_for_port(
                    self._target_node_id, self._target_port_name, is_input=True
                )
                self._update_port_state_callback(
                    self._source_node_id, self._source_port_name, False, len(source_remaining) > 0
                )
                self._update_port_state_callback(
                    self._target_node_id, self._target_port_name, True, len(target_remaining) > 0
                )

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute RemoveConnectionCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Restore the connection."""
        if not self._connection_data:
            return False

        try:
            # Recreate the connection
            connection = self._graph.connect(
                self._connection_data["source_node_id"],
                self._connection_data["source_port_name"],
                self._connection_data["target_node_id"],
                self._connection_data["target_port_name"],
                validate=False,
            )

            # Create visual widget
            if self._add_widget_callback and connection:
                self._add_widget_callback(connection)

            # Update port visual states
            if self._update_port_state_callback:
                self._update_port_state_callback(
                    self._source_node_id, self._source_port_name, False, True
                )
                self._update_port_state_callback(
                    self._target_node_id, self._target_port_name, True, True
                )

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo RemoveConnectionCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        return "Delete Connection"
