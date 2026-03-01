"""
Node graph view for displaying and interacting with the node graph canvas.

This module provides the QGraphicsView subclass that handles user interaction
with the node graph including panning, zooming, and viewport management.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QWheelEvent, QMouseEvent, QKeyEvent, QAction
from PyQt6.QtWidgets import QGraphicsView, QMenu
from PyQt6 import sip
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

from visualpython.graph.scene import NodeGraphScene
from visualpython.graph.selection_manager import SelectionManager, SelectionMode
from visualpython.ui.panels.node_palette import NODE_MIME_TYPE
from visualpython.ui.panels.workflow_library_panel import WORKFLOW_MIME_TYPE
from visualpython.nodes.models.port import are_types_compatible

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget
    from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QContextMenuEvent
    from visualpython.nodes.views.port_widget import PortWidget
    from visualpython.nodes.views.node_widget import NodeWidget
    from visualpython.graph.connection_widget import ConnectionWidget
    from visualpython.graph.graph import Graph


class NodeGraphView(QGraphicsView):
    """
    Graphics view for the node graph editor.

    Provides viewport management, pan/zoom functionality, and user interaction
    handling for the node graph canvas.

    Signals:
        zoom_changed: Emitted when the zoom level changes (new zoom factor).
        view_panned: Emitted when the view is panned.
        selection_changed: Emitted when node selection changes (list of node IDs).

    Attributes:
        MIN_ZOOM: Minimum zoom level (zoom out limit).
        MAX_ZOOM: Maximum zoom level (zoom in limit).
        ZOOM_STEP: Zoom factor multiplier per step.
        DEFAULT_ZOOM: Default zoom level (1.0 = 100%).
    """

    MIN_ZOOM = 0.1
    MAX_ZOOM = 5.0
    ZOOM_STEP = 1.15
    DEFAULT_ZOOM = 1.0

    zoom_changed = pyqtSignal(float)
    view_panned = pyqtSignal()
    node_dropped = pyqtSignal(str, float, float)  # node_type, scene_x, scene_y
    workflow_dropped = pyqtSignal(str, float, float)  # file_path, scene_x, scene_y
    connection_requested = pyqtSignal(object, object)  # source_port_widget, target_port_widget
    selection_changed = pyqtSignal(list)  # List of selected node IDs
    create_subworkflow_requested = pyqtSignal()  # Request to create subworkflow from selection
    group_nodes_requested = pyqtSignal(list)  # List of node IDs to group
    edit_code_requested = pyqtSignal(str)  # node_id - Request to edit code for a Code node

    def __init__(
        self,
        scene: Optional[NodeGraphScene] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the node graph view.

        Args:
            scene: Optional NodeGraphScene to display. Creates one if not provided.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        # Create scene if not provided
        if scene is None:
            scene = NodeGraphScene()
        self.setScene(scene)

        # Zoom tracking
        self._zoom_level = self.DEFAULT_ZOOM

        # Pan state
        self._is_panning = False
        self._pan_start_pos = QPointF()

        # Connection drawing state
        self._is_drawing_connection = False
        self._connection_source_port: Optional["PortWidget"] = None
        self._is_connection_from_output = True
        self._highlighted_port: Optional["PortWidget"] = None  # Track highlighted port during drag
        self._handled_connection_press = False  # Track if we handled a connection click
        self._clicked_connection: Optional["ConnectionWidget"] = None  # Last left-clicked connection
        self._custom_selecting = False  # Guard: suppress sync_from_scene during custom selection

        # Selection manager
        self._selection_manager = SelectionManager(scene)
        self._selection_manager.selection_changed.connect(self._on_selection_manager_changed)

        # Connect scene selection changes to sync with manager
        scene.selectionChanged.connect(self._on_scene_selection_changed)

        # Configure view
        self._setup_view()

    def _setup_view(self) -> None:
        """Configure view settings for optimal node graph editing."""
        # Rendering settings
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Viewport settings
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Transform settings
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # Interaction settings
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        # Performance optimization
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)

        # Enable keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Install app-level event filter for Delete key on connections
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
            logger.info("Event filter installed in _setup_view for Delete key")
        else:
            logger.warning("QApplication.instance() is None — event filter NOT installed")
        self._event_filter_installed = True

        # Enable drop events
        self.setAcceptDrops(True)

        # Center on origin
        self.centerOn(0, 0)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Handle mouse wheel events for zooming.

        Args:
            event: The wheel event.
        """
        # Check for Ctrl modifier for alternative zoom behavior
        # Default: zoom with wheel, pan with Ctrl+wheel
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Pass to parent for horizontal scrolling
            super().wheelEvent(event)
            return

        # Calculate zoom factor
        delta = event.angleDelta().y()

        if delta > 0:
            # Zoom in
            factor = self.ZOOM_STEP
        elif delta < 0:
            # Zoom out
            factor = 1.0 / self.ZOOM_STEP
        else:
            return

        # Apply zoom with limits
        self._apply_zoom(factor)

    def _apply_zoom(self, factor: float) -> None:
        """
        Apply a zoom factor with limit checking.

        Args:
            factor: The zoom factor to apply.
        """
        new_zoom = self._zoom_level * factor

        # Clamp to limits
        if new_zoom < self.MIN_ZOOM:
            factor = self.MIN_ZOOM / self._zoom_level
            new_zoom = self.MIN_ZOOM
        elif new_zoom > self.MAX_ZOOM:
            factor = self.MAX_ZOOM / self._zoom_level
            new_zoom = self.MAX_ZOOM

        # Apply transformation if zoom changed
        if abs(new_zoom - self._zoom_level) > 0.001:
            self._zoom_level = new_zoom
            self.scale(factor, factor)
            self.zoom_changed.emit(self._zoom_level)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press events for panning, connection drawing, and selection.

        Supports keyboard modifiers for selection:
        - No modifier: Replace selection (single select)
        - Ctrl: Toggle item in selection (multi-select)
        - Shift: Extend selection (range select)
        - Ctrl+Shift: Add to selection

        Args:
            event: The mouse event.
        """
        # Middle mouse button or Space + Left click for panning
        if event.button() == Qt.MouseButton.MiddleButton:
            self._start_panning(event)
        elif (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            # Alt+Left click for panning (alternative method)
            self._start_panning(event)
        elif event.button() == Qt.MouseButton.LeftButton:
            # Check if we clicked on a port widget
            port_widget = self._get_port_widget_at(event.position())
            if port_widget:
                logger.info("LEFT-CLICK: on port widget %s", port_widget)
                self._start_connection_drawing(port_widget)
                event.accept()
            else:
                # Check if we clicked on a node widget for custom selection handling
                node_widget = self._get_node_widget_at(event.position())
                if node_widget:
                    logger.info("LEFT-CLICK: on node %s", node_widget.node_id)
                    self._clicked_connection = None
                    # Determine selection mode from modifiers
                    mode = self._get_selection_mode_from_modifiers(event.modifiers())

                    # Guard: prevent sync_from_scene from overwriting
                    # our selection when super() triggers scene changes.
                    self._custom_selecting = True
                    try:
                        self._selection_manager.select_node(node_widget.node_id, mode)
                        event.accept()
                        # Still call super for drag handling
                        super().mousePressEvent(event)
                        # Re-apply scene selection after super() cleared it.
                        # This keeps the scene and selection manager in sync
                        # so that later sync_from_scene (e.g. on mouse release)
                        # sees the correct state.
                        for nid in self._selection_manager.selected_node_ids:
                            w = self.graph_scene.get_node_widget(nid)
                            if w:
                                w.setSelected(True)
                        logger.info(
                            "LEFT-CLICK: after reapply, selected_ids=%s",
                            self._selection_manager.selected_node_ids,
                        )
                    finally:
                        self._custom_selecting = False
                else:
                    # Check if we clicked on a connection line
                    conn_widget = self._get_connection_widget_at(event.position())
                    if conn_widget:
                        logger.info("LEFT-CLICK: on connection %s", conn_widget)
                        # Clear node selection
                        self._selection_manager.clear_selection()
                        # Handle connection selection with modifier support
                        has_ctrl = bool(
                            event.modifiers()
                            & Qt.KeyboardModifier.ControlModifier
                        )
                        if has_ctrl:
                            conn_widget.setSelected(not conn_widget.isSelected())
                        else:
                            for item in self.graph_scene.selectedItems():
                                item.setSelected(False)
                            conn_widget.setSelected(True)
                        self.graph_scene.setFocusItem(conn_widget)
                        self._clicked_connection = conn_widget
                        self._handled_connection_press = True
                        # Give the view keyboard focus so keyPressEvent fires
                        self.setFocus(Qt.FocusReason.MouseFocusReason)
                        logger.info("LEFT-CLICK conn: setFocus called, hasFocus=%s", self.hasFocus())
                        event.accept()
                    else:
                        # Clicked on empty space - let rubber band handle it
                        logger.info("LEFT-CLICK: on empty space")
                        self._clicked_connection = None
                        # Clear selection if no modifiers
                        if not (event.modifiers() & (
                            Qt.KeyboardModifier.ControlModifier |
                            Qt.KeyboardModifier.ShiftModifier
                        )):
                            self._selection_manager.clear_selection()
                        super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse move events for panning and connection drawing.

        Args:
            event: The mouse event.
        """
        if self._is_panning:
            # Calculate delta
            delta = event.position() - self._pan_start_pos
            self._pan_start_pos = event.position()

            # Pan the view
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            self.view_panned.emit()
        elif self._is_drawing_connection:
            # Update temporary connection to follow mouse
            scene_pos = self.mapToScene(event.position().toPoint())
            self.graph_scene.update_temp_connection(scene_pos)

            # Check if hovering over a port and update visual feedback
            self._update_connection_compatibility_feedback(event.position())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse release events to stop panning or complete connection.

        Args:
            event: The mouse event.
        """
        if event.button() == Qt.MouseButton.MiddleButton and self._is_panning:
            self._stop_panning()
        elif event.button() == Qt.MouseButton.LeftButton and self._is_panning:
            self._stop_panning()
        elif event.button() == Qt.MouseButton.LeftButton and self._is_drawing_connection:
            # Check if we released on a compatible port
            target_port_widget = self._get_port_widget_at(event.position())
            self._finish_connection_drawing(target_port_widget)
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton and self._handled_connection_press:
            # Don't forward release to super after a connection click;
            # super would send a scene event that clears the connection's selection
            self._handled_connection_press = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _start_panning(self, event: QMouseEvent) -> None:
        """
        Start panning the view.

        Args:
            event: The mouse event that triggered panning.
        """
        self._is_panning = True
        self._pan_start_pos = event.position()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def _stop_panning(self) -> None:
        """Stop panning the view."""
        self._is_panning = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        Handle key press events.

        Args:
            event: The key event.
        """
        logger.info("KEY: key=%s hasFocus=%s", event.key(), self.hasFocus())
        # Escape to cancel connection drawing or clear selection
        if event.key() == Qt.Key.Key_Escape:
            if self._is_drawing_connection:
                self.cancel_connection_drawing()
            else:
                self._selection_manager.clear_selection()
            event.accept()
        # Home key to reset view
        elif event.key() == Qt.Key.Key_Home:
            self.reset_view()
        # Plus/Equal for zoom in
        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_in()
        # Minus for zoom out
        elif event.key() == Qt.Key.Key_Minus:
            self.zoom_out()
        # 0 for reset zoom
        elif event.key() == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.reset_zoom()
        # Ctrl+A for select all
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._selection_manager.select_all()
            event.accept()
        # Delete key for deleting selected nodes and connections
        # (only when no text editing widget is focused)
        elif event.key() == Qt.Key.Key_Delete:
            from PyQt6.QtWidgets import (
                QApplication, QLineEdit, QTextEdit, QPlainTextEdit,
                QSpinBox, QDoubleSpinBox, QGraphicsProxyWidget,
            )
            focused = QApplication.focusWidget()
            edit_types = (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)
            is_editing = False
            if focused:
                if isinstance(focused, edit_types):
                    is_editing = True
                elif isinstance(focused, QGraphicsProxyWidget):
                    embedded = focused.widget()
                    if embedded and isinstance(embedded, edit_types):
                        is_editing = True
            if is_editing:
                super().keyPressEvent(event)
            else:
                logger.info("Delete key: nodes=%s, clicked_conn=%s",
                            self._selection_manager.selected_node_ids,
                            self._clicked_connection is not None)
                self._delete_selected_nodes()
                event.accept()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        """Catch Delete at the application level when the view lacks focus."""
        from PyQt6.QtCore import QEvent
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(watched, event)
        try:
            key = event.key()
        except AttributeError:
            logger.debug("Event object missing key() attribute", exc_info=True)
            return super().eventFilter(watched, event)
        if key != Qt.Key.Key_Delete:
            return super().eventFilter(watched, event)

        # Don't steal Delete from text widgets (including those
        # inside QGraphicsProxyWidget, where focusWidget() returns the proxy)
        from PyQt6.QtWidgets import (
            QApplication, QLineEdit, QTextEdit, QPlainTextEdit,
            QSpinBox, QDoubleSpinBox,
        )
        from PyQt6.QtWidgets import QGraphicsProxyWidget
        focused = QApplication.focusWidget()
        if focused:
            edit_types = (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)
            if isinstance(focused, edit_types):
                return super().eventFilter(watched, event)
            # Check if a QGraphicsProxyWidget has an editing widget inside
            if isinstance(focused, QGraphicsProxyWidget):
                embedded = focused.widget()
                if embedded and isinstance(embedded, edit_types):
                    return super().eventFilter(watched, event)

        # Only act when this view is the active/visible graph tab
        if not self.isVisible():
            return super().eventFilter(watched, event)

        # Check if there's anything to delete
        has_nodes = bool(self._selection_manager.selected_node_ids)
        has_conns = bool(self.graph_scene.get_selected_connection_widgets())
        has_clicked = self._clicked_connection is not None

        logger.info(
            "eventFilter Delete: nodes=%s conns=%s clicked=%s focused=%s visible=%s",
            has_nodes, has_conns, has_clicked,
            type(focused).__name__ if focused else None,
            self.isVisible(),
        )

        if has_nodes or has_conns or has_clicked:
            self._delete_selected_nodes()
            return True
        return super().eventFilter(watched, event)

    def contextMenuEvent(self, event: "QContextMenuEvent") -> None:
        """
        Handle right-click context menu events.

        Shows a context menu with actions based on current selection state.
        For Code nodes, an "Edit Code" action is available.
        Also supports right-clicking on connections to delete them.

        Args:
            event: The context menu event.
        """
        menu = QMenu(self)

        # Check if we right-clicked on a connection line
        from PyQt6.QtCore import QPointF
        clicked_conn = self._get_connection_widget_at(
            QPointF(event.pos().x(), event.pos().y())
        )
        if clicked_conn:
            delete_conn_action = QAction("Delete Connection", menu)
            delete_conn_action.triggered.connect(
                lambda: self.graph_scene._on_connection_delete_requested(clicked_conn)
            )
            menu.addAction(delete_conn_action)
            menu.exec(event.globalPos())
            return

        # Get items at click position
        scene_pos = self.mapToScene(event.pos())
        items_at_pos = self.graph_scene.items(scene_pos)

        # Check if we clicked on a node
        from visualpython.nodes.views.node_widget import NodeWidget
        from visualpython.nodes.models.code_node import CodeNode
        clicked_node = None
        for item in items_at_pos:
            if isinstance(item, NodeWidget):
                clicked_node = item
                break

        # If clicked on a node that's not selected, select it
        if clicked_node and not clicked_node.isSelected():
            self._selection_manager.select_node(clicked_node.node_id, SelectionMode.REPLACE)

        # Get selected nodes
        selected_ids = self._selection_manager.selected_node_ids

        if selected_ids:
            # Check if clicked node is a Code node - add Edit Code action first
            if clicked_node and isinstance(clicked_node.node, CodeNode):
                edit_code_action = QAction("Edit Code", menu)
                edit_code_action.setShortcut("Ctrl+E")
                node_id = clicked_node.node_id
                edit_code_action.triggered.connect(
                    lambda checked, nid=node_id: self.edit_code_requested.emit(nid)
                )
                menu.addAction(edit_code_action)
                menu.addSeparator()

            # Delete action
            delete_count = len(selected_ids)
            delete_text = f"Delete ({delete_count} nodes)" if delete_count > 1 else "Delete"
            delete_action = QAction(delete_text, menu)
            delete_action.setShortcut("Delete")
            delete_action.triggered.connect(self._delete_selected_nodes)
            menu.addAction(delete_action)

            menu.addSeparator()

            # Create subworkflow from selection
            if len(selected_ids) >= 1:
                subworkflow_action = QAction("Create Subworkflow from Selection", menu)
                subworkflow_action.setShortcut("Ctrl+Shift+S")
                subworkflow_action.triggered.connect(
                    lambda: self.create_subworkflow_requested.emit()
                )
                menu.addAction(subworkflow_action)

            # Group selected
            if len(selected_ids) > 1:
                group_action = QAction("Group Selected Nodes", menu)
                group_action.setShortcut("Ctrl+Alt+G")
                group_action.triggered.connect(
                    lambda: self.group_nodes_requested.emit(list(selected_ids))
                )
                menu.addAction(group_action)

        # Show the menu if it has actions
        if not menu.isEmpty():
            menu.exec(event.globalPos())

    def dragEnterEvent(self, event: "QDragEnterEvent") -> None:
        """
        Handle drag enter events for node and workflow drops.

        Args:
            event: The drag enter event.
        """
        mime_data = event.mimeData()
        if mime_data.hasFormat(NODE_MIME_TYPE) or mime_data.hasFormat(WORKFLOW_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: "QDragMoveEvent") -> None:
        """
        Handle drag move events for node and workflow drops.

        Args:
            event: The drag move event.
        """
        mime_data = event.mimeData()
        if mime_data.hasFormat(NODE_MIME_TYPE) or mime_data.hasFormat(WORKFLOW_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: "QDropEvent") -> None:
        """
        Handle drop events for creating nodes or inserting workflows.

        Args:
            event: The drop event.
        """
        mime_data = event.mimeData()

        # Get the drop position in scene coordinates
        drop_pos = self.mapToScene(event.position().toPoint())
        drop_x = drop_pos.x()
        drop_y = drop_pos.y()

        # Snap to grid if enabled
        scene = self.graph_scene
        if scene.snap_to_grid_enabled:
            drop_x, drop_y = scene.snap_to_grid(drop_x, drop_y)

        if mime_data.hasFormat(NODE_MIME_TYPE):
            # Get the node type from MIME data
            node_type_bytes = mime_data.data(NODE_MIME_TYPE)
            node_type = bytes(node_type_bytes).decode("utf-8")

            # Emit signal with node type and position
            self.node_dropped.emit(node_type, drop_x, drop_y)

            event.acceptProposedAction()
        elif mime_data.hasFormat(WORKFLOW_MIME_TYPE):
            # Get the workflow file path from MIME data
            file_path_bytes = mime_data.data(WORKFLOW_MIME_TYPE)
            file_path = bytes(file_path_bytes).decode("utf-8")

            # Emit signal with workflow file path and position
            self.workflow_dropped.emit(file_path, drop_x, drop_y)

            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # Public API

    @property
    def zoom_level(self) -> float:
        """Get the current zoom level (1.0 = 100%)."""
        return self._zoom_level

    @property
    def graph_scene(self) -> NodeGraphScene:
        """Get the node graph scene."""
        scene = self.scene()
        if isinstance(scene, NodeGraphScene):
            return scene
        raise RuntimeError("Scene is not a NodeGraphScene")

    def zoom_in(self) -> None:
        """Zoom in by one step."""
        self._apply_zoom(self.ZOOM_STEP)

    def zoom_out(self) -> None:
        """Zoom out by one step."""
        self._apply_zoom(1.0 / self.ZOOM_STEP)

    def reset_zoom(self) -> None:
        """Reset zoom to 100%."""
        if abs(self._zoom_level - self.DEFAULT_ZOOM) > 0.001:
            factor = self.DEFAULT_ZOOM / self._zoom_level
            self._zoom_level = self.DEFAULT_ZOOM
            self.scale(factor, factor)
            self.zoom_changed.emit(self._zoom_level)

    def reset_view(self) -> None:
        """Reset view to origin with default zoom."""
        self.reset_zoom()
        self.centerOn(0, 0)
        self.view_panned.emit()

    def set_zoom(self, zoom: float) -> None:
        """
        Set the zoom level directly.

        Args:
            zoom: The desired zoom level (clamped to MIN_ZOOM..MAX_ZOOM).
        """
        zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, zoom))
        if abs(zoom - self._zoom_level) > 0.001:
            factor = zoom / self._zoom_level
            self._zoom_level = zoom
            self.scale(factor, factor)
            self.zoom_changed.emit(self._zoom_level)

    def fit_in_view(self) -> None:
        """Fit all items in the scene within the view (alias for fit_in_view_all)."""
        self.fit_in_view_all()

    def fit_in_view_all(self) -> None:
        """Fit all items in the scene within the view."""
        scene = self.scene()
        if scene is None:
            return

        # Get bounding rect of all items
        items_rect = scene.itemsBoundingRect()
        if items_rect.isEmpty():
            # No items, reset view
            self.reset_view()
            return

        # Add padding
        padding = 50
        items_rect.adjust(-padding, -padding, padding, padding)

        # Fit to view
        self.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)

        # Calculate and update zoom level
        view_rect = self.viewport().rect()
        scale_x = view_rect.width() / items_rect.width()
        scale_y = view_rect.height() / items_rect.height()
        self._zoom_level = min(scale_x, scale_y)

        # Clamp zoom
        if self._zoom_level < self.MIN_ZOOM:
            self.set_zoom(self.MIN_ZOOM)
        elif self._zoom_level > self.MAX_ZOOM:
            self.set_zoom(self.MAX_ZOOM)

        self.zoom_changed.emit(self._zoom_level)

    def center_on_items(self) -> None:
        """Center the view on all items."""
        scene = self.scene()
        if scene is None:
            return

        items_rect = scene.itemsBoundingRect()
        if not items_rect.isEmpty():
            self.centerOn(items_rect.center())
            self.view_panned.emit()

    def map_to_scene_coords(self, x: int, y: int) -> tuple[float, float]:
        """
        Map viewport coordinates to scene coordinates.

        Args:
            x: X coordinate in viewport space.
            y: Y coordinate in viewport space.

        Returns:
            Tuple of (scene_x, scene_y) coordinates.
        """
        from PyQt6.QtCore import QPoint
        scene_pos = self.mapToScene(QPoint(x, y))
        return (scene_pos.x(), scene_pos.y())

    def get_visible_rect(self) -> tuple[float, float, float, float]:
        """
        Get the currently visible scene rectangle.

        Returns:
            Tuple of (x, y, width, height) in scene coordinates.
        """
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        return (visible.x(), visible.y(), visible.width(), visible.height())

    # Connection Drawing Methods

    def _get_port_widget_at(self, pos: QPointF) -> Optional["PortWidget"]:
        """
        Get a port widget at the given viewport position.

        Args:
            pos: Position in viewport coordinates.

        Returns:
            The PortWidget at the position, or None if not found.
        """
        from visualpython.nodes.views.port_widget import PortWidget

        # Use the view's items() which correctly applies the device
        # transform for hit-testing (scene.items misses items when
        # the view is transformed/zoomed).
        items = self.items(pos.toPoint())

        # Find a port widget
        for item in items:
            if isinstance(item, PortWidget):
                return item

        return None

    def _start_connection_drawing(self, port_widget: "PortWidget") -> None:
        """
        Start drawing a connection from a port.

        Args:
            port_widget: The port widget to start from.
        """
        self._is_drawing_connection = True
        self._connection_source_port = port_widget
        self._is_connection_from_output = port_widget.is_output

        # Start temporary connection in scene
        self.graph_scene.start_temp_connection(
            port_widget, is_from_output=self._is_connection_from_output
        )

        # Change cursor
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Disable rubber band selection during connection drawing
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def _finish_connection_drawing(
        self, target_port_widget: Optional["PortWidget"]
    ) -> None:
        """
        Finish drawing a connection.

        Args:
            target_port_widget: The target port widget, or None if cancelled.
        """
        if not self._is_drawing_connection or not self._connection_source_port:
            return

        source_port = self._connection_source_port
        valid_connection = False

        if target_port_widget and target_port_widget != source_port:
            # Check if the connection is valid (output -> input or input -> output)
            # and type compatible
            if self._is_connection_from_output:
                # Started from output, need to end on input
                if target_port_widget.is_input:
                    # Also check type compatibility
                    if are_types_compatible(
                        source_port.port.port_type,
                        target_port_widget.port.port_type
                    ):
                        valid_connection = True
                        # Emit signal for connection creation
                        self.connection_requested.emit(source_port, target_port_widget)
            else:
                # Started from input, need to end on output
                if target_port_widget.is_output:
                    # Also check type compatibility
                    if are_types_compatible(
                        target_port_widget.port.port_type,
                        source_port.port.port_type
                    ):
                        valid_connection = True
                        # Swap source and target so output is first
                        self.connection_requested.emit(target_port_widget, source_port)

        # Clear any port highlights
        self._clear_connection_highlights()

        # Clean up temporary connection
        self.graph_scene.finish_temp_connection(
            target_port_widget if valid_connection else None
        )

        # Reset state
        self._is_drawing_connection = False
        self._connection_source_port = None
        self._is_connection_from_output = True

        # Restore cursor and drag mode
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def cancel_connection_drawing(self) -> None:
        """Cancel the current connection drawing operation."""
        if self._is_drawing_connection:
            self._finish_connection_drawing(None)

    def _update_connection_compatibility_feedback(self, pos: QPointF) -> None:
        """
        Update visual feedback for connection type compatibility during drag.

        Args:
            pos: Current mouse position in viewport coordinates.
        """
        if not self._is_drawing_connection or not self._connection_source_port:
            return

        # Get port widget at current position
        target_port = self._get_port_widget_at(pos)

        # Clear previous highlight if we moved away
        if self._highlighted_port and self._highlighted_port != target_port:
            self._highlighted_port.set_highlight_state(None)
            self._highlighted_port = None

        # Update temporary connection color
        temp_conn = self.graph_scene.temp_connection
        if temp_conn is None:
            return

        if target_port and target_port != self._connection_source_port:
            # Check if connection would be valid
            is_valid = self._check_connection_compatibility(target_port)

            # Update temporary connection line color
            temp_conn.set_valid_target(is_valid)

            # Update port highlight
            if is_valid:
                target_port.set_highlight_state("compatible")
            else:
                target_port.set_highlight_state("incompatible")
            self._highlighted_port = target_port
        else:
            # Not over a port, reset to valid state
            temp_conn.set_valid_target(True)

    def _check_connection_compatibility(self, target_port: "PortWidget") -> bool:
        """
        Check if a connection from source to target would be type-compatible.

        Args:
            target_port: The potential target port widget.

        Returns:
            True if the connection would be valid.
        """
        if not self._connection_source_port:
            return False

        source_port = self._connection_source_port

        # Determine which is output and which is input
        if self._is_connection_from_output:
            # Source is output, target should be input
            if not target_port.is_input:
                return False
            source_type = source_port.port.port_type
            target_type = target_port.port.port_type
        else:
            # Source is input, target should be output
            if not target_port.is_output:
                return False
            source_type = target_port.port.port_type
            target_type = source_port.port.port_type

        # Check type compatibility
        return are_types_compatible(source_type, target_type)

    def _clear_connection_highlights(self) -> None:
        """Clear any port highlights from connection drawing."""
        if self._highlighted_port:
            self._highlighted_port.set_highlight_state(None)
            self._highlighted_port = None

    @property
    def is_drawing_connection(self) -> bool:
        """Check if currently drawing a connection."""
        return self._is_drawing_connection

    @property
    def selection_manager(self) -> SelectionManager:
        """Get the selection manager."""
        return self._selection_manager

    def _get_node_widget_at(self, pos: QPointF) -> Optional["NodeWidget"]:
        """
        Get a node widget at the given viewport position.

        Args:
            pos: Position in viewport coordinates.

        Returns:
            The NodeWidget at the position, or None if not found.
        """
        # Convert to scene coordinates
        scene_pos = self.mapToScene(pos.toPoint())

        # Manually check all node widgets using their bounding rect.
        for widget in self.graph_scene.get_all_node_widgets():
            local_pos = widget.mapFromScene(scene_pos)
            if widget.boundingRect().contains(local_pos):
                return widget

        return None

    def _get_connection_widget_at(self, pos: QPointF) -> Optional["ConnectionWidget"]:
        """
        Get a connection widget at the given viewport position.

        First checks scene.items() for an exact hit, then falls back to
        iterating all connection widgets with a wider shape tolerance.

        Args:
            pos: Position in viewport coordinates.

        Returns:
            The ConnectionWidget at the position, or None if not found.
        """
        from visualpython.graph.connection_widget import ConnectionWidget

        scene_pos = self.mapToScene(pos.toPoint())

        # Primary: use the view's items() for correct device-transform
        # hit-testing.
        for item in self.items(pos.toPoint()):
            if isinstance(item, ConnectionWidget):
                return item

        # Fallback: iterate all connections with 15px stroke tolerance
        # (catches thin paths that scene.items() may miss).
        for conn_widget in self.graph_scene.get_all_connection_widgets():
            if not conn_widget.isVisible():
                continue
            local_pos = conn_widget.mapFromScene(scene_pos)
            if conn_widget.shape().contains(local_pos):
                return conn_widget

        return None

    def _get_selection_mode_from_modifiers(
        self, modifiers: Qt.KeyboardModifier
    ) -> SelectionMode:
        """
        Determine selection mode from keyboard modifiers.

        Args:
            modifiers: Current keyboard modifiers.

        Returns:
            The appropriate SelectionMode.
        """
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if ctrl and shift:
            return SelectionMode.ADD
        elif ctrl:
            return SelectionMode.TOGGLE
        elif shift:
            return SelectionMode.EXTEND
        else:
            return SelectionMode.REPLACE

    def _on_selection_manager_changed(self, selected_ids: list) -> None:
        """
        Handle selection changes from the selection manager.

        Args:
            selected_ids: List of selected node IDs.
        """
        self.selection_changed.emit(selected_ids)

    def _on_scene_selection_changed(self) -> None:
        """
        Handle selection changes from the scene (e.g., rubber band).

        Syncs the selection manager with the scene's selection state.
        """
        # Only sync if we're not in the middle of a custom selection operation
        if not self._is_drawing_connection and not self._custom_selecting:
            # Check if the scene is still valid before syncing
            scene = self.scene()
            if scene is not None and not sip.isdeleted(scene):
                before = self._selection_manager.selected_node_ids
                self._selection_manager.sync_from_scene()
                after = self._selection_manager.selected_node_ids
                if before != after:
                    logger.info(
                        "sync_from_scene: %s -> %s", before, after
                    )

    def _delete_selected_nodes(self) -> None:
        """Delete all selected nodes and connections."""
        selected_ids = self._selection_manager.selected_node_ids

        # Collect connections to delete from multiple sources
        from visualpython.graph.connection_widget import ConnectionWidget

        selected_connections = self.graph_scene.get_selected_connection_widgets()

        # Fallback 1: scene focus item
        focus_item = self.graph_scene.focusItem()
        if isinstance(focus_item, ConnectionWidget) and focus_item not in selected_connections:
            selected_connections.append(focus_item)

        # Fallback 2: last left-clicked connection (most reliable)
        if (
            self._clicked_connection is not None
            and self._clicked_connection not in selected_connections
        ):
            selected_connections.append(self._clicked_connection)

        logger.info(
            "DELETE: nodes=%s, connections=%d, focus=%s, clicked=%s",
            selected_ids,
            len(selected_connections),
            type(focus_item).__name__ if focus_item else None,
            self._clicked_connection is not None,
        )

        for conn_widget in selected_connections:
            self.graph_scene._on_connection_delete_requested(conn_widget)
        self._clicked_connection = None

        # Emit delete request for each selected node
        # The scene will handle the actual deletion
        for node_id in selected_ids:
            self.graph_scene.node_delete_requested.emit(node_id)

    def get_selected_node_ids(self) -> list:
        """
        Get the IDs of all selected nodes.

        Returns:
            List of selected node IDs.
        """
        return self._selection_manager.selected_node_ids

    def select_nodes_by_ids(
        self,
        node_ids: list,
        mode: SelectionMode = SelectionMode.REPLACE,
    ) -> None:
        """
        Select nodes by their IDs.

        Args:
            node_ids: List of node IDs to select.
            mode: Selection mode to use.
        """
        self._selection_manager.select_nodes(node_ids, mode)

    def clear_selection(self) -> None:
        """Clear all selection."""
        self._selection_manager.clear_selection()

    def load_graph(self, graph: "Graph") -> None:
        """
        Load a graph into the view, creating visual widgets for all nodes and connections.

        This method clears any existing widgets and recreates them from the given graph.
        Used when opening a project file or creating a new project.

        Args:
            graph: The graph model to visualize.
        """
        from visualpython.graph.graph import Graph

        scene = self.graph_scene

        # Clear existing widgets
        scene.clear_connection_widgets()
        scene.clear_node_widgets()
        scene.clear_group_widgets()

        # Add node widgets for each node in the graph
        for node in graph.nodes:
            scene.add_node_widget(node)

        # Add connection widgets for each connection in the graph
        for connection in graph.connections:
            scene.add_connection_widget(connection)

        # Add group widgets for each group in the graph
        for group in graph.groups:
            scene.add_group_widget(group)
            # Handle collapsed groups - hide their nodes
            if group.collapsed:
                scene.set_nodes_visibility_for_group(group.id, False)

        # Center on the loaded content if there are any nodes
        if graph.nodes:
            self.center_on_items()
