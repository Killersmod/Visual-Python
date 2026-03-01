"""
Serialization module for VisualPython projects.

This module provides functionality for saving and loading visual Python
programs to and from JSON files, as well as persisting global variables
and exporting/importing reusable node libraries.

Two variable serialization backends are available:
- VariableSerializer: JSON-based serialization (simple, human-readable)
- SqliteVariableSerializer: SQLite-based serialization (scalable, efficient)
"""

from visualpython.serialization.project_serializer import (
    ProjectSerializer,
    save_project,
    load_project,
    SerializationError,
)
from visualpython.serialization.variable_serializer import (
    VariableSerializer,
    save_variables,
    load_variables,
)
from visualpython.serialization.library_serializer import (
    LibrarySerializer,
    LibraryData,
    LibraryMetadata,
    export_library,
    load_library,
)
from visualpython.serialization.sqlite_variable_serializer import (
    SqliteVariableSerializer,
    create_sqlite_store,
    save_variables_sqlite,
    load_variables_sqlite,
    migrate_json_to_sqlite,
)

__all__ = [
    # Project serialization
    "ProjectSerializer",
    "save_project",
    "load_project",
    "SerializationError",
    # JSON variable serialization
    "VariableSerializer",
    "save_variables",
    "load_variables",
    # SQLite variable serialization
    "SqliteVariableSerializer",
    "create_sqlite_store",
    "save_variables_sqlite",
    "load_variables_sqlite",
    "migrate_json_to_sqlite",
    # Library serialization
    "LibrarySerializer",
    "LibraryData",
    "LibraryMetadata",
    "export_library",
    "load_library",
]
