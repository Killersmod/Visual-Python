"""
Selection manager for node graph items.

This module provides centralized management of selection state for nodes and
connections in the graph, supporting single and multi-select with keyboard
modifiers.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import List, Optional, Set, TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6 import sip
from visualpython.utils.logging import get_logger

if TYPE_CHECKING:
    from visualpython.nodes.views.node_widget import NodeWidget
    from visualpython.graph.connection_widget import ConnectionWidget
    from visualpython.graph.scene import NodeGraphScene

logger = get_logger(__name__)


class SelectionMode(Enum):
    """Selection mode based on keyboard modifiers."""

    REPLACE = auto()  # Default: replace current selection
    TOGGLE = auto()   # Ctrl: toggle item in selection
    EXTEND = auto()   # Shift: extend selection (range select)
    ADD = auto()      # Ctrl+Shift: add to selection without toggle


class SelectionManager(QObject):
    """
    Centralized manager for graph item selection.

    Handles single and multi-select for nodes with keyboard modifier support,
    tracks selection state, and emits signals for selection changes.

    Signals:
        selection_changed: Emitted when selection changes (list of selected node IDs).
        nodes_selected: Emitted when nodes are selected (list of node IDs).
        nodes_deselected: Emitted when nodes are deselected (list of node IDs).
        selection_cleared: Emitted when all selection is cleared.

    Attributes:
        _scene: The NodeGraphScene being managed.
        _selected_node_ids: Set of currently selected node IDs.
        _last_selected_node_id: The most recently selected node (for range selection).
        _selection_anchor_id: The anchor node for range selection.
    """

    selection_changed = pyqtSignal(list)  # List[str] of node IDs
    nodes_selected = pyqtSignal(list)     # List[str] of newly selected node IDs
    nodes_deselected = pyqtSignal(list)   # List[str] of deselected node IDs
    selection_cleared = pyqtSignal()

    def __init__(
        self,
        scene: Optional["NodeGraphScene"] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Initialize the selection manager.

        Args:
            scene: The NodeGraphScene to manage selection for.
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self._scene = scene
        self._selected_node_ids: Set[str] = set()
        self._last_selected_node_id: Optional[str] = None
        self._selection_anchor_id: Optional[str] = None

    def set_scene(self, scene: "NodeGraphScene") -> None:
        """
        Set the scene to manage selection for.

        Args:
            scene: The NodeGraphScene to manage.
        """
        self._scene = scene

    @property
    def selected_node_ids(self) -> List[str]:
        """Get list of selected node IDs."""
        return list(self._selected_node_ids)

    @property
    def selected_count(self) -> int:
        """Get the number of selected nodes."""
        return len(self._selected_node_ids)

    @property
    def has_selection(self) -> bool:
        """Check if any nodes are selected."""
        return len(self._selected_node_ids) > 0

    @property
    def last_selected_node_id(self) -> Optional[str]:
        """Get the most recently selected node ID."""
        return self._last_selected_node_id

    def is_selected(self, node_id: str) -> bool:
        """
        Check if a node is selected.

        Args:
            node_id: The ID of the node to check.

        Returns:
            True if the node is selected.
        """
        return node_id in self._selected_node_ids

    def select_node(
        self,
        node_id: str,
        mode: SelectionMode = SelectionMode.REPLACE,
    ) -> None:
        """
        Select a node with the specified selection mode.

        Args:
            node_id: The ID of the node to select.
            mode: The selection mode to use.
        """
        if self._scene is None or sip.isdeleted(self._scene):
            return

        try:
            widget = self._scene.get_node_widget(node_id)
        except RuntimeError:
            # Scene was deleted during the call
            logger.debug("Scene C++ object deleted during select_node", exc_info=True)
            return
        if widget is None:
            return

        previously_selected = set(self._selected_node_ids)

        if mode == SelectionMode.REPLACE:
            # Clear all other selections and select this node
            self._clear_selection_internal()
            self._select_node_internal(node_id, widget)
            self._selection_anchor_id = node_id

        elif mode == SelectionMode.TOGGLE:
            # Toggle this node's selection state
            if node_id in self._selected_node_ids:
                self._deselect_node_internal(node_id, widget)
            else:
                self._select_node_internal(node_id, widget)
                self._selection_anchor_id = node_id

        elif mode == SelectionMode.EXTEND:
            # Range select from anchor to this node
            if self._selection_anchor_id:
                self._range_select(self._selection_anchor_id, node_id)
            else:
                self._select_node_internal(node_id, widget)
                self._selection_anchor_id = node_id

        elif mode == SelectionMode.ADD:
            # Add to selection without toggle
            if node_id not in self._selected_node_ids:
                self._select_node_internal(node_id, widget)

        self._last_selected_node_id = node_id
        self._emit_selection_changes(previously_selected)

    def select_nodes(
        self,
        node_ids: List[str],
        mode: SelectionMode = SelectionMode.REPLACE,
    ) -> None:
        """
        Select multiple nodes with the specified selection mode.

        Args:
            node_ids: List of node IDs to select.
            mode: The selection mode to use.
        """
        if self._scene is None or sip.isdeleted(self._scene) or not node_ids:
            return

        previously_selected = set(self._selected_node_ids)

        try:
            if mode == SelectionMode.REPLACE:
                # Clear all and select the specified nodes
                self._clear_selection_internal()
                for node_id in node_ids:
                    widget = self._scene.get_node_widget(node_id)
                    if widget:
                        self._select_node_internal(node_id, widget)
                if node_ids:
                    self._selection_anchor_id = node_ids[0]
                    self._last_selected_node_id = node_ids[-1]

            elif mode == SelectionMode.TOGGLE:
                # Toggle each node's selection
                for node_id in node_ids:
                    widget = self._scene.get_node_widget(node_id)
                    if widget:
                        if node_id in self._selected_node_ids:
                            self._deselect_node_internal(node_id, widget)
                        else:
                            self._select_node_internal(node_id, widget)

            elif mode in (SelectionMode.ADD, SelectionMode.EXTEND):
                # Add all nodes to selection
                for node_id in node_ids:
                    widget = self._scene.get_node_widget(node_id)
                    if widget and node_id not in self._selected_node_ids:
                        self._select_node_internal(node_id, widget)
        except RuntimeError:
            # Scene was deleted during the call
            logger.debug("Scene C++ object deleted during select_nodes", exc_info=True)
            return

        self._emit_selection_changes(previously_selected)

    def deselect_node(self, node_id: str) -> None:
        """
        Deselect a specific node.

        Args:
            node_id: The ID of the node to deselect.
        """
        if self._scene is None or sip.isdeleted(self._scene):
            return

        try:
            widget = self._scene.get_node_widget(node_id)
        except RuntimeError:
            # Scene was deleted during the call
            logger.debug("Scene C++ object deleted during deselect_node", exc_info=True)
            return

        if widget and node_id in self._selected_node_ids:
            previously_selected = set(self._selected_node_ids)
            self._deselect_node_internal(node_id, widget)
            self._emit_selection_changes(previously_selected)

    def clear_selection(self) -> None:
        """Clear all selection."""
        if not self._selected_node_ids:
            return

        previously_selected = set(self._selected_node_ids)
        self._clear_selection_internal()
        self._selection_anchor_id = None
        self._last_selected_node_id = None
        self._emit_selection_changes(previously_selected)
        self.selection_cleared.emit()

    def select_all(self) -> None:
        """Select all nodes in the scene."""
        if self._scene is None or sip.isdeleted(self._scene):
            return

        try:
            previously_selected = set(self._selected_node_ids)
            for widget in self._scene.get_all_node_widgets():
                self._select_node_internal(widget.node_id, widget)
        except RuntimeError:
            # Scene was deleted during the call
            logger.debug("Scene C++ object deleted during select_all", exc_info=True)
            return

        self._emit_selection_changes(previously_selected)

    def invert_selection(self) -> None:
        """Invert the current selection."""
        if self._scene is None or sip.isdeleted(self._scene):
            return

        try:
            previously_selected = set(self._selected_node_ids)
            all_widgets = self._scene.get_all_node_widgets()

            for widget in all_widgets:
                node_id = widget.node_id
                if node_id in self._selected_node_ids:
                    self._deselect_node_internal(node_id, widget)
                else:
                    self._select_node_internal(node_id, widget)
        except RuntimeError:
            # Scene was deleted during the call
            logger.debug("Scene C++ object deleted during invert_selection", exc_info=True)
            return

        self._emit_selection_changes(previously_selected)

    def get_selected_node_widgets(self) -> List["NodeWidget"]:
        """
        Get all selected node widgets.

        Returns:
            List of selected NodeWidget instances.
        """
        if self._scene is None or sip.isdeleted(self._scene):
            return []

        widgets = []
        try:
            for node_id in self._selected_node_ids:
                widget = self._scene.get_node_widget(node_id)
                if widget:
                    widgets.append(widget)
        except RuntimeError:
            # Scene was deleted during the call
            logger.debug("Scene C++ object deleted during get_selected_node_widgets", exc_info=True)
            return []
        return widgets

    def sync_from_scene(self) -> None:
        """
        Synchronize selection state from the scene's actual selection.

        This should be called after rubber-band selection or other
        scene-level selection changes.
        """
        if self._scene is None:
            return

        # Check if the scene's C++ object has been deleted
        if sip.isdeleted(self._scene):
            return

        previously_selected = set(self._selected_node_ids)

        # Get actually selected items from scene
        try:
            selected_widgets = self._scene.get_selected_node_widgets()
        except RuntimeError:
            # Scene was deleted during the call
            logger.debug("Scene C++ object deleted during sync_from_scene", exc_info=True)
            return

        new_selected = {w.node_id for w in selected_widgets}

        self._selected_node_ids = new_selected

        if new_selected:
            # Update anchor to first selected if not already in selection
            if self._selection_anchor_id not in new_selected:
                self._selection_anchor_id = next(iter(new_selected))
            self._last_selected_node_id = next(iter(new_selected))

        self._emit_selection_changes(previously_selected)

    def _select_node_internal(
        self, node_id: str, widget: "NodeWidget"
    ) -> None:
        """Internal method to select a node without emitting signals."""
        self._selected_node_ids.add(node_id)
        widget.setSelected(True)

    def _deselect_node_internal(
        self, node_id: str, widget: "NodeWidget"
    ) -> None:
        """Internal method to deselect a node without emitting signals."""
        self._selected_node_ids.discard(node_id)
        widget.setSelected(False)

    def _clear_selection_internal(self) -> None:
        """Internal method to clear all selection without emitting signals."""
        if self._scene is None or sip.isdeleted(self._scene):
            self._selected_node_ids.clear()
            return

        try:
            for node_id in list(self._selected_node_ids):
                widget = self._scene.get_node_widget(node_id)
                if widget:
                    widget.setSelected(False)
        except RuntimeError:
            # Scene was deleted during the call
            logger.debug("Scene C++ object deleted during _clear_selection_internal", exc_info=True)
        self._selected_node_ids.clear()

    def _range_select(self, anchor_id: str, target_id: str) -> None:
        """
        Perform range selection between anchor and target nodes.

        For now, this selects all nodes between the anchor and target
        based on their vertical position (top to bottom).

        Args:
            anchor_id: The anchor node ID.
            target_id: The target node ID.
        """
        if self._scene is None or sip.isdeleted(self._scene):
            return

        try:
            anchor_widget = self._scene.get_node_widget(anchor_id)
            target_widget = self._scene.get_node_widget(target_id)

            if not anchor_widget or not target_widget:
                return

            # Get positions
            anchor_pos = anchor_widget.pos()
            target_pos = target_widget.pos()

            # Determine bounding box for range selection
            min_y = min(anchor_pos.y(), target_pos.y())
            max_y = max(anchor_pos.y(), target_pos.y()) + max(
                anchor_widget.height, target_widget.height
            )
            min_x = min(anchor_pos.x(), target_pos.x())
            max_x = max(anchor_pos.x(), target_pos.x()) + max(
                anchor_widget.width, target_widget.width
            )

            # Select all nodes within the bounding box
            for widget in self._scene.get_all_node_widgets():
                pos = widget.pos()
                # Check if node center is within the range
                center_x = pos.x() + widget.width / 2
                center_y = pos.y() + widget.height / 2

                if min_x <= center_x <= max_x and min_y <= center_y <= max_y:
                    self._select_node_internal(widget.node_id, widget)
        except RuntimeError:
            # Scene was deleted during the call
            logger.debug("Scene C++ object deleted during _range_select", exc_info=True)
            return

    def _emit_selection_changes(self, previously_selected: Set[str]) -> None:
        """
        Emit selection change signals based on the difference.

        Args:
            previously_selected: Set of previously selected node IDs.
        """
        # Compute differences
        newly_selected = self._selected_node_ids - previously_selected
        newly_deselected = previously_selected - self._selected_node_ids

        # Emit signals
        if newly_selected:
            self.nodes_selected.emit(list(newly_selected))
        if newly_deselected:
            self.nodes_deselected.emit(list(newly_deselected))
        if newly_selected or newly_deselected:
            self.selection_changed.emit(list(self._selected_node_ids))
