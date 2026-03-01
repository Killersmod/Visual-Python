"""
Execution engine for running visual Python scripts.

This module provides the ExecutionEngine class that executes generated Python
scripts using exec() with proper context management, enabling the running
of visual scripts.
"""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

from visualpython.compiler.ast_validator import validate_python_code, ValidationMode
from visualpython.execution.context import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    NodeExecutionStatus,
    NodeExecutionSummary,
)
from visualpython.execution.error_report import (
    ErrorCategory,
    ErrorReport,
    NodeLocation,
)
from visualpython.execution.type_info import TypeInfo
from visualpython.execution.type_inference import TypeInferenceEngine, TypeMismatch
from visualpython.nodes.models.base_node import ExecutionState
from visualpython.variables import GlobalVariableStore

if TYPE_CHECKING:
    from visualpython.execution.case import Case
    from visualpython.graph.graph import Graph
    from visualpython.nodes.models.base_node import BaseNode


# Thread-local storage for the current execution Case instance.
# This allows nodes to access the Case during execution without
# modifying the execute() method signature.
_execution_local = threading.local()


def get_current_case() -> Optional[Case]:
    """
    Get the Case instance for the current execution.

    This function returns the Case instance that is active during
    the current graph execution. It can be used by nodes that need
    to access per-execution shared state.

    Returns:
        The current Case instance, or None if no execution is in progress.

    Example:
        >>> from visualpython.execution.engine import get_current_case
        >>> case = get_current_case()
        >>> if case:
        ...     case.set("counter", 0)
        ...     case.counter += 1
    """
    return getattr(_execution_local, "case", None)


def _set_current_case(case: Optional[Case]) -> None:
    """
    Set the Case instance for the current execution.

    This is an internal function used by the ExecutionEngine to
    make the Case available during node execution.

    Args:
        case: The Case instance to set, or None to clear.
    """
    _execution_local.case = case


class ExecutionError(Exception):
    """Exception raised when script execution fails."""

    def __init__(
        self,
        message: str,
        node_id: Optional[str] = None,
        original_error: Optional[Exception] = None,
        node_location: Optional[NodeLocation] = None,
        error_report: Optional[ErrorReport] = None,
    ) -> None:
        """
        Initialize an execution error.

        Args:
            message: Error description.
            node_id: Optional ID of the node that caused the error.
            original_error: The original exception that was caught.
            node_location: Optional location information for the node.
            error_report: Optional detailed error report with context.
        """
        self.node_id = node_id
        self.original_error = original_error
        self.node_location = node_location
        self.error_report = error_report
        self.stack_trace: Optional[str] = None

        # Capture stack trace if original error exists
        if original_error:
            self.stack_trace = "".join(traceback.format_exception(
                type(original_error), original_error, original_error.__traceback__
            ))

        super().__init__(message)

    @property
    def has_location(self) -> bool:
        """Check if location information is available."""
        return self.node_location is not None

    def get_location_info(self) -> Optional[Dict[str, Any]]:
        """Get location information as a dictionary."""
        if self.node_location:
            return self.node_location.to_dict()
        return None

    def get_formatted_error(self) -> str:
        """Get a formatted error message with location info."""
        lines = [str(self)]
        if self.node_location:
            lines.append(f"  Node: {self.node_location.node_name} ({self.node_location.node_type})")
            lines.append(f"  Position: ({self.node_location.x:.1f}, {self.node_location.y:.1f})")
        if self.error_report and self.error_report.suggestions:
            lines.append("  Suggestions:")
            for suggestion in self.error_report.suggestions:
                lines.append(f"    - {suggestion}")
        return "\n".join(lines)


class ExecutionEngine:
    """
    Engine for executing visual Python scripts.

    The ExecutionEngine traverses a graph of nodes and executes each node
    in the correct order, respecting data flow and control flow connections.
    It uses Python's exec() to execute code nodes and manages the execution
    context for sharing data between nodes.

    The engine supports:
    - Sequential execution following flow connections
    - Data flow between nodes via ports
    - Control flow with if/else branching
    - For loop iteration
    - Parallel execution via thread nodes
    - Global variable access via GlobalVariableStore
    - Execution state tracking and error handling

    Example:
        >>> from visualpython.graph.graph import Graph
        >>> graph = Graph()
        >>> # ... build graph with nodes ...
        >>> engine = ExecutionEngine(graph)
        >>> result = engine.execute()
        >>> if result.succeeded:
        ...     print("Execution completed successfully!")
    """

    def __init__(
        self,
        graph: Graph,
        on_node_start: Optional[Callable[[BaseNode], None]] = None,
        on_node_complete: Optional[Callable[[BaseNode, Dict[str, Any]], None]] = None,
        on_node_error: Optional[Callable[[BaseNode, Exception], None]] = None,
        on_node_skipped: Optional[Callable[[BaseNode, str], None]] = None,
        on_step_paused: Optional[Callable[[BaseNode], None]] = None,
        on_type_inferred: Optional[Callable[[str, str, TypeInfo], None]] = None,
        on_type_mismatch: Optional[Callable[[TypeMismatch], None]] = None,
        step_mode: bool = False,
        enable_type_inference: bool = True,
        strict_type_checking: bool = False,
        continue_on_error: bool = True,
    ) -> None:
        """
        Initialize the execution engine.

        Args:
            graph: The graph to execute.
            on_node_start: Optional callback when a node starts executing.
            on_node_complete: Optional callback when a node completes.
            on_node_error: Optional callback when a node encounters an error.
            on_node_skipped: Optional callback when a node is skipped (e.g., due to
                upstream failure). Receives the node and the skip reason.
            on_step_paused: Optional callback when execution pauses for step-through.
            on_type_inferred: Optional callback when a type is inferred.
            on_type_mismatch: Optional callback when a type mismatch is detected.
            step_mode: Whether to start in step-through execution mode.
            enable_type_inference: Whether to enable runtime type inference.
            strict_type_checking: If True, type mismatches cause execution errors.
            continue_on_error: If True, execution continues after node errors,
                marking downstream nodes as skipped. If False, execution stops
                at the first error (legacy behavior).
        """
        self._graph = graph
        self._context = ExecutionContext()
        self._on_node_start = on_node_start
        self._on_node_complete = on_node_complete
        self._on_node_error = on_node_error
        self._on_node_skipped = on_node_skipped
        self._on_step_paused = on_step_paused
        self._on_type_inferred = on_type_inferred
        self._on_type_mismatch = on_type_mismatch
        self._thread_lock = threading.Lock()
        self._thread_errors: Dict[str, Exception] = {}

        # Continue-on-error mode configuration
        self._continue_on_error = continue_on_error

        # Type inference configuration
        self._enable_type_inference = enable_type_inference
        self._strict_type_checking = strict_type_checking
        self._type_inference_engine: Optional[TypeInferenceEngine] = None

        if enable_type_inference:
            self._type_inference_engine = TypeInferenceEngine(
                on_type_inferred=on_type_inferred,
                on_mismatch_detected=self._handle_type_mismatch,
                strict_mode=strict_type_checking,
            )

        if step_mode:
            self._context.enable_step_mode()

    @property
    def graph(self) -> Graph:
        """Get the graph being executed."""
        return self._graph

    @property
    def context(self) -> ExecutionContext:
        """Get the execution context."""
        return self._context

    @property
    def type_inference_engine(self) -> Optional[TypeInferenceEngine]:
        """Get the type inference engine if enabled."""
        return self._type_inference_engine

    @property
    def continue_on_error(self) -> bool:
        """Check if continue-on-error mode is enabled."""
        return self._continue_on_error

    @continue_on_error.setter
    def continue_on_error(self, value: bool) -> None:
        """Set continue-on-error mode."""
        self._continue_on_error = value

    def _handle_type_mismatch(self, mismatch: TypeMismatch) -> None:
        """
        Handle a detected type mismatch.

        Args:
            mismatch: The detected TypeMismatch.
        """
        # Record in context
        self._context.record_type_mismatch(mismatch)

        # Notify callback
        if self._on_type_mismatch:
            self._on_type_mismatch(mismatch)

        # In strict mode, this would already be marked as an error in the engine

    def execute(self) -> ExecutionResult:
        """
        Execute the visual script.

        This method:
        1. Validates the graph
        2. Finds start nodes
        3. Executes nodes in flow order
        4. Returns the execution result

        The Case instance from the execution context is made available
        during execution via the get_current_case() function, allowing
        nodes to access per-execution shared state.

        Returns:
            ExecutionResult containing execution status and outputs.
        """
        # Preserve step mode before reset
        was_step_mode = self._context.step_mode

        # Reset context and graph state
        self._context.reset()
        self._graph.reset_execution_state()

        # Reset type inference engine
        if self._type_inference_engine:
            self._type_inference_engine.reset()
            # Register all port types for type checking
            self._register_all_port_types()

        # Restore step mode after reset
        if was_step_mode:
            self._context.enable_step_mode()

        # Clear and prepare global variable store
        global_store = GlobalVariableStore.get_instance()
        global_store.clear()

        # Make the Case instance available for nodes during execution
        _set_current_case(self._context.case)

        # Start execution
        self._context.start()

        try:
            # Validate graph
            errors = self._validate_graph()
            if errors:
                logger.error("Graph validation failed: %s", errors)
                self._context.fail("; ".join(errors))
                return self._context.get_result()

            # Find start nodes
            start_nodes = self._graph.get_nodes_by_type("start")
            if not start_nodes:
                all_types = [n.node_type for n in self._graph.nodes]
                logger.error(
                    "No start node found in graph (id=%s). "
                    "Graph has %d nodes, types: %s",
                    id(self._graph), len(self._graph.nodes), all_types,
                )
                self._context.fail("Graph must have at least one Start node")
                return self._context.get_result()

            # Execute from each start node
            for start_node in start_nodes:
                if self._context.is_cancelled():
                    break
                self._execute_from_node(start_node)

            # Check for cancellation
            if self._context.is_cancelled():
                return self._context.get_result()

            # Check if there were errors in continue-on-error mode
            # In this mode, we complete execution even with errors
            if self._continue_on_error and self._context.get_failed_node_count() > 0:
                # Execution completed but with errors - still mark as COMPLETED
                # The ExecutionResult will contain the error information
                self._context.complete()
            else:
                # Mark as completed (normal case, no errors)
                self._context.complete()

        except ExecutionError as e:
            logger.error("Execution error in node %s: %s", e.node_id, e, exc_info=True)
            self._context.fail(
                str(e),
                node_id=e.node_id,
                error_report=e.error_report,
                node_location=e.node_location,
            )
        except Exception as e:
            logger.error("Unexpected execution error: %s", e, exc_info=True)
            # Create error report for unexpected errors
            unexpected_report = ErrorReport.from_exception(
                exception=e,
                node=None,
                execution_path=[r.node_id for r in self._context.get_execution_records()],
            )
            self._context.fail(
                f"Unexpected error: {str(e)}",
                error_report=unexpected_report,
            )
        finally:
            # Clear the Case from thread-local storage after execution completes
            _set_current_case(None)

        return self._context.get_result()

    def execute_single_node(
        self,
        node: BaseNode,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a single node with provided inputs.

        This is useful for testing individual nodes or step-by-step execution.

        Args:
            node: The node to execute.
            inputs: Optional input values. If not provided, values are
                    gathered from connected nodes.

        Returns:
            Dictionary of output values from the node.

        Raises:
            ExecutionError: If execution fails.
        """
        if inputs is None:
            inputs = self._gather_inputs(node)

        return self._execute_node(node, inputs)

    def cancel(self) -> None:
        """Cancel the current execution."""
        self._context.cancel()

    def enable_step_mode(self) -> None:
        """Enable step-through execution mode."""
        self._context.enable_step_mode()

    def disable_step_mode(self) -> None:
        """Disable step-through execution mode."""
        self._context.disable_step_mode()

    @property
    def step_mode(self) -> bool:
        """Check if step mode is enabled."""
        return self._context.step_mode

    def step(self) -> None:
        """Execute the next step in step-through mode."""
        self._context.step()

    def continue_execution(self) -> None:
        """Continue execution normally (exit step mode for current run)."""
        self._context.continue_execution()

    def _register_all_port_types(self) -> None:
        """Register all port types from the graph for type inference."""
        if not self._type_inference_engine:
            return

        for node in self._graph.nodes:
            # Register output ports
            for port in node.output_ports:
                self._type_inference_engine.register_port(
                    node.id,
                    port.name,
                    port.port_type,
                    is_output=True,
                )
            # Register input ports
            for port in node.input_ports:
                self._type_inference_engine.register_port(
                    node.id,
                    port.name,
                    port.port_type,
                    is_output=False,
                )

    def _validate_graph(self) -> List[str]:
        """
        Validate the graph before execution.

        Returns:
            List of validation error messages.
        """
        errors: List[str] = []

        # Check for cycles (which would cause infinite execution)
        if self._graph.has_cycle():
            errors.append("Graph contains cycles which would cause infinite execution")

        # Check for start node
        start_nodes = self._graph.get_nodes_by_type("start")
        if not start_nodes:
            logger.warning(
                "Validation: no start node in graph (id=%s, %d nodes)",
                id(self._graph), len(self._graph.nodes),
            )
            errors.append("Graph must have at least one Start node")

        # Validate all nodes
        graph_errors = self._graph.validate()
        if graph_errors:
            logger.warning("Graph validation errors: %s", graph_errors)
        errors.extend(graph_errors)

        return errors

    def _execute_from_node(self, node: BaseNode) -> None:
        """
        Execute starting from a node and following flow connections.

        When continue_on_error mode is enabled:
        - If this node should be skipped (upstream failed), mark it skipped and skip downstream
        - If this node fails, record the error and skip downstream nodes
        - Execution continues with other branches

        Args:
            node: The node to start execution from.
        """
        if self._context.is_cancelled():
            return

        if self._context.is_node_executed(node.id):
            return

        # Check if this node should be skipped due to upstream failure
        if self._context.is_node_skipped(node.id):
            return

        # Check if any upstream node failed (for data dependencies)
        skip_reason = self._check_upstream_failures(node)
        if skip_reason:
            self._mark_node_and_downstream_skipped(node, skip_reason)
            return

        # Gather inputs from connected nodes
        inputs = self._gather_inputs(node)

        # Execute the node
        try:
            outputs = self._execute_node(node, inputs)
        except ExecutionError as e:
            if self._continue_on_error:
                # Record the error and mark downstream nodes as skipped
                self._handle_node_execution_error(node, e)
                return
            else:
                # Legacy behavior: re-raise the error
                raise
        except Exception as e:
            exec_error = ExecutionError(
                f"Failed to execute node '{node.name}': {str(e)}",
                node_id=node.id,
                original_error=e,
            )
            if self._continue_on_error:
                self._handle_node_execution_error(node, exec_error)
                return
            else:
                raise exec_error

        # Store outputs in context
        self._context.set_node_outputs(node.id, outputs)

        # Handle breakpoint nodes
        if node.node_type == "breakpoint":
            self._handle_breakpoint_flow(node, outputs)
            if self._context.is_cancelled():
                return

        # Handle control flow based on node type
        if node.node_type == "if":
            self._handle_if_flow(node, outputs)
        elif node.node_type == "for_loop":
            self._handle_for_loop_flow(node, inputs)
        elif node.node_type == "merge":
            self._handle_merge_flow(node)
        elif node.node_type == "thread":
            self._handle_thread_flow(node, inputs)
        elif node.node_type == "thread_join":
            self._handle_thread_join_flow(node, inputs)
        elif node.node_type == "subgraph":
            self._handle_subgraph_flow(node, inputs, outputs)
        else:
            # Follow standard execution flow
            self._follow_flow(node, "exec_out")

    def _check_upstream_failures(self, node: BaseNode) -> Optional[str]:
        """
        Check if any upstream node (connected via data ports) has failed.

        This ensures that nodes don't execute if they depend on data from
        failed nodes.

        Args:
            node: The node to check upstream failures for.

        Returns:
            Skip reason string if upstream failed, None otherwise.
        """
        for port in node.input_ports:
            # Only check data connections, not flow connections
            if port.port_type.name == "FLOW":
                continue

            if port.is_connected() and port.connection:
                source_node_id = port.connection.source_node_id
                # Check if the source node failed
                if self._context.is_node_failed(source_node_id):
                    source_node = self._graph.get_node(source_node_id)
                    source_name = source_node.name if source_node else source_node_id
                    return f"Upstream node '{source_name}' failed"
                # Check if the source node was skipped
                if self._context.is_node_skipped(source_node_id):
                    source_node = self._graph.get_node(source_node_id)
                    source_name = source_node.name if source_node else source_node_id
                    return f"Upstream node '{source_name}' was skipped"

        return None

    def _handle_node_execution_error(
        self,
        node: BaseNode,
        error: ExecutionError,
    ) -> None:
        """
        Handle a node execution error in continue-on-error mode.

        This records the error on the node and in the context, then marks
        all downstream nodes as skipped.

        Args:
            node: The node that failed.
            error: The execution error that occurred.
        """
        # Record the error in the context
        if error.error_report:
            self._context.record_node_error(node.id, error.error_report)
            # Also add the error to the node itself
            node.add_execution_error(error.error_report)
        else:
            # Create an error report if we don't have one
            error_report = ErrorReport.from_exception(
                exception=error.original_error or error,
                node=node,
                execution_path=[r.node_id for r in self._context.get_execution_records()],
            )
            self._context.record_node_error(node.id, error_report)
            node.add_execution_error(error_report)

        # Create and store a summary for this failed node
        record = self._context._current_record
        execution_time = record.execution_time_ms if record else None
        summary = NodeExecutionSummary.from_node(
            node,
            status=NodeExecutionStatus.FAILED,
            execution_time_ms=execution_time,
        )
        self._context.set_node_summary(summary)

        # Mark downstream nodes as skipped
        skip_reason = f"Upstream node '{node.name}' failed"
        self._mark_downstream_nodes_skipped(node, skip_reason)

    def _mark_node_and_downstream_skipped(
        self,
        node: BaseNode,
        reason: str,
    ) -> None:
        """
        Mark a node and all its downstream nodes as skipped.

        Args:
            node: The node to skip.
            reason: The reason for skipping.
        """
        # Skip this node
        self._mark_node_skipped(node, reason)

        # Skip all downstream nodes
        self._mark_downstream_nodes_skipped(node, f"Upstream node '{node.name}' was skipped")

    def _mark_node_skipped(self, node: BaseNode, reason: str) -> None:
        """
        Mark a single node as skipped.

        Args:
            node: The node to skip.
            reason: The reason for skipping.
        """
        # Update node state
        node.execution_state = ExecutionState.SKIPPED

        # Record in context
        self._context.mark_node_skipped(node.id, reason)

        # Create and store a summary for this skipped node
        summary = NodeExecutionSummary.from_node(
            node,
            status=NodeExecutionStatus.SKIPPED,
            skip_reason=reason,
        )
        self._context.set_node_summary(summary)

        # Notify callback
        if self._on_node_skipped:
            self._on_node_skipped(node, reason)

    def _mark_downstream_nodes_skipped(
        self,
        node: BaseNode,
        reason: str,
    ) -> None:
        """
        Mark all downstream nodes (via flow connections) as skipped.

        This recursively skips all nodes reachable from the given node's
        flow output ports.

        Args:
            node: The node whose downstream nodes should be skipped.
            reason: The reason for skipping (e.g., "Upstream node 'X' failed").
        """
        downstream_nodes = self._get_downstream_nodes(node)

        for downstream_node_id in downstream_nodes:
            if self._context.is_node_executed(downstream_node_id):
                # Already executed, don't skip
                continue
            if self._context.is_node_skipped(downstream_node_id):
                # Already skipped
                continue

            downstream_node = self._graph.get_node(downstream_node_id)
            if downstream_node:
                self._mark_node_skipped(downstream_node, reason)

    def _get_downstream_nodes(self, node: BaseNode) -> List[str]:
        """
        Get all node IDs that are downstream of the given node.

        This traverses all flow connections (exec_out, true_branch, false_branch,
        loop_body, completed, etc.) to find all reachable nodes.

        Args:
            node: The node to find downstream nodes for.

        Returns:
            List of downstream node IDs.
        """
        downstream_nodes: List[str] = []
        visited: set = set()

        def traverse(node_id: str) -> None:
            if node_id in visited:
                return
            visited.add(node_id)

            # Get all outgoing connections from this node
            connections = self._graph.get_outgoing_connections(node_id)
            for conn in connections:
                target_id = conn.target_node_id
                if target_id not in visited:
                    downstream_nodes.append(target_id)
                    traverse(target_id)

        # Start traversal from the given node
        traverse(node.id)

        return downstream_nodes

    def _execute_node(
        self,
        node: BaseNode,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a single node.

        Args:
            node: The node to execute.
            inputs: Input values for the node.

        Returns:
            Dictionary of output values.

        Raises:
            ExecutionError: If execution fails.
        """
        # Step mode: Pause before executing the node
        if self._context.step_mode and not self._context.is_cancelled():
            self._context.pause_for_step(node.id)

            # Notify step paused callback
            if self._on_step_paused:
                self._on_step_paused(node)

            # Wait for step command
            if not self._context.wait_for_resume():
                # Cancelled while waiting for step
                return {}

        # Begin recording
        self._context.begin_node_execution(node, inputs)

        # Update node state to RUNNING before notifying callback
        # This ensures UI can reflect the running state when the callback is invoked
        node.execution_state = ExecutionState.RUNNING

        # Notify start callback after state is set
        if self._on_node_start:
            self._on_node_start(node)

        try:
            # Execute the node
            outputs = node.execute(inputs)

            # Infer and record output types
            if self._type_inference_engine:
                for port_name, value in outputs.items():
                    type_info = self._type_inference_engine.record_output(
                        node.id, port_name, value
                    )
                    # Also store in context for persistence
                    self._context.set_output_type(node.id, port_name, type_info)
                    # Update the port's inferred type
                    output_port = node.get_output_port(port_name)
                    if output_port:
                        output_port.inferred_type = type_info

            # Update node state
            node.execution_state = ExecutionState.COMPLETED

            # End recording
            self._context.end_node_execution(node, outputs)

            # Create and store a summary for this successful node
            record = self._context._execution_records[-1] if self._context._execution_records else None
            execution_time = record.execution_time_ms if record else None
            summary = NodeExecutionSummary.from_node(
                node,
                status=NodeExecutionStatus.SUCCESS,
                execution_time_ms=execution_time,
            )
            self._context.set_node_summary(summary)

            # Notify complete callback
            if self._on_node_complete:
                self._on_node_complete(node, outputs)

            return outputs

        except Exception as e:
            # Update node state
            node.execution_state = ExecutionState.ERROR
            node.error_message = str(e)

            # Create node location for error tracking
            node_location = NodeLocation.from_node(node)

            # Get the execution path (nodes executed before this one)
            execution_path = [
                record.node_id for record in self._context.get_execution_records()
            ]

            # Create detailed error report
            error_report = ErrorReport.from_exception(
                exception=e,
                node=node,
                execution_path=execution_path,
                input_values=inputs,
            )

            # End recording with error
            self._context.end_node_execution(node, {}, str(e))

            # Notify error callback
            if self._on_node_error:
                self._on_node_error(node, e)

            raise ExecutionError(
                f"Node '{node.name}' execution failed: {str(e)}",
                node_id=node.id,
                original_error=e,
                node_location=node_location,
                error_report=error_report,
            )

    def _gather_inputs(self, node: BaseNode) -> Dict[str, Any]:
        """
        Gather input values for a node from connected sources.

        Value priority (highest to lowest):
        1. Connected value (from another node's output port)
        2. Inline value (user-entered via inline widget)
        3. Default value (defined in node definition)

        If a connected source node hasn't been executed yet, it will be
        executed on-demand (lazy evaluation). This enables pure data nodes
        (like Get Case Variable) to work without requiring explicit
        execution flow connections.

        Args:
            node: The node to gather inputs for.

        Returns:
            Dictionary of input port names to values.
        """
        inputs: Dict[str, Any] = {}

        for port in node.input_ports:
            # Skip flow ports for data gathering
            if port.port_type.name == "FLOW":
                continue

            if port.is_connected() and port.connection:
                # Get value from connected output port (highest priority)
                source_node_id = port.connection.source_node_id
                source_port_name = port.connection.source_port_name

                # If source node hasn't been executed yet, execute it on-demand
                if not self._context.is_node_executed(source_node_id):
                    self._execute_data_dependency(source_node_id)

                value = self._context.get_node_output(source_node_id, source_port_name)
                if value is not None:
                    inputs[port.name] = value

                    # Record input type and check for mismatches
                    if self._type_inference_engine:
                        mismatch = self._type_inference_engine.record_input(
                            node.id,
                            port.name,
                            value,
                            source_node_id,
                            source_port_name,
                        )
                        # Update port's inferred type
                        type_info = TypeInfo.from_value(value)
                        port.inferred_type = type_info
                        self._context.set_input_type(node.id, port.name, type_info)

                        # In strict mode, raise error on mismatch
                        if mismatch and self._strict_type_checking:
                            raise ExecutionError(
                                f"Type mismatch: {mismatch.message}",
                                node_id=node.id,
                            )
                else:
                    # Connection exists but no value yet - fall back to inline or default
                    fallback_value = port.get_effective_value()
                    if fallback_value is not None:
                        inputs[port.name] = fallback_value
            else:
                # No connection - use inline value if set, otherwise default value
                effective_value = port.get_effective_value()
                if effective_value is not None:
                    inputs[port.name] = effective_value

        return inputs

    def _execute_data_dependency(self, source_node_id: str) -> None:
        """
        Execute a source node on-demand to resolve a data dependency.

        This enables pure data nodes (e.g. Get Case Variable) to be evaluated
        lazily when their output is needed, without requiring them to be part
        of the explicit execution flow.

        Uses node.execute() directly rather than _execute_node() to avoid
        interfering with the execution tracking, UI callbacks, and step mode
        handling of the main execution pipeline.

        Args:
            source_node_id: The ID of the source node to execute.
        """
        if self._context.is_node_executed(source_node_id):
            return
        if self._context.is_cancelled():
            return

        source_node = self._graph.get_node(source_node_id)
        if source_node is None:
            return

        # Recursively gather inputs for the source node (may trigger further
        # on-demand executions up the dependency chain)
        source_inputs = self._gather_inputs(source_node)

        try:
            source_outputs = source_node.execute(source_inputs)
            self._context.set_node_outputs(source_node_id, source_outputs)
            self._context.mark_node_executed(source_node_id)
        except Exception as e:
            logger.warning(
                "On-demand execution of node '%s' (%s) failed: %s",
                source_node.name, source_node_id, e,
            )

    def _follow_flow(self, node: BaseNode, port_name: str) -> None:
        """
        Follow execution flow from a node's output port.

        Args:
            node: The source node.
            port_name: The name of the flow output port.
        """
        if self._context.is_cancelled():
            return

        # Get connections from this flow port
        connections = self._graph.get_connections_for_port(
            node.id, port_name, is_input=False
        )

        for connection in connections:
            target_node = self._graph.get_node(connection.target_node_id)
            if target_node:
                # Handle merge node - track which input was triggered
                if target_node.node_type == "merge":
                    from visualpython.nodes.models.merge_node import MergeNode
                    if isinstance(target_node, MergeNode):
                        target_node.trigger_input(connection.target_port_name)

                # Handle thread join node - mark thread as completed
                if target_node.node_type == "thread_join":
                    from visualpython.nodes.models.thread_join_node import ThreadJoinNode
                    if isinstance(target_node, ThreadJoinNode):
                        # Extract thread index from port name (thread_in_N)
                        port_name = connection.target_port_name
                        if port_name.startswith("thread_in_"):
                            try:
                                thread_idx = int(port_name.split("_")[-1])
                                # Get data from corresponding data port if available
                                data_port_name = f"data_in_{thread_idx}"
                                thread_data = self._context.get_node_output(
                                    node.id, "data_out"
                                ) if hasattr(node, "id") else None
                                target_node.mark_thread_completed(thread_idx, thread_data)
                            except (ValueError, IndexError):
                                logger.debug("Value conversion skipped", exc_info=True)
                                pass

                if not self._context.is_node_executed(target_node.id):
                    self._execute_from_node(target_node)

    def _handle_if_flow(self, node: BaseNode, outputs: Dict[str, Any]) -> None:
        """
        Handle execution flow for an if node.

        Args:
            node: The if node.
            outputs: The outputs from the if node execution.
        """
        result = outputs.get("result", False)

        if result:
            # Execute true branch
            self._follow_flow(node, "true_branch")
        else:
            # Execute false branch
            self._follow_flow(node, "false_branch")

    def _handle_breakpoint_flow(self, node: BaseNode, outputs: Dict[str, Any]) -> None:
        """
        Handle execution flow for a breakpoint node.

        When a breakpoint is hit and should pause:
        1. Pauses the execution context
        2. Notifies callbacks that a breakpoint was hit
        3. Waits for resume signal
        4. Continues execution after resume

        Args:
            node: The breakpoint node.
            outputs: The outputs from the breakpoint node execution.
        """
        from visualpython.nodes.models.breakpoint_node import BreakpointNode

        if not isinstance(node, BreakpointNode):
            return

        # Check if the breakpoint should pause
        was_paused = outputs.get("was_paused", False)

        if was_paused:
            # Pause execution
            self._context.pause(node.id)

            # Notify start callback that we're paused (UI can show paused state)
            if self._on_node_start:
                self._on_node_start(node)

            # Wait for resume signal
            resumed = self._context.wait_for_resume()

            if not resumed or self._context.is_cancelled():
                # Execution was cancelled while paused
                return

            # Clear the paused state on the node
            node.resume()

        # Continue to the next node
        self._follow_flow(node, "exec_out")

    def _handle_subgraph_flow(
        self,
        node: BaseNode,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
    ) -> None:
        """
        Handle execution flow for a subgraph node.

        Executes the internal graph of a SubgraphNode by:
        1. Building the internal graph from embedded data
        2. Setting input values on SubgraphInput nodes
        3. Executing internal nodes following flow connections
        4. Collecting outputs from SubgraphOutput nodes
        5. Continuing the outer flow

        Args:
            node: The subgraph node.
            inputs: The gathered input values for the subgraph.
            outputs: The outputs from SubgraphNode.execute() (placeholders).
        """
        from visualpython.nodes.models.subgraph_node import SubgraphNode

        if not isinstance(node, SubgraphNode):
            self._follow_flow(node, "exec_out")
            return

        graph_data = node.get_internal_graph_data()
        if not graph_data:
            self._follow_flow(node, "exec_out")
            return

        # Build the internal graph from embedded data
        from visualpython.nodes.registry import get_node_registry
        from visualpython.graph.graph import Graph

        registry = get_node_registry()

        def _node_factory(node_data: Dict[str, Any]) -> "BaseNode":
            """Create a node from serialized data using the registry."""
            node_type = node_data.get("type")
            if not node_type:
                raise ValueError("Node data missing 'type' field")
            node_type_info = registry.get_node_type(node_type)
            if node_type_info is None:
                raise ValueError(f"Unknown node type: '{node_type}'")
            return node_type_info.node_class.from_dict(node_data)

        try:
            internal_graph = Graph.from_dict(graph_data, _node_factory)
        except Exception as e:
            # If we can't build the internal graph, just follow the flow
            self._follow_flow(node, "exec_out")
            return

        # Set input values on SubgraphInput nodes
        for port_name, internal_node_id in node.input_mappings.items():
            internal_node = internal_graph.get_node(internal_node_id)
            if internal_node and port_name in inputs:
                # Store the value so SubgraphInput can provide it
                internal_node._default_value = inputs[port_name]

        # Find flow entry points from metadata
        metadata = graph_data.get("metadata", {})
        flow_entry_points = metadata.get("flow_entry_points", [])

        # Fallback: if no flow_entry_points in metadata, look for Start nodes
        if not flow_entry_points:
            for n in internal_graph.nodes:
                if n.node_type == "start":
                    flow_entry_points = [{"node_id": n.id}]
                    break

        # Execute internal nodes starting from flow entry points
        if flow_entry_points:
            # Create a nested engine for the internal graph (without requiring start nodes)
            nested_engine = _SubgraphExecutionEngine(internal_graph)
            for entry in flow_entry_points:
                entry_node = internal_graph.get_node(entry["node_id"])
                if entry_node:
                    nested_engine.execute_from(entry_node)

            # Collect outputs from SubgraphOutput nodes
            for port_name, internal_node_id in node.output_mappings.items():
                node_outputs = nested_engine.get_node_outputs(internal_node_id)
                if node_outputs:
                    value = node_outputs.get("_subgraph_output", node_outputs.get("value"))
                    if value is not None:
                        outputs[port_name] = value
                        self._context.set_node_outputs(node.id, outputs)

        # Continue outer flow
        self._follow_flow(node, "exec_out")

    def _handle_for_loop_flow(self, node: BaseNode, inputs: Dict[str, Any]) -> None:
        """
        Handle execution flow for a for loop node.

        Args:
            node: The for loop node.
            inputs: The inputs to the for loop.
        """
        from visualpython.nodes.models.for_loop_node import ForLoopNode

        if not isinstance(node, ForLoopNode):
            return

        iterable = inputs.get("iterable", [])

        # Iterate over each item
        for iteration_outputs in node.iterate(iterable):
            if self._context.is_cancelled():
                break

            # Store current iteration outputs
            self._context.set_node_outputs(node.id, iteration_outputs)

            # Execute loop body
            # Clear executed state for nodes in loop body to allow re-execution
            self._clear_loop_body_executed_state(node)
            self._follow_flow(node, "loop_body")

        # After loop completes, follow the completed flow
        if not self._context.is_cancelled():
            self._follow_flow(node, "completed")

    def _handle_merge_flow(self, node: BaseNode) -> None:
        """
        Handle execution flow for a merge node.

        The merge node converges multiple execution paths into a single
        continuation point. It tracks which inputs have been triggered
        and continues execution based on its merge strategy.

        Args:
            node: The merge node.
        """
        from visualpython.nodes.models.merge_node import MergeNode

        if not isinstance(node, MergeNode):
            return

        # Simply follow the standard exec_out flow
        # The merge node's execution has already completed
        self._follow_flow(node, "exec_out")

    def _handle_thread_flow(self, node: BaseNode, inputs: Dict[str, Any]) -> None:
        """
        Handle execution flow for a thread node with parallel execution.

        The thread node spawns multiple threads to execute downstream paths
        concurrently. Each thread_out_N port represents a parallel execution path.

        Args:
            node: The thread node.
            inputs: The inputs to the thread node.
        """
        from visualpython.nodes.models.thread_node import ThreadNode

        if not isinstance(node, ThreadNode):
            return

        # Get the indices of connected thread outputs
        connected_indices = node.get_connected_thread_indices()

        if not connected_indices:
            # No threads connected, just follow exec_out
            self._follow_flow(node, "exec_out")
            return

        # Create threads for each connected output
        threads: List[threading.Thread] = []
        thread_errors: Dict[int, Exception] = {}
        thread_lock = threading.Lock()

        def execute_thread_branch(thread_index: int) -> None:
            """Execute a single thread branch."""
            try:
                port_name = f"thread_out_{thread_index}"
                connections = self._graph.get_connections_for_port(
                    node.id, port_name, is_input=False
                )

                for connection in connections:
                    if self._context.is_cancelled():
                        break

                    target_node = self._graph.get_node(connection.target_node_id)
                    if target_node:
                        # Use lock for thread-safe context access
                        with thread_lock:
                            if not self._context.is_node_executed(target_node.id):
                                # Mark as executed to prevent other threads from picking it up
                                self._context._executed_nodes.add(target_node.id)

                        # Execute the branch (this will recursively follow the flow)
                        self._execute_thread_branch(target_node, thread_lock)

                # Mark thread as completed
                with self._thread_lock:
                    node.mark_thread_completed(thread_index)

            except Exception as e:
                with thread_lock:
                    thread_errors[thread_index] = e
                    node.mark_thread_completed(thread_index, error=str(e))

        # Spawn threads for each connected output
        for idx in connected_indices:
            thread = threading.Thread(
                target=execute_thread_branch,
                args=(idx,),
                name=f"ThreadNode-{node.id[:8]}-thread-{idx}",
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads if configured to do so
        if node.wait_for_all:
            for thread in threads:
                thread.join()

            # Check for errors
            if thread_errors:
                error_messages = [f"Thread {idx}: {str(e)}" for idx, e in thread_errors.items()]
                raise ExecutionError(
                    f"Thread execution failed: {'; '.join(error_messages)}",
                    node_id=node.id,
                )

            # Update outputs with thread results
            outputs = node.execute(inputs)
            outputs["thread_results"] = node.thread_results
            self._context.set_node_outputs(node.id, outputs)

            # Follow exec_out after all threads complete
            self._follow_flow(node, "exec_out")

    def _handle_thread_join_flow(self, node: BaseNode, inputs: Dict[str, Any]) -> None:
        """
        Handle execution flow for a thread join node.

        The thread join node waits for threads to complete before continuing.
        It acts as a synchronization point for parallel execution paths.

        Args:
            node: The thread join node.
            inputs: The inputs to the thread join node.
        """
        from visualpython.nodes.models.thread_join_node import ThreadJoinNode

        if not isinstance(node, ThreadJoinNode):
            return

        # The thread join node collects completion signals from threads.
        # When threads complete and reach this node via thread_in_N ports,
        # the node tracks their completion.

        # Check if we're ready to continue based on completion status
        if node.is_ready_to_continue():
            # All required threads have completed, continue execution
            self._follow_flow(node, "exec_out")
        elif node.wait_for_all:
            # Wait for all threads to complete
            # Note: In practice, threads reaching this node will mark themselves
            # as completed, and the last thread to complete will trigger
            # the continuation
            completed = node.wait_for_completion()
            if completed:
                self._follow_flow(node, "exec_out")
            else:
                # Timeout occurred
                raise ExecutionError(
                    f"Thread join timeout: waited {node.timeout_ms}ms for threads to complete",
                    node_id=node.id,
                )
        else:
            # wait_for_all is False, so any completed thread should trigger continuation
            # If we reach here and no thread has completed yet, we should wait
            completed = node.wait_for_completion()
            if completed:
                self._follow_flow(node, "exec_out")
            else:
                raise ExecutionError(
                    f"Thread join timeout: waited {node.timeout_ms}ms for any thread to complete",
                    node_id=node.id,
                )

    def _execute_thread_branch(
        self,
        node: BaseNode,
        thread_lock: threading.Lock,
    ) -> None:
        """
        Execute a branch of nodes within a thread context.

        This is similar to _execute_from_node but with thread-safe access.

        Args:
            node: The node to execute.
            thread_lock: Lock for thread-safe context access.
        """
        if self._context.is_cancelled():
            return

        # Gather inputs from connected nodes (thread-safe read)
        with thread_lock:
            inputs = self._gather_inputs(node)

        # Execute the node
        try:
            outputs = self._execute_node(node, inputs)
        except ExecutionError:
            raise
        except Exception as e:
            raise ExecutionError(
                f"Failed to execute node '{node.name}' in thread: {str(e)}",
                node_id=node.id,
                original_error=e,
            )

        # Store outputs in context (thread-safe write)
        with thread_lock:
            self._context.set_node_outputs(node.id, outputs)

        # Handle control flow based on node type
        # Note: Nested thread nodes within threads are executed sequentially
        if node.node_type == "if":
            self._handle_if_flow_threaded(node, outputs, thread_lock)
        elif node.node_type == "for_loop":
            self._handle_for_loop_flow_threaded(node, inputs, thread_lock)
        elif node.node_type == "merge":
            self._follow_flow_threaded(node, "exec_out", thread_lock)
        elif node.node_type == "thread":
            # Nested threads are executed sequentially to avoid complexity
            self._handle_thread_flow(node, inputs)
        elif node.node_type == "thread_join":
            # Handle thread join in threaded context
            self._handle_thread_join_flow_threaded(node, inputs, thread_lock)
        else:
            # Follow standard execution flow
            self._follow_flow_threaded(node, "exec_out", thread_lock)

    def _follow_flow_threaded(
        self,
        node: BaseNode,
        port_name: str,
        thread_lock: threading.Lock,
    ) -> None:
        """
        Follow execution flow from a node's output port (thread-safe version).

        Args:
            node: The source node.
            port_name: The name of the flow output port.
            thread_lock: Lock for thread-safe context access.
        """
        if self._context.is_cancelled():
            return

        # Get connections from this flow port
        connections = self._graph.get_connections_for_port(
            node.id, port_name, is_input=False
        )

        for connection in connections:
            target_node = self._graph.get_node(connection.target_node_id)
            if target_node:
                # Handle merge node - track which input was triggered
                if target_node.node_type == "merge":
                    from visualpython.nodes.models.merge_node import MergeNode
                    if isinstance(target_node, MergeNode):
                        with thread_lock:
                            target_node.trigger_input(connection.target_port_name)

                # Handle thread join node - mark thread as completed
                if target_node.node_type == "thread_join":
                    from visualpython.nodes.models.thread_join_node import ThreadJoinNode
                    if isinstance(target_node, ThreadJoinNode):
                        port_name = connection.target_port_name
                        if port_name.startswith("thread_in_"):
                            try:
                                thread_idx = int(port_name.split("_")[-1])
                                with thread_lock:
                                    thread_data = self._context.get_node_output(
                                        node.id, "data_out"
                                    ) if hasattr(node, "id") else None
                                target_node.mark_thread_completed(thread_idx, thread_data)
                            except (ValueError, IndexError):
                                logger.debug("Value conversion skipped", exc_info=True)
                                pass

                with thread_lock:
                    already_executed = self._context.is_node_executed(target_node.id)
                    if not already_executed:
                        self._context._executed_nodes.add(target_node.id)

                if not already_executed:
                    self._execute_thread_branch(target_node, thread_lock)

    def _handle_if_flow_threaded(
        self,
        node: BaseNode,
        outputs: Dict[str, Any],
        thread_lock: threading.Lock,
    ) -> None:
        """
        Handle execution flow for an if node (thread-safe version).

        Args:
            node: The if node.
            outputs: The outputs from the if node execution.
            thread_lock: Lock for thread-safe context access.
        """
        result = outputs.get("result", False)

        if result:
            self._follow_flow_threaded(node, "true_branch", thread_lock)
        else:
            self._follow_flow_threaded(node, "false_branch", thread_lock)

    def _handle_for_loop_flow_threaded(
        self,
        node: BaseNode,
        inputs: Dict[str, Any],
        thread_lock: threading.Lock,
    ) -> None:
        """
        Handle execution flow for a for loop node (thread-safe version).

        Args:
            node: The for loop node.
            inputs: The inputs to the for loop.
            thread_lock: Lock for thread-safe context access.
        """
        from visualpython.nodes.models.for_loop_node import ForLoopNode

        if not isinstance(node, ForLoopNode):
            return

        iterable = inputs.get("iterable", [])

        # Iterate over each item
        for iteration_outputs in node.iterate(iterable):
            if self._context.is_cancelled():
                break

            # Store current iteration outputs
            with thread_lock:
                self._context.set_node_outputs(node.id, iteration_outputs)
                # Clear executed state for nodes in loop body to allow re-execution
                loop_body_nodes = self._get_loop_body_nodes(node)
                for node_id in loop_body_nodes:
                    self._context._executed_nodes.discard(node_id)

            # Execute loop body
            self._follow_flow_threaded(node, "loop_body", thread_lock)

        # After loop completes, follow the completed flow
        if not self._context.is_cancelled():
            self._follow_flow_threaded(node, "completed", thread_lock)

    def _handle_thread_join_flow_threaded(
        self,
        node: BaseNode,
        inputs: Dict[str, Any],
        thread_lock: threading.Lock,
    ) -> None:
        """
        Handle execution flow for a thread join node (thread-safe version).

        Args:
            node: The thread join node.
            inputs: The inputs to the thread join node.
            thread_lock: Lock for thread-safe context access.
        """
        from visualpython.nodes.models.thread_join_node import ThreadJoinNode

        if not isinstance(node, ThreadJoinNode):
            return

        # Check if we're ready to continue
        with thread_lock:
            ready = node.is_ready_to_continue()

        if ready:
            self._follow_flow_threaded(node, "exec_out", thread_lock)
        elif node.wait_for_all:
            # Wait for all threads to complete
            completed = node.wait_for_completion()
            if completed:
                self._follow_flow_threaded(node, "exec_out", thread_lock)
            else:
                raise ExecutionError(
                    f"Thread join timeout in thread context",
                    node_id=node.id,
                )
        else:
            # Wait for any thread to complete
            completed = node.wait_for_completion()
            if completed:
                self._follow_flow_threaded(node, "exec_out", thread_lock)
            else:
                raise ExecutionError(
                    f"Thread join timeout in thread context",
                    node_id=node.id,
                )

    def _clear_loop_body_executed_state(self, loop_node: BaseNode) -> None:
        """
        Clear executed state for nodes in a loop body to allow re-execution.

        Args:
            loop_node: The for loop node.
        """
        # Get all nodes connected to loop_body
        loop_body_nodes = self._get_loop_body_nodes(loop_node)

        for node_id in loop_body_nodes:
            # Remove from executed set to allow re-execution
            self._context._executed_nodes.discard(node_id)

    def _get_loop_body_nodes(self, loop_node: BaseNode) -> List[str]:
        """
        Get all node IDs that are part of a loop body.

        Args:
            loop_node: The for loop node.

        Returns:
            List of node IDs in the loop body.
        """
        loop_body_nodes: List[str] = []
        visited: set = set()

        def traverse(node_id: str) -> None:
            if node_id in visited or node_id == loop_node.id:
                return
            visited.add(node_id)
            loop_body_nodes.append(node_id)

            # Get outgoing connections
            connections = self._graph.get_outgoing_connections(node_id)
            for conn in connections:
                # Don't traverse back to the loop node's "completed" port
                if conn.target_node_id != loop_node.id:
                    traverse(conn.target_node_id)

        # Start from loop_body connections
        loop_body_connections = self._graph.get_connections_for_port(
            loop_node.id, "loop_body", is_input=False
        )
        for conn in loop_body_connections:
            traverse(conn.target_node_id)

        return loop_body_nodes


def execute_graph(graph: Graph) -> ExecutionResult:
    """
    Convenience function to execute a graph.

    Args:
        graph: The graph to execute.

    Returns:
        ExecutionResult containing execution status and outputs.
    """
    engine = ExecutionEngine(graph)
    return engine.execute()


def execute_code(
    code: str,
    inputs: Optional[Dict[str, Any]] = None,
    global_vars: Optional[Dict[str, Any]] = None,
    case: Optional[Case] = None,
) -> Dict[str, Any]:
    """
    Execute Python code directly using exec().

    This function provides a simple way to execute Python code with
    a controlled namespace, similar to how CodeNodes execute their code.

    Uses AST validation to catch syntax errors before execution.

    Args:
        code: The Python code to execute.
        inputs: Optional dictionary of input values accessible as 'inputs'.
        global_vars: Optional dictionary of global variables accessible as 'globals'.
        case: Optional Case instance for per-execution shared state accessible as 'case'.

    Returns:
        Dictionary of outputs set by the code in 'outputs'.

    Raises:
        SyntaxError: If the code has syntax errors.
        Exception: Any exception raised during code execution.

    Example:
        >>> result = execute_code(
        ...     "outputs['result'] = inputs['x'] * 2",
        ...     inputs={'x': 5}
        ... )
        >>> print(result)
        {'result': 10}

        # Using case for shared state:
        >>> from visualpython.execution.case import Case
        >>> case = Case()
        >>> result = execute_code(
        ...     "case.counter = case.get('counter', 0) + 1; outputs['count'] = case.counter",
        ...     case=case
        ... )
        >>> print(result)
        {'count': 1}
    """
    if inputs is None:
        inputs = {}
    if global_vars is None:
        global_vars = {}

    # Validate code syntax using AST before execution
    validation_result = validate_python_code(code, mode=ValidationMode.EXEC)
    if not validation_result.valid:
        error_msg = "; ".join(validation_result.error_messages)
        raise SyntaxError(f"Code validation failed: {error_msg}")

    outputs: Dict[str, Any] = {}

    # Create the execution namespace
    namespace: Dict[str, Any] = {
        "inputs": inputs,
        "outputs": outputs,
        "globals": global_vars,
    }

    # Add case to namespace if provided, otherwise use the current execution case
    if case is not None:
        namespace["case"] = case
    else:
        current_case = get_current_case()
        if current_case is not None:
            namespace["case"] = current_case

    # Execute the code
    exec(code, namespace)

    return outputs


class _SubgraphExecutionEngine:
    """
    Lightweight execution engine for subgraph internal graphs.

    Unlike the full ExecutionEngine, this can start execution from any node
    (not just StartNodes), making it suitable for executing subgraph internals
    where SubgraphInput nodes serve as entry points.
    """

    def __init__(self, graph: Graph) -> None:
        self._graph = graph
        self._node_outputs: Dict[str, Dict[str, Any]] = {}
        self._executed_nodes: Set[str] = set()

    def execute_from(self, entry_node: BaseNode) -> None:
        """Execute the graph starting from the given entry node."""
        self._execute_node_chain(entry_node)

    def get_node_outputs(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get the stored outputs for a node."""
        return self._node_outputs.get(node_id)

    def _execute_node_chain(self, node: BaseNode) -> None:
        """Execute a node and follow its flow connections."""
        if node.id in self._executed_nodes:
            return

        self._executed_nodes.add(node.id)

        # Gather inputs and execute the node
        try:
            inputs = self._gather_inputs(node)
            outputs = node.execute(inputs)
        except Exception as e:
            logger.error(
                "Error executing node '%s' (type=%s) in subgraph: %s",
                node.name, node.node_type, e,
            )
            outputs = {}

        self._node_outputs[node.id] = outputs

        # Follow flow connections (exec_out)
        connections = self._graph.get_connections_for_port(
            node.id, "exec_out", is_input=False
        )
        for conn in connections:
            next_node = self._graph.get_node(conn.target_node_id)
            if next_node and next_node.id not in self._executed_nodes:
                self._execute_node_chain(next_node)

    def _gather_inputs(self, node: BaseNode) -> Dict[str, Any]:
        """Gather input values from connected sources and inline values."""
        inputs: Dict[str, Any] = {}

        for port in node.input_ports:
            if port.port_type.name == "FLOW":
                continue

            if port.is_connected() and port.connection:
                source_node_id = port.connection.source_node_id
                source_port_name = port.connection.source_port_name

                source_outputs = self._node_outputs.get(source_node_id, {})
                value = source_outputs.get(source_port_name)
                if value is not None:
                    inputs[port.name] = value
                else:
                    # Fall back to inline or default
                    effective = port.get_effective_value()
                    if effective is not None:
                        inputs[port.name] = effective
            else:
                effective = port.get_effective_value()
                if effective is not None:
                    inputs[port.name] = effective

        return inputs
