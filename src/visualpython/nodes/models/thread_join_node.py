"""
Thread join node model for synchronization in VisualPython.

This module defines the ThreadJoinNode class, which waits for thread completion
before continuing execution, enabling synchronization points in parallel workflows.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class ThreadJoinNode(BaseNode):
    """
    A node that waits for thread completion before continuing execution.

    The ThreadJoinNode provides synchronization points in parallel workflows
    by waiting for specified threads to complete before allowing execution
    to continue. This is essential for coordinating parallel operations and
    ensuring all parallel work is done before proceeding.

    The node works in conjunction with ThreadNode:
    - ThreadNode spawns parallel threads for concurrent execution
    - ThreadJoinNode waits for those threads to complete

    The node supports configurable behavior:
    1. Number of threads to wait for (2-8)
    2. Wait for all threads or just any single thread
    3. Timeout for waiting (optional)

    The node has:
    - exec_in: Single execution flow input
    - Multiple thread_in_N ports for receiving completion signals from threads
    - exec_out: Execution flow output after synchronization
    - all_completed: Boolean indicating if all threads completed
    - completed_count: Number of threads that completed
    - thread_data: Aggregated data from completed threads

    Attributes:
        num_inputs: Number of thread input ports (2-8).
        wait_for_all: Whether to wait for all threads before continuing.
        timeout_ms: Optional timeout in milliseconds (0 = no timeout).
        completed_threads: Set of completed thread indices.
        thread_data: Dictionary storing data received from each thread.

    Example:
        >>> node = ThreadJoinNode(num_inputs=3, wait_for_all=True)
        >>> # Connect thread outputs from ThreadNode to thread_in_1, thread_in_2, thread_in_3
        >>> # Node waits for all three threads to complete before continuing
    """

    # Class-level metadata
    node_type: str = "thread_join"
    """Unique identifier for thread join nodes."""

    node_category: str = "Control Flow"
    """Category for organizing in the UI."""

    node_color: str = "#673AB7"
    """Deep purple color to indicate synchronization/joining."""

    # Thread input limits
    MIN_INPUTS: int = 2
    MAX_INPUTS: int = 8

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        num_inputs: int = 2,
        wait_for_all: bool = True,
        timeout_ms: int = 0,
    ) -> None:
        """
        Initialize a new ThreadJoinNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Thread Join'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            num_inputs: Number of thread input ports to create (2-8, default 2).
            wait_for_all: Whether to wait for all threads before continuing (default True).
            timeout_ms: Timeout in milliseconds, 0 for no timeout (default 0).
        """
        self._num_inputs: int = max(self.MIN_INPUTS, min(self.MAX_INPUTS, num_inputs))
        self._wait_for_all: bool = wait_for_all
        self._timeout_ms: int = max(0, timeout_ms)
        self._completed_threads: set = set()
        self._thread_data: Dict[int, Any] = {}
        self._completion_event: threading.Event = threading.Event()
        self._lock: threading.Lock = threading.Lock()
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the thread join node.

        The thread join node has:
        - exec_in: Execution flow input
        - Multiple thread_in_N ports for receiving thread completion signals
        - exec_out: Execution flow output after synchronization
        - all_completed: Boolean indicating if all threads completed
        - completed_count: Number of completed threads
        - thread_data: Aggregated data from all threads
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input - triggers wait for thread completion",
            required=True,
        ))

        # Create thread input ports based on num_inputs
        for i in range(1, self._num_inputs + 1):
            self.add_input_port(InputPort(
                name=f"thread_in_{i}",
                port_type=PortType.FLOW,
                description=f"Thread {i} completion input - connect from thread output",
                required=False,
            ))

        # Optional data input ports corresponding to each thread input
        for i in range(1, self._num_inputs + 1):
            self.add_input_port(InputPort(
                name=f"data_in_{i}",
                port_type=PortType.ANY,
                description=f"Optional data input from thread {i}",
                required=False,
            ))

        # Execution flow output - after synchronization
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output - continues after threads complete",
        ))

        # Boolean output indicating if all threads completed
        self.add_output_port(OutputPort(
            name="all_completed",
            port_type=PortType.BOOLEAN,
            description="True if all connected threads completed successfully",
        ))

        # Count of completed threads
        self.add_output_port(OutputPort(
            name="completed_count",
            port_type=PortType.INTEGER,
            description="Number of threads that completed",
        ))

        # Aggregated thread data
        self.add_output_port(OutputPort(
            name="thread_data",
            port_type=PortType.DICT,
            description="Dictionary of data from each thread (keyed by thread number)",
        ))

    @property
    def num_inputs(self) -> int:
        """Get the number of thread input ports."""
        return self._num_inputs

    @property
    def wait_for_all(self) -> bool:
        """Get whether to wait for all threads to complete."""
        return self._wait_for_all

    @wait_for_all.setter
    def wait_for_all(self, value: bool) -> None:
        """Set whether to wait for all threads to complete."""
        self._wait_for_all = value

    @property
    def timeout_ms(self) -> int:
        """Get the timeout in milliseconds."""
        return self._timeout_ms

    @timeout_ms.setter
    def timeout_ms(self, value: int) -> None:
        """Set the timeout in milliseconds."""
        self._timeout_ms = max(0, value)

    @property
    def completed_threads(self) -> set:
        """Get the set of completed thread indices."""
        with self._lock:
            return self._completed_threads.copy()

    @property
    def thread_data(self) -> Dict[int, Any]:
        """Get the data received from threads."""
        with self._lock:
            return self._thread_data.copy()

    def add_input(self) -> bool:
        """
        Add an additional thread input if below maximum.

        Returns:
            True if a new input was added, False if at maximum.
        """
        if self._num_inputs >= self.MAX_INPUTS:
            return False

        self._num_inputs += 1
        new_idx = self._num_inputs

        # Add the new thread input port
        self.add_input_port(InputPort(
            name=f"thread_in_{new_idx}",
            port_type=PortType.FLOW,
            description=f"Thread {new_idx} completion input - connect from thread output",
            required=False,
        ))

        # Add corresponding data input port
        self.add_input_port(InputPort(
            name=f"data_in_{new_idx}",
            port_type=PortType.ANY,
            description=f"Optional data input from thread {new_idx}",
            required=False,
        ))

        return True

    def remove_input(self) -> bool:
        """
        Remove the last thread input if above minimum.

        Returns:
            True if an input was removed, False if at minimum.
        """
        if self._num_inputs <= self.MIN_INPUTS:
            return False

        idx = self._num_inputs
        self.remove_input_port(f"thread_in_{idx}")
        self.remove_input_port(f"data_in_{idx}")
        self._num_inputs -= 1

        return True

    def get_connected_input_count(self) -> int:
        """
        Get the number of thread input ports that have connections.

        Returns:
            Count of connected thread input ports.
        """
        count = 0
        for i in range(1, self._num_inputs + 1):
            port = self.get_input_port(f"thread_in_{i}")
            if port and port.is_connected():
                count += 1
        return count

    def get_connected_input_indices(self) -> List[int]:
        """
        Get the indices of thread input ports that have connections.

        Returns:
            List of indices (1-based) of connected thread input ports.
        """
        indices = []
        for i in range(1, self._num_inputs + 1):
            port = self.get_input_port(f"thread_in_{i}")
            if port and port.is_connected():
                indices.append(i)
        return indices

    def mark_thread_completed(self, thread_index: int, data: Any = None) -> None:
        """
        Mark a thread as completed and store its data.

        This method is called by the execution engine when a thread
        completes and reaches this join node.

        Args:
            thread_index: The index of the completed thread (1-based).
            data: Optional data from the completed thread.
        """
        with self._lock:
            if 1 <= thread_index <= self._num_inputs:
                self._completed_threads.add(thread_index)
                self._thread_data[thread_index] = data

                # Check if we should signal completion
                if self._should_signal_completion():
                    self._completion_event.set()

    def _should_signal_completion(self) -> bool:
        """
        Check if the completion condition is met.

        Returns:
            True if ready to proceed, False otherwise.
        """
        connected_indices = self.get_connected_input_indices()
        if not connected_indices:
            return True

        if self._wait_for_all:
            # All connected threads must be completed
            return all(idx in self._completed_threads for idx in connected_indices)
        else:
            # At least one connected thread must be completed
            return any(idx in self._completed_threads for idx in connected_indices)

    def wait_for_completion(self) -> bool:
        """
        Wait for threads to complete based on configuration.

        This method blocks until the completion condition is met or timeout occurs.

        Returns:
            True if completion condition was met, False if timeout occurred.
        """
        # Check if already complete
        with self._lock:
            if self._should_signal_completion():
                return True

        # Wait with optional timeout
        if self._timeout_ms > 0:
            return self._completion_event.wait(timeout=self._timeout_ms / 1000.0)
        else:
            self._completion_event.wait()
            return True

    def is_ready_to_continue(self) -> bool:
        """
        Check if the join node is ready to continue execution.

        Returns:
            True if ready to continue, False otherwise.
        """
        with self._lock:
            return self._should_signal_completion()

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate num_inputs range
        if self._num_inputs < self.MIN_INPUTS or self._num_inputs > self.MAX_INPUTS:
            errors.append(
                f"Number of inputs must be between {self.MIN_INPUTS} and {self.MAX_INPUTS}"
            )

        # Validate timeout
        if self._timeout_ms < 0:
            errors.append("Timeout cannot be negative")

        # Check if at least one thread input is connected
        if self.get_connected_input_count() == 0:
            errors.append(
                "At least one thread input should be connected for synchronization"
            )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the thread join node - wait for thread completion.

        The actual waiting logic is handled by the ExecutionEngine.
        This method aggregates the thread data and returns status.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary with outputs:
            - all_completed: Boolean indicating if all threads completed
            - completed_count: Number of completed threads
            - thread_data: Data from each thread
        """
        # Collect data from inputs
        with self._lock:
            for i in range(1, self._num_inputs + 1):
                data_key = f"data_in_{i}"
                if data_key in inputs:
                    self._thread_data[i] = inputs[data_key]

        connected_indices = self.get_connected_input_indices()
        all_completed = all(idx in self._completed_threads for idx in connected_indices)

        return {
            "all_completed": all_completed,
            "completed_count": len(self._completed_threads),
            "thread_data": self._thread_data.copy(),
        }

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        super().reset_state()
        with self._lock:
            self._completed_threads.clear()
            self._thread_data.clear()
            self._completion_event.clear()

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get thread join node specific properties for serialization.

        Returns:
            Dictionary containing num_inputs, wait_for_all, and timeout_ms.
        """
        return {
            "num_inputs": self._num_inputs,
            "wait_for_all": self._wait_for_all,
            "timeout_ms": self._timeout_ms,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load thread join node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._wait_for_all = properties.get("wait_for_all", True)
        self._timeout_ms = properties.get("timeout_ms", 0)
        new_num_inputs = properties.get("num_inputs", 2)

        # Adjust number of input ports if different
        while self._num_inputs < new_num_inputs and self._num_inputs < self.MAX_INPUTS:
            self.add_input()
        while self._num_inputs > new_num_inputs and self._num_inputs > self.MIN_INPUTS:
            self.remove_input()

    def __repr__(self) -> str:
        """Get a detailed string representation of the thread join node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"num_inputs={self._num_inputs}, "
            f"wait_for_all={self._wait_for_all}, "
            f"completed={len(self._completed_threads)}/{self.get_connected_input_count()}, "
            f"state={self._execution_state.name})"
        )
