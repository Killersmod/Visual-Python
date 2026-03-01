"""
Workflow tab widget for managing multiple workflows in tabs.

This module provides a tabbed interface for working with multiple workflows
simultaneously, similar to draw.io but for visual Python programming.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
import logging
import uuid

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRect
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush, QFontMetrics
from PyQt6.QtWidgets import (
    QTabWidget,
    QTabBar,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QInputDialog,
    QFileDialog,
    QStyle,
    QPushButton,
    QLabel,
    QFrame,
    QSizePolicy,
    QStyleOptionTab,
    QStylePainter,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph
    from visualpython.graph.view import NodeGraphView


class ViewMode(Enum):
    """View modes for workflow visualization."""

    EDIT = auto()
    """Standard editing mode with full node details."""

    RUN = auto()
    """Run/debug mode showing execution state."""

    COLLAPSED = auto()
    """Collapsed view showing only workflow structure and subgraphs."""

    EXPANDED = auto()
    """Expanded view unrolling all nested workflows."""


@dataclass
class WorkflowTab:
    """
    Represents a single workflow tab.

    Attributes:
        tab_id: Unique identifier for the tab.
        name: Display name for the tab.
        file_path: Optional path to saved file.
        graph: The workflow graph.
        graph_view: The visual view widget.
        is_modified: Whether the workflow has unsaved changes.
        view_mode: Current view mode for this workflow.
        is_subworkflow: Whether this is opened as a subworkflow editor.
        parent_workflow_id: If subworkflow, the parent workflow tab ID.
        subgraph_node_id: If subworkflow, the ID of the SubgraphNode being edited.
        hierarchy_depth: Nesting level in the subgraph hierarchy (0 = root).
    """

    tab_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Workflow"
    file_path: Optional[Path] = None
    graph: Optional["Graph"] = None
    graph_view: Optional["NodeGraphView"] = None
    is_modified: bool = False
    view_mode: ViewMode = ViewMode.EDIT
    is_subworkflow: bool = False
    parent_workflow_id: Optional[str] = None
    subgraph_node_id: Optional[str] = None
    hierarchy_depth: int = 0

    @property
    def display_name(self) -> str:
        """Get the display name with modification indicator."""
        prefix = "*" if self.is_modified else ""
        return f"{prefix}{self.name}"

    @property
    def tooltip(self) -> str:
        """Get the tooltip text for the tab including hierarchy info."""
        lines = []

        # Add hierarchy info for subworkflows
        if self.is_subworkflow:
            depth_desc = f"Level {self.hierarchy_depth}" if self.hierarchy_depth > 0 else "Root"
            lines.append(f"Subworkflow ({depth_desc}): {self.name}")
        else:
            lines.append(f"Workflow: {self.name}")

        # Add file path if available
        if self.file_path:
            lines.append(f"File: {self.file_path}")

        # Add parent info for subworkflows
        if self.is_subworkflow and self.parent_workflow_id:
            lines.append("(Click to edit, changes sync to parent)")

        if not self.file_path and not self.is_subworkflow:
            lines.append("(Unsaved)")

        return "\n".join(lines)


class WorkflowTabBar(QTabBar):
    """
    Custom tab bar that visually distinguishes subgraph tabs from root workflow tabs.

    Subgraph tabs are styled with a different background color and a subtle
    gradient to make them visually distinct and help users understand the
    hierarchy at a glance.
    """

    # Tab background colors — high-contrast scheme so the active tab
    # is clearly distinguishable from inactive and hovered tabs.
    ROOT_TAB_BG = QColor("#252525")
    ROOT_TAB_BG_SELECTED = QColor("#404040")
    ROOT_TAB_BG_HOVER = QColor("#353535")

    # Subgraph tabs use blue-tinted colors to indicate nested content
    SUBGRAPH_TAB_BG = QColor("#1a3050")
    SUBGRAPH_TAB_BG_SELECTED = QColor("#2a5080")
    SUBGRAPH_TAB_BG_HOVER = QColor("#203d65")

    # Deep nesting uses purple-tinted colors for visibility
    DEEP_SUBGRAPH_TAB_BG = QColor("#301850")
    DEEP_SUBGRAPH_TAB_BG_SELECTED = QColor("#502880")
    DEEP_SUBGRAPH_TAB_BG_HOVER = QColor("#3d2065")

    # Border colors for different tab types
    ROOT_TAB_BORDER = QColor("#555555")
    ROOT_TAB_BORDER_SELECTED = QColor("#4CAF50")  # Green accent for active root tab
    SUBGRAPH_TAB_BORDER = QColor("#3d6a9e")
    SUBGRAPH_TAB_BORDER_SELECTED = QColor("#5599dd")  # Brighter blue for active subgraph
    DEEP_SUBGRAPH_TAB_BORDER = QColor("#6d3d9e")
    DEEP_SUBGRAPH_TAB_BORDER_SELECTED = QColor("#9955dd")  # Brighter purple for active deep

    # Background color for the tab bar itself (visible between/behind tabs)
    TAB_BAR_BG = QColor("#1e1e1e")

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the custom tab bar."""
        super().__init__(parent)

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

        # Ensure the tab bar paints its own opaque background so that
        # the parent widget's (potentially light) background never bleeds
        # through behind the custom-painted tabs.
        self.setAutoFillBackground(True)

        # Store tab metadata (tab_id -> is_subworkflow, hierarchy_depth)
        self._tab_metadata: Dict[int, Dict[str, Any]] = {}

        # We draw our own close buttons in paintEvent; Qt's built-in close
        # button widgets are NOT used (setTabsClosable is False).
        self._tabs_closable = True

    def set_tab_metadata(
        self, index: int, is_subworkflow: bool, hierarchy_depth: int, pinned: bool = False
    ) -> None:
        """
        Set metadata for a tab to determine its styling.

        Args:
            index: The tab index.
            is_subworkflow: Whether this tab is a subworkflow.
            hierarchy_depth: The nesting depth (0 = root, 1+ = subgraph levels).
            pinned: Whether this tab is pinned (cannot be closed).
        """
        self._tab_metadata[index] = {
            "is_subworkflow": is_subworkflow,
            "hierarchy_depth": hierarchy_depth,
            "pinned": pinned,
        }
        # Trigger a geometry update to ensure tabSizeHint is recalculated
        self.updateGeometry()
        # Trigger a repaint to apply the new styling
        self.update()

    def is_tab_pinned(self, index: int) -> bool:
        """Check if a tab is pinned (cannot be closed)."""
        metadata = self._tab_metadata.get(index, {})
        return metadata.get("pinned", False)

    def clear_tab_metadata(self, index: int) -> None:
        """Remove metadata for a tab (called when tab is closed)."""
        self._tab_metadata.pop(index, None)

    def update_metadata_indices(self, mapping: Dict[int, Dict[str, Any]]) -> None:
        """Replace all tab metadata (used after tab reordering/removal)."""
        self._tab_metadata = mapping
        self.updateGeometry()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        """Handle mouse move to update hover effects."""
        super().mouseMoveEvent(event)
        self.update()  # Trigger repaint for hover state changes

    def leaveEvent(self, event) -> None:
        """Handle mouse leave to clear hover effects."""
        super().leaveEvent(event)
        self.update()  # Trigger repaint to remove hover state

    def mousePressEvent(self, event) -> None:
        """Handle mouse press – detect clicks on our custom close buttons."""
        if event.button() == Qt.MouseButton.LeftButton and self._tabs_closable:
            pos = event.pos()
            for index in range(self.count()):
                rect = self.tabRect(index)
                if not rect.contains(pos):
                    continue
                # Check if click is inside the custom close button area
                if self.is_tab_pinned(index):
                    break  # Pinned tabs have no close button
                close_rect = rect.adjusted(rect.width() - 20, 4, -4, -4)
                close_rect.setWidth(16)
                close_rect.setHeight(16)
                if close_rect.contains(pos):
                    # Emit the standard tabCloseRequested signal on the parent
                    tab_widget = self.parent()
                    if hasattr(tab_widget, 'tabCloseRequested'):
                        tab_widget.tabCloseRequested.emit(index)
                    return  # Consume the event
                break
        super().mousePressEvent(event)

    def tabInserted(self, index: int) -> None:
        """Called when a tab is inserted to ensure proper geometry update."""
        super().tabInserted(index)
        # Force geometry recalculation when a new tab is inserted
        self.updateGeometry()

    def tabLayoutChange(self) -> None:
        """Called when tabs are rearranged or closed."""
        super().tabLayoutChange()
        # Force geometry recalculation when layout changes
        self.updateGeometry()
        self.update()

    def tabSizeHint(self, index: int) -> QSize:
        """
        Provide a size hint for tabs that ensures text visibility.

        This method calculates an appropriate tab width based on:
        - The text content of the tab
        - Space needed for the icon (if present)
        - Space needed for the close button (if tabs are closable)
        - Minimum padding for visual comfort

        Args:
            index: The index of the tab.

        Returns:
            QSize with appropriate width and height for the tab.
        """
        # Get the default size hint from parent
        size = super().tabSizeHint(index)

        # Calculate the minimum width needed for this tab
        text = self.tabText(index)
        font_metrics = QFontMetrics(self.font())
        text_width = font_metrics.horizontalAdvance(text)

        # Add space for icon if present
        icon_space = 0
        if not self.tabIcon(index).isNull():
            icon_space = 28  # Icon width (16) + spacing

        # Add space for close button if tabs are closable and not pinned
        close_button_space = 0
        if self._tabs_closable and not self.is_tab_pinned(index):
            close_button_space = 28  # Close button area
        elif self.is_tab_pinned(index):
            close_button_space = 16  # Space for pin indicator (smaller than close button)

        # Add padding
        left_padding = 8
        right_padding = 8

        # Calculate total minimum width
        min_width = left_padding + icon_space + text_width + close_button_space + right_padding

        # Ensure a reasonable minimum width to accommodate tab names
        # 140px provides enough space for typical workflow names with icons and close buttons
        min_width = max(min_width, 140)

        # Cap at a reasonable maximum to prevent overly wide tabs
        max_width = 300
        min_width = min(min_width, max_width)

        # Return the size with updated width
        return QSize(min_width, size.height())

    def _get_tab_colors(self, index: int, is_selected: bool, is_hover: bool) -> tuple:
        """
        Get the background and border colors for a tab based on its type and state.

        Returns:
            Tuple of (background_color, border_color)
        """
        metadata = self._tab_metadata.get(index, {})
        is_subworkflow = metadata.get("is_subworkflow", False)
        hierarchy_depth = metadata.get("hierarchy_depth", 0)

        if is_subworkflow:
            if hierarchy_depth >= 2:
                # Deep nested subgraph (level 2+)
                if is_selected:
                    bg = self.DEEP_SUBGRAPH_TAB_BG_SELECTED
                    border = self.DEEP_SUBGRAPH_TAB_BORDER_SELECTED
                elif is_hover:
                    bg = self.DEEP_SUBGRAPH_TAB_BG_HOVER
                    border = self.DEEP_SUBGRAPH_TAB_BORDER
                else:
                    bg = self.DEEP_SUBGRAPH_TAB_BG
                    border = self.DEEP_SUBGRAPH_TAB_BORDER
            else:
                # First-level subgraph
                if is_selected:
                    bg = self.SUBGRAPH_TAB_BG_SELECTED
                    border = self.SUBGRAPH_TAB_BORDER_SELECTED
                elif is_hover:
                    bg = self.SUBGRAPH_TAB_BG_HOVER
                    border = self.SUBGRAPH_TAB_BORDER
                else:
                    bg = self.SUBGRAPH_TAB_BG
                    border = self.SUBGRAPH_TAB_BORDER
        else:
            # Root workflow
            if is_selected:
                bg = self.ROOT_TAB_BG_SELECTED
                border = self.ROOT_TAB_BORDER_SELECTED
            elif is_hover:
                bg = self.ROOT_TAB_BG_HOVER
                border = self.ROOT_TAB_BORDER
            else:
                bg = self.ROOT_TAB_BG
                border = self.ROOT_TAB_BORDER

        return bg, border

    def paintEvent(self, event) -> None:
        """
        Custom paint event to draw tabs with distinct styling for subgraphs.

        Subgraph tabs get a blue-tinted background, while deeply nested
        subgraphs get a purple-tinted background for easy visual identification.
        """
        painter = QStylePainter(self)

        # Fill the entire tab bar background first so no parent/sibling
        # widget background can bleed through and obscure the tab text.
        painter.fillRect(self.rect(), self.TAB_BAR_BG)

        # Get hover state
        hover_index = -1
        cursor_pos = self.mapFromGlobal(self.cursor().pos())
        for i in range(self.count()):
            if self.tabRect(i).contains(cursor_pos):
                hover_index = i
                break

        for index in range(self.count()):
            # Create option for this tab
            option = QStyleOptionTab()
            self.initStyleOption(option, index)

            # Determine tab state
            is_selected = index == self.currentIndex()
            is_hover = index == hover_index

            # Get colors for this tab type
            bg_color, border_color = self._get_tab_colors(index, is_selected, is_hover)

            # Get tab rectangle
            rect = self.tabRect(index)

            # Draw background with rounded corners
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Draw the tab background
            painter.setBrush(QBrush(bg_color))
            painter.setPen(QPen(border_color, 1))

            # Rounded rectangle for the tab
            radius = 4
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, 0), radius, radius)

            # For the selected tab, draw a bright accent line at the top
            # For subgraph tabs, always draw a subtle accent line
            metadata = self._tab_metadata.get(index, {})
            if is_selected:
                painter.setPen(QPen(border_color, 2))
                painter.drawLine(
                    rect.left() + radius + 1,
                    rect.top() + 1,
                    rect.right() - radius - 1,
                    rect.top() + 1
                )
            elif metadata.get("is_subworkflow", False):
                painter.setPen(QPen(border_color.lighter(120), 1))
                painter.drawLine(
                    rect.left() + radius + 1,
                    rect.top() + 1,
                    rect.right() - radius - 1,
                    rect.top() + 1
                )

            painter.restore()

            # Draw the icon if present
            icon = self.tabIcon(index)
            if not icon.isNull():
                icon_rect = QRect(rect)  # copy — don't mutate option.rect
                icon_rect.setLeft(icon_rect.left() + 8)
                icon_rect.setWidth(16)
                icon_rect.setTop(icon_rect.top() + (icon_rect.height() - 16) // 2)
                icon_rect.setHeight(16)
                icon.paint(painter, icon_rect)

            # Draw the text
            text = self.tabText(index)
            text_rect = QRect(rect)

            # Adjust text position if there's an icon
            left_padding = 8
            if not icon.isNull():
                left_padding = 28  # Icon width (16) + spacing (8) + initial padding (4)
            text_rect.setLeft(text_rect.left() + left_padding)

            # Adjust for close button if tabs are closable, or pin indicator if pinned
            # Reserve more space for the close button area (button is 16px + padding)
            right_padding = 8
            metadata = self._tab_metadata.get(index, {})
            is_tab_pinned = metadata.get("pinned", False)
            if self._tabs_closable and not is_tab_pinned:
                right_padding = 28  # Close button (16px) + padding (12px)
            elif is_tab_pinned:
                right_padding = 20  # Pin indicator (12px) + padding (8px)
            text_rect.setRight(text_rect.right() - right_padding)

            # Set text color (lighter for better contrast on colored backgrounds)
            text_color = QColor("#e0e0e0") if not is_selected else QColor("#ffffff")
            painter.setPen(text_color)

            # Get font metrics to properly elide text if needed
            font_metrics = QFontMetrics(painter.font())
            available_width = text_rect.width()

            # Elide text with ellipsis if it's too long to fit
            elided_text = font_metrics.elidedText(
                text,
                Qt.TextElideMode.ElideRight,
                available_width
            )

            # Draw the elided text
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                elided_text
            )

            # Check if tab is pinned (no close button for pinned tabs)
            is_pinned = self.is_tab_pinned(index)

            # Draw close button if tabs are closable, not pinned, and this is current or hover
            if self._tabs_closable and not is_pinned and (is_selected or is_hover):
                close_rect = rect.adjusted(rect.width() - 20, 4, -4, -4)
                close_rect.setWidth(16)
                close_rect.setHeight(16)

                # Draw close button background on hover
                close_hover = close_rect.contains(cursor_pos)
                if close_hover:
                    painter.setBrush(QBrush(QColor("#ff5555")))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(close_rect, 2, 2)

                # Draw X
                painter.setPen(QPen(QColor("#ffffff" if close_hover else "#aaaaaa"), 1.5))
                margin = 4
                painter.drawLine(
                    close_rect.left() + margin, close_rect.top() + margin,
                    close_rect.right() - margin, close_rect.bottom() - margin
                )
                painter.drawLine(
                    close_rect.right() - margin, close_rect.top() + margin,
                    close_rect.left() + margin, close_rect.bottom() - margin
                )
            elif is_pinned and (is_selected or is_hover):
                # Draw a pin icon for pinned tabs instead of close button
                pin_rect = rect.adjusted(rect.width() - 18, 6, -6, -6)
                pin_rect.setWidth(12)
                pin_rect.setHeight(12)

                # Draw a subtle pin indicator (like a thumbtack)
                painter.setPen(QPen(QColor("#888888"), 1.5))
                # Draw pin body (vertical line)
                cx = pin_rect.center().x()
                painter.drawLine(cx, pin_rect.top() + 2, cx, pin_rect.bottom() - 2)
                # Draw pin head (horizontal line at top)
                painter.drawLine(pin_rect.left() + 2, pin_rect.top() + 3, pin_rect.right() - 2, pin_rect.top() + 3)


class WorkflowTabWidget(QTabWidget):
    """
    Tabbed widget for managing multiple workflows.

    Provides tab management similar to draw.io, allowing users to:
    - Work on multiple workflows simultaneously
    - Switch between workflows quickly
    - Open subworkflows in new tabs for editing
    - View workflows in different modes (edit, run, collapsed, expanded)

    Signals:
        tab_changed: Emitted when the active tab changes (tab_id).
        workflow_created: Emitted when a new workflow is created (tab_id).
        workflow_closed: Emitted when a workflow tab is closed (tab_id).
        workflow_modified: Emitted when a workflow is modified (tab_id).
        workflow_saved: Emitted when a workflow is saved (tab_id, file_path).
        view_mode_changed: Emitted when view mode changes (tab_id, view_mode).
        subworkflow_opened: Emitted when a subworkflow is opened for editing (tab_id, parent_id).
        hierarchy_changed: Emitted when the tab hierarchy changes (e.g., subworkflow opened/closed).
    """

    # Signals
    tab_changed = pyqtSignal(str)  # tab_id
    workflow_created = pyqtSignal(str)  # tab_id
    workflow_closed = pyqtSignal(str)  # tab_id
    workflow_modified = pyqtSignal(str)  # tab_id
    workflow_saved = pyqtSignal(str, str)  # tab_id, file_path
    view_mode_changed = pyqtSignal(str, object)  # tab_id, ViewMode
    subworkflow_opened = pyqtSignal(str, str)  # tab_id, parent_tab_id
    hierarchy_changed = pyqtSignal()  # emitted when tab parent-child relationships change

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the workflow tab widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        # Tab storage
        self._tabs: Dict[str, WorkflowTab] = {}
        self._tab_index_to_id: Dict[int, str] = {}

        # Graph view factory (set by application controller)
        self._create_graph_view: Optional[Callable[[], "NodeGraphView"]] = None
        self._create_graph: Optional[Callable[[], "Graph"]] = None

        # Setup UI
        self._setup_ui()
        self._connect_signals()

    # Icon colors for hierarchy visualization
    ROOT_ICON_COLOR = QColor("#4CAF50")  # Green for root workflows
    SUBGRAPH_ICON_COLOR = QColor("#2196F3")  # Blue for subgraphs
    DEEP_SUBGRAPH_ICON_COLOR = QColor("#9C27B0")  # Purple for deeply nested subgraphs

    def _setup_ui(self) -> None:
        """Set up the tab widget UI."""
        # Use custom tab bar for distinct subgraph styling
        self._custom_tab_bar = WorkflowTabBar(self)
        self.setTabBar(self._custom_tab_bar)

        # Close buttons are drawn by WorkflowTabBar.paintEvent() and handled
        # by WorkflowTabBar.mousePressEvent().  Do NOT call setTabsClosable(True)
        # because Qt's built-in close-button widgets would overlay the custom
        # painted text.

        # Enable movable tabs
        self.setMovable(True)

        # Show tab bar when empty
        self.setDocumentMode(True)

        # Enable context menu on tabs
        self.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Minimal stylesheet – clear the pane border and ensure the tab bar
        # has a dark background so the default platform style does not draw
        # a light surface behind the custom-painted tabs.
        self.setStyleSheet("""
            QTabWidget::pane {
                border: none;
            }
            QTabBar {
                background-color: #1e1e1e;
            }
        """)

        # Cache for hierarchy icons
        self._icon_cache: Dict[int, QIcon] = {}

        # Create subworkflow info bar (shown when a subworkflow tab is active)
        self._setup_subworkflow_info_bar()

    def _setup_subworkflow_info_bar(self) -> None:
        """
        Set up the subworkflow info bar that appears when editing a subworkflow.

        This bar provides quick access to:
        - Navigate to parent workflow
        - Save workflow to its library file
        - Shows the breadcrumb path in the hierarchy
        """
        # Create the info bar frame
        self._subworkflow_info_bar = QFrame(self)
        self._subworkflow_info_bar.setObjectName("subworkflow_info_bar")
        self._subworkflow_info_bar.setFrameShape(QFrame.Shape.StyledPanel)
        self._subworkflow_info_bar.setFrameShadow(QFrame.Shadow.Raised)
        self._subworkflow_info_bar.setStyleSheet("""
            QFrame#subworkflow_info_bar {
                background-color: #2d4a6e;
                border: 1px solid #3d5a7e;
                border-radius: 4px;
                padding: 4px;
                margin: 2px;
            }
            QLabel {
                color: #ffffff;
                font-size: 11px;
            }
            QPushButton {
                background-color: #3d6a9e;
                color: #ffffff;
                border: 1px solid #4d7aae;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 11px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4d7aae;
                border-color: #5d8abe;
            }
            QPushButton:pressed {
                background-color: #2d5a8e;
            }
            QPushButton#save_workflow_btn {
                background-color: #4CAF50;
                border-color: #5CBF60;
            }
            QPushButton#save_workflow_btn:hover {
                background-color: #5CBF60;
                border-color: #6CCF70;
            }
            QPushButton#save_workflow_btn:pressed {
                background-color: #3C9F40;
            }
        """)

        # Create layout for the info bar
        info_bar_layout = QHBoxLayout(self._subworkflow_info_bar)
        info_bar_layout.setContentsMargins(8, 4, 8, 4)
        info_bar_layout.setSpacing(12)

        # Hierarchy icon/indicator
        hierarchy_icon_label = QLabel()
        hierarchy_icon_label.setPixmap(
            self._create_hierarchy_icon(1).pixmap(QSize(16, 16))
        )
        info_bar_layout.addWidget(hierarchy_icon_label)

        # Breadcrumb label showing hierarchy path
        self._breadcrumb_label = QLabel("Subworkflow")
        self._breadcrumb_label.setObjectName("breadcrumb_label")
        info_bar_layout.addWidget(self._breadcrumb_label)

        # Spacer to push buttons to the right
        info_bar_layout.addStretch(1)

        # Navigate to Parent button
        self._goto_parent_btn = QPushButton("Go to Parent")
        self._goto_parent_btn.setToolTip("Navigate to the parent workflow tab")
        self._goto_parent_btn.clicked.connect(self._on_goto_parent_clicked)
        info_bar_layout.addWidget(self._goto_parent_btn)

        # Save Workflow button (saves directly to the library file)
        self._save_workflow_btn = QPushButton("Save Workflow")
        self._save_workflow_btn.setObjectName("save_workflow_btn")
        self._save_workflow_btn.setToolTip(
            "Save changes to the workflow library file.\n"
            "All SubgraphNodes referencing this workflow will see the update."
        )
        self._save_workflow_btn.clicked.connect(self._on_save_workflow_clicked)
        info_bar_layout.addWidget(self._save_workflow_btn)

        # Initially hide the info bar (shown only for subworkflow tabs)
        self._subworkflow_info_bar.setVisible(False)

        # The info bar will be positioned by overriding resizeEvent
        self._subworkflow_info_bar.setParent(self)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self.currentChanged.connect(self._on_current_changed)
        self.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tabBar().customContextMenuRequested.connect(self._show_tab_context_menu)
        self.tabBar().tabMoved.connect(self._on_tab_moved)

    def _create_hierarchy_icon(self, depth: int) -> QIcon:
        """
        Create an icon that visually represents the hierarchy depth.

        Args:
            depth: The hierarchy depth (0 = root, 1 = first-level subgraph, etc.)

        Returns:
            A QIcon representing the hierarchy level.
        """
        # Check cache first
        if depth in self._icon_cache:
            return self._icon_cache[depth]

        # Create a 16x16 pixmap
        size = 16
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Determine color based on depth
        if depth == 0:
            color = self.ROOT_ICON_COLOR
        elif depth == 1:
            color = self.SUBGRAPH_ICON_COLOR
        else:
            color = self.DEEP_SUBGRAPH_ICON_COLOR

        # Draw different shapes based on depth
        if depth == 0:
            # Root workflow: filled circle (workflow icon)
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(120), 1))
            painter.drawEllipse(2, 2, size - 4, size - 4)
        else:
            # Subgraph: nested squares/boxes to indicate depth
            # Draw outer rectangle
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(120), 1))

            # For deeper nesting, draw stacked/nested boxes
            offset = min(depth - 1, 2) * 2  # Max 2 levels of visual nesting
            rect_size = size - 4 - offset

            # Draw shadow/background boxes for depth indication
            if depth > 1:
                shadow_color = color.darker(150)
                painter.setBrush(QBrush(shadow_color))
                painter.setPen(QPen(shadow_color.darker(120), 1))
                painter.drawRoundedRect(4, 4, rect_size, rect_size, 2, 2)

            # Draw main box
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(120), 1))
            painter.drawRoundedRect(2 + offset, 2, rect_size, rect_size, 2, 2)

            # Add small arrow indicator for subgraph
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            # Draw a small ">" inside to indicate "drill-down"
            center_x = 2 + offset + rect_size // 2
            center_y = 2 + rect_size // 2
            arrow_size = 3
            painter.drawLine(
                int(center_x - arrow_size // 2), int(center_y - arrow_size),
                int(center_x + arrow_size // 2), int(center_y)
            )
            painter.drawLine(
                int(center_x + arrow_size // 2), int(center_y),
                int(center_x - arrow_size // 2), int(center_y + arrow_size)
            )

        painter.end()

        icon = QIcon(pixmap)
        self._icon_cache[depth] = icon
        return icon

    def _update_tab_icon(self, tab_id: str) -> None:
        """
        Update the icon for a specific tab based on its hierarchy depth.

        Args:
            tab_id: ID of the tab to update.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        icon = self._create_hierarchy_icon(tab.hierarchy_depth)

        # Find the tab index and set the icon
        for index in range(self.count()):
            if self._tab_index_to_id.get(index) == tab_id:
                self.setTabIcon(index, icon)
                break

    def _update_all_tab_icons(self) -> None:
        """Update icons for all tabs based on their hierarchy depth."""
        for tab_id in self._tabs.keys():
            self._update_tab_icon(tab_id)

    def set_graph_view_factory(
        self,
        create_view: Callable[[], "NodeGraphView"],
        create_graph: Callable[[], "Graph"],
    ) -> None:
        """
        Set the factory functions for creating new graph views and graphs.

        Args:
            create_view: Function that creates a new NodeGraphView.
            create_graph: Function that creates a new Graph.
        """
        self._create_graph_view = create_view
        self._create_graph = create_graph

    def create_new_workflow(
        self,
        name: str = "Untitled Workflow",
        graph: Optional["Graph"] = None,
    ) -> str:
        """
        Create a new workflow tab.

        Args:
            name: Name for the new workflow.
            graph: Optional existing graph to use.

        Returns:
            The ID of the created tab.
        """
        if self._create_graph_view is None or self._create_graph is None:
            raise RuntimeError("Graph view factory not set")

        # Create new graph and view
        new_graph = graph if graph is not None else self._create_graph()
        logger.debug(
            "create_new_workflow: graph param id=%s, new_graph id=%s, same=%s",
            id(graph) if graph is not None else None,
            id(new_graph),
            graph is new_graph if graph is not None else "N/A",
        )
        new_view = self._create_graph_view()
        new_view.load_graph(new_graph)

        # Update graph name
        new_graph.name = name

        # Create tab data
        tab = WorkflowTab(
            name=name,
            graph=new_graph,
            graph_view=new_view,
        )

        # Add to storage
        self._tabs[tab.tab_id] = tab

        # Add tab to widget
        index = self.addTab(new_view, tab.display_name)
        self._tab_index_to_id[index] = tab.tab_id

        # Set tooltip and hierarchy icon
        self.setTabToolTip(index, tab.tooltip)
        self._update_tab_icon(tab.tab_id)

        # Set tab styling metadata (root workflow)
        self._custom_tab_bar.set_tab_metadata(index, False, 0, pinned=False)

        # Switch to new tab
        self.setCurrentIndex(index)

        # Emit signal
        self.workflow_created.emit(tab.tab_id)

        return tab.tab_id

    def open_workflow(self, file_path: str, graph: "Graph") -> str:
        """
        Open a workflow from a file.

        Args:
            file_path: Path to the workflow file.
            graph: The loaded graph.

        Returns:
            The ID of the created tab.
        """
        if self._create_graph_view is None:
            raise RuntimeError("Graph view factory not set")

        path = Path(file_path)

        # Check if already open
        for tab_id, tab in self._tabs.items():
            if tab.file_path == path:
                # Switch to existing tab
                self._switch_to_tab(tab_id)
                return tab_id

        # Create new view
        new_view = self._create_graph_view()
        new_view.load_graph(graph)

        # Create tab data
        tab = WorkflowTab(
            name=path.stem,
            file_path=path,
            graph=graph,
            graph_view=new_view,
        )

        # Add to storage
        self._tabs[tab.tab_id] = tab

        # Add tab to widget
        index = self.addTab(new_view, tab.display_name)
        self._tab_index_to_id[index] = tab.tab_id

        # Set tooltip and hierarchy icon
        self.setTabToolTip(index, tab.tooltip)
        self._update_tab_icon(tab.tab_id)

        # Set tab styling metadata (root workflow from file)
        self._custom_tab_bar.set_tab_metadata(index, False, 0, pinned=False)

        # Switch to new tab
        self.setCurrentIndex(index)

        # Emit signal
        self.workflow_created.emit(tab.tab_id)

        return tab.tab_id

    def open_subworkflow(
        self,
        parent_tab_id: str,
        subgraph_node_id: str,
        subgraph_data: Optional[Dict[str, Any]] = None,
        name: str = "Subworkflow",
        library_file_path: Optional[str] = None,
    ) -> str:
        """
        Open a subworkflow for editing in a new tab.

        For reference-based nodes, pass library_file_path to load from file.
        For legacy embedded nodes, pass subgraph_data.

        Args:
            parent_tab_id: ID of the parent workflow tab.
            subgraph_node_id: ID of the SubgraphNode being edited.
            subgraph_data: Legacy embedded graph data (optional).
            name: Display name for the subworkflow.
            library_file_path: Path to the library .vpy file (optional).

        Returns:
            The ID of the created tab.
        """
        if self._create_graph_view is None or self._create_graph is None:
            raise RuntimeError("Graph view factory not set")

        # Check if already open by library file path
        if library_file_path:
            for tab_id, tab in self._tabs.items():
                if tab.file_path and str(tab.file_path) == library_file_path:
                    self._switch_to_tab(tab_id)
                    return tab_id

        # Check if already open by parent/node ID
        for tab_id, tab in self._tabs.items():
            if (tab.is_subworkflow and
                tab.parent_workflow_id == parent_tab_id and
                tab.subgraph_node_id == subgraph_node_id):
                self._switch_to_tab(tab_id)
                return tab_id

        if library_file_path:
            # Reference-based: load from library file using ProjectSerializer
            from visualpython.serialization.project_serializer import ProjectSerializer
            from visualpython.nodes.registry import get_node_registry

            serializer = ProjectSerializer(get_node_registry())
            new_graph = serializer.load(library_file_path)
            new_graph.name = name
        elif subgraph_data:
            # Legacy embedded: deserialize from dict
            from visualpython.graph.graph import Graph
            from visualpython.nodes.registry import get_node_registry

            registry = get_node_registry()

            def node_factory(node_data: Dict[str, Any]) -> Any:
                node_type = node_data.get("type")
                if not node_type:
                    raise ValueError("Node data missing 'type' field")
                node_type_info = registry.get_node_type(node_type)
                if node_type_info is None:
                    raise ValueError(f"Unknown node type: '{node_type}'")
                return node_type_info.node_class.from_dict(node_data)

            new_graph = Graph.from_dict(subgraph_data, node_factory)
            new_graph.name = name
        else:
            raise ValueError("Either subgraph_data or library_file_path must be provided")

        # Create new view
        new_view = self._create_graph_view()
        new_view.load_graph(new_graph)

        # Calculate hierarchy depth based on parent's depth
        parent_tab = self._tabs.get(parent_tab_id)
        parent_depth = parent_tab.hierarchy_depth if parent_tab else 0

        # Create tab data
        tab = WorkflowTab(
            name=name,
            file_path=Path(library_file_path) if library_file_path else None,
            graph=new_graph,
            graph_view=new_view,
            is_subworkflow=True,
            parent_workflow_id=parent_tab_id,
            subgraph_node_id=subgraph_node_id,
            hierarchy_depth=parent_depth + 1,
        )

        # Add to storage
        self._tabs[tab.tab_id] = tab

        # Add tab to widget
        index = self.addTab(new_view, tab.display_name)
        self._tab_index_to_id[index] = tab.tab_id

        # Set tooltip and hierarchy icon
        self.setTabToolTip(index, tab.tooltip)
        self._update_tab_icon(tab.tab_id)

        # Set tab styling metadata (subworkflow with depth-based coloring)
        self._custom_tab_bar.set_tab_metadata(
            index,
            is_subworkflow=True,
            hierarchy_depth=tab.hierarchy_depth
        )

        # Switch to new tab
        self.setCurrentIndex(index)

        # Emit signals
        self.workflow_created.emit(tab.tab_id)
        self.subworkflow_opened.emit(tab.tab_id, parent_tab_id)
        self.hierarchy_changed.emit()  # Hierarchy changed due to new subworkflow

        return tab.tab_id

    def close_tab(self, tab_id: str, force: bool = False) -> bool:
        """
        Close a workflow tab.

        If the tab has child tabs (subworkflows) open, the user will be
        prompted to either close all children or cancel.

        For subworkflow tabs with unsaved changes, a specialized confirmation
        dialog is shown offering to sync changes to the parent before closing.

        Args:
            tab_id: ID of the tab to close.
            force: If True, close without prompting for save.

        Returns:
            True if the tab was closed, False if cancelled.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return False

        # Check for child tabs (subworkflows opened from this tab)
        # Child tabs are ALWAYS closed when closing a parent to prevent orphaned
        # subworkflow tabs that can't sync back to their parent.
        children = self.get_child_tabs(tab_id)
        if children:
            # Get all descendants (children, grandchildren, etc.)
            descendants = self.get_all_descendant_tabs(tab_id)

            # If not forcing and there are modified descendants, show confirmation
            if not force:
                has_modified = any(d.is_modified for d in descendants)
                if has_modified:
                    child_names = ", ".join(c.name for c in children[:3])
                    if len(children) > 3:
                        child_names += f" and {len(children) - 3} more"

                    result = QMessageBox.question(
                        self,
                        "Close Workflow and Subworkflows",
                        f"This workflow has subworkflow tabs open: {child_names}\n\n"
                        "Closing this workflow will also close all subworkflow tabs.\n"
                        "Some subworkflows have unsaved changes that will need to be "
                        "synced or discarded.\n\n"
                        "Continue?",
                        QMessageBox.StandardButton.Yes |
                        QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel,
                    )

                    if result == QMessageBox.StandardButton.Cancel:
                        return False

            # Close all descendants first (in reverse order: grandchildren before children)
            for descendant in reversed(descendants):
                # Handle unsaved changes in descendants (unless forcing)
                if descendant.is_modified and not force:
                    close_result = self._show_subworkflow_close_confirmation(
                        descendant, parent_initiated=True
                    )
                    if close_result == "cancel":
                        return False
                    elif close_result == "save":
                        if not self._save_tab(descendant.tab_id):
                            continue_result = QMessageBox.question(
                                self,
                                "Save Failed",
                                f"Failed to save '{descendant.name}' to library.\n\n"
                                "Close anyway and lose changes?",
                                QMessageBox.StandardButton.Yes |
                                QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No,
                            )
                            if continue_result == QMessageBox.StandardButton.No:
                                return False
                    # "discard" - continue closing without saving

                # Remove the tab
                for index in range(self.count()):
                    if self._tab_index_to_id.get(index) == descendant.tab_id:
                        self.removeTab(index)
                        break
                del self._tabs[descendant.tab_id]
                self.workflow_closed.emit(descendant.tab_id)

            self._rebuild_index_mapping()

        # Check for unsaved changes - use specialized dialog for subworkflows
        if tab.is_modified and not force:
            if tab.is_subworkflow:
                # Use specialized subworkflow close confirmation
                close_result = self._show_subworkflow_close_confirmation(tab)
                if close_result == "cancel":
                    return False
                elif close_result == "save":
                    if not self._save_tab(tab_id):
                        continue_result = QMessageBox.question(
                            self,
                            "Save Failed",
                            f"Failed to save '{tab.name}' to library.\n\n"
                            "Close anyway and lose changes?",
                            QMessageBox.StandardButton.Yes |
                            QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No,
                        )
                        if continue_result == QMessageBox.StandardButton.No:
                            return False
                # "discard" - continue closing without saving
            else:
                # Standard unsaved changes dialog for regular workflows
                result = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    f"'{tab.name}' has unsaved changes. Save before closing?",
                    QMessageBox.StandardButton.Save |
                    QMessageBox.StandardButton.Discard |
                    QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save,
                )

                if result == QMessageBox.StandardButton.Cancel:
                    return False
                elif result == QMessageBox.StandardButton.Save:
                    # Trigger save
                    if not self._save_tab(tab_id):
                        return False

        # Remember if this was a subworkflow (for hierarchy_changed signal)
        was_subworkflow = tab.is_subworkflow

        # Find and remove the tab
        for index in range(self.count()):
            if self._tab_index_to_id.get(index) == tab_id:
                self.removeTab(index)
                break

        # Clean up
        del self._tabs[tab_id]
        self._rebuild_index_mapping()

        # Emit signals
        self.workflow_closed.emit(tab_id)
        if was_subworkflow:
            self.hierarchy_changed.emit()  # Hierarchy changed due to subworkflow close

        return True

    def _show_subworkflow_close_confirmation(self, tab: WorkflowTab, parent_initiated: bool = False) -> str:
        """
        Show a close confirmation dialog for subworkflow tabs.

        Offers options to:
        - Save changes to library and close
        - Close without saving (discard changes)
        - Cancel closing

        Args:
            tab: The subworkflow tab with unsaved changes.
            parent_initiated: Whether this close is triggered by parent tab closing.

        Returns:
            One of: "save", "discard", or "cancel"
        """
        library_path = tab.file_path or "the workflow library"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Unsaved Workflow Changes")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText(f"'{tab.name}' has unsaved changes.")
        msg_box.setInformativeText(
            f"Save changes to the library before closing?\n\n"
            f"Library file: {library_path}\n\n"
            "- Save & Close: Save changes to the library file, then close\n"
            "- Close Without Saving: Close and discard changes\n"
            "- Cancel: Keep this tab open"
        )

        save_button = msg_box.addButton("Save && Close", QMessageBox.ButtonRole.AcceptRole)
        discard_button = msg_box.addButton("Close Without Saving", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        msg_box.setDefaultButton(save_button)

        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QMessageBox QLabel {
                color: #D4D4D4;
            }
            QPushButton {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #555555;
                padding: 6px 16px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #4A4A4A;
                border-color: #666666;
            }
            QPushButton:pressed {
                background-color: #2D2D2D;
            }
        """)

        save_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: #FFFFFF;
                border: 1px solid #5CBF60;
                padding: 6px 16px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #5CBF60;
                border-color: #6CCF70;
            }
            QPushButton:pressed {
                background-color: #3C9F40;
            }
        """)

        discard_button.setStyleSheet("""
            QPushButton {
                background-color: #D32F2F;
                color: #FFFFFF;
                border: 1px solid #E35353;
                padding: 6px 16px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #E35353;
                border-color: #F06060;
            }
            QPushButton:pressed {
                background-color: #B71C1C;
            }
        """)

        msg_box.exec()

        clicked_button = msg_box.clickedButton()
        if clicked_button == save_button:
            return "save"
        elif clicked_button == discard_button:
            return "discard"
        else:
            return "cancel"

    def mark_modified(self, tab_id: str, modified: bool = True) -> None:
        """
        Mark a workflow as modified or unmodified.

        Args:
            tab_id: ID of the tab.
            modified: Whether the workflow is modified.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        tab.is_modified = modified

        # Update tab text
        for index in range(self.count()):
            if self._tab_index_to_id.get(index) == tab_id:
                self.setTabText(index, tab.display_name)
                break

        if modified:
            self.workflow_modified.emit(tab_id)

    def set_view_mode(self, tab_id: str, mode: ViewMode) -> None:
        """
        Set the view mode for a workflow.

        Args:
            tab_id: ID of the tab.
            mode: The view mode to set.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        if tab.view_mode != mode:
            tab.view_mode = mode

            # Update the view
            if tab.graph_view:
                self._apply_view_mode(tab)

            self.view_mode_changed.emit(tab_id, mode)

    def get_view_mode(self, tab_id: str) -> Optional[ViewMode]:
        """Get the current view mode for a tab."""
        tab = self._tabs.get(tab_id)
        return tab.view_mode if tab else None

    def get_current_tab_id(self) -> Optional[str]:
        """Get the ID of the currently active tab."""
        index = self.currentIndex()
        return self._tab_index_to_id.get(index)

    def get_current_tab(self) -> Optional[WorkflowTab]:
        """Get the currently active tab data."""
        tab_id = self.get_current_tab_id()
        return self._tabs.get(tab_id) if tab_id else None

    def get_current_graph(self) -> Optional["Graph"]:
        """Get the graph of the currently active tab."""
        tab = self.get_current_tab()
        return tab.graph if tab else None

    def get_current_graph_view(self) -> Optional["NodeGraphView"]:
        """Get the graph view of the currently active tab."""
        tab = self.get_current_tab()
        return tab.graph_view if tab else None

    def get_tab(self, tab_id: str) -> Optional[WorkflowTab]:
        """Get a tab by its ID."""
        return self._tabs.get(tab_id)

    def get_all_tabs(self) -> List[WorkflowTab]:
        """Get all workflow tabs."""
        return list(self._tabs.values())

    # Parent-child hierarchy tracking methods

    def get_child_tabs(self, tab_id: str) -> List[WorkflowTab]:
        """
        Get all direct child tabs (subworkflows opened from this tab).

        Args:
            tab_id: ID of the parent tab.

        Returns:
            List of child WorkflowTab objects.
        """
        return [
            tab for tab in self._tabs.values()
            if tab.parent_workflow_id == tab_id
        ]

    def get_all_descendant_tabs(self, tab_id: str) -> List[WorkflowTab]:
        """
        Get all descendant tabs (children, grandchildren, etc.) recursively.

        This is useful for determining all tabs that would be affected if
        a parent tab is closed or modified.

        Args:
            tab_id: ID of the ancestor tab.

        Returns:
            List of all descendant WorkflowTab objects, in depth-first order.
        """
        descendants: List[WorkflowTab] = []
        children = self.get_child_tabs(tab_id)

        for child in children:
            descendants.append(child)
            # Recursively get grandchildren
            descendants.extend(self.get_all_descendant_tabs(child.tab_id))

        return descendants

    def get_ancestry_chain(self, tab_id: str) -> List[WorkflowTab]:
        """
        Get the full ancestry chain from root to this tab.

        The chain starts with the root workflow and ends with this tab.
        For a root workflow, returns a list with just that tab.

        Args:
            tab_id: ID of the tab.

        Returns:
            List of WorkflowTab objects from root to this tab.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return []

        chain: List[WorkflowTab] = []
        current = tab

        # Build chain from current to root
        while current:
            chain.insert(0, current)  # Insert at beginning
            if current.parent_workflow_id:
                current = self._tabs.get(current.parent_workflow_id)
            else:
                break

        return chain

    def get_root_tab(self, tab_id: str) -> Optional[WorkflowTab]:
        """
        Get the root (top-level) workflow tab for a given tab.

        For a root workflow, returns itself.

        Args:
            tab_id: ID of the tab.

        Returns:
            The root WorkflowTab, or None if tab not found.
        """
        chain = self.get_ancestry_chain(tab_id)
        return chain[0] if chain else None

    def get_parent_tab(self, tab_id: str) -> Optional[WorkflowTab]:
        """
        Get the direct parent tab for a subworkflow.

        Args:
            tab_id: ID of the subworkflow tab.

        Returns:
            The parent WorkflowTab, or None if this is a root tab or not found.
        """
        tab = self._tabs.get(tab_id)
        if not tab or not tab.parent_workflow_id:
            return None
        return self._tabs.get(tab.parent_workflow_id)

    def is_parent_available(self, tab_id: str) -> tuple[bool, str]:
        """
        Check if a subworkflow tab's parent is available for syncing.

        This checks both that the parent tab exists AND that the SubgraphNode
        in the parent workflow still exists. A subworkflow can become orphaned
        if the parent tab was closed or if the SubgraphNode was deleted.

        Args:
            tab_id: ID of the subworkflow tab.

        Returns:
            A tuple of (is_available, reason) where:
            - is_available: True if parent is available for sync operations
            - reason: Empty string if available, or explanation if not
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return False, "Tab not found"

        if not tab.is_subworkflow:
            return False, "Not a subworkflow tab"

        if not tab.parent_workflow_id:
            return False, "No parent workflow ID"

        # Check if parent tab exists
        parent_tab = self._tabs.get(tab.parent_workflow_id)
        if not parent_tab:
            return False, "Parent workflow tab was closed"

        # Use 'is None' instead of truthiness because Graph.__len__
        # returns 0 for empty graphs, making them falsy.
        if parent_tab.graph is None:
            return False, "Parent workflow has no graph"

        # Check if the SubgraphNode still exists in the parent
        subgraph_node = parent_tab.graph.get_node(tab.subgraph_node_id)
        if not subgraph_node:
            return False, "Subgraph node was deleted from parent"

        return True, ""

    def get_hierarchy_depth(self, tab_id: str) -> int:
        """
        Get the nesting depth of a tab in the subgraph hierarchy.

        Root workflows have depth 0. Direct subgraphs have depth 1, etc.

        Args:
            tab_id: ID of the tab.

        Returns:
            The hierarchy depth (0 for root, 1 for first-level subgraph, etc.)
        """
        tab = self._tabs.get(tab_id)
        return tab.hierarchy_depth if tab else 0

    def has_child_tabs(self, tab_id: str) -> bool:
        """
        Check if a tab has any child tabs (subworkflows) open.

        Args:
            tab_id: ID of the tab.

        Returns:
            True if the tab has open child tabs.
        """
        return len(self.get_child_tabs(tab_id)) > 0

    def has_modified_descendants(self, tab_id: str) -> bool:
        """
        Check if any descendant tabs have unsaved modifications.

        Args:
            tab_id: ID of the ancestor tab.

        Returns:
            True if any descendant has unsaved changes.
        """
        descendants = self.get_all_descendant_tabs(tab_id)
        return any(tab.is_modified for tab in descendants)

    def get_hierarchy_info(self, tab_id: str) -> Dict[str, Any]:
        """
        Get comprehensive hierarchy information for a tab.

        Returns a dictionary with:
        - tab: The tab itself
        - depth: Hierarchy depth (0 = root)
        - parent: Parent tab (if any)
        - children: Direct child tabs
        - all_descendants: All descendant tabs
        - ancestry_chain: Full chain from root to this tab
        - root: The root workflow tab
        - is_root: Whether this is a root workflow

        Args:
            tab_id: ID of the tab.

        Returns:
            Dictionary with hierarchy information.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return {}

        children = self.get_child_tabs(tab_id)
        descendants = self.get_all_descendant_tabs(tab_id)
        ancestry = self.get_ancestry_chain(tab_id)
        parent = self.get_parent_tab(tab_id)
        root = self.get_root_tab(tab_id)

        return {
            "tab": tab,
            "depth": tab.hierarchy_depth,
            "parent": parent,
            "children": children,
            "all_descendants": descendants,
            "ancestry_chain": ancestry,
            "root": root,
            "is_root": not tab.is_subworkflow,
            "has_children": len(children) > 0,
            "descendant_count": len(descendants),
            "has_modified_descendants": any(d.is_modified for d in descendants),
        }

    def get_hierarchy_breadcrumb(self, tab_id: str, separator: str = " › ") -> str:
        """
        Get a formatted breadcrumb string showing the hierarchy path.

        For example: "MainWorkflow › ProcessData › FilterItems"

        Args:
            tab_id: ID of the tab.
            separator: String to use between hierarchy levels.

        Returns:
            Formatted breadcrumb string.
        """
        ancestry = self.get_ancestry_chain(tab_id)
        if not ancestry:
            return ""
        return separator.join(tab.name for tab in ancestry)

    def close_with_descendants(self, tab_id: str, force: bool = False) -> bool:
        """
        Close a tab and all its descendant tabs.

        This ensures proper cleanup when closing a parent workflow that
        has subworkflow tabs open.

        Args:
            tab_id: ID of the tab to close.
            force: If True, close without prompting for save.

        Returns:
            True if all tabs were closed, False if cancelled.
        """
        # Get all descendants first (in reverse depth order so we close deepest first)
        descendants = self.get_all_descendant_tabs(tab_id)

        # Check for unsaved changes in any descendant
        if not force:
            modified_descendants = [d for d in descendants if d.is_modified]
            if modified_descendants:
                names = ", ".join(d.name for d in modified_descendants[:3])
                if len(modified_descendants) > 3:
                    names += f" and {len(modified_descendants) - 3} more"

                result = QMessageBox.question(
                    self,
                    "Unsaved Changes in Subworkflows",
                    f"The following subworkflows have unsaved changes: {names}\n\n"
                    "Close all anyway?",
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )

                if result == QMessageBox.StandardButton.No:
                    return False

        # Close descendants in reverse order (deepest first)
        for descendant in reversed(descendants):
            if not self.close_tab(descendant.tab_id, force=True):
                return False

        # Now close the parent tab itself
        return self.close_tab(tab_id, force=force)

    def navigate_to_parent(self, tab_id: str) -> bool:
        """
        Navigate to the parent tab of a subworkflow.

        Args:
            tab_id: ID of the subworkflow tab.

        Returns:
            True if navigation succeeded, False if tab has no parent.
        """
        parent = self.get_parent_tab(tab_id)
        if parent:
            self._switch_to_tab(parent.tab_id)
            return True
        return False

    def navigate_to_root(self, tab_id: str) -> bool:
        """
        Navigate to the root workflow tab for any subworkflow.

        Args:
            tab_id: ID of any tab in the hierarchy.

        Returns:
            True if navigation succeeded.
        """
        root = self.get_root_tab(tab_id)
        if root:
            self._switch_to_tab(root.tab_id)
            return True
        return False

    def rename_tab(self, tab_id: str, new_name: str) -> None:
        """
        Rename a workflow tab.

        Args:
            tab_id: ID of the tab.
            new_name: New name for the workflow.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        tab.name = new_name
        if tab.graph:
            tab.graph.name = new_name

        # Update tab text
        for index in range(self.count()):
            if self._tab_index_to_id.get(index) == tab_id:
                self.setTabText(index, tab.display_name)
                self.setTabToolTip(index, tab.tooltip)
                break

        self.mark_modified(tab_id, True)

    # Internal methods

    def _switch_to_tab(self, tab_id: str) -> None:
        """Switch to a specific tab by ID."""
        for index in range(self.count()):
            if self._tab_index_to_id.get(index) == tab_id:
                self.setCurrentIndex(index)
                break

    def _rebuild_index_mapping(self) -> None:
        """Rebuild the index to ID mapping and tab bar metadata after tab changes."""
        self._tab_index_to_id.clear()
        new_metadata: Dict[int, Dict[str, Any]] = {}

        for index in range(self.count()):
            widget = self.widget(index)
            for tab_id, tab in self._tabs.items():
                if tab.graph_view is widget:
                    self._tab_index_to_id[index] = tab_id
                    # Store metadata for tab styling
                    new_metadata[index] = {
                        "is_subworkflow": tab.is_subworkflow,
                        "hierarchy_depth": tab.hierarchy_depth,
                    }
                    break

        # Update tab bar metadata for styling
        self._custom_tab_bar.update_metadata_indices(new_metadata)

    def _on_current_changed(self, index: int) -> None:
        """Handle tab change."""
        tab_id = self._tab_index_to_id.get(index)
        if tab_id:
            # Update the subworkflow info bar visibility and content
            self._update_subworkflow_info_bar(tab_id)
            self.tab_changed.emit(tab_id)

    def _on_tab_moved(self, from_index: int, to_index: int) -> None:
        """
        Handle tab moved event to ensure main (root) tab stays at position 0.

        If the root workflow tab is moved away from position 0, or another tab
        is moved to position 0 displacing the root, this method moves the root
        tab back to position 0.

        Args:
            from_index: The original index of the moved tab.
            to_index: The new index of the moved tab.
        """
        # Find the root workflow tab (the one that's not a subworkflow)
        root_tab_id = None
        root_current_index = -1

        for index in range(self.count()):
            tab_id = self._tab_index_to_id.get(index)
            if tab_id:
                tab = self._tabs.get(tab_id)
                if tab and not tab.is_subworkflow:
                    root_tab_id = tab_id
                    root_current_index = index
                    break

        # If the root tab is not at index 0, move it back
        if root_tab_id and root_current_index != 0:
            # Block signals to prevent infinite loop
            self.blockSignals(True)
            self.tabBar().blockSignals(True)

            try:
                # Move the root tab back to position 0
                self.tabBar().moveTab(root_current_index, 0)

                # Update the internal index mappings
                self._update_tab_index_mappings()
            finally:
                self.blockSignals(False)
                self.tabBar().blockSignals(False)

    def _update_tab_index_mappings(self) -> None:
        """Update internal index-to-id mappings after tab reorder."""
        # Rebuild the index mapping based on current tab order
        new_mapping: Dict[int, str] = {}

        for tab_id, tab in self._tabs.items():
            # Find this tab's current index by its graph_view widget
            for index in range(self.count()):
                if self.widget(index) == tab.graph_view:
                    new_mapping[index] = tab_id
                    break

        self._tab_index_to_id = new_mapping

        # Also update the tab bar metadata indices
        new_metadata: Dict[int, Dict[str, Any]] = {}
        for index, tab_id in new_mapping.items():
            tab = self._tabs.get(tab_id)
            if tab:
                # Root workflows (not subworkflows) are pinned
                new_metadata[index] = {
                    "is_subworkflow": tab.is_subworkflow,
                    "hierarchy_depth": tab.hierarchy_depth,
                    "pinned": not tab.is_subworkflow,  # Pin root workflows
                }

        self._custom_tab_bar.update_metadata_indices(new_metadata)

    def _update_subworkflow_info_bar(self, tab_id: str) -> None:
        """
        Update the subworkflow info bar for the given tab.

        Shows the info bar with relevant controls if the tab is a subworkflow,
        otherwise hides it.

        Args:
            tab_id: ID of the current tab.
        """
        tab = self._tabs.get(tab_id)

        if tab and tab.is_subworkflow:
            # Update breadcrumb to show full hierarchy path
            breadcrumb = self.get_hierarchy_breadcrumb(tab_id)
            self._breadcrumb_label.setText(breadcrumb)

            # Show library file path as tooltip
            if tab.file_path:
                self._breadcrumb_label.setToolTip(f"Library file: {tab.file_path}")

            # Enable buttons
            self._goto_parent_btn.setEnabled(True)
            self._save_workflow_btn.setEnabled(True)

            # Show the info bar
            self._subworkflow_info_bar.setVisible(True)
            self._position_subworkflow_info_bar()
        else:
            # Hide the info bar for non-subworkflow tabs
            self._subworkflow_info_bar.setVisible(False)

    def _position_subworkflow_info_bar(self) -> None:
        """Position the subworkflow info bar at the top of the current tab."""
        if not self._subworkflow_info_bar.isVisible():
            return

        # Get the current widget (graph view)
        current_widget = self.currentWidget()
        if not current_widget:
            return

        # Position the info bar at the top of the tab content area
        # with a small margin
        tab_rect = self.tabBar().geometry()
        margin = 4

        # Calculate position: below the tab bar, aligned with tab content
        x = margin
        y = tab_rect.height() + margin
        width = self.width() - (2 * margin)
        height = self._subworkflow_info_bar.sizeHint().height()

        self._subworkflow_info_bar.setGeometry(x, y, width, height)
        self._subworkflow_info_bar.raise_()  # Ensure it's on top

    def _on_goto_parent_clicked(self) -> None:
        """Handle click on 'Go to Parent' button."""
        tab_id = self.get_current_tab_id()
        if not tab_id:
            return

        tab = self._tabs.get(tab_id)
        if not tab or not tab.is_subworkflow:
            return

        # Check if parent tab exists
        parent_tab = self.get_parent_tab(tab_id)
        if not parent_tab:
            QMessageBox.warning(
                self,
                "Parent Not Found",
                f"Cannot navigate to parent workflow.\n\n"
                f"The parent workflow tab has been closed.",
                QMessageBox.StandardButton.Ok,
            )
            # Update the info bar to show orphan status
            self._update_subworkflow_info_bar(tab_id)
            return

        self.navigate_to_parent(tab_id)

    def _on_save_workflow_clicked(self) -> None:
        """
        Handle click on 'Save Workflow' button.

        Saves the current subworkflow tab directly to its library file.
        The version is auto-incremented by ProjectSerializer.save().
        """
        tab_id = self.get_current_tab_id()
        if not tab_id:
            return

        tab = self._tabs.get(tab_id)
        if not tab:
            return

        file_path = tab.file_path
        if not file_path:
            # Prompt for save location
            from PyQt6.QtWidgets import QFileDialog
            file_path_str, _ = QFileDialog.getSaveFileName(
                self,
                "Save Workflow to Library",
                f"{tab.name}.vpy",
                "VisualPython Projects (*.vpy);;All Files (*)",
            )
            if not file_path_str:
                return
            file_path = Path(file_path_str)

        # Save via ProjectSerializer
        from visualpython.serialization.project_serializer import ProjectSerializer
        from visualpython.nodes.registry import get_node_registry

        serializer = ProjectSerializer(get_node_registry())

        try:
            serializer.save(tab.graph, file_path)
            tab.file_path = Path(file_path) if not isinstance(file_path, Path) else file_path
            self.mark_modified(tab_id, False)

            # Update tab text
            for index in range(self.count()):
                if self._tab_index_to_id.get(index) == tab_id:
                    self.setTabText(index, tab.display_name)
                    self.setTabToolTip(index, tab.tooltip)
                    break

            self.workflow_saved.emit(tab_id, str(file_path))
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save workflow: {e}",
            )

    def _on_tab_close_requested(self, index: int) -> None:
        """Handle tab close request."""
        # Check if this tab is pinned - pinned tabs cannot be closed
        if self._custom_tab_bar.is_tab_pinned(index):
            return  # Ignore close request for pinned tabs

        tab_id = self._tab_index_to_id.get(index)
        if tab_id:
            self.close_tab(tab_id)

    def _show_tab_context_menu(self, pos) -> None:
        """Show context menu for tab bar."""
        index = self.tabBar().tabAt(pos)
        if index < 0:
            return

        tab_id = self._tab_index_to_id.get(index)
        if not tab_id:
            return

        tab = self._tabs.get(tab_id)
        if not tab:
            return

        menu = QMenu(self)

        # Rename action
        rename_action = menu.addAction("Rename...")
        rename_action.triggered.connect(lambda: self._prompt_rename(tab_id))

        menu.addSeparator()

        # View mode submenu
        view_menu = menu.addMenu("View Mode")

        edit_action = view_menu.addAction("Edit Mode")
        edit_action.setCheckable(True)
        edit_action.setChecked(tab.view_mode == ViewMode.EDIT)
        edit_action.triggered.connect(
            lambda: self.set_view_mode(tab_id, ViewMode.EDIT)
        )

        run_action = view_menu.addAction("Run/Debug Mode")
        run_action.setCheckable(True)
        run_action.setChecked(tab.view_mode == ViewMode.RUN)
        run_action.triggered.connect(
            lambda: self.set_view_mode(tab_id, ViewMode.RUN)
        )

        collapsed_action = view_menu.addAction("Collapsed View")
        collapsed_action.setCheckable(True)
        collapsed_action.setChecked(tab.view_mode == ViewMode.COLLAPSED)
        collapsed_action.triggered.connect(
            lambda: self.set_view_mode(tab_id, ViewMode.COLLAPSED)
        )

        expanded_action = view_menu.addAction("Expanded View")
        expanded_action.setCheckable(True)
        expanded_action.setChecked(tab.view_mode == ViewMode.EXPANDED)
        expanded_action.triggered.connect(
            lambda: self.set_view_mode(tab_id, ViewMode.EXPANDED)
        )

        menu.addSeparator()

        # Save action
        save_action = menu.addAction("Save")
        save_action.triggered.connect(lambda: self._save_tab(tab_id))

        if tab.is_subworkflow:
            # Navigate to parent action
            parent_tab = self.get_parent_tab(tab_id)
            if parent_tab:
                goto_parent_action = menu.addAction(f"Go to Parent: {parent_tab.name}")
                goto_parent_action.triggered.connect(
                    lambda: self._switch_to_tab(parent_tab.tab_id)
                )

        # Show child tabs if any
        children = self.get_child_tabs(tab_id)
        if children:
            children_menu = menu.addMenu(f"Open Subworkflows ({len(children)})")
            for child in children:
                child_action = children_menu.addAction(child.name)
                child_action.triggered.connect(
                    lambda checked, cid=child.tab_id: self._switch_to_tab(cid)
                )

        menu.addSeparator()

        # Close action
        close_action = menu.addAction("Close")
        close_action.triggered.connect(lambda: self.close_tab(tab_id))

        # Close others action
        if len(self._tabs) > 1:
            close_others_action = menu.addAction("Close Other Tabs")
            close_others_action.triggered.connect(
                lambda: self._close_other_tabs(tab_id)
            )

        menu.exec(self.tabBar().mapToGlobal(pos))

    def _prompt_rename(self, tab_id: str) -> None:
        """Prompt user to rename a tab."""
        tab = self._tabs.get(tab_id)
        if not tab:
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Workflow",
            "Enter new name:",
            text=tab.name,
        )

        if ok and new_name:
            self.rename_tab(tab_id, new_name)

    def _save_tab(self, tab_id: str) -> bool:
        """
        Save a workflow tab.

        Args:
            tab_id: ID of the tab to save.

        Returns:
            True if saved successfully.
        """
        tab = self._tabs.get(tab_id)
        if not tab:
            return False

        file_path = tab.file_path

        if not file_path:
            # Prompt for file path
            file_path_str, _ = QFileDialog.getSaveFileName(
                self,
                "Save Workflow",
                f"{tab.name}.vpy",
                "VisualPython Projects (*.vpy);;JSON Files (*.json);;All Files (*)",
            )

            if not file_path_str:
                return False

            file_path = Path(file_path_str)

        # Save the graph
        from visualpython.serialization import ProjectSerializer
        from visualpython.nodes.registry import get_node_registry

        registry = get_node_registry()
        serializer = ProjectSerializer(registry)

        try:
            serializer.save(tab.graph, file_path)

            # Update tab
            tab.file_path = file_path
            tab.name = file_path.stem
            self.mark_modified(tab_id, False)

            # Update tab text
            for index in range(self.count()):
                if self._tab_index_to_id.get(index) == tab_id:
                    self.setTabText(index, tab.display_name)
                    self.setTabToolTip(index, tab.tooltip)
                    break

            self.workflow_saved.emit(tab_id, str(file_path))
            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save workflow: {e}",
            )
            return False

    def _close_other_tabs(self, keep_tab_id: str) -> None:
        """Close all tabs except the specified one."""
        tab_ids = list(self._tabs.keys())
        for tab_id in tab_ids:
            if tab_id != keep_tab_id:
                self.close_tab(tab_id)

    def _apply_view_mode(self, tab: WorkflowTab) -> None:
        """
        Apply the view mode to a workflow's graph view.

        Args:
            tab: The workflow tab to update.
        """
        if not tab.graph_view or tab.graph is None:
            return

        scene = tab.graph_view.graph_scene

        if tab.view_mode == ViewMode.EDIT:
            # Standard editing mode
            scene.set_view_mode_edit()

        elif tab.view_mode == ViewMode.RUN:
            # Run/debug mode - highlight execution state
            scene.set_view_mode_run()

        elif tab.view_mode == ViewMode.COLLAPSED:
            # Collapsed view - hide subgraph internals
            scene.set_view_mode_collapsed()

        elif tab.view_mode == ViewMode.EXPANDED:
            # Expanded view - show all nested content
            scene.set_view_mode_expanded()

    def resizeEvent(self, event) -> None:
        """
        Handle widget resize to reposition the subworkflow info bar.

        Args:
            event: The resize event.
        """
        super().resizeEvent(event)
        # Reposition the subworkflow info bar if visible
        if hasattr(self, '_subworkflow_info_bar') and self._subworkflow_info_bar.isVisible():
            self._position_subworkflow_info_bar()

    def showEvent(self, event) -> None:
        """
        Handle widget show event.

        Args:
            event: The show event.
        """
        super().showEvent(event)
        # Update info bar visibility for current tab
        tab_id = self.get_current_tab_id()
        if tab_id and hasattr(self, '_subworkflow_info_bar'):
            self._update_subworkflow_info_bar(tab_id)
