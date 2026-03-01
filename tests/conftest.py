"""Shared fixtures for VisualPython tests."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from visualpython.ui.main_window import MainWindow
from visualpython.core.application import ApplicationController


@pytest.fixture
def app_setup(qtbot):
    """
    Create a fully wired MainWindow + ApplicationController with
    the default Start -> Print("Hello") -> Print("World!") graph.

    Yields (window, controller) and tears down afterwards.
    """
    window = MainWindow()
    qtbot.addWidget(window)

    controller = ApplicationController()
    controller.set_main_window(window)
    controller.setup_tab_widget_factories()
    controller.create_initial_workflow_tab()

    # Add default nodes
    start_node = controller.add_node("start", x=-200, y=0)
    print1 = controller.add_node("print", x=200, y=-50)
    print2 = controller.add_node("print", x=600, y=-50)

    # Set inline values
    if print1:
        print1.message = "Hello"
        msg_port = print1.get_input_port("message")
        if msg_port:
            msg_port.inline_value = "Hello"
    if print2:
        print2.message = "World!"
        msg_port = print2.get_input_port("message")
        if msg_port:
            msg_port.inline_value = "World!"

    # Connect Start -> Print1 -> Print2
    graph = controller._graph
    if start_node and print1 and print2:
        graph_view = window.get_current_graph_view()
        conn1 = graph.connect(start_node.id, "exec_out", print1.id, "exec_in")
        conn2 = graph.connect(print1.id, "exec_out", print2.id, "exec_in")
        if graph_view:
            graph_view.graph_scene.add_connection_widget(conn1)
            graph_view.graph_scene.add_connection_widget(conn2)

    # Wire signals (same as __main__.py)
    window.run_requested.connect(controller.run_graph)
    window.stop_requested.connect(controller.stop_execution)

    # Never prompt "Unsaved Changes" during tests
    window._check_save_changes = lambda: True

    window.show()
    qtbot.waitExposed(window)

    yield window, controller

    window.close()
