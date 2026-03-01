"""
Main application window for VisualPython.

This module provides the primary user interface container including
the menu bar, toolbar, and central widget area for the node graph editor.
"""

from __future__ import annotations

from typing import Callable, List, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QToolBar,
    QStatusBar,
    QMenuBar,
    QMenu,
    QMessageBox,
    QFileDialog,
    QDockWidget,
    QFrame,
    QLabel,
    QSizePolicy,
)

from visualpython.ui.widgets.execution_state_indicator import ExecutionStateIndicator
from visualpython.ui.widgets.minimap import MinimapWidget
from visualpython.ui.widgets.unsaved_changes_banner import UnsavedChangesBanner
from visualpython.ui.widgets.workflow_tab_widget import WorkflowTabWidget
from visualpython.execution.state_manager import ExecutionState
from visualpython.core.keybindings_manager import KeybindingsManager

if TYPE_CHECKING:
    from PyQt6.QtGui import QCloseEvent
    from visualpython.ui.panels.workflow_library_panel import WorkflowLibraryPanel
    from visualpython.graph.graph import Graph
    from visualpython.graph.view import NodeGraphView


class MainWindow(QMainWindow):
    """
    Main application window for VisualPython.

    Provides the primary user interface container with menu bar, toolbar,
    and central widget area for the node graph editor.

    Signals:
        new_project_requested: Emitted when File > New is triggered.
        open_project_requested: Emitted when File > Open is triggered.
        save_project_requested: Emitted when File > Save is triggered.
        save_as_requested: Emitted when File > Save As is triggered.
        undo_requested: Emitted when Edit > Undo is triggered.
        redo_requested: Emitted when Edit > Redo is triggered.
        run_requested: Emitted when Run > Run is triggered.
        stop_requested: Emitted when Run > Stop is triggered.

    Attributes:
        WINDOW_TITLE: Default window title.
        DEFAULT_WIDTH: Default window width in pixels.
        DEFAULT_HEIGHT: Default window height in pixels.
    """

    WINDOW_TITLE = "VisualPython"
    DEFAULT_WIDTH = 1200
    DEFAULT_HEIGHT = 800

    # Signals for external handlers
    new_project_requested = pyqtSignal()
    open_project_requested = pyqtSignal(str)
    save_project_requested = pyqtSignal()
    save_as_requested = pyqtSignal(str)
    export_python_requested = pyqtSignal(str)
    save_variables_requested = pyqtSignal(str)
    load_variables_requested = pyqtSignal(str)
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    run_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    step_requested = pyqtSignal()  # Step to next node in step-through mode
    continue_requested = pyqtSignal()  # Continue execution (exit step mode)
    step_mode_toggled = pyqtSignal(bool)  # Step mode enabled/disabled
    auto_layout_requested = pyqtSignal(str)  # algorithm name
    export_library_requested = pyqtSignal(str)  # file path
    import_library_requested = pyqtSignal(str)  # file path
    import_python_script_requested = pyqtSignal(str)  # file path
    snap_to_grid_toggled = pyqtSignal(bool)  # enabled state
    group_selected_requested = pyqtSignal()  # Group selected nodes
    ungroup_selected_requested = pyqtSignal()  # Ungroup selected group
    find_requested = pyqtSignal()  # Search for nodes
    view_mode_changed = pyqtSignal(str)  # View mode (edit, run, collapsed, expanded)
    save_to_workflow_library_requested = pyqtSignal()  # Save current workflow to library
    create_subworkflow_requested = pyqtSignal()  # Create subworkflow from selection
    navigate_to_node_requested = pyqtSignal(str)  # Navigate to node by ID (pan/zoom and select)

    # Tab-related signals
    tab_changed = pyqtSignal(str)  # Emitted when active tab changes (tab_id)
    workflow_tab_created = pyqtSignal(str)  # Emitted when new workflow tab is created (tab_id)
    workflow_tab_closed = pyqtSignal(str)  # Emitted when workflow tab is closed (tab_id)
    subworkflow_tab_opened = pyqtSignal(str, str)  # Emitted when subworkflow opened (tab_id, parent_tab_id)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the main application window.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._current_file: Optional[str] = None
        self._is_modified: bool = False

        # Keybindings manager (loads from persistent config)
        self._keybindings_manager = KeybindingsManager()

        self._setup_window()
        self._setup_central_widget()
        self._setup_node_palette()
        self._setup_node_properties_panel()
        self._setup_variable_panel()
        self._setup_variable_inspector()
        self._setup_output_console()
        self._setup_minimap()
        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_status_bar()

        # Apply user keybindings to all actions
        self._apply_keybindings()

        self._update_window_title()

    def _setup_window(self) -> None:
        """Configure basic window properties."""
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setMinimumSize(800, 600)

    def _setup_central_widget(self) -> None:
        """Set up the central widget area with workflow tabs for the node graph editor."""
        self._central_widget = QWidget(self)
        self._central_layout = QVBoxLayout(self._central_widget)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        self._central_layout.setSpacing(0)
        self.setCentralWidget(self._central_widget)

        # Unsaved changes notification banner (hidden by default)
        self._unsaved_changes_banner = UnsavedChangesBanner(self._central_widget)
        self._unsaved_changes_banner.save_clicked.connect(self._on_save)
        self._central_layout.addWidget(self._unsaved_changes_banner)

        # Create workflow tab widget for managing multiple workflows
        self._workflow_tab_widget = WorkflowTabWidget(self._central_widget)
        self._central_layout.addWidget(self._workflow_tab_widget)

        # Connect tab widget signals
        self._connect_workflow_tab_signals()

    def _connect_workflow_tab_signals(self) -> None:
        """Connect workflow tab widget signals to main window signals."""
        # Forward tab change signal
        self._workflow_tab_widget.tab_changed.connect(self._on_workflow_tab_changed)

        # Forward workflow lifecycle signals
        self._workflow_tab_widget.workflow_created.connect(self.workflow_tab_created.emit)
        self._workflow_tab_widget.workflow_closed.connect(self._on_workflow_tab_closed)
        self._workflow_tab_widget.subworkflow_opened.connect(self.subworkflow_tab_opened.emit)

        # Connect signals that affect status bar display
        self._workflow_tab_widget.workflow_modified.connect(self._on_workflow_modified)
        self._workflow_tab_widget.view_mode_changed.connect(self._on_view_mode_changed_internal)

    def _on_workflow_tab_closed(self, tab_id: str) -> None:
        """
        Handle workflow tab closed event.

        Updates the status bar context and forwards the signal.

        Args:
            tab_id: The ID of the closed tab.
        """
        # Check if there are any remaining tabs
        remaining_tabs = self._workflow_tab_widget.get_all_tabs()
        if not remaining_tabs:
            # No tabs left, hide the context widget
            self._tab_context_widget.setVisible(False)
            self._status_bar.showMessage("No workflows open")
        else:
            # Update context for the now-current tab
            current_tab = self._workflow_tab_widget.get_current_tab()
            if current_tab:
                self._update_status_bar_tab_context(current_tab)

        # Forward the signal
        self.workflow_tab_closed.emit(tab_id)

    def _on_workflow_modified(self, tab_id: str) -> None:
        """
        Handle workflow modified event.

        Updates the status bar modified indicator if this is the current tab.

        Args:
            tab_id: The ID of the modified tab.
        """
        # Only update if this is the current tab
        current_tab_id = self._workflow_tab_widget.get_current_tab_id()
        if tab_id == current_tab_id:
            tab = self._workflow_tab_widget.get_tab(tab_id)
            if tab:
                self._update_status_bar_tab_context(tab)

    def _on_view_mode_changed_internal(self, tab_id: str, view_mode) -> None:
        """
        Handle view mode change event.

        Updates the status bar view mode indicator if this is the current tab.

        Args:
            tab_id: The ID of the tab with changed view mode.
            view_mode: The new view mode.
        """
        # Only update if this is the current tab
        current_tab_id = self._workflow_tab_widget.get_current_tab_id()
        if tab_id == current_tab_id:
            tab = self._workflow_tab_widget.get_tab(tab_id)
            if tab:
                self._update_status_bar_tab_context(tab)

    def _on_workflow_tab_changed(self, tab_id: str) -> None:
        """
        Handle workflow tab change.

        Updates the status bar context widget and emits the tab_changed signal.

        Args:
            tab_id: The ID of the newly active tab.
        """
        tab = self._workflow_tab_widget.get_tab(tab_id)
        if tab:
            # Update the permanent tab context widget in status bar
            self._update_status_bar_tab_context(tab)

            # Show a temporary message about the tab switch
            context = "Subworkflow" if tab.is_subworkflow else "Workflow"
            self._status_bar.showMessage(f"Switched to {context}: {tab.name}", 2000)

            # Update minimap if it exists and we have a graph view
            if hasattr(self, '_minimap') and tab.graph_view:
                self._minimap.set_graph_view(tab.graph_view)

        self.tab_changed.emit(tab_id)

    def _setup_node_palette(self) -> None:
        """Set up the node palette dock widget."""
        from visualpython.ui.panels.node_palette import NodePaletteWidget

        # Create the node palette widget
        self._node_palette = NodePaletteWidget()

        # Create a dock widget to contain the palette
        self._palette_dock = QDockWidget("Node Palette", self)
        self._palette_dock.setObjectName("NodePaletteDock")
        self._palette_dock.setWidget(self._node_palette)
        self._palette_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._palette_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Add to the left side of the window
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._palette_dock)

    def _setup_node_properties_panel(self) -> None:
        """Set up the node properties panel dock widget."""
        from visualpython.ui.panels.node_properties_panel import NodePropertiesPanel

        # Create the node properties panel widget
        self._node_properties_panel = NodePropertiesPanel()

        # Create a dock widget to contain the properties panel
        self._properties_dock = QDockWidget("Properties", self)
        self._properties_dock.setObjectName("NodePropertiesDock")
        self._properties_dock.setWidget(self._node_properties_panel)
        self._properties_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._properties_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Add to the right side of the window
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._properties_dock)

    def _setup_variable_panel(self) -> None:
        """Set up the variable panel dock widget (with Dependencies tab)."""
        from visualpython.ui.panels.variable_panel import VariableAndDependencyContainer

        # Create the container with both Variables and Dependencies tabs
        self._variable_container = VariableAndDependencyContainer()
        # Keep a direct reference for backward compatibility
        self._variable_panel = self._variable_container.variable_panel

        # Create a dock widget to contain the variable panel
        self._variable_dock = QDockWidget("Variables", self)
        self._variable_dock.setObjectName("VariablePanelDock")
        self._variable_dock.setWidget(self._variable_container)
        self._variable_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self._variable_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Add to the right side of the window, tabbed with properties
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._variable_dock)
        # Tab the variable panel with the properties panel
        self.tabifyDockWidget(self._properties_dock, self._variable_dock)
        # Keep properties panel in front by default
        self._properties_dock.raise_()

    def _setup_output_console(self) -> None:
        """Set up the output console dock widget."""
        from visualpython.ui.panels.output_console import OutputConsoleWidget

        # Create the output console widget
        self._output_console = OutputConsoleWidget()

        # Create a dock widget to contain the console
        self._console_dock = QDockWidget("Output Console", self)
        self._console_dock.setObjectName("OutputConsoleDock")
        self._console_dock.setWidget(self._output_console)
        self._console_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._console_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Add to the bottom of the window
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._console_dock)

        # Set up the execution summary panel as a tabbed panel with the console
        self._setup_execution_summary_panel()

        # Set up the log viewer panel as a tabbed panel
        self._setup_log_viewer_panel()

    def _setup_execution_summary_panel(self) -> None:
        """Set up the execution summary panel dock widget as tabbed with Output Console."""
        from visualpython.ui.panels.execution_summary_panel import ExecutionSummaryPanel

        # Create the execution summary panel widget
        self._execution_summary_panel = ExecutionSummaryPanel()

        # Create a dock widget to contain the summary panel
        self._summary_dock = QDockWidget("Execution Summary", self)
        self._summary_dock.setObjectName("ExecutionSummaryDock")
        self._summary_dock.setWidget(self._execution_summary_panel)
        self._summary_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._summary_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Add to the bottom of the window
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._summary_dock)

        # Tab the execution summary panel with the output console
        self.tabifyDockWidget(self._console_dock, self._summary_dock)

        # Keep the output console in front by default
        self._console_dock.raise_()

        # Connect summary panel signals for navigation
        # Both single-click (error_clicked) and double-click (node_navigate_requested)
        # should navigate to the node
        self._execution_summary_panel.error_clicked.connect(
            self._on_error_clicked
        )
        self._execution_summary_panel.node_navigate_requested.connect(
            self.navigate_to_node_requested.emit
        )

    def _on_error_clicked(self, node_id: str, error_index: int) -> None:
        """
        Handle error click from the execution summary panel.

        Navigates to the node when an error is clicked.

        Args:
            node_id: The ID of the node with the error.
            error_index: The index of the error (not used for navigation).
        """
        self.navigate_to_node_requested.emit(node_id)

    def _setup_log_viewer_panel(self) -> None:
        """Set up the log viewer panel dock widget as tabbed with Output Console."""
        from visualpython.ui.panels.log_viewer_panel import LogViewerPanel

        # Create the log viewer panel widget
        self._log_viewer_panel = LogViewerPanel()

        # Create a dock widget to contain the log viewer
        self._logs_dock = QDockWidget("Logs", self)
        self._logs_dock.setObjectName("LogViewerDock")
        self._logs_dock.setWidget(self._log_viewer_panel)
        self._logs_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._logs_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Add to the bottom of the window
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._logs_dock)

        # Tab the log viewer with the execution summary panel
        self.tabifyDockWidget(self._summary_dock, self._logs_dock)

        # Keep the output console in front by default
        self._console_dock.raise_()

    def get_log_handler(self) -> "logging.Handler":
        """Get the Qt logging handler for installation on a logger."""
        return self._log_viewer_panel.get_handler()

    def _setup_variable_inspector(self) -> None:
        """Set up the variable inspector dock widget."""
        from visualpython.ui.panels.variable_inspector import VariableInspectorWidget

        # Create the variable inspector widget
        self._variable_inspector = VariableInspectorWidget()

        # Create a dock widget to contain the variable inspector
        self._inspector_dock = QDockWidget("Variable Inspector", self)
        self._inspector_dock.setObjectName("VariableInspectorDock")
        self._inspector_dock.setWidget(self._variable_inspector)
        self._inspector_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self._inspector_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Add to the right side of the window, tabbed with other panels
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._inspector_dock)
        # Tab the inspector with the variable panel
        self.tabifyDockWidget(self._variable_dock, self._inspector_dock)
        # Keep variable panel in front by default
        self._variable_dock.raise_()

    def _setup_minimap(self) -> None:
        """Set up the minimap dock widget."""
        # Create the minimap widget
        self._minimap = MinimapWidget()

        # Create a dock widget to contain the minimap
        self._minimap_dock = QDockWidget("Minimap", self)
        self._minimap_dock.setObjectName("MinimapDock")
        self._minimap_dock.setWidget(self._minimap)
        self._minimap_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self._minimap_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Add to the right side of the window, below other panels
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._minimap_dock)

        # Also set up the workflow library panel
        self._setup_workflow_library()

    def _setup_workflow_library(self) -> None:
        """Set up the workflow library dock widget."""
        from visualpython.ui.panels.workflow_library_panel import WorkflowLibraryPanel

        # Create the workflow library widget
        self._workflow_library = WorkflowLibraryPanel()

        # Create a dock widget to contain the library
        self._library_dock = QDockWidget("Workflow Library", self)
        self._library_dock.setObjectName("WorkflowLibraryDock")
        self._library_dock.setWidget(self._workflow_library)
        self._library_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._library_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # Add to the left side of the window, tabbed with node palette
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._library_dock)
        self.tabifyDockWidget(self._palette_dock, self._library_dock)
        # Keep node palette in front by default
        self._palette_dock.raise_()

    @property
    def workflow_library(self) -> "WorkflowLibraryPanel":
        """Get the workflow library panel."""
        return self._workflow_library

    def _setup_menu_bar(self) -> None:
        """Set up the menu bar with standard menus."""
        menu_bar = self.menuBar()

        # File menu
        self._file_menu = menu_bar.addMenu("&File")
        self._setup_file_menu()

        # Edit menu
        self._edit_menu = menu_bar.addMenu("&Edit")
        self._setup_edit_menu()

        # View menu
        self._view_menu = menu_bar.addMenu("&View")
        self._setup_view_menu()

        # Run menu
        self._run_menu = menu_bar.addMenu("&Run")
        self._setup_run_menu()

        # Help menu
        self._help_menu = menu_bar.addMenu("&Help")
        self._setup_help_menu()

    def _setup_file_menu(self) -> None:
        """Set up the File menu actions."""
        # New
        self._new_action = QAction("&New", self)
        self._new_action.setShortcut(QKeySequence.StandardKey.New)
        self._new_action.setStatusTip("Create a new project")
        self._new_action.triggered.connect(self._on_new)
        self._file_menu.addAction(self._new_action)

        # Open
        self._open_action = QAction("&Open...", self)
        self._open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._open_action.setStatusTip("Open an existing project")
        self._open_action.triggered.connect(self._on_open)
        self._file_menu.addAction(self._open_action)

        self._file_menu.addSeparator()

        # Save
        self._save_action = QAction("&Save", self)
        self._save_action.setShortcut(QKeySequence.StandardKey.Save)
        self._save_action.setStatusTip("Save the current project")
        self._save_action.triggered.connect(self._on_save)
        self._file_menu.addAction(self._save_action)

        # Save As
        self._save_as_action = QAction("Save &As...", self)
        self._save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._save_as_action.setStatusTip("Save the project with a new name")
        self._save_as_action.triggered.connect(self._on_save_as)
        self._file_menu.addAction(self._save_as_action)

        self._file_menu.addSeparator()

        # Export as Python
        self._export_python_action = QAction("&Export as Python...", self)
        self._export_python_action.setShortcut("Ctrl+Shift+E")
        self._export_python_action.setStatusTip("Export the graph as a standalone Python script")
        self._export_python_action.triggered.connect(self._on_export_python)
        self._file_menu.addAction(self._export_python_action)

        self._file_menu.addSeparator()

        # Save Variables
        self._save_variables_action = QAction("Save &Variables...", self)
        self._save_variables_action.setShortcut("Ctrl+Shift+V")
        self._save_variables_action.setStatusTip("Save global variables to a JSON file")
        self._save_variables_action.triggered.connect(self._on_save_variables)
        self._file_menu.addAction(self._save_variables_action)

        # Load Variables
        self._load_variables_action = QAction("&Load Variables...", self)
        self._load_variables_action.setShortcut("Ctrl+Shift+L")
        self._load_variables_action.setStatusTip("Load global variables from a JSON file")
        self._load_variables_action.triggered.connect(self._on_load_variables)
        self._file_menu.addAction(self._load_variables_action)

        self._file_menu.addSeparator()

        # Export as Library
        self._export_library_action = QAction("Export as &Library...", self)
        self._export_library_action.setShortcut("Ctrl+Shift+X")
        self._export_library_action.setStatusTip("Export selected nodes as a reusable library")
        self._export_library_action.triggered.connect(self._on_export_library)
        self._file_menu.addAction(self._export_library_action)

        # Import Library
        self._import_library_action = QAction("&Import Library...", self)
        self._import_library_action.setShortcut("Ctrl+Shift+I")
        self._import_library_action.setStatusTip("Import a node library into the current project")
        self._import_library_action.triggered.connect(self._on_import_library)
        self._file_menu.addAction(self._import_library_action)

        # Import Python Script as Code Node
        self._import_python_script_action = QAction("Import &Python Script as Code Node...", self)
        self._import_python_script_action.setShortcut("Ctrl+Shift+P")
        self._import_python_script_action.setStatusTip(
            "Import an existing Python script as a code node"
        )
        self._import_python_script_action.triggered.connect(self._on_import_python_script)
        self._file_menu.addAction(self._import_python_script_action)

        self._file_menu.addSeparator()

        # Exit
        self._exit_action = QAction("E&xit", self)
        self._exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self._exit_action.setStatusTip("Exit the application")
        self._exit_action.triggered.connect(self.close)
        self._file_menu.addAction(self._exit_action)

    def _setup_edit_menu(self) -> None:
        """Set up the Edit menu actions."""
        # Undo
        self._undo_action = QAction("&Undo", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.setStatusTip("Undo the last action")
        self._undo_action.triggered.connect(self._on_undo)
        self._edit_menu.addAction(self._undo_action)

        # Redo
        self._redo_action = QAction("&Redo", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.setStatusTip("Redo the last undone action")
        self._redo_action.triggered.connect(self._on_redo)
        self._edit_menu.addAction(self._redo_action)

        self._edit_menu.addSeparator()

        # Cut
        self._cut_action = QAction("Cu&t", self)
        self._cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        self._cut_action.setStatusTip("Cut the selected items")
        self._edit_menu.addAction(self._cut_action)

        # Copy
        self._copy_action = QAction("&Copy", self)
        self._copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self._copy_action.setStatusTip("Copy the selected items")
        self._edit_menu.addAction(self._copy_action)

        # Paste
        self._paste_action = QAction("&Paste", self)
        self._paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        self._paste_action.setStatusTip("Paste items from clipboard")
        self._edit_menu.addAction(self._paste_action)

        # Duplicate
        self._duplicate_action = QAction("D&uplicate", self)
        self._duplicate_action.setShortcut("Ctrl+D")
        self._duplicate_action.setStatusTip("Duplicate selected nodes")
        self._edit_menu.addAction(self._duplicate_action)

        self._edit_menu.addSeparator()

        # Delete
        self._delete_action = QAction("&Delete", self)
        self._delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self._delete_action.setStatusTip("Delete the selected items")
        self._edit_menu.addAction(self._delete_action)

        # Select All
        self._select_all_action = QAction("Select &All", self)
        self._select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        self._select_all_action.setStatusTip("Select all items")
        self._edit_menu.addAction(self._select_all_action)

        self._edit_menu.addSeparator()

        # Find (search nodes)
        self._find_action = QAction("&Find...", self)
        self._find_action.setShortcut(QKeySequence.StandardKey.Find)
        self._find_action.setStatusTip("Search for nodes by name or content")
        self._edit_menu.addAction(self._find_action)

        self._edit_menu.addSeparator()

        # Group selected nodes
        self._group_action = QAction("&Group Selected", self)
        self._group_action.setShortcut("Ctrl+Alt+G")
        self._group_action.setStatusTip("Group selected nodes into a collapsible container")
        self._group_action.triggered.connect(self._on_group_selected)
        self._edit_menu.addAction(self._group_action)

        # Ungroup
        self._ungroup_action = QAction("&Ungroup", self)
        self._ungroup_action.setShortcut("Ctrl+Shift+G")
        self._ungroup_action.setStatusTip("Remove selected group (keeps nodes)")
        self._ungroup_action.triggered.connect(self._on_ungroup_selected)
        self._edit_menu.addAction(self._ungroup_action)

        self._edit_menu.addSeparator()

        # Create Subworkflow from selection
        self._create_subworkflow_action = QAction("Create &Subworkflow from Selection", self)
        self._create_subworkflow_action.setShortcut("Ctrl+Shift+S")
        self._create_subworkflow_action.setStatusTip(
            "Convert selected nodes into a reusable subworkflow"
        )
        self._create_subworkflow_action.triggered.connect(self._on_create_subworkflow)
        self._edit_menu.addAction(self._create_subworkflow_action)

        # Save to Workflow Library
        self._save_to_library_action = QAction("Save to &Workflow Library...", self)
        self._save_to_library_action.setShortcut("Ctrl+Alt+S")
        self._save_to_library_action.setStatusTip(
            "Save the current workflow to the library for reuse"
        )
        self._save_to_library_action.triggered.connect(self._on_save_to_workflow_library)
        self._edit_menu.addAction(self._save_to_library_action)

        self._edit_menu.addSeparator()

        # Keyboard Shortcuts
        self._keybindings_action = QAction("&Keyboard Shortcuts...", self)
        self._keybindings_action.setStatusTip("Customize keyboard shortcuts")
        self._keybindings_action.triggered.connect(self._on_edit_keybindings)
        self._edit_menu.addAction(self._keybindings_action)

    def _setup_view_menu(self) -> None:
        """Set up the View menu actions."""
        # Zoom In
        self._zoom_in_action = QAction("Zoom &In", self)
        self._zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self._zoom_in_action.setStatusTip("Zoom in on the canvas")
        self._view_menu.addAction(self._zoom_in_action)

        # Zoom Out
        self._zoom_out_action = QAction("Zoom &Out", self)
        self._zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self._zoom_out_action.setStatusTip("Zoom out on the canvas")
        self._view_menu.addAction(self._zoom_out_action)

        # Reset Zoom
        self._reset_zoom_action = QAction("&Reset Zoom", self)
        self._reset_zoom_action.setShortcut("Ctrl+0")
        self._reset_zoom_action.setStatusTip("Reset zoom to 100%")
        self._view_menu.addAction(self._reset_zoom_action)

        self._view_menu.addSeparator()

        # Fit to Window
        self._fit_action = QAction("&Fit to Window", self)
        self._fit_action.setShortcut("Ctrl+Shift+F")
        self._fit_action.setStatusTip("Fit the graph to the window")
        self._view_menu.addAction(self._fit_action)

        self._view_menu.addSeparator()

        # Snap to Grid
        self._snap_to_grid_action = QAction("S&nap to Grid", self)
        self._snap_to_grid_action.setCheckable(True)
        self._snap_to_grid_action.setChecked(False)
        self._snap_to_grid_action.setShortcut("Ctrl+G")
        self._snap_to_grid_action.setStatusTip("Snap nodes to the grid when moving or placing")
        self._snap_to_grid_action.triggered.connect(self._on_snap_to_grid_toggled)
        self._view_menu.addAction(self._snap_to_grid_action)

        self._view_menu.addSeparator()

        # Toggle Node Palette
        self._toggle_node_palette_action = self._palette_dock.toggleViewAction()
        self._toggle_node_palette_action.setText("Show &Node Palette")
        self._toggle_node_palette_action.setStatusTip("Toggle node palette visibility")
        self._view_menu.addAction(self._toggle_node_palette_action)

        # Toggle Properties Panel
        self._toggle_properties_action = self._properties_dock.toggleViewAction()
        self._toggle_properties_action.setText("Show &Properties Panel")
        self._toggle_properties_action.setStatusTip("Toggle node properties panel visibility")
        self._view_menu.addAction(self._toggle_properties_action)

        # Toggle Output Console
        self._toggle_console_action = self._console_dock.toggleViewAction()
        self._toggle_console_action.setText("Show &Output Console")
        self._toggle_console_action.setStatusTip("Toggle output console visibility")
        self._view_menu.addAction(self._toggle_console_action)

        # Toggle Execution Summary Panel
        self._toggle_summary_action = self._summary_dock.toggleViewAction()
        self._toggle_summary_action.setText("Show &Execution Summary")
        self._toggle_summary_action.setStatusTip("Toggle execution summary panel visibility")
        self._view_menu.addAction(self._toggle_summary_action)

        # Toggle Logs Panel
        self._toggle_logs_action = self._logs_dock.toggleViewAction()
        self._toggle_logs_action.setText("Show &Logs")
        self._toggle_logs_action.setStatusTip("Toggle log viewer panel visibility")
        self._view_menu.addAction(self._toggle_logs_action)

        # Toggle Variable Panel
        self._toggle_variable_panel_action = self._variable_dock.toggleViewAction()
        self._toggle_variable_panel_action.setText("Show &Variables Panel")
        self._toggle_variable_panel_action.setStatusTip("Toggle variable panel visibility")
        self._view_menu.addAction(self._toggle_variable_panel_action)

        # Toggle Variable Inspector
        self._toggle_inspector_action = self._inspector_dock.toggleViewAction()
        self._toggle_inspector_action.setText("Show Variable &Inspector")
        self._toggle_inspector_action.setStatusTip("Toggle variable inspector panel visibility")
        self._view_menu.addAction(self._toggle_inspector_action)

        # Toggle Minimap
        self._toggle_minimap_action = self._minimap_dock.toggleViewAction()
        self._toggle_minimap_action.setText("Show &Minimap")
        self._toggle_minimap_action.setStatusTip("Toggle minimap visibility")
        self._view_menu.addAction(self._toggle_minimap_action)

        # Toggle Workflow Library
        self._toggle_library_action = self._library_dock.toggleViewAction()
        self._toggle_library_action.setText("Show Workflow &Library")
        self._toggle_library_action.setStatusTip("Toggle workflow library panel visibility")
        self._view_menu.addAction(self._toggle_library_action)

        self._view_menu.addSeparator()

        # View Mode submenu
        self._view_mode_menu = self._view_menu.addMenu("View &Mode")
        self._setup_view_mode_menu()

        self._view_menu.addSeparator()

        # Toggle Toolbar
        self._toggle_toolbar_action = QAction("Show &Toolbar", self)
        self._toggle_toolbar_action.setCheckable(True)
        self._toggle_toolbar_action.setChecked(True)
        self._toggle_toolbar_action.setStatusTip("Toggle toolbar visibility")
        self._toggle_toolbar_action.triggered.connect(self._on_toggle_toolbar)
        self._view_menu.addAction(self._toggle_toolbar_action)

        # Toggle Status Bar
        self._toggle_status_bar_action = QAction("Show &Status Bar", self)
        self._toggle_status_bar_action.setCheckable(True)
        self._toggle_status_bar_action.setChecked(True)
        self._toggle_status_bar_action.setStatusTip("Toggle status bar visibility")
        self._toggle_status_bar_action.triggered.connect(self._on_toggle_status_bar)
        self._view_menu.addAction(self._toggle_status_bar_action)

        self._view_menu.addSeparator()

        # Auto Layout submenu
        self._layout_menu = self._view_menu.addMenu("Auto &Layout")
        self._setup_layout_menu()

    def _setup_layout_menu(self) -> None:
        """Set up the Auto Layout submenu actions."""
        # Hierarchical Layout
        self._hierarchical_layout_action = QAction("&Hierarchical Layout", self)
        self._hierarchical_layout_action.setShortcut("Ctrl+L")
        self._hierarchical_layout_action.setStatusTip(
            "Arrange nodes in layers based on data flow direction"
        )
        self._hierarchical_layout_action.triggered.connect(
            lambda: self._on_auto_layout("hierarchical")
        )
        self._layout_menu.addAction(self._hierarchical_layout_action)

        # Force-Directed Layout
        self._force_directed_layout_action = QAction("&Force-Directed Layout", self)
        self._force_directed_layout_action.setShortcut("Ctrl+Shift+L")
        self._force_directed_layout_action.setStatusTip(
            "Arrange nodes using physics-based simulation"
        )
        self._force_directed_layout_action.triggered.connect(
            lambda: self._on_auto_layout("force-directed")
        )
        self._layout_menu.addAction(self._force_directed_layout_action)

    def _setup_view_mode_menu(self) -> None:
        """Set up the View Mode submenu actions."""
        from PyQt6.QtGui import QActionGroup

        # Create action group for mutual exclusivity
        self._view_mode_group = QActionGroup(self)

        # Edit Mode
        self._edit_mode_action = QAction("&Edit Mode", self)
        self._edit_mode_action.setCheckable(True)
        self._edit_mode_action.setChecked(True)
        self._edit_mode_action.setShortcut("Ctrl+1")
        self._edit_mode_action.setStatusTip("Standard editing mode with full node details")
        self._edit_mode_action.triggered.connect(lambda: self._on_view_mode_changed("edit"))
        self._view_mode_group.addAction(self._edit_mode_action)
        self._view_mode_menu.addAction(self._edit_mode_action)

        # Run/Debug Mode
        self._run_mode_action = QAction("&Run/Debug Mode", self)
        self._run_mode_action.setCheckable(True)
        self._run_mode_action.setShortcut("Ctrl+2")
        self._run_mode_action.setStatusTip("View mode optimized for watching execution progress")
        self._run_mode_action.triggered.connect(lambda: self._on_view_mode_changed("run"))
        self._view_mode_group.addAction(self._run_mode_action)
        self._view_mode_menu.addAction(self._run_mode_action)

        # Collapsed View
        self._collapsed_view_action = QAction("&Collapsed View", self)
        self._collapsed_view_action.setCheckable(True)
        self._collapsed_view_action.setShortcut("Ctrl+3")
        self._collapsed_view_action.setStatusTip("Show high-level workflow structure with collapsed subgraphs")
        self._collapsed_view_action.triggered.connect(lambda: self._on_view_mode_changed("collapsed"))
        self._view_mode_group.addAction(self._collapsed_view_action)
        self._view_mode_menu.addAction(self._collapsed_view_action)

        # Expanded View
        self._expanded_view_action = QAction("E&xpanded View", self)
        self._expanded_view_action.setCheckable(True)
        self._expanded_view_action.setShortcut("Ctrl+4")
        self._expanded_view_action.setStatusTip("Show all nested workflows expanded")
        self._expanded_view_action.triggered.connect(lambda: self._on_view_mode_changed("expanded"))
        self._view_mode_group.addAction(self._expanded_view_action)
        self._view_mode_menu.addAction(self._expanded_view_action)

    def _on_view_mode_changed(self, mode: str) -> None:
        """
        Handle view mode change from menu.

        Args:
            mode: The view mode to apply ("edit", "run", "collapsed", "expanded").
        """
        self.view_mode_changed.emit(mode)

    def _on_auto_layout(self, algorithm: str) -> None:
        """
        Handle auto layout menu action.

        Args:
            algorithm: The layout algorithm to apply.
        """
        self.auto_layout_requested.emit(algorithm)

    def _setup_run_menu(self) -> None:
        """Set up the Run menu actions."""
        # Run
        self._run_action = QAction("&Run", self)
        self._run_action.setShortcut("F5")
        self._run_action.setStatusTip("Execute the current graph")
        self._run_action.triggered.connect(self._on_run)
        self._run_menu.addAction(self._run_action)

        # Stop
        self._stop_action = QAction("&Stop", self)
        self._stop_action.setShortcut("Shift+F5")
        self._stop_action.setStatusTip("Stop the current execution")
        self._stop_action.setEnabled(False)
        self._stop_action.triggered.connect(self._on_stop)
        self._run_menu.addAction(self._stop_action)

        self._run_menu.addSeparator()

        # Step Mode toggle
        self._step_mode_action = QAction("Step &Mode", self)
        self._step_mode_action.setShortcut("F10")
        self._step_mode_action.setCheckable(True)
        self._step_mode_action.setStatusTip("Enable step-through debugging (pause at each node)")
        self._step_mode_action.triggered.connect(self._on_step_mode_toggled)
        self._run_menu.addAction(self._step_mode_action)

        # Step (execute next node)
        self._step_action = QAction("Step &Next", self)
        self._step_action.setShortcut("F11")
        self._step_action.setStatusTip("Execute the next node in step-through mode")
        self._step_action.setEnabled(False)
        self._step_action.triggered.connect(self._on_step)
        self._run_menu.addAction(self._step_action)

        # Continue (exit step mode and run to completion)
        self._continue_action = QAction("&Continue", self)
        self._continue_action.setShortcut("F8")
        self._continue_action.setStatusTip("Continue execution without stepping")
        self._continue_action.setEnabled(False)
        self._continue_action.triggered.connect(self._on_continue)
        self._run_menu.addAction(self._continue_action)

        self._run_menu.addSeparator()

        # Run Selected
        self._run_selected_action = QAction("Run &Selected", self)
        self._run_selected_action.setShortcut("Ctrl+F5")
        self._run_selected_action.setStatusTip("Execute selected nodes only")
        self._run_menu.addAction(self._run_selected_action)

    def _setup_help_menu(self) -> None:
        """Set up the Help menu actions."""
        # Documentation
        self._docs_action = QAction("&Documentation", self)
        self._docs_action.setShortcut("F1")
        self._docs_action.setStatusTip("Open the documentation")
        self._help_menu.addAction(self._docs_action)

        self._help_menu.addSeparator()

        # About
        self._about_action = QAction("&About VisualPython", self)
        self._about_action.setStatusTip("About VisualPython")
        self._about_action.triggered.connect(self._on_about)
        self._help_menu.addAction(self._about_action)

    def _setup_toolbar(self) -> None:
        """Set up the main toolbar with common actions."""
        self._toolbar = QToolBar("Main Toolbar", self)
        self._toolbar.setObjectName("MainToolbar")
        self._toolbar.setMovable(False)
        self._toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)

        # Add actions to toolbar
        self._toolbar.addAction(self._new_action)
        self._toolbar.addAction(self._open_action)
        self._toolbar.addAction(self._save_action)

        self._toolbar.addSeparator()

        self._toolbar.addAction(self._undo_action)
        self._toolbar.addAction(self._redo_action)

        self._toolbar.addSeparator()

        self._toolbar.addAction(self._cut_action)
        self._toolbar.addAction(self._copy_action)
        self._toolbar.addAction(self._paste_action)

        self._toolbar.addSeparator()

        self._toolbar.addAction(self._run_action)
        self._toolbar.addAction(self._stop_action)
        self._toolbar.addAction(self._step_mode_action)
        self._toolbar.addAction(self._step_action)
        self._toolbar.addAction(self._continue_action)

    def _setup_status_bar(self) -> None:
        """Set up the status bar with tab context indicator and execution state indicator."""
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)

        # Create tab context indicator widget (shows current tab information)
        self._tab_context_widget = self._create_tab_context_widget()

        # Create execution state indicator
        self._execution_state_indicator = ExecutionStateIndicator()

        # Add separator between context and execution state
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.VLine)
        separator1.setFrameShadow(QFrame.Shadow.Sunken)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)

        # Add permanent widgets (right-aligned)
        # Order: Tab Context | Separator | Execution State
        self._status_bar.addPermanentWidget(self._tab_context_widget)
        self._status_bar.addPermanentWidget(separator1)
        self._status_bar.addPermanentWidget(self._execution_state_indicator)

        self._status_bar.showMessage("Ready")

    def _create_tab_context_widget(self) -> QWidget:
        """
        Create the tab context widget for the status bar.

        This widget displays:
        - Tab type icon (workflow/subworkflow)
        - Tab name or hierarchy breadcrumb
        - View mode
        - Modified indicator

        Returns:
            The configured context widget.
        """
        widget = QWidget()
        widget.setObjectName("tab_context_widget")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(8)

        # Tab type indicator (icon/label showing workflow or subworkflow)
        self._tab_type_label = QLabel()
        self._tab_type_label.setObjectName("tab_type_label")
        self._tab_type_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
            }
            QLabel[tabType="workflow"] {
                background-color: #4CAF50;
                color: white;
            }
            QLabel[tabType="subworkflow"] {
                background-color: #2196F3;
                color: white;
            }
            QLabel[tabType="deep_subworkflow"] {
                background-color: #9C27B0;
                color: white;
            }
        """)
        layout.addWidget(self._tab_type_label)

        # Separator between type and breadcrumb
        type_separator = QFrame()
        type_separator.setFrameShape(QFrame.Shape.VLine)
        type_separator.setFrameShadow(QFrame.Shadow.Sunken)
        type_separator.setFixedWidth(1)
        layout.addWidget(type_separator)

        # Tab breadcrumb/name label
        self._tab_breadcrumb_label = QLabel()
        self._tab_breadcrumb_label.setObjectName("tab_breadcrumb_label")
        self._tab_breadcrumb_label.setToolTip("Current workflow hierarchy")
        self._tab_breadcrumb_label.setStyleSheet("""
            QLabel {
                color: #E0E0E0;
                font-size: 11px;
            }
        """)
        layout.addWidget(self._tab_breadcrumb_label)

        # Modified indicator
        self._modified_indicator_label = QLabel()
        self._modified_indicator_label.setObjectName("modified_indicator_label")
        self._modified_indicator_label.setStyleSheet("""
            QLabel {
                color: #FFA726;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        layout.addWidget(self._modified_indicator_label)

        # View mode indicator (shown in brackets)
        self._view_mode_label = QLabel()
        self._view_mode_label.setObjectName("view_mode_label")
        self._view_mode_label.setStyleSheet("""
            QLabel {
                color: #90CAF9;
                font-size: 10px;
                font-style: italic;
            }
        """)
        layout.addWidget(self._view_mode_label)

        # Initially hide the widget until a tab is active
        widget.setVisible(False)

        return widget

    def _update_window_title(self) -> None:
        """Update the window title to reflect current file and modification state."""
        title = self.WINDOW_TITLE
        if self._current_file:
            title = f"{self._current_file} - {title}"
        else:
            title = f"Untitled - {title}"

        if self._is_modified:
            title = f"*{title}"

        self.setWindowTitle(title)

    # Signal handlers

    def _on_new(self) -> None:
        """Handle File > New action."""
        if self._check_save_changes():
            self._current_file = None
            self.is_modified = False
            self.new_project_requested.emit()
            self._status_bar.showMessage("New project created", 3000)

    def _on_open(self) -> None:
        """Handle File > Open action."""
        if not self._check_save_changes():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "VisualPython Projects (*.vpy);;JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            self._current_file = file_path
            self.is_modified = False
            self.open_project_requested.emit(file_path)
            self._status_bar.showMessage(f"Opened: {file_path}", 3000)

    def _on_save(self) -> None:
        """Handle File > Save action."""
        if self._current_file:
            self.is_modified = False
            self.save_project_requested.emit()
            self._status_bar.showMessage(f"Saved: {self._current_file}", 3000)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        """Handle File > Save As action."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            "",
            "VisualPython Projects (*.vpy);;JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            self._current_file = file_path
            self.is_modified = False
            self.save_as_requested.emit(file_path)
            self._status_bar.showMessage(f"Saved as: {file_path}", 3000)

    def _on_export_python(self) -> None:
        """Handle File > Export as Python action."""
        # Suggest a default filename based on current project file
        default_name = ""
        if self._current_file:
            from pathlib import Path
            default_name = Path(self._current_file).stem + ".py"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export as Python",
            default_name,
            "Python Files (*.py);;All Files (*)",
        )

        if file_path:
            self.export_python_requested.emit(file_path)

    def _on_save_variables(self) -> None:
        """Handle File > Save Variables action."""
        # Suggest a default filename based on current project file
        default_name = "variables.json"
        if self._current_file:
            from pathlib import Path
            default_name = Path(self._current_file).stem + "_variables.json"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Variables",
            default_name,
            "JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            self.save_variables_requested.emit(file_path)

    def _on_load_variables(self) -> None:
        """Handle File > Load Variables action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Variables",
            "",
            "JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            self.load_variables_requested.emit(file_path)

    def _on_export_library(self) -> None:
        """Handle File > Export as Library action."""
        # Just emit signal - dialog is shown by ApplicationController
        self.export_library_requested.emit("")

    def _on_import_library(self) -> None:
        """Handle File > Import Library action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Node Library",
            "",
            "VisualPython Libraries (*.vnl);;JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            self.import_library_requested.emit(file_path)

    def _on_import_python_script(self) -> None:
        """Handle File > Import Python Script as Code Node action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Python Script as Code Node",
            "",
            "Python Files (*.py);;All Files (*)",
        )

        if file_path:
            self.import_python_script_requested.emit(file_path)

    def _on_undo(self) -> None:
        """Handle Edit > Undo action."""
        self.undo_requested.emit()

    def _on_redo(self) -> None:
        """Handle Edit > Redo action."""
        self.redo_requested.emit()

    def _on_run(self) -> None:
        """Handle Run > Run action."""
        self._run_action.setEnabled(False)
        self._stop_action.setEnabled(True)
        self._status_bar.showMessage("Running...")
        self.run_requested.emit()

    def _on_stop(self) -> None:
        """Handle Run > Stop action."""
        self._run_action.setEnabled(True)
        self._stop_action.setEnabled(False)
        self._step_action.setEnabled(False)
        self._continue_action.setEnabled(False)
        self._status_bar.showMessage("Stopped", 3000)
        self.stop_requested.emit()

    def _on_step_mode_toggled(self, checked: bool) -> None:
        """Handle Run > Step Mode toggle."""
        self.step_mode_toggled.emit(checked)
        status = "enabled" if checked else "disabled"
        self._status_bar.showMessage(f"Step-through mode {status}", 3000)

    def _on_step(self) -> None:
        """Handle Run > Step Next action."""
        self._status_bar.showMessage("Stepping to next node...")
        self.step_requested.emit()

    def _on_continue(self) -> None:
        """Handle Run > Continue action."""
        self._step_action.setEnabled(False)
        self._continue_action.setEnabled(False)
        self._status_bar.showMessage("Continuing execution...")
        self.continue_requested.emit()

    def _on_toggle_toolbar(self, checked: bool) -> None:
        """Toggle toolbar visibility."""
        self._toolbar.setVisible(checked)

    def _on_toggle_status_bar(self, checked: bool) -> None:
        """Toggle status bar visibility."""
        self._status_bar.setVisible(checked)

    def _on_snap_to_grid_toggled(self, checked: bool) -> None:
        """Handle View > Snap to Grid toggle."""
        self.snap_to_grid_toggled.emit(checked)
        status = "enabled" if checked else "disabled"
        self._status_bar.showMessage(f"Snap to grid {status}", 3000)

    def _on_group_selected(self) -> None:
        """Handle Edit > Group Selected action."""
        self.group_selected_requested.emit()

    def _on_ungroup_selected(self) -> None:
        """Handle Edit > Ungroup action."""
        self.ungroup_selected_requested.emit()

    def _on_create_subworkflow(self) -> None:
        """Handle Edit > Create Subworkflow from Selection action."""
        self.create_subworkflow_requested.emit()

    def _on_save_to_workflow_library(self) -> None:
        """Handle Edit > Save to Workflow Library action."""
        self.save_to_workflow_library_requested.emit()

    def _on_about(self) -> None:
        """Show the About dialog."""
        from visualpython import __version__

        QMessageBox.about(
            self,
            "About VisualPython",
            f"<h3>VisualPython v{__version__}</h3>"
            "<p>A visual node-based scripting environment for Python.</p>"
            "<p>Create Python scripts through an intuitive node-based editor.</p>"
            "<p>&copy; 2024 VisualPython Team</p>",
        )

    def _on_edit_keybindings(self) -> None:
        """Open the keybindings editor dialog."""
        from visualpython.ui.dialogs.keybindings_dialog import KeybindingsDialog

        dialog = KeybindingsDialog(self._keybindings_manager, self)
        if dialog.exec() == KeybindingsDialog.DialogCode.Accepted:
            self._apply_keybindings()

    def _apply_keybindings(self) -> None:
        """Apply keybindings from the manager to all QAction shortcuts."""
        action_map = {
            "file.new": self._new_action,
            "file.open": self._open_action,
            "file.save": self._save_action,
            "file.save_as": self._save_as_action,
            "file.export_python": self._export_python_action,
            "file.exit": self._exit_action,
            "edit.undo": self._undo_action,
            "edit.redo": self._redo_action,
            "edit.cut": self._cut_action,
            "edit.copy": self._copy_action,
            "edit.paste": self._paste_action,
            "edit.duplicate": self._duplicate_action,
            "edit.delete": self._delete_action,
            "edit.select_all": self._select_all_action,
            "edit.find": self._find_action,
            "edit.group": self._group_action,
            "edit.ungroup": self._ungroup_action,
            "view.zoom_in": self._zoom_in_action,
            "view.zoom_out": self._zoom_out_action,
            "view.reset_zoom": self._reset_zoom_action,
            "view.fit_window": self._fit_action,
            "view.snap_grid": self._snap_to_grid_action,
            "run.run": self._run_action,
            "run.stop": self._stop_action,
            "run.step_mode": self._step_mode_action,
            "run.step_next": self._step_action,
            "run.continue": self._continue_action,
            "run.run_selected": self._run_selected_action,
        }

        for action_id, action in action_map.items():
            shortcut = self._keybindings_manager.get(action_id)
            action.setShortcut(shortcut)

    @property
    def keybindings_manager(self) -> KeybindingsManager:
        """Get the keybindings manager."""
        return self._keybindings_manager

    def _check_save_changes(self) -> bool:
        """
        Check if there are unsaved changes and prompt user to save.

        Returns:
            True if it's safe to proceed (saved or discarded), False if cancelled.
        """
        if not self._is_modified:
            return True

        result = QMessageBox.warning(
            self,
            "Unsaved Changes",
            "The project has unsaved changes. Do you want to save them?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

        if result == QMessageBox.StandardButton.Save:
            self._on_save()
            return True
        elif result == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    def closeEvent(self, event: "QCloseEvent") -> None:
        """
        Handle window close event.

        Args:
            event: The close event.
        """
        if self._check_save_changes():
            event.accept()
        else:
            event.ignore()

    # Public API

    @property
    def current_file(self) -> Optional[str]:
        """Get the current file path."""
        return self._current_file

    @current_file.setter
    def current_file(self, file_path: Optional[str]) -> None:
        """
        Set the current file path.

        Args:
            file_path: The file path or None.
        """
        self._current_file = file_path
        self._update_window_title()

    @property
    def is_modified(self) -> bool:
        """Check if the project has unsaved changes."""
        return self._is_modified

    @is_modified.setter
    def is_modified(self, modified: bool) -> None:
        """
        Set the modification state.

        Args:
            modified: Whether the project has unsaved changes.
        """
        self._is_modified = modified
        self._update_window_title()
        self._unsaved_changes_banner.setVisible(modified)

    @property
    def central_widget(self) -> QWidget:
        """Get the central widget container."""
        return self._central_widget

    @property
    def central_layout(self) -> QVBoxLayout:
        """Get the central widget layout for adding child widgets."""
        return self._central_layout

    @property
    def workflow_tab_widget(self) -> WorkflowTabWidget:
        """
        Get the workflow tab widget for managing multiple workflow tabs.

        Returns:
            The WorkflowTabWidget instance.
        """
        return self._workflow_tab_widget

    def set_graph_view_factory(
        self,
        create_view: Callable[[], "NodeGraphView"],
        create_graph: Callable[[], "Graph"],
    ) -> None:
        """
        Set factory functions for creating new graph views and graphs in tabs.

        This must be called before creating workflow tabs.

        Args:
            create_view: Function that creates a new NodeGraphView.
            create_graph: Function that creates a new Graph.
        """
        self._workflow_tab_widget.set_graph_view_factory(create_view, create_graph)

    def create_workflow_tab(
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
        return self._workflow_tab_widget.create_new_workflow(name, graph)

    def open_workflow_in_tab(self, file_path: str, graph: "Graph") -> str:
        """
        Open a workflow from a file in a new tab.

        Args:
            file_path: Path to the workflow file.
            graph: The loaded graph.

        Returns:
            The ID of the created tab.
        """
        return self._workflow_tab_widget.open_workflow(file_path, graph)

    def get_current_tab_id(self) -> Optional[str]:
        """Get the ID of the currently active workflow tab."""
        return self._workflow_tab_widget.get_current_tab_id()

    def get_current_graph(self) -> Optional["Graph"]:
        """Get the graph of the currently active workflow tab."""
        return self._workflow_tab_widget.get_current_graph()

    def get_current_graph_view(self) -> Optional["NodeGraphView"]:
        """Get the graph view of the currently active workflow tab."""
        return self._workflow_tab_widget.get_current_graph_view()

    def mark_current_tab_modified(self, modified: bool = True) -> None:
        """
        Mark the current workflow tab as modified or unmodified.

        Args:
            modified: Whether the workflow is modified.
        """
        tab_id = self._workflow_tab_widget.get_current_tab_id()
        if tab_id:
            self._workflow_tab_widget.mark_modified(tab_id, modified)

    def update_tab_context_in_status_bar(self) -> None:
        """Update the status bar to show current tab context."""
        tab = self._workflow_tab_widget.get_current_tab()
        if tab:
            self._update_status_bar_tab_context(tab)

    def _update_status_bar_tab_context(self, tab) -> None:
        """
        Update the status bar's permanent tab context widget.

        Shows detailed information about the current tab including:
        - Tab type (Workflow, Subworkflow, or Deep Subworkflow)
        - Hierarchy breadcrumb for subworkflows
        - View mode indicator
        - Modified status indicator

        Args:
            tab: The WorkflowTab to display information for.
        """
        # Import ViewMode for comparison
        from visualpython.ui.widgets.workflow_tab_widget import ViewMode

        # Show the tab context widget
        self._tab_context_widget.setVisible(True)

        # Update tab type indicator
        if tab.is_subworkflow:
            if tab.hierarchy_depth >= 2:
                self._tab_type_label.setText("DEEP SUB")
                self._tab_type_label.setProperty("tabType", "deep_subworkflow")
                self._tab_type_label.setToolTip(f"Deep subworkflow (Level {tab.hierarchy_depth})")
            else:
                self._tab_type_label.setText("SUBFLOW")
                self._tab_type_label.setProperty("tabType", "subworkflow")
                self._tab_type_label.setToolTip("Subworkflow (Level 1)")
        else:
            self._tab_type_label.setText("WORKFLOW")
            self._tab_type_label.setProperty("tabType", "workflow")
            self._tab_type_label.setToolTip("Root workflow")

        # Force style refresh for dynamic property change
        self._tab_type_label.style().unpolish(self._tab_type_label)
        self._tab_type_label.style().polish(self._tab_type_label)

        # Update breadcrumb/name
        if tab.is_subworkflow:
            # Show full hierarchy breadcrumb for subworkflows
            breadcrumb = self._workflow_tab_widget.get_hierarchy_breadcrumb(tab.tab_id)
            self._tab_breadcrumb_label.setText(breadcrumb)
            self._tab_breadcrumb_label.setToolTip(f"Hierarchy: {breadcrumb}")
        else:
            # Show just the name for root workflows
            self._tab_breadcrumb_label.setText(tab.name)
            if tab.file_path:
                self._tab_breadcrumb_label.setToolTip(f"File: {tab.file_path}")
            else:
                self._tab_breadcrumb_label.setToolTip("Unsaved workflow")

        # Update modified indicator
        if tab.is_modified:
            self._modified_indicator_label.setText("●")
            self._modified_indicator_label.setToolTip("Unsaved changes")
            self._modified_indicator_label.setVisible(True)
        else:
            self._modified_indicator_label.setText("")
            self._modified_indicator_label.setVisible(False)

        # Update view mode indicator
        view_mode_text = ""
        if tab.view_mode == ViewMode.EDIT:
            view_mode_text = ""  # Don't show for default mode
        elif tab.view_mode == ViewMode.RUN:
            view_mode_text = "[Run Mode]"
        elif tab.view_mode == ViewMode.COLLAPSED:
            view_mode_text = "[Collapsed]"
        elif tab.view_mode == ViewMode.EXPANDED:
            view_mode_text = "[Expanded]"

        if view_mode_text:
            self._view_mode_label.setText(view_mode_text)
            self._view_mode_label.setVisible(True)
        else:
            self._view_mode_label.setText("")
            self._view_mode_label.setVisible(False)

    def set_canvas_widget(self, widget: QWidget) -> None:
        """
        Set the main canvas widget in the central area.

        Note: This method is kept for backwards compatibility. For new code,
        prefer using the workflow tab widget directly via create_workflow_tab()
        or set_graph_view_factory().

        Args:
            widget: The widget to use as the main canvas (e.g., node graph editor).
        """
        # If the widget is being set before the tab widget exists, use old behavior
        if not hasattr(self, '_workflow_tab_widget') or self._workflow_tab_widget is None:
            # Remove any existing widgets (old behavior)
            while self._central_layout.count():
                item = self._central_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            self._central_layout.addWidget(widget)
        else:
            # Tab widget exists - this canvas should go in the first/main tab
            # This is for backwards compatibility during initial setup
            pass  # The tab widget is already in the layout

    def show_status_message(self, message: str, timeout: int = 0) -> None:
        """
        Show a message in the status bar.

        Args:
            message: The message to display.
            timeout: Time in milliseconds before the message is cleared (0 = permanent).
        """
        self._status_bar.showMessage(message, timeout)

    def execution_finished(self) -> None:
        """Reset UI state after execution finishes."""
        self._run_action.setEnabled(True)
        self._stop_action.setEnabled(False)
        self._step_action.setEnabled(False)
        self._continue_action.setEnabled(False)
        self._status_bar.showMessage("Execution completed", 3000)

    def on_step_paused(self, node_name: str) -> None:
        """
        Update UI when execution pauses at a node for step-through.

        Args:
            node_name: Name of the node where execution paused.
        """
        self._step_action.setEnabled(True)
        self._continue_action.setEnabled(True)
        self._status_bar.showMessage(f"Paused at: {node_name}")

    def set_step_mode(self, enabled: bool) -> None:
        """
        Set the step mode checkbox state.

        Args:
            enabled: Whether step mode should be enabled.
        """
        self._step_mode_action.setChecked(enabled)

    @property
    def is_step_mode_enabled(self) -> bool:
        """Check if step mode is enabled."""
        return self._step_mode_action.isChecked()

    def set_undo_enabled(self, enabled: bool) -> None:
        """Enable or disable the undo action."""
        self._undo_action.setEnabled(enabled)

    def set_redo_enabled(self, enabled: bool) -> None:
        """Enable or disable the redo action."""
        self._redo_action.setEnabled(enabled)

    # Access to actions for external binding
    @property
    def cut_action(self) -> QAction:
        """Get the cut action."""
        return self._cut_action

    @property
    def copy_action(self) -> QAction:
        """Get the copy action."""
        return self._copy_action

    @property
    def paste_action(self) -> QAction:
        """Get the paste action."""
        return self._paste_action

    @property
    def delete_action(self) -> QAction:
        """Get the delete action."""
        return self._delete_action

    @property
    def duplicate_action(self) -> QAction:
        """Get the duplicate action."""
        return self._duplicate_action

    @property
    def select_all_action(self) -> QAction:
        """Get the select all action."""
        return self._select_all_action

    @property
    def zoom_in_action(self) -> QAction:
        """Get the zoom in action."""
        return self._zoom_in_action

    @property
    def zoom_out_action(self) -> QAction:
        """Get the zoom out action."""
        return self._zoom_out_action

    @property
    def reset_zoom_action(self) -> QAction:
        """Get the reset zoom action."""
        return self._reset_zoom_action

    @property
    def fit_action(self) -> QAction:
        """Get the fit to window action."""
        return self._fit_action

    @property
    def snap_to_grid_action(self) -> QAction:
        """Get the snap to grid action."""
        return self._snap_to_grid_action

    @property
    def run_selected_action(self) -> QAction:
        """Get the run selected action."""
        return self._run_selected_action

    @property
    def step_mode_action(self) -> QAction:
        """Get the step mode toggle action."""
        return self._step_mode_action

    @property
    def step_action(self) -> QAction:
        """Get the step next action."""
        return self._step_action

    @property
    def continue_action(self) -> QAction:
        """Get the continue execution action."""
        return self._continue_action

    @property
    def docs_action(self) -> QAction:
        """Get the documentation action."""
        return self._docs_action

    @property
    def hierarchical_layout_action(self) -> QAction:
        """Get the hierarchical layout action."""
        return self._hierarchical_layout_action

    @property
    def force_directed_layout_action(self) -> QAction:
        """Get the force-directed layout action."""
        return self._force_directed_layout_action

    @property
    def export_python_action(self) -> QAction:
        """Get the export as Python action."""
        return self._export_python_action

    @property
    def export_library_action(self) -> QAction:
        """Get the export as library action."""
        return self._export_library_action

    @property
    def import_library_action(self) -> QAction:
        """Get the import library action."""
        return self._import_library_action

    @property
    def import_python_script_action(self) -> QAction:
        """Get the import Python script as code node action."""
        return self._import_python_script_action

    @property
    def group_action(self) -> QAction:
        """Get the group selected nodes action."""
        return self._group_action

    @property
    def ungroup_action(self) -> QAction:
        """Get the ungroup action."""
        return self._ungroup_action

    @property
    def find_action(self) -> QAction:
        """Get the find/search action."""
        return self._find_action

    @property
    def node_palette(self):
        """Get the node palette widget."""
        return self._node_palette

    @property
    def palette_dock(self) -> QDockWidget:
        """Get the node palette dock widget."""
        return self._palette_dock

    @property
    def output_console(self):
        """Get the output console widget."""
        return self._output_console

    @property
    def console_dock(self) -> QDockWidget:
        """Get the output console dock widget."""
        return self._console_dock

    @property
    def node_properties_panel(self):
        """Get the node properties panel widget."""
        return self._node_properties_panel

    @property
    def properties_dock(self) -> QDockWidget:
        """Get the node properties dock widget."""
        return self._properties_dock

    @property
    def variable_panel(self):
        """Get the variable panel widget."""
        return self._variable_panel

    @property
    def dependency_panel(self):
        """Get the dependency panel widget."""
        return self._variable_container.dependency_panel

    @property
    def variable_dock(self) -> QDockWidget:
        """Get the variable panel dock widget."""
        return self._variable_dock

    @property
    def variable_inspector(self):
        """Get the variable inspector widget."""
        return self._variable_inspector

    @property
    def inspector_dock(self) -> QDockWidget:
        """Get the variable inspector dock widget."""
        return self._inspector_dock

    @property
    def minimap(self) -> MinimapWidget:
        """Get the minimap widget."""
        return self._minimap

    @property
    def minimap_dock(self) -> QDockWidget:
        """Get the minimap dock widget."""
        return self._minimap_dock

    @property
    def execution_summary_panel(self):
        """Get the execution summary panel widget."""
        return self._execution_summary_panel

    @property
    def summary_dock(self) -> QDockWidget:
        """Get the execution summary dock widget."""
        return self._summary_dock

    def connect_minimap_to_graph_view(self, graph_view) -> None:
        """
        Connect the minimap to a graph view for navigation.

        Args:
            graph_view: The NodeGraphView to connect.
        """
        self._minimap.set_graph_view(graph_view)

    def get_stdout_callback(self) -> Callable[[str], None]:
        """
        Get a callback function for writing stdout to the console.

        Returns:
            A callable that writes text to the console stdout.
        """
        return self._output_console.write_stdout

    def get_stderr_callback(self) -> Callable[[str], None]:
        """
        Get a callback function for writing stderr to the console.

        Returns:
            A callable that writes text to the console stderr.
        """
        return self._output_console.write_stderr

    def console_execution_started(self) -> None:
        """Notify the console that execution has started."""
        self._output_console.execution_started()

    def console_execution_finished(self, success: bool, message: str = "") -> None:
        """
        Notify the console that execution has finished.

        Args:
            success: Whether execution was successful.
            message: Optional status message.
        """
        self._output_console.execution_finished(success, message)

    def variable_panel_execution_started(self) -> None:
        """Notify the variable panel that execution has started."""
        self._variable_panel.execution_started()

    def variable_panel_execution_finished(self) -> None:
        """Notify the variable panel that execution has finished."""
        self._variable_panel.execution_finished()

    def refresh_variable_panel(self) -> None:
        """Refresh the variable panel to show current state."""
        self._variable_panel.refresh()

    def summary_panel_execution_started(self) -> None:
        """Notify the execution summary panel that execution has started."""
        self._execution_summary_panel.execution_started()

    def summary_panel_execution_finished(self, success: bool, message: str = "") -> None:
        """
        Notify the execution summary panel that execution has finished.

        Args:
            success: Whether execution was successful.
            message: Optional status message.
        """
        self._execution_summary_panel.execution_finished(success, message)

    def update_summary_panel_from_result(self, result) -> None:
        """
        Update the execution summary panel with results from execution.

        This should be called after execution completes to populate the
        panel with statistics and error information.

        Args:
            result: The ExecutionResult from execution.
        """
        self._execution_summary_panel.update_from_result(result)
        # If there were errors, show the summary panel
        if result.node_summaries:
            # Check if any summaries indicate failures
            from visualpython.execution.context import NodeExecutionStatus
            has_errors = any(
                s.status == NodeExecutionStatus.FAILED
                for s in result.node_summaries.values()
            )
            if has_errors:
                self.show_execution_summary()

    def show_execution_summary(self) -> None:
        """Show the execution summary panel and bring it to front."""
        self._summary_dock.show()
        self._summary_dock.raise_()

    @property
    def execution_state_indicator(self) -> ExecutionStateIndicator:
        """Get the execution state indicator widget."""
        return self._execution_state_indicator

    def set_execution_state(self, state: ExecutionState) -> None:
        """
        Set the execution state in the indicator.

        Args:
            state: The new execution state.
        """
        self._execution_state_indicator.set_state(state)

    def connect_execution_state_manager(self, manager) -> None:
        """
        Connect the execution state indicator to a state manager.

        Args:
            manager: The ExecutionStateManager to connect to.
        """
        self._execution_state_indicator.connect_to_manager(manager)
        # Also connect the variable inspector
        self._variable_inspector.connect_to_state_manager(manager)

    def show_variable_inspector(self) -> None:
        """Show the variable inspector panel and bring it to front."""
        self._inspector_dock.show()
        self._inspector_dock.raise_()

    def refresh_variable_inspector(self) -> None:
        """Refresh the variable inspector to show current state."""
        self._variable_inspector.refresh()
