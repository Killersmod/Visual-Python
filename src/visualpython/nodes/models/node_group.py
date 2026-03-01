"""
Node group model for organizing nodes into collapsible containers.

This module provides the NodeGroup class that allows users to group multiple
nodes into a container, reducing visual complexity of large graphs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode, Position


@dataclass
class GroupBounds:
    """Represents the bounding rectangle of a group."""

    x: float = 0.0
    y: float = 0.0
    width: float = 200.0
    height: float = 150.0

    def to_dict(self) -> Dict[str, float]:
        """Convert bounds to dictionary for serialization."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "GroupBounds":
        """Create GroupBounds from a dictionary."""
        return cls(
            x=data.get("x", 0.0),
            y=data.get("y", 0.0),
            width=data.get("width", 200.0),
            height=data.get("height", 150.0),
        )


class NodeGroup:
    """
    A container for organizing multiple nodes into a collapsible group.

    Node groups provide visual organization for complex graphs by:
    - Grouping related nodes into a named container
    - Allowing collapse/expand to reduce visual complexity
    - Providing a distinct visual boundary around contained nodes
    - Supporting drag-to-move all contained nodes together

    Attributes:
        id: Unique identifier for this group.
        name: Display name shown on the group header.
        node_ids: Set of node IDs contained in this group.
        collapsed: Whether the group is currently collapsed.
        color: Custom color for the group header (hex string).
        bounds: The bounding rectangle of the group.
    """

    # Default group color
    DEFAULT_COLOR = "#5C6BC0"  # Indigo

    def __init__(
        self,
        group_id: Optional[str] = None,
        name: str = "Group",
        node_ids: Optional[Set[str]] = None,
        collapsed: bool = False,
        color: Optional[str] = None,
        bounds: Optional[GroupBounds] = None,
    ) -> None:
        """
        Initialize a new node group.

        Args:
            group_id: Optional unique identifier. If not provided, a UUID is generated.
            name: Display name for the group.
            node_ids: Optional set of node IDs to include in the group.
            collapsed: Initial collapsed state.
            color: Optional custom color (hex string).
            bounds: Optional initial bounds.
        """
        self._id: str = group_id or str(uuid.uuid4())
        self._name: str = name
        self._node_ids: Set[str] = node_ids.copy() if node_ids else set()
        self._collapsed: bool = collapsed
        self._color: str = color or self.DEFAULT_COLOR
        self._bounds: GroupBounds = bounds or GroupBounds()

        # Comment/description for the group
        self._description: str = ""

    # Properties

    @property
    def id(self) -> str:
        """Get the unique identifier for this group."""
        return self._id

    @property
    def name(self) -> str:
        """Get the display name of this group."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set the display name of this group."""
        self._name = value if value else "Group"

    @property
    def node_ids(self) -> Set[str]:
        """Get the set of node IDs in this group."""
        return self._node_ids.copy()

    @property
    def node_count(self) -> int:
        """Get the number of nodes in this group."""
        return len(self._node_ids)

    @property
    def is_empty(self) -> bool:
        """Check if the group has no nodes."""
        return len(self._node_ids) == 0

    @property
    def collapsed(self) -> bool:
        """Check if the group is collapsed."""
        return self._collapsed

    @collapsed.setter
    def collapsed(self, value: bool) -> None:
        """Set the collapsed state of the group."""
        self._collapsed = value

    @property
    def color(self) -> str:
        """Get the group header color."""
        return self._color

    @color.setter
    def color(self, value: str) -> None:
        """Set the group header color."""
        self._color = value if value else self.DEFAULT_COLOR

    @property
    def bounds(self) -> GroupBounds:
        """Get the bounding rectangle of the group."""
        return self._bounds

    @bounds.setter
    def bounds(self, value: GroupBounds) -> None:
        """Set the bounding rectangle of the group."""
        self._bounds = value

    @property
    def description(self) -> str:
        """Get the description/comment for this group."""
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        """Set the description/comment for this group."""
        self._description = value if value else ""

    # Node management methods

    def add_node(self, node_id: str) -> None:
        """
        Add a node to this group.

        Args:
            node_id: The ID of the node to add.
        """
        self._node_ids.add(node_id)

    def remove_node(self, node_id: str) -> bool:
        """
        Remove a node from this group.

        Args:
            node_id: The ID of the node to remove.

        Returns:
            True if the node was removed, False if it wasn't in the group.
        """
        if node_id in self._node_ids:
            self._node_ids.discard(node_id)
            return True
        return False

    def contains_node(self, node_id: str) -> bool:
        """
        Check if a node is in this group.

        Args:
            node_id: The ID of the node to check.

        Returns:
            True if the node is in this group.
        """
        return node_id in self._node_ids

    def add_nodes(self, node_ids: List[str]) -> None:
        """
        Add multiple nodes to this group.

        Args:
            node_ids: List of node IDs to add.
        """
        self._node_ids.update(node_ids)

    def remove_nodes(self, node_ids: List[str]) -> int:
        """
        Remove multiple nodes from this group.

        Args:
            node_ids: List of node IDs to remove.

        Returns:
            Number of nodes removed.
        """
        count = 0
        for node_id in node_ids:
            if node_id in self._node_ids:
                self._node_ids.discard(node_id)
                count += 1
        return count

    def clear_nodes(self) -> None:
        """Remove all nodes from this group."""
        self._node_ids.clear()

    # Collapse/expand methods

    def toggle_collapsed(self) -> bool:
        """
        Toggle the collapsed state.

        Returns:
            The new collapsed state.
        """
        self._collapsed = not self._collapsed
        return self._collapsed

    def expand(self) -> None:
        """Expand the group (show all nodes)."""
        self._collapsed = False

    def collapse(self) -> None:
        """Collapse the group (hide nodes)."""
        self._collapsed = True

    # Bounds calculation

    def calculate_bounds_from_nodes(
        self,
        nodes: List["BaseNode"],
        padding: float = 40.0,
        header_height: float = 32.0,
    ) -> GroupBounds:
        """
        Calculate the group bounds based on contained node positions.

        Args:
            nodes: List of node objects that are in this group.
            padding: Padding around the nodes.
            header_height: Height of the group header.

        Returns:
            Calculated GroupBounds.
        """
        if not nodes:
            return self._bounds

        # Find the bounding box of all nodes
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        # Assume typical node size (will be refined when we have actual widgets)
        node_width = 150.0
        node_height = 100.0

        for node in nodes:
            x = node.position.x
            y = node.position.y

            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + node_width)
            max_y = max(max_y, y + node_height)

        # Add padding and header space
        self._bounds = GroupBounds(
            x=min_x - padding,
            y=min_y - padding - header_height,
            width=max_x - min_x + padding * 2,
            height=max_y - min_y + padding * 2 + header_height,
        )

        return self._bounds

    # Serialization methods

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the group to a dictionary for JSON storage.

        Returns:
            Dictionary representation of the group.
        """
        data = {
            "id": self._id,
            "name": self._name,
            "node_ids": list(self._node_ids),
            "collapsed": self._collapsed,
            "color": self._color,
            "bounds": self._bounds.to_dict(),
        }
        # Only include description if set
        if self._description:
            data["description"] = self._description
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeGroup":
        """
        Deserialize a group from a dictionary.

        Args:
            data: Dictionary containing group data.

        Returns:
            A new NodeGroup instance.
        """
        bounds = None
        if "bounds" in data:
            bounds = GroupBounds.from_dict(data["bounds"])

        group = cls(
            group_id=data.get("id"),
            name=data.get("name", "Group"),
            node_ids=set(data.get("node_ids", [])),
            collapsed=data.get("collapsed", False),
            color=data.get("color"),
            bounds=bounds,
        )

        if "description" in data:
            group._description = data["description"]

        return group

    # String representations

    def __repr__(self) -> str:
        """Get a detailed string representation."""
        return (
            f"NodeGroup("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"nodes={len(self._node_ids)}, "
            f"collapsed={self._collapsed})"
        )

    def __str__(self) -> str:
        """Get a simple string representation."""
        state = "collapsed" if self._collapsed else "expanded"
        return f"Group '{self._name}' ({len(self._node_ids)} nodes, {state})"

    def __eq__(self, other: object) -> bool:
        """Check equality based on group ID."""
        if not isinstance(other, NodeGroup):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        """Hash based on group ID."""
        return hash(self._id)
