"""
Clipboard manager for node copy/paste operations.

This module provides clipboard operations for copying and pasting nodes
with their connections in the visual programming system.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal
from visualpython.utils.logging import get_logger

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph
    from visualpython.nodes.models.base_node import BaseNode
    from visualpython.nodes.registry import NodeRegistry

logger = get_logger(__name__)

# Offset applied to pasted nodes to make them visible
PASTE_OFFSET_X = 40
PASTE_OFFSET_Y = 40


@dataclass
class ClipboardData:
    """
    Data structure for clipboard contents.

    Attributes:
        nodes: List of serialized node dictionaries.
        connections: List of serialized connection dictionaries (only internal connections).
    """
    nodes: List[Dict[str, Any]]
    connections: List[Dict[str, str]]

    def to_json(self) -> str:
        """Serialize to JSON string for clipboard storage."""
        return json.dumps({
            "visualpython_clipboard": True,
            "version": "1.0",
            "nodes": self.nodes,
            "connections": self.connections,
        })

    @classmethod
    def from_json(cls, json_str: str) -> Optional[ClipboardData]:
        """
        Deserialize from JSON string.

        Args:
            json_str: The JSON string from clipboard.

        Returns:
            ClipboardData if valid, None if invalid format.
        """
        try:
            data = json.loads(json_str)
            if not data.get("visualpython_clipboard"):
                return None
            return cls(
                nodes=data.get("nodes", []),
                connections=data.get("connections", []),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Failed to deserialize clipboard data", exc_info=True)
            return None


class ClipboardManager(QObject):
    """
    Manages clipboard operations for nodes in the visual programming system.

    Provides copy, cut, and paste functionality for nodes with their internal
    connections preserved. Uses the system clipboard for storage when available,
    with an internal fallback for testing.

    Signals:
        nodes_copied: Emitted when nodes are copied (count).
        nodes_cut: Emitted when nodes are cut (count).
        nodes_pasted: Emitted when nodes are pasted (list of new node IDs).
        clipboard_changed: Emitted when clipboard content changes.
    """

    nodes_copied = pyqtSignal(int)
    nodes_cut = pyqtSignal(int)
    nodes_pasted = pyqtSignal(list)
    clipboard_changed = pyqtSignal()

    def __init__(
        self,
        registry: "NodeRegistry",
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Initialize the clipboard manager.

        Args:
            registry: The node registry for creating nodes.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._registry = registry
        self._paste_count = 0  # Track consecutive pastes for offset
        self._internal_clipboard: Optional[str] = None  # Fallback for testing

    def _get_system_clipboard(self):
        """Get the Qt system clipboard, or None if not available."""
        try:
            app = QApplication.instance()
            if app is not None:
                return QApplication.clipboard()
        except Exception:
            logger.debug("System clipboard not available", exc_info=True)
        return None

    def _get_clipboard_data(self) -> Optional[ClipboardData]:
        """
        Get clipboard data from system clipboard or internal fallback.

        Returns:
            ClipboardData if valid VisualPython clipboard content, None otherwise.
        """
        text = None

        # Try system clipboard first
        clipboard = self._get_system_clipboard()
        if clipboard is not None:
            text = clipboard.text()
        else:
            # Fall back to internal clipboard
            text = self._internal_clipboard

        if not text:
            return None

        return ClipboardData.from_json(text)

    def _set_clipboard_data(self, data: ClipboardData) -> None:
        """
        Store clipboard data to system clipboard or internal fallback.

        Args:
            data: The clipboard data to store.
        """
        json_str = data.to_json()

        # Try system clipboard first
        clipboard = self._get_system_clipboard()
        if clipboard is not None:
            clipboard.setText(json_str)
        else:
            # Fall back to internal clipboard
            self._internal_clipboard = json_str

        self._paste_count = 0  # Reset paste count on new copy
        self.clipboard_changed.emit()

    def has_clipboard_content(self) -> bool:
        """
        Check if there is valid VisualPython content in the clipboard.

        Returns:
            True if clipboard contains valid node data.
        """
        return self._get_clipboard_data() is not None

    def get_clipboard_node_count(self) -> int:
        """
        Get the number of nodes currently in the clipboard.

        Returns:
            Number of nodes, or 0 if clipboard is empty/invalid.
        """
        data = self._get_clipboard_data()
        return len(data.nodes) if data else 0

    def copy_nodes(
        self,
        graph: "Graph",
        node_ids: List[str],
    ) -> int:
        """
        Copy selected nodes and their internal connections to clipboard.

        Args:
            graph: The graph containing the nodes.
            node_ids: List of node IDs to copy.

        Returns:
            Number of nodes copied.
        """
        if not node_ids:
            return 0

        node_ids_set = set(node_ids)

        # Serialize nodes
        serialized_nodes: List[Dict[str, Any]] = []
        for node_id in node_ids:
            node = graph.get_node(node_id)
            if node:
                serialized_nodes.append(node.to_dict())

        if not serialized_nodes:
            return 0

        # Get only internal connections (both source and target in selection)
        serialized_connections: List[Dict[str, str]] = []
        for connection in graph.connections:
            if (connection.source_node_id in node_ids_set and
                connection.target_node_id in node_ids_set):
                serialized_connections.append(connection.to_dict())

        # Store to clipboard
        clipboard_data = ClipboardData(
            nodes=serialized_nodes,
            connections=serialized_connections,
        )
        self._set_clipboard_data(clipboard_data)

        count = len(serialized_nodes)
        self.nodes_copied.emit(count)
        return count

    def cut_nodes(
        self,
        graph: "Graph",
        node_ids: List[str],
        delete_callback: callable,
    ) -> int:
        """
        Cut selected nodes (copy and delete).

        Args:
            graph: The graph containing the nodes.
            node_ids: List of node IDs to cut.
            delete_callback: Callback function to delete nodes (takes node_id).

        Returns:
            Number of nodes cut.
        """
        count = self.copy_nodes(graph, node_ids)
        if count > 0:
            # Delete nodes after copying
            for node_id in node_ids:
                delete_callback(node_id)
            self.nodes_cut.emit(count)
        return count

    def paste_nodes(
        self,
        graph: "Graph",
        add_node_callback: callable,
        add_connection_callback: callable,
    ) -> List[str]:
        """
        Paste nodes from clipboard into the graph.

        Creates new nodes with new IDs at offset positions and recreates
        internal connections between them.

        Args:
            graph: The target graph.
            add_node_callback: Callback to add a node (takes node).
            add_connection_callback: Callback to add a connection
                (takes source_id, source_port, target_id, target_port).

        Returns:
            List of newly created node IDs.
        """
        clipboard_data = self._get_clipboard_data()
        if not clipboard_data or not clipboard_data.nodes:
            return []

        # Increment paste count for progressive offset
        self._paste_count += 1
        offset_x = PASTE_OFFSET_X * self._paste_count
        offset_y = PASTE_OFFSET_Y * self._paste_count

        # Map old node IDs to new node IDs
        id_mapping: Dict[str, str] = {}
        new_node_ids: List[str] = []

        # Create new nodes
        for node_data in clipboard_data.nodes:
            old_id = node_data.get("id")
            node_type = node_data.get("type")

            if not old_id or not node_type:
                continue

            # Generate new ID
            new_id = str(uuid.uuid4())
            id_mapping[old_id] = new_id

            # Create new node data with updated ID and position
            new_node_data = node_data.copy()
            new_node_data["id"] = new_id

            # Offset position
            if "position" in new_node_data:
                new_node_data["position"] = {
                    "x": new_node_data["position"].get("x", 0) + offset_x,
                    "y": new_node_data["position"].get("y", 0) + offset_y,
                }

            # Clear port connections (we'll recreate them)
            for port_data in new_node_data.get("input_ports", []):
                port_data["connection"] = None
            for port_data in new_node_data.get("output_ports", []):
                port_data["connections"] = []

            # Create the node using the registry
            node = self._create_node_from_dict(new_node_data)
            if node:
                add_node_callback(node)
                new_node_ids.append(new_id)

        # Recreate connections with new IDs
        for conn_data in clipboard_data.connections:
            old_source_id = conn_data.get("source_node_id")
            old_target_id = conn_data.get("target_node_id")

            # Only create connection if both nodes were pasted
            if old_source_id in id_mapping and old_target_id in id_mapping:
                new_source_id = id_mapping[old_source_id]
                new_target_id = id_mapping[old_target_id]

                add_connection_callback(
                    new_source_id,
                    conn_data.get("source_port_name"),
                    new_target_id,
                    conn_data.get("target_port_name"),
                )

        if new_node_ids:
            self.nodes_pasted.emit(new_node_ids)

        return new_node_ids

    def _create_node_from_dict(
        self,
        node_data: Dict[str, Any],
    ) -> Optional["BaseNode"]:
        """
        Create a node instance from serialized dictionary data.

        Args:
            node_data: Serialized node dictionary.

        Returns:
            New node instance, or None if creation failed.
        """
        from visualpython.nodes.models.base_node import Position

        node_type = node_data.get("type")
        if not node_type:
            return None

        position_data = node_data.get("position", {})
        position = Position(
            x=position_data.get("x", 0),
            y=position_data.get("y", 0),
        )

        # Create the node
        node = self._registry.create_node(
            node_type=node_type,
            node_id=node_data.get("id"),
            name=node_data.get("name"),
            position=position,
        )

        # Load additional properties if node was created
        if node and "properties" in node_data:
            node._load_serializable_properties(node_data["properties"])

        return node

    def clear(self) -> None:
        """Clear the clipboard content."""
        # Clear system clipboard if available
        clipboard = self._get_system_clipboard()
        if clipboard is not None:
            clipboard.clear()

        # Always clear internal clipboard
        self._internal_clipboard = None
        self._paste_count = 0
        self.clipboard_changed.emit()
