"""
Type information classes for representing inferred runtime types.

This module provides classes for representing and manipulating type information
during execution, enabling smart validation and type hints for connections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Type, Union, get_args, get_origin

from visualpython.nodes.models.port import PortType


class TypeKind(Enum):
    """Categorizes the kind of type being represented."""

    PRIMITIVE = auto()
    """Simple types like int, str, float, bool."""

    COLLECTION = auto()
    """Collection types like list, dict, set, tuple."""

    COMPOSITE = auto()
    """Complex types with nested type information."""

    UNION = auto()
    """Union of multiple possible types."""

    ANY = auto()
    """Any type (unknown or accepts all)."""

    NONE = auto()
    """None/null type."""


@dataclass
class TypeInfo:
    """
    Represents runtime type information for a value.

    This class captures both the Python type and its mapping to PortType,
    along with any element types for collections.

    Attributes:
        python_type: The Python type of the value.
        port_type: The corresponding PortType enum value.
        kind: The category of type (primitive, collection, etc).
        element_type: For collections, the type of elements (if uniform).
        key_type: For dicts, the type of keys.
        value_type: For dicts, the type of values.
        type_args: Additional type arguments for complex types.
        is_inferred: Whether this type was inferred at runtime.
    """

    python_type: Optional[Type[Any]] = None
    port_type: PortType = PortType.ANY
    kind: TypeKind = TypeKind.ANY
    element_type: Optional[TypeInfo] = None
    key_type: Optional[TypeInfo] = None
    value_type: Optional[TypeInfo] = None
    type_args: List[TypeInfo] = field(default_factory=list)
    is_inferred: bool = True

    def __post_init__(self) -> None:
        """Validate and normalize type info after initialization."""
        if self.type_args is None:
            self.type_args = []

    @property
    def type_name(self) -> str:
        """Get a human-readable name for this type."""
        if self.python_type is None:
            return "Any"

        base_name = self.python_type.__name__

        if self.kind == TypeKind.COLLECTION:
            if self.python_type == list:
                if self.element_type:
                    return f"List[{self.element_type.type_name}]"
                return "List"
            elif self.python_type == dict:
                if self.key_type and self.value_type:
                    return f"Dict[{self.key_type.type_name}, {self.value_type.type_name}]"
                return "Dict"
            elif self.python_type == set:
                if self.element_type:
                    return f"Set[{self.element_type.type_name}]"
                return "Set"
            elif self.python_type == tuple:
                if self.type_args:
                    args_str = ", ".join(t.type_name for t in self.type_args)
                    return f"Tuple[{args_str}]"
                return "Tuple"

        if self.kind == TypeKind.UNION:
            if self.type_args:
                args_str = " | ".join(t.type_name for t in self.type_args)
                return f"({args_str})"

        return base_name

    def is_compatible_with(self, target: TypeInfo) -> bool:
        """
        Check if this type is compatible with a target type.

        Args:
            target: The target type to check compatibility with.

        Returns:
            True if this type can be used where target type is expected.
        """
        # Any accepts everything
        if target.port_type == PortType.ANY:
            return True
        if self.port_type == PortType.ANY:
            return True

        # Same port type is always compatible
        if self.port_type == target.port_type:
            return True

        # Integer can be used where float is expected
        if self.port_type == PortType.INTEGER and target.port_type == PortType.FLOAT:
            return True

        # Float can be used where integer is expected (with truncation)
        if self.port_type == PortType.FLOAT and target.port_type == PortType.INTEGER:
            return True

        return False

    def is_compatible_with_port_type(self, port_type: PortType) -> bool:
        """
        Check if this type is compatible with a declared port type.

        Args:
            port_type: The declared port type to check against.

        Returns:
            True if this type is compatible with the port type.
        """
        # ANY accepts everything
        if port_type == PortType.ANY:
            return True
        if self.port_type == PortType.ANY:
            return True

        # Direct match
        if self.port_type == port_type:
            return True

        # Integer/Float compatibility
        if self.port_type == PortType.INTEGER and port_type == PortType.FLOAT:
            return True
        if self.port_type == PortType.FLOAT and port_type == PortType.INTEGER:
            return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the type info to a dictionary."""
        data: Dict[str, Any] = {
            "type_name": self.type_name,
            "port_type": self.port_type.name,
            "kind": self.kind.name,
            "is_inferred": self.is_inferred,
        }

        if self.python_type:
            data["python_type"] = self.python_type.__name__

        if self.element_type:
            data["element_type"] = self.element_type.to_dict()

        if self.key_type:
            data["key_type"] = self.key_type.to_dict()

        if self.value_type:
            data["value_type"] = self.value_type.to_dict()

        if self.type_args:
            data["type_args"] = [t.to_dict() for t in self.type_args]

        return data

    @classmethod
    def from_value(cls, value: Any) -> TypeInfo:
        """
        Infer type information from a runtime value.

        Args:
            value: The value to infer type from.

        Returns:
            TypeInfo representing the inferred type.
        """
        if value is None:
            return cls(
                python_type=type(None),
                port_type=PortType.ANY,
                kind=TypeKind.NONE,
            )

        python_type = type(value)

        # Handle primitives
        if isinstance(value, bool):
            return cls(
                python_type=bool,
                port_type=PortType.BOOLEAN,
                kind=TypeKind.PRIMITIVE,
            )
        elif isinstance(value, int):
            return cls(
                python_type=int,
                port_type=PortType.INTEGER,
                kind=TypeKind.PRIMITIVE,
            )
        elif isinstance(value, float):
            return cls(
                python_type=float,
                port_type=PortType.FLOAT,
                kind=TypeKind.PRIMITIVE,
            )
        elif isinstance(value, str):
            return cls(
                python_type=str,
                port_type=PortType.STRING,
                kind=TypeKind.PRIMITIVE,
            )

        # Handle collections
        if isinstance(value, list):
            element_type = None
            if len(value) > 0:
                # Infer element type from first element
                # For more robust inference, could check all elements
                first_elem_type = cls.from_value(value[0])
                # Check if all elements have the same type
                all_same = all(
                    cls.from_value(elem).port_type == first_elem_type.port_type
                    for elem in value
                )
                if all_same:
                    element_type = first_elem_type

            return cls(
                python_type=list,
                port_type=PortType.LIST,
                kind=TypeKind.COLLECTION,
                element_type=element_type,
            )

        if isinstance(value, dict):
            key_type = None
            value_type = None

            if len(value) > 0:
                # Infer key and value types from first item
                first_key, first_val = next(iter(value.items()))
                key_type = cls.from_value(first_key)
                value_type = cls.from_value(first_val)

            return cls(
                python_type=dict,
                port_type=PortType.DICT,
                kind=TypeKind.COLLECTION,
                key_type=key_type,
                value_type=value_type,
            )

        if isinstance(value, set):
            element_type = None
            if len(value) > 0:
                first_elem = next(iter(value))
                element_type = cls.from_value(first_elem)

            return cls(
                python_type=set,
                port_type=PortType.LIST,  # Sets map to LIST port type
                kind=TypeKind.COLLECTION,
                element_type=element_type,
            )

        if isinstance(value, tuple):
            type_args = [cls.from_value(elem) for elem in value]
            return cls(
                python_type=tuple,
                port_type=PortType.LIST,  # Tuples map to LIST port type
                kind=TypeKind.COLLECTION,
                type_args=type_args,
            )

        # Default to OBJECT for anything else
        return cls(
            python_type=python_type,
            port_type=PortType.OBJECT,
            kind=TypeKind.COMPOSITE,
        )

    @classmethod
    def from_port_type(cls, port_type: PortType) -> TypeInfo:
        """
        Create a TypeInfo from a PortType declaration.

        Args:
            port_type: The port type to create TypeInfo for.

        Returns:
            TypeInfo representing the declared type.
        """
        type_mapping: Dict[PortType, tuple] = {
            PortType.ANY: (None, TypeKind.ANY),
            PortType.FLOW: (None, TypeKind.NONE),
            PortType.STRING: (str, TypeKind.PRIMITIVE),
            PortType.INTEGER: (int, TypeKind.PRIMITIVE),
            PortType.FLOAT: (float, TypeKind.PRIMITIVE),
            PortType.BOOLEAN: (bool, TypeKind.PRIMITIVE),
            PortType.LIST: (list, TypeKind.COLLECTION),
            PortType.DICT: (dict, TypeKind.COLLECTION),
            PortType.OBJECT: (object, TypeKind.COMPOSITE),
        }

        python_type, kind = type_mapping.get(port_type, (None, TypeKind.ANY))

        return cls(
            python_type=python_type,
            port_type=port_type,
            kind=kind,
            is_inferred=False,
        )

    @classmethod
    def any_type(cls) -> TypeInfo:
        """Create a TypeInfo representing any type."""
        return cls(
            python_type=None,
            port_type=PortType.ANY,
            kind=TypeKind.ANY,
            is_inferred=False,
        )

    def __eq__(self, other: object) -> bool:
        """Check equality with another TypeInfo."""
        if not isinstance(other, TypeInfo):
            return NotImplemented
        return (
            self.python_type == other.python_type
            and self.port_type == other.port_type
            and self.kind == other.kind
        )

    def __hash__(self) -> int:
        """Hash for TypeInfo."""
        return hash((self.python_type, self.port_type, self.kind))

    def __repr__(self) -> str:
        """Get string representation."""
        return f"TypeInfo({self.type_name}, port_type={self.port_type.name})"


@dataclass
class TypeMismatch:
    """
    Represents a type mismatch between an inferred type and expected type.

    Attributes:
        source_node_id: ID of the node producing the value.
        source_port_name: Name of the output port.
        target_node_id: ID of the node receiving the value.
        target_port_name: Name of the input port.
        inferred_type: The actual inferred type of the value.
        expected_type: The expected type from the port declaration.
        message: Human-readable description of the mismatch.
        severity: Severity level (warning, error).
    """

    source_node_id: str
    source_port_name: str
    target_node_id: str
    target_port_name: str
    inferred_type: TypeInfo
    expected_type: TypeInfo
    message: str = ""
    severity: str = "warning"

    def __post_init__(self) -> None:
        """Generate message if not provided."""
        if not self.message:
            self.message = (
                f"Type mismatch: {self.inferred_type.type_name} "
                f"is not compatible with {self.expected_type.type_name}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the type mismatch to a dictionary."""
        return {
            "source_node_id": self.source_node_id,
            "source_port_name": self.source_port_name,
            "target_node_id": self.target_node_id,
            "target_port_name": self.target_port_name,
            "inferred_type": self.inferred_type.to_dict(),
            "expected_type": self.expected_type.to_dict(),
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class PortTypeInfo:
    """
    Stores type information for a specific port.

    Attributes:
        node_id: ID of the node owning the port.
        port_name: Name of the port.
        is_input: Whether this is an input port.
        declared_type: The type declared on the port.
        inferred_type: The type inferred at runtime.
        last_value: The last value that flowed through (for debugging).
    """

    node_id: str
    port_name: str
    is_input: bool
    declared_type: TypeInfo
    inferred_type: Optional[TypeInfo] = None
    last_value: Optional[Any] = None

    @property
    def effective_type(self) -> TypeInfo:
        """Get the most specific known type (inferred if available, else declared)."""
        if self.inferred_type and self.inferred_type.kind != TypeKind.ANY:
            return self.inferred_type
        return self.declared_type

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the port type info to a dictionary."""
        return {
            "node_id": self.node_id,
            "port_name": self.port_name,
            "is_input": self.is_input,
            "declared_type": self.declared_type.to_dict(),
            "inferred_type": self.inferred_type.to_dict() if self.inferred_type else None,
        }
