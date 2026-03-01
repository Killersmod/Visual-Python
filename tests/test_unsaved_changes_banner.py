"""Tests for the unsaved changes notification banner."""

from __future__ import annotations

from pathlib import Path

import pytest


def _simulate_save(window, controller, tmp_path):
    """Helper: set file paths and call _on_save without opening dialogs."""
    save_path = str(tmp_path / "test_project.vpy")
    window._current_file = save_path
    controller._current_file = Path(save_path)
    window._on_save()


def test_banner_hidden_on_startup(app_setup, qtbot):
    """Banner should not be visible when the project has no unsaved changes."""
    window, controller = app_setup

    # Fixture adds default nodes which marks modified — reset it
    window.is_modified = False

    assert hasattr(window, '_unsaved_changes_banner')
    assert not window._unsaved_changes_banner.isVisible()


def test_banner_appears_when_node_added(app_setup, qtbot):
    """Adding a node triggers _mark_modified, which should show the banner."""
    window, controller = app_setup

    # Reset to clean state
    window.is_modified = False
    assert not window._unsaved_changes_banner.isVisible()

    # Add a node — this calls _mark_modified() in the controller
    controller.add_node("print", x=0, y=100)

    assert window._unsaved_changes_banner.isVisible()


def test_banner_disappears_after_save(app_setup, qtbot, tmp_path):
    """After saving, the banner should hide."""
    window, controller = app_setup

    # Mark as modified
    window.is_modified = True
    assert window._unsaved_changes_banner.isVisible()

    # Save via helper (sets both window and controller file paths)
    _simulate_save(window, controller, tmp_path)

    assert not window._unsaved_changes_banner.isVisible()


def test_banner_reappears_on_further_modification(app_setup, qtbot, tmp_path):
    """After saving, modifying again should show the banner again."""
    window, controller = app_setup

    window.is_modified = True
    assert window._unsaved_changes_banner.isVisible()

    _simulate_save(window, controller, tmp_path)
    assert not window._unsaved_changes_banner.isVisible()

    # Modify again
    controller.add_node("print", x=0, y=200)
    assert window._unsaved_changes_banner.isVisible()


def test_banner_has_correct_text_and_button(app_setup, qtbot):
    """Banner should contain the expected message label and save button."""
    window, controller = app_setup
    banner = window._unsaved_changes_banner

    assert "unsaved changes" in banner._message_label.text().lower()
    assert banner._save_button.text() == "Save"


def test_banner_appears_when_node_moved(app_setup, qtbot):
    """Moving a node should mark the project as modified and show the banner."""
    window, controller = app_setup

    # Reset to clean state
    window.is_modified = False
    assert not window._unsaved_changes_banner.isVisible()

    # Get the first print node and its widget
    graph = controller._graph
    nodes = [n for n in graph.nodes if n.name == "Print"]
    assert len(nodes) >= 1
    node = nodes[0]

    graph_view = window.get_current_graph_view()
    assert graph_view is not None
    widget = graph_view.graph_scene.get_node_widget(node.id)
    assert widget is not None

    # Simulate a completed drag by emitting move_finished directly
    old_x, old_y = widget.x(), widget.y()
    new_x, new_y = old_x + 100, old_y + 50
    widget.setPos(new_x, new_y)
    widget.signals.move_finished.emit(node.id, old_x, old_y, new_x, new_y)

    assert window._unsaved_changes_banner.isVisible()
    assert window.is_modified


def test_node_move_supports_undo(app_setup, qtbot):
    """Undoing a node move should restore the original position."""
    window, controller = app_setup

    # Reset to clean state and clear undo history
    window.is_modified = False
    controller.clear_undo_history()

    # Get a node and its widget
    graph = controller._graph
    nodes = [n for n in graph.nodes if n.name == "Print"]
    node = nodes[0]

    graph_view = window.get_current_graph_view()
    widget = graph_view.graph_scene.get_node_widget(node.id)

    old_x, old_y = widget.x(), widget.y()
    new_x, new_y = old_x + 100, old_y + 50

    # Simulate move
    widget.setPos(new_x, new_y)
    node.position.x = new_x
    node.position.y = new_y
    widget.signals.move_finished.emit(node.id, old_x, old_y, new_x, new_y)

    assert node.position.x == new_x
    assert node.position.y == new_y

    # Undo the move
    controller.undo()

    assert node.position.x == old_x
    assert node.position.y == old_y


def test_banner_appears_when_inline_value_typed(app_setup, qtbot):
    """Typing a value in an inline widget should show the banner."""
    window, controller = app_setup

    # Reset to clean state
    window.is_modified = False
    assert not window._unsaved_changes_banner.isVisible()

    # Get a print node and simulate an inline value change via the scene signal
    graph = controller._graph
    nodes = [n for n in graph.nodes if n.name == "Print"]
    assert len(nodes) >= 1
    node = nodes[0]

    graph_view = window.get_current_graph_view()
    scene = graph_view.graph_scene

    # Emit the inline value changed signal as if the user typed a new message
    scene.node_inline_value_changed.emit(node.id, "message", "Hello", "New message")

    assert window._unsaved_changes_banner.isVisible()
    assert window.is_modified


def test_banner_after_undo_redo_cycle(app_setup, qtbot):
    """Undo and redo should keep the banner visible (graph differs from saved state)."""
    window, controller = app_setup

    window.is_modified = False
    controller.clear_undo_history()

    # Add a node to trigger modified state
    controller.add_node("print", x=0, y=300)
    assert window._unsaved_changes_banner.isVisible()

    # Undo — still modified (undo itself is a change from the saved point of view)
    controller.undo()
    assert window._unsaved_changes_banner.isVisible()

    # Redo — still modified
    controller.redo()
    assert window._unsaved_changes_banner.isVisible()
