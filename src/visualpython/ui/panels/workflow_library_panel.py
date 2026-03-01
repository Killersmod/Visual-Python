"""
Workflow library panel for browsing and managing saved workflows.

This module provides a panel for browsing, searching, and managing
saved workflow files that can be used as subworkflows in other workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import json

from PyQt6.QtCore import Qt, pyqtSignal, QDir, QFileSystemWatcher, QSize, QMimeData
from PyQt6.QtGui import QIcon, QAction, QDrag, QColor, QPainter, QPixmap, QFont, QBrush
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLineEdit,
    QPushButton,
    QToolButton,
    QMenu,
    QLabel,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QSplitter,
    QTextEdit,
    QFrame,
    QHeaderView,
    QAbstractItemView,
)

from visualpython.utils.logging import get_logger

# MIME type for workflow drag and drop
WORKFLOW_MIME_TYPE = "application/x-visualpython-workflow"

logger = get_logger(__name__)


class WorkflowLibraryTree(QTreeWidget):
    """
    Tree widget for workflow library with drag support.

    Enables dragging workflow items to the graph canvas to insert them
    as subworkflow nodes.
    """

    delete_pressed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the workflow library tree."""
        super().__init__(parent)
        self._drag_start_position = None
        self._workflows: Dict[str, "WorkflowInfo"] = {}

    def set_workflows(self, workflows: Dict[str, "WorkflowInfo"]) -> None:
        """Set the workflows dictionary reference for drag operations."""
        self._workflows = workflows

    def keyPressEvent(self, event) -> None:
        """Emit delete_pressed when Delete key is pressed."""
        if event.key() == Qt.Key.Key_Delete:
            self.delete_pressed.emit()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        """Record position for drag detection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Start drag if mouse moved enough after press."""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        if self._drag_start_position is None:
            super().mouseMoveEvent(event)
            return

        # Check if we've moved enough for a drag
        distance = (event.position().toPoint() - self._drag_start_position).manhattanLength()
        if distance < 10:  # Minimum drag distance
            super().mouseMoveEvent(event)
            return

        # Get the item being dragged
        item = self.currentItem()
        if item is None:
            super().mouseMoveEvent(event)
            return

        # Check if it's a workflow (not a folder)
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if file_path and file_path in self._workflows:
            self._start_drag(item, file_path)

    def _start_drag(self, item: QTreeWidgetItem, file_path: str) -> None:
        """
        Start a drag operation for a workflow item.

        Args:
            item: The tree widget item being dragged.
            file_path: Path to the workflow file.
        """
        info = self._workflows.get(file_path)
        if not info:
            return

        # Create MIME data with the workflow file path
        mime_data = QMimeData()
        mime_data.setData(WORKFLOW_MIME_TYPE, file_path.encode("utf-8"))

        # Create drag object
        drag = QDrag(self)
        drag.setMimeData(mime_data)

        # Create a pixmap for the drag preview
        pixmap = self._create_drag_pixmap(info)
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        # Execute the drag
        drag.exec(Qt.DropAction.CopyAction)

        # Reset drag start position
        self._drag_start_position = None

    def _create_drag_pixmap(self, info: "WorkflowInfo") -> QPixmap:
        """
        Create a pixmap for the drag preview.

        Args:
            info: The workflow info being dragged.

        Returns:
            A pixmap showing the workflow being dragged.
        """
        # Create pixmap with workflow info
        width = 160
        height = 40
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded rectangle with subgraph color (purple)
        color = QColor("#9C27B0")
        painter.setBrush(color)
        painter.setPen(color.darker(120))
        painter.drawRoundedRect(2, 2, width - 4, height - 4, 6, 6)

        # Draw text
        painter.setPen(Qt.GlobalColor.white)
        text = info.name if len(info.name) <= 20 else info.name[:17] + "..."
        painter.drawText(10, 26, text)

        painter.end()
        return pixmap


@dataclass
class WorkflowInfo:
    """
    Information about a workflow file.

    Attributes:
        file_path: Path to the workflow file.
        name: Display name of the workflow.
        description: Description of the workflow.
        author: Author of the workflow.
        version: Version string.
        tags: List of tags for categorization.
        created_at: Creation timestamp.
        modified_at: Last modified timestamp.
        node_count: Number of nodes in the workflow.
        input_count: Number of inputs (for subworkflows).
        output_count: Number of outputs (for subworkflows).
        is_subworkflow: Whether this is designed as a subworkflow.
    """

    file_path: Path
    name: str = "Untitled"
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    modified_at: str = ""
    node_count: int = 0
    input_count: int = 0
    output_count: int = 0
    is_subworkflow: bool = False

    @classmethod
    def from_file(cls, file_path: Path) -> Optional["WorkflowInfo"]:
        """
        Load workflow info from a file.

        Args:
            file_path: Path to the workflow file.

        Returns:
            WorkflowInfo if successfully loaded, None otherwise.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            graph_data = data.get("graph", data)
            metadata = graph_data.get("metadata", {})
            nodes = graph_data.get("nodes", [])

            # Count inputs/outputs for subworkflow detection
            input_count = sum(
                1 for n in nodes if n.get("type") == "subgraph_input"
            )
            output_count = sum(
                1 for n in nodes if n.get("type") == "subgraph_output"
            )

            return cls(
                file_path=file_path,
                name=metadata.get("name", file_path.stem),
                description=metadata.get("description", ""),
                author=metadata.get("author", ""),
                version=metadata.get("version", "1.0.0"),
                tags=metadata.get("tags", []),
                created_at=metadata.get("created_at", ""),
                modified_at=metadata.get("modified_at", ""),
                node_count=len(nodes),
                input_count=input_count,
                output_count=output_count,
                is_subworkflow=input_count > 0 or output_count > 0,
            )

        except Exception:
            logger.debug("Failed to load workflow info", exc_info=True)
            return None


class WorkflowLibraryPanel(QWidget):
    """
    Panel for browsing and managing saved workflows.

    Provides a file browser-like interface for:
    - Browsing workflow files in configured directories
    - Searching workflows by name or tags
    - Viewing workflow details
    - Inserting workflows as subworkflows
    - Managing workflow folders

    Signals:
        workflow_selected: Emitted when a workflow is selected (WorkflowInfo).
        workflow_open_requested: Emitted when user wants to open workflow (file_path).
        workflow_insert_requested: Emitted when user wants to insert as subworkflow (file_path).
        workflow_drag_started: Emitted when drag starts (file_path).
        save_current_requested: Emitted to request saving current workflow to library.
        save_selection_as_workflow_requested: Emitted to convert selection to workflow.
        workflow_added: Emitted when a workflow is added to the library (file_path, name).
        library_refreshed: Emitted after the library refresh completes.
    """

    workflow_selected = pyqtSignal(object)  # WorkflowInfo
    workflow_open_requested = pyqtSignal(str)  # file_path
    workflow_insert_requested = pyqtSignal(str)  # file_path
    workflow_drag_started = pyqtSignal(str)  # file_path
    save_current_requested = pyqtSignal()  # Request to save current workflow to library
    save_selection_as_workflow_requested = pyqtSignal()  # Convert selection to workflow
    workflow_added = pyqtSignal(str, str)  # Emitted when workflow is added (file_path, name)
    library_refreshed = pyqtSignal()  # Emitted after library refresh completes
    workflow_version_changed = pyqtSignal(str, str)  # Emitted when a workflow version changes (file_path, new_version)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the workflow library panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        # State
        self._library_paths: List[Path] = []
        self._workflows: Dict[str, WorkflowInfo] = {}  # file_path -> info
        self._current_selection: Optional[WorkflowInfo] = None
        self._selected_workflows: List[WorkflowInfo] = []
        self._active_workflow_path: Optional[str] = None

        # File watcher for auto-refresh
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)

        # Setup UI
        self._setup_ui()
        self._connect_signals()

        # Load default library path
        self._load_default_library()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with title and buttons
        header = QHBoxLayout()

        title = QLabel("Workflow Library")
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title)

        header.addStretch()

        # Add folder button
        add_folder_btn = QToolButton()
        add_folder_btn.setText("+")
        add_folder_btn.setToolTip("Add library folder")
        add_folder_btn.clicked.connect(self._on_add_folder)
        header.addWidget(add_folder_btn)

        # Refresh button
        refresh_btn = QToolButton()
        refresh_btn.setText("↻")
        refresh_btn.setToolTip("Refresh library")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Action buttons row for creating/saving workflows
        action_row = QHBoxLayout()

        # Create new empty workflow button
        self._new_workflow_btn = QPushButton("+ New")
        self._new_workflow_btn.setToolTip(
            "Create a new empty workflow in the library"
        )
        self._new_workflow_btn.clicked.connect(self._on_new_workflow)
        action_row.addWidget(self._new_workflow_btn)

        # Save current workflow to library button
        self._save_to_library_btn = QPushButton("💾 Save to Library")
        self._save_to_library_btn.setToolTip(
            "Save the current workflow to the library so you can reuse it"
        )
        self._save_to_library_btn.clicked.connect(self._on_save_to_library)
        action_row.addWidget(self._save_to_library_btn)

        # Create workflow from selection button
        self._create_from_selection_btn = QPushButton("✂ From Selection")
        self._create_from_selection_btn.setToolTip(
            "Create a reusable workflow from the selected nodes"
        )
        self._create_from_selection_btn.clicked.connect(self._on_create_from_selection)
        action_row.addWidget(self._create_from_selection_btn)

        layout.addLayout(action_row)

        # Search bar
        search_layout = QHBoxLayout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search workflows...")
        self._search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self._search_input)

        filter_btn = QToolButton()
        filter_btn.setText("⚙")
        filter_btn.setToolTip("Filter options")
        filter_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        filter_btn.setMenu(self._create_filter_menu())
        search_layout.addWidget(filter_btn)

        layout.addLayout(search_layout)

        # Splitter for tree and details
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Workflow tree with custom drag support
        self._tree = WorkflowLibraryTree()
        self._tree.setHeaderLabels(["Name", "Type", "Nodes"])
        self._tree.setColumnCount(3)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # Set column widths
        header_view = self._tree.header()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        splitter.addWidget(self._tree)

        # Details panel
        details_frame = QFrame()
        details_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(8, 8, 8, 8)

        self._details_name = QLabel("Select a workflow")
        self._details_name.setStyleSheet("font-weight: bold; font-size: 12pt;")
        details_layout.addWidget(self._details_name)

        self._details_description = QTextEdit()
        self._details_description.setReadOnly(True)
        self._details_description.setMaximumHeight(60)
        self._details_description.setStyleSheet("background: transparent; border: none;")
        details_layout.addWidget(self._details_description)

        self._details_info = QLabel()
        self._details_info.setWordWrap(True)
        self._details_info.setStyleSheet("color: #888;")
        details_layout.addWidget(self._details_info)

        # Action buttons
        actions_layout = QHBoxLayout()

        self._open_btn = QPushButton("Open")
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open_clicked)
        actions_layout.addWidget(self._open_btn)

        self._insert_btn = QPushButton("Insert as Subworkflow")
        self._insert_btn.setEnabled(False)
        self._insert_btn.clicked.connect(self._on_insert_clicked)
        actions_layout.addWidget(self._insert_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        actions_layout.addWidget(self._delete_btn)

        details_layout.addLayout(actions_layout)

        splitter.addWidget(details_frame)

        # Set splitter proportions
        splitter.setSizes([200, 100])

        layout.addWidget(splitter)

    def _create_filter_menu(self) -> QMenu:
        """Create the filter options menu."""
        menu = QMenu(self)

        # Filter by type
        self._filter_all = menu.addAction("All Workflows")
        self._filter_all.setCheckable(True)
        self._filter_all.setChecked(True)
        self._filter_all.triggered.connect(lambda: self._set_filter("all"))

        self._filter_subworkflows = menu.addAction("Subworkflows Only")
        self._filter_subworkflows.setCheckable(True)
        self._filter_subworkflows.triggered.connect(
            lambda: self._set_filter("subworkflows")
        )

        self._filter_main = menu.addAction("Main Workflows Only")
        self._filter_main.setCheckable(True)
        self._filter_main.triggered.connect(lambda: self._set_filter("main"))

        menu.addSeparator()

        # Sort options
        sort_menu = menu.addMenu("Sort by")
        sort_menu.addAction("Name").triggered.connect(
            lambda: self._set_sort("name")
        )
        sort_menu.addAction("Modified").triggered.connect(
            lambda: self._set_sort("modified")
        )
        sort_menu.addAction("Node count").triggered.connect(
            lambda: self._set_sort("nodes")
        )

        return menu

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.delete_pressed.connect(self._on_delete_clicked)

    def _load_default_library(self) -> None:
        """Load the default library path."""
        # Default to user's documents folder
        default_path = Path.home() / "VisualPython" / "Workflows"
        if not default_path.exists():
            default_path.mkdir(parents=True, exist_ok=True)

        self.add_library_path(default_path)

    def add_library_path(self, path: Path) -> None:
        """
        Add a library folder to scan for workflows.

        Args:
            path: Path to the library folder.
        """
        if path not in self._library_paths:
            self._library_paths.append(path)
            if path.exists():
                self._watcher.addPath(str(path))
            self.refresh()

    def remove_library_path(self, path: Path) -> None:
        """
        Remove a library folder.

        Args:
            path: Path to remove.
        """
        if path in self._library_paths:
            self._library_paths.remove(path)
            self._watcher.removePath(str(path))
            self.refresh()

    def refresh(self) -> None:
        """Refresh the workflow list from all library paths."""
        self._workflows.clear()

        for lib_path in self._library_paths:
            if lib_path.exists():
                self._scan_directory(lib_path)

        # Update tree's workflows reference for drag support
        self._tree.set_workflows(self._workflows)
        self._update_tree()

        # Emit signal to notify listeners that refresh is complete
        self.library_refreshed.emit()

    def set_active_workflow(self, file_path: Optional[str]) -> None:
        """Highlight the tree item matching the given file path as the active workflow."""
        self._active_workflow_path = file_path
        active_resolved = str(Path(file_path).resolve()) if file_path else None

        for i in range(self._tree.topLevelItemCount()):
            folder_item = self._tree.topLevelItem(i)
            for j in range(folder_item.childCount()):
                child = folder_item.child(j)
                item_path = child.data(0, Qt.ItemDataRole.UserRole)
                is_active = (
                    active_resolved is not None
                    and item_path is not None
                    and str(Path(item_path).resolve()) == active_resolved
                )
                font = child.font(0)
                font.setBold(is_active)
                for col in range(3):
                    child.setFont(col, font)
                    child.setBackground(
                        col,
                        QBrush(QColor("#2a5080")) if is_active else QBrush(),
                    )
                if is_active:
                    child.setForeground(0, QBrush(QColor("#ffffff")))
                else:
                    child.setForeground(0, QBrush())

    def notify_subworkflow_added(self, file_path: str, name: str) -> None:
        """
        Notify the library that a subworkflow has been added externally.

        This method should be called when a subworkflow is created and saved
        to the library by another component (e.g., ApplicationController).
        It triggers an immediate refresh to ensure the new workflow appears
        in the library panel.

        Args:
            file_path: Path to the newly added workflow file.
            name: Name of the workflow.

        Example:
            >>> # After creating a subworkflow programmatically
            >>> library_panel.notify_subworkflow_added(
            ...     "/path/to/subworkflow.vpy",
            ...     "My Subworkflow"
            ... )
        """
        # Cancel any pending debounced refresh to ensure immediate update
        if hasattr(self, "_refresh_timer") and self._refresh_timer.isActive():
            self._refresh_timer.stop()

        # Perform immediate refresh
        self.refresh()

        # Emit signal to notify about the new workflow
        self.workflow_added.emit(file_path, name)

    def _scan_directory(self, directory: Path, parent_path: str = "") -> None:
        """
        Scan a directory for workflow files.

        Args:
            directory: Directory to scan.
            parent_path: Parent path for nested directories.
        """
        try:
            for item in directory.iterdir():
                if item.is_dir():
                    # Recurse into subdirectories
                    self._scan_directory(item, f"{parent_path}/{item.name}")
                elif item.suffix in (".vpy", ".json", ".vns"):
                    # Try to load workflow info
                    info = WorkflowInfo.from_file(item)
                    if info:
                        self._workflows[str(item)] = info
        except PermissionError:
            logger.debug("Permission denied scanning directory", exc_info=True)
            pass

    def _update_tree(self) -> None:
        """Update the tree widget with current workflows."""
        self._tree.clear()

        # Group by folder
        folders: Dict[str, QTreeWidgetItem] = {}

        for file_path, info in sorted(
            self._workflows.items(), key=lambda x: x[1].name.lower()
        ):
            # Get folder path
            path = Path(file_path)
            parent_folder = str(path.parent)

            # Get or create folder item
            if parent_folder not in folders:
                folder_item = QTreeWidgetItem([path.parent.name, "", ""])
                folder_item.setData(0, Qt.ItemDataRole.UserRole, parent_folder)
                folder_item.setExpanded(True)
                self._tree.addTopLevelItem(folder_item)
                folders[parent_folder] = folder_item

            # Create workflow item
            workflow_type = "Subworkflow" if info.is_subworkflow else "Workflow"
            item = QTreeWidgetItem([
                info.name,
                workflow_type,
                str(info.node_count),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, file_path)
            item.setToolTip(0, info.description or str(path))

            folders[parent_folder].addChild(item)

        # Apply current search filter
        self._apply_search_filter()

        # Re-apply active workflow highlighting after tree rebuild
        if self._active_workflow_path:
            self.set_active_workflow(self._active_workflow_path)

    def _apply_search_filter(self) -> None:
        """Apply the current search filter to the tree."""
        search_text = self._search_input.text().lower()

        for i in range(self._tree.topLevelItemCount()):
            folder_item = self._tree.topLevelItem(i)
            folder_visible = False

            for j in range(folder_item.childCount()):
                item = folder_item.child(j)
                file_path = item.data(0, Qt.ItemDataRole.UserRole)
                info = self._workflows.get(file_path)

                visible = True
                if search_text:
                    # Search in name, description, and tags
                    text_match = (
                        search_text in info.name.lower() or
                        search_text in info.description.lower() or
                        any(search_text in tag.lower() for tag in info.tags)
                    )
                    visible = text_match

                item.setHidden(not visible)
                if visible:
                    folder_visible = True

            folder_item.setHidden(not folder_visible)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._apply_search_filter()

    def _on_selection_changed(self) -> None:
        """Handle tree selection change."""
        items = self._tree.selectedItems()
        if not items:
            self._current_selection = None
            self._selected_workflows = []
            self._update_details(None)
            return

        # Build list of selected workflows (skip folder items)
        selected: List[WorkflowInfo] = []
        for item in items:
            file_path = item.data(0, Qt.ItemDataRole.UserRole)
            info = self._workflows.get(file_path)
            if info:
                selected.append(info)

        self._selected_workflows = selected

        if len(selected) == 1:
            self._current_selection = selected[0]
            self._update_details(selected[0])
            self.workflow_selected.emit(selected[0])
        elif len(selected) > 1:
            self._current_selection = selected[0]
            self._update_details_multi(selected)
        else:
            self._current_selection = None
            self._update_details(None)

    def _update_details(self, info: Optional[WorkflowInfo]) -> None:
        """Update the details panel."""
        if info:
            self._details_name.setText(info.name)
            self._details_description.setText(
                info.description or "No description available."
            )

            # Build info text
            info_parts = []
            if info.author:
                info_parts.append(f"Author: {info.author}")
            if info.version:
                info_parts.append(f"Version: {info.version}")
            info_parts.append(f"Nodes: {info.node_count}")
            if info.is_subworkflow:
                info_parts.append(f"Inputs: {info.input_count}, Outputs: {info.output_count}")
            if info.tags:
                info_parts.append(f"Tags: {', '.join(info.tags)}")
            if info.modified_at:
                info_parts.append(f"Modified: {info.modified_at[:10]}")

            self._details_info.setText("\n".join(info_parts))

            self._open_btn.setEnabled(True)
            self._insert_btn.setEnabled(True)
            self._delete_btn.setEnabled(True)
            self._delete_btn.setText("Delete")
        else:
            self._details_name.setText("Select a workflow")
            self._details_description.setText("")
            self._details_info.setText("")
            self._open_btn.setEnabled(False)
            self._insert_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            self._delete_btn.setText("Delete")

    def _update_details_multi(self, infos: List[WorkflowInfo]) -> None:
        """Update the details panel for multiple selections."""
        count = len(infos)
        total_nodes = sum(info.node_count for info in infos)
        self._details_name.setText(f"{count} workflows selected")
        self._details_description.setText("")
        self._details_info.setText(f"Total nodes: {total_nodes}")
        self._open_btn.setEnabled(False)
        self._insert_btn.setEnabled(False)
        self._delete_btn.setEnabled(True)
        self._delete_btn.setText(f"Delete ({count})")

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click on item."""
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if file_path and file_path in self._workflows:
            self.workflow_open_requested.emit(file_path)

    def _on_open_clicked(self) -> None:
        """Handle open button click."""
        if self._current_selection:
            self.workflow_open_requested.emit(str(self._current_selection.file_path))

    def _on_insert_clicked(self) -> None:
        """Handle insert as subworkflow button click."""
        if self._current_selection:
            self.workflow_insert_requested.emit(str(self._current_selection.file_path))

    def _on_delete_clicked(self) -> None:
        """Handle delete button click."""
        if len(self._selected_workflows) > 1:
            self._delete_multiple_workflows(self._selected_workflows)
        elif self._current_selection:
            self._delete_workflow(str(self._current_selection.file_path))

    def _on_add_folder(self) -> None:
        """Handle add folder button click."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Library Folder",
            str(Path.home()),
        )
        if folder:
            self.add_library_path(Path(folder))

    def _on_directory_changed(self, path: str) -> None:
        """Handle directory change from file watcher."""
        # Debounce refreshes
        from PyQt6.QtCore import QTimer
        if not hasattr(self, "_refresh_timer"):
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(500)  # 500ms debounce

    def _show_context_menu(self, pos) -> None:
        """Show context menu for tree items."""
        item = self._tree.itemAt(pos)
        if not item:
            return

        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        info = self._workflows.get(file_path)

        menu = QMenu(self)

        # Check for multi-selection
        if len(self._selected_workflows) > 1:
            count = len(self._selected_workflows)
            delete_action = menu.addAction(f"Delete {count} Selected")
            selected = list(self._selected_workflows)
            delete_action.triggered.connect(
                lambda: self._delete_multiple_workflows(selected)
            )
            menu.exec(self._tree.mapToGlobal(pos))
            return

        if info:
            # Workflow item
            open_action = menu.addAction("Open")
            open_action.triggered.connect(
                lambda: self.workflow_open_requested.emit(file_path)
            )

            insert_action = menu.addAction("Insert as Subworkflow")
            insert_action.triggered.connect(
                lambda: self.workflow_insert_requested.emit(file_path)
            )

            menu.addSeparator()

            # Show in explorer/finder
            show_action = menu.addAction("Show in File Explorer")
            show_action.triggered.connect(
                lambda: self._show_in_explorer(file_path)
            )

            menu.addSeparator()

            # Delete
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(
                lambda: self._delete_workflow(file_path)
            )
        else:
            # Folder item
            remove_action = menu.addAction("Remove from Library")
            remove_action.triggered.connect(
                lambda: self.remove_library_path(Path(file_path))
            )

        menu.exec(self._tree.mapToGlobal(pos))

    def _show_in_explorer(self, file_path: str) -> None:
        """Show file in system file explorer."""
        import subprocess
        import platform

        path = Path(file_path)
        system = platform.system()

        try:
            if system == "Windows":
                subprocess.run(["explorer", "/select,", str(path)])
            elif system == "Darwin":
                subprocess.run(["open", "-R", str(path)])
            else:
                subprocess.run(["xdg-open", str(path.parent)])
        except Exception:
            logger.debug("Failed to reveal workflow in file manager", exc_info=True)
            pass

    def _delete_workflow(self, file_path: str) -> None:
        """Delete a workflow file."""
        info = self._workflows.get(file_path)
        if not info:
            return

        result = QMessageBox.question(
            self,
            "Delete Workflow",
            f"Are you sure you want to delete '{info.name}'?\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            try:
                Path(file_path).unlink()
                self.refresh()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Delete Error",
                    f"Failed to delete workflow: {e}",
                )

    def _delete_multiple_workflows(self, workflows: List[WorkflowInfo]) -> None:
        """Delete multiple workflow files with a single confirmation."""
        if not workflows:
            return

        names = "\n".join(f"  - {info.name}" for info in workflows)
        result = QMessageBox.question(
            self,
            "Delete Workflows",
            f"Are you sure you want to delete {len(workflows)} workflows?\n\n"
            f"{names}\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            errors = []
            for info in workflows:
                try:
                    Path(info.file_path).unlink()
                except Exception as e:
                    errors.append(f"{info.name}: {e}")
            if errors:
                QMessageBox.critical(
                    self,
                    "Delete Errors",
                    "Failed to delete some workflows:\n\n" + "\n".join(errors),
                )
            self.refresh()

    def _set_filter(self, filter_type: str) -> None:
        """Set the workflow type filter."""
        self._filter_all.setChecked(filter_type == "all")
        self._filter_subworkflows.setChecked(filter_type == "subworkflows")
        self._filter_main.setChecked(filter_type == "main")
        self._update_tree()

    def _set_sort(self, sort_by: str) -> None:
        """Set the sort order."""
        # This would re-sort the tree
        self._update_tree()

    def _on_save_to_library(self) -> None:
        """Handle save current workflow to library button click."""
        self.save_current_requested.emit()

    def _on_create_from_selection(self) -> None:
        """Handle create workflow from selection button click."""
        self.save_selection_as_workflow_requested.emit()

    def _on_new_workflow(self) -> None:
        """Handle new workflow button click. Creates an empty workflow file in the library."""
        name, ok = QInputDialog.getText(
            self,
            "New Workflow",
            "Enter a name for the new workflow:",
            text="New Workflow",
        )
        if not ok or not name.strip():
            return
        self._create_empty_workflow(name.strip())

    def _create_empty_workflow(self, name: str) -> Optional[Path]:
        """Create a new empty workflow file in the default library path."""
        # Sanitize the name for filename
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        safe_name = safe_name.strip()
        if not safe_name:
            safe_name = "New_Workflow"

        save_dir = self.get_default_save_path()
        save_dir.mkdir(parents=True, exist_ok=True)

        file_path = save_dir / f"{safe_name}.vpy"

        # Handle filename conflicts
        if file_path.exists():
            counter = 1
            while file_path.exists():
                file_path = save_dir / f"{safe_name}_{counter}.vpy"
                counter += 1

        now = datetime.now().isoformat()

        graph_data = {
            "format_version": "1.0.0",
            "file_type": "visualpython_project",
            "graph": {
                "nodes": [],
                "connections": [],
                "metadata": {
                    "name": name,
                    "description": "",
                    "author": "",
                    "version": "1.0.0",
                    "tags": [],
                    "created_at": now,
                    "modified_at": now,
                },
            },
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, indent=2)

            self.refresh()
            self.workflow_added.emit(str(file_path), name)
            return file_path

        except Exception as e:
            QMessageBox.critical(
                self,
                "Create Error",
                f"Failed to create workflow: {e}",
            )
            return None

    def get_default_save_path(self) -> Path:
        """Get the default path for saving new workflows."""
        if self._library_paths:
            return self._library_paths[0]
        return Path.home() / "VisualPython" / "Workflows"

    def save_workflow_to_library(
        self,
        graph_data: dict,
        name: str,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> Optional[Path]:
        """
        Save a workflow to the library.

        Args:
            graph_data: The serialized graph data.
            name: Name for the workflow.
            description: Optional description.
            tags: Optional list of tags.

        Returns:
            Path where the workflow was saved, or None if cancelled.
        """
        from datetime import datetime

        # Prompt for name if not provided
        if not name:
            name, ok = QInputDialog.getText(
                self,
                "Save Workflow to Library",
                "Enter workflow name:",
                text="My Workflow",
            )
            if not ok or not name:
                return None

        # Sanitize the name for filename
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        safe_name = safe_name.strip()

        # Get save path
        save_dir = self.get_default_save_path()
        save_dir.mkdir(parents=True, exist_ok=True)

        file_path = save_dir / f"{safe_name}.vpy"

        # Check if file exists
        if file_path.exists():
            result = QMessageBox.question(
                self,
                "File Exists",
                f"A workflow named '{name}' already exists.\n\nOverwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return None

        # Add metadata
        if "graph" in graph_data:
            metadata = graph_data["graph"].setdefault("metadata", {})
        else:
            metadata = graph_data.setdefault("metadata", {})

        metadata["name"] = name
        metadata["description"] = description
        metadata["tags"] = tags or []
        metadata["created_at"] = metadata.get("created_at", datetime.now().isoformat())
        metadata["modified_at"] = datetime.now().isoformat()

        # Auto-increment version on save
        from visualpython.serialization.project_serializer import ProjectSerializer
        old_version = metadata.get("version", "1.0.0")
        metadata["version"] = ProjectSerializer.increment_version(old_version)

        # Save the file
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, indent=2)

            # Refresh the library to show the new workflow
            self.refresh()

            # Emit signal to notify listeners about the new workflow
            self.workflow_added.emit(str(file_path), name)

            # Notify about version change so SubgraphNodes can refresh
            self.workflow_version_changed.emit(str(file_path), metadata["version"])

            QMessageBox.information(
                self,
                "Workflow Saved",
                f"Workflow '{name}' has been saved to the library.\n\n"
                f"Location: {file_path}",
            )

            return file_path

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save workflow: {e}",
            )
            return None

    def save_embedded_subgraph_to_library(
        self,
        embedded_graph_data: dict,
        name: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
        silent: bool = False,
        auto_rename: bool = False,
    ) -> Optional[Path]:
        """
        Save embedded subgraph data as a library file.

        This method converts embedded subgraph data (from a SubgraphNode) into
        the standard workflow library format and saves it to the library.

        Args:
            embedded_graph_data: The embedded graph data containing nodes and connections.
                                 Expected format: {"nodes": [...], "connections": [...]}
            name: Name for the workflow. If empty and not silent, prompts the user.
            description: Optional description for the workflow.
            tags: Optional list of tags. Defaults to ["subworkflow"].
            silent: If True, skips all dialogs and confirmation messages.
                   Used for auto-save operations.
            auto_rename: If True, automatically renames to avoid conflicts
                        instead of asking user or failing.

        Returns:
            Path where the workflow was saved, or None if cancelled/failed.

        Example:
            >>> # From a SubgraphNode's embedded data
            >>> subgraph_node = graph.get_node(node_id)
            >>> panel.save_embedded_subgraph_to_library(
            ...     subgraph_node.embedded_graph_data,
            ...     name="My Subworkflow",
            ...     description="A reusable component",
            ...     tags=["utility", "subworkflow"],
            ... )
        """
        from datetime import datetime

        # Validate input
        if not embedded_graph_data:
            if not silent:
                QMessageBox.warning(
                    self,
                    "Invalid Data",
                    "No embedded graph data provided.",
                )
            return None

        # Ensure we have the expected structure
        nodes = embedded_graph_data.get("nodes", [])
        connections = embedded_graph_data.get("connections", [])

        # Prompt for name if not provided and not in silent mode
        if not name:
            if silent:
                name = "Untitled Subworkflow"
            else:
                name, ok = QInputDialog.getText(
                    self,
                    "Save Subgraph to Library",
                    "Enter a name for this subgraph:",
                    text="My Subworkflow",
                )
                if not ok or not name:
                    return None

        # Set default tags
        if tags is None:
            tags = ["subworkflow"]
        elif "subworkflow" not in tags:
            tags = ["subworkflow"] + list(tags)

        # Sanitize the name for filename
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        safe_name = safe_name.strip()
        if not safe_name:
            safe_name = "Untitled_Subworkflow"

        # Get save path
        save_dir = self.get_default_save_path()
        save_dir.mkdir(parents=True, exist_ok=True)

        file_path = save_dir / f"{safe_name}.vpy"

        # Handle file conflicts
        if file_path.exists():
            if auto_rename:
                # Auto-rename to avoid conflicts
                counter = 1
                while file_path.exists():
                    file_path = save_dir / f"{safe_name}_{counter}.vpy"
                    counter += 1
            elif not silent:
                result = QMessageBox.question(
                    self,
                    "File Exists",
                    f"A subgraph named '{name}' already exists.\n\nOverwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if result != QMessageBox.StandardButton.Yes:
                    return None
            else:
                # Silent mode without auto_rename: fail silently on conflict
                return None

        # Count inputs/outputs for metadata
        input_count = sum(
            1 for n in nodes if n.get("type") == "subgraph_input"
        )
        output_count = sum(
            1 for n in nodes if n.get("type") == "subgraph_output"
        )

        # Build the standard workflow library format
        # Must include file_type and format_version so ProjectSerializer.deserialize()
        # can open these files via the "Open" button.
        now = datetime.now().isoformat()

        # Preserve flow entry/exit points from the incoming embedded data so
        # the execution engine knows where to start running inside the subgraph.
        incoming_metadata = embedded_graph_data.get("metadata", {})
        flow_entry_points = incoming_metadata.get("flow_entry_points", [])
        flow_exit_points = incoming_metadata.get("flow_exit_points", [])

        graph_data = {
            "format_version": "1.0.0",
            "file_type": "visualpython_project",
            "graph": {
                "nodes": nodes,
                "connections": connections,
                "metadata": {
                    "name": name,
                    "description": description or f"Subgraph with {len(nodes)} nodes",
                    "author": "",
                    "version": "1.0.0",
                    "tags": tags,
                    "created_at": now,
                    "modified_at": now,
                    "input_count": input_count,
                    "output_count": output_count,
                    "is_subworkflow": True,
                    "flow_entry_points": flow_entry_points,
                    "flow_exit_points": flow_exit_points,
                },
            }
        }

        # Save the file
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, indent=2)

            # Refresh the library to show the new subworkflow
            self.refresh()

            # Emit signal to notify listeners about the new workflow
            # This ensures the library UI is updated even if refresh is debounced
            self.workflow_added.emit(str(file_path), name)

            # Notify about version so SubgraphNodes can track it
            version = graph_data.get("graph", {}).get("metadata", {}).get("version", "1.0.0")
            self.workflow_version_changed.emit(str(file_path), version)

            if not silent:
                QMessageBox.information(
                    self,
                    "Subgraph Saved",
                    f"Subgraph '{name}' has been saved to the library.\n\n"
                    f"Location: {file_path}\n"
                    f"Inputs: {input_count}, Outputs: {output_count}",
                )

            return file_path

        except Exception as e:
            if not silent:
                QMessageBox.critical(
                    self,
                    "Save Error",
                    f"Failed to save subgraph: {e}",
                )
            return None
