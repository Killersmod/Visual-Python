"""
Variable type registry for managing type annotations on global variables.

This module provides the VariableTypeRegistry class which allows users to
specify expected types for global variables with validation. This improves
code safety by catching type errors early during execution.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Type, Union

from visualpython.nodes.models.port import PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class TypeValidationSeverity(Enum):
    """Severity level for type validation violations."""

    ERROR = auto()
    """Type mismatch should cause execution to fail."""

    WARNING = auto()
    """Type mismatch should be logged but execution continues."""


@dataclass
class TypeAnnotation:
    """
    Represents a type annotation for a global variable.

    Attributes:
        variable_name: The name of the variable this annotation applies to.
        expected_type: The expected PortType for the variable.
        python_types: Optional tuple of Python types that are acceptable.
        severity: The severity level for validation violations.
        description: Optional description of the expected type.
        allow_none: Whether None is an acceptable value.
    """

    variable_name: str
    expected_type: PortType
    python_types: tuple[type, ...] = field(default_factory=tuple)
    severity: TypeValidationSeverity = TypeValidationSeverity.ERROR
    description: str = ""
    allow_none: bool = False

    def __post_init__(self) -> None:
        """Set up python_types based on expected_type if not provided."""
        if not self.python_types:
            self.python_types = _get_python_types_for_port_type(self.expected_type)

    def validate(self, value: Any) -> Optional[TypeValidationError]:
        """
        Validate a value against this type annotation.

        Args:
            value: The value to validate.

        Returns:
            A TypeValidationError if validation fails, None if valid.
        """
        # Handle None values
        if value is None:
            if self.allow_none:
                return None
            return TypeValidationError(
                variable_name=self.variable_name,
                expected_type=self.expected_type,
                actual_type=type(None),
                actual_value=value,
                message=f"Variable '{self.variable_name}' does not allow None values",
                severity=self.severity,
            )

        # ANY type accepts everything
        if self.expected_type == PortType.ANY:
            return None

        # FLOW type is not valid for variable values
        if self.expected_type == PortType.FLOW:
            return TypeValidationError(
                variable_name=self.variable_name,
                expected_type=self.expected_type,
                actual_type=type(value),
                actual_value=value,
                message=f"Variable '{self.variable_name}' cannot have FLOW type",
                severity=self.severity,
            )

        # Check against python_types
        if self.python_types and not isinstance(value, self.python_types):
            expected_names = ", ".join(t.__name__ for t in self.python_types)
            return TypeValidationError(
                variable_name=self.variable_name,
                expected_type=self.expected_type,
                actual_type=type(value),
                actual_value=value,
                message=(
                    f"Variable '{self.variable_name}' expected type "
                    f"{expected_names}, got {type(value).__name__}"
                ),
                severity=self.severity,
            )

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the type annotation to a dictionary."""
        return {
            "variable_name": self.variable_name,
            "expected_type": self.expected_type.name,
            "python_types": [t.__name__ for t in self.python_types],
            "severity": self.severity.name,
            "description": self.description,
            "allow_none": self.allow_none,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TypeAnnotation:
        """Deserialize a type annotation from a dictionary."""
        return cls(
            variable_name=data["variable_name"],
            expected_type=PortType[data["expected_type"]],
            python_types=tuple(
                _get_type_by_name(name) for name in data.get("python_types", [])
            ),
            severity=TypeValidationSeverity[data.get("severity", "ERROR")],
            description=data.get("description", ""),
            allow_none=data.get("allow_none", False),
        )


@dataclass
class TypeValidationError:
    """
    Represents a type validation error for a variable.

    Attributes:
        variable_name: The name of the variable that failed validation.
        expected_type: The expected PortType.
        actual_type: The actual Python type of the value.
        actual_value: The actual value that failed validation.
        message: Human-readable error message.
        severity: The severity level of this error.
    """

    variable_name: str
    expected_type: PortType
    actual_type: type
    actual_value: Any
    message: str
    severity: TypeValidationSeverity = TypeValidationSeverity.ERROR

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the validation error to a dictionary."""
        return {
            "variable_name": self.variable_name,
            "expected_type": self.expected_type.name,
            "actual_type": self.actual_type.__name__,
            "actual_value": repr(self.actual_value),
            "message": self.message,
            "severity": self.severity.name,
        }


class VariableTypeRegistry:
    """
    Registry for managing type annotations on global variables.

    The VariableTypeRegistry maintains a collection of type annotations
    that specify expected types for global variables. It provides validation
    methods to check values against their declared types.

    This class implements a singleton pattern to ensure all components
    access the same registry instance.

    Thread Safety:
        All methods in this class are thread-safe through the use of a
        reentrant lock (RLock).

    Example:
        >>> registry = VariableTypeRegistry.get_instance()
        >>> registry.set_annotation("counter", PortType.INTEGER)
        >>> registry.validate("counter", 42)  # Returns None (valid)
        >>> registry.validate("counter", "hello")  # Returns TypeValidationError
    """

    _instance: Optional[VariableTypeRegistry] = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        """
        Initialize a new VariableTypeRegistry instance.

        Note:
            This constructor should not be called directly. Use
            get_instance() to obtain the singleton instance.
        """
        self._annotations: Dict[str, TypeAnnotation] = {}
        self._lock: threading.RLock = threading.RLock()
        self._validation_callbacks: List[Callable[[TypeValidationError], None]] = []

    @classmethod
    def get_instance(cls) -> VariableTypeRegistry:
        """
        Get the singleton instance of the VariableTypeRegistry.

        This method is thread-safe through double-checked locking pattern.

        Returns:
            The single VariableTypeRegistry instance.
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset the singleton instance.

        This is primarily useful for testing purposes to ensure
        a clean state between tests. This method is thread-safe.
        """
        with cls._instance_lock:
            cls._instance = None

    def set_annotation(
        self,
        variable_name: str,
        expected_type: PortType,
        python_types: Optional[tuple[type, ...]] = None,
        severity: TypeValidationSeverity = TypeValidationSeverity.ERROR,
        description: str = "",
        allow_none: bool = False,
    ) -> TypeAnnotation:
        """
        Set a type annotation for a variable.

        Args:
            variable_name: The name of the variable to annotate.
            expected_type: The expected PortType for the variable.
            python_types: Optional tuple of acceptable Python types.
            severity: The severity level for validation violations.
            description: Optional description of the expected type.
            allow_none: Whether None is an acceptable value.

        Returns:
            The created TypeAnnotation.

        Example:
            >>> registry.set_annotation("counter", PortType.INTEGER)
            >>> registry.set_annotation(
            ...     "config",
            ...     PortType.DICT,
            ...     description="Application configuration",
            ...     allow_none=True
            ... )
        """
        annotation = TypeAnnotation(
            variable_name=variable_name,
            expected_type=expected_type,
            python_types=python_types or tuple(),
            severity=severity,
            description=description,
            allow_none=allow_none,
        )
        with self._lock:
            self._annotations[variable_name] = annotation
        return annotation

    def set_annotation_from_type(
        self,
        variable_name: str,
        python_type: type,
        severity: TypeValidationSeverity = TypeValidationSeverity.ERROR,
        description: str = "",
        allow_none: bool = False,
    ) -> TypeAnnotation:
        """
        Set a type annotation using a Python type.

        Convenience method that infers the PortType from a Python type.

        Args:
            variable_name: The name of the variable to annotate.
            python_type: The expected Python type.
            severity: The severity level for validation violations.
            description: Optional description of the expected type.
            allow_none: Whether None is an acceptable value.

        Returns:
            The created TypeAnnotation.

        Example:
            >>> registry.set_annotation_from_type("counter", int)
            >>> registry.set_annotation_from_type("name", str, allow_none=True)
        """
        port_type = _get_port_type_for_python_type(python_type)
        return self.set_annotation(
            variable_name=variable_name,
            expected_type=port_type,
            python_types=(python_type,),
            severity=severity,
            description=description,
            allow_none=allow_none,
        )

    def get_annotation(self, variable_name: str) -> Optional[TypeAnnotation]:
        """
        Get the type annotation for a variable.

        Args:
            variable_name: The name of the variable.

        Returns:
            The TypeAnnotation if one exists, None otherwise.
        """
        with self._lock:
            return self._annotations.get(variable_name)

    def has_annotation(self, variable_name: str) -> bool:
        """
        Check if a variable has a type annotation.

        Args:
            variable_name: The name of the variable.

        Returns:
            True if the variable has an annotation, False otherwise.
        """
        with self._lock:
            return variable_name in self._annotations

    def remove_annotation(self, variable_name: str) -> bool:
        """
        Remove the type annotation for a variable.

        Args:
            variable_name: The name of the variable.

        Returns:
            True if an annotation was removed, False if none existed.
        """
        with self._lock:
            if variable_name in self._annotations:
                del self._annotations[variable_name]
                return True
            return False

    def validate(self, variable_name: str, value: Any) -> Optional[TypeValidationError]:
        """
        Validate a value against the type annotation for a variable.

        Args:
            variable_name: The name of the variable.
            value: The value to validate.

        Returns:
            A TypeValidationError if validation fails, None if valid or
            if no annotation exists for the variable.

        Example:
            >>> error = registry.validate("counter", "not an int")
            >>> if error:
            ...     print(error.message)
        """
        annotation = self.get_annotation(variable_name)
        if annotation is None:
            return None

        error = annotation.validate(value)
        if error is not None:
            self._notify_validation_error(error)
        return error

    def validate_strict(
        self, variable_name: str, value: Any
    ) -> Optional[TypeValidationError]:
        """
        Validate a value strictly, raising ValueError for errors with ERROR severity.

        Args:
            variable_name: The name of the variable.
            value: The value to validate.

        Returns:
            A TypeValidationError for WARNING severity violations.

        Raises:
            ValueError: If validation fails with ERROR severity.
        """
        error = self.validate(variable_name, value)
        if error is not None and error.severity == TypeValidationSeverity.ERROR:
            raise ValueError(error.message)
        return error

    def list_annotations(self) -> Dict[str, TypeAnnotation]:
        """
        Get a copy of all type annotations.

        Returns:
            A dictionary mapping variable names to their TypeAnnotations.
        """
        with self._lock:
            return self._annotations.copy()

    def list_annotated_variables(self) -> List[str]:
        """
        Get a list of all annotated variable names.

        Returns:
            A list of variable names that have type annotations.
        """
        with self._lock:
            return list(self._annotations.keys())

    def clear(self) -> None:
        """Clear all type annotations."""
        with self._lock:
            self._annotations.clear()

    def add_validation_callback(
        self, callback: Callable[[TypeValidationError], None]
    ) -> None:
        """
        Add a callback to be invoked when a validation error occurs.

        Args:
            callback: A function that takes a TypeValidationError.
        """
        with self._lock:
            self._validation_callbacks.append(callback)

    def remove_validation_callback(
        self, callback: Callable[[TypeValidationError], None]
    ) -> bool:
        """
        Remove a validation callback.

        Args:
            callback: The callback to remove.

        Returns:
            True if the callback was removed, False if not found.
        """
        with self._lock:
            try:
                self._validation_callbacks.remove(callback)
                return True
            except ValueError:
                logger.debug("Type validation failed", exc_info=True)
                return False

    def _notify_validation_error(self, error: TypeValidationError) -> None:
        """Notify all registered callbacks of a validation error."""
        with self._lock:
            callbacks = self._validation_callbacks.copy()
        for callback in callbacks:
            try:
                callback(error)
            except Exception:
                pass  # Don't let callback errors break validation

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all annotations to a dictionary."""
        with self._lock:
            return {
                name: annotation.to_dict()
                for name, annotation in self._annotations.items()
            }

    def from_dict(self, data: Dict[str, Any], merge: bool = False) -> int:
        """
        Load annotations from a dictionary.

        Args:
            data: Dictionary mapping variable names to annotation data.
            merge: If True, merge with existing annotations.
                   If False, clear existing annotations first.

        Returns:
            Number of annotations loaded.
        """
        with self._lock:
            if not merge:
                self._annotations.clear()

            loaded = 0
            for name, annotation_data in data.items():
                try:
                    annotation = TypeAnnotation.from_dict(annotation_data)
                    self._annotations[name] = annotation
                    loaded += 1
                except Exception:
                    pass  # Skip invalid annotations

            return loaded

    def count(self) -> int:
        """Get the number of type annotations."""
        with self._lock:
            return len(self._annotations)

    def __len__(self) -> int:
        """Get the number of type annotations using len()."""
        return self.count()

    def __contains__(self, variable_name: str) -> bool:
        """Check if a variable has an annotation using 'in' operator."""
        return self.has_annotation(variable_name)

    def __repr__(self) -> str:
        """Get a string representation of the registry."""
        with self._lock:
            count = len(self._annotations)
        return f"VariableTypeRegistry(annotations={count})"


def _get_python_types_for_port_type(port_type: PortType) -> tuple[type, ...]:
    """
    Get the Python types corresponding to a PortType.

    Args:
        port_type: The PortType to convert.

    Returns:
        A tuple of Python types.
    """
    type_mapping: Dict[PortType, tuple[type, ...]] = {
        PortType.ANY: (),  # Empty tuple means any type
        PortType.FLOW: (),
        PortType.STRING: (str,),
        PortType.INTEGER: (int,),
        PortType.FLOAT: (int, float),  # int is acceptable for float
        PortType.BOOLEAN: (bool,),
        PortType.LIST: (list,),
        PortType.DICT: (dict,),
        PortType.OBJECT: (object,),
    }
    return type_mapping.get(port_type, ())


def _get_port_type_for_python_type(python_type: type) -> PortType:
    """
    Get the PortType corresponding to a Python type.

    Args:
        python_type: The Python type to convert.

    Returns:
        The corresponding PortType.
    """
    type_mapping: Dict[type, PortType] = {
        str: PortType.STRING,
        int: PortType.INTEGER,
        float: PortType.FLOAT,
        bool: PortType.BOOLEAN,
        list: PortType.LIST,
        dict: PortType.DICT,
    }
    return type_mapping.get(python_type, PortType.OBJECT)


def _get_type_by_name(name: str) -> type:
    """
    Get a Python type by its name.

    Args:
        name: The name of the type.

    Returns:
        The Python type.
    """
    builtin_types: Dict[str, type] = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "frozenset": frozenset,
        "bytes": bytes,
        "NoneType": type(None),
        "object": object,
    }
    return builtin_types.get(name, object)
