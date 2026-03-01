"""
Execution context for tracking state during script execution.

This module provides the ExecutionContext class that maintains all state
information during the execution of a visual script, including node outputs,
execution history, and error information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode
    from visualpython.execution.case import Case
    from visualpython.execution.error_report import ErrorReport, NodeLocation
    from visualpython.execution.type_info import TypeInfo, TypeMismatch


class ExecutionStatus(Enum):
    """Represents the overall execution status."""

    PENDING = auto()
    """Execution has not started yet."""

    RUNNING = auto()
    """Execution is currently in progress."""

    PAUSED = auto()
    """Execution is paused at a breakpoint."""

    COMPLETED = auto()
    """Execution finished successfully."""

    FAILED = auto()
    """Execution failed with an error."""

    CANCELLED = auto()
    """Execution was cancelled by the user."""


class NodeExecutionStatus(Enum):
    """Represents the execution status of an individual node."""

    PENDING = auto()
    """Node has not been executed yet."""

    SUCCESS = auto()
    """Node executed successfully without errors."""

    FAILED = auto()
    """Node encountered an error during execution."""

    SKIPPED = auto()
    """Node was skipped (e.g., due to upstream failure or conditional branching)."""


@dataclass
class NodeExecutionSummary:
    """
    Summary of a single node's execution for the execution summary panel.

    This dataclass provides a lightweight summary of a node's execution status,
    designed specifically for displaying in the ExecutionSummaryPanel. It tracks
    whether the node succeeded, failed, or was skipped, along with any errors
    that occurred and timing information.

    Unlike NodeExecutionRecord which captures detailed execution history for
    debugging and replay, NodeExecutionSummary is optimized for quick status
    display and navigation.

    Attributes:
        node_id: Unique identifier of the node.
        node_name: Display name of the node.
        node_type: Type of the node (e.g., 'code', 'if', 'for_loop').
        status: Execution status (SUCCESS, FAILED, or SKIPPED).
        errors: List of ErrorReport objects if execution failed.
        execution_time_ms: Execution time in milliseconds (None if not executed).
        skip_reason: Reason the node was skipped (if status is SKIPPED).
        location_x: X coordinate of the node on the canvas for navigation.
        location_y: Y coordinate of the node on the canvas for navigation.

    Example:
        >>> summary = NodeExecutionSummary(
        ...     node_id="abc123",
        ...     node_name="Process Data",
        ...     node_type="code",
        ...     status=NodeExecutionStatus.SUCCESS,
        ...     execution_time_ms=45.2,
        ...     location_x=100.0,
        ...     location_y=200.0,
        ... )
        >>> summary.succeeded
        True
        >>> summary.has_errors
        False
    """

    node_id: str
    node_name: str
    node_type: str
    status: NodeExecutionStatus = NodeExecutionStatus.PENDING
    errors: List[ErrorReport] = field(default_factory=list)
    execution_time_ms: Optional[float] = None
    skip_reason: Optional[str] = None
    location_x: float = 0.0
    location_y: float = 0.0

    @property
    def succeeded(self) -> bool:
        """Check if the node executed successfully."""
        return self.status == NodeExecutionStatus.SUCCESS

    @property
    def failed(self) -> bool:
        """Check if the node failed during execution."""
        return self.status == NodeExecutionStatus.FAILED

    @property
    def skipped(self) -> bool:
        """Check if the node was skipped."""
        return self.status == NodeExecutionStatus.SKIPPED

    @property
    def has_errors(self) -> bool:
        """Check if the node has any errors."""
        return len(self.errors) > 0

    @property
    def error_count(self) -> int:
        """Get the number of errors for this node."""
        return len(self.errors)

    @property
    def first_error_message(self) -> Optional[str]:
        """Get the message from the first error, if any.

        Returns:
            The error message from the first error, or None if no errors.
        """
        if self.errors:
            return self.errors[0].message
        return None

    def add_error(self, error: ErrorReport) -> None:
        """Add an error to this summary.

        Args:
            error: The ErrorReport to add.
        """
        self.errors.append(error)
        # Automatically set status to FAILED when an error is added
        self.status = NodeExecutionStatus.FAILED

    @classmethod
    def from_node(
        cls,
        node: BaseNode,
        status: NodeExecutionStatus = NodeExecutionStatus.PENDING,
        execution_time_ms: Optional[float] = None,
        skip_reason: Optional[str] = None,
    ) -> NodeExecutionSummary:
        """
        Create a NodeExecutionSummary from a BaseNode instance.

        Args:
            node: The node to create a summary for.
            status: The execution status of the node.
            execution_time_ms: The execution time in milliseconds.
            skip_reason: Reason the node was skipped (if applicable).

        Returns:
            NodeExecutionSummary with node information and execution status.
        """
        summary = cls(
            node_id=node.id,
            node_name=node.name,
            node_type=node.node_type,
            status=status,
            errors=node.execution_errors.copy(),
            execution_time_ms=execution_time_ms,
            skip_reason=skip_reason,
            location_x=node.position.x,
            location_y=node.position.y,
        )
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_type": self.node_type,
            "status": self.status.name,
            "errors": [error.to_dict() for error in self.errors],
            "execution_time_ms": self.execution_time_ms,
            "skip_reason": self.skip_reason,
            "location_x": self.location_x,
            "location_y": self.location_y,
        }

    def __repr__(self) -> str:
        """Get a string representation of the summary."""
        error_info = f", errors={self.error_count}" if self.has_errors else ""
        time_info = f", time={self.execution_time_ms:.1f}ms" if self.execution_time_ms else ""
        return (
            f"NodeExecutionSummary("
            f"node='{self.node_name}', "
            f"status={self.status.name}"
            f"{error_info}{time_info})"
        )


@dataclass
class NodeExecutionRecord:
    """
    Record of a single node's execution.

    Attributes:
        node_id: The ID of the executed node.
        node_type: The type of the node.
        node_name: The name of the node.
        inputs: The inputs provided to the node.
        outputs: The outputs produced by the node.
        started_at: When execution started.
        completed_at: When execution completed.
        error: Error message if execution failed.
        execution_time_ms: Execution time in milliseconds.
        location_x: X coordinate of the node on the canvas.
        location_y: Y coordinate of the node on the canvas.
        input_types: Inferred types for each input value.
        output_types: Inferred types for each output value.
    """

    node_id: str
    node_type: str
    node_name: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    location_x: float = 0.0
    location_y: float = 0.0
    input_types: Dict[str, Any] = field(default_factory=dict)
    output_types: Dict[str, Any] = field(default_factory=dict)

    @property
    def execution_time_ms(self) -> Optional[float]:
        """Calculate execution time in milliseconds."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds() * 1000
        return None

    @property
    def succeeded(self) -> bool:
        """Check if execution succeeded."""
        return self.error is None and self.completed_at is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "node_name": self.node_name,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "location_x": self.location_x,
            "location_y": self.location_y,
            "input_types": self.input_types,
            "output_types": self.output_types,
        }


@dataclass
class ExecutionResult:
    """
    Result of executing a visual script.

    Attributes:
        status: The final execution status.
        started_at: When execution started.
        completed_at: When execution completed.
        node_records: Records of each node's execution.
        final_outputs: Final outputs from end nodes.
        error: Error message if execution failed.
        error_node_id: ID of the node where error occurred.
        error_report: Detailed error report with location and context.
        error_node_location: Location information for the error node.
        node_summaries: Dictionary mapping node_id to NodeExecutionSummary
            for the execution summary panel.
    """

    status: ExecutionStatus = ExecutionStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    node_records: List[NodeExecutionRecord] = field(default_factory=list)
    final_outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_node_id: Optional[str] = None
    error_report: Optional[ErrorReport] = None
    error_node_location: Optional[NodeLocation] = None
    node_summaries: Dict[str, "NodeExecutionSummary"] = field(default_factory=dict)

    @property
    def execution_time_ms(self) -> Optional[float]:
        """Calculate total execution time in milliseconds."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds() * 1000
        return None

    @property
    def succeeded(self) -> bool:
        """Check if execution succeeded."""
        return self.status == ExecutionStatus.COMPLETED

    @property
    def nodes_executed(self) -> int:
        """Get the number of nodes executed."""
        return len(self.node_records)

    def get_error_location_info(self) -> Optional[Dict[str, Any]]:
        """
        Get error location information for debugging.

        Returns:
            Dictionary with node location info if an error occurred, None otherwise.
        """
        if not self.error_node_location:
            return None
        return self.error_node_location.to_dict()

    def get_execution_path(self) -> List[str]:
        """
        Get the list of node IDs that were executed before the error.

        Returns:
            List of node IDs in execution order.
        """
        return [record.node_id for record in self.node_records]

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "status": self.status.name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "node_records": [r.to_dict() for r in self.node_records],
            "final_outputs": self.final_outputs,
            "error": self.error,
            "error_node_id": self.error_node_id,
            "error_report": self.error_report.to_dict() if self.error_report else None,
            "error_node_location": self.error_node_location.to_dict() if self.error_node_location else None,
            "execution_time_ms": self.execution_time_ms,
            "nodes_executed": self.nodes_executed,
            "node_summaries": {
                node_id: summary.to_dict()
                for node_id, summary in self.node_summaries.items()
            },
        }


class ExecutionContext:
    """
    Maintains execution state during script execution.

    The ExecutionContext tracks:
    - Node outputs for data flow between nodes
    - Execution history for debugging and visualization
    - Global variables accessible to all nodes
    - Case variables for per-execution shared state
    - Error state and cancellation
    - Per-node errors (collected without stopping execution)
    - Skipped nodes due to upstream failures
    - Node execution summaries for the summary panel

    Example:
        >>> context = ExecutionContext()
        >>> context.set_node_output("node1", "result", 42)
        >>> value = context.get_node_output("node1", "result")
        >>> print(value)
        42
        >>> # Case variables for shared state
        >>> context.case.set("counter", 0)
        >>> context.case.counter += 1
        >>> # Record a node error without stopping execution
        >>> from visualpython.execution.error_report import ErrorReport, ErrorCategory
        >>> error = ErrorReport(error_id="err1", category=ErrorCategory.RUNTIME, message="Test error")
        >>> context.record_node_error("node2", error)
        >>> # Mark downstream nodes as skipped
        >>> context.mark_node_skipped("node3", "Upstream node 'node2' failed")
    """

    def __init__(self) -> None:
        """Initialize a new execution context."""
        self._status: ExecutionStatus = ExecutionStatus.PENDING
        self._started_at: Optional[datetime] = None
        self._completed_at: Optional[datetime] = None

        # Node outputs: {node_id: {port_name: value}}
        self._node_outputs: Dict[str, Dict[str, Any]] = {}

        # Nodes that have been executed
        self._executed_nodes: Set[str] = set()

        # Nodes currently executing (for loop detection)
        self._executing_nodes: Set[str] = set()

        # Execution history
        self._execution_records: List[NodeExecutionRecord] = []

        # Current record being built
        self._current_record: Optional[NodeExecutionRecord] = None

        # Error tracking (legacy - for first/fatal error)
        self._error: Optional[str] = None
        self._error_node_id: Optional[str] = None
        self._error_report: Optional[ErrorReport] = None
        self._error_node_location: Optional[NodeLocation] = None

        # Per-node error collection (for continue-on-error execution)
        # Maps node_id -> list of ErrorReport objects
        self._node_errors: Dict[str, List[ErrorReport]] = {}

        # Set of node IDs that were skipped (due to upstream failures)
        self._skipped_nodes: Set[str] = set()

        # Skip reasons: node_id -> reason string
        self._skip_reasons: Dict[str, str] = {}

        # Nodes that failed (for quick lookup)
        self._failed_nodes: Set[str] = set()

        # Node execution summaries for the summary panel
        self._node_summaries: Dict[str, NodeExecutionSummary] = {}

        # Cancellation flag
        self._cancelled: bool = False

        # Pause/resume state for breakpoints
        self._paused: bool = False
        self._paused_node_id: Optional[str] = None
        self._resume_event: Optional[Any] = None  # threading.Event when paused

        # Step-through execution mode
        self._step_mode: bool = False
        self._step_pending: bool = False  # True when waiting for step command

        # Global execution namespace for exec()
        self._global_namespace: Dict[str, Any] = {}

        # Type inference tracking
        # Maps (node_id, port_name) -> TypeInfo
        self._inferred_output_types: Dict[tuple, TypeInfo] = {}
        self._inferred_input_types: Dict[tuple, TypeInfo] = {}
        self._type_mismatches: List[TypeMismatch] = []

        # Case context for per-execution shared state (lazy initialization)
        self._case: Optional[Case] = None

    @property
    def case(self) -> Case:
        """
        Get the Case instance for per-execution shared state.

        The Case is lazily initialized on first access. It provides a
        shared context for variables that need to be accessed across
        all nodes during a single execution run.

        Unlike GlobalVariableStore, Case variables are automatically
        cleared when the execution context is reset.

        Returns:
            The Case instance for this execution context.

        Example:
            >>> context = ExecutionContext()
            >>> context.case.set("counter", 0)
            >>> context.case.counter
            0
            >>> context.case.increment("counter")
            1
        """
        if self._case is None:
            from visualpython.execution.case import Case
            self._case = Case()
        return self._case

    @property
    def status(self) -> ExecutionStatus:
        """Get the current execution status."""
        return self._status

    @property
    def is_running(self) -> bool:
        """Check if execution is currently running."""
        return self._status == ExecutionStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        """Check if execution has completed (successfully or with failure)."""
        return self._status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        )

    @property
    def error(self) -> Optional[str]:
        """Get the error message if execution failed."""
        return self._error

    @property
    def error_node_id(self) -> Optional[str]:
        """Get the ID of the node where error occurred."""
        return self._error_node_id

    def start(self) -> None:
        """Mark execution as started."""
        self._status = ExecutionStatus.RUNNING
        self._started_at = datetime.now()
        self._error = None
        self._error_node_id = None
        self._cancelled = False

    def complete(self) -> None:
        """Mark execution as completed successfully."""
        self._status = ExecutionStatus.COMPLETED
        self._completed_at = datetime.now()

    def fail(
        self,
        error: str,
        node_id: Optional[str] = None,
        error_report: Optional[ErrorReport] = None,
        node_location: Optional[NodeLocation] = None,
    ) -> None:
        """
        Mark execution as failed.

        Args:
            error: The error message.
            node_id: Optional ID of the node where error occurred.
            error_report: Optional detailed error report with context.
            node_location: Optional location information for the error node.
        """
        self._status = ExecutionStatus.FAILED
        self._completed_at = datetime.now()
        self._error = error
        self._error_node_id = node_id
        self._error_report = error_report
        self._error_node_location = node_location

    def cancel(self) -> None:
        """Cancel the execution."""
        self._cancelled = True
        self._status = ExecutionStatus.CANCELLED
        self._completed_at = datetime.now()

    def is_cancelled(self) -> bool:
        """Check if execution has been cancelled."""
        return self._cancelled

    # Pause/resume functionality for breakpoints

    def pause(self, node_id: str) -> None:
        """
        Pause execution at a breakpoint.

        Args:
            node_id: The ID of the breakpoint node where execution paused.
        """
        import threading
        self._paused = True
        self._paused_node_id = node_id
        self._status = ExecutionStatus.PAUSED
        self._resume_event = threading.Event()

    def resume(self) -> None:
        """Resume execution after being paused at a breakpoint."""
        self._paused = False
        self._paused_node_id = None
        self._status = ExecutionStatus.RUNNING
        if self._resume_event:
            self._resume_event.set()
            self._resume_event = None

    def is_paused(self) -> bool:
        """Check if execution is currently paused at a breakpoint."""
        return self._paused

    def get_paused_node_id(self) -> Optional[str]:
        """Get the ID of the node where execution is paused."""
        return self._paused_node_id

    def wait_for_resume(self, timeout: Optional[float] = None) -> bool:
        """
        Block until execution is resumed.

        Args:
            timeout: Optional timeout in seconds. If None, waits indefinitely.

        Returns:
            True if resumed, False if timeout occurred or cancelled.
        """
        if not self._resume_event:
            return True

        # Check for cancellation while waiting
        while self._paused and not self._cancelled:
            if self._resume_event.wait(timeout=0.1):
                return True
            if timeout is not None:
                timeout -= 0.1
                if timeout <= 0:
                    return False

        return not self._cancelled

    # Step-through execution mode

    @property
    def step_mode(self) -> bool:
        """Check if step-through execution mode is enabled."""
        return self._step_mode

    def enable_step_mode(self) -> None:
        """Enable step-through execution mode."""
        self._step_mode = True

    def disable_step_mode(self) -> None:
        """Disable step-through execution mode."""
        self._step_mode = False
        self._step_pending = False

    def is_step_pending(self) -> bool:
        """Check if execution is waiting for a step command."""
        return self._step_pending

    def pause_for_step(self, node_id: str) -> None:
        """
        Pause execution for step-through debugging at a node.

        Args:
            node_id: The ID of the node where execution paused.
        """
        import threading
        self._paused = True
        self._step_pending = True
        self._paused_node_id = node_id
        self._status = ExecutionStatus.PAUSED
        self._resume_event = threading.Event()

    def step(self) -> None:
        """
        Execute the next step in step-through mode.

        Resumes execution to the next pause point.
        """
        self._step_pending = False
        if self._resume_event:
            self._resume_event.set()
            self._resume_event = None
        self._paused = False
        self._status = ExecutionStatus.RUNNING

    def continue_execution(self) -> None:
        """
        Continue execution normally (exit step mode for current run).

        Disables step mode and resumes execution without pausing.
        """
        self._step_mode = False
        self._step_pending = False
        self.resume()

    # Node output management

    def set_node_output(self, node_id: str, port_name: str, value: Any) -> None:
        """
        Set an output value for a node's port.

        Args:
            node_id: The ID of the node.
            port_name: The name of the output port.
            value: The value to store.
        """
        if node_id not in self._node_outputs:
            self._node_outputs[node_id] = {}
        self._node_outputs[node_id][port_name] = value

    def set_node_outputs(self, node_id: str, outputs: Dict[str, Any]) -> None:
        """
        Set all output values for a node.

        Args:
            node_id: The ID of the node.
            outputs: Dictionary of port names to values.
        """
        self._node_outputs[node_id] = outputs.copy()

    def get_node_output(self, node_id: str, port_name: str) -> Optional[Any]:
        """
        Get an output value from a node's port.

        Args:
            node_id: The ID of the node.
            port_name: The name of the output port.

        Returns:
            The stored value, or None if not found.
        """
        if node_id in self._node_outputs:
            return self._node_outputs[node_id].get(port_name)
        return None

    def get_node_outputs(self, node_id: str) -> Dict[str, Any]:
        """
        Get all output values for a node.

        Args:
            node_id: The ID of the node.

        Returns:
            Dictionary of port names to values.
        """
        return self._node_outputs.get(node_id, {}).copy()

    def has_node_output(self, node_id: str, port_name: str) -> bool:
        """Check if a node output exists."""
        if node_id in self._node_outputs:
            return port_name in self._node_outputs[node_id]
        return False

    # Execution tracking

    def mark_node_executed(self, node_id: str) -> None:
        """Mark a node as having been executed."""
        self._executed_nodes.add(node_id)
        self._executing_nodes.discard(node_id)

    def is_node_executed(self, node_id: str) -> bool:
        """Check if a node has been executed."""
        return node_id in self._executed_nodes

    def mark_node_executing(self, node_id: str) -> None:
        """Mark a node as currently executing."""
        self._executing_nodes.add(node_id)

    def is_node_executing(self, node_id: str) -> bool:
        """Check if a node is currently executing."""
        return node_id in self._executing_nodes

    def get_executed_node_ids(self) -> Set[str]:
        """Get the set of executed node IDs."""
        return self._executed_nodes.copy()

    # Per-node error collection (for continue-on-error execution)

    def record_node_error(
        self,
        node_id: str,
        error_report: ErrorReport,
    ) -> None:
        """
        Record an error for a specific node without stopping execution.

        This method allows the execution engine to collect errors from multiple
        nodes instead of stopping at the first error. The errors can then be
        displayed in the execution summary panel.

        Args:
            node_id: The ID of the node that encountered the error.
            error_report: The detailed error report.

        Example:
            >>> context = ExecutionContext()
            >>> from visualpython.execution.error_report import ErrorReport, ErrorCategory
            >>> error = ErrorReport(
            ...     error_id="err1",
            ...     category=ErrorCategory.RUNTIME,
            ...     message="Division by zero"
            ... )
            >>> context.record_node_error("node_abc", error)
            >>> context.has_node_errors("node_abc")
            True
        """
        if node_id not in self._node_errors:
            self._node_errors[node_id] = []
        self._node_errors[node_id].append(error_report)
        self._failed_nodes.add(node_id)

    def get_node_errors(self, node_id: str) -> List[ErrorReport]:
        """
        Get all errors recorded for a specific node.

        Args:
            node_id: The ID of the node.

        Returns:
            List of ErrorReport objects for this node (empty if no errors).
        """
        return self._node_errors.get(node_id, []).copy()

    def has_node_errors(self, node_id: str) -> bool:
        """
        Check if a node has any recorded errors.

        Args:
            node_id: The ID of the node.

        Returns:
            True if the node has errors, False otherwise.
        """
        return node_id in self._node_errors and len(self._node_errors[node_id]) > 0

    def get_all_node_errors(self) -> Dict[str, List[ErrorReport]]:
        """
        Get all errors organized by node ID.

        Returns:
            Dictionary mapping node_id to list of ErrorReport objects.
        """
        return {node_id: errors.copy() for node_id, errors in self._node_errors.items()}

    def get_failed_node_ids(self) -> Set[str]:
        """
        Get the set of node IDs that have errors.

        Returns:
            Set of node IDs that encountered errors.
        """
        return self._failed_nodes.copy()

    def get_total_error_count(self) -> int:
        """
        Get the total number of errors across all nodes.

        Returns:
            Total count of errors.
        """
        return sum(len(errors) for errors in self._node_errors.values())

    # Skipped node tracking

    def mark_node_skipped(self, node_id: str, reason: str) -> None:
        """
        Mark a node as skipped (e.g., due to upstream failure).

        Args:
            node_id: The ID of the node to skip.
            reason: The reason for skipping (e.g., "Upstream node 'X' failed").

        Example:
            >>> context = ExecutionContext()
            >>> context.mark_node_skipped("node_xyz", "Upstream node 'node_abc' failed")
            >>> context.is_node_skipped("node_xyz")
            True
            >>> context.get_skip_reason("node_xyz")
            "Upstream node 'node_abc' failed"
        """
        self._skipped_nodes.add(node_id)
        self._skip_reasons[node_id] = reason

    def is_node_skipped(self, node_id: str) -> bool:
        """
        Check if a node was skipped.

        Args:
            node_id: The ID of the node.

        Returns:
            True if the node was skipped, False otherwise.
        """
        return node_id in self._skipped_nodes

    def get_skip_reason(self, node_id: str) -> Optional[str]:
        """
        Get the reason a node was skipped.

        Args:
            node_id: The ID of the node.

        Returns:
            The skip reason, or None if the node wasn't skipped.
        """
        return self._skip_reasons.get(node_id)

    def get_skipped_node_ids(self) -> Set[str]:
        """
        Get the set of node IDs that were skipped.

        Returns:
            Set of skipped node IDs.
        """
        return self._skipped_nodes.copy()

    def is_node_failed(self, node_id: str) -> bool:
        """
        Check if a node failed during execution.

        Args:
            node_id: The ID of the node.

        Returns:
            True if the node failed, False otherwise.
        """
        return node_id in self._failed_nodes

    # Node execution summaries

    def set_node_summary(self, summary: NodeExecutionSummary) -> None:
        """
        Store a node execution summary.

        Args:
            summary: The NodeExecutionSummary to store.
        """
        self._node_summaries[summary.node_id] = summary

    def get_node_summary(self, node_id: str) -> Optional[NodeExecutionSummary]:
        """
        Get the execution summary for a specific node.

        Args:
            node_id: The ID of the node.

        Returns:
            The NodeExecutionSummary if available, None otherwise.
        """
        return self._node_summaries.get(node_id)

    def get_all_node_summaries(self) -> Dict[str, NodeExecutionSummary]:
        """
        Get all node execution summaries.

        Returns:
            Dictionary mapping node_id to NodeExecutionSummary.
        """
        return self._node_summaries.copy()

    def get_successful_node_count(self) -> int:
        """
        Get the count of nodes that executed successfully.

        Returns:
            Number of successful nodes.
        """
        return sum(
            1 for summary in self._node_summaries.values()
            if summary.status == NodeExecutionStatus.SUCCESS
        )

    def get_failed_node_count(self) -> int:
        """
        Get the count of nodes that failed.

        Returns:
            Number of failed nodes.
        """
        return len(self._failed_nodes)

    def get_skipped_node_count(self) -> int:
        """
        Get the count of nodes that were skipped.

        Returns:
            Number of skipped nodes.
        """
        return len(self._skipped_nodes)

    def get_execution_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive execution statistics.

        Returns:
            Dictionary with execution statistics including counts and percentages.
        """
        total = len(self._node_summaries)
        successful = self.get_successful_node_count()
        failed = self.get_failed_node_count()
        skipped = self.get_skipped_node_count()

        return {
            "total_nodes": total,
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "total_errors": self.get_total_error_count(),
            "success_rate": (successful / total * 100) if total > 0 else 0.0,
            "failure_rate": (failed / total * 100) if total > 0 else 0.0,
            "skip_rate": (skipped / total * 100) if total > 0 else 0.0,
        }

    # Execution records

    def begin_node_execution(self, node: BaseNode, inputs: Dict[str, Any]) -> None:
        """
        Begin recording a node's execution.

        Args:
            node: The node being executed.
            inputs: The inputs provided to the node.
        """
        self._current_record = NodeExecutionRecord(
            node_id=node.id,
            node_type=node.node_type,
            node_name=node.name,
            inputs=inputs.copy(),
            started_at=datetime.now(),
            location_x=node.position.x,
            location_y=node.position.y,
        )
        self.mark_node_executing(node.id)

    def end_node_execution(
        self,
        node: BaseNode,
        outputs: Dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        """
        End recording a node's execution.

        Args:
            node: The node that was executed.
            outputs: The outputs produced by the node.
            error: Error message if execution failed.
        """
        if self._current_record and self._current_record.node_id == node.id:
            self._current_record.outputs = outputs.copy()
            self._current_record.completed_at = datetime.now()
            self._current_record.error = error
            self._execution_records.append(self._current_record)
            self._current_record = None

        if error is None:
            self.mark_node_executed(node.id)
        else:
            self._executing_nodes.discard(node.id)

    def get_execution_records(self) -> List[NodeExecutionRecord]:
        """Get all execution records."""
        return self._execution_records.copy()

    # Global namespace

    @property
    def global_namespace(self) -> Dict[str, Any]:
        """Get the global namespace for exec()."""
        return self._global_namespace

    def set_global_variable(self, name: str, value: Any) -> None:
        """Set a variable in the global namespace."""
        self._global_namespace[name] = value

    def get_global_variable(self, name: str, default: Any = None) -> Any:
        """Get a variable from the global namespace."""
        return self._global_namespace.get(name, default)

    # Type inference tracking

    def set_output_type(
        self,
        node_id: str,
        port_name: str,
        type_info: TypeInfo,
    ) -> None:
        """
        Record the inferred type for an output port.

        Args:
            node_id: ID of the node.
            port_name: Name of the output port.
            type_info: The inferred TypeInfo.
        """
        self._inferred_output_types[(node_id, port_name)] = type_info

    def get_output_type(
        self,
        node_id: str,
        port_name: str,
    ) -> Optional[TypeInfo]:
        """
        Get the inferred type for an output port.

        Args:
            node_id: ID of the node.
            port_name: Name of the output port.

        Returns:
            The TypeInfo if available, None otherwise.
        """
        return self._inferred_output_types.get((node_id, port_name))

    def set_input_type(
        self,
        node_id: str,
        port_name: str,
        type_info: TypeInfo,
    ) -> None:
        """
        Record the inferred type for an input port.

        Args:
            node_id: ID of the node.
            port_name: Name of the input port.
            type_info: The inferred TypeInfo.
        """
        self._inferred_input_types[(node_id, port_name)] = type_info

    def get_input_type(
        self,
        node_id: str,
        port_name: str,
    ) -> Optional[TypeInfo]:
        """
        Get the inferred type for an input port.

        Args:
            node_id: ID of the node.
            port_name: Name of the input port.

        Returns:
            The TypeInfo if available, None otherwise.
        """
        return self._inferred_input_types.get((node_id, port_name))

    def record_type_mismatch(self, mismatch: TypeMismatch) -> None:
        """
        Record a detected type mismatch.

        Args:
            mismatch: The TypeMismatch to record.
        """
        self._type_mismatches.append(mismatch)

    def get_type_mismatches(self) -> List[TypeMismatch]:
        """Get all recorded type mismatches."""
        return self._type_mismatches.copy()

    def get_all_inferred_types(self) -> Dict[str, Dict[str, TypeInfo]]:
        """
        Get all inferred types organized by node.

        Returns:
            Dictionary mapping node_id to dict of port_name -> TypeInfo.
        """
        result: Dict[str, Dict[str, TypeInfo]] = {}

        for (node_id, port_name), type_info in self._inferred_output_types.items():
            if node_id not in result:
                result[node_id] = {}
            result[node_id][f"output.{port_name}"] = type_info

        for (node_id, port_name), type_info in self._inferred_input_types.items():
            if node_id not in result:
                result[node_id] = {}
            result[node_id][f"input.{port_name}"] = type_info

        return result

    # Result generation

    def get_result(self) -> ExecutionResult:
        """
        Generate the final execution result.

        Returns:
            ExecutionResult containing all execution information.
        """
        result = ExecutionResult(
            status=self._status,
            started_at=self._started_at,
            completed_at=self._completed_at,
            node_records=self._execution_records.copy(),
            error=self._error,
            error_node_id=self._error_node_id,
            error_report=self._error_report,
            error_node_location=self._error_node_location,
            node_summaries=self._node_summaries.copy(),
        )

        # Collect final outputs from all nodes
        for node_id, outputs in self._node_outputs.items():
            for port_name, value in outputs.items():
                result.final_outputs[f"{node_id}.{port_name}"] = value

        return result

    def reset(self) -> None:
        """Reset the context for a new execution."""
        self._status = ExecutionStatus.PENDING
        self._started_at = None
        self._completed_at = None
        self._node_outputs.clear()
        self._executed_nodes.clear()
        self._executing_nodes.clear()
        self._execution_records.clear()
        self._current_record = None
        self._error = None
        self._error_node_id = None
        self._error_report = None
        self._error_node_location = None
        self._cancelled = False
        self._paused = False
        self._paused_node_id = None
        self._resume_event = None
        self._step_mode = False
        self._step_pending = False
        self._global_namespace.clear()
        # Reset type inference tracking
        self._inferred_output_types.clear()
        self._inferred_input_types.clear()
        self._type_mismatches.clear()
        # Reset Case context (set to None for lazy re-initialization)
        self._case = None
        # Reset per-node error collection
        self._node_errors.clear()
        self._skipped_nodes.clear()
        self._skip_reasons.clear()
        self._failed_nodes.clear()
        self._node_summaries.clear()

    def __repr__(self) -> str:
        """Get a string representation of the context."""
        return (
            f"ExecutionContext(status={self._status.name}, "
            f"executed={len(self._executed_nodes)}, "
            f"failed={len(self._failed_nodes)}, "
            f"skipped={len(self._skipped_nodes)}, "
            f"records={len(self._execution_records)})"
        )
