"""
Property-related commands for undo/redo functionality.

This module provides commands for changing node properties.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, TYPE_CHECKING

from visualpython.commands.command import Command
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph


class SetNodePropertyCommand(Command):
    """
    Command to change a node property value.

    Supports merging consecutive changes to the same property.
    """

    def __init__(
        self,
        graph: "Graph",
        node_id: str,
        property_name: str,
        old_value: Any,
        new_value: Any,
        update_callback: Optional[Callable[[str, str, Any], None]] = None,
    ) -> None:
        """
        Initialize the set property command.

        Args:
            graph: The graph containing the node.
            node_id: ID of the node.
            property_name: Name of the property to change.
            old_value: Original property value.
            new_value: New property value.
            update_callback: Callback(node_id, property_name, value) to update visuals.
        """
        super().__init__(graph)
        self._node_id = node_id
        self._property_name = property_name
        self._old_value = old_value
        self._new_value = new_value
        self._update_callback = update_callback

    def execute(self) -> bool:
        """Set the property to the new value."""
        try:
            node = self._graph.get_node(self._node_id)
            if not node:
                return False

            # Set the property value
            self._set_property_value(node, self._property_name, self._new_value)

            if self._update_callback:
                self._update_callback(self._node_id, self._property_name, self._new_value)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute SetNodePropertyCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Restore the old property value."""
        try:
            node = self._graph.get_node(self._node_id)
            if not node:
                return False

            # Restore the old value
            self._set_property_value(node, self._property_name, self._old_value)

            if self._update_callback:
                self._update_callback(self._node_id, self._property_name, self._old_value)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo SetNodePropertyCommand", exc_info=True)
            return False

    def _set_property_value(self, node, property_name: str, value: Any) -> None:
        """
        Set a property value on a node.

        Handles both standard attributes and custom properties.

        Args:
            node: The node to modify.
            property_name: Name of the property.
            value: Value to set.
        """
        # Handle common properties
        if property_name == "name":
            node.name = value
        elif property_name == "position_x":
            node.position.x = value
        elif property_name == "position_y":
            node.position.y = value
        elif hasattr(node, property_name):
            setattr(node, property_name, value)
        elif hasattr(node, "_properties") and isinstance(node._properties, dict):
            node._properties[property_name] = value
        else:
            # Try to set as attribute
            setattr(node, property_name, value)

    @property
    def description(self) -> str:
        """Get command description."""
        return f"Change {self._property_name}"

    def can_merge(self, other: Command) -> bool:
        """Check if we can merge with another property change for the same property."""
        if not isinstance(other, SetNodePropertyCommand):
            return False
        return (
            other._node_id == self._node_id
            and other._property_name == self._property_name
        )

    def merge(self, other: Command) -> bool:
        """Merge another property change, keeping original value and taking new end value."""
        if not isinstance(other, SetNodePropertyCommand):
            return False
        if other._node_id != self._node_id:
            return False
        if other._property_name != self._property_name:
            return False

        # Keep our original value, update to the new end value
        self._new_value = other._new_value
        return True


class SetInlineValueCommand(Command):
    """
    Command to change a port's inline value for undo/redo.

    Supports merging consecutive changes to the same port.
    """

    def __init__(
        self,
        graph: "Graph",
        node_id: str,
        port_name: str,
        old_value: Any,
        new_value: Any,
        update_callback: Optional[Callable[[str, str, Any], None]] = None,
    ) -> None:
        super().__init__(graph)
        self._node_id = node_id
        self._port_name = port_name
        self._old_value = old_value
        self._new_value = new_value
        self._update_callback = update_callback

    def _apply_value(self, value: Any) -> bool:
        node = self._graph.get_node(self._node_id)
        if not node:
            return False
        port = node.get_input_port(self._port_name)
        if not port:
            return False
        port.inline_value = value
        if self._update_callback:
            self._update_callback(self._node_id, self._port_name, value)
        return True

    def execute(self) -> bool:
        try:
            if self._apply_value(self._new_value):
                self._executed = True
                return True
            return False
        except Exception:
            logger.debug("Failed to execute SetInlineValueCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        try:
            if self._apply_value(self._old_value):
                self._executed = False
                return True
            return False
        except Exception:
            logger.debug("Failed to undo SetInlineValueCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        return f"Change {self._port_name}"

    def can_merge(self, other: Command) -> bool:
        if not isinstance(other, SetInlineValueCommand):
            return False
        return (
            other._node_id == self._node_id
            and other._port_name == self._port_name
        )

    def merge(self, other: Command) -> bool:
        if not self.can_merge(other):
            return False
        self._new_value = other._new_value
        return True
