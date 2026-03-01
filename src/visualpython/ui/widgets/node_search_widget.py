"""
Node search widget for finding nodes on the canvas by name or content.

This module provides a floating search widget that allows users to search
for nodes on the canvas and navigate through results with highlighting.
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QLabel,
    QPushButton,
    QFrame,
)

if TYPE_CHECKING:
    from visualpython.graph.scene import NodeGraphScene
    from visualpython.graph.view import NodeGraphView
    from visualpython.nodes.views.node_widget import NodeWidget


class NodeSearchWidget(QFrame):
    """
    Floating search widget for finding nodes on the canvas.

    Provides a search box that filters nodes by name or content,
    with navigation buttons to cycle through results and visual
    highlighting of matching nodes.

    Signals:
        search_changed: Emitted when the search query changes.
        result_selected: Emitted when a search result is selected (node_id).
        closed: Emitted when the search widget is closed.
    """

    search_changed = pyqtSignal(str)  # search query
    result_selected = pyqtSignal(str)  # node_id
    closed = pyqtSignal()

    # Highlight colors for search results
    HIGHLIGHT_COLOR_CURRENT = "#FFD700"  # Gold for current result
    HIGHLIGHT_COLOR_MATCH = "#FFA500"  # Orange for other matches

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the node search widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._scene: Optional[NodeGraphScene] = None
        self._view: Optional[NodeGraphView] = None
        self._results: List[str] = []  # List of node IDs matching search
        self._current_index: int = -1
        self._highlighted_node_ids: set = set()  # Track which nodes are highlighted

        self._setup_ui()
        self._setup_style()
        self._connect_signals()

        # Hide by default
        self.hide()

    def _setup_ui(self) -> None:
        """Set up the widget UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # Search icon/label
        self._search_label = QLabel("Find:")
        layout.addWidget(self._search_label)

        # Search input field
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search nodes by name or content...")
        self._search_input.setMinimumWidth(250)
        self._search_input.setClearButtonEnabled(True)
        layout.addWidget(self._search_input, 1)

        # Results counter
        self._results_label = QLabel("")
        self._results_label.setMinimumWidth(60)
        layout.addWidget(self._results_label)

        # Navigation buttons
        self._prev_button = QPushButton("<")
        self._prev_button.setFixedWidth(30)
        self._prev_button.setToolTip("Previous result (Shift+Enter)")
        self._prev_button.setEnabled(False)
        layout.addWidget(self._prev_button)

        self._next_button = QPushButton(">")
        self._next_button.setFixedWidth(30)
        self._next_button.setToolTip("Next result (Enter)")
        self._next_button.setEnabled(False)
        layout.addWidget(self._next_button)

        # Close button
        self._close_button = QPushButton("X")
        self._close_button.setFixedWidth(30)
        self._close_button.setToolTip("Close (Escape)")
        layout.addWidget(self._close_button)

    def _setup_style(self) -> None:
        """Set up the widget styling."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        self.setStyleSheet("""
            NodeSearchWidget {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 6px;
            }
            QLabel {
                color: #CCCCCC;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                color: #FFFFFF;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #00AAFF;
            }
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                color: #CCCCCC;
                font-size: 12px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #00AAFF;
            }
            QPushButton:pressed {
                background-color: #555555;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666666;
            }
        """)

    def _connect_signals(self) -> None:
        """Connect widget signals to handlers."""
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.returnPressed.connect(self._on_next_result)
        self._prev_button.clicked.connect(self._on_prev_result)
        self._next_button.clicked.connect(self._on_next_result)
        self._close_button.clicked.connect(self.close_search)

    def set_scene_and_view(
        self,
        scene: "NodeGraphScene",
        view: "NodeGraphView"
    ) -> None:
        """
        Set the scene and view to search in.

        Args:
            scene: The node graph scene containing nodes.
            view: The node graph view for centering on results.
        """
        self._scene = scene
        self._view = view

    def show_search(self) -> None:
        """Show and focus the search widget."""
        self.show()
        self._search_input.setFocus()
        self._search_input.selectAll()

    def close_search(self) -> None:
        """Close the search widget and clear highlights."""
        self._clear_highlights()
        self._search_input.clear()
        self._results = []
        self._current_index = -1
        self._update_results_label()
        self.hide()
        self.closed.emit()

    def _on_search_changed(self, text: str) -> None:
        """
        Handle search text changes.

        Args:
            text: The new search text.
        """
        self._perform_search(text)
        self.search_changed.emit(text)

    def _perform_search(self, query: str) -> None:
        """
        Perform the search and update results.

        Args:
            query: The search query string.
        """
        # Clear previous highlights
        self._clear_highlights()
        self._results = []
        self._current_index = -1

        if not query or not self._scene:
            self._update_ui_state()
            return

        query_lower = query.lower()

        # Search through all node widgets
        for node_widget in self._scene.get_all_node_widgets():
            node = node_widget.node

            # Search in node name
            if query_lower in node.name.lower():
                self._results.append(node.id)
                continue

            # Search in node type
            if query_lower in node.node_type.lower():
                self._results.append(node.id)
                continue

            # Search in node properties (for nodes with code or other content)
            if self._search_node_properties(node, query_lower):
                self._results.append(node.id)

        # Update UI and highlight results
        self._update_ui_state()

        if self._results:
            self._current_index = 0
            self._highlight_all_results()
            self._focus_current_result()

    def _search_node_properties(self, node, query: str) -> bool:
        """
        Search in node-specific properties.

        Args:
            node: The node to search in.
            query: The lowercase search query.

        Returns:
            True if the query matches any property.
        """
        # Get serializable properties which contain node-specific data
        properties = node._get_serializable_properties()

        for key, value in properties.items():
            if isinstance(value, str) and query in value.lower():
                return True
            elif isinstance(value, dict):
                for v in value.values():
                    if isinstance(v, str) and query in v.lower():
                        return True

        # Also check comment field
        if node.comment and query in node.comment.lower():
            return True

        return False

    def _update_ui_state(self) -> None:
        """Update the UI based on current search state."""
        has_results = len(self._results) > 0
        self._prev_button.setEnabled(has_results and len(self._results) > 1)
        self._next_button.setEnabled(has_results and len(self._results) > 1)
        self._update_results_label()

    def _update_results_label(self) -> None:
        """Update the results counter label."""
        if not self._search_input.text():
            self._results_label.setText("")
        elif len(self._results) == 0:
            self._results_label.setText("No results")
            self._results_label.setStyleSheet("color: #FF6B6B;")
        else:
            self._results_label.setText(
                f"{self._current_index + 1} of {len(self._results)}"
            )
            self._results_label.setStyleSheet("color: #90EE90;")

    def _on_next_result(self) -> None:
        """Navigate to the next search result."""
        if not self._results:
            return

        self._current_index = (self._current_index + 1) % len(self._results)
        self._highlight_all_results()
        self._focus_current_result()

    def _on_prev_result(self) -> None:
        """Navigate to the previous search result."""
        if not self._results:
            return

        self._current_index = (self._current_index - 1) % len(self._results)
        self._highlight_all_results()
        self._focus_current_result()

    def _highlight_all_results(self) -> None:
        """Apply highlight effects to all matching nodes."""
        if not self._scene:
            return

        for i, node_id in enumerate(self._results):
            widget = self._scene.get_node_widget(node_id)
            if widget:
                is_current = (i == self._current_index)
                self._apply_highlight(widget, is_current)

    def _apply_highlight(
        self,
        widget: "NodeWidget",
        is_current: bool
    ) -> None:
        """
        Apply highlight effect to a node widget.

        Args:
            widget: The node widget to highlight.
            is_current: Whether this is the current focused result.
        """
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect

        # Track that this node is highlighted
        self._highlighted_node_ids.add(widget.node_id)

        # Create highlight effect
        effect = QGraphicsDropShadowEffect()
        effect.setBlurRadius(30)
        effect.setOffset(0, 0)

        if is_current:
            # Gold glow for current result
            effect.setColor(QColor(255, 215, 0, 200))
        else:
            # Orange glow for other matches
            effect.setColor(QColor(255, 165, 0, 150))

        widget.setGraphicsEffect(effect)

    def _clear_highlights(self) -> None:
        """Clear all highlight effects from nodes."""
        if not self._scene:
            self._highlighted_node_ids.clear()
            return

        from PyQt6.QtWidgets import QGraphicsDropShadowEffect

        for node_id in self._highlighted_node_ids:
            widget = self._scene.get_node_widget(node_id)
            if widget:
                # Create default shadow effect (same as NodeWidget default)
                shadow = QGraphicsDropShadowEffect()
                shadow.setBlurRadius(15)
                shadow.setOffset(3, 3)
                shadow.setColor(QColor(0, 0, 0, 100))
                widget.setGraphicsEffect(shadow)

        self._highlighted_node_ids.clear()

    def _focus_current_result(self) -> None:
        """Center the view on the current result and select it."""
        if not self._results or self._current_index < 0:
            return

        node_id = self._results[self._current_index]

        if self._scene and self._view:
            widget = self._scene.get_node_widget(node_id)
            if widget:
                # Center view on the node
                self._view.centerOn(widget)

                # Select the node
                self._scene.clearSelection()
                widget.setSelected(True)

        self._update_results_label()
        self.result_selected.emit(node_id)

    def keyPressEvent(self, event) -> None:
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            self.close_search()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._on_prev_result()
            else:
                self._on_next_result()
        else:
            super().keyPressEvent(event)


class NodeSearchController:
    """
    Controller for managing the node search widget integration.

    Handles the Ctrl+F shortcut and positioning of the search widget
    within the main window.
    """

    def __init__(
        self,
        parent_widget: QWidget,
        scene: "NodeGraphScene",
        view: "NodeGraphView"
    ) -> None:
        """
        Initialize the search controller.

        Args:
            parent_widget: The parent widget (typically the main window central widget).
            scene: The node graph scene.
            view: The node graph view.
        """
        self._parent = parent_widget
        self._scene = scene
        self._view = view

        # Create the search widget
        self._search_widget = NodeSearchWidget(parent_widget)
        self._search_widget.set_scene_and_view(scene, view)

        # Set up keyboard shortcut
        self._setup_shortcut()

        # Position the widget
        self._position_widget()

    def _setup_shortcut(self) -> None:
        """Set up the Ctrl+F keyboard shortcut."""
        shortcut = QShortcut(QKeySequence.StandardKey.Find, self._parent)
        shortcut.activated.connect(self.toggle_search)

    def _position_widget(self) -> None:
        """Position the search widget at the top center of the parent."""
        # Position will be updated when shown
        self._search_widget.closed.connect(self._on_search_closed)

    def toggle_search(self) -> None:
        """Toggle the search widget visibility."""
        if self._search_widget.isVisible():
            self._search_widget.close_search()
        else:
            self._update_position()
            self._search_widget.show_search()

    def show_search(self) -> None:
        """Show the search widget."""
        self._update_position()
        self._search_widget.show_search()

    def hide_search(self) -> None:
        """Hide the search widget."""
        self._search_widget.close_search()

    def _update_position(self) -> None:
        """Update the search widget position based on parent size."""
        parent_width = self._parent.width()
        widget_width = self._search_widget.sizeHint().width()

        # Center horizontally, position at top with margin
        x = (parent_width - widget_width) // 2
        y = 10  # Margin from top

        self._search_widget.move(x, y)

    def _on_search_closed(self) -> None:
        """Handle search widget closed event."""
        # Return focus to the view
        if self._view:
            self._view.setFocus()

    @property
    def search_widget(self) -> NodeSearchWidget:
        """Get the search widget instance."""
        return self._search_widget
