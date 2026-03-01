"""
Group-related commands for undo/redo functionality.

This module provides commands for creating, removing, and modifying node groups.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from visualpython.commands.command import Command
from visualpython.nodes.models.node_group import NodeGroup, GroupBounds
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph


class CreateGroupCommand(Command):
    """
    Command to create a new node group containing selected nodes.
    """

    def __init__(
        self,
        graph: "Graph",
        node_ids: List[str],
        name: str = "Group",
        color: Optional[str] = None,
        add_widget_callback: Optional[Callable[[NodeGroup], None]] = None,
        remove_widget_callback: Optional[Callable[[str], None]] = None,
        calculate_bounds_callback: Optional[Callable[[List[str]], GroupBounds]] = None,
    ) -> None:
        """
        Initialize the create group command.

        Args:
            graph: The graph to add the group to.
            node_ids: List of node IDs to include in the group.
            name: Display name for the group.
            color: Optional custom color for the group.
            add_widget_callback: Callback to create the visual widget.
            remove_widget_callback: Callback to remove the visual widget.
            calculate_bounds_callback: Callback to calculate group bounds from nodes.
        """
        super().__init__(graph)
        self._node_ids = node_ids.copy()
        self._name = name
        self._color = color
        self._add_widget_callback = add_widget_callback
        self._remove_widget_callback = remove_widget_callback
        self._calculate_bounds_callback = calculate_bounds_callback
        self._group_id: Optional[str] = None
        self._group_data: Optional[Dict[str, Any]] = None

    def execute(self) -> bool:
        """Create the group and add it to the graph."""
        try:
            # Calculate bounds if callback provided
            bounds = None
            if self._calculate_bounds_callback and self._node_ids:
                bounds = self._calculate_bounds_callback(self._node_ids)

            # Create the group
            group = NodeGroup(
                group_id=self._group_id,  # Use stored ID for redo
                name=self._name,
                node_ids=set(self._node_ids),
                color=self._color,
                bounds=bounds,
            )

            # Add to graph
            self._graph.add_group(group)
            self._group_id = group.id
            self._group_data = group.to_dict()

            # Create visual widget
            if self._add_widget_callback:
                self._add_widget_callback(group)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute CreateGroupCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Remove the group from the graph."""
        if not self._group_id:
            return False

        try:
            # Remove visual widget first
            if self._remove_widget_callback:
                self._remove_widget_callback(self._group_id)

            # Remove from graph
            self._graph.remove_group(self._group_id)
            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo CreateGroupCommand", exc_info=True)
            return False

    def redo(self) -> bool:
        """Re-create the group using stored data."""
        return self.execute()

    @property
    def description(self) -> str:
        """Get command description."""
        return "Create Group"

    @property
    def group_id(self) -> Optional[str]:
        """Get the ID of the created group."""
        return self._group_id


class RemoveGroupCommand(Command):
    """
    Command to remove a node group (ungroup nodes).

    This removes the group container but keeps the nodes.
    """

    def __init__(
        self,
        graph: "Graph",
        group_id: str,
        add_widget_callback: Optional[Callable[[NodeGroup], None]] = None,
        remove_widget_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize the remove group command.

        Args:
            graph: The graph to remove the group from.
            group_id: ID of the group to remove.
            add_widget_callback: Callback to create visual widget (for undo).
            remove_widget_callback: Callback to remove visual widget.
        """
        super().__init__(graph)
        self._group_id = group_id
        self._add_widget_callback = add_widget_callback
        self._remove_widget_callback = remove_widget_callback
        self._group_data: Optional[Dict[str, Any]] = None

    def execute(self) -> bool:
        """Remove the group from the graph."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            # Store group data for undo
            self._group_data = group.to_dict()

            # Remove visual widget
            if self._remove_widget_callback:
                self._remove_widget_callback(self._group_id)

            # Remove from graph
            self._graph.remove_group(self._group_id)
            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute RemoveGroupCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Restore the group."""
        if not self._group_data:
            return False

        try:
            # Recreate the group
            group = NodeGroup.from_dict(self._group_data)
            self._graph.add_group(group)

            # Create visual widget
            if self._add_widget_callback:
                self._add_widget_callback(group)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo RemoveGroupCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        return "Ungroup"


class AddNodesToGroupCommand(Command):
    """
    Command to add nodes to an existing group.
    """

    def __init__(
        self,
        graph: "Graph",
        group_id: str,
        node_ids: List[str],
        update_widget_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize the add nodes to group command.

        Args:
            graph: The graph containing the group.
            group_id: ID of the group to add nodes to.
            node_ids: List of node IDs to add.
            update_widget_callback: Callback to update the group widget.
        """
        super().__init__(graph)
        self._group_id = group_id
        self._node_ids = node_ids.copy()
        self._update_widget_callback = update_widget_callback
        # Track which nodes were actually added (may already be in group)
        self._added_node_ids: List[str] = []

    def execute(self) -> bool:
        """Add nodes to the group."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            self._added_node_ids = []
            for node_id in self._node_ids:
                if not group.contains_node(node_id):
                    group.add_node(node_id)
                    self._added_node_ids.append(node_id)

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute AddNodesToGroupCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Remove the added nodes from the group."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            for node_id in self._added_node_ids:
                group.remove_node(node_id)

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo AddNodesToGroupCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        count = len(self._node_ids)
        return f"Add {count} Node{'s' if count != 1 else ''} to Group"


class RemoveNodesFromGroupCommand(Command):
    """
    Command to remove nodes from a group.
    """

    def __init__(
        self,
        graph: "Graph",
        group_id: str,
        node_ids: List[str],
        update_widget_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize the remove nodes from group command.

        Args:
            graph: The graph containing the group.
            group_id: ID of the group to remove nodes from.
            node_ids: List of node IDs to remove.
            update_widget_callback: Callback to update the group widget.
        """
        super().__init__(graph)
        self._group_id = group_id
        self._node_ids = node_ids.copy()
        self._update_widget_callback = update_widget_callback
        # Track which nodes were actually removed
        self._removed_node_ids: List[str] = []

    def execute(self) -> bool:
        """Remove nodes from the group."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            self._removed_node_ids = []
            for node_id in self._node_ids:
                if group.contains_node(node_id):
                    group.remove_node(node_id)
                    self._removed_node_ids.append(node_id)

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute RemoveNodesFromGroupCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Add the removed nodes back to the group."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            for node_id in self._removed_node_ids:
                group.add_node(node_id)

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo RemoveNodesFromGroupCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        count = len(self._node_ids)
        return f"Remove {count} Node{'s' if count != 1 else ''} from Group"


class RenameGroupCommand(Command):
    """
    Command to rename a group.
    """

    def __init__(
        self,
        graph: "Graph",
        group_id: str,
        old_name: str,
        new_name: str,
        update_widget_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize the rename group command.

        Args:
            graph: The graph containing the group.
            group_id: ID of the group to rename.
            old_name: Original name.
            new_name: New name.
            update_widget_callback: Callback to update the group widget.
        """
        super().__init__(graph)
        self._group_id = group_id
        self._old_name = old_name
        self._new_name = new_name
        self._update_widget_callback = update_widget_callback

    def execute(self) -> bool:
        """Rename the group."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            group.name = self._new_name

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute RenameGroupCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Restore the original name."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            group.name = self._old_name

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo RenameGroupCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        return "Rename Group"


class ToggleGroupCollapsedCommand(Command):
    """
    Command to toggle a group's collapsed state.
    """

    def __init__(
        self,
        graph: "Graph",
        group_id: str,
        update_widget_callback: Optional[Callable[[str], None]] = None,
        update_node_visibility_callback: Optional[Callable[[str, bool], None]] = None,
    ) -> None:
        """
        Initialize the toggle collapsed command.

        Args:
            graph: The graph containing the group.
            group_id: ID of the group to toggle.
            update_widget_callback: Callback to update the group widget.
            update_node_visibility_callback: Callback to show/hide contained nodes.
        """
        super().__init__(graph)
        self._group_id = group_id
        self._update_widget_callback = update_widget_callback
        self._update_node_visibility_callback = update_node_visibility_callback
        self._previous_state: Optional[bool] = None

    def execute(self) -> bool:
        """Toggle the collapsed state."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            self._previous_state = group.collapsed
            new_state = group.toggle_collapsed()

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id)

            if self._update_node_visibility_callback:
                self._update_node_visibility_callback(self._group_id, new_state)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute ToggleGroupCollapsedCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Restore the previous collapsed state."""
        try:
            if self._previous_state is None:
                return False

            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            group.collapsed = self._previous_state

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id)

            if self._update_node_visibility_callback:
                self._update_node_visibility_callback(self._group_id, self._previous_state)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo ToggleGroupCollapsedCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        return "Toggle Group Collapse"


class MoveGroupCommand(Command):
    """
    Command to move a group (and all contained nodes) to a new position.
    """

    def __init__(
        self,
        graph: "Graph",
        group_id: str,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
        update_widget_callback: Optional[Callable[[str, float, float], None]] = None,
        move_contained_nodes_callback: Optional[Callable[[str, float, float], None]] = None,
    ) -> None:
        """
        Initialize the move group command.

        Args:
            graph: The graph containing the group.
            group_id: ID of the group to move.
            old_x: Original X position.
            old_y: Original Y position.
            new_x: New X position.
            new_y: New Y position.
            update_widget_callback: Callback to update visual widget position.
            move_contained_nodes_callback: Callback to move contained nodes.
        """
        super().__init__(graph)
        self._group_id = group_id
        self._old_x = old_x
        self._old_y = old_y
        self._new_x = new_x
        self._new_y = new_y
        self._update_widget_callback = update_widget_callback
        self._move_contained_nodes_callback = move_contained_nodes_callback

    def execute(self) -> bool:
        """Move the group to the new position."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            # Calculate delta
            dx = self._new_x - self._old_x
            dy = self._new_y - self._old_y

            # Update group position
            group.bounds.x = self._new_x
            group.bounds.y = self._new_y

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id, self._new_x, self._new_y)

            if self._move_contained_nodes_callback:
                self._move_contained_nodes_callback(self._group_id, dx, dy)

            self._executed = True
            return True
        except Exception:
            logger.debug("Failed to execute MoveGroupCommand", exc_info=True)
            return False

    def undo(self) -> bool:
        """Move the group back to the original position."""
        try:
            group = self._graph.get_group(self._group_id)
            if not group:
                return False

            # Calculate delta
            dx = self._old_x - self._new_x
            dy = self._old_y - self._new_y

            # Update group position
            group.bounds.x = self._old_x
            group.bounds.y = self._old_y

            if self._update_widget_callback:
                self._update_widget_callback(self._group_id, self._old_x, self._old_y)

            if self._move_contained_nodes_callback:
                self._move_contained_nodes_callback(self._group_id, dx, dy)

            self._executed = False
            return True
        except Exception:
            logger.debug("Failed to undo MoveGroupCommand", exc_info=True)
            return False

    @property
    def description(self) -> str:
        """Get command description."""
        return "Move Group"

    def can_merge(self, other: Command) -> bool:
        """Check if we can merge with another move command for the same group."""
        if not isinstance(other, MoveGroupCommand):
            return False
        return other._group_id == self._group_id

    def merge(self, other: Command) -> bool:
        """Merge another move command, keeping original position and new end position."""
        if not isinstance(other, MoveGroupCommand):
            return False
        if other._group_id != self._group_id:
            return False

        self._new_x = other._new_x
        self._new_y = other._new_y
        return True
