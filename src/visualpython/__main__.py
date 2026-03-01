"""
Entry point for the VisualPython application.

This module provides the main entry point for running VisualPython
as a Python package or via the console script.
"""

from __future__ import annotations

import faulthandler
import logging
import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import QApplication

from visualpython.ui.main_window import MainWindow
from visualpython.core.application import ApplicationController
from visualpython.ui.widgets.node_search_widget import NodeSearchController
from visualpython.utils.logging import setup_logging, get_logger

# Centralised logging – writes to disk, stderr, and an in-memory buffer.
setup_logging()

_crash_log = Path(__file__).resolve().parent.parent.parent / "crash.log"
_logger = get_logger("visualpython")


def _install_exception_hooks() -> None:
    """Install global exception hooks to catch silent crashes."""
    # Enable faulthandler to dump C-level tracebacks on segfault
    faulthandler.enable(file=sys.stderr, all_threads=True)
    try:
        faulthandler.enable(file=open(_crash_log, "a"), all_threads=True)
    except Exception:
        _logger.debug("Could not enable faulthandler on crash log file", exc_info=True)

    _original_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        _logger.critical(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb)
        )
        _original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook


def main(args: Optional[List[str]] = None) -> int:
    """
    Run the VisualPython application.

    Args:
        args: Optional list of command line arguments. If None, sys.argv is used.

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    _install_exception_hooks()

    if args is None:
        args = sys.argv

    _logger.info("Starting VisualPython...")
    _logger.info("Python %s", sys.version)
    _logger.info("Args: %s", args)

    try:
        app = QApplication(args)
    except Exception:
        _logger.critical("Failed to create QApplication", exc_info=True)
        raise
    app.setApplicationName("VisualPython")
    app.setOrganizationName("VisualPython")
    app.setOrganizationDomain("visualpython.org")

    try:
        _logger.info("Creating MainWindow...")
        window = MainWindow()

        # Install Qt log handler so logs appear in the Logs panel
        _qt_log_handler = window.get_log_handler()
        _qt_log_handler.setLevel(logging.DEBUG)
        from visualpython.utils.logging import _LOG_FORMAT
        _qt_log_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logging.getLogger().addHandler(_qt_log_handler)

        _logger.info("Creating ApplicationController...")
        # Create the application controller to manage graph state and serialization
        controller = ApplicationController()
        controller.set_main_window(window)

        # Set up the workflow tab system factories
        _logger.info("Setting up tab widget factories...")
        controller.setup_tab_widget_factories()

        # Create the initial workflow tab with a graph view
        _logger.info("Creating initial workflow tab...")
        controller.create_initial_workflow_tab()

        # Add default nodes: Start + 2 Print nodes with "Hello" and "World!" messages
        _logger.info("Adding default nodes...")
        start_node = controller.add_node("start", x=-200, y=0)
        print1 = controller.add_node("print", x=200, y=-50)
        print2 = controller.add_node("print", x=600, y=-50)

        # Set default messages on print nodes via port inline values
        graph_view = window.get_current_graph_view()
        if print1:
            print1.message = "Hello"
            msg_port = print1.get_input_port("message")
            if msg_port:
                msg_port.inline_value = "Hello"
            if graph_view:
                widget = graph_view.graph_scene.get_node_widget(print1.id)
                if widget:
                    widget.sync_inline_widgets_from_ports()
        if print2:
            print2.message = "World!"
            msg_port = print2.get_input_port("message")
            if msg_port:
                msg_port.inline_value = "World!"
            if graph_view:
                widget = graph_view.graph_scene.get_node_widget(print2.id)
                if widget:
                    widget.sync_inline_widgets_from_ports()

        # Connect Start → Print1 → Print2 (execution flow)
        graph = controller._graph
        if start_node and print1 and print2:
            conn1 = graph.connect(start_node.id, "exec_out", print1.id, "exec_in")
            conn2 = graph.connect(print1.id, "exec_out", print2.id, "exec_in")
            if graph_view:
                graph_view.graph_scene.add_connection_widget(conn1)
                graph_view.graph_scene.add_connection_widget(conn2)

        # Reset modified state so the default layout doesn't appear as unsaved changes
        window.is_modified = False

        # Get the graph view from the initial tab for connecting signals
        graph_view = window.get_current_graph_view()

        if graph_view:
            # Connect view menu actions to the graph view
            window.zoom_in_action.triggered.connect(graph_view.zoom_in)
            window.zoom_out_action.triggered.connect(graph_view.zoom_out)
            window.reset_zoom_action.triggered.connect(graph_view.reset_zoom)
            window.fit_action.triggered.connect(graph_view.fit_in_view_all)

            # Connect edit menu actions to the controller/view
            window.delete_action.triggered.connect(controller.delete_selected_nodes)
            window.select_all_action.triggered.connect(graph_view.selection_manager.select_all)

            # Connect minimap to the graph view
            window.connect_minimap_to_graph_view(graph_view)

            # Set up node search functionality (Ctrl+F)
            search_controller = NodeSearchController(
                window.central_widget,
                graph_view.graph_scene,
                graph_view
            )

            # Connect Find menu action to search controller
            window.find_action.triggered.connect(search_controller.show_search)

        # Connect undo/redo signals
        window.undo_requested.connect(controller.undo)
        window.redo_requested.connect(controller.redo)

        # Update undo/redo action states based on availability
        controller.can_undo_changed.connect(window.set_undo_enabled)
        controller.can_redo_changed.connect(window.set_redo_enabled)

        # Initialize undo/redo button states
        window.set_undo_enabled(controller.can_undo)
        window.set_redo_enabled(controller.can_redo)

        # Connect run/stop actions to the controller
        window.run_requested.connect(controller.run_graph)
        window.stop_requested.connect(controller.stop_execution)

        # Connect execution state manager to the UI
        window.connect_execution_state_manager(controller.execution_state_manager)

        _logger.info("Showing window...")
        window.showMaximized()

        _logger.info("Entering event loop...")
        return app.exec()

    except Exception:
        _logger.critical("Fatal error during startup", exc_info=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
