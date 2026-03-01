"""
Type inference engine for inferring data types flowing through connections.

This module provides the TypeInferenceEngine that tracks and infers types
as data flows through the visual script, enabling smart validation and hints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from visualpython.execution.type_info import (
    PortTypeInfo,
    TypeInfo,
    TypeKind,
    TypeMismatch,
)
from visualpython.nodes.models.port import PortType

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode
    from visualpython.nodes.models.connection_model import ConnectionModel
    from visualpython.nodes.models.port import Connection, InputPort, OutputPort


@dataclass
class InferenceResult:
    """
    Result of a type inference operation.

    Attributes:
        inferred_types: Dictionary mapping (node_id, port_name) to inferred TypeInfo.
        mismatches: List of detected type mismatches.
        warnings: List of warning messages.
        errors: List of error messages.
    """

    inferred_types: Dict[tuple, TypeInfo] = field(default_factory=dict)
    mismatches: List[TypeMismatch] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    @property
    def has_mismatches(self) -> bool:
        """Check if there are any type mismatches."""
        return len(self.mismatches) > 0

    def get_type(self, node_id: str, port_name: str) -> Optional[TypeInfo]:
        """Get the inferred type for a specific port."""
        return self.inferred_types.get((node_id, port_name))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the inference result to a dictionary."""
        return {
            "inferred_types": {
                f"{node_id}.{port_name}": type_info.to_dict()
                for (node_id, port_name), type_info in self.inferred_types.items()
            },
            "mismatches": [m.to_dict() for m in self.mismatches],
            "warnings": self.warnings.copy(),
            "errors": self.errors.copy(),
        }


class TypeInferenceEngine:
    """
    Engine for inferring data types flowing through connections.

    The TypeInferenceEngine tracks types as data flows through the visual
    script during execution. It provides:
    - Runtime type inference from actual values
    - Type compatibility checking between connections
    - Detection of type mismatches
    - Type hints for smart validation

    Example:
        >>> engine = TypeInferenceEngine()
        >>> engine.record_output(node_id, "result", 42)
        >>> type_info = engine.get_inferred_type(node_id, "result")
        >>> print(type_info.type_name)  # "int"
    """

    def __init__(
        self,
        on_type_inferred: Optional[Callable[[str, str, TypeInfo], None]] = None,
        on_mismatch_detected: Optional[Callable[[TypeMismatch], None]] = None,
        strict_mode: bool = False,
    ) -> None:
        """
        Initialize the type inference engine.

        Args:
            on_type_inferred: Optional callback when a type is inferred.
            on_mismatch_detected: Optional callback when a mismatch is detected.
            strict_mode: If True, type mismatches are treated as errors.
        """
        self._on_type_inferred = on_type_inferred
        self._on_mismatch_detected = on_mismatch_detected
        self._strict_mode = strict_mode

        # Maps (node_id, port_name) -> TypeInfo
        self._inferred_output_types: Dict[tuple, TypeInfo] = {}
        self._inferred_input_types: Dict[tuple, TypeInfo] = {}

        # Maps (node_id, port_name) -> declared PortType
        self._declared_types: Dict[tuple, PortType] = {}

        # Store type mismatches detected during execution
        self._mismatches: List[TypeMismatch] = []

        # Track which node IDs have been visited for type propagation
        self._visited: Set[str] = set()

    def reset(self) -> None:
        """Reset all inferred type information."""
        self._inferred_output_types.clear()
        self._inferred_input_types.clear()
        self._declared_types.clear()
        self._mismatches.clear()
        self._visited.clear()

    def register_port(
        self,
        node_id: str,
        port_name: str,
        port_type: PortType,
        is_output: bool,
    ) -> None:
        """
        Register a port's declared type.

        Args:
            node_id: ID of the node owning the port.
            port_name: Name of the port.
            port_type: Declared type of the port.
            is_output: Whether this is an output port.
        """
        self._declared_types[(node_id, port_name)] = port_type

    def record_output(
        self,
        node_id: str,
        port_name: str,
        value: Any,
    ) -> TypeInfo:
        """
        Record an output value and infer its type.

        This method is called when a node produces an output value.
        It infers the type from the value and stores it for later use.

        Args:
            node_id: ID of the node producing the output.
            port_name: Name of the output port.
            value: The output value.

        Returns:
            The inferred TypeInfo for the value.
        """
        type_info = TypeInfo.from_value(value)
        self._inferred_output_types[(node_id, port_name)] = type_info

        # Notify callback
        if self._on_type_inferred:
            self._on_type_inferred(node_id, port_name, type_info)

        return type_info

    def record_input(
        self,
        node_id: str,
        port_name: str,
        value: Any,
        source_node_id: Optional[str] = None,
        source_port_name: Optional[str] = None,
    ) -> Optional[TypeMismatch]:
        """
        Record an input value and check for type compatibility.

        This method is called when a node receives an input value.
        It checks the inferred type against the declared port type.

        Args:
            node_id: ID of the node receiving the input.
            port_name: Name of the input port.
            value: The input value.
            source_node_id: Optional ID of the source node.
            source_port_name: Optional name of the source port.

        Returns:
            TypeMismatch if a type mismatch is detected, None otherwise.
        """
        type_info = TypeInfo.from_value(value)
        self._inferred_input_types[(node_id, port_name)] = type_info

        # Check against declared type
        declared_port_type = self._declared_types.get((node_id, port_name), PortType.ANY)
        declared_type_info = TypeInfo.from_port_type(declared_port_type)

        if not type_info.is_compatible_with(declared_type_info):
            mismatch = TypeMismatch(
                source_node_id=source_node_id or "",
                source_port_name=source_port_name or "",
                target_node_id=node_id,
                target_port_name=port_name,
                inferred_type=type_info,
                expected_type=declared_type_info,
                severity="error" if self._strict_mode else "warning",
            )
            self._mismatches.append(mismatch)

            if self._on_mismatch_detected:
                self._on_mismatch_detected(mismatch)

            return mismatch

        return None

    def get_inferred_type(
        self,
        node_id: str,
        port_name: str,
        is_output: bool = True,
    ) -> Optional[TypeInfo]:
        """
        Get the inferred type for a port.

        Args:
            node_id: ID of the node.
            port_name: Name of the port.
            is_output: Whether this is an output port.

        Returns:
            The inferred TypeInfo if available, None otherwise.
        """
        if is_output:
            return self._inferred_output_types.get((node_id, port_name))
        return self._inferred_input_types.get((node_id, port_name))

    def get_effective_type(
        self,
        node_id: str,
        port_name: str,
        is_output: bool = True,
    ) -> TypeInfo:
        """
        Get the most specific known type for a port.

        Returns the inferred type if available, otherwise the declared type.

        Args:
            node_id: ID of the node.
            port_name: Name of the port.
            is_output: Whether this is an output port.

        Returns:
            The most specific TypeInfo available.
        """
        # Try inferred type first
        inferred = self.get_inferred_type(node_id, port_name, is_output)
        if inferred and inferred.kind != TypeKind.ANY:
            return inferred

        # Fall back to declared type
        declared_port_type = self._declared_types.get((node_id, port_name), PortType.ANY)
        return TypeInfo.from_port_type(declared_port_type)

    def get_mismatches(self) -> List[TypeMismatch]:
        """Get all detected type mismatches."""
        return self._mismatches.copy()

    def get_result(self) -> InferenceResult:
        """
        Get the complete inference result.

        Returns:
            InferenceResult containing all inferred types and mismatches.
        """
        all_types = {}
        all_types.update(self._inferred_output_types)
        all_types.update(self._inferred_input_types)

        return InferenceResult(
            inferred_types=all_types,
            mismatches=self._mismatches.copy(),
        )

    def propagate_types(
        self,
        connection_model: ConnectionModel,
        start_node_id: str,
    ) -> InferenceResult:
        """
        Propagate inferred types through connections starting from a node.

        This performs forward type propagation through the graph,
        updating inferred types for connected input ports based on
        the output types of their source nodes.

        Args:
            connection_model: The connection model to traverse.
            start_node_id: ID of the node to start propagation from.

        Returns:
            InferenceResult with propagated types and any mismatches.
        """
        self._visited.clear()
        self._propagate_from_node(connection_model, start_node_id)

        return self.get_result()

    def _propagate_from_node(
        self,
        connection_model: ConnectionModel,
        node_id: str,
    ) -> None:
        """
        Recursively propagate types from a node to its downstream connections.

        Args:
            connection_model: The connection model to traverse.
            node_id: ID of the current node.
        """
        if node_id in self._visited:
            return
        self._visited.add(node_id)

        # Get outgoing connections and propagate types
        outgoing = connection_model.get_outgoing_connections(node_id)

        for conn in outgoing:
            # Get the inferred output type
            output_type = self._inferred_output_types.get(
                (conn.source_node_id, conn.source_port_name)
            )

            if output_type:
                # Propagate to the target input port
                self._inferred_input_types[
                    (conn.target_node_id, conn.target_port_name)
                ] = output_type

                # Check for type mismatch
                declared_port_type = self._declared_types.get(
                    (conn.target_node_id, conn.target_port_name),
                    PortType.ANY,
                )
                declared_type_info = TypeInfo.from_port_type(declared_port_type)

                if not output_type.is_compatible_with(declared_type_info):
                    mismatch = TypeMismatch(
                        source_node_id=conn.source_node_id,
                        source_port_name=conn.source_port_name,
                        target_node_id=conn.target_node_id,
                        target_port_name=conn.target_port_name,
                        inferred_type=output_type,
                        expected_type=declared_type_info,
                        severity="error" if self._strict_mode else "warning",
                    )
                    self._mismatches.append(mismatch)

                    if self._on_mismatch_detected:
                        self._on_mismatch_detected(mismatch)

            # Continue propagation to downstream node
            self._propagate_from_node(connection_model, conn.target_node_id)

    def validate_connection_types(
        self,
        source_node_id: str,
        source_port_name: str,
        target_node_id: str,
        target_port_name: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that a connection has compatible types.

        Uses inferred types when available for more accurate validation.

        Args:
            source_node_id: ID of the source node.
            source_port_name: Name of the source port.
            target_node_id: ID of the target node.
            target_port_name: Name of the target port.

        Returns:
            Tuple of (is_valid, error_message).
        """
        # Get source type (prefer inferred, fall back to declared)
        source_type = self.get_effective_type(
            source_node_id, source_port_name, is_output=True
        )

        # Get target type (declared)
        target_port_type = self._declared_types.get(
            (target_node_id, target_port_name),
            PortType.ANY,
        )
        target_type = TypeInfo.from_port_type(target_port_type)

        if source_type.is_compatible_with(target_type):
            return True, None

        error_msg = (
            f"Type mismatch: {source_type.type_name} cannot connect to "
            f"{target_type.type_name}"
        )
        return False, error_msg

    def get_type_hints(
        self,
        node_id: str,
        port_name: str,
        is_output: bool = True,
    ) -> Dict[str, Any]:
        """
        Get type hints for a port for UI display.

        Returns a dictionary with type information suitable for
        displaying in the UI, including tooltips and badges.

        Args:
            node_id: ID of the node.
            port_name: Name of the port.
            is_output: Whether this is an output port.

        Returns:
            Dictionary with type hint information.
        """
        effective_type = self.get_effective_type(node_id, port_name, is_output)
        inferred = self.get_inferred_type(node_id, port_name, is_output)

        return {
            "type_name": effective_type.type_name,
            "port_type": effective_type.port_type.name,
            "is_inferred": inferred is not None,
            "declared_type": self._declared_types.get(
                (node_id, port_name), PortType.ANY
            ).name,
            "tooltip": f"Type: {effective_type.type_name}"
            + (f" (inferred)" if inferred else " (declared)"),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the engine state to a dictionary."""
        return {
            "inferred_output_types": {
                f"{node_id}.{port_name}": type_info.to_dict()
                for (node_id, port_name), type_info in self._inferred_output_types.items()
            },
            "inferred_input_types": {
                f"{node_id}.{port_name}": type_info.to_dict()
                for (node_id, port_name), type_info in self._inferred_input_types.items()
            },
            "mismatches": [m.to_dict() for m in self._mismatches],
        }

    def __repr__(self) -> str:
        """Get string representation."""
        return (
            f"TypeInferenceEngine("
            f"outputs={len(self._inferred_output_types)}, "
            f"inputs={len(self._inferred_input_types)}, "
            f"mismatches={len(self._mismatches)})"
        )
