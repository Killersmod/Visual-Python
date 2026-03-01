"""
Execution state manager for VisualPython.

This module provides a centralized manager for tracking and exposing
execution state (idle, running, paused, error) to the UI.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Optional
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal


class ExecutionState(Enum):
    """
    Represents the overall execution state of the application.

    This enum defines the high-level states that are exposed to the UI
    for status display and user feedback.
    """

    IDLE = auto()
    """No execution in progress, ready to run."""

    RUNNING = auto()
    """Execution is currently in progress."""

    PAUSED = auto()
    """Execution is paused (reserved for future breakpoint support)."""

    ERROR = auto()
    """Execution ended with an error."""


class ExecutionStateManager(QObject):
    """
    Centralized manager for tracking execution state.

    This class provides a single source of truth for execution state
    that can be observed by UI components through Qt signals.

    Signals:
        state_changed(ExecutionState): Emitted when the execution state changes.
        error_occurred(str): Emitted when an error occurs during execution.
        progress_updated(int, int): Emitted when execution progress changes (current, total).
        execution_started: Emitted when execution begins.
        execution_finished(bool): Emitted when execution ends (success: bool).
        step_paused(str, str): Emitted when paused for step-through (node_id, node_name).
        step_mode_changed(bool): Emitted when step mode is enabled/disabled.

    Example:
        >>> manager = ExecutionStateManager()
        >>> manager.state_changed.connect(on_state_changed)
        >>> manager.start_execution()
        >>> # State is now RUNNING
        >>> manager.finish_execution(success=True)
        >>> # State is now IDLE
    """

    # Signals
    state_changed = pyqtSignal(object)  # ExecutionState
    error_occurred = pyqtSignal(str)  # error message
    progress_updated = pyqtSignal(int, int)  # current, total
    execution_started = pyqtSignal()
    execution_finished = pyqtSignal(bool)  # success
    step_paused = pyqtSignal(str, str)  # node_id, node_name
    step_mode_changed = pyqtSignal(bool)  # step_mode_enabled

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Initialize the execution state manager.

        Args:
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self._state: ExecutionState = ExecutionState.IDLE
        self._error_message: Optional[str] = None
        self._started_at: Optional[datetime] = None
        self._current_node: Optional[str] = None
        self._current_node_name: Optional[str] = None
        self._nodes_executed: int = 0
        self._total_nodes: int = 0
        self._step_mode: bool = False

    @property
    def state(self) -> ExecutionState:
        """Get the current execution state."""
        return self._state

    @property
    def is_idle(self) -> bool:
        """Check if the execution state is idle."""
        return self._state == ExecutionState.IDLE

    @property
    def is_running(self) -> bool:
        """Check if execution is currently running."""
        return self._state == ExecutionState.RUNNING

    @property
    def is_paused(self) -> bool:
        """Check if execution is paused."""
        return self._state == ExecutionState.PAUSED

    @property
    def is_error(self) -> bool:
        """Check if execution ended with an error."""
        return self._state == ExecutionState.ERROR

    @property
    def error_message(self) -> Optional[str]:
        """Get the error message if in error state."""
        return self._error_message

    @property
    def current_node(self) -> Optional[str]:
        """Get the ID of the currently executing node."""
        return self._current_node

    @property
    def current_node_name(self) -> Optional[str]:
        """Get the name of the currently executing node."""
        return self._current_node_name

    @property
    def is_step_mode(self) -> bool:
        """Check if step-through execution mode is enabled."""
        return self._step_mode

    @property
    def execution_duration_ms(self) -> Optional[float]:
        """
        Get the duration of the current or last execution in milliseconds.

        Returns:
            Duration in milliseconds, or None if no execution has started.
        """
        if self._started_at is None:
            return None
        delta = datetime.now() - self._started_at
        return delta.total_seconds() * 1000

    @property
    def progress(self) -> tuple[int, int]:
        """
        Get the current execution progress.

        Returns:
            Tuple of (nodes_executed, total_nodes).
        """
        return (self._nodes_executed, self._total_nodes)

    def _set_state(self, new_state: ExecutionState) -> None:
        """
        Set the execution state and emit signal if changed.

        Args:
            new_state: The new execution state.
        """
        if self._state != new_state:
            self._state = new_state
            self.state_changed.emit(new_state)

    def start_execution(self, total_nodes: int = 0) -> None:
        """
        Mark the start of execution.

        Args:
            total_nodes: Total number of nodes to execute (for progress tracking).
        """
        self._error_message = None
        self._started_at = datetime.now()
        self._current_node = None
        self._nodes_executed = 0
        self._total_nodes = total_nodes
        self._set_state(ExecutionState.RUNNING)
        self.execution_started.emit()

    def finish_execution(self, success: bool = True, error: Optional[str] = None) -> None:
        """
        Mark the end of execution.

        Args:
            success: Whether execution completed successfully.
            error: Error message if execution failed.
        """
        self._current_node = None

        if success:
            self._error_message = None
            self._set_state(ExecutionState.IDLE)
        else:
            self._error_message = error
            self._set_state(ExecutionState.ERROR)
            if error:
                self.error_occurred.emit(error)

        self.execution_finished.emit(success)

    def pause_execution(self) -> None:
        """
        Mark execution as paused.

        This is reserved for future breakpoint support.
        """
        if self._state == ExecutionState.RUNNING:
            self._set_state(ExecutionState.PAUSED)

    def resume_execution(self) -> None:
        """
        Resume execution from paused state.

        This is reserved for future breakpoint support.
        """
        if self._state == ExecutionState.PAUSED:
            self._set_state(ExecutionState.RUNNING)

    def cancel_execution(self) -> None:
        """Mark execution as cancelled (returns to idle)."""
        self._current_node = None
        self._current_node_name = None
        self._error_message = None
        self._set_state(ExecutionState.IDLE)
        self.execution_finished.emit(False)

    def set_current_node(self, node_id: Optional[str], node_name: Optional[str] = None) -> None:
        """
        Set the currently executing node.

        Args:
            node_id: The ID of the node being executed, or None.
            node_name: The name of the node being executed, or None.
        """
        self._current_node = node_id
        self._current_node_name = node_name

    # Step-through execution support

    def enable_step_mode(self) -> None:
        """Enable step-through execution mode."""
        if not self._step_mode:
            self._step_mode = True
            self.step_mode_changed.emit(True)

    def disable_step_mode(self) -> None:
        """Disable step-through execution mode."""
        if self._step_mode:
            self._step_mode = False
            self.step_mode_changed.emit(False)

    def toggle_step_mode(self) -> bool:
        """
        Toggle step-through execution mode.

        Returns:
            The new step mode state.
        """
        if self._step_mode:
            self.disable_step_mode()
        else:
            self.enable_step_mode()
        return self._step_mode

    def on_step_paused(self, node_id: str, node_name: str) -> None:
        """
        Handle execution pausing at a node for step-through.

        Args:
            node_id: The ID of the node where execution paused.
            node_name: The name of the node.
        """
        self._current_node = node_id
        self._current_node_name = node_name
        self._set_state(ExecutionState.PAUSED)
        self.step_paused.emit(node_id, node_name)

    def increment_progress(self) -> None:
        """Increment the progress counter when a node completes."""
        self._nodes_executed += 1
        self.progress_updated.emit(self._nodes_executed, self._total_nodes)

    def set_progress(self, current: int, total: int) -> None:
        """
        Set the execution progress explicitly.

        Args:
            current: Number of nodes executed.
            total: Total number of nodes to execute.
        """
        self._nodes_executed = current
        self._total_nodes = total
        self.progress_updated.emit(current, total)

    def reset(self) -> None:
        """Reset the manager to initial state."""
        self._error_message = None
        self._started_at = None
        self._current_node = None
        self._current_node_name = None
        self._nodes_executed = 0
        self._total_nodes = 0
        # Don't reset step_mode - preserve user preference
        self._set_state(ExecutionState.IDLE)

    def clear_error(self) -> None:
        """Clear the error state and return to idle."""
        if self._state == ExecutionState.ERROR:
            self._error_message = None
            self._set_state(ExecutionState.IDLE)

    def get_state_display_text(self) -> str:
        """
        Get a human-readable display text for the current state.

        Returns:
            A string suitable for display in the UI.
        """
        if self._state == ExecutionState.PAUSED and self._current_node_name:
            return f"Paused at {self._current_node_name}"

        state_texts = {
            ExecutionState.IDLE: "Ready",
            ExecutionState.RUNNING: "Running",
            ExecutionState.PAUSED: "Paused",
            ExecutionState.ERROR: "Error",
        }
        return state_texts.get(self._state, "Unknown")

    def __repr__(self) -> str:
        """Get a string representation of the manager."""
        return (
            f"ExecutionStateManager(state={self._state.name}, "
            f"progress={self._nodes_executed}/{self._total_nodes})"
        )
