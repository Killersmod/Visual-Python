"""
Thread node model for parallel execution in VisualPython.

This module defines the ThreadNode class, which spawns new threads
for parallel execution of connected downstream nodes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType

if TYPE_CHECKING:
    pass


class ThreadNode(BaseNode):
    """
    A node that spawns new threads for parallel execution of downstream nodes.

    The ThreadNode enables concurrent processing by executing connected
    downstream paths in separate threads. Each thread output port represents
    a parallel execution path that runs concurrently with other paths.

    The node supports configurable behavior:
    1. Number of parallel threads (2-8)
    2. Wait for all threads to complete before continuing (synchronization point)
    3. Pass through data to all threads or distribute data across threads

    The node has:
    - exec_in: Single execution flow input
    - Multiple thread_out_N ports for parallel execution paths
    - exec_out: Execution flow output after all threads complete (when wait_all=True)
    - data_in: Optional data input to pass to threads
    - thread_results: Combined results from all threads

    Attributes:
        num_threads: Number of parallel thread outputs (2-8).
        wait_for_all: Whether to wait for all threads before continuing.
        thread_results: Dictionary storing results from each thread.

    Example:
        >>> node = ThreadNode(num_threads=3)
        >>> # Connect different processing chains to thread_out_1, thread_out_2, thread_out_3
        >>> # All three chains execute in parallel
    """

    # Class-level metadata
    node_type: str = "thread"
    """Unique identifier for thread nodes."""

    node_category: str = "Control Flow"
    """Category for organizing in the UI."""

    node_color: str = "#9C27B0"
    """Purple color to distinguish thread nodes as parallel execution."""

    # Thread count limits
    MIN_THREADS: int = 2
    MAX_THREADS: int = 8

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        num_threads: int = 2,
        wait_for_all: bool = True,
    ) -> None:
        """
        Initialize a new ThreadNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Thread'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            num_threads: Number of parallel thread outputs to create (2-8, default 2).
            wait_for_all: Whether to wait for all threads before continuing (default True).
        """
        self._num_threads: int = max(self.MIN_THREADS, min(self.MAX_THREADS, num_threads))
        self._wait_for_all: bool = wait_for_all
        self._thread_results: Dict[int, Any] = {}
        self._completed_threads: set = set()
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the thread node.

        The thread node has:
        - exec_in: Execution flow input
        - data_in: Optional data to pass to all threads
        - thread_out_N: Multiple thread execution outputs for parallel paths
        - exec_out: Execution flow output after threads complete
        - thread_results: Combined results from all threads
        """
        # Execution flow input
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input - triggers parallel thread spawning",
            required=True,
        ))

        # Optional data input to pass to threads
        self.add_input_port(InputPort(
            name="data_in",
            port_type=PortType.ANY,
            description="Optional data to pass to all thread branches",
            required=False,
        ))

        # Create thread output ports based on num_threads
        for i in range(1, self._num_threads + 1):
            self.add_output_port(OutputPort(
                name=f"thread_out_{i}",
                port_type=PortType.FLOW,
                description=f"Thread {i} execution output - runs in parallel",
            ))

        # Execution flow output - after all threads complete (when wait_for_all=True)
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output - continues after threads complete",
        ))

        # Data output - combined results from all threads
        self.add_output_port(OutputPort(
            name="thread_results",
            port_type=PortType.DICT,
            description="Dictionary of results from each thread (keyed by thread number)",
        ))

        # Data output - the input data passed through for convenience
        self.add_output_port(OutputPort(
            name="data_out",
            port_type=PortType.ANY,
            description="Pass-through of the input data",
        ))

    @property
    def num_threads(self) -> int:
        """Get the number of thread outputs."""
        return self._num_threads

    @property
    def wait_for_all(self) -> bool:
        """Get whether to wait for all threads to complete."""
        return self._wait_for_all

    @wait_for_all.setter
    def wait_for_all(self, value: bool) -> None:
        """Set whether to wait for all threads to complete."""
        self._wait_for_all = value

    @property
    def thread_results(self) -> Dict[int, Any]:
        """Get the results from completed threads."""
        return self._thread_results.copy()

    @property
    def completed_threads(self) -> set:
        """Get the set of completed thread indices."""
        return self._completed_threads.copy()

    def add_thread(self) -> bool:
        """
        Add an additional thread output if below maximum.

        Returns:
            True if a new thread was added, False if at maximum.
        """
        if self._num_threads >= self.MAX_THREADS:
            return False

        self._num_threads += 1
        new_idx = self._num_threads

        # Add the new thread output port
        self.add_output_port(OutputPort(
            name=f"thread_out_{new_idx}",
            port_type=PortType.FLOW,
            description=f"Thread {new_idx} execution output - runs in parallel",
        ))

        return True

    def remove_thread(self) -> bool:
        """
        Remove the last thread output if above minimum.

        Returns:
            True if a thread was removed, False if at minimum.
        """
        if self._num_threads <= self.MIN_THREADS:
            return False

        idx = self._num_threads
        self.remove_output_port(f"thread_out_{idx}")
        self._num_threads -= 1

        return True

    def get_connected_thread_count(self) -> int:
        """
        Get the number of thread output ports that have connections.

        Returns:
            Count of connected thread output ports.
        """
        count = 0
        for i in range(1, self._num_threads + 1):
            port = self.get_output_port(f"thread_out_{i}")
            if port and port.is_connected():
                count += 1
        return count

    def get_connected_thread_indices(self) -> List[int]:
        """
        Get the indices of thread output ports that have connections.

        Returns:
            List of indices (1-based) of connected thread output ports.
        """
        indices = []
        for i in range(1, self._num_threads + 1):
            port = self.get_output_port(f"thread_out_{i}")
            if port and port.is_connected():
                indices.append(i)
        return indices

    def mark_thread_completed(self, thread_index: int, result: Any = None) -> None:
        """
        Mark a thread as completed and store its result.

        Args:
            thread_index: The index of the completed thread (1-based).
            result: Optional result data from the thread.
        """
        if 1 <= thread_index <= self._num_threads:
            self._completed_threads.add(thread_index)
            self._thread_results[thread_index] = result

    def are_all_threads_completed(self) -> bool:
        """
        Check if all connected threads have completed.

        Returns:
            True if all connected threads have completed, False otherwise.
        """
        connected_indices = self.get_connected_thread_indices()
        return all(idx in self._completed_threads for idx in connected_indices)

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Validate num_threads range
        if self._num_threads < self.MIN_THREADS or self._num_threads > self.MAX_THREADS:
            errors.append(f"Number of threads must be between {self.MIN_THREADS} and {self.MAX_THREADS}")

        # Check if at least one thread output is connected
        if self.get_connected_thread_count() == 0:
            errors.append("At least one thread output should be connected for parallel execution")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the thread node - prepare for parallel execution.

        The actual thread spawning is handled by the ExecutionEngine.
        This method sets up the initial state and passes through data.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary with outputs:
            - data_out: Pass-through of input data
            - thread_results: Results from threads (populated by engine)
        """
        # Get input data to pass to threads
        data_in = inputs.get("data_in")

        return {
            "data_out": data_in,
            "thread_results": self._thread_results.copy(),
        }

    def reset_state(self) -> None:
        """Reset the node to its initial state."""
        super().reset_state()
        self._thread_results.clear()
        self._completed_threads.clear()

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get thread node specific properties for serialization.

        Returns:
            Dictionary containing the number of threads and wait_for_all setting.
        """
        return {
            "num_threads": self._num_threads,
            "wait_for_all": self._wait_for_all,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load thread node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._wait_for_all = properties.get("wait_for_all", True)
        new_num_threads = properties.get("num_threads", 2)

        # Adjust number of thread ports if different
        while self._num_threads < new_num_threads and self._num_threads < self.MAX_THREADS:
            self.add_thread()
        while self._num_threads > new_num_threads and self._num_threads > self.MIN_THREADS:
            self.remove_thread()

    def __repr__(self) -> str:
        """Get a detailed string representation of the thread node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"num_threads={self._num_threads}, "
            f"wait_for_all={self._wait_for_all}, "
            f"completed={len(self._completed_threads)}/{self.get_connected_thread_count()}, "
            f"state={self._execution_state.name})"
        )
