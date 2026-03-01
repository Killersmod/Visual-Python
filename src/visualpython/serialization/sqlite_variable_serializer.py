"""
SQLite-based variable serialization for persistent storage.

This module provides the SqliteVariableSerializer class and convenience functions
for managing global variables using SQLite storage, enabling efficient persistence
of application state across sessions with better performance for large datasets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from visualpython.serialization.project_serializer import SerializationError
from visualpython.variables.global_store import GlobalVariableStore
from visualpython.variables.sqlite_store import SqliteVariableStore


class SqliteVariableSerializer:
    """
    Handles serialization and deserialization of global variables using SQLite.

    The SqliteVariableSerializer provides an alternative to the JSON-based
    VariableSerializer, using SQLite for storage. This offers better performance
    for large datasets and supports incremental updates without rewriting the
    entire file.

    Example:
        >>> serializer = SqliteVariableSerializer("variables.db")
        >>> serializer.save()
        >>> serializer.load()

    Attributes:
        FILE_FORMAT_VERSION: Current version of the storage format.
    """

    FILE_FORMAT_VERSION = "1.0.0"

    def __init__(
        self,
        db_path: Union[str, Path],
        store: Optional[GlobalVariableStore] = None,
        wal_mode: bool = True,
    ) -> None:
        """
        Initialize the SQLite variable serializer.

        Args:
            db_path: Path to the SQLite database file.
            store: Optional GlobalVariableStore to sync with. If not provided,
                   uses the singleton instance.
            wal_mode: If True, enable Write-Ahead Logging for better
                      concurrent performance. Defaults to True.
        """
        self._db_path = Path(db_path)
        self._memory_store = store or GlobalVariableStore.get_instance()
        self._sqlite_store = SqliteVariableStore(db_path, wal_mode=wal_mode)

    @property
    def db_path(self) -> Path:
        """Get the database file path."""
        return self._db_path

    @property
    def sqlite_store(self) -> SqliteVariableStore:
        """Get the underlying SQLite store for direct access."""
        return self._sqlite_store

    def save(self) -> int:
        """
        Save global variables from memory to SQLite.

        This synchronizes the in-memory GlobalVariableStore to the SQLite
        database, making all variables persistent.

        Returns:
            Number of variables saved.

        Raises:
            SerializationError: If the save operation fails.
        """
        try:
            return self._sqlite_store.sync_from_global_store()
        except Exception as e:
            raise SerializationError(f"Failed to save variables to SQLite: {e}") from e

    def load(self, merge: bool = False) -> int:
        """
        Load global variables from SQLite to memory.

        This synchronizes the SQLite database to the in-memory
        GlobalVariableStore, restoring persisted variables.

        Args:
            merge: If True, merge loaded variables with existing ones.
                   If False (default), clear existing variables first.

        Returns:
            Number of variables loaded.

        Raises:
            SerializationError: If the load operation fails.
        """
        try:
            if merge:
                # Get existing variables
                existing = self._memory_store.list_all()
                # Load from SQLite
                self._sqlite_store.sync_to_global_store()
                # Merge back existing (SQLite values take precedence)
                for name, value in existing.items():
                    if not self._memory_store.exists(name):
                        self._memory_store.set(name, value)
                return self._memory_store.count()
            else:
                return self._sqlite_store.sync_to_global_store()
        except Exception as e:
            raise SerializationError(f"Failed to load variables from SQLite: {e}") from e

    def set(self, name: str, value: Any) -> None:
        """
        Set a variable in both memory and SQLite simultaneously.

        This provides real-time persistence - every change is immediately
        saved to the database.

        Args:
            name: The name of the variable.
            value: The value to store.
        """
        self._memory_store.set(name, value)
        self._sqlite_store.set(name, value)

    def get(self, name: str, default: Any = None) -> Any:
        """
        Get a variable value.

        This reads from the in-memory store for performance.

        Args:
            name: The name of the variable.
            default: Default value if not found.

        Returns:
            The variable value or default.
        """
        return self._memory_store.get(name, default)

    def delete(self, name: str) -> bool:
        """
        Delete a variable from both memory and SQLite.

        Args:
            name: The name of the variable to delete.

        Returns:
            True if deleted, False if not found.
        """
        memory_deleted = self._memory_store.delete(name)
        sqlite_deleted = self._sqlite_store.delete(name)
        return memory_deleted or sqlite_deleted

    def clear(self) -> None:
        """
        Clear all variables from both memory and SQLite.
        """
        self._memory_store.clear()
        self._sqlite_store.clear()

    def count(self) -> int:
        """
        Get the number of variables.

        Returns:
            The count of variables.
        """
        return self._memory_store.count()

    def list_names(self) -> list:
        """
        Get all variable names.

        Returns:
            List of variable names.
        """
        return self._memory_store.list_names()

    def export_to_json(self, file_path: Union[str, Path], pretty: bool = True) -> None:
        """
        Export SQLite variables to JSON format.

        This allows interoperability with the JSON-based VariableSerializer.

        Args:
            file_path: Path to the output JSON file.
            pretty: If True, format with indentation.

        Raises:
            SerializationError: If export fails.
        """
        import json

        try:
            data = self._sqlite_store.export_to_dict()
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                if pretty:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                else:
                    json.dump(data, f, ensure_ascii=False, default=str)

        except Exception as e:
            raise SerializationError(f"Failed to export to JSON: {e}") from e

    def import_from_json(
        self, file_path: Union[str, Path], merge: bool = False
    ) -> int:
        """
        Import variables from JSON format into SQLite.

        This allows migration from JSON-based storage to SQLite.

        Args:
            file_path: Path to the input JSON file.
            merge: If True, merge with existing variables.

        Returns:
            Number of variables imported.

        Raises:
            SerializationError: If import fails.
        """
        import json

        try:
            path = Path(file_path)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            count = self._sqlite_store.import_from_dict(data, merge=merge)
            # Sync to memory
            self._sqlite_store.sync_to_global_store()
            return count

        except json.JSONDecodeError as e:
            raise SerializationError(f"Invalid JSON: {e}") from e
        except Exception as e:
            raise SerializationError(f"Failed to import from JSON: {e}") from e

    def vacuum(self) -> None:
        """
        Compact the SQLite database file.

        Call this periodically after many delete operations to
        reclaim disk space.
        """
        self._sqlite_store.vacuum()

    def close(self) -> None:
        """
        Close the SQLite connection.

        After calling close(), the serializer cannot be used anymore.
        """
        self._sqlite_store.close()

    def __enter__(self) -> "SqliteVariableSerializer":
        """Support using the serializer as a context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close when exiting the context."""
        self.close()


# Module-level convenience functions


def create_sqlite_store(
    db_path: Union[str, Path],
    store: Optional[GlobalVariableStore] = None,
) -> SqliteVariableSerializer:
    """
    Create a new SQLite variable serializer.

    This is a convenience function for creating a SqliteVariableSerializer.

    Args:
        db_path: Path to the SQLite database file.
        store: Optional GlobalVariableStore to sync with.

    Returns:
        A new SqliteVariableSerializer instance.

    Example:
        >>> from visualpython.serialization import create_sqlite_store
        >>> serializer = create_sqlite_store("my_variables.db")
        >>> serializer.save()
    """
    return SqliteVariableSerializer(db_path, store)


def save_variables_sqlite(
    db_path: Union[str, Path],
    store: Optional[GlobalVariableStore] = None,
) -> int:
    """
    Save global variables to a SQLite database.

    This is a convenience function that creates a SqliteVariableSerializer,
    saves variables, and closes the connection.

    Args:
        db_path: Path to the SQLite database file.
        store: Optional GlobalVariableStore to use.

    Returns:
        Number of variables saved.

    Raises:
        SerializationError: If the save fails.

    Example:
        >>> from visualpython.serialization import save_variables_sqlite
        >>> count = save_variables_sqlite("my_variables.db")
        >>> print(f"Saved {count} variables")
    """
    with SqliteVariableSerializer(db_path, store) as serializer:
        return serializer.save()


def load_variables_sqlite(
    db_path: Union[str, Path],
    merge: bool = False,
    store: Optional[GlobalVariableStore] = None,
) -> int:
    """
    Load global variables from a SQLite database.

    This is a convenience function that creates a SqliteVariableSerializer,
    loads variables, and closes the connection.

    Args:
        db_path: Path to the SQLite database file.
        merge: If True, merge with existing variables.
        store: Optional GlobalVariableStore to use.

    Returns:
        Number of variables loaded.

    Raises:
        SerializationError: If the load fails.

    Example:
        >>> from visualpython.serialization import load_variables_sqlite
        >>> count = load_variables_sqlite("my_variables.db")
        >>> print(f"Loaded {count} variables")
    """
    with SqliteVariableSerializer(db_path, store) as serializer:
        return serializer.load(merge=merge)


def migrate_json_to_sqlite(
    json_path: Union[str, Path],
    db_path: Union[str, Path],
) -> int:
    """
    Migrate variables from JSON format to SQLite.

    This utility function helps transition from JSON-based storage
    to the more efficient SQLite storage.

    Args:
        json_path: Path to the source JSON file.
        db_path: Path to the destination SQLite database.

    Returns:
        Number of variables migrated.

    Example:
        >>> from visualpython.serialization import migrate_json_to_sqlite
        >>> count = migrate_json_to_sqlite("old_vars.json", "new_vars.db")
    """
    with SqliteVariableSerializer(db_path) as serializer:
        return serializer.import_from_json(json_path)
