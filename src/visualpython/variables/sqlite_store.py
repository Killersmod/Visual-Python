"""
SQLite-based variable store for persistent state management across nodes.

This module defines the SqliteVariableStore class, which provides a SQLite-backed
storage system for global variables. Unlike the in-memory GlobalVariableStore,
this store persists variables to disk, making them available across sessions.

Thread Safety:
    All operations on the SqliteVariableStore are thread-safe through the use
    of a reentrant lock (RLock). SQLite connections are created per-thread to
    ensure safe concurrent access.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union

from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class SqliteVariableStore:
    """
    A SQLite-backed storage for persistent global variables.

    This class provides a centralized, persistent store for variables that need
    to be shared across multiple nodes during graph execution and persisted
    across sessions. It implements a similar interface to GlobalVariableStore
    for easy interchangeability.

    The store supports basic dictionary-like operations including get, set,
    delete, and iteration, along with additional utility methods for
    variable management. All data is persisted to a SQLite database file.

    Thread Safety:
        All methods in this class are thread-safe. A reentrant lock (RLock)
        is used to protect all operations. Each thread gets its own SQLite
        connection to ensure safe concurrent access.

    Performance:
        This store is optimized for large datasets through:
        - Efficient SQLite indexing on variable names
        - Batch operations for bulk updates
        - Connection pooling per thread
        - Optional WAL mode for better concurrent performance

    Attributes:
        _db_path: Path to the SQLite database file.
        _lock: Instance-level lock for thread-safe operations.
        _local: Thread-local storage for connections.
        _schema_version: Current schema version for migrations.

    Example:
        >>> store = SqliteVariableStore("variables.db")
        >>> store.set("counter", 0)
        >>> store.get("counter")
        0
        >>> store.increment("counter")
        1
        >>> store.close()
    """

    SCHEMA_VERSION = 1
    """Current schema version for database migrations."""

    # Type mapping for serialization
    SUPPORTED_TYPES = {
        "NoneType": type(None),
        "bool": bool,
        "int": int,
        "float": float,
        "str": str,
        "list": list,
        "tuple": tuple,
        "dict": dict,
        "set": set,
        "frozenset": frozenset,
        "bytes": bytes,
    }

    def __init__(
        self,
        db_path: Union[str, Path],
        wal_mode: bool = True,
        auto_vacuum: bool = True,
    ) -> None:
        """
        Initialize a new SqliteVariableStore instance.

        Args:
            db_path: Path to the SQLite database file. Use ':memory:' for
                     an in-memory database (useful for testing).
            wal_mode: If True, enable Write-Ahead Logging for better
                      concurrent performance. Defaults to True.
            auto_vacuum: If True, enable auto-vacuum to reclaim space.
                         Defaults to True.

        Note:
            The database schema will be created automatically if it doesn't exist.
            Schema migrations are handled automatically for version upgrades.
        """
        self._db_path: Path = Path(db_path) if db_path != ":memory:" else Path(":memory:")
        self._db_path_str: str = str(db_path)
        self._lock: threading.RLock = threading.RLock()
        self._local: threading.local = threading.local()
        self._wal_mode: bool = wal_mode
        self._auto_vacuum: bool = auto_vacuum
        self._closed: bool = False

        # Initialize the database schema
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a thread-local SQLite connection.

        Returns:
            A SQLite connection for the current thread.

        Raises:
            RuntimeError: If the store has been closed.
        """
        if self._closed:
            raise RuntimeError("SqliteVariableStore has been closed")

        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                self._db_path_str,
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row

            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")

            # Configure for performance
            if self._wal_mode and self._db_path_str != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -64000")  # 64MB cache

            self._local.connection = conn

        return self._local.connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        """
        Context manager for database transactions.

        Yields:
            A cursor for executing queries within a transaction.

        Note:
            The transaction is automatically committed on success
            or rolled back on exception.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def _initialize_database(self) -> None:
        """
        Initialize the database schema.

        Creates the necessary tables if they don't exist and handles
        schema migrations for version upgrades.
        """
        with self._lock:
            with self._transaction() as cursor:
                # Create metadata table for schema versioning
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)

                # Create variables table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS variables (
                        name TEXT PRIMARY KEY,
                        type_name TEXT NOT NULL,
                        value_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                # Create index for faster lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_variables_name
                    ON variables(name)
                """)

                # Check and update schema version
                cursor.execute(
                    "SELECT value FROM _metadata WHERE key = 'schema_version'"
                )
                row = cursor.fetchone()

                if row is None:
                    # Fresh database, set initial version
                    cursor.execute(
                        "INSERT INTO _metadata (key, value) VALUES (?, ?)",
                        ("schema_version", str(self.SCHEMA_VERSION)),
                    )
                else:
                    current_version = int(row["value"])
                    if current_version < self.SCHEMA_VERSION:
                        self._migrate_schema(cursor, current_version)

    def _migrate_schema(
        self, cursor: sqlite3.Cursor, from_version: int
    ) -> None:
        """
        Migrate the database schema to the current version.

        Args:
            cursor: Database cursor for executing migrations.
            from_version: The current schema version in the database.
        """
        # Add migration logic here as schema evolves
        # For now, just update the version number
        cursor.execute(
            "UPDATE _metadata SET value = ? WHERE key = 'schema_version'",
            (str(self.SCHEMA_VERSION),),
        )

    def _serialize_value(self, value: Any) -> Tuple[str, str]:
        """
        Serialize a Python value for storage.

        Args:
            value: The value to serialize.

        Returns:
            A tuple of (type_name, json_string).
        """
        type_name = type(value).__name__

        if value is None:
            return ("NoneType", "null")
        elif isinstance(value, bool):
            # bool must be checked before int (bool is subclass of int)
            return ("bool", json.dumps(value))
        elif isinstance(value, (int, float, str)):
            return (type_name, json.dumps(value))
        elif isinstance(value, (list, dict)):
            return (type_name, json.dumps(value, default=str))
        elif isinstance(value, tuple):
            return ("tuple", json.dumps(list(value), default=str))
        elif isinstance(value, set):
            return ("set", json.dumps(list(value), default=str))
        elif isinstance(value, frozenset):
            return ("frozenset", json.dumps(list(value), default=str))
        elif isinstance(value, bytes):
            return ("bytes", json.dumps(base64.b64encode(value).decode("ascii")))
        else:
            # For unknown types, store as string
            return ("_raw", json.dumps(str(value)))

    def _deserialize_value(self, type_name: str, value_json: str) -> Any:
        """
        Deserialize a stored value back to Python.

        Args:
            type_name: The type name stored with the value.
            value_json: The JSON-serialized value.

        Returns:
            The deserialized Python value.
        """
        value = json.loads(value_json)

        if type_name == "NoneType":
            return None
        elif type_name == "bool":
            return bool(value)
        elif type_name == "int":
            return int(value)
        elif type_name == "float":
            return float(value)
        elif type_name == "str":
            return str(value)
        elif type_name == "list":
            return value
        elif type_name == "tuple":
            return tuple(value)
        elif type_name == "dict":
            return value
        elif type_name == "set":
            return set(value)
        elif type_name == "frozenset":
            return frozenset(value)
        elif type_name == "bytes":
            return base64.b64decode(value.encode("ascii"))
        else:
            # Unknown type, return as-is
            return value

    def set(self, name: str, value: Any) -> None:
        """
        Set a variable value.

        This method is thread-safe and persistent.

        Args:
            name: The name of the variable.
            value: The value to store. Can be any JSON-serializable Python object.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("my_var", [1, 2, 3])
            >>> store.get("my_var")
            [1, 2, 3]
        """
        type_name, value_json = self._serialize_value(value)
        now = datetime.now().isoformat()

        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO variables (name, type_name, value_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        type_name = excluded.type_name,
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    (name, type_name, value_json, now, now),
                )

    def get(self, name: str, default: Any = None) -> Any:
        """
        Get a variable value.

        This method is thread-safe.

        Args:
            name: The name of the variable to retrieve.
            default: The value to return if the variable doesn't exist.
                Defaults to None.

        Returns:
            The variable value if it exists, otherwise the default value.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("exists", 42)
            >>> store.get("exists")
            42
            >>> store.get("not_exists", "default")
            'default'
        """
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT type_name, value_json FROM variables WHERE name = ?",
                    (name,),
                )
                row = cursor.fetchone()

                if row is None:
                    return default

                return self._deserialize_value(row["type_name"], row["value_json"])

    def delete(self, name: str) -> bool:
        """
        Delete a variable.

        This method is thread-safe.

        Args:
            name: The name of the variable to delete.

        Returns:
            True if the variable was deleted, False if it didn't exist.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("to_delete", 123)
            >>> store.delete("to_delete")
            True
            >>> store.delete("to_delete")
            False
        """
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute("DELETE FROM variables WHERE name = ?", (name,))
                return cursor.rowcount > 0

    def exists(self, name: str) -> bool:
        """
        Check if a variable exists.

        This method is thread-safe.

        Args:
            name: The name of the variable to check.

        Returns:
            True if the variable exists, False otherwise.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("test", "value")
            >>> store.exists("test")
            True
            >>> store.exists("nonexistent")
            False
        """
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT 1 FROM variables WHERE name = ?", (name,)
                )
                return cursor.fetchone() is not None

    def clear(self) -> None:
        """
        Clear all variables.

        This removes all variables from the store, resetting it to
        an empty state. This method is thread-safe.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("var1", 1)
            >>> store.set("var2", 2)
            >>> store.clear()
            >>> store.list_names()
            []
        """
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute("DELETE FROM variables")

    def list_names(self) -> List[str]:
        """
        Get a list of all variable names.

        This method is thread-safe.

        Returns:
            A list of all variable names currently stored.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("a", 1)
            >>> store.set("b", 2)
            >>> sorted(store.list_names())
            ['a', 'b']
        """
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute("SELECT name FROM variables ORDER BY name")
                return [row["name"] for row in cursor.fetchall()]

    def list_all(self) -> Dict[str, Any]:
        """
        Get all variables as a dictionary.

        This method is thread-safe.

        Returns:
            A dictionary of all variables with their values.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("x", 10)
            >>> store.set("y", 20)
            >>> store.list_all()
            {'x': 10, 'y': 20}
        """
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT name, type_name, value_json FROM variables ORDER BY name"
                )
                result = {}
                for row in cursor.fetchall():
                    result[row["name"]] = self._deserialize_value(
                        row["type_name"], row["value_json"]
                    )
                return result

    def count(self) -> int:
        """
        Get the number of stored variables.

        This method is thread-safe.

        Returns:
            The count of variables in the store.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.clear()
            >>> store.count()
            0
            >>> store.set("var", "value")
            >>> store.count()
            1
        """
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM variables")
                row = cursor.fetchone()
                return row["count"] if row else 0

    def update(self, variables: Dict[str, Any]) -> None:
        """
        Update multiple variables at once.

        This method is thread-safe and atomic - all variables are
        updated in a single transaction.

        Args:
            variables: A dictionary of variable names and values to set.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.update({"a": 1, "b": 2, "c": 3})
            >>> store.get("b")
            2
        """
        now = datetime.now().isoformat()

        with self._lock:
            with self._transaction() as cursor:
                for name, value in variables.items():
                    type_name, value_json = self._serialize_value(value)
                    cursor.execute(
                        """
                        INSERT INTO variables (name, type_name, value_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(name) DO UPDATE SET
                            type_name = excluded.type_name,
                            value_json = excluded.value_json,
                            updated_at = excluded.updated_at
                        """,
                        (name, type_name, value_json, now, now),
                    )

    def items(self) -> List[Tuple[str, Any]]:
        """
        Get all variable name-value pairs.

        This method is thread-safe.

        Returns:
            A list of tuples of (name, value) for each variable.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("key", "value")
            >>> for name, val in store.items():
            ...     print(f"{name}: {val}")
            key: value
        """
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT name, type_name, value_json FROM variables ORDER BY name"
                )
                result = []
                for row in cursor.fetchall():
                    value = self._deserialize_value(
                        row["type_name"], row["value_json"]
                    )
                    result.append((row["name"], value))
                return result

    def __contains__(self, name: str) -> bool:
        """
        Check if a variable exists using the 'in' operator.

        This method is thread-safe.

        Args:
            name: The name of the variable to check.

        Returns:
            True if the variable exists, False otherwise.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("test", 1)
            >>> "test" in store
            True
        """
        return self.exists(name)

    def __len__(self) -> int:
        """
        Get the number of variables using len().

        This method is thread-safe.

        Returns:
            The count of variables in the store.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.clear()
            >>> len(store)
            0
        """
        return self.count()

    def __repr__(self) -> str:
        """Get a detailed string representation of the store."""
        return f"SqliteVariableStore(db_path='{self._db_path}', variables={self.count()})"

    def __str__(self) -> str:
        """Get a simple string representation of the store."""
        return f"SqliteVariableStore with {self.count()} variable(s)"

    # Atomic operations for thread-safe read-modify-write patterns

    def get_and_set(self, name: str, value: Any) -> Any:
        """
        Atomically get the current value and set a new value.

        This is useful for operations where you need to know the previous
        value while setting a new one, in a thread-safe manner.

        Args:
            name: The name of the variable.
            value: The new value to set.

        Returns:
            The previous value, or None if the variable didn't exist.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("counter", 5)
            >>> old_value = store.get_and_set("counter", 10)
            >>> print(old_value)  # 5
            >>> print(store.get("counter"))  # 10
        """
        with self._lock:
            old_value = self.get(name)
            self.set(name, value)
            return old_value

    def set_if_absent(self, name: str, value: Any) -> Any:
        """
        Set a variable only if it doesn't already exist.

        This is useful for initializing variables in a thread-safe manner
        without overwriting existing values.

        Args:
            name: The name of the variable.
            value: The value to set if the variable doesn't exist.

        Returns:
            The current value if it exists, otherwise the new value.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set_if_absent("counter", 0)  # Returns 0, sets counter
            >>> store.set_if_absent("counter", 100)  # Returns 0, doesn't change
        """
        with self._lock:
            current = self.get(name)
            if current is None and not self.exists(name):
                self.set(name, value)
                return value
            return current

    def increment(self, name: str, delta: int = 1) -> int:
        """
        Atomically increment a numeric variable.

        This method safely increments a variable by the given delta,
        initializing it to 0 if it doesn't exist.

        Args:
            name: The name of the variable to increment.
            delta: The amount to increment by (default: 1).

        Returns:
            The new value after incrementing.

        Raises:
            TypeError: If the current value is not numeric.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("counter", 5)
            >>> store.increment("counter")
            6
            >>> store.increment("counter", 10)
            16
        """
        with self._lock:
            current = self.get(name, 0)
            if not isinstance(current, (int, float)):
                raise TypeError(
                    f"Cannot increment non-numeric value of type {type(current).__name__}"
                )
            new_value = current + delta
            self.set(name, new_value)
            return new_value

    def decrement(self, name: str, delta: int = 1) -> int:
        """
        Atomically decrement a numeric variable.

        This method safely decrements a variable by the given delta,
        initializing it to 0 if it doesn't exist.

        Args:
            name: The name of the variable to decrement.
            delta: The amount to decrement by (default: 1).

        Returns:
            The new value after decrementing.

        Raises:
            TypeError: If the current value is not numeric.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("counter", 10)
            >>> store.decrement("counter")
            9
            >>> store.decrement("counter", 5)
            4
        """
        return self.increment(name, -delta)

    def update_with(
        self, name: str, func: Callable[[Any], Any], default: Any = None
    ) -> Any:
        """
        Atomically update a variable using a function.

        This method applies a function to the current value and stores
        the result, all within a single lock acquisition. This is useful
        for complex atomic updates.

        Args:
            name: The name of the variable.
            func: A function that takes the current value and returns the new value.
            default: The default value to use if the variable doesn't exist.

        Returns:
            The new value after applying the function.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("items", [1, 2, 3])
            >>> store.update_with("items", lambda x: x + [4])
            [1, 2, 3, 4]
        """
        with self._lock:
            current = self.get(name, default)
            new_value = func(current)
            self.set(name, new_value)
            return new_value

    def append_to_list(self, name: str, value: Any) -> List[Any]:
        """
        Atomically append a value to a list variable.

        If the variable doesn't exist, it creates a new list.

        Args:
            name: The name of the list variable.
            value: The value to append.

        Returns:
            The list after appending.

        Raises:
            TypeError: If the current value is not a list.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.append_to_list("items", "first")
            ['first']
            >>> store.append_to_list("items", "second")
            ['first', 'second']
        """
        with self._lock:
            current = self.get(name)
            if current is None:
                current = []
            elif not isinstance(current, list):
                raise TypeError(
                    f"Cannot append to non-list value of type {type(current).__name__}"
                )
            current.append(value)
            self.set(name, current)
            return current.copy()

    def get_lock(self) -> threading.RLock:
        """
        Get the internal lock for advanced synchronization scenarios.

        This allows users to perform multiple operations atomically by
        acquiring the lock manually. Use with caution and always release
        the lock properly.

        Returns:
            The internal RLock instance.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> with store.get_lock():
            ...     # Multiple operations are atomic
            ...     x = store.get("x")
            ...     y = store.get("y")
            ...     store.set("sum", x + y)
        """
        return self._lock

    # Additional methods for persistence management

    def get_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata about a variable including timestamps.

        Args:
            name: The name of the variable.

        Returns:
            Dictionary with 'created_at' and 'updated_at' timestamps,
            or None if the variable doesn't exist.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("example", "value")
            >>> meta = store.get_metadata("example")
            >>> print(meta['created_at'])
        """
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT created_at, updated_at FROM variables WHERE name = ?",
                    (name,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return {
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }

    def vacuum(self) -> None:
        """
        Compact the database file to reclaim unused space.

        This should be called periodically after many delete operations
        to reduce the database file size.
        """
        with self._lock:
            conn = self._get_connection()
            conn.execute("VACUUM")

    def close(self) -> None:
        """
        Close the database connection.

        After calling close(), the store cannot be used anymore.
        This method is thread-safe.
        """
        with self._lock:
            self._closed = True
            if hasattr(self._local, "connection") and self._local.connection:
                self._local.connection.close()
                self._local.connection = None

    def __enter__(self) -> "SqliteVariableStore":
        """Support using the store as a context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close the store when exiting the context."""
        self.close()

    # Import/Export methods for interoperability

    def export_to_dict(self) -> Dict[str, Any]:
        """
        Export all variables to a dictionary format compatible with VariableSerializer.

        Returns:
            Dictionary containing all variables with metadata.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> store.set("x", 10)
            >>> data = store.export_to_dict()
        """
        from visualpython.serialization.variable_serializer import VariableSerializer

        # Create a temporary serializer to handle type serialization
        temp_serializer = VariableSerializer.__new__(VariableSerializer)
        temp_serializer._store = None

        variables = {}
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT name, type_name, value_json FROM variables ORDER BY name"
                )
                for row in cursor.fetchall():
                    value = self._deserialize_value(
                        row["type_name"], row["value_json"]
                    )
                    variables[row["name"]] = temp_serializer._serialize_value(value)

        return {
            "format_version": "1.0.0",
            "file_type": "visualpython_variables",
            "saved_at": datetime.now().isoformat(),
            "variable_count": len(variables),
            "variables": variables,
        }

    def import_from_dict(
        self, data: Dict[str, Any], merge: bool = False
    ) -> int:
        """
        Import variables from a dictionary format (compatible with VariableSerializer).

        Args:
            data: Dictionary containing serialized variables.
            merge: If True, merge with existing variables.
                   If False, clear existing variables first.

        Returns:
            Number of variables imported.

        Example:
            >>> store = SqliteVariableStore("test.db")
            >>> count = store.import_from_dict(data)
        """
        from visualpython.serialization.variable_serializer import VariableSerializer

        # Validate format
        file_type = data.get("file_type")
        if file_type != "visualpython_variables":
            raise ValueError(
                f"Invalid file type: expected 'visualpython_variables', got '{file_type}'"
            )

        variables_data = data.get("variables")
        if variables_data is None:
            raise ValueError("Missing 'variables' field in data")

        if not isinstance(variables_data, dict):
            raise ValueError("'variables' field must be a dictionary")

        # Create a temporary serializer to handle type deserialization
        temp_serializer = VariableSerializer.__new__(VariableSerializer)
        temp_serializer._store = None

        with self._lock:
            if not merge:
                self.clear()

            count = 0
            for name, value_data in variables_data.items():
                try:
                    value = temp_serializer._deserialize_value(value_data)
                    self.set(name, value)
                    count += 1
                except Exception:
                    # Skip invalid entries
                    logger.warning("SQLite store error", exc_info=True)
                    pass

            return count

    def sync_from_global_store(self) -> int:
        """
        Import all variables from the GlobalVariableStore.

        This is useful for persisting in-memory variables to SQLite.

        Returns:
            Number of variables synchronized.
        """
        from visualpython.variables.global_store import GlobalVariableStore

        store = GlobalVariableStore.get_instance()
        variables = store.list_all()

        with self._lock:
            self.clear()
            self.update(variables)
            return len(variables)

    def sync_to_global_store(self) -> int:
        """
        Export all variables to the GlobalVariableStore.

        This is useful for loading persisted variables into memory.

        Returns:
            Number of variables synchronized.
        """
        from visualpython.variables.global_store import GlobalVariableStore

        store = GlobalVariableStore.get_instance()
        variables = self.list_all()

        store.clear()
        store.update(variables)
        return len(variables)
