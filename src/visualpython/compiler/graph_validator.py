"""
Graph validation module for pre-compilation validation of node graphs.

This module provides the GraphValidator class that performs comprehensive
validation of a graph before compilation, including cycle detection with
detailed human-readable error messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph
    from visualpython.nodes.models.base_node import BaseNode


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    ERROR = auto()
    """Critical issue that prevents compilation."""

    WARNING = auto()
    """Non-critical issue that may cause unexpected behavior."""

    INFO = auto()
    """Informational message about the graph structure."""


@dataclass
class CycleInfo:
    """
    Detailed information about a detected cycle in the graph.

    Provides both machine-readable data (node IDs) and human-readable
    descriptions for debugging and user feedback.

    Attributes:
        node_ids: List of node IDs forming the cycle, in order.
        node_names: List of node names forming the cycle, in order.
        description: Human-readable description of the cycle.
        involved_connections: List of connection descriptions in the cycle.
    """

    node_ids: List[str] = field(default_factory=list)
    node_names: List[str] = field(default_factory=list)
    description: str = ""
    involved_connections: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        """Get a string representation of the cycle."""
        if self.description:
            return self.description
        if self.node_names:
            cycle_path = " -> ".join(self.node_names)
            return f"Cycle detected: {cycle_path}"
        return "Cycle detected"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize cycle info to a dictionary."""
        return {
            "node_ids": self.node_ids.copy(),
            "node_names": self.node_names.copy(),
            "description": self.description,
            "involved_connections": self.involved_connections.copy(),
        }


@dataclass
class ValidationIssue:
    """
    Represents a single validation issue found in the graph.

    Attributes:
        severity: The severity level of the issue.
        message: Human-readable description of the issue.
        node_id: Optional ID of the node associated with the issue.
        node_name: Optional name of the node for display purposes.
        details: Optional additional details about the issue.
    """

    severity: ValidationSeverity
    message: str
    node_id: Optional[str] = None
    node_name: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        """Get a string representation of the issue."""
        prefix = f"[{self.severity.name}]"
        if self.node_name:
            return f"{prefix} {self.node_name}: {self.message}"
        if self.node_id:
            return f"{prefix} Node {self.node_id[:8]}...: {self.message}"
        return f"{prefix} {self.message}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize issue to a dictionary."""
        result = {
            "severity": self.severity.name,
            "message": self.message,
        }
        if self.node_id:
            result["node_id"] = self.node_id
        if self.node_name:
            result["node_name"] = self.node_name
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class ValidationResult:
    """
    Complete result of graph validation.

    Attributes:
        is_valid: True if no errors were found (warnings may exist).
        issues: List of all validation issues found.
        cycles: List of detected cycles with detailed information.
        can_compile: True if the graph can be compiled (no blocking errors).
    """

    is_valid: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)
    cycles: List[CycleInfo] = field(default_factory=list)
    can_compile: bool = True

    @property
    def errors(self) -> List[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    @property
    def has_cycles(self) -> bool:
        """Check if any cycles were detected."""
        return len(self.cycles) > 0

    @property
    def error_messages(self) -> List[str]:
        """Get list of error messages as strings."""
        return [str(e) for e in self.errors]

    @property
    def warning_messages(self) -> List[str]:
        """Get list of warning messages as strings."""
        return [str(w) for w in self.warnings]

    @property
    def cycle_descriptions(self) -> List[str]:
        """Get human-readable descriptions of all cycles."""
        return [str(c) for c in self.cycles]

    def add_error(
        self,
        message: str,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add an error issue."""
        self.issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                message=message,
                node_id=node_id,
                node_name=node_name,
                details=details,
            )
        )
        self.is_valid = False
        self.can_compile = False

    def add_warning(
        self,
        message: str,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a warning issue."""
        self.issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message=message,
                node_id=node_id,
                node_name=node_name,
                details=details,
            )
        )

    def add_info(
        self,
        message: str,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add an informational issue."""
        self.issues.append(
            ValidationIssue(
                severity=ValidationSeverity.INFO,
                message=message,
                node_id=node_id,
                node_name=node_name,
                details=details,
            )
        )

    def add_cycle(self, cycle_info: CycleInfo) -> None:
        """Add a detected cycle."""
        self.cycles.append(cycle_info)
        self.is_valid = False
        self.can_compile = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to a dictionary."""
        return {
            "is_valid": self.is_valid,
            "can_compile": self.can_compile,
            "issues": [i.to_dict() for i in self.issues],
            "cycles": [c.to_dict() for c in self.cycles],
        }

    def __str__(self) -> str:
        """Get a summary string of the validation result."""
        if self.is_valid:
            if self.warnings:
                return f"Valid with {len(self.warnings)} warning(s)"
            return "Valid"
        return f"Invalid: {len(self.errors)} error(s), {len(self.cycles)} cycle(s)"


class GraphValidator:
    """
    Validates graph structure before compilation.

    The GraphValidator performs comprehensive checks including:
    - Cycle detection to prevent infinite loops
    - Node configuration validation
    - Connection type compatibility
    - Required input verification
    - Start/End node presence

    This validator should be used before attempting to compile a graph
    to provide detailed, actionable error messages.

    Example:
        >>> validator = GraphValidator(graph)
        >>> result = validator.validate()
        >>> if not result.is_valid:
        ...     for error in result.errors:
        ...         print(f"Error: {error}")
        ...     for cycle in result.cycles:
        ...         print(f"Cycle: {cycle}")
        >>> if result.can_compile:
        ...     generator = CodeGenerator(graph)
        ...     code = generator.generate()
    """

    def __init__(self, graph: Graph) -> None:
        """
        Initialize the validator.

        Args:
            graph: The graph to validate.
        """
        self._graph = graph

    @property
    def graph(self) -> Graph:
        """Get the graph being validated."""
        return self._graph

    def validate(self) -> ValidationResult:
        """
        Perform complete validation of the graph.

        Returns:
            ValidationResult containing all issues found.
        """
        result = ValidationResult()

        # Run all validation checks
        self._validate_cycles(result)
        self._validate_nodes(result)
        self._validate_connections(result)
        self._validate_structure(result)

        return result

    def validate_for_compilation(self) -> ValidationResult:
        """
        Perform validation focused on compilation requirements.

        This is a stricter validation that ensures the graph can be
        compiled to executable Python code.

        Returns:
            ValidationResult with compilation-specific checks.
        """
        result = ValidationResult()

        # Cycles are critical for compilation
        self._validate_cycles(result)

        # Must have a start node
        self._validate_start_nodes(result)

        # Validate node configurations
        self._validate_nodes(result)

        # Validate connections
        self._validate_connections(result)

        return result

    def detect_cycles(self) -> List[CycleInfo]:
        """
        Detect all cycles in the graph.

        Returns:
            List of CycleInfo objects describing each cycle.
        """
        result = ValidationResult()
        self._validate_cycles(result)
        return result.cycles

    def has_cycles(self) -> bool:
        """
        Quick check if the graph contains any cycles.

        Returns:
            True if cycles exist, False otherwise.
        """
        return self._graph.has_cycle()

    def _validate_cycles(self, result: ValidationResult) -> None:
        """
        Detect and report all cycles in the graph.

        Uses DFS with three-color marking to find all cycles and
        builds detailed CycleInfo objects with node names.
        """
        if not self._graph.has_cycle():
            return

        # Get cycles from the graph
        raw_cycles = self._graph.find_cycles()

        for cycle_ids in raw_cycles:
            # Build detailed cycle info
            cycle_info = self._build_cycle_info(cycle_ids)
            result.add_cycle(cycle_info)

            # Also add as an error for the error list
            result.add_error(
                message=cycle_info.description,
                details={"cycle_node_ids": cycle_ids},
            )

    def _build_cycle_info(self, node_ids: List[str]) -> CycleInfo:
        """
        Build detailed cycle information from a list of node IDs.

        Args:
            node_ids: List of node IDs forming the cycle.

        Returns:
            CycleInfo with detailed information about the cycle.
        """
        node_names: List[str] = []
        involved_connections: List[str] = []

        # Get node names
        for node_id in node_ids:
            node = self._graph.get_node(node_id)
            if node:
                node_names.append(node.name)
            else:
                node_names.append(f"Unknown({node_id[:8]}...)")

        # Build connection descriptions
        for i in range(len(node_ids) - 1):
            source_name = node_names[i]
            target_name = node_names[i + 1]
            involved_connections.append(f"{source_name} -> {target_name}")

        # Build description
        cycle_path = " -> ".join(node_names)
        description = (
            f"Cycle detected: {cycle_path}\n"
            f"This creates an infinite loop that prevents execution."
        )

        return CycleInfo(
            node_ids=node_ids,
            node_names=node_names,
            description=description,
            involved_connections=involved_connections,
        )

    def _validate_nodes(self, result: ValidationResult) -> None:
        """Validate individual node configurations."""
        for node in self._graph.nodes:
            node_errors = node.validate()
            for error in node_errors:
                result.add_error(
                    message=error,
                    node_id=node.id,
                    node_name=node.name,
                )

    def _validate_connections(self, result: ValidationResult) -> None:
        """Validate all connections in the graph."""
        # Use the graph's connection validation
        connection_errors = self._graph._connection_model.validate_all_connections()
        for error in connection_errors:
            result.add_error(message=error)

    def _validate_structure(self, result: ValidationResult) -> None:
        """Validate overall graph structure."""
        # Check for orphaned nodes (nodes with no connections)
        for node in self._graph.nodes:
            incoming = self._graph.get_incoming_connections(node.id)
            outgoing = self._graph.get_outgoing_connections(node.id)

            if not incoming and not outgoing:
                # Node is completely disconnected
                if node.node_type not in ("start",):  # Start nodes can be alone
                    result.add_warning(
                        message="Node has no connections",
                        node_id=node.id,
                        node_name=node.name,
                    )

    def _validate_start_nodes(self, result: ValidationResult) -> None:
        """Validate start node requirements."""
        start_nodes = self._graph.get_nodes_by_type("start")

        if not start_nodes:
            result.add_error(
                message="Graph must have at least one Start node for compilation"
            )
        elif len(start_nodes) > 1:
            result.add_warning(
                message=f"Graph has {len(start_nodes)} Start nodes - "
                "multiple entry points may cause unexpected behavior"
            )


def validate_graph(graph: Graph) -> ValidationResult:
    """
    Convenience function to validate a graph.

    Args:
        graph: The graph to validate.

    Returns:
        ValidationResult containing all issues found.

    Example:
        >>> result = validate_graph(my_graph)
        >>> if result.has_cycles:
        ...     print("Cannot compile: graph contains cycles")
        ...     for cycle in result.cycles:
        ...         print(f"  - {cycle}")
    """
    validator = GraphValidator(graph)
    return validator.validate()


def validate_graph_for_compilation(graph: Graph) -> ValidationResult:
    """
    Convenience function to validate a graph for compilation.

    Args:
        graph: The graph to validate.

    Returns:
        ValidationResult with compilation-specific checks.

    Example:
        >>> result = validate_graph_for_compilation(my_graph)
        >>> if result.can_compile:
        ...     code = CodeGenerator(graph).generate()
        ... else:
        ...     print("Cannot compile:", result.error_messages)
    """
    validator = GraphValidator(graph)
    return validator.validate_for_compilation()
