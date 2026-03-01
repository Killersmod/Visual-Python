"""
Variables module for global variable management and persistence.

This module provides storage for global variables accessible across all nodes.
It enables shared state management throughout the visual scripting environment.

Two storage backends are available:
- GlobalVariableStore: In-memory dictionary-based storage (fast, not persistent)
- SqliteVariableStore: SQLite-backed storage (persistent, scalable for large datasets)

Type Annotations:
- VariableTypeRegistry: Registry for managing type annotations on variables
- TypeAnnotation: Represents a type annotation for a variable
- TypeValidationError: Represents a type validation error
- TypeValidationSeverity: Severity level for validation errors
"""

from visualpython.variables.global_store import GlobalVariableStore
from visualpython.variables.sqlite_store import SqliteVariableStore
from visualpython.variables.type_registry import (
    TypeAnnotation,
    TypeValidationError,
    TypeValidationSeverity,
    VariableTypeRegistry,
)

__all__ = [
    "GlobalVariableStore",
    "SqliteVariableStore",
    "TypeAnnotation",
    "TypeValidationError",
    "TypeValidationSeverity",
    "VariableTypeRegistry",
]
