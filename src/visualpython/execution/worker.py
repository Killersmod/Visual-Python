"""
Worker thread for executing visual Python scripts.

This module provides a QThread-based worker for running execution in the
background, allowing the UI to remain responsive and enabling the user
to stop execution at any time.
"""

from __future__ import annotations

from typing import Optional, Callable, Dict, Any, TYPE_CHECKING

from PyQt6.QtCore import QThread, pyqtSignal, QObject

from visualpython.execution.engine import ExecutionEngine
from visualpython.execution.context import ExecutionResult
from visualpython.execution.output_capture import OutputCapture

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph
    from visualpython.nodes.models.base_node import BaseNode


class ExecutionWorker(QObject):
    """
    Worker object for executing graphs in a background thread.

    This worker is designed to be moved to a QThread and executes the
    graph asynchronously, emitting signals for progress updates and
    completion.

    Signals:
        execution_finished(ExecutionResult): Emitted when execution completes.
        node_started(BaseNode): Emitted when a node starts executing.
        node_completed(BaseNode, dict): Emitted when a node completes.
        node_error(BaseNode, Exception): Emitted when a node has an error.
        stdout_received(str): Emitted when stdout output is captured.
        stderr_received(str): Emitted when stderr output is captured.
        step_paused(BaseNode): Emitted when execution pauses for step-through.
    """

    execution_finished = pyqtSignal(object)  # ExecutionResult
    node_started = pyqtSignal(object)  # BaseNode
    node_completed = pyqtSignal(object, object)  # BaseNode, dict
    node_error = pyqtSignal(object, object)  # BaseNode, Exception
    stdout_received = pyqtSignal(str)
    stderr_received = pyqtSignal(str)
    step_paused = pyqtSignal(object)  # BaseNode

    def __init__(
        self,
        graph: "Graph",
        step_mode: bool = False,
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Initialize the execution worker.

        Args:
            graph: The graph to execute.
            step_mode: Whether to start in step-through execution mode.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._graph = graph
        self._step_mode = step_mode
        self._engine: Optional[ExecutionEngine] = None

    def run(self) -> None:
        """Execute the graph."""
        # Create the execution engine with callbacks
        self._engine = ExecutionEngine(
            self._graph,
            on_node_start=self._on_node_start,
            on_node_complete=self._on_node_complete,
            on_node_error=self._on_node_error,
            on_step_paused=self._on_step_paused,
            step_mode=self._step_mode,
        )

        # Reset graph state
        self._graph.reset_execution_state()

        # Use output capture to redirect stdout/stderr
        with OutputCapture(
            on_stdout=self._on_stdout,
            on_stderr=self._on_stderr,
        ):
            result = self._engine.execute()

        self.execution_finished.emit(result)

    def cancel(self) -> None:
        """Cancel the current execution."""
        if self._engine:
            self._engine.cancel()

    def step(self) -> None:
        """Execute the next step in step-through mode."""
        if self._engine:
            self._engine.step()

    def continue_execution(self) -> None:
        """Continue execution normally (exit step mode for current run)."""
        if self._engine:
            self._engine.continue_execution()

    def enable_step_mode(self) -> None:
        """Enable step-through execution mode."""
        if self._engine:
            self._engine.enable_step_mode()

    def disable_step_mode(self) -> None:
        """Disable step-through execution mode."""
        if self._engine:
            self._engine.disable_step_mode()

    @property
    def step_mode(self) -> bool:
        """Check if step mode is enabled."""
        if self._engine:
            return self._engine.step_mode
        return self._step_mode

    def _on_node_start(self, node: "BaseNode") -> None:
        """Handle node start callback."""
        self.node_started.emit(node)

    def _on_step_paused(self, node: "BaseNode") -> None:
        """Handle step paused callback."""
        self.step_paused.emit(node)

    def _on_node_complete(self, node: "BaseNode", outputs: Dict[str, Any]) -> None:
        """Handle node complete callback."""
        self.node_completed.emit(node, outputs)

    def _on_node_error(self, node: "BaseNode", error: Exception) -> None:
        """Handle node error callback."""
        self.node_error.emit(node, error)

    def _on_stdout(self, text: str) -> None:
        """Handle stdout output."""
        self.stdout_received.emit(text)

    def _on_stderr(self, text: str) -> None:
        """Handle stderr output."""
        self.stderr_received.emit(text)


class ExecutionThread(QThread):
    """
    Thread for running graph execution.

    This thread manages the ExecutionWorker and provides a simple interface
    for starting and stopping execution.

    Signals:
        execution_finished(ExecutionResult): Emitted when execution completes.
        node_started(BaseNode): Emitted when a node starts executing.
        node_completed(BaseNode, dict): Emitted when a node completes.
        node_error(BaseNode, Exception): Emitted when a node has an error.
        stdout_received(str): Emitted when stdout output is captured.
        stderr_received(str): Emitted when stderr output is captured.
        step_paused(BaseNode): Emitted when execution pauses for step-through.
    """

    execution_finished = pyqtSignal(object)  # ExecutionResult
    node_started = pyqtSignal(object)  # BaseNode
    node_completed = pyqtSignal(object, object)  # BaseNode, dict
    node_error = pyqtSignal(object, object)  # BaseNode, Exception
    stdout_received = pyqtSignal(str)
    stderr_received = pyqtSignal(str)
    step_paused = pyqtSignal(object)  # BaseNode

    def __init__(
        self,
        graph: "Graph",
        step_mode: bool = False,
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Initialize the execution thread.

        Args:
            graph: The graph to execute.
            step_mode: Whether to start in step-through execution mode.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._graph = graph
        self._step_mode = step_mode
        self._worker: Optional[ExecutionWorker] = None

    def run(self) -> None:
        """Run the execution in this thread."""
        self._worker = ExecutionWorker(self._graph, step_mode=self._step_mode)

        # Connect worker signals to thread signals for forwarding
        self._worker.execution_finished.connect(self.execution_finished.emit)
        self._worker.node_started.connect(self.node_started.emit)
        self._worker.node_completed.connect(self.node_completed.emit)
        self._worker.node_error.connect(self.node_error.emit)
        self._worker.stdout_received.connect(self.stdout_received.emit)
        self._worker.stderr_received.connect(self.stderr_received.emit)
        self._worker.step_paused.connect(self.step_paused.emit)

        # Execute
        self._worker.run()

    def cancel(self) -> None:
        """Cancel the current execution."""
        if self._worker:
            self._worker.cancel()

    def step(self) -> None:
        """Execute the next step in step-through mode."""
        if self._worker:
            self._worker.step()

    def continue_execution(self) -> None:
        """Continue execution normally (exit step mode for current run)."""
        if self._worker:
            self._worker.continue_execution()

    def enable_step_mode(self) -> None:
        """Enable step-through execution mode."""
        if self._worker:
            self._worker.enable_step_mode()

    def disable_step_mode(self) -> None:
        """Disable step-through execution mode."""
        if self._worker:
            self._worker.disable_step_mode()

    @property
    def step_mode(self) -> bool:
        """Check if step mode is enabled."""
        if self._worker:
            return self._worker.step_mode
        return self._step_mode
