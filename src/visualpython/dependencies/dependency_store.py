"""
SQLite-based storage for dependency tree persistence.

Stores named dependency trees with their hashes for tracking
and comparing dependency states across sessions.

Thread Safety:
    All operations are thread-safe through the use of a reentrant lock (RLock).
    SQLite connections are created per-thread to ensure safe concurrent access.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class DependencyStore:
    """
    SQLite-backed storage for named dependency trees.

    Follows the same thread-safe pattern as SqliteVariableStore:
    RLock + thread-local connections + _transaction() context manager.
    """

    SCHEMA_VERSION = 1

    def __init__(
        self,
        db_path: Union[str, Path],
        wal_mode: bool = True,
    ) -> None:
        self._db_path: Path = Path(db_path) if db_path != ":memory:" else Path(":memory:")
        self._db_path_str: str = str(db_path)
        self._lock: threading.RLock = threading.RLock()
        self._local: threading.local = threading.local()
        self._wal_mode: bool = wal_mode
        self._closed: bool = False
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local SQLite connection."""
        if self._closed:
            raise RuntimeError("DependencyStore has been closed")

        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                self._db_path_str,
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row

            conn.execute("PRAGMA foreign_keys = ON")

            if self._wal_mode and self._db_path_str != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -64000")

            self._local.connection = conn

        return self._local.connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        """Context manager for database transactions."""
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
        """Create tables if they don't exist."""
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dependency_trees (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        tree_hash TEXT NOT NULL,
                        tree_json TEXT NOT NULL,
                        graph_file_path TEXT,
                        graph_name TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dependency_trees_hash
                    ON dependency_trees(tree_hash)
                """)

                cursor.execute(
                    "INSERT OR IGNORE INTO _metadata (key, value) VALUES (?, ?)",
                    ("schema_version", str(self.SCHEMA_VERSION)),
                )

    def save_tree(
        self,
        name: str,
        tree_hash: str,
        tree_json: str,
        graph_file_path: Optional[str] = None,
        graph_name: Optional[str] = None,
    ) -> int:
        """
        Save or update a named dependency tree. Returns the row ID.

        If a tree with the same name exists, it is updated.
        """
        now = datetime.now().isoformat()
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT id, created_at FROM dependency_trees WHERE name = ?",
                    (name,),
                )
                row = cursor.fetchone()

                if row:
                    cursor.execute(
                        """
                        UPDATE dependency_trees
                        SET tree_hash = ?, tree_json = ?, graph_file_path = ?,
                            graph_name = ?, updated_at = ?
                        WHERE name = ?
                        """,
                        (tree_hash, tree_json, graph_file_path, graph_name, now, name),
                    )
                    return row["id"]
                else:
                    cursor.execute(
                        """
                        INSERT INTO dependency_trees
                            (name, tree_hash, tree_json, graph_file_path, graph_name,
                             created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (name, tree_hash, tree_json, graph_file_path, graph_name, now, now),
                    )
                    return cursor.lastrowid

    def get_tree(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a dependency tree by name."""
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT * FROM dependency_trees WHERE name = ?",
                    (name,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None

    def get_tree_by_hash(self, tree_hash: str) -> Optional[Dict[str, Any]]:
        """Get the first dependency tree matching a hash."""
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT * FROM dependency_trees WHERE tree_hash = ?",
                    (tree_hash,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None

    def list_trees(self) -> List[Dict[str, Any]]:
        """List all saved dependency trees, ordered by most recently updated."""
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "SELECT * FROM dependency_trees ORDER BY updated_at DESC"
                )
                return [dict(row) for row in cursor.fetchall()]

    def delete_tree(self, name: str) -> bool:
        """Delete a named dependency tree. Returns True if a row was deleted."""
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    "DELETE FROM dependency_trees WHERE name = ?",
                    (name,),
                )
                return cursor.rowcount > 0

    def rename_tree(self, old_name: str, new_name: str) -> bool:
        """Rename a dependency tree. Returns True if successful."""
        now = datetime.now().isoformat()
        with self._lock:
            with self._transaction() as cursor:
                cursor.execute(
                    """
                    UPDATE dependency_trees
                    SET name = ?, updated_at = ?
                    WHERE name = ?
                    """,
                    (new_name, now, old_name),
                )
                return cursor.rowcount > 0

    def close(self) -> None:
        """Close the store and any open connections."""
        with self._lock:
            self._closed = True
            if hasattr(self._local, "connection") and self._local.connection:
                try:
                    self._local.connection.close()
                except Exception:
                    pass
                self._local.connection = None
