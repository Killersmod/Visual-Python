"""
Application controller for VisualPython.

This module provides the central application controller that manages the graph model,
handles save/load operations, and coordinates between the UI and data model.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.utils.logging import get_logger

# Logger for debugging subgraph connection issues
logger = get_logger(__name__)

from PyQt6.QtCore import QObject, pyqtSignal

from visualpython.graph.graph import Graph
from visualpython.graph.clipboard_manager import ClipboardManager
from visualpython.nodes.registry import NodeRegistry, get_node_registry
from visualpython.templates.registry import TemplateRegistry, get_template_registry
from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.serialization import (
    ProjectSerializer,
    SerializationError,
    VariableSerializer,
    LibrarySerializer,
    LibraryData,
    LibraryMetadata,
)
from visualpython.execution.engine import ExecutionEngine, ExecutionError
from visualpython.execution.context import ExecutionResult, ExecutionStatus
from visualpython.execution.output_capture import OutputCapture
from visualpython.execution.state_manager import ExecutionStateManager, ExecutionState
from visualpython.execution.worker import ExecutionThread
from visualpython.compiler.code_generator import CodeGenerator, GenerationError
from visualpython.commands.undo_manager import UndoRedoManager
from visualpython.commands.node_commands import (
    AddNodeCommand,
    RemoveNodeCommand,
    MoveNodeCommand,
    RenameNodeCommand,
    DuplicateNodesCommand,
)
from visualpython.commands.connection_commands import (
    AddConnectionCommand,
    RemoveConnectionCommand,
)
from visualpython.commands.property_commands import SetNodePropertyCommand, SetInlineValueCommand
from visualpython.commands.command import CompositeCommand
from visualpython.commands.group_commands import (
    CreateGroupCommand,
    RemoveGroupCommand,
    AddNodesToGroupCommand,
    RemoveNodesFromGroupCommand,
    RenameGroupCommand,
)
from visualpython.nodes.models.node_group import NodeGroup

if TYPE_CHECKING:
    from visualpython.ui.main_window import MainWindow
    from visualpython.graph.view import NodeGraphView
    from visualpython.nodes.views.port_widget import PortWidget
    from visualpython.nodes.models.port import Connection


class ApplicationController(QObject):
    """
    Central application controller for VisualPython.

    Manages the graph model and coordinates between the UI components.
    Handles project save/load operations and state management.

    Signals:
        graph_changed: Emitted when the graph is replaced (new/load).
        graph_modified: Emitted when the graph is modified.
        node_added: Emitted when a node is added (node_id).
        node_removed: Emitted when a node is removed (node_id).
        error_occurred: Emitted when an error occurs (error_message).
        selection_changed: Emitted when node selection changes (list of node IDs).
        subworkflow_created: Emitted when a subworkflow is created (node_id, name, embedded_graph_data).
    """

    graph_changed = pyqtSignal()
    graph_modified = pyqtSignal()
    node_added = pyqtSignal(str)
    node_removed = pyqtSignal(str)
    connection_removed = pyqtSignal(str)  # connection_key
    error_occurred = pyqtSignal(str)
    execution_finished = pyqtSignal(bool, str)  # (success, message)
    execution_state_changed = pyqtSignal(object)  # ExecutionState
    selection_changed = pyqtSignal(list)  # List of selected node IDs
    can_undo_changed = pyqtSignal(bool)  # Undo availability changed
    can_redo_changed = pyqtSignal(bool)  # Redo availability changed
    variables_saved = pyqtSignal(str)  # Emitted when variables are saved (file_path)
    variables_loaded = pyqtSignal(str, int)  # Emitted when variables are loaded (file_path, count)
    library_exported = pyqtSignal(str, int)  # Emitted when library is exported (file_path, node_count)
    library_imported = pyqtSignal(str, int)  # Emitted when library is imported (file_path, node_count)
    group_created = pyqtSignal(str)  # Emitted when a group is created (group_id)
    group_removed = pyqtSignal(str)  # Emitted when a group is removed (group_id)
    subworkflow_created = pyqtSignal(str, str, object)  # Emitted when subworkflow is created (node_id, name, embedded_graph_data)
    current_tab_changed = pyqtSignal(str, object)  # Emitted when current tab changes (tab_id, tab_context_dict)

    def __init__(
        self,
        main_window: Optional["MainWindow"] = None,
        graph_view: Optional["NodeGraphView"] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Initialize the application controller.

        Args:
            main_window: The main application window.
            graph_view: The node graph view widget.
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self._main_window = main_window
        self._graph_view = graph_view
        self._graph: Graph = Graph()
        self._current_file: Optional[Path] = None
        self._registry: NodeRegistry = get_node_registry()
        self._serializer: ProjectSerializer = ProjectSerializer(self._registry)
        self._execution_engine: Optional[ExecutionEngine] = None
        self._execution_thread: Optional[ExecutionThread] = None
        self._execution_state_manager: ExecutionStateManager = ExecutionStateManager(self)

        # Forward execution state changes
        self._execution_state_manager.state_changed.connect(self.execution_state_changed.emit)

        # Ensure default nodes are registered
        if not self._registry.get_all_node_types():
            self._registry.register_default_nodes()

        # Initialize template registry and load default templates
        self._template_registry: TemplateRegistry = get_template_registry()
        self._template_registry.load_default_templates()

        # Initialize clipboard manager
        self._clipboard_manager: ClipboardManager = ClipboardManager(self._registry, self)

        # Initialize variable serializer
        self._variable_serializer: VariableSerializer = VariableSerializer()

        # Initialize library serializer
        self._library_serializer: LibrarySerializer = LibrarySerializer()

        # Initialize dependency store for persisting named dependency trees
        from visualpython.dependencies.dependency_store import DependencyStore
        dep_db_dir = Path.home() / "VisualPython"
        dep_db_dir.mkdir(parents=True, exist_ok=True)
        self._dependency_store: DependencyStore = DependencyStore(
            dep_db_dir / "dependencies.db"
        )

        # Track if workflow library signals are connected
        self._workflow_library_connected: bool = False

        # Track if workflow tab signals are connected
        self._workflow_tabs_connected: bool = False

        # Current tab context tracking
        self._current_tab_id: Optional[str] = None
        self._current_tab_name: str = "Untitled Workflow"
        self._is_subworkflow_tab: bool = False
        self._parent_tab_id: Optional[str] = None
        self._subgraph_node_id: Optional[str] = None

        # Initialize undo/redo manager
        self._undo_redo_manager: UndoRedoManager = UndoRedoManager(parent=self)
        self._undo_redo_manager.can_undo_changed.connect(self.can_undo_changed.emit)
        self._undo_redo_manager.can_redo_changed.connect(self.can_redo_changed.emit)

        # Connect signals
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect UI signals to handlers."""
        if self._main_window:
            self._main_window.new_project_requested.connect(self.new_project)
            self._main_window.open_project_requested.connect(self.open_project)
            self._main_window.save_project_requested.connect(self.save_project)
            self._main_window.save_as_requested.connect(self.save_project_as)
            self._main_window.export_python_requested.connect(self.export_as_python)
            self._main_window.save_variables_requested.connect(self.save_variables)
            self._main_window.load_variables_requested.connect(self.load_variables)
            # Connect clipboard actions
            self._main_window.copy_action.triggered.connect(self.copy_selected_nodes)
            self._main_window.cut_action.triggered.connect(self.cut_selected_nodes)
            self._main_window.paste_action.triggered.connect(self.paste_nodes)
            # Connect duplicate action
            self._main_window.duplicate_action.triggered.connect(self.duplicate_selected_nodes)
            # Connect variable panel save/load signals
            self._main_window.variable_panel.save_requested.connect(
                self._on_variable_panel_save_requested
            )
            self._main_window.variable_panel.load_requested.connect(
                self._on_variable_panel_load_requested
            )
            # Connect dependency panel
            self._connect_dependency_panel()

            # Connect node properties panel
            self._connect_node_properties_panel()
            # Connect auto layout signal
            self._main_window.auto_layout_requested.connect(self.apply_auto_layout)
            # Connect library export/import signals
            self._main_window.export_library_requested.connect(self.export_library)
            self._main_window.import_library_requested.connect(self.import_library)
            # Connect Python script import signal
            self._main_window.import_python_script_requested.connect(
                self.import_python_script
            )
            # Connect snap to grid toggle
            self._main_window.snap_to_grid_toggled.connect(self._on_snap_to_grid_toggled)
            # Connect group signals
            self._main_window.group_selected_requested.connect(self._on_group_selected_requested)
            self._main_window.ungroup_selected_requested.connect(self._on_ungroup_selected_requested)
            # Connect step-through execution signals
            self._main_window.step_mode_toggled.connect(self._on_step_mode_toggled)
            self._main_window.step_requested.connect(self._on_step_requested)
            self._main_window.continue_requested.connect(self._on_continue_requested)

            # Connect view mode changes
            self._main_window.view_mode_changed.connect(self._on_view_mode_changed)

            # Connect workflow operations
            self._main_window.save_to_workflow_library_requested.connect(
                self._on_save_to_workflow_library
            )
            self._main_window.create_subworkflow_requested.connect(
                self._on_create_subworkflow_from_selection
            )

            # Connect workflow library signals
            self._connect_workflow_library()

            # Connect workflow tab widget signals
            self._connect_workflow_tab_signals()

            # Connect node navigation signal from execution summary panel
            self._main_window.navigate_to_node_requested.connect(
                self._on_navigate_to_node_requested
            )

        if self._graph_view:
            self._graph_view.node_dropped.connect(self._on_node_dropped)
            self._graph_view.workflow_dropped.connect(self._on_workflow_dropped)
            self._graph_view.connection_requested.connect(self._on_connection_requested)
            # Connect selection changed signal
            self._graph_view.selection_changed.connect(self._on_selection_changed)
            # Connect graph_changed to update the view when loading projects
            self.graph_changed.connect(self._on_graph_changed)
            # Connect scene deletion signals
            scene = self._graph_view.graph_scene
            scene.connection_delete_requested.connect(self._on_connection_delete_requested)
            scene.node_delete_requested.connect(self._on_node_delete_requested)
            scene.group_delete_requested.connect(self._on_group_delete_requested)
            scene.node_name_changed.connect(self._on_node_name_changed)
            scene.node_inline_value_changed.connect(self._on_inline_value_changed)
            scene.node_move_finished.connect(self._on_node_move_finished)
            # Connect subgraph navigation signal
            scene.open_subgraph_requested.connect(self._on_open_subgraph_requested)
            # Connect workflow context menu signals
            self._graph_view.create_subworkflow_requested.connect(
                self._on_create_subworkflow_from_selection
            )
            # Connect code editor signal
            self._graph_view.edit_code_requested.connect(self._on_edit_code_requested)

    def set_main_window(self, main_window: "MainWindow") -> None:
        """
        Set the main window reference and connect signals.

        Args:
            main_window: The main application window.
        """
        self._main_window = main_window
        self._main_window.new_project_requested.connect(self.new_project)
        self._main_window.open_project_requested.connect(self.open_project)
        self._main_window.save_project_requested.connect(self.save_project)
        self._main_window.save_as_requested.connect(self.save_project_as)
        self._main_window.export_python_requested.connect(self.export_as_python)
        self._main_window.save_variables_requested.connect(self.save_variables)
        self._main_window.load_variables_requested.connect(self.load_variables)
        # Connect variable panel save/load signals
        self._main_window.variable_panel.save_requested.connect(
            self._on_variable_panel_save_requested
        )
        self._main_window.variable_panel.load_requested.connect(
            self._on_variable_panel_load_requested
        )
        # Connect clipboard actions
        self._main_window.copy_action.triggered.connect(self.copy_selected_nodes)
        self._main_window.cut_action.triggered.connect(self.cut_selected_nodes)
        self._main_window.paste_action.triggered.connect(self.paste_nodes)
        # Connect duplicate action
        self._main_window.duplicate_action.triggered.connect(self.duplicate_selected_nodes)
        # Connect node properties panel
        self._connect_node_properties_panel()
        # Connect auto layout signal
        self._main_window.auto_layout_requested.connect(self.apply_auto_layout)
        # Connect library export/import signals
        self._main_window.export_library_requested.connect(self.export_library)
        self._main_window.import_library_requested.connect(self.import_library)
        # Connect Python script import signal
        self._main_window.import_python_script_requested.connect(
            self.import_python_script
        )
        # Connect snap to grid toggle
        self._main_window.snap_to_grid_toggled.connect(self._on_snap_to_grid_toggled)
        # Connect group signals
        self._main_window.group_selected_requested.connect(self._on_group_selected_requested)
        self._main_window.ungroup_selected_requested.connect(self._on_ungroup_selected_requested)
        # Connect step-through execution signals
        self._main_window.step_mode_toggled.connect(self._on_step_mode_toggled)
        self._main_window.step_requested.connect(self._on_step_requested)
        self._main_window.continue_requested.connect(self._on_continue_requested)

        # Connect view mode changes
        self._main_window.view_mode_changed.connect(self._on_view_mode_changed)

        # Connect workflow operations
        self._main_window.save_to_workflow_library_requested.connect(
            self._on_save_to_workflow_library
        )
        self._main_window.create_subworkflow_requested.connect(
            self._on_create_subworkflow_from_selection
        )

        # Connect workflow library signals
        self._connect_workflow_library()

        # Connect workflow tab widget signals
        self._connect_workflow_tab_signals()

        # Connect node navigation signal from execution summary panel
        self._main_window.navigate_to_node_requested.connect(
            self._on_navigate_to_node_requested
        )

    def set_graph_view(self, graph_view: "NodeGraphView") -> None:
        """
        Set the graph view reference and connect signals.

        Args:
            graph_view: The node graph view widget.
        """
        self._graph_view = graph_view
        self._graph_view.node_dropped.connect(self._on_node_dropped)
        self._graph_view.workflow_dropped.connect(self._on_workflow_dropped)
        self._graph_view.connection_requested.connect(self._on_connection_requested)
        # Connect selection changed signal
        self._graph_view.selection_changed.connect(self._on_selection_changed)
        # Connect graph_changed to update the view when loading projects
        self.graph_changed.connect(self._on_graph_changed)
        # Connect scene deletion signals
        scene = self._graph_view.graph_scene
        scene.connection_delete_requested.connect(self._on_connection_delete_requested)
        scene.node_delete_requested.connect(self._on_node_delete_requested)
        scene.group_delete_requested.connect(self._on_group_delete_requested)
        scene.node_name_changed.connect(self._on_node_name_changed)
        scene.node_inline_value_changed.connect(self._on_inline_value_changed)
        scene.node_move_finished.connect(self._on_node_move_finished)
        # Connect subgraph navigation signal
        scene.open_subgraph_requested.connect(self._on_open_subgraph_requested)
        # Connect workflow context menu signals
        self._graph_view.create_subworkflow_requested.connect(
            self._on_create_subworkflow_from_selection
        )
        # Connect code editor signal
        self._graph_view.edit_code_requested.connect(self._on_edit_code_requested)

    @property
    def graph(self) -> Graph:
        """Get the current graph."""
        return self._graph

    @property
    def current_file(self) -> Optional[Path]:
        """Get the current file path."""
        return self._current_file

    @property
    def is_modified(self) -> bool:
        """Check if the graph has unsaved changes."""
        return self._graph.is_modified

    @property
    def execution_state_manager(self) -> ExecutionStateManager:
        """Get the execution state manager."""
        return self._execution_state_manager

    @property
    def execution_state(self) -> ExecutionState:
        """Get the current execution state."""
        return self._execution_state_manager.state

    # Current Tab Context Properties

    @property
    def current_tab_id(self) -> Optional[str]:
        """Get the ID of the currently active tab."""
        return self._current_tab_id

    @property
    def current_tab_name(self) -> str:
        """Get the name of the currently active tab."""
        return self._current_tab_name

    @property
    def is_subworkflow_tab(self) -> bool:
        """Check if the current tab is editing a subworkflow."""
        return self._is_subworkflow_tab

    @property
    def parent_tab_id(self) -> Optional[str]:
        """Get the parent tab ID if current tab is a subworkflow."""
        return self._parent_tab_id

    @property
    def subgraph_node_id(self) -> Optional[str]:
        """Get the SubgraphNode ID being edited in the current tab."""
        return self._subgraph_node_id

    def get_current_tab_context(self) -> Dict[str, Any]:
        """
        Get the full context information for the current tab.

        Returns a dictionary containing:
            - tab_id: The unique ID of the current tab
            - name: The display name of the tab
            - is_subworkflow: Whether this is a subworkflow editing tab
            - parent_tab_id: The parent tab ID (if subworkflow)
            - subgraph_node_id: The SubgraphNode being edited (if subworkflow)
            - file_path: The associated file path (if any)
            - is_modified: Whether the workflow has unsaved changes

        Returns:
            Dictionary with current tab context.
        """
        return {
            "tab_id": self._current_tab_id,
            "name": self._current_tab_name,
            "is_subworkflow": self._is_subworkflow_tab,
            "parent_tab_id": self._parent_tab_id,
            "subgraph_node_id": self._subgraph_node_id,
            "file_path": str(self._current_file) if self._current_file else None,
            "is_modified": self._graph.is_modified if self._graph else False,
        }

    def _update_tab_context(self, tab_id: str) -> None:
        """
        Update the internal tab context tracking from the active tab.

        This method syncs the ApplicationController's tab context state with
        the actual WorkflowTab data from the WorkflowTabWidget.

        Args:
            tab_id: The ID of the tab to sync context from.
        """
        if not self._main_window or not hasattr(self._main_window, 'workflow_tab_widget'):
            return

        tab = self._main_window.workflow_tab_widget.get_tab(tab_id)
        if tab:
            old_tab_id = self._current_tab_id

            # Update all context fields
            self._current_tab_id = tab.tab_id
            self._current_tab_name = tab.name
            self._is_subworkflow_tab = tab.is_subworkflow
            self._parent_tab_id = tab.parent_workflow_id
            self._subgraph_node_id = tab.subgraph_node_id

            # Update current file from tab's file_path
            if tab.file_path:
                self._current_file = tab.file_path
            elif not tab.is_subworkflow:
                # Only clear file path for main workflows, not subworkflows
                self._current_file = None

            # Emit signal if tab actually changed
            if old_tab_id != tab_id:
                self.current_tab_changed.emit(tab_id, self.get_current_tab_context())

    # Factory Methods for Graph/View Creation

    def create_graph(self, name: str = "Untitled Graph") -> Graph:
        """
        Factory method to create a new Graph instance.

        This method is designed to be used by the WorkflowTabWidget to create
        new graphs for workflow tabs. It ensures graphs are created with
        consistent settings.

        Args:
            name: Name for the new graph.

        Returns:
            A new Graph instance.
        """
        return Graph(name=name)

    def create_graph_view(self) -> "NodeGraphView":
        """
        Factory method to create a new NodeGraphView instance.

        This method is designed to be used by the WorkflowTabWidget to create
        new graph views for workflow tabs. It sets up the view with proper
        scene configuration and signal connections.

        Returns:
            A new NodeGraphView instance with scene configured.
        """
        from visualpython.graph.view import NodeGraphView
        from visualpython.graph.scene import NodeGraphScene

        # Create a new scene and view
        scene = NodeGraphScene()
        view = NodeGraphView(scene=scene)

        # Connect scene signals for node/connection management
        # These enable undo/redo and proper state tracking
        scene.node_delete_requested.connect(self._on_node_delete_requested)
        scene.connection_delete_requested.connect(self._on_connection_delete_requested)
        scene.group_delete_requested.connect(self._on_group_delete_requested)
        scene.node_name_changed.connect(self._on_node_name_changed)
        scene.node_inline_value_changed.connect(self._on_inline_value_changed)
        scene.node_move_finished.connect(self._on_node_move_finished)
        # Connect subgraph navigation signal
        scene.open_subgraph_requested.connect(self._on_open_subgraph_requested)

        # Connect view signals
        view.node_dropped.connect(self._on_node_dropped)
        view.workflow_dropped.connect(self._on_workflow_dropped)
        view.connection_requested.connect(self._on_connection_requested)
        view.selection_changed.connect(self._on_selection_changed)
        view.create_subworkflow_requested.connect(
            self._on_create_subworkflow_from_selection
        )
        view.edit_code_requested.connect(self._on_edit_code_requested)

        return view

    def setup_tab_widget_factories(self) -> None:
        """
        Set up the factory methods on the WorkflowTabWidget.

        This method registers the graph and view factory functions with the
        MainWindow's WorkflowTabWidget so it can create new tabs with proper
        Graph and NodeGraphView instances.

        Should be called after the MainWindow is set via set_main_window().
        """
        if self._main_window:
            self._main_window.set_graph_view_factory(
                create_view=self.create_graph_view,
                create_graph=self.create_graph,
            )

    def create_initial_workflow_tab(self) -> str:
        """
        Create the initial workflow tab when the application starts.

        This method creates the first workflow tab with the current graph
        and sets up the main view for editing.

        Returns:
            The ID of the created tab.
        """
        if not self._main_window:
            raise RuntimeError("MainWindow must be set before creating workflow tabs")

        # Ensure factories are set up
        self.setup_tab_widget_factories()

        # Create initial tab with current graph
        logger.debug(
            "create_initial_workflow_tab: passing self._graph (id=%s) to tab",
            id(self._graph),
        )
        tab_id = self._main_window.create_workflow_tab(
            name=self._graph.name or "Untitled Workflow",
            graph=self._graph,
        )

        # Verify the tab received the same graph object (not a copy)
        tab_widget = self._main_window.workflow_tab_widget
        created_tab = tab_widget.get_tab(tab_id) if tab_widget else None
        if created_tab:
            logger.debug(
                "create_initial_workflow_tab: tab.graph id=%s (same=%s)",
                id(created_tab.graph),
                created_tab.graph is self._graph,
            )
            # Fix divergence: ensure the tab has the same graph object
            if created_tab.graph is not self._graph:
                logger.warning(
                    "create_initial_workflow_tab: tab graph DIVERGED! "
                    "Pushing self._graph to tab.",
                )
                created_tab.graph = self._graph

        # Get the graph view from the new tab and set it as current
        graph_view = self._main_window.get_current_graph_view()
        if graph_view and self._graph_view is None:
            self._graph_view = graph_view
            # Connect graph_changed to update the view
            self.graph_changed.connect(self._on_graph_changed)

        # Update the tab context tracking for the initial tab
        self._update_tab_context(tab_id)

        return tab_id

    def new_project(self) -> None:
        """Create a new empty project.

        Clears the current graph, resets the view to default state,
        and clears the output console for a fresh start.
        """
        self._graph = Graph()
        self._current_file = None
        self._undo_redo_manager.clear()  # Clear undo history for new project

        # Keep the current tab's graph in sync with the new graph
        if self._main_window and hasattr(self._main_window, 'workflow_tab_widget'):
            tab_widget = self._main_window.workflow_tab_widget
            current_tab = tab_widget.get_current_tab() if tab_widget else None
            if current_tab is not None:
                current_tab.graph = self._graph

        self.graph_changed.emit()

        if self._main_window:
            self._main_window.current_file = None
            self._main_window.is_modified = False
            # Clear the output console for a fresh start
            self._main_window.output_console.clear()
            # Update properties panel graph reference
            if hasattr(self._main_window, 'node_properties_panel'):
                self._main_window.node_properties_panel.set_graph(self._graph)
                self._main_window.node_properties_panel.on_selection_changed([])

        if self._graph_view:
            # Reset view to default zoom and center on origin
            self._graph_view.reset_view()

    def new_from_template(self, template_id: str) -> bool:
        """
        Create a new project from a template.

        Loads a pre-built template graph as the starting point for a new project.
        This provides a quick way to start common tasks.

        Args:
            template_id: The ID of the template to load.

        Returns:
            True if the template was successfully loaded, False otherwise.
        """
        template = self._template_registry.get_template(template_id)
        if template is None:
            error_msg = f"Template not found: {template_id}"
            self.error_occurred.emit(error_msg)
            if self._main_window:
                self._main_window.show_status_message(error_msg, 3000)
            return False

        try:
            # Create the graph from template
            new_graph = self._template_registry.create_graph_from_template(template_id)
            if new_graph is None:
                error_msg = f"Failed to create graph from template: {template_id}"
                self.error_occurred.emit(error_msg)
                if self._main_window:
                    self._main_window.show_status_message(error_msg, 3000)
                return False

            # Replace the current graph
            self._graph = new_graph
            self._current_file = None
            self._undo_redo_manager.clear()

            # Keep the current tab's graph in sync
            if self._main_window and hasattr(self._main_window, 'workflow_tab_widget'):
                tab_widget = self._main_window.workflow_tab_widget
                current_tab = tab_widget.get_current_tab() if tab_widget else None
                if current_tab is not None:
                    current_tab.graph = self._graph

            self.graph_changed.emit()

            if self._main_window:
                self._main_window.current_file = None
                self._main_window.is_modified = True  # Mark as modified since it's unsaved
                # Clear the output console
                self._main_window.output_console.clear()
                # Update properties panel graph reference
                if hasattr(self._main_window, 'node_properties_panel'):
                    self._main_window.node_properties_panel.set_graph(self._graph)
                    self._main_window.node_properties_panel.on_selection_changed([])
                # Show success message
                self._main_window.show_status_message(
                    f"Created new project from template: {template.name}", 3000
                )

            if self._graph_view:
                # Reset view and fit content
                self._graph_view.reset_view()
                # Fit to show all the template nodes
                self._graph_view.fit_in_view()

            return True

        except Exception as e:
            error_msg = f"Error creating project from template: {e}"
            self.error_occurred.emit(error_msg)
            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Template Error",
                    error_msg,
                )
            return False

    @property
    def template_registry(self) -> TemplateRegistry:
        """Get the template registry."""
        return self._template_registry

    def open_project(self, file_path: str) -> bool:
        """
        Open a project from a file.

        Args:
            file_path: Path to the project file.

        Returns:
            True if successful, False otherwise.
        """
        try:
            path = Path(file_path)
            self._graph = self._serializer.load(path)
            self._current_file = path
            self._undo_redo_manager.clear()  # Clear undo history when loading project

            # Keep the current tab's graph in sync with the loaded graph
            if self._main_window and hasattr(self._main_window, 'workflow_tab_widget'):
                tab_widget = self._main_window.workflow_tab_widget
                current_tab = tab_widget.get_current_tab() if tab_widget else None
                if current_tab is not None:
                    current_tab.graph = self._graph

            self.graph_changed.emit()

            if self._main_window:
                self._main_window.current_file = str(path)
                self._main_window.is_modified = False
                # Update properties panel graph reference
                if hasattr(self._main_window, 'node_properties_panel'):
                    self._main_window.node_properties_panel.set_graph(self._graph)
                    self._main_window.node_properties_panel.on_selection_changed([])
                # Update dependency panel with new graph
                self._update_dependency_panel()

            return True

        except SerializationError as e:
            error_msg = f"Failed to open project: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Open Error",
                    error_msg,
                )

            return False

    def save_project(self) -> bool:
        """
        Save the current project to the current file.

        If the active tab is a library workflow (has its own file_path),
        saves to that file instead of the main project file.

        Returns:
            True if successful, False otherwise.
        """
        # Check if the current tab has its own library file to save to
        if self._main_window and hasattr(self._main_window, 'workflow_tab_widget'):
            tab_widget = self._main_window.workflow_tab_widget
            current_tab = tab_widget.get_current_tab()
            if current_tab and current_tab.file_path:
                try:
                    self._serializer.save(current_tab.graph, current_tab.file_path)
                    current_tab.is_modified = False
                    if self._main_window:
                        self._main_window.show_status_message(
                            f"Saved '{current_tab.name}' to {current_tab.file_path}", 3000
                        )
                    return True
                except Exception as e:
                    error_msg = f"Failed to save workflow: {e}"
                    self.error_occurred.emit(error_msg)
                    return False

        if self._current_file is None:
            # No file set, prompt for save as
            if self._main_window:
                self._main_window._on_save_as()
            return False

        return self._save_to_file(self._current_file)

    def save_project_as(self, file_path: str) -> bool:
        """
        Save the project to a new file.

        Args:
            file_path: Path to save the project to.

        Returns:
            True if successful, False otherwise.
        """
        path = Path(file_path)
        if self._save_to_file(path):
            self._current_file = path
            return True
        return False

    def _save_to_file(self, path: Path) -> bool:
        """
        Save the graph to a file.

        Args:
            path: The file path to save to.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Always save the root graph for project files, even if the
            # user is currently editing a subworkflow tab.
            save_graph = self._get_root_graph()
            self._serializer.save(save_graph, path)

            if self._main_window:
                self._main_window.is_modified = False

            return True

        except SerializationError as e:
            error_msg = f"Failed to save project: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Save Error",
                    error_msg,
                )

            return False

    def _on_node_dropped(self, node_type: str, scene_x: float, scene_y: float) -> None:
        """
        Handle node drop from palette.

        Args:
            node_type: Type of node to create.
            scene_x: X position in scene coordinates.
            scene_y: Y position in scene coordinates.
        """
        self._ensure_graph_synced()

        # Build additional kwargs for specific node types
        node_kwargs = {}

        # For Code nodes, apply the default template from the palette if set
        if node_type == "code":
            from visualpython.ui.panels.node_palette import NodePaletteWidget
            default_template = NodePaletteWidget.get_default_code_template()
            if default_template:
                node_kwargs["code"] = default_template

        command = AddNodeCommand(
            graph=self._graph,
            node_type=node_type,
            x=scene_x,
            y=scene_y,
            registry=self._registry,
            add_widget_callback=self._add_node_widget,
            remove_widget_callback=self._remove_node_widget,
            **node_kwargs,
        )
        if self._undo_redo_manager.execute(command):
            self.node_added.emit(command.node_id)
            self._mark_modified()

    def _on_workflow_dropped(self, file_path: str, scene_x: float, scene_y: float) -> None:
        """
        Handle workflow drop from library panel (drag-and-drop to create subgraph).

        Creates a reference-based SubgraphNode pointing to the library file.

        Args:
            file_path: Path to the workflow file.
            scene_x: X position in scene coordinates.
            scene_y: Y position in scene coordinates.
        """
        from pathlib import Path
        from visualpython.nodes.models.subgraph_node import SubgraphNode

        # Ensure we operate on the current tab's graph
        self._ensure_graph_synced()

        try:
            path = Path(file_path)

            # Create a reference-based SubgraphNode pointing to the library file
            subgraph_node = SubgraphNode.create_reference(
                library_path=str(path),
                name=f"Subgraph: {path.stem}",
            )

            # Set position from drop location
            subgraph_node.position = Position(x=scene_x, y=scene_y)

            self._graph.add_node(subgraph_node)

            if self._graph_view:
                self._graph_view.graph_scene.add_node_widget(subgraph_node)

            self.node_added.emit(subgraph_node.id)
            self._mark_modified()
            if self._main_window:
                self._main_window.show_status_message(
                    f"Inserted subgraph: {subgraph_node.subgraph_name}", 2000
                )
        except Exception as e:
            self.error_occurred.emit(f"Failed to insert workflow as subgraph: {e}")

    def _on_connection_requested(
        self,
        source_port_widget: "PortWidget",
        target_port_widget: "PortWidget",
    ) -> None:
        """
        Handle connection request from drag-and-drop in the view.

        Args:
            source_port_widget: The output port widget (source).
            target_port_widget: The input port widget (target).
        """
        # Ensure we are working with the current tab's graph
        self._ensure_graph_synced()

        # Extract node and port information from widgets
        source_port = source_port_widget.port
        target_port = target_port_widget.port

        # Use the widget's parent node reference for determining node IDs.
        # This is the authoritative source because the widget was created from
        # the actual node. The port.node reference may incorrectly point to
        # internal SubgraphInput/SubgraphOutput nodes from embedded graph data.
        if source_port_widget.parent_node and source_port_widget.parent_node.node:
            source_node_id = source_port_widget.parent_node.node.id
        elif source_port.node:
            source_node_id = source_port.node.id
        else:
            logger.error("Cannot determine source node for port '%s'", source_port.name)
            self.error_occurred.emit("Cannot create connection: Source port has no node reference")
            return

        if target_port_widget.parent_node and target_port_widget.parent_node.node:
            target_node_id = target_port_widget.parent_node.node.id
        elif target_port.node:
            target_node_id = target_port.node.id
        else:
            logger.error("Cannot determine target node for port '%s'", target_port.name)
            self.error_occurred.emit("Cannot create connection: Target port has no node reference")
            return

        source_port_name = source_port.name
        target_port_name = target_port.name

        # Check if connection can be made
        can_connect, error_msg = self._graph.can_connect(
            source_node_id, source_port_name, target_node_id, target_port_name
        )

        if not can_connect:
            # Log diagnostic info to help track down graph divergence issues
            graph_nodes = list(self._graph._connection_model._nodes.keys())
            logger.warning(
                "Connection failed: %s | source=%s, target=%s | "
                "graph has %d nodes: %s",
                error_msg, source_node_id, target_node_id,
                len(graph_nodes), graph_nodes,
            )
            self.error_occurred.emit(f"Cannot create connection: {error_msg}")
            if self._main_window:
                self._main_window.show_status_message(
                    f"Connection failed: {error_msg}", 3000
                )
            return

        try:
            command = AddConnectionCommand(
                graph=self._graph,
                source_node_id=source_node_id,
                source_port_name=source_port_name,
                target_node_id=target_node_id,
                target_port_name=target_port_name,
                add_widget_callback=self._add_connection_widget,
                remove_widget_callback=self._remove_connection_widget,
                update_port_state_callback=self._update_port_connection_state,
            )
            if self._undo_redo_manager.execute(command):
                self._mark_modified()
                if self._main_window:
                    self._main_window.show_status_message("Connection created", 2000)

        except Exception as e:
            self.error_occurred.emit(f"Failed to create connection: {e}")
            if self._main_window:
                self._main_window.show_status_message(
                    f"Connection failed: {e}", 3000
                )

    def _on_connection_delete_requested(self, connection: "Connection") -> None:
        """
        Handle connection delete request from the scene.

        Args:
            connection: The connection model to delete.
        """
        try:
            command = RemoveConnectionCommand(
                graph=self._graph,
                source_node_id=connection.source_node_id,
                source_port_name=connection.source_port_name,
                target_node_id=connection.target_node_id,
                target_port_name=connection.target_port_name,
                add_widget_callback=self._add_connection_widget,
                remove_widget_callback=self._remove_connection_widget,
                update_port_state_callback=self._update_port_connection_state,
            )
            if self._undo_redo_manager.execute(command):
                connection_key = (
                    f"{connection.source_node_id}:"
                    f"{connection.source_port_name}:"
                    f"{connection.target_node_id}:"
                    f"{connection.target_port_name}"
                )
                self.connection_removed.emit(connection_key)
                self._mark_modified()

                if self._main_window:
                    self._main_window.show_status_message("Connection deleted", 2000)

        except Exception as e:
            self.error_occurred.emit(f"Failed to delete connection: {e}")
            if self._main_window:
                self._main_window.show_status_message(
                    f"Delete failed: {e}", 3000
                )

    def _on_node_delete_requested(self, node_id: str) -> None:
        """
        Handle node delete request from the scene.

        Args:
            node_id: The ID of the node to delete.
        """
        try:
            command = RemoveNodeCommand(
                graph=self._graph,
                node_id=node_id,
                registry=self._registry,
                add_widget_callback=self._add_node_widget,
                remove_widget_callback=self._remove_node_widget,
                add_connection_callback=self._add_connection_widget,
                remove_connection_callback=self._remove_connection_by_model,
            )
            if self._undo_redo_manager.execute(command):
                self.node_removed.emit(node_id)
                self._mark_modified()

                if self._main_window:
                    self._main_window.show_status_message("Node deleted", 2000)

        except Exception as e:
            self.error_occurred.emit(f"Failed to delete node: {e}")
            if self._main_window:
                self._main_window.show_status_message(
                    f"Delete failed: {e}", 3000
                )

    def _on_node_name_changed(
        self, node_id: str, old_name: str, new_name: str
    ) -> None:
        """
        Handle node name change from the scene.

        Creates a RenameNodeCommand for undo/redo support when a node
        is renamed through inline editing in the graph.

        Args:
            node_id: The ID of the node that was renamed.
            old_name: The previous name of the node.
            new_name: The new name of the node.
        """
        try:
            from visualpython.commands.node_commands import RenameNodeCommand

            # Create update callback to refresh the widget
            def update_widget(nid: str) -> None:
                if self._graph_view:
                    widget = self._graph_view.graph_scene.get_node_widget(nid)
                    if widget:
                        widget.prepareGeometryChange()
                        widget._calculate_size()
                        widget.update()

            # Note: The name has already been changed in the node model by the widget
            # We need to temporarily revert it so the command can properly track the change
            node = self._graph.get_node(node_id)
            if node:
                node._name = old_name  # Temporarily revert

            command = RenameNodeCommand(
                graph=self._graph,
                node_id=node_id,
                old_name=old_name,
                new_name=new_name,
                update_widget_callback=update_widget,
            )
            if self._undo_redo_manager.execute(command):
                self._mark_modified()

                if self._main_window:
                    self._main_window.show_status_message(
                        f"Node renamed to '{new_name}'", 2000
                    )

        except Exception as e:
            self.error_occurred.emit(f"Failed to rename node: {e}")
            if self._main_window:
                self._main_window.show_status_message(
                    f"Rename failed: {e}", 3000
                )

    def _on_open_subgraph_requested(self, node_id: str) -> None:
        """
        Handle request to open a subgraph node for editing in a new tab.

        This is triggered when the user double-clicks a SubgraphNodeWidget or
        selects "Edit Subgraph" from the context menu. Opens the subgraph's
        internal workflow in a new tab for editing.

        Args:
            node_id: The ID of the subgraph node to open.
        """
        from visualpython.nodes.models.subgraph_node import SubgraphNode

        # Get the node from the graph
        node = self._graph.get_node(node_id)
        if node is None:
            self.error_occurred.emit(f"Node not found: {node_id}")
            return

        # Verify it's a SubgraphNode
        if not isinstance(node, SubgraphNode):
            self.error_occurred.emit(f"Node {node_id} is not a subgraph node")
            return

        # Delegate to open_subgraph_in_tab (to be implemented in T010)
        self.open_subgraph_in_tab(node_id)

    def open_subgraph_in_tab(self, node_id: str) -> Optional[str]:
        """
        Open a subgraph node's internal workflow in a new tab.

        This method creates a new tab in the workflow tab widget containing
        the subgraph's internal workflow for editing. Changes made in the
        subgraph tab will be synced back to the parent SubgraphNode when
        the tab is saved or the user selects "Update Parent Workflow".

        The method performs the following steps:
        1. Validates that the node exists and is a SubgraphNode
        2. Retrieves the embedded graph data from the SubgraphNode
        3. Gets the current tab ID to use as the parent tab reference
        4. Opens a new subworkflow tab via the WorkflowTabWidget
        5. Updates the controller's graph reference to the subgraph's graph

        Args:
            node_id: The ID of the subgraph node to open.

        Returns:
            The tab ID of the newly created subworkflow tab, or None if
            the operation failed.

        Raises:
            Emits error_occurred signal if:
            - The node is not found
            - The node is not a SubgraphNode
            - The node has no embedded graph data
            - The WorkflowTabWidget is not available
        """
        from visualpython.nodes.models.subgraph_node import SubgraphNode

        # Validate the node exists
        node = self._graph.get_node(node_id)
        if node is None:
            self.error_occurred.emit(f"Cannot open subgraph: node {node_id} not found")
            return None

        # Validate it's a SubgraphNode
        if not isinstance(node, SubgraphNode):
            self.error_occurred.emit(
                f"Cannot open subgraph: node {node_id} is not a subgraph node"
            )
            return None

        # For reference-based nodes, use the library file path
        # For legacy embedded nodes, use the embedded graph data
        library_file_path = None
        subgraph_data = None
        if node.is_reference_based and node.subgraph_path:
            library_file_path = node.subgraph_path
            if node.is_reference_broken:
                self.error_occurred.emit(
                    f"Cannot open subgraph '{node.subgraph_name}': "
                    f"referenced file not found: {node.subgraph_path}"
                )
                return None
        else:
            subgraph_data = node.get_internal_graph_data()
            if subgraph_data is None:
                self.error_occurred.emit(
                    f"Cannot open subgraph '{node.subgraph_name}': no graph data. "
                    "The subgraph may need to be loaded from a file first."
                )
                return None

        # Ensure the main window and workflow tab widget are available
        if not self._main_window:
            self.error_occurred.emit("Cannot open subgraph: main window not available")
            return None

        if not hasattr(self._main_window, 'workflow_tab_widget'):
            self.error_occurred.emit(
                "Cannot open subgraph: workflow tab widget not available"
            )
            return None

        # Get the current tab ID to use as the parent reference
        parent_tab_id = self._current_tab_id
        if parent_tab_id is None:
            # Try to get it from the workflow tab widget
            parent_tab_id = self._main_window.workflow_tab_widget.get_current_tab_id()

        if parent_tab_id is None:
            self.error_occurred.emit(
                "Cannot open subgraph: no active parent workflow tab"
            )
            return None

        # Show status message while opening
        self._main_window.show_status_message(
            f"Opening subgraph '{node.subgraph_name}' for editing...", 2000
        )

        try:
            # Open the subworkflow in a new tab
            tab_id = self._main_window.workflow_tab_widget.open_subworkflow(
                parent_tab_id=parent_tab_id,
                subgraph_node_id=node_id,
                subgraph_data=subgraph_data,
                name=node.subgraph_name,
                library_file_path=library_file_path,
            )

            # Update the controller's graph and view references to the new subgraph
            # This is handled automatically by _on_workflow_tab_changed when the
            # new tab becomes active, but we can also update the context here
            self._update_tab_context(tab_id)

            # Update the graph reference to the subgraph's graph
            new_graph = self._main_window.workflow_tab_widget.get_current_graph()
            if new_graph:
                self._graph = new_graph

            # Update the graph view reference
            new_view = self._main_window.workflow_tab_widget.get_current_graph_view()
            if new_view:
                self._graph_view = new_view

            # Show success message
            self._main_window.show_status_message(
                f"Opened subgraph '{node.subgraph_name}' in new tab", 3000
            )

            return tab_id

        except Exception as e:
            error_msg = f"Failed to open subgraph '{node.subgraph_name}': {e}"
            self.error_occurred.emit(error_msg)
            if self._main_window:
                self._main_window.show_status_message(error_msg, 5000)
            return None

    def _on_edit_code_requested(self, node_id: str) -> None:
        """
        Handle request to edit code in a Code node from the graph context menu.

        Opens a modal code editor dialog with the node's current code content.
        If the user saves changes, updates the node's code property using the
        command system for undo/redo support.

        Args:
            node_id: The ID of the Code node to edit.
        """
        from visualpython.ui.dialogs.code_edit_dialog import CodeEditDialog
        from visualpython.nodes.models.code_node import CodeNode

        # Get the node from the graph
        node = self._graph.get_node(node_id)
        if node is None:
            self.error_occurred.emit(f"Node not found: {node_id}")
            return

        # Verify it's a Code node
        if not isinstance(node, CodeNode):
            self.error_occurred.emit(f"Node {node_id} is not a Code node")
            return

        # Get current code from the node
        current_code = node.code

        # Create dialog title with node name
        title = f"Edit Code - {node.name}"

        # Open the code edit dialog
        parent_widget = self._main_window if self._main_window else None
        accepted, new_code = CodeEditDialog.edit_code(
            parent=parent_widget,
            title=title,
            initial_code=current_code,
        )

        if accepted and new_code != current_code:
            # Use the command system to update the code for undo/redo support
            command = SetNodePropertyCommand(
                graph=self._graph,
                node_id=node_id,
                property_name="code",
                old_value=current_code,
                new_value=new_code,
            )
            if self._undo_redo_manager.execute(command):
                self._mark_modified()
                if self._main_window:
                    self._main_window.show_status_message("Code updated", 2000)
                # Update the node widget's code preview if visible
                if self._graph_view:
                    scene = self._graph_view.graph_scene
                    node_widget = scene.get_node_widget(node_id)
                    if node_widget:
                        node_widget.update_code_preview()

    def add_node(
        self,
        node_type: str,
        x: float = 0.0,
        y: float = 0.0,
        name: Optional[str] = None,
    ):
        """
        Add a node to the graph.

        Args:
            node_type: Type of node to create.
            x: X position.
            y: Y position.
            name: Optional custom name for the node.

        Returns:
            The created node, or None if creation failed.
        """
        node = self._registry.create_node(
            node_type=node_type,
            name=name,
            position=Position(x, y),
        )

        if node:
            self._graph.add_node(node)

            # Log graph identity for debugging graph-reference divergence
            logger.debug(
                "add_node: added '%s' to self._graph (id=%s, now %d nodes)",
                node_type, id(self._graph), len(self._graph.nodes),
            )

            # Create the visual widget for the node
            if self._graph_view:
                self._graph_view.graph_scene.add_node_widget(node)

            self.node_added.emit(node.id)
            self._mark_modified()
            return node

        return None

    def remove_node(self, node_id: str) -> bool:
        """
        Remove a node from the graph.

        Args:
            node_id: ID of the node to remove.

        Returns:
            True if the node was removed, False otherwise.
        """
        node = self._graph.remove_node(node_id)
        if node:
            self.node_removed.emit(node_id)
            self._mark_modified()
            return True
        return False

    def _mark_modified(self) -> None:
        """Mark the graph as modified."""
        if self._main_window:
            self._main_window.is_modified = True
        self.graph_modified.emit()

    def _connect_node_properties_panel(self) -> None:
        """Connect the node properties panel to the application."""
        if self._main_window and hasattr(self._main_window, 'node_properties_panel'):
            panel = self._main_window.node_properties_panel
            # Set the graph reference so the panel can look up nodes
            panel.set_graph(self._graph)
            # Connect panel signals to mark graph as modified
            panel.property_changed.connect(self._on_node_property_changed)
            panel.node_name_changed.connect(self._on_node_name_changed)
            panel.node_color_changed.connect(self._on_node_color_changed)
            # Connect selection changes to update panel
            self.selection_changed.connect(panel.on_selection_changed)

    def _on_node_property_changed(
        self, node_id: str, property_name: str, value: Any
    ) -> None:
        """
        Handle property change from the properties panel.

        Args:
            node_id: ID of the node.
            property_name: Name of the changed property.
            value: New value.
        """
        node = self._graph.get_node(node_id)
        if not node:
            return

        # Get old value for undo
        if property_name == "position_x":
            old_value = node.position.x
        elif property_name == "position_y":
            old_value = node.position.y
        elif hasattr(node, property_name):
            old_value = getattr(node, property_name)
        else:
            old_value = None

        command = SetNodePropertyCommand(
            graph=self._graph,
            node_id=node_id,
            property_name=property_name,
            old_value=old_value,
            new_value=value,
            update_callback=self._on_property_update,
        )
        if self._undo_redo_manager.execute(command):
            self._mark_modified()

    def _on_property_update(self, node_id: str, property_name: str, value: Any) -> None:
        """
        Callback to update visual state after property change.

        Args:
            node_id: ID of the node.
            property_name: Name of the changed property.
            value: New value.
        """
        if not self._graph_view:
            return

        node = self._graph.get_node(node_id)
        if not node:
            return

        scene = self._graph_view.graph_scene
        widget = scene.get_node_widget(node_id)
        if not widget:
            return

        # Update the node widget based on property type
        if property_name in ("position_x", "position_y"):
            # Position changes just need setPos
            widget.setPos(node.position.x, node.position.y)
        elif property_name == "code":
            # Code changes need full sync to update the code display
            # This ensures the CodeNodeWidget updates its code preview
            # and validation state
            widget.sync_from_model()
        else:
            # For other properties, do a basic update
            widget.update()

    def _on_node_move_finished(
        self, node_id: str, old_x: float, old_y: float, new_x: float, new_y: float
    ) -> None:
        """
        Handle node move finished from the scene.

        Creates a MoveNodeCommand for undo/redo support when a node
        is dragged to a new position.

        Args:
            node_id: ID of the node that was moved.
            old_x: Original X position.
            old_y: Original Y position.
            new_x: New X position.
            new_y: New Y position.
        """
        # The node model position is already updated by the widget's itemChange.
        # We temporarily revert it so the command can properly track the change.
        node = self._graph.get_node(node_id)
        if not node:
            return

        node.position.x = old_x
        node.position.y = old_y

        command = MoveNodeCommand(
            graph=self._graph,
            node_id=node_id,
            old_x=old_x,
            old_y=old_y,
            new_x=new_x,
            new_y=new_y,
            update_widget_callback=self._update_node_widget_position,
        )
        if self._undo_redo_manager.execute(command):
            self._mark_modified()

    def _update_node_widget_position(
        self, node_id: str, x: float, y: float
    ) -> None:
        """
        Callback to update a node widget's position after undo/redo.

        Args:
            node_id: ID of the node.
            x: X position to set.
            y: Y position to set.
        """
        if not self._graph_view:
            return

        widget = self._graph_view.graph_scene.get_node_widget(node_id)
        if widget:
            widget.setPos(x, y)
            self._graph_view.graph_scene.update_connections_for_node(node_id)

    def _on_inline_value_changed(
        self, node_id: str, port_name: str, old_value: object, new_value: object
    ) -> None:
        """
        Handle inline value change from a node widget for undo/redo.

        Args:
            node_id: ID of the node.
            port_name: Name of the input port.
            old_value: Previous inline value.
            new_value: New inline value.
        """
        command = SetInlineValueCommand(
            graph=self._graph,
            node_id=node_id,
            port_name=port_name,
            old_value=old_value,
            new_value=new_value,
            update_callback=self._on_inline_value_update,
        )
        if self._undo_redo_manager.execute(command):
            self._mark_modified()

    def _on_inline_value_update(
        self, node_id: str, port_name: str, value: Any
    ) -> None:
        """
        Callback to update the inline widget after undo/redo.

        Args:
            node_id: ID of the node.
            port_name: Name of the input port.
            value: Value to display.
        """
        if not self._graph_view:
            return

        scene = self._graph_view.graph_scene
        widget = scene.get_node_widget(node_id)
        if not widget:
            return

        # Update the old-value tracker so next user edit has correct baseline
        widget._inline_old_values[port_name] = value

        port_widget = widget.get_input_port_widget(port_name)
        if port_widget:
            port_widget.sync_inline_widget_from_port()

    def _on_node_name_changed(self, node_id: str, new_name: str) -> None:
        """
        Handle node name change from the properties panel.

        Args:
            node_id: ID of the node.
            new_name: New name for the node.
        """
        node = self._graph.get_node(node_id)
        if not node:
            return

        old_name = node.name

        command = RenameNodeCommand(
            graph=self._graph,
            node_id=node_id,
            old_name=old_name,
            new_name=new_name,
            update_widget_callback=self._update_node_widget,
        )
        if self._undo_redo_manager.execute(command):
            self._mark_modified()

    def _on_node_color_changed(self, node_id: str, new_color: Any) -> None:
        """
        Handle node color change from the properties panel.

        Args:
            node_id: ID of the node.
            new_color: New color hex string, or None to reset to default.
        """
        node = self._graph.get_node(node_id)
        if not node:
            return

        old_color = node.custom_color

        command = SetNodePropertyCommand(
            graph=self._graph,
            node_id=node_id,
            property_name="custom_color",
            old_value=old_color,
            new_value=new_color,
            update_callback=self._on_color_update,
        )
        if self._undo_redo_manager.execute(command):
            self._mark_modified()

    def _on_color_update(self, node_id: str, property_name: str, value: Any) -> None:
        """
        Callback to update visual state after color change.

        Args:
            node_id: ID of the node.
            property_name: Should be 'custom_color'.
            value: New color value.
        """
        if self._graph_view:
            scene = self._graph_view.graph_scene
            widget = scene.get_node_widget(node_id)
            if widget:
                widget.update_color()

    def _update_node_widget(self, node_id: str) -> None:
        """
        Update a node widget's visual appearance.

        Args:
            node_id: ID of the node.
        """
        if self._graph_view:
            scene = self._graph_view.graph_scene
            widget = scene.get_node_widget(node_id)
            if widget:
                widget.update()

    # Helper methods for undo/redo command callbacks

    def _add_node_widget(self, node: BaseNode) -> None:
        """
        Add a visual widget for a node.

        Args:
            node: The node to create a widget for.
        """
        if self._graph_view:
            self._graph_view.graph_scene.add_node_widget(node)

    def _remove_node_widget(self, node_id: str) -> None:
        """
        Remove the visual widget for a node.

        Args:
            node_id: ID of the node whose widget to remove.
        """
        if self._graph_view:
            scene = self._graph_view.graph_scene
            # First remove all connection widgets for this node
            connection_widgets = scene.get_connections_for_node(node_id)
            for conn_widget in connection_widgets:
                conn = conn_widget.connection
                # Update the other node's port state
                if conn.source_node_id == node_id:
                    other_node_widget = scene.get_node_widget(conn.target_node_id)
                    if other_node_widget:
                        port_widget = other_node_widget.get_input_port_widget(
                            conn.target_port_name
                        )
                        if port_widget:
                            port_widget.is_connected = False
                else:
                    other_node_widget = scene.get_node_widget(conn.source_node_id)
                    if other_node_widget:
                        port_widget = other_node_widget.get_output_port_widget(
                            conn.source_port_name
                        )
                        if port_widget:
                            remaining = self._graph.get_connections_for_port(
                                conn.source_node_id,
                                conn.source_port_name,
                                is_input=False,
                            )
                            remaining = [
                                c for c in remaining
                                if c.target_node_id != node_id
                            ]
                            port_widget.is_connected = len(remaining) > 0
                scene.remove_connection_widget(conn_widget.connection_key)
            # Remove the node widget
            scene.remove_node_widget(node_id)

    def _add_connection_widget(self, connection: "Connection") -> None:
        """
        Add a visual widget for a connection.

        Args:
            connection: The connection to create a widget for.
        """
        if self._graph_view:
            self._graph_view.graph_scene.add_connection_widget(connection)

    def _remove_connection_widget(self, connection_key: str) -> None:
        """
        Remove a visual connection widget by its key.

        Args:
            connection_key: The connection key (source:port:target:port).
        """
        if self._graph_view:
            self._graph_view.graph_scene.remove_connection_widget(connection_key)

    def _remove_connection_by_model(self, connection: "Connection") -> None:
        """
        Remove a visual connection widget by its model.

        Args:
            connection: The connection model.
        """
        if self._graph_view:
            connection_key = (
                f"{connection.source_node_id}:"
                f"{connection.source_port_name}:"
                f"{connection.target_node_id}:"
                f"{connection.target_port_name}"
            )
            self._graph_view.graph_scene.remove_connection_widget(connection_key)

    def _update_port_connection_state(
        self, node_id: str, port_name: str, is_input: bool, is_connected: bool
    ) -> None:
        """
        Update the visual connection state of a port.

        Args:
            node_id: ID of the node.
            port_name: Name of the port.
            is_input: True if input port, False if output port.
            is_connected: Whether the port is connected.
        """
        if self._graph_view:
            scene = self._graph_view.graph_scene
            node_widget = scene.get_node_widget(node_id)
            if node_widget:
                if is_input:
                    port_widget = node_widget.get_input_port_widget(port_name)
                else:
                    port_widget = node_widget.get_output_port_widget(port_name)
                if port_widget:
                    port_widget.is_connected = is_connected

    # Group widget helpers

    def _add_group_widget(self, group: "NodeGroup") -> None:
        """
        Add a visual widget for a group.

        Args:
            group: The group to create a widget for.
        """
        if self._graph_view:
            self._graph_view.graph_scene.add_group_widget(group)

    def _remove_group_widget(self, group_id: str) -> None:
        """
        Remove the visual widget for a group.

        Args:
            group_id: ID of the group whose widget to remove.
        """
        if self._graph_view:
            self._graph_view.graph_scene.remove_group_widget(group_id)

    def _update_group_widget(self, group_id: str) -> None:
        """
        Update the visual widget for a group.

        Args:
            group_id: ID of the group to update.
        """
        if self._graph_view:
            self._graph_view.graph_scene.update_group_widget(group_id)

    def _calculate_group_bounds(self, node_ids: List[str]):
        """
        Calculate bounds for a group based on node positions.

        Args:
            node_ids: List of node IDs.

        Returns:
            GroupBounds object.
        """
        if self._graph_view:
            return self._graph_view.graph_scene.calculate_bounds_for_nodes(node_ids)
        from visualpython.nodes.models.node_group import GroupBounds
        return GroupBounds()

    # Group management methods

    def create_group_from_selection(
        self,
        name: str = "Group",
        color: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a group from the currently selected nodes.

        Args:
            name: Name for the group.
            color: Optional color for the group.

        Returns:
            The ID of the created group, or None if no nodes selected.
        """
        selected_ids = self.get_selected_node_ids()
        if not selected_ids:
            if self._main_window:
                self._main_window.show_status_message(
                    "No nodes selected to group", 3000
                )
            return None

        # Check if any selected nodes are already in a group
        for node_id in selected_ids:
            existing_group = self._graph.get_group_for_node(node_id)
            if existing_group:
                if self._main_window:
                    self._main_window.show_status_message(
                        f"Some nodes are already in group '{existing_group.name}'",
                        3000
                    )
                # Continue anyway - we'll add them to the new group

        command = CreateGroupCommand(
            graph=self._graph,
            node_ids=selected_ids,
            name=name,
            color=color,
            add_widget_callback=self._add_group_widget,
            remove_widget_callback=self._remove_group_widget,
            calculate_bounds_callback=self._calculate_group_bounds,
        )

        if self._undo_redo_manager.execute(command):
            self.group_created.emit(command.group_id)
            self._mark_modified()
            if self._main_window:
                self._main_window.show_status_message(
                    f"Created group '{name}' with {len(selected_ids)} nodes", 2000
                )
            return command.group_id

        return None

    def ungroup(self, group_id: str) -> bool:
        """
        Remove a group (ungroup nodes).

        The nodes remain in place, only the group container is removed.

        Args:
            group_id: ID of the group to remove.

        Returns:
            True if the group was removed.
        """
        group = self._graph.get_group(group_id)
        if not group:
            return False

        # If group is collapsed, expand it first to show nodes
        if group.collapsed and self._graph_view:
            self._graph_view.graph_scene.set_nodes_visibility_for_group(
                group_id, True
            )

        command = RemoveGroupCommand(
            graph=self._graph,
            group_id=group_id,
            add_widget_callback=self._add_group_widget,
            remove_widget_callback=self._remove_group_widget,
        )

        if self._undo_redo_manager.execute(command):
            self.group_removed.emit(group_id)
            self._mark_modified()
            if self._main_window:
                self._main_window.show_status_message("Group removed", 2000)
            return True

        return False

    def add_nodes_to_group(self, group_id: str, node_ids: List[str]) -> bool:
        """
        Add nodes to an existing group.

        Args:
            group_id: ID of the group.
            node_ids: List of node IDs to add.

        Returns:
            True if nodes were added.
        """
        command = AddNodesToGroupCommand(
            graph=self._graph,
            group_id=group_id,
            node_ids=node_ids,
            update_widget_callback=lambda gid: self._update_group_bounds(gid),
        )

        if self._undo_redo_manager.execute(command):
            self._mark_modified()
            return True
        return False

    def _update_group_bounds(self, group_id: str) -> None:
        """Update the bounds of a group widget."""
        if self._graph_view:
            self._graph_view.graph_scene.update_group_bounds(group_id)

    def remove_nodes_from_group(self, group_id: str, node_ids: List[str]) -> bool:
        """
        Remove nodes from a group.

        Args:
            group_id: ID of the group.
            node_ids: List of node IDs to remove.

        Returns:
            True if nodes were removed.
        """
        command = RemoveNodesFromGroupCommand(
            graph=self._graph,
            group_id=group_id,
            node_ids=node_ids,
            update_widget_callback=lambda gid: self._update_group_bounds(gid),
        )

        if self._undo_redo_manager.execute(command):
            self._mark_modified()
            return True
        return False

    def rename_group(self, group_id: str, new_name: str) -> bool:
        """
        Rename a group.

        Args:
            group_id: ID of the group.
            new_name: New name for the group.

        Returns:
            True if the group was renamed.
        """
        group = self._graph.get_group(group_id)
        if not group:
            return False

        old_name = group.name
        if old_name == new_name:
            return True

        command = RenameGroupCommand(
            graph=self._graph,
            group_id=group_id,
            old_name=old_name,
            new_name=new_name,
            update_widget_callback=self._update_group_widget,
        )

        if self._undo_redo_manager.execute(command):
            self._mark_modified()
            return True
        return False

    def _on_group_delete_requested(self, group_id: str) -> None:
        """
        Handle group delete request from the scene.

        Args:
            group_id: The ID of the group to delete.
        """
        self.ungroup(group_id)

    def _on_selection_changed(self, selected_node_ids: list) -> None:
        """
        Handle selection changes from the view.

        Args:
            selected_node_ids: List of selected node IDs.
        """
        self.selection_changed.emit(selected_node_ids)
        if self._main_window:
            count = len(selected_node_ids)
            if count == 0:
                self._main_window.show_status_message("Selection cleared", 1500)
            elif count == 1:
                node = self._graph.get_node(selected_node_ids[0])
                if node:
                    self._main_window.show_status_message(
                        f"Selected: {node.name}", 1500
                    )
            else:
                self._main_window.show_status_message(
                    f"Selected {count} nodes", 1500
                )

    def get_selected_node_ids(self) -> list:
        """
        Get the IDs of currently selected nodes.

        Returns:
            List of selected node IDs.
        """
        if self._graph_view:
            return self._graph_view.get_selected_node_ids()
        return []

    def get_selected_nodes(self) -> list:
        """
        Get the currently selected node models.

        Returns:
            List of selected BaseNode instances.
        """
        selected_ids = self.get_selected_node_ids()
        return [
            self._graph.get_node(node_id)
            for node_id in selected_ids
            if self._graph.get_node(node_id) is not None
        ]

    def delete_selected_nodes(self) -> int:
        """
        Delete all currently selected nodes and connections.

        Delegates to the view's comprehensive delete method which handles
        both nodes and connections (selected items + focused connection).

        Returns:
            Number of items deleted.
        """
        if self._graph_view:
            self._graph_view._delete_selected_nodes()
        return 0

    def _on_graph_changed(self) -> None:
        """Handle graph changed event to update the visual representation."""
        if self._graph_view:
            self._graph_view.load_graph(self._graph)

    def _connect_dependency_panel(self) -> None:
        """Connect dependency panel signals and set up its store."""
        if not self._main_window or not hasattr(self._main_window, 'dependency_panel'):
            return

        dep_panel = self._main_window.dependency_panel
        dep_panel.set_dependency_store(self._dependency_store)
        dep_panel.dependency_selected.connect(self._on_dependency_selected)
        dep_panel.tree_saved.connect(self._on_dependency_tree_saved)

        # Auto-rescan when graph structure changes
        self.node_added.connect(self._on_dependency_rescan_needed)
        self.node_removed.connect(self._on_dependency_rescan_needed)
        self.subworkflow_created.connect(
            lambda *_: self._on_dependency_rescan_needed()
        )
        self.graph_modified.connect(self._on_dependency_rescan_needed)

        # Set initial graph state (also triggers first auto-scan)
        self._update_dependency_panel()

    def _on_dependency_rescan_needed(self, *_args: Any) -> None:
        """Trigger a debounced dependency rescan after a graph structure change."""
        if not self._main_window or not hasattr(self._main_window, 'dependency_panel'):
            return
        self._main_window.dependency_panel.request_scan()

    def _update_dependency_panel(self) -> None:
        """Update the dependency panel with the current graph and library paths."""
        if not self._main_window or not hasattr(self._main_window, 'dependency_panel'):
            return

        dep_panel = self._main_window.dependency_panel

        # Gather scan paths from the workflow library and project directory
        scan_paths: list = []
        if hasattr(self._main_window, 'workflow_library'):
            scan_paths.extend(self._main_window.workflow_library._library_paths)
        if self._current_file:
            scan_paths.append(self._current_file.parent)
        dep_panel.set_library_paths(scan_paths)

        # set_graph triggers an auto-scan via request_scan()
        file_path = str(self._current_file) if self._current_file else None
        dep_panel.set_graph(self._graph, file_path)

    def _on_dependency_selected(self, file_path: str) -> None:
        """Open a dependency workflow in a new tab."""
        if not self._main_window:
            return
        try:
            graph = self._serializer.load(file_path)
        except SerializationError as e:
            self.error_occurred.emit(f"Failed to open dependency: {e}")
            return
        self._main_window.open_workflow_in_tab(file_path, graph)

    def _on_dependency_tree_saved(self, name: str, tree_hash: str) -> None:
        """Log when a dependency tree is saved."""
        logger.info(
            "Dependency tree '%s' saved (hash: %s)", name, tree_hash[:12]
        )

    def _connect_workflow_library(self) -> None:
        """Connect workflow library panel signals."""
        if not self._main_window or not hasattr(self._main_window, 'workflow_library'):
            return

        # Prevent duplicate connections
        if self._workflow_library_connected:
            return

        library = self._main_window.workflow_library

        # Connect library signals
        library.workflow_open_requested.connect(self._on_workflow_open_requested)
        library.workflow_insert_requested.connect(self._on_workflow_insert_requested)
        library.save_current_requested.connect(self._on_save_to_workflow_library)
        library.save_selection_as_workflow_requested.connect(
            self._on_create_subworkflow_from_selection
        )

        # Connect subworkflow_created signal to auto-save to library
        self.subworkflow_created.connect(self._auto_save_subworkflow_to_library)

        # Connect version change signal to refresh SubgraphNodes
        library.workflow_version_changed.connect(self._on_workflow_version_changed)
        library.library_refreshed.connect(self._on_library_refreshed)

        # Rescan dependencies when library changes (reverse deps may change)
        library.library_refreshed.connect(self._on_dependency_rescan_needed)
        library.workflow_version_changed.connect(
            lambda *_: self._on_dependency_rescan_needed()
        )

        self._workflow_library_connected = True

    def _connect_workflow_tab_signals(self) -> None:
        """
        Connect workflow tab widget signals to ApplicationController handlers.

        This method connects the tab-related signals from MainWindow (which forwards
        them from WorkflowTabWidget) to handler methods in the ApplicationController.

        Signals connected:
        - tab_changed: Active tab changed
        - workflow_tab_created: New workflow tab created
        - workflow_tab_closed: Workflow tab closed
        - subworkflow_tab_opened: Subworkflow opened for editing
        """
        if not self._main_window:
            return

        # Prevent duplicate connections
        if self._workflow_tabs_connected:
            return

        # Connect tab change signal to update ApplicationController context
        self._main_window.tab_changed.connect(self._on_workflow_tab_changed)

        # Connect workflow lifecycle signals
        self._main_window.workflow_tab_created.connect(self._on_workflow_tab_created)
        self._main_window.workflow_tab_closed.connect(self._on_workflow_tab_closed)

        # Connect subworkflow tab signal
        self._main_window.subworkflow_tab_opened.connect(self._on_subworkflow_tab_opened)

        # Connect directly to the WorkflowTabWidget for the workflow_modified signal
        # (not forwarded through MainWindow)
        if hasattr(self._main_window, 'workflow_tab_widget'):
            tab_widget = self._main_window.workflow_tab_widget
            tab_widget.workflow_modified.connect(self._on_workflow_tab_modified)
            tab_widget.workflow_saved.connect(self._on_workflow_tab_saved)
            tab_widget.view_mode_changed.connect(self._on_workflow_tab_view_mode_changed)

        self._workflow_tabs_connected = True

    def _on_workflow_tab_changed(self, tab_id: str) -> None:
        """
        Handle active workflow tab change.

        Updates the ApplicationController to reference the new active tab's
        graph and graph_view for operations. Also updates the internal tab
        context tracking to maintain accurate state.

        Args:
            tab_id: The ID of the newly active tab.
        """
        if not self._main_window:
            return

        # Update the tab context tracking first
        self._update_tab_context(tab_id)

        # Get the tab directly for the most reliable graph reference
        tab_widget = self._main_window.workflow_tab_widget
        tab = tab_widget.get_tab(tab_id) if tab_widget else None

        new_graph = tab.graph if tab else None
        new_graph_view = tab.graph_view if tab else None

        if new_graph:
            # Update the internal graph reference
            # Note: This doesn't disconnect signals from the old graph
            # because we want to keep track of all graphs in tabs
            self._graph = new_graph
        elif tab:
            # Tab exists but has no graph — this shouldn't happen.
            # Log a warning for debugging but don't carry over the old graph.
            logger.warning(
                "_on_workflow_tab_changed: tab '%s' (id=%s) has graph=None; "
                "self._graph NOT updated (retains id=%s).",
                tab.name, tab_id, id(self._graph),
            )

        if new_graph_view:
            self._graph_view = new_graph_view

            # Update node properties panel with new graph reference
            if hasattr(self._main_window, 'node_properties_panel'):
                self._main_window.node_properties_panel.set_graph(new_graph)
                # Clear selection since we switched tabs
                self._main_window.node_properties_panel.on_selection_changed([])

            # Update minimap to show the new graph view
            if hasattr(self._main_window, 'minimap'):
                self._main_window.connect_minimap_to_graph_view(new_graph_view)

        # Log the tab context for debugging (when needed)
        if self._is_subworkflow_tab:
            context_msg = f"Switched to subworkflow tab: {self._current_tab_name}"
        else:
            context_msg = f"Switched to workflow tab: {self._current_tab_name}"

        # Show brief status message
        self._main_window.show_status_message(context_msg, 1500)

        # Highlight the active workflow in the library panel
        if hasattr(self._main_window, 'workflow_library'):
            tab_file = str(tab.file_path) if tab and tab.file_path else None
            self._main_window.workflow_library.set_active_workflow(tab_file)

        # Update dependency panel with new graph context
        self._update_dependency_panel()

    def _ensure_graph_synced(self) -> None:
        """
        Ensure self._graph and the current tab's graph are the same object.

        The controller's graph reference can diverge from the active tab's
        graph after tab switches, new-project, or open-project operations.
        Call this at the top of any method that reads or mutates the graph
        to guarantee consistency.

        The tab's graph is treated as authoritative (it is the graph the view
        was loaded with and that the scene widgets correspond to). When they
        differ, self._graph is updated to match the tab. As a fallback, if
        the tab's graph is None, self._graph is pushed to the tab.
        """
        if not self._main_window or not hasattr(self._main_window, 'workflow_tab_widget'):
            return

        tab_widget = self._main_window.workflow_tab_widget
        current_tab = tab_widget.get_current_tab() if tab_widget else None
        if current_tab is None:
            return

        if current_tab.graph is not self._graph:
            if current_tab.graph is not None:
                # Subworkflow tabs intentionally have their own independent
                # graph — never overwrite them with the parent graph.
                if current_tab.is_subworkflow:
                    logger.debug(
                        "_ensure_graph_synced: subworkflow tab has its own "
                        "graph (id=%s, %d nodes); updating self._graph.",
                        id(current_tab.graph),
                        len(current_tab.graph.nodes),
                    )
                    self._graph = current_tab.graph
                elif not current_tab.graph.nodes and self._graph.nodes:
                    # Root tab received a stale/new graph during creation.
                    # Push self._graph to the tab to repair the link.
                    logger.warning(
                        "_ensure_graph_synced: tab graph (id=%s, 0 nodes) "
                        "diverged from self._graph (id=%s, %d nodes). "
                        "Pushing self._graph to tab.",
                        id(current_tab.graph),
                        id(self._graph),
                        len(self._graph.nodes),
                    )
                    current_tab.graph = self._graph
                    # Reload the view to show the correct nodes
                    if current_tab.graph_view:
                        current_tab.graph_view.load_graph(self._graph)
                else:
                    # Tab has a valid graph with nodes — use it as source
                    # of truth.
                    logger.debug(
                        "_ensure_graph_synced: pulling tab graph (id=%s) "
                        "into self._graph (was id=%s).",
                        id(current_tab.graph),
                        id(self._graph),
                    )
                    self._graph = current_tab.graph
            else:
                # Tab's graph is None — push self._graph as a recovery,
                # but only for root tabs. For subworkflow tabs, this
                # indicates the graph hasn't been set up yet.
                if not current_tab.is_subworkflow:
                    logger.warning(
                        "_ensure_graph_synced: current tab graph is None! "
                        "Pushing self._graph (id=%s) to tab as fallback.",
                        id(self._graph),
                    )
                    current_tab.graph = self._graph

        tab_view = current_tab.graph_view
        if tab_view is not None and tab_view is not self._graph_view:
            self._graph_view = tab_view

    def _on_workflow_tab_created(self, tab_id: str) -> None:
        """
        Handle new workflow tab creation.

        This is called when a new workflow tab is created (either via New or
        when opening a subworkflow for editing).

        Args:
            tab_id: The ID of the newly created tab.
        """
        if self._main_window:
            tab = self._main_window.workflow_tab_widget.get_tab(tab_id)
            if tab:
                self._main_window.show_status_message(
                    f"Created new workflow tab: {tab.name}", 2000
                )

    def _on_workflow_tab_closed(self, tab_id: str) -> None:
        """
        Handle workflow tab closed.

        Cleans up any resources associated with the closed tab.

        Args:
            tab_id: The ID of the closed tab.
        """
        if self._main_window:
            # Check if the closed tab was the current one
            was_current = (self._current_tab_id == tab_id)

            self._main_window.show_status_message("Workflow tab closed", 2000)

            # If no tabs remain, create a new empty one
            if self._main_window.workflow_tab_widget.count() == 0:
                self.new_project()
                self.create_initial_workflow_tab()
            elif was_current:
                # Update context to the new active tab
                new_current_id = self._main_window.get_current_tab_id()
                if new_current_id:
                    self._update_tab_context(new_current_id)

    def _on_subworkflow_tab_opened(self, tab_id: str, parent_tab_id: str) -> None:
        """
        Handle subworkflow opened for editing in a new tab.

        This is triggered when a user double-clicks on a SubgraphNode to
        edit its internal graph. Updates the internal tab context to reflect
        the new subworkflow editing context.

        Args:
            tab_id: The ID of the new subworkflow tab.
            parent_tab_id: The ID of the parent workflow tab.
        """
        if self._main_window:
            tab = self._main_window.workflow_tab_widget.get_tab(tab_id)
            parent_tab = self._main_window.workflow_tab_widget.get_tab(parent_tab_id)

            if tab and parent_tab:
                # Update tab context since we're now in a subworkflow tab
                self._update_tab_context(tab_id)

                self._main_window.show_status_message(
                    f"Opened subworkflow '{tab.name}' from '{parent_tab.name}'", 3000
                )

    def _on_workflow_tab_modified(self, tab_id: str) -> None:
        """
        Handle workflow modification in a tab.

        Updates the modification state in the main window title if the
        modified tab is the current one.

        Args:
            tab_id: The ID of the modified tab.
        """
        if not self._main_window:
            return

        # Use the tracked current_tab_id for comparison
        if self._current_tab_id == tab_id:
            # Update the main window's modification state
            self._main_window.is_modified = True

    def _on_workflow_tab_saved(self, tab_id: str, file_path: str) -> None:
        """
        Handle workflow saved in a tab.

        Args:
            tab_id: The ID of the saved tab.
            file_path: The path where the workflow was saved.
        """
        if self._main_window:
            self._main_window.show_status_message(
                f"Workflow saved: {file_path}", 3000
            )

            # Update current file if this is the main/active tab
            # Use the tracked current_tab_id for comparison
            if self._current_tab_id == tab_id:
                self._current_file = Path(file_path)
                self._main_window.current_file = file_path
                self._main_window.is_modified = False

                # Also update the tab context to reflect the saved state
                self._update_tab_context(tab_id)

    def _on_workflow_tab_view_mode_changed(self, tab_id: str, view_mode: object) -> None:
        """
        Handle view mode change in a workflow tab.

        Args:
            tab_id: The ID of the tab whose view mode changed.
            view_mode: The new ViewMode enum value.
        """
        if self._main_window:
            from visualpython.ui.widgets.workflow_tab_widget import ViewMode

            mode_names = {
                ViewMode.EDIT: "Edit Mode",
                ViewMode.RUN: "Run/Debug Mode",
                ViewMode.COLLAPSED: "Collapsed View",
                ViewMode.EXPANDED: "Expanded View",
            }
            mode_name = mode_names.get(view_mode, str(view_mode))
            self._main_window.show_status_message(
                f"View mode: {mode_name}", 1500
            )

    def _on_workflow_open_requested(self, file_path: str) -> None:
        """
        Handle request to open a workflow from the library in a new tab.

        Args:
            file_path: Path to the workflow file.
        """
        try:
            graph = self._serializer.load(file_path)
        except SerializationError as e:
            error_msg = f"Failed to open project: {e}"
            self.error_occurred.emit(error_msg)
            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(self._main_window, "Open Error", error_msg)
            return

        if self._main_window:
            self._main_window.open_workflow_in_tab(file_path, graph)

    def _on_workflow_insert_requested(self, file_path: str) -> None:
        """
        Handle request to insert a workflow as a subgraph.

        Creates a reference-based SubgraphNode that points to the library file.

        Args:
            file_path: Path to the workflow file to insert.
        """
        from pathlib import Path
        from visualpython.nodes.models.subgraph_node import SubgraphNode

        # Ensure we operate on the current tab's graph
        self._ensure_graph_synced()

        try:
            path = Path(file_path)
            name = path.stem

            # Create a reference-based SubgraphNode pointing to the library file
            subgraph_node = SubgraphNode.create_reference(
                library_path=str(path),
                name=f"Subgraph: {name}",
            )

            # Add at center of view or default position
            if self._graph_view:
                viewport_center = self._graph_view.mapToScene(
                    self._graph_view.viewport().rect().center()
                )
                subgraph_node.position = Position(
                    x=viewport_center.x(),
                    y=viewport_center.y()
                )
            else:
                subgraph_node.position = Position(x=200, y=200)

            self._graph.add_node(subgraph_node)

            if self._graph_view:
                self._graph_view.graph_scene.add_node_widget(subgraph_node)

            self.node_added.emit(subgraph_node.id)
            self._mark_modified()
            if self._main_window:
                self._main_window.show_status_message(
                    f"Inserted subgraph: {subgraph_node.subgraph_name}", 2000
                )
        except Exception as e:
            self.error_occurred.emit(f"Failed to insert workflow as subgraph: {e}")

    def _on_view_mode_changed(self, mode: str) -> None:
        """
        Handle view mode change from the menu.

        Args:
            mode: The view mode ("edit", "run", "collapsed", "expanded").
        """
        if not self._graph_view:
            return

        scene = self._graph_view.graph_scene

        if mode == "edit":
            scene.set_view_mode_edit()
        elif mode == "run":
            scene.set_view_mode_run()
        elif mode == "collapsed":
            scene.set_view_mode_collapsed()
        elif mode == "expanded":
            scene.set_view_mode_expanded()

        if self._main_window:
            mode_names = {
                "edit": "Edit Mode",
                "run": "Run/Debug Mode",
                "collapsed": "Collapsed View",
                "expanded": "Expanded View",
            }
            self._main_window.show_status_message(
                f"View mode: {mode_names.get(mode, mode)}", 1500
            )

    def _on_save_to_workflow_library(self) -> None:
        """Handle request to save current workflow to the library."""
        if not self._main_window:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                None,
                "Error",
                "Main window not initialized. Cannot save to workflow library."
            )
            return

        if not hasattr(self._main_window, 'workflow_library'):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self._main_window,
                "Error",
                "Workflow library not available. Please restart the application."
            )
            return

        library = self._main_window.workflow_library

        # Serialize the current graph
        graph_data = self._serializer.serialize(self._graph)

        # Get workflow name from graph or prompt
        default_name = self._graph.name if self._graph.name else "My Workflow"

        from PyQt6.QtWidgets import QInputDialog, QDialog

        # Create a dialog to get workflow details
        name, ok = QInputDialog.getText(
            self._main_window,
            "Save to Workflow Library",
            "Enter workflow name:",
            text=default_name,
        )

        if not ok or not name:
            return

        description, ok = QInputDialog.getText(
            self._main_window,
            "Workflow Description",
            "Enter a description (optional):",
            text="",
        )

        if not ok:
            description = ""

        # Save using the library panel
        file_path = library.save_workflow_to_library(
            graph_data,
            name,
            description,
        )

        if file_path:
            self._main_window.show_status_message(
                f"Workflow saved to library: {name}", 3000
            )

    def _auto_save_subworkflow_to_library(
        self,
        node_id: str,
        name: str,
        embedded_graph_data: dict,
    ) -> None:
        """
        Automatically save a newly created subworkflow to the library.

        This method is called when the subworkflow_created signal is emitted,
        allowing users to reuse the subworkflow in other projects.

        Args:
            node_id: The ID of the created SubgraphNode.
            name: The name given to the subworkflow.
            embedded_graph_data: The serialized graph data of the subworkflow.
        """
        if not self._main_window:
            return

        if not hasattr(self._main_window, 'workflow_library'):
            return

        library = self._main_window.workflow_library

        # Use the library panel's dedicated method for saving embedded subgraph data
        # silent=True for auto-save (no dialogs), auto_rename=True to handle conflicts
        file_path = library.save_embedded_subgraph_to_library(
            embedded_graph_data=embedded_graph_data,
            name=name,
            description="Subworkflow created from selection",
            tags=["subworkflow", "auto-generated"],
            silent=True,
            auto_rename=True,
        )

        if file_path:
            # Show a status message about the auto-save
            self._main_window.show_status_message(
                f"Subworkflow '{name}' auto-saved to library", 3000
            )
        else:
            # Log the error but don't interrupt the user's workflow
            self.error_occurred.emit("Failed to auto-save subworkflow to library")

    def _on_workflow_version_changed(self, file_path: str, new_version: str) -> None:
        """
        Handle workflow version change from the library.

        Refreshes any SubgraphNodes in the current graph that reference
        the changed workflow file.

        Args:
            file_path: Path to the workflow file that was updated.
            new_version: The new version string.
        """
        if not self._graph:
            return

        from visualpython.nodes.models.subgraph_node import SubgraphNode

        for node in self._graph.nodes:
            if (isinstance(node, SubgraphNode) and
                node.is_reference_based and
                node.subgraph_path == file_path):
                node.refresh_from_reference()
                if self._graph_view:
                    widget = self._graph_view.graph_scene.get_node_widget(node.id)
                    if widget:
                        widget.update()

    def _on_library_refreshed(self) -> None:
        """
        Handle library refresh (file system changes detected).

        Checks all reference-based SubgraphNodes for version changes.
        """
        if not self._graph:
            return

        from visualpython.nodes.models.subgraph_node import SubgraphNode

        for node in self._graph.nodes:
            if isinstance(node, SubgraphNode) and node.is_reference_based:
                changed, new_version = node.check_version_changed()
                if changed:
                    node.refresh_from_reference()
                    if self._graph_view:
                        widget = self._graph_view.graph_scene.get_node_widget(node.id)
                        if widget:
                            widget.update()

    def _on_create_subworkflow_from_selection(self) -> None:
        """Handle request to create a subworkflow from selected nodes."""
        if not self._graph_view:
            return

        scene = self._graph_view.graph_scene
        selected_widgets = scene.get_selected_node_widgets()
        selected_nodes = [w.node.id for w in selected_widgets]

        if not selected_nodes:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self._main_window,
                "No Selection",
                "Please select some nodes first to create a subworkflow.",
            )
            return

        if len(selected_nodes) < 1:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self._main_window,
                "Not Enough Nodes",
                "Please select at least one node to create a subworkflow.",
            )
            return

        from PyQt6.QtWidgets import QInputDialog

        # Get subworkflow name
        name, ok = QInputDialog.getText(
            self._main_window,
            "Create Subworkflow",
            "Enter name for the subworkflow:",
            text="My Subworkflow",
        )

        if not ok or not name:
            return

        # Create subworkflow from selected nodes with custom naming
        self._create_subworkflow_from_nodes(selected_nodes, name)

    def _create_subworkflow_from_nodes(
        self,
        node_ids: List[str],
        name: str,
    ) -> None:
        """
        Create a SubgraphNode from selected nodes.

        This method:
        1. Collects the selected nodes and their internal connections
        2. Identifies external connections (inputs/outputs)
        3. Creates SubgraphInput/SubgraphOutput nodes for external connections
        4. Creates a SubgraphNode containing all the selected nodes
        5. Replaces the selected nodes with the SubgraphNode
        6. Reconnects external connections to the SubgraphNode

        Args:
            node_ids: List of node IDs to include in the subworkflow.
            name: Name for the subworkflow.
        """
        from visualpython.nodes.models.subgraph_node import SubgraphNode
        from visualpython.nodes.models.base_node import Position
        import json

        # Ensure self._graph is in sync with the current tab's graph
        self._ensure_graph_synced()

        # Get the selected nodes, filtering out Start/End nodes which must
        # remain in the root graph for execution to work
        nodes_to_include = []
        excluded_types = {"start", "end"}
        for node_id in node_ids:
            node = self._graph.get_node(node_id)
            if node:
                if node.node_type in excluded_types:
                    logger.debug(
                        "Excluding %s node '%s' from subworkflow (must stay in root graph)",
                        node.node_type, node.name,
                    )
                    continue
                nodes_to_include.append(node)

        if not nodes_to_include:
            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self._main_window,
                    "Cannot Create Subworkflow",
                    "No eligible nodes selected. Start and End nodes cannot "
                    "be moved into a subworkflow.",
                )
            return

        # Find the center position of selected nodes
        center_x = sum(n.position.x for n in nodes_to_include) / len(nodes_to_include)
        center_y = sum(n.position.y for n in nodes_to_include) / len(nodes_to_include)

        # Identify internal and external connections
        # Use only included node IDs (after filtering out Start/End)
        node_id_set = {n.id for n in nodes_to_include}
        internal_connections = []
        external_input_connections = []  # Connections coming INTO the selection
        external_output_connections = []  # Connections going OUT of the selection

        for conn in self._graph.get_all_connections():
            src_in = conn.source_node_id in node_id_set
            tgt_in = conn.target_node_id in node_id_set

            if src_in and tgt_in:
                # Internal connection
                internal_connections.append(conn)
            elif src_in and not tgt_in:
                # Output connection (from selection to outside)
                external_output_connections.append(conn)
            elif not src_in and tgt_in:
                # Input connection (from outside to selection)
                external_input_connections.append(conn)

        # Helper to check if a connection is a FLOW connection
        def _is_flow_input(conn) -> bool:
            from visualpython.nodes.models.port import PortType
            node = self._graph.get_node(conn.target_node_id)
            if node:
                port = node.get_input_port(conn.target_port_name)
                return port is not None and port.port_type == PortType.FLOW
            return False

        def _is_flow_output(conn) -> bool:
            from visualpython.nodes.models.port import PortType
            node = self._graph.get_node(conn.source_node_id)
            if node:
                port = node.get_output_port(conn.source_port_name)
                return port is not None and port.port_type == PortType.FLOW
            return False

        # Separate FLOW and DATA connections
        flow_input_connections = [c for c in external_input_connections if _is_flow_input(c)]
        data_input_connections = [c for c in external_input_connections if not _is_flow_input(c)]
        flow_output_connections = [c for c in external_output_connections if _is_flow_output(c)]
        data_output_connections = [c for c in external_output_connections if not _is_flow_output(c)]

        # Build the subgraph data
        subgraph_nodes = []
        subgraph_connections = []
        input_mappings = {}
        output_mappings = {}

        # Calculate position bounds for selected nodes
        min_x = min(n.position.x for n in nodes_to_include)
        min_y = min(n.position.y for n in nodes_to_include)
        max_x = max(n.position.x for n in nodes_to_include) - min_x + 300

        # Add SubgraphInput nodes for DATA external inputs only
        # FLOW connections use the SubgraphNode's built-in exec_in/exec_out
        input_port_index = 0
        input_node_map = {}  # Maps (target_node_id, target_port) -> (input_node_id, port_name)

        for conn in data_input_connections:
            key = (conn.target_node_id, conn.target_port_name)
            if key not in input_node_map:
                input_node_id = f"subgraph_input_{input_port_index}"
                port_name = f"input_{input_port_index}"

                subgraph_nodes.append({
                    "id": input_node_id,
                    "type": "subgraph_input",
                    "name": f"Input: {conn.target_port_name}",
                    "position": {"x": -200, "y": input_port_index * 100},
                    "properties": {"port_name": port_name},
                })

                input_mappings[port_name] = input_node_id
                input_node_map[key] = (input_node_id, port_name)
                input_port_index += 1

        # Track FLOW input targets for internal flow entry points
        flow_input_targets = {}  # Maps (target_node_id, target_port) -> conn
        for conn in flow_input_connections:
            flow_input_targets[(conn.target_node_id, conn.target_port_name)] = conn

        # Add the selected nodes (preserving their current names, positions adjusted)
        # Users can edit node names directly by double-clicking on the node title
        for node in nodes_to_include:
            node_data = node.to_dict()
            # Adjust position relative to the subgraph
            node_data["position"]["x"] -= min_x - 100
            node_data["position"]["y"] -= min_y
            subgraph_nodes.append(node_data)

        # Add SubgraphOutput nodes for DATA external outputs only
        output_port_index = 0
        output_node_map = {}  # Maps (source_node_id, source_port) -> (output_node_id, port_name)

        for conn in data_output_connections:
            key = (conn.source_node_id, conn.source_port_name)
            if key not in output_node_map:
                output_node_id = f"subgraph_output_{output_port_index}"
                port_name = f"output_{output_port_index}"

                subgraph_nodes.append({
                    "id": output_node_id,
                    "type": "subgraph_output",
                    "name": f"Output: {conn.source_port_name}",
                    "position": {"x": max_x, "y": output_port_index * 100},
                    "properties": {"port_name": port_name},
                })

                output_mappings[port_name] = output_node_id
                output_node_map[key] = (output_node_id, port_name)
                output_port_index += 1

        # Add internal connections
        for conn in internal_connections:
            subgraph_connections.append({
                "source_node_id": conn.source_node_id,
                "source_port_name": conn.source_port_name,
                "target_node_id": conn.target_node_id,
                "target_port_name": conn.target_port_name,
            })

        # Add connections from SubgraphInput nodes to internal nodes (DATA only)
        for conn in data_input_connections:
            key = (conn.target_node_id, conn.target_port_name)
            input_node_id, _ = input_node_map[key]
            subgraph_connections.append({
                "source_node_id": input_node_id,
                "source_port_name": "value",
                "target_node_id": conn.target_node_id,
                "target_port_name": conn.target_port_name,
            })

        # Add connections from internal nodes to SubgraphOutput nodes (DATA only)
        for conn in data_output_connections:
            key = (conn.source_node_id, conn.source_port_name)
            output_node_id, _ = output_node_map[key]
            subgraph_connections.append({
                "source_node_id": conn.source_node_id,
                "source_port_name": conn.source_port_name,
                "target_node_id": output_node_id,
                "target_port_name": "value",
            })

        # Build the embedded graph data
        # Store flow entry points: internal nodes whose exec_in was externally connected
        flow_entry_points = [
            {"node_id": conn.target_node_id, "port_name": conn.target_port_name}
            for conn in flow_input_connections
        ]
        # Store flow exit points: internal nodes whose exec_out was externally connected
        flow_exit_points = [
            {"node_id": conn.source_node_id, "port_name": conn.source_port_name}
            for conn in flow_output_connections
        ]

        embedded_graph_data = {
            "nodes": subgraph_nodes,
            "connections": subgraph_connections,
            "metadata": {
                "name": name,
                "flow_entry_points": flow_entry_points,
                "flow_exit_points": flow_exit_points,
            },
        }

        # Save to library first so we can create a reference-based SubgraphNode
        library_file_path = None
        if self._main_window and hasattr(self._main_window, 'workflow_library'):
            library = self._main_window.workflow_library
            library_file_path = library.save_embedded_subgraph_to_library(
                embedded_graph_data=embedded_graph_data,
                name=name,
                description="Subworkflow created from selection",
                tags=["subworkflow", "auto-generated"],
                silent=True,
                auto_rename=True,
            )

        if library_file_path:
            # Create a reference-based SubgraphNode pointing to the library file
            subgraph_node = SubgraphNode.create_reference(
                library_path=str(library_file_path),
                name=f"Subgraph: {name}",
            )
            subgraph_node.position = Position(x=center_x, y=center_y)
        else:
            # Fallback: create legacy embedded SubgraphNode if library save failed
            subgraph_node = SubgraphNode(name=f"Subgraph: {name}")
            subgraph_node._subgraph_name = name
            subgraph_node._embedded_graph_data = embedded_graph_data
            subgraph_node._input_mappings = input_mappings
            subgraph_node._output_mappings = output_mappings
            subgraph_node._subgraph_loaded = True
            subgraph_node.position = Position(x=center_x, y=center_y)
            subgraph_node.sync_ports_from_graph()

        # Now perform the replacement:
        # 1. Remove external connections
        for conn in external_input_connections + external_output_connections:
            self._graph.disconnect(
                conn.source_node_id,
                conn.source_port_name,
                conn.target_node_id,
                conn.target_port_name,
            )

        # 2. Remove the included nodes (and their internal connections)
        # Only remove nodes that were actually included (Start/End were filtered out)
        for node in nodes_to_include:
            if self._graph.get_node(node.id):
                self._graph.remove_node(node.id)

        # 3. Add the SubgraphNode
        self._graph.add_node(subgraph_node)

        # 4. Reconnect external FLOW inputs to SubgraphNode's built-in exec_in
        for conn in flow_input_connections:
            self._graph.connect(
                conn.source_node_id,
                conn.source_port_name,
                subgraph_node.id,
                "exec_in",
            )

        # 5. Reconnect external DATA inputs to SubgraphNode's dynamic ports
        for conn in data_input_connections:
            key = (conn.target_node_id, conn.target_port_name)
            _, port_name = input_node_map[key]
            self._graph.connect(
                conn.source_node_id,
                conn.source_port_name,
                subgraph_node.id,
                port_name,
            )

        # 6. Reconnect external FLOW outputs from SubgraphNode's built-in exec_out
        for conn in flow_output_connections:
            self._graph.connect(
                subgraph_node.id,
                "exec_out",
                conn.target_node_id,
                conn.target_port_name,
            )

        # 7. Reconnect external DATA outputs from SubgraphNode's dynamic ports
        for conn in data_output_connections:
            key = (conn.source_node_id, conn.source_port_name)
            _, port_name = output_node_map[key]
            self._graph.connect(
                subgraph_node.id,
                port_name,
                conn.target_node_id,
                conn.target_port_name,
            )

        # Incrementally update the scene instead of load_graph to avoid
        # the clear_node_widgets → node_widget_removed signal cascade
        # that empties the graph model.
        if self._graph_view:
            scene = self._graph_view.graph_scene
            # Block signals to prevent auto-sync / parent-node tracking
            # from interfering during the incremental update.
            scene.blockSignals(True)
            try:
                # 1. Remove connection widgets for all removed connections
                all_removed_connections = (
                    external_input_connections
                    + external_output_connections
                    + internal_connections
                )
                for conn in all_removed_connections:
                    scene.remove_connection_widget_by_connection(conn)

                # 2. Remove node widgets for nodes moved into the subworkflow
                for node in nodes_to_include:
                    if not scene.remove_node_widget(node.id):
                        logger.warning(
                            "_create_subworkflow_from_nodes: failed to remove "
                            "widget for node '%s' (id=%s) from scene",
                            node.name, node.id,
                        )

                # 3. Add the SubgraphNode widget
                scene.add_node_widget(subgraph_node)

                # 4. Add connection widgets for the new connections to SubgraphNode
                for conn in self._graph.connections:
                    if (conn.source_node_id == subgraph_node.id
                            or conn.target_node_id == subgraph_node.id):
                        scene.add_connection_widget(conn)
            finally:
                scene.blockSignals(False)

        # Save root graph reference before open_subworkflow triggers tab
        # switching which reassigns self._graph via _on_workflow_tab_changed.
        saved_graph = self._graph
        saved_graph_view = self._graph_view

        if self._main_window:
            self._main_window.show_status_message(
                f"Created subworkflow '{name}' with {len(nodes_to_include)} nodes", 3000
            )
            self._main_window.is_modified = True

        # Emit signal so other components (e.g., workflow library) can respond
        self.subworkflow_created.emit(subgraph_node.id, name, embedded_graph_data)

        # Open the newly created subworkflow in a new tab, but keep the main tab active
        # so the user can see the condensed SubgraphNode in the main workflow
        if self._main_window and self._main_window.workflow_tab_widget:
            parent_tab_id = self._main_window.workflow_tab_widget.get_current_tab_id()
            if parent_tab_id:
                self._main_window.workflow_tab_widget.open_subworkflow(
                    parent_tab_id=parent_tab_id,
                    subgraph_node_id=subgraph_node.id,
                    subgraph_data=embedded_graph_data if not library_file_path else None,
                    name=name,
                    library_file_path=str(library_file_path) if library_file_path else None,
                )
                # Switch back to the parent tab to show the SubgraphNode
                # The user can double-click the SubgraphNode to edit the subworkflow
                self._main_window.workflow_tab_widget._switch_to_tab(parent_tab_id)

        # Restore root graph reference in case tab switching didn't properly
        # restore it (e.g. if _on_workflow_tab_changed set self._graph to
        # the subworkflow graph during the open_subworkflow → setCurrentIndex
        # call chain).
        self._graph = saved_graph
        self._graph_view = saved_graph_view

    def get_serialized_graph(self) -> dict:
        """
        Get the serialized representation of the current graph.

        Returns:
            Dictionary containing the serialized graph data.
        """
        return self._serializer.serialize(self._graph)

    def _update_node_widget_state(self, node: "BaseNode") -> None:
        """
        Update the visual state of a node widget during execution.

        Args:
            node: The node whose widget should be updated.
        """
        if self._graph_view:
            scene = self._graph_view.graph_scene
            widget = scene.get_node_widget(node.id)
            if widget:
                widget.update_execution_state()

    def _update_all_node_widgets(self) -> None:
        """Update the visual state of all node widgets."""
        if self._graph_view:
            scene = self._graph_view.graph_scene
            for widget in scene.get_all_node_widgets():
                widget.update_execution_state()

    def _on_node_execution_start(self, node: "BaseNode") -> None:
        """
        Callback when a node starts executing.

        Args:
            node: The node that started executing.
        """
        self._execution_state_manager.set_current_node(node.id)
        self._update_node_widget_state(node)

    def _on_node_execution_complete(self, node: "BaseNode", outputs: Dict[str, Any]) -> None:
        """
        Callback when a node completes execution.

        Args:
            node: The node that completed.
            outputs: The outputs from the node execution.
        """
        self._execution_state_manager.increment_progress()
        self._update_node_widget_state(node)

    def _on_node_execution_error(self, node: "BaseNode", error: Exception) -> None:
        """
        Callback when a node encounters an error.

        Args:
            node: The node that had an error.
            error: The exception that occurred.
        """
        logger.error("Node '%s' (%s) execution error: %s", node.name, node.id, error)
        self._update_node_widget_state(node)

    def _get_root_graph(self) -> "Graph":
        """
        Get the root (top-level) workflow graph for execution.

        When the active tab is a subworkflow, this resolves to the root
        workflow's graph so that execution always starts from the Start node.

        Returns:
            The root graph, or self._graph if no tab widget is available.
        """
        if (self._main_window and
                hasattr(self._main_window, 'workflow_tab_widget') and
                self._current_tab_id):
            tab_widget = self._main_window.workflow_tab_widget
            root_tab = tab_widget.get_root_tab(self._current_tab_id)
            # Use 'is not None' instead of truthiness because Graph.__len__
            # returns 0 for empty graphs, making them falsy.
            if root_tab and root_tab.graph is not None:
                logger.debug(
                    "_get_root_graph: using root_tab.graph (id=%s, %d nodes) "
                    "for tab_id=%s",
                    id(root_tab.graph), len(root_tab.graph.nodes),
                    self._current_tab_id,
                )
                return root_tab.graph
        logger.debug(
            "_get_root_graph: falling back to self._graph (id=%s, %d nodes)",
            id(self._graph), len(self._graph.nodes),
        )
        return self._graph

    def run_graph(self, step_mode: bool = False) -> None:
        """
        Execute the root workflow graph in a background thread.

        Always executes the root (top-level) graph, even if a subworkflow
        tab is currently active. This ensures execution starts from the
        Start node and subgraphs are executed as part of the main flow.

        Args:
            step_mode: If True, enables step-through execution that pauses
                      at each node for debugging.
        """
        # Don't start if already running
        if self._execution_thread is not None and self._execution_thread.isRunning():
            return

        # Ensure the controller graph and tab graph are in sync before execution
        self._ensure_graph_synced()

        # Always execute the root graph (which contains the Start node)
        execution_graph = self._get_root_graph()

        # Safety check: if the root tab's graph has diverged and is empty
        # but self._graph has nodes, the references have diverged — use
        # self._graph and push it to the tab to repair the link.
        if not execution_graph.nodes and self._graph.nodes:
            logger.warning(
                "run_graph: root graph (id=%s) has 0 nodes but "
                "self._graph (id=%s) has %d nodes — references diverged! "
                "Using self._graph for execution.",
                id(execution_graph), id(self._graph),
                len(self._graph.nodes),
            )
            execution_graph = self._graph
            # Also repair the tab's graph reference
            if (self._main_window and
                    hasattr(self._main_window, 'workflow_tab_widget')):
                tab_widget = self._main_window.workflow_tab_widget
                root_tab = tab_widget.get_root_tab(self._current_tab_id)
                if root_tab:
                    root_tab.graph = self._graph
        node_types = [n.node_type for n in execution_graph.nodes]
        logger.info(
            "run_graph: executing graph (id=%s) with %d nodes, types=%s",
            id(execution_graph), len(execution_graph.nodes), node_types,
        )

        # Check if step mode is enabled from the state manager
        use_step_mode = step_mode or self._execution_state_manager.is_step_mode

        # Update execution state to RUNNING
        total_nodes = len(execution_graph.nodes)
        self._execution_state_manager.start_execution(total_nodes)

        if self._main_window:
            if use_step_mode:
                self._main_window.show_status_message("Starting step-through execution...")
            else:
                self._main_window.show_status_message("Running...")
            self._main_window.console_execution_started()
            self._main_window.variable_panel_execution_started()
            self._main_window.summary_panel_execution_started()

        # Reset all node widgets to IDLE state before execution starts
        execution_graph.reset_execution_state()
        self._update_all_node_widgets()

        # Create execution thread with step mode
        self._execution_thread = ExecutionThread(
            execution_graph,
            step_mode=use_step_mode,
            parent=self,
        )

        # Connect thread signals
        self._execution_thread.execution_finished.connect(self._on_execution_finished)
        self._execution_thread.node_started.connect(self._on_node_execution_start)
        self._execution_thread.node_completed.connect(self._on_node_execution_complete)
        self._execution_thread.node_error.connect(self._on_node_execution_error)
        self._execution_thread.step_paused.connect(self._on_step_paused)

        # Connect stdout/stderr signals to console
        if self._main_window:
            self._execution_thread.stdout_received.connect(
                self._main_window.get_stdout_callback()
            )
            self._execution_thread.stderr_received.connect(
                self._main_window.get_stderr_callback()
            )

        # Start execution in background thread
        self._execution_thread.start()

    def _on_execution_finished(self, result: ExecutionResult) -> None:
        """
        Handle execution completion from the background thread.

        Args:
            result: The execution result.
        """
        # Clean up thread reference
        if self._execution_thread:
            self._execution_thread.wait()  # Ensure thread has fully finished
            self._execution_thread.deleteLater()
            self._execution_thread = None

        # Handle the result based on status
        logger.info("Execution finished with status: %s", result.status.name)
        if result.status == ExecutionStatus.CANCELLED:
            # Execution was cancelled by user
            message = "Execution stopped by user"
            self._execution_state_manager.cancel_execution()
            self.execution_finished.emit(False, message)
            if self._main_window:
                self._main_window.execution_finished()
                self._main_window.console_execution_finished(False, message)
                self._main_window.variable_panel_execution_finished()
                self._main_window.update_summary_panel_from_result(result)
                self._main_window.show_status_message(message, 3000)
        elif result.succeeded:
            duration_ms = result.execution_time_ms or 0
            message = f"Execution completed in {duration_ms:.0f}ms"
            self._execution_state_manager.finish_execution(success=True)
            self.execution_finished.emit(True, message)
            if self._main_window:
                self._main_window.execution_finished()
                self._main_window.console_execution_finished(True, message)
                self._main_window.variable_panel_execution_finished()
                self._main_window.update_summary_panel_from_result(result)
                self._main_window.show_status_message(message, 5000)
        else:
            error_message = result.error or "Unknown error"
            logger.error("Execution failed: %s", error_message)
            if result.error_report:
                logger.error("Error report: %s", result.error_report.format_user_message())
            self._execution_state_manager.finish_execution(success=False, error=error_message)
            self.execution_finished.emit(False, error_message)
            if self._main_window:
                self._main_window.execution_finished()
                self._main_window.console_execution_finished(False, error_message)
                self._main_window.variable_panel_execution_finished()
                self._main_window.update_summary_panel_from_result(result)
                self._main_window.show_status_message(
                    f"Execution failed: {error_message}", 5000
                )
                # Show detailed error dialog for failures
                from visualpython.ui.dialogs import ExecutionErrorDialog
                if result.error_report:
                    ExecutionErrorDialog.show_error(
                        self._main_window,
                        error_report=result.error_report,
                    )
                else:
                    ExecutionErrorDialog.show_error(
                        self._main_window,
                        message=error_message,
                        exception_type="Execution Error",
                    )

        # Update all node widgets to show final execution state
        self._update_all_node_widgets()

    def stop_execution(self) -> None:
        """
        Stop the current execution if running.

        Cancels any active execution thread and updates UI state.
        The cancellation is handled cooperatively - the execution engine
        checks for cancellation at key points during execution.
        """
        if self._execution_thread and self._execution_thread.isRunning():
            # Signal cancellation to the execution engine
            self._execution_thread.cancel()
            # Note: The thread will finish and call _on_execution_finished
            # which handles the UI updates and cleanup

    # Step-through execution handlers

    def _on_step_mode_toggled(self, enabled: bool) -> None:
        """
        Handle step mode toggle from the UI.

        Args:
            enabled: Whether step mode is now enabled.
        """
        if enabled:
            self._execution_state_manager.enable_step_mode()
        else:
            self._execution_state_manager.disable_step_mode()

    def _on_step_requested(self) -> None:
        """Handle step next request from the UI."""
        if self._execution_thread and self._execution_thread.isRunning():
            self._execution_thread.step()
            if self._main_window:
                self._main_window.show_status_message("Stepping to next node...")

    def _on_continue_requested(self) -> None:
        """Handle continue request from the UI (exit step mode for current run)."""
        if self._execution_thread and self._execution_thread.isRunning():
            self._execution_thread.continue_execution()
            if self._main_window:
                self._main_window.show_status_message("Continuing execution...")

    def _on_step_paused(self, node: "BaseNode") -> None:
        """
        Handle step pause event when execution pauses at a node.

        Args:
            node: The node where execution paused.
        """
        # Update state manager
        self._execution_state_manager.on_step_paused(node.id, node.name)

        # Update UI
        if self._main_window:
            self._main_window.on_step_paused(node.name)
            # Show the variable inspector to enable runtime state inspection
            self._main_window.show_variable_inspector()

        # Highlight the current node
        self._highlight_paused_node(node)

    def _highlight_paused_node(self, node: "BaseNode") -> None:
        """
        Visually highlight a node that is paused for step-through.

        Args:
            node: The node to highlight.
        """
        if self._graph_view:
            scene = self._graph_view.graph_scene
            widget = scene.get_node_widget(node.id)
            if widget:
                # Update the execution state to show it's paused
                widget.update_execution_state()
                # Scroll to make the node visible
                self._graph_view.centerOn(widget)

    def _on_navigate_to_node_requested(self, node_id: str) -> None:
        """
        Handle navigation request to a specific node.

        This is triggered when clicking an error in the execution summary panel.
        It pans the view to center on the node and selects it.

        Args:
            node_id: The ID of the node to navigate to.
        """
        if not self._graph_view:
            return

        scene = self._graph_view.graph_scene
        widget = scene.get_node_widget(node_id)
        if widget:
            # Select the node (clears previous selection and selects this one)
            self._graph_view.select_nodes_by_ids([node_id])
            # Pan the view to center on the node
            self._graph_view.centerOn(widget)
            # Show status message
            if self._main_window:
                node = self._graph.get_node(node_id) if self._graph else None
                node_name = node.name if node else node_id
                self._main_window.show_status_message(
                    f"Navigated to node: {node_name}", 2000
                )

    def step(self) -> None:
        """Public method to execute the next step in step-through mode."""
        self._on_step_requested()

    def continue_execution_from_step(self) -> None:
        """Public method to continue execution without stepping."""
        self._on_continue_requested()

    def enable_step_mode(self) -> None:
        """Enable step-through execution mode."""
        self._execution_state_manager.enable_step_mode()
        if self._main_window:
            self._main_window.set_step_mode(True)

    def disable_step_mode(self) -> None:
        """Disable step-through execution mode."""
        self._execution_state_manager.disable_step_mode()
        if self._main_window:
            self._main_window.set_step_mode(False)

    @property
    def is_step_mode_enabled(self) -> bool:
        """Check if step mode is currently enabled."""
        return self._execution_state_manager.is_step_mode

    def export_as_python(self, file_path: str) -> bool:
        """
        Export the current graph as a standalone Python script.

        Compiles the node graph to Python code and saves it to the specified file.
        This allows users to inspect the generated code or run it independently.

        Args:
            file_path: Path to save the Python script to.

        Returns:
            True if export was successful, False otherwise.
        """
        try:
            # Generate Python code from the graph
            generator = CodeGenerator(self._graph)
            result = generator.generate()

            if not result.success:
                error_msg = "Failed to generate Python code:\n" + "\n".join(result.errors)
                self.error_occurred.emit(error_msg)

                if self._main_window:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.critical(
                        self._main_window,
                        "Export Error",
                        error_msg,
                    )

                return False

            # Write the generated code to the file
            path = Path(file_path)
            path.write_text(result.code, encoding="utf-8")

            if self._main_window:
                self._main_window.show_status_message(
                    f"Exported to: {file_path}", 5000
                )

                # Show warnings if any
                if result.warnings:
                    from PyQt6.QtWidgets import QMessageBox
                    warning_msg = "Export completed with warnings:\n" + "\n".join(result.warnings)
                    QMessageBox.warning(
                        self._main_window,
                        "Export Warnings",
                        warning_msg,
                    )

            return True

        except GenerationError as e:
            error_msg = f"Code generation error: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Export Error",
                    error_msg,
                )

            return False

        except OSError as e:
            error_msg = f"Failed to write file: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Export Error",
                    error_msg,
                )

            return False

        except Exception as e:
            error_msg = f"Unexpected error during export: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Export Error",
                    error_msg,
                )

            return False

    # Clipboard Operations

    @property
    def clipboard_manager(self) -> ClipboardManager:
        """Get the clipboard manager."""
        return self._clipboard_manager

    def copy_selected_nodes(self) -> int:
        """
        Copy the currently selected nodes to the clipboard.

        Returns:
            Number of nodes copied.
        """
        selected_ids = self.get_selected_node_ids()
        if not selected_ids:
            if self._main_window:
                self._main_window.show_status_message("No nodes selected to copy", 2000)
            return 0

        count = self._clipboard_manager.copy_nodes(self._graph, selected_ids)

        if self._main_window:
            if count > 0:
                self._main_window.show_status_message(
                    f"Copied {count} node{'s' if count > 1 else ''}", 2000
                )
            else:
                self._main_window.show_status_message("Failed to copy nodes", 2000)

        return count

    def cut_selected_nodes(self) -> int:
        """
        Cut the currently selected nodes (copy and delete).

        Returns:
            Number of nodes cut.
        """
        selected_ids = self.get_selected_node_ids()
        if not selected_ids:
            if self._main_window:
                self._main_window.show_status_message("No nodes selected to cut", 2000)
            return 0

        count = self._clipboard_manager.cut_nodes(
            self._graph,
            selected_ids,
            self._on_node_delete_requested,
        )

        if self._main_window:
            if count > 0:
                self._main_window.show_status_message(
                    f"Cut {count} node{'s' if count > 1 else ''}", 2000
                )
                self._mark_modified()
            else:
                self._main_window.show_status_message("Failed to cut nodes", 2000)

        return count

    def paste_nodes(self) -> List[str]:
        """
        Paste nodes from the clipboard into the graph.

        Returns:
            List of newly created node IDs.
        """
        if not self._clipboard_manager.has_clipboard_content():
            if self._main_window:
                self._main_window.show_status_message("Clipboard is empty", 2000)
            return []

        new_node_ids = self._clipboard_manager.paste_nodes(
            self._graph,
            self._add_pasted_node,
            self._add_pasted_connection,
        )

        if new_node_ids:
            self._mark_modified()

            # Select the newly pasted nodes
            if self._graph_view:
                self._graph_view.clear_selection()
                self._graph_view.select_nodes_by_ids(new_node_ids)

            if self._main_window:
                count = len(new_node_ids)
                self._main_window.show_status_message(
                    f"Pasted {count} node{'s' if count > 1 else ''}", 2000
                )
        else:
            if self._main_window:
                self._main_window.show_status_message("Failed to paste nodes", 2000)

        return new_node_ids

    def duplicate_selected_nodes(self) -> List[str]:
        """
        Duplicate the currently selected nodes.

        Creates copies of selected nodes with their internal connections
        at an offset position. This is a quick alternative to copy+paste.

        Returns:
            List of newly created node IDs.
        """
        selected_ids = self.get_selected_node_ids()
        if not selected_ids:
            if self._main_window:
                self._main_window.show_status_message("No nodes selected to duplicate", 2000)
            return []

        command = DuplicateNodesCommand(
            graph=self._graph,
            node_ids=selected_ids,
            registry=self._registry,
            add_node_callback=self._add_node_widget,
            remove_node_callback=self._remove_node_widget,
            add_connection_callback=self._add_duplicated_connection,
            remove_connection_callback=self._remove_connection_by_model,
        )

        if self._undo_redo_manager.execute(command):
            new_node_ids = command.new_node_ids
            self._mark_modified()

            # Select the newly duplicated nodes
            if self._graph_view and new_node_ids:
                self._graph_view.clear_selection()
                self._graph_view.select_nodes_by_ids(new_node_ids)

            if self._main_window:
                count = len(new_node_ids)
                self._main_window.show_status_message(
                    f"Duplicated {count} node{'s' if count > 1 else ''}", 2000
                )

            return new_node_ids
        else:
            if self._main_window:
                self._main_window.show_status_message("Failed to duplicate nodes", 2000)
            return []

    def _add_duplicated_connection(self, connection: "Connection") -> None:
        """
        Add a visual widget for a duplicated connection and update port states.

        Args:
            connection: The connection to create a widget for.
        """
        if self._graph_view:
            scene = self._graph_view.graph_scene
            scene.add_connection_widget(connection)

            # Update port widget visual states
            source_node_widget = scene.get_node_widget(connection.source_node_id)
            target_node_widget = scene.get_node_widget(connection.target_node_id)

            if source_node_widget:
                source_port_widget = source_node_widget.get_output_port_widget(
                    connection.source_port_name
                )
                if source_port_widget:
                    source_port_widget.is_connected = True

            if target_node_widget:
                target_port_widget = target_node_widget.get_input_port_widget(
                    connection.target_port_name
                )
                if target_port_widget:
                    target_port_widget.is_connected = True

    def _add_pasted_node(self, node: BaseNode) -> None:
        """
        Add a pasted node to the graph and create its widget.

        Args:
            node: The node to add.
        """
        self._graph.add_node(node)

        # Create the visual widget for the node
        if self._graph_view:
            self._graph_view.graph_scene.add_node_widget(node)

        self.node_added.emit(node.id)

    def _add_pasted_connection(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> None:
        """
        Add a connection between pasted nodes.

        Args:
            source_node_id: ID of the source node.
            source_port_name: Name of the source port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target port.
        """
        try:
            # Create the connection in the data model
            connection = self._graph.connect(
                source_node_id,
                source_port_name,
                target_node_id,
                target_port_name,
                validate=False,  # Skip validation for pasted connections
            )

            # Create the visual widget for the connection
            if self._graph_view:
                scene = self._graph_view.graph_scene
                scene.add_connection_widget(connection)

                # Update port widget visual states
                source_node_widget = scene.get_node_widget(source_node_id)
                target_node_widget = scene.get_node_widget(target_node_id)

                if source_node_widget:
                    source_port_widget = source_node_widget.get_output_port_widget(
                        source_port_name
                    )
                    if source_port_widget:
                        source_port_widget.is_connected = True

                if target_node_widget:
                    target_port_widget = target_node_widget.get_input_port_widget(
                        target_port_name
                    )
                    if target_port_widget:
                        target_port_widget.is_connected = True

        except Exception as e:
            # Log error but don't fail the paste operation
            self.error_occurred.emit(f"Failed to recreate connection: {e}")

    # Undo/Redo Operations

    @property
    def undo_redo_manager(self) -> UndoRedoManager:
        """Get the undo/redo manager."""
        return self._undo_redo_manager

    def undo(self) -> bool:
        """
        Undo the last operation.

        Returns:
            True if undo was successful.
        """
        if self._undo_redo_manager.undo():
            self._mark_modified()
            if self._main_window:
                self._main_window.show_status_message(
                    f"Undid: {self._undo_redo_manager.redo_text.replace('Redo ', '')}", 2000
                )
            return True
        return False

    def redo(self) -> bool:
        """
        Redo the last undone operation.

        Returns:
            True if redo was successful.
        """
        if self._undo_redo_manager.redo():
            self._mark_modified()
            if self._main_window:
                self._main_window.show_status_message(
                    f"Redid: {self._undo_redo_manager.undo_text.replace('Undo ', '')}", 2000
                )
            return True
        return False

    @property
    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self._undo_redo_manager.can_undo

    @property
    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self._undo_redo_manager.can_redo

    def clear_undo_history(self) -> None:
        """Clear the undo/redo history."""
        self._undo_redo_manager.clear()

    # Variable Persistence Operations

    def save_variables(self, file_path: str) -> bool:
        """
        Save global variables to a JSON file.

        Args:
            file_path: Path to save the variables to.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self._variable_serializer.save(file_path)
            self.variables_saved.emit(file_path)

            if self._main_window:
                self._main_window.show_status_message(
                    f"Variables saved to: {file_path}", 5000
                )

            return True

        except SerializationError as e:
            error_msg = f"Failed to save variables: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Save Variables Error",
                    error_msg,
                )

            return False

    def load_variables(self, file_path: str, merge: bool = False) -> bool:
        """
        Load global variables from a JSON file.

        Args:
            file_path: Path to load the variables from.
            merge: If True, merge with existing variables.
                   If False (default), replace existing variables.

        Returns:
            True if successful, False otherwise.
        """
        try:
            count = self._variable_serializer.load(file_path, merge=merge)
            self.variables_loaded.emit(file_path, count)

            if self._main_window:
                self._main_window.show_status_message(
                    f"Loaded {count} variables from: {file_path}", 5000
                )
                # Refresh the variable panel to show loaded variables
                self._main_window.variable_panel_execution_finished()

            return True

        except SerializationError as e:
            error_msg = f"Failed to load variables: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Load Variables Error",
                    error_msg,
                )

            return False

    def _on_variable_panel_save_requested(self) -> None:
        """Handle save request from the variable panel."""
        if self._main_window:
            from PyQt6.QtWidgets import QFileDialog

            # Suggest a default filename based on current project file
            default_name = "variables.json"
            if self._current_file:
                default_name = self._current_file.stem + "_variables.json"

            file_path, _ = QFileDialog.getSaveFileName(
                self._main_window,
                "Save Variables",
                default_name,
                "JSON Files (*.json);;All Files (*)",
            )

            if file_path:
                self.save_variables(file_path)

    def _on_variable_panel_load_requested(self) -> None:
        """Handle load request from the variable panel."""
        if self._main_window:
            from PyQt6.QtWidgets import QFileDialog

            file_path, _ = QFileDialog.getOpenFileName(
                self._main_window,
                "Load Variables",
                "",
                "JSON Files (*.json);;All Files (*)",
            )

            if file_path:
                self.load_variables(file_path)

    # Library Export/Import Operations

    def export_library(
        self,
        file_path: str = "",
        node_ids: Optional[List[str]] = None,
        name: str = "",
        description: str = "",
        author: str = "",
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Export selected nodes as a reusable library.

        Args:
            file_path: Path to save the library file. If empty, shows dialog.
            node_ids: Optional list of node IDs to export. If None, uses selection.
            name: Library name. If empty, auto-generated.
            description: Library description.
            author: Library author.
            tags: Optional list of tags for the library.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Get nodes to export
            if node_ids is None:
                node_ids = self.get_selected_node_ids()

            if not node_ids:
                error_msg = "No nodes selected for export"
                self.error_occurred.emit(error_msg)
                if self._main_window:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self._main_window,
                        "Export Library",
                        error_msg,
                    )
                return False

            # Get the actual node objects
            nodes = [self._graph.get_node(node_id) for node_id in node_ids]
            nodes = [n for n in nodes if n is not None]

            if not nodes:
                error_msg = "Could not find selected nodes"
                self.error_occurred.emit(error_msg)
                return False

            # Show dialog if no file path provided
            if not file_path and self._main_window:
                from visualpython.ui.dialogs.library_export_dialog import LibraryExportDialog

                dialog = LibraryExportDialog(self._main_window)
                dialog.set_suggested_name(f"Library ({len(nodes)} nodes)")

                if not dialog.exec():
                    return False  # User cancelled

                file_path = dialog.get_file_path()
                if not file_path:
                    return False

                # Get metadata from dialog
                metadata = dialog.get_metadata()
            else:
                # Create metadata from parameters
                if not name:
                    name = f"Library ({len(nodes)} nodes)"
                metadata = LibraryMetadata(
                    name=name,
                    description=description,
                    author=author,
                    tags=tags or [],
                )

            # Export the library
            library = self._library_serializer.export_nodes(
                nodes=nodes,
                connections=self._graph.connections,
                metadata=metadata,
            )
            self._library_serializer.save(library, file_path)

            self.library_exported.emit(file_path, len(nodes))

            if self._main_window:
                self._main_window.show_status_message(
                    f"Exported {len(nodes)} nodes to: {file_path}", 5000
                )

            return True

        except SerializationError as e:
            error_msg = f"Failed to export library: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Export Library Error",
                    error_msg,
                )

            return False

        except Exception as e:
            error_msg = f"Unexpected error exporting library: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Export Library Error",
                    error_msg,
                )

            return False

    def import_library(
        self,
        file_path: str,
        position_offset: tuple = (50.0, 50.0),
    ) -> List[str]:
        """
        Import a node library into the current graph.

        Args:
            file_path: Path to the library file.
            position_offset: Offset to apply to imported node positions.

        Returns:
            List of new node IDs created, or empty list on failure.
        """
        try:
            # Load the library
            library = self._library_serializer.load(file_path)

            # Prepare nodes with new IDs and offset positions
            prepared_nodes, prepared_connections, id_mapping = \
                self._library_serializer.prepare_nodes_for_import(library, position_offset)

            new_node_ids: List[str] = []

            # Create nodes
            for node_data in prepared_nodes:
                node = self._create_node_from_dict(node_data)
                if node:
                    self._graph.add_node(node)
                    if self._graph_view:
                        self._graph_view.graph_scene.add_node_widget(node)
                    self.node_added.emit(node.id)
                    new_node_ids.append(node.id)

            # Create connections
            for conn_data in prepared_connections:
                try:
                    connection = self._graph.connect(
                        conn_data["source_node_id"],
                        conn_data["source_port_name"],
                        conn_data["target_node_id"],
                        conn_data["target_port_name"],
                        validate=False,
                    )
                    if self._graph_view:
                        self._graph_view.graph_scene.add_connection_widget(connection)
                        # Update port visual states
                        self._update_port_connection_state(
                            conn_data["source_node_id"],
                            conn_data["source_port_name"],
                            is_input=False,
                            is_connected=True,
                        )
                        self._update_port_connection_state(
                            conn_data["target_node_id"],
                            conn_data["target_port_name"],
                            is_input=True,
                            is_connected=True,
                        )
                except Exception as e:
                    self.error_occurred.emit(f"Failed to create connection: {e}")

            if new_node_ids:
                self._mark_modified()

                # Select the imported nodes
                if self._graph_view:
                    self._graph_view.clear_selection()
                    self._graph_view.select_nodes_by_ids(new_node_ids)

                self.library_imported.emit(file_path, len(new_node_ids))

                if self._main_window:
                    lib_name = library.metadata.name
                    self._main_window.show_status_message(
                        f"Imported '{lib_name}' ({len(new_node_ids)} nodes)", 5000
                    )

            return new_node_ids

        except SerializationError as e:
            error_msg = f"Failed to import library: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Import Library Error",
                    error_msg,
                )

            return []

        except Exception as e:
            error_msg = f"Unexpected error importing library: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Import Library Error",
                    error_msg,
                )

            return []

    def _create_node_from_dict(self, node_data: Dict[str, Any]) -> Optional[BaseNode]:
        """
        Create a node instance from serialized dictionary data.

        Args:
            node_data: Serialized node dictionary.

        Returns:
            New node instance, or None if creation failed.
        """
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

    def get_library_info(self, file_path: str) -> Optional[LibraryMetadata]:
        """
        Get metadata from a library file without fully loading it.

        Args:
            file_path: Path to the library file.

        Returns:
            LibraryMetadata if successful, None on error.
        """
        try:
            library = self._library_serializer.load(file_path)
            return library.metadata
        except SerializationError:
            logger.error("Serialization failed", exc_info=True)
            return None

    def import_python_script(self, file_path: str) -> Optional[str]:
        """
        Import a Python script file as a new CodeNode.

        Reads an existing Python script and creates a CodeNode with the
        script's contents. This enables reuse of existing Python code
        within the visual programming environment.

        Args:
            file_path: Path to the Python script file.

        Returns:
            The ID of the created CodeNode, or None if import failed.
        """
        from visualpython.compiler.ast_validator import validate_user_code

        try:
            path = Path(file_path)

            # Check file exists
            if not path.exists():
                error_msg = f"File not found: {file_path}"
                self.error_occurred.emit(error_msg)
                if self._main_window:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.critical(
                        self._main_window,
                        "Import Error",
                        error_msg,
                    )
                return None

            # Read the file contents
            try:
                code_content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Try with a different encoding
                code_content = path.read_text(encoding="latin-1")

            # Validate the Python syntax
            validation_result = validate_user_code(code_content)
            if not validation_result.valid:
                error_msg = (
                    f"The Python file has syntax errors:\n"
                    + "\n".join(validation_result.error_messages)
                )
                self.error_occurred.emit(error_msg)
                if self._main_window:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self._main_window,
                        "Import Warning",
                        error_msg + "\n\nThe file will be imported anyway, "
                        "but you'll need to fix the errors before execution.",
                    )

            # Determine the position for the new node
            # Place at center of current view or use default position
            x_pos, y_pos = 100.0, 100.0
            if self._graph_view:
                # Get the center of the visible area
                view_center = self._graph_view.mapToScene(
                    self._graph_view.viewport().rect().center()
                )
                x_pos = view_center.x()
                y_pos = view_center.y()

            # Create the CodeNode with a name based on the filename
            node_name = path.stem  # Filename without extension

            # Use command pattern for undo support
            command = AddNodeCommand(
                graph=self._graph,
                node_type="code",
                x=x_pos,
                y=y_pos,
                registry=self._registry,
                add_widget_callback=self._add_node_widget,
                remove_widget_callback=self._remove_node_widget,
            )

            if self._undo_redo_manager.execute(command):
                node_id = command.node_id
                node = self._graph.get_node(node_id)

                if node:
                    # Set the code content and name
                    node._code = code_content
                    node._name = node_name

                    # Update the node widget to reflect the new name
                    self._update_node_widget(node_id)

                    self.node_added.emit(node_id)
                    self._mark_modified()

                    # Select the newly created node
                    if self._graph_view:
                        self._graph_view.clear_selection()
                        self._graph_view.select_nodes_by_ids([node_id])

                    if self._main_window:
                        self._main_window.show_status_message(
                            f"Imported Python script as code node: {node_name}", 5000
                        )

                    return node_id

            return None

        except OSError as e:
            error_msg = f"Failed to read file: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Import Error",
                    error_msg,
                )

            return None

        except Exception as e:
            error_msg = f"Unexpected error importing Python script: {e}"
            self.error_occurred.emit(error_msg)

            if self._main_window:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self._main_window,
                    "Import Error",
                    error_msg,
                )

            return None

    # Layout Operations

    def apply_auto_layout(self, algorithm: str = "hierarchical") -> bool:
        """
        Apply an automatic layout algorithm to organize nodes.

        Args:
            algorithm: The layout algorithm to use.
                       Options: 'hierarchical', 'force-directed'

        Returns:
            True if layout was applied successfully, False otherwise.
        """
        from visualpython.layout import HierarchicalLayout, ForceDirectedLayout, LayoutOptions
        from visualpython.commands.layout_commands import ApplyLayoutCommand

        if self._graph.is_empty:
            if self._main_window:
                self._main_window.show_status_message("No nodes to layout", 2000)
            return False

        try:
            # Create layout options
            options = LayoutOptions(
                horizontal_spacing=200.0,
                vertical_spacing=120.0,
                snap_to_grid=True,
                grid_size=20.0,
                center_layout=True,
            )

            # Select algorithm
            if algorithm.lower() == "force-directed":
                layout = ForceDirectedLayout(options)
            else:
                layout = HierarchicalLayout(options)

            # Calculate layout
            result = layout.calculate(self._graph)

            if not result.success:
                if self._main_window:
                    error_msg = result.error_message or "Layout calculation failed"
                    self._main_window.show_status_message(f"Layout failed: {error_msg}", 3000)
                return False

            # Create and execute the command
            command = ApplyLayoutCommand(
                graph=self._graph,
                layout_result=result,
                update_widget_callback=self._update_node_widget_position,
                update_connections_callback=self._update_all_connections,
            )

            if self._undo_redo_manager.execute(command):
                self._mark_modified()

                if self._main_window:
                    self._main_window.show_status_message(
                        f"Applied {layout.name} layout to {len(result.positions)} nodes", 3000
                    )

                # Fit the view to show all nodes
                if self._graph_view:
                    self._graph_view.fit_in_view()

                return True

            return False

        except Exception as e:
            if self._main_window:
                self._main_window.show_status_message(f"Layout error: {e}", 3000)
            return False

    def apply_hierarchical_layout(self) -> bool:
        """Apply hierarchical layout algorithm."""
        return self.apply_auto_layout("hierarchical")

    def apply_force_directed_layout(self) -> bool:
        """Apply force-directed layout algorithm."""
        return self.apply_auto_layout("force-directed")

    def _update_node_widget_position(self, node_id: str, x: float, y: float) -> None:
        """
        Update a node widget's visual position.

        Args:
            node_id: ID of the node.
            x: New X position.
            y: New Y position.
        """
        if self._graph_view:
            scene = self._graph_view.graph_scene
            widget = scene.get_node_widget(node_id)
            if widget:
                widget.setPos(x, y)

    def _update_all_connections(self) -> None:
        """Update all connection widget paths after a layout change."""
        if self._graph_view:
            scene = self._graph_view.graph_scene
            for conn_widget in scene.get_all_connection_widgets():
                conn_widget.update_path()

    def _on_snap_to_grid_toggled(self, enabled: bool) -> None:
        """
        Handle snap to grid toggle from the View menu.

        Args:
            enabled: Whether snap to grid is enabled.
        """
        if self._graph_view:
            self._graph_view.graph_scene.snap_to_grid_enabled = enabled

    def _on_group_selected_requested(self) -> None:
        """Handle group selected nodes request from the Edit menu."""
        # Prompt for group name
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self._main_window,
            "Create Group",
            "Enter group name:",
            text="Group"
        )

        if ok and name:
            self.create_group_from_selection(name=name)

    def _on_ungroup_selected_requested(self) -> None:
        """Handle ungroup request from the Edit menu."""
        if not self._graph_view:
            return

        # Check if a group is selected
        selected_groups = self._graph_view.graph_scene.get_selected_group_widgets()
        if selected_groups:
            # Ungroup the first selected group
            for group_widget in selected_groups:
                self.ungroup(group_widget.group_id)
        else:
            # Check if selected nodes are in a group
            selected_node_ids = self.get_selected_node_ids()
            if selected_node_ids:
                # Find the group containing the first selected node
                group = self._graph.get_group_for_node(selected_node_ids[0])
                if group:
                    self.ungroup(group.id)
                else:
                    if self._main_window:
                        self._main_window.show_status_message(
                            "Selected nodes are not in a group", 3000
                        )
