"""
Dependency panel for displaying workflow dependency trees.

This module provides a panel widget that automatically scans the current
workflow graph to discover all subgraph/script dependencies (forward) and
which other projects reference this workflow (reverse). Scanning runs in a
background QThread and auto-triggers on graph changes. Dependency trees can
be named, hashed, and persisted to SQLite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QInputDialog,
    QMessageBox,
    QMenu,
)

from visualpython.dependencies.dependency_scanner import (
    DependencyNode,
    DependencyScanner,
    ReverseDependency,
)
from visualpython.utils.logging import get_logger

if TYPE_CHECKING:
    from visualpython.dependencies.dependency_store import DependencyStore
    from visualpython.graph.graph import Graph

logger = get_logger(__name__)

# Colors for dependency node types
DEP_TYPE_COLORS = {
    "reference": QColor("#569CD6"),   # Blue for file references
    "embedded": QColor("#DCDCAA"),    # Yellow for embedded
    "circular": QColor("#F44747"),    # Red for circular refs
    "broken": QColor("#F44747"),      # Red for broken refs
    "reverse": QColor("#C586C0"),     # Purple for reverse deps
    "saved": QColor("#B5CEA8"),       # Green for saved trees
}

# Debounce delay for auto-scan (ms)
_SCAN_DEBOUNCE_MS = 300


class _ScanWorker(QThread):
    """Background thread that runs the dependency scanner."""

    scan_finished = pyqtSignal(list, list)  # forward_tree, reverse_deps

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scanner = DependencyScanner()
        self._graph: Optional["Graph"] = None
        self._file_path: Optional[str] = None
        self._scan_paths: List[Path] = []

    def configure(
        self,
        graph: Optional["Graph"],
        file_path: Optional[str],
        scan_paths: List[Path],
    ) -> None:
        """Configure the next scan. Call before start()."""
        self._graph = graph
        self._file_path = file_path
        self._scan_paths = list(scan_paths)

    def run(self) -> None:
        """Execute scan in background thread."""
        forward: List[DependencyNode] = []
        reverse: List[ReverseDependency] = []

        if self._graph is not None:
            try:
                forward = self._scanner.scan_forward(self._graph)
            except Exception as e:
                logger.debug("Forward scan error: %s", e)

            if self._file_path and self._scan_paths:
                try:
                    reverse = self._scanner.scan_reverse(
                        self._file_path, self._scan_paths
                    )
                except Exception as e:
                    logger.debug("Reverse scan error: %s", e)

        self.scan_finished.emit(forward, reverse)


class DependencyPanelWidget(QWidget):
    """
    Panel widget for displaying workflow dependency trees.

    Scans automatically in the background whenever the graph changes.
    Shows three views via a combo box:
    - Forward dependencies: What subgraphs this workflow uses (recursive)
    - Reverse dependencies: Which other workflows use this one
    - Saved trees: Named dependency trees persisted in SQLite

    Signals:
        dependency_selected: Emitted when a dependency is double-clicked (file_path).
        tree_saved: Emitted when a dependency tree is saved (tree_name, tree_hash).
    """

    dependency_selected = pyqtSignal(str)
    tree_saved = pyqtSignal(str, str)

    VIEW_FORWARD = "forward"
    VIEW_REVERSE = "reverse"
    VIEW_SAVED = "saved"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_graph: Optional["Graph"] = None
        self._current_file_path: Optional[str] = None
        self._library_paths: List[Path] = []
        self._project_paths: List[Path] = []
        self._forward_tree: List[DependencyNode] = []
        self._reverse_deps: List[ReverseDependency] = []
        self._dep_store: Optional["DependencyStore"] = None
        self._scanner = DependencyScanner()

        # Background scan worker
        self._scan_worker = _ScanWorker(self)
        self._scan_worker.scan_finished.connect(self._on_scan_finished)

        # Debounce timer for auto-scan — avoids rapid rescans on burst changes
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(_SCAN_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._do_background_scan)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with title and buttons
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        header_label = QLabel("Dependencies")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)

        self._count_label = QLabel("(0)")
        self._count_label.setStyleSheet("color: #888; font-size: 11px;")
        header_layout.addWidget(self._count_label)

        header_layout.addStretch()

        # View mode combo
        self._view_combo = QComboBox()
        self._view_combo.addItem("Forward Deps", self.VIEW_FORWARD)
        self._view_combo.addItem("Reverse Deps", self.VIEW_REVERSE)
        self._view_combo.addItem("Saved Trees", self.VIEW_SAVED)
        self._view_combo.setMaximumWidth(120)
        self._view_combo.currentIndexChanged.connect(self._on_view_changed)
        self._view_combo.setStyleSheet("""
            QComboBox {
                background-color: #2D2D2D;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 3px;
                padding: 2px 6px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #2D2D2D;
                color: #D4D4D4;
                selection-background-color: #094771;
            }
        """)
        header_layout.addWidget(self._view_combo)

        # Scan button (manual re-scan)
        self._scan_button = QPushButton("Scan")
        self._scan_button.setMaximumWidth(50)
        self._scan_button.setToolTip("Re-scan for dependencies")
        self._scan_button.clicked.connect(self.request_scan)
        header_layout.addWidget(self._scan_button)

        # Save tree button
        self._save_button = QPushButton("Save")
        self._save_button.setMaximumWidth(50)
        self._save_button.setToolTip("Save current dependency tree with a name")
        self._save_button.clicked.connect(self._on_save_tree)
        header_layout.addWidget(self._save_button)

        layout.addLayout(header_layout)

        # Tree widget for displaying dependencies
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Type", "Path"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        # Configure header
        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self._tree.setColumnWidth(0, 150)
        self._tree.setColumnWidth(1, 80)

        # Monospace font
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._tree.setFont(font)

        # Dark theme styling (matches variable_panel.py)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
            }
            QTreeWidget::item {
                padding: 4px 2px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
            }
            QTreeWidget::item:hover {
                background-color: #2A2D2E;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: #D4D4D4;
                padding: 4px 8px;
                border: none;
                border-right: 1px solid #3C3C3C;
                border-bottom: 1px solid #3C3C3C;
            }
            QScrollBar:vertical {
                background-color: #1E1E1E;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #5A5A5A;
                min-height: 20px;
                border-radius: 6px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #787878;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        layout.addWidget(self._tree)

        # Empty state label
        self._empty_label = QLabel("Scanning for dependencies...")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: #888; font-style: italic; padding: 20px;"
        )
        layout.addWidget(self._empty_label)

        self.setMinimumWidth(200)
        self.setMinimumHeight(150)

    # --- Public API ---

    def set_graph(
        self,
        graph: Optional["Graph"],
        file_path: Optional[str] = None,
    ) -> None:
        """Set the current graph and auto-trigger a background scan."""
        self._current_graph = graph
        self._current_file_path = file_path
        self.request_scan()

    def set_library_paths(self, paths: List[Path]) -> None:
        """Set the workflow library paths to scan for reverse dependencies."""
        self._library_paths = list(paths)

    def set_project_paths(self, paths: List[Path]) -> None:
        """Set additional project paths to scan (e.g. Graphs/ directory)."""
        self._project_paths = list(paths)

    def set_dependency_store(self, store: "DependencyStore") -> None:
        """Set the SQLite dependency store."""
        self._dep_store = store

    @pyqtSlot()
    def request_scan(self) -> None:
        """Request a debounced background scan. Safe to call rapidly."""
        self._debounce_timer.start()

    @pyqtSlot()
    def scan(self) -> None:
        """Run scan synchronously (used by the Scan button for immediate feedback)."""
        if self._current_graph is None:
            return

        self._forward_tree = self._scanner.scan_forward(self._current_graph)

        scan_paths = list(self._library_paths) + list(self._project_paths)
        if self._current_file_path:
            self._reverse_deps = self._scanner.scan_reverse(
                self._current_file_path, scan_paths
            )
        else:
            self._reverse_deps = []

        self._update_display()

    # --- Background scanning ---

    def _do_background_scan(self) -> None:
        """Start a background scan if not already running."""
        if self._current_graph is None:
            self._forward_tree = []
            self._reverse_deps = []
            self._update_display()
            return

        if self._scan_worker.isRunning():
            # A scan is already in progress — reschedule
            self._debounce_timer.start()
            return

        scan_paths = list(self._library_paths) + list(self._project_paths)
        self._scan_worker.configure(
            self._current_graph,
            self._current_file_path,
            scan_paths,
        )
        self._scan_worker.start()

    @pyqtSlot(list, list)
    def _on_scan_finished(
        self,
        forward_tree: List[DependencyNode],
        reverse_deps: List[ReverseDependency],
    ) -> None:
        """Handle results from the background scan worker."""
        self._forward_tree = forward_tree
        self._reverse_deps = reverse_deps
        self._update_display()

    # --- Display ---

    def _update_display(self) -> None:
        """Update the tree widget based on the current view mode."""
        view = self._view_combo.currentData()
        if view == self.VIEW_FORWARD:
            self._populate_forward_tree()
        elif view == self.VIEW_REVERSE:
            self._populate_reverse_tree()
        elif view == self.VIEW_SAVED:
            self._populate_saved_trees()

    def _populate_forward_tree(self) -> None:
        """Populate tree with forward dependency data."""
        self._tree.clear()

        if not self._forward_tree:
            self._tree.hide()
            self._empty_label.setText("No subgraph dependencies found.")
            self._empty_label.show()
            self._count_label.setText("(0)")
            return

        self._empty_label.hide()
        self._tree.show()

        count = 0
        for dep in self._forward_tree:
            count += self._add_dep_node_to_tree(dep)

        self._count_label.setText(f"({count})")
        self._tree.expandAll()

    def _populate_reverse_tree(self) -> None:
        """Populate tree with reverse dependency data."""
        self._tree.clear()

        if not self._reverse_deps:
            self._tree.hide()
            self._empty_label.setText("No graphs reference this workflow.")
            self._empty_label.show()
            self._count_label.setText("(0)")
            return

        self._empty_label.hide()
        self._tree.show()

        for rev in self._reverse_deps:
            item = QTreeWidgetItem(self._tree)
            item.setText(0, rev.name)
            item.setText(1, "reverse")
            item.setText(2, rev.file_path)
            item.setToolTip(0, f"Uses this workflow as: {rev.node_name}")
            item.setToolTip(2, rev.file_path)
            item.setData(0, Qt.ItemDataRole.UserRole, rev.file_path)

            color = DEP_TYPE_COLORS["reverse"]
            item.setForeground(1, color)

            if rev.version:
                item.setToolTip(1, f"v{rev.version}")

        self._count_label.setText(f"({len(self._reverse_deps)})")

    def _populate_saved_trees(self) -> None:
        """Populate tree with saved/named dependency trees from SQLite."""
        self._tree.clear()

        if not self._dep_store:
            self._tree.hide()
            self._empty_label.setText("No dependency store configured.")
            self._empty_label.show()
            self._count_label.setText("(0)")
            return

        trees = self._dep_store.list_trees()
        if not trees:
            self._tree.hide()
            self._empty_label.setText(
                "No saved dependency trees. Scan and Save to create one."
            )
            self._empty_label.show()
            self._count_label.setText("(0)")
            return

        self._empty_label.hide()
        self._tree.show()

        for tree_row in trees:
            parent_item = QTreeWidgetItem(self._tree)
            parent_item.setText(0, tree_row["name"])
            parent_item.setText(1, "saved")
            hash_short = tree_row["tree_hash"][:12] + "..."
            parent_item.setText(2, hash_short)
            parent_item.setToolTip(0, f"Graph: {tree_row.get('graph_name', 'N/A')}")
            parent_item.setToolTip(
                2,
                f"Hash: {tree_row['tree_hash']}\n"
                f"File: {tree_row.get('graph_file_path', 'N/A')}\n"
                f"Updated: {tree_row['updated_at']}",
            )
            parent_item.setData(
                0, Qt.ItemDataRole.UserRole, tree_row.get("graph_file_path")
            )
            parent_item.setData(
                0, Qt.ItemDataRole.UserRole + 1, tree_row["name"]
            )

            color = DEP_TYPE_COLORS["saved"]
            parent_item.setForeground(1, color)

            # Expand the saved tree's children
            try:
                dep_list = json.loads(tree_row["tree_json"])
                for dep_data in dep_list:
                    dep_node = DependencyNode.from_dict(dep_data)
                    self._add_dep_node_to_tree(dep_node, parent_item)
            except (json.JSONDecodeError, KeyError):
                pass

        self._count_label.setText(f"({len(trees)})")
        self._tree.expandAll()

    def _add_dep_node_to_tree(
        self,
        dep: DependencyNode,
        parent: Optional[QTreeWidgetItem] = None,
    ) -> int:
        """
        Recursively add a DependencyNode to the QTreeWidget.

        Returns the total count of nodes added.
        """
        if parent is not None:
            item = QTreeWidgetItem(parent)
        else:
            item = QTreeWidgetItem(self._tree)

        item.setText(0, dep.name)
        item.setText(1, dep.node_type)

        path_display = dep.file_path or "(embedded)"
        item.setText(2, path_display)
        item.setToolTip(2, dep.file_path or "Embedded in parent graph")

        if dep.file_path:
            item.setData(0, Qt.ItemDataRole.UserRole, dep.file_path)

        # Color the type column
        if dep.is_broken:
            color = DEP_TYPE_COLORS["broken"]
            item.setForeground(0, color)
            item.setToolTip(0, f"{dep.name} (BROKEN - file not found)")
        elif dep.node_type == "circular":
            color = DEP_TYPE_COLORS["circular"]
            item.setForeground(0, QColor("#F44747"))
        else:
            color = DEP_TYPE_COLORS.get(dep.node_type, QColor("#D4D4D4"))

        item.setForeground(1, color)

        if dep.version:
            item.setToolTip(1, f"v{dep.version}")

        count = 1
        for child in dep.children:
            count += self._add_dep_node_to_tree(child, item)

        return count

    # --- Hashing and persistence ---

    def _on_save_tree(self) -> None:
        """Save the current forward dependency tree with a user-provided name."""
        if not self._forward_tree:
            QMessageBox.information(
                self,
                "No Dependencies",
                "No dependencies to save.",
            )
            return

        if not self._dep_store:
            QMessageBox.warning(
                self,
                "No Store",
                "Dependency store is not configured.",
            )
            return

        tree_hash = DependencyScanner.compute_tree_hash(self._forward_tree)

        # Check if this exact tree already exists
        existing = self._dep_store.get_tree_by_hash(tree_hash)
        default_name = ""
        if existing:
            default_name = existing["name"]

        name, ok = QInputDialog.getText(
            self,
            "Save Dependency Tree",
            "Enter a name for this dependency tree:",
            text=default_name,
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        tree_json = json.dumps(
            [dep.to_dict() for dep in self._forward_tree],
            sort_keys=True,
        )

        graph_name = None
        if self._current_graph:
            metadata = self._current_graph.metadata
            graph_name = getattr(metadata, "name", None)

        self._dep_store.save_tree(
            name=name,
            tree_hash=tree_hash,
            tree_json=tree_json,
            graph_file_path=self._current_file_path,
            graph_name=graph_name,
        )

        self.tree_saved.emit(name, tree_hash)

        # If currently viewing saved trees, refresh
        if self._view_combo.currentData() == self.VIEW_SAVED:
            self._populate_saved_trees()

    # --- Event handlers ---

    def _on_view_changed(self, _index: int) -> None:
        """Handle view mode change."""
        self._update_display()

    def _on_item_clicked(
        self, item: QTreeWidgetItem, _column: int
    ) -> None:
        """Handle single-click to navigate to a dependency workflow."""
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if file_path and Path(file_path).exists():
            self.dependency_selected.emit(file_path)

    def _on_item_double_clicked(
        self, item: QTreeWidgetItem, _column: int
    ) -> None:
        """Handle double-click to navigate to a dependency."""
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if file_path and Path(file_path).exists():
            self.dependency_selected.emit(file_path)

    def _on_context_menu(self, position: Any) -> None:
        """Show context menu for tree items."""
        item = self._tree.itemAt(position)
        if not item:
            return

        menu = QMenu(self)
        view = self._view_combo.currentData()

        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if file_path and Path(file_path).exists():
            open_action = menu.addAction("Open in New Tab")
            open_action.triggered.connect(
                lambda: self.dependency_selected.emit(file_path)
            )

        if view == self.VIEW_SAVED:
            tree_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if tree_name and self._dep_store:
                menu.addSeparator()
                rename_action = menu.addAction("Rename Tree")
                rename_action.triggered.connect(
                    lambda: self._rename_saved_tree(tree_name)
                )
                delete_action = menu.addAction("Delete Tree")
                delete_action.triggered.connect(
                    lambda: self._delete_saved_tree(tree_name)
                )

        if menu.actions():
            menu.exec(self._tree.viewport().mapToGlobal(position))

    def _rename_saved_tree(self, old_name: str) -> None:
        """Rename a saved dependency tree."""
        if not self._dep_store:
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Dependency Tree",
            "Enter a new name:",
            text=old_name,
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return

        if self._dep_store.rename_tree(old_name, new_name.strip()):
            self._populate_saved_trees()

    def _delete_saved_tree(self, name: str) -> None:
        """Delete a saved dependency tree."""
        if not self._dep_store:
            return

        reply = QMessageBox.question(
            self,
            "Delete Dependency Tree",
            f"Delete saved tree '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._dep_store.delete_tree(name):
                self._populate_saved_trees()
