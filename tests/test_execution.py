"""Test that the default graph executes without errors."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from visualpython.execution.context import ExecutionStatus


def test_default_graph_runs_without_error(app_setup, qtbot):
    """Press F5 on the default graph and assert execution succeeds."""
    window, controller = app_setup

    # Capture the execution result via the controller signal
    results = []
    controller.execution_finished.connect(
        lambda success, msg: results.append((success, msg))
    )

    # Trigger Run (same as pressing F5)
    controller.run_graph()

    # Wait for execution_finished signal (up to 10 seconds)
    with qtbot.waitSignal(controller.execution_finished, timeout=10_000):
        pass

    assert len(results) == 1, "Expected exactly one execution_finished signal"
    success, message = results[0]
    assert success, f"Execution failed: {message}"
    assert "completed" in message.lower()
