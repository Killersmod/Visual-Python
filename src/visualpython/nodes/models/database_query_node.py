"""
Database query node model for executing SQL queries against databases.

This module defines the DatabaseQueryNode class, which executes SQL queries
against databases using configurable connection strings. Supports SQLite,
PostgreSQL, MySQL, and other databases via connection string configuration.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class DatabaseType(Enum):
    """Supported database types."""

    SQLITE = "sqlite"
    """SQLite database (file-based)."""

    POSTGRESQL = "postgresql"
    """PostgreSQL database."""

    MYSQL = "mysql"
    """MySQL/MariaDB database."""

    MSSQL = "mssql"
    """Microsoft SQL Server."""

    ORACLE = "oracle"
    """Oracle database."""

    CUSTOM = "custom"
    """Custom connection string."""


class DatabaseQueryNode(BaseNode):
    """
    A node that executes SQL queries against databases.

    The DatabaseQueryNode connects to databases using connection strings and
    executes SQL queries, returning results as a list of dictionaries. It
    supports parameterized queries to prevent SQL injection.

    The configuration can be:
    - Set directly on the node (via properties)
    - Provided dynamically through input ports

    Attributes:
        connection_string: The database connection string.
        database_type: The type of database (sqlite, postgresql, etc.).
        query: The SQL query to execute.
        parameters: Dictionary of query parameters for parameterized queries.
        timeout: Query timeout in seconds.
        fetch_size: Maximum number of rows to fetch (0 = all rows).

    Example:
        >>> node = DatabaseQueryNode(
        ...     database_type="sqlite",
        ...     connection_string="data.db",
        ...     query="SELECT * FROM users WHERE active = :active",
        ...     parameters={"active": True}
        ... )
        >>> result = node.execute({})
        >>> result['success']
        True
        >>> result['rows']
        [{'id': 1, 'name': 'Alice', 'active': True}, ...]
    """

    # Class-level metadata
    node_type: str = "database_query"
    """Unique identifier for database query nodes."""

    node_category: str = "Database"
    """Category for organizing in the UI."""

    node_color: str = "#FF9800"
    """Orange color for database operations."""

    # Constants
    DEFAULT_TIMEOUT: float = 30.0
    """Default query timeout in seconds."""

    DEFAULT_FETCH_SIZE: int = 0
    """Default fetch size (0 = unlimited)."""

    MAX_FETCH_SIZE: int = 100000
    """Maximum fetch size to prevent memory issues."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        connection_string: str = "",
        database_type: str = "sqlite",
        query: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        timeout: float = DEFAULT_TIMEOUT,
        fetch_size: int = DEFAULT_FETCH_SIZE,
    ) -> None:
        """
        Initialize a new DatabaseQueryNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Database Query'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            connection_string: The database connection string or file path.
            database_type: The type of database (sqlite, postgresql, mysql, etc.).
            query: The SQL query to execute.
            parameters: Dictionary of query parameters for parameterized queries.
            timeout: Query timeout in seconds.
            fetch_size: Maximum number of rows to fetch (0 = all rows).
        """
        self._connection_string: str = connection_string
        self._database_type: str = database_type.lower()
        self._query: str = query
        self._parameters: Dict[str, Any] = parameters or {}
        self._timeout: float = timeout
        self._fetch_size: int = min(fetch_size, self.MAX_FETCH_SIZE) if fetch_size > 0 else 0
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the database query node.

        The database query node has:
        - An execution flow input port (for controlling execution order)
        - A connection_string input port (optional, for dynamic connection)
        - A query input port (optional, for dynamic queries)
        - A parameters input port (optional, for dynamic query parameters)
        - A timeout input port (optional, for dynamic timeout)
        - An execution flow output port (for chaining execution)
        - A rows output port with the query results as list of dicts
        - A row_count output port with the number of rows returned
        - A columns output port with column names
        - A success output port indicating whether the query succeeded
        - An error_message output port with error details if failed
        - A last_insert_id output port for INSERT statements
        - A rows_affected output port for UPDATE/DELETE statements
        """
        # Execution flow ports
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # Connection string input (optional - allows dynamic connection)
        self.add_input_port(InputPort(
            name="connection_string",
            port_type=PortType.STRING,
            description="Database connection string (overrides configured connection)",
            required=False,
            display_hint=self._connection_string,
        ))

        # Query input (optional - allows dynamic queries)
        self.add_input_port(InputPort(
            name="query",
            port_type=PortType.STRING,
            description="SQL query to execute (overrides configured query)",
            required=False,
            display_hint=self._query,
        ))

        # Parameters input (optional - allows dynamic parameters)
        self.add_input_port(InputPort(
            name="parameters",
            port_type=PortType.DICT,
            description="Query parameters dictionary for parameterized queries",
            required=False,
        ))

        # Timeout input (optional - allows dynamic timeout)
        self.add_input_port(InputPort(
            name="timeout",
            port_type=PortType.FLOAT,
            description="Query timeout in seconds (overrides configured timeout)",
            required=False,
            display_hint=self._timeout,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="rows",
            port_type=PortType.LIST,
            description="Query results as a list of dictionaries",
        ))
        self.add_output_port(OutputPort(
            name="row_count",
            port_type=PortType.INTEGER,
            description="Number of rows returned or affected",
        ))
        self.add_output_port(OutputPort(
            name="columns",
            port_type=PortType.LIST,
            description="List of column names from the result",
        ))
        self.add_output_port(OutputPort(
            name="success",
            port_type=PortType.BOOLEAN,
            description="Whether the query executed successfully",
        ))
        self.add_output_port(OutputPort(
            name="error_message",
            port_type=PortType.STRING,
            description="Error message if the query failed",
        ))
        self.add_output_port(OutputPort(
            name="last_insert_id",
            port_type=PortType.INTEGER,
            description="Last inserted row ID (for INSERT statements)",
        ))
        self.add_output_port(OutputPort(
            name="rows_affected",
            port_type=PortType.INTEGER,
            description="Number of rows affected (for UPDATE/DELETE statements)",
        ))

    @property
    def connection_string(self) -> str:
        """Get the configured connection string."""
        return self._connection_string

    @connection_string.setter
    def connection_string(self, value: str) -> None:
        """
        Set the database connection string.

        Args:
            value: The connection string or file path.
        """
        self._connection_string = value

    @property
    def database_type(self) -> str:
        """Get the configured database type."""
        return self._database_type

    @database_type.setter
    def database_type(self, value: str) -> None:
        """
        Set the database type.

        Args:
            value: The database type (sqlite, postgresql, mysql, etc.).
        """
        self._database_type = value.lower()

    @property
    def query(self) -> str:
        """Get the configured SQL query."""
        return self._query

    @query.setter
    def query(self, value: str) -> None:
        """
        Set the SQL query.

        Args:
            value: The SQL query string.
        """
        self._query = value

    @property
    def parameters(self) -> Dict[str, Any]:
        """Get the configured query parameters."""
        return self._parameters.copy()

    @parameters.setter
    def parameters(self, value: Dict[str, Any]) -> None:
        """
        Set the query parameters.

        Args:
            value: Dictionary of query parameters.
        """
        self._parameters = value or {}

    @property
    def timeout(self) -> float:
        """Get the configured timeout."""
        return self._timeout

    @timeout.setter
    def timeout(self, value: float) -> None:
        """
        Set the query timeout.

        Args:
            value: Timeout in seconds.
        """
        self._timeout = value

    @property
    def fetch_size(self) -> int:
        """Get the configured fetch size."""
        return self._fetch_size

    @fetch_size.setter
    def fetch_size(self, value: int) -> None:
        """
        Set the fetch size.

        Args:
            value: Maximum number of rows to fetch (0 = unlimited).
        """
        self._fetch_size = min(value, self.MAX_FETCH_SIZE) if value > 0 else 0

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # Check if connection string is provided or will be via input
        if not self._connection_string:
            conn_port = self.get_input_port("connection_string")
            if conn_port and not conn_port.is_connected():
                errors.append(
                    "Connection string must be configured or provided via input port"
                )

        # Check if query is provided or will be via input
        if not self._query:
            query_port = self.get_input_port("query")
            if query_port and not query_port.is_connected():
                errors.append(
                    "SQL query must be configured or provided via input port"
                )

        # Validate database type
        valid_types = {t.value for t in DatabaseType}
        if self._database_type and self._database_type not in valid_types:
            errors.append(
                f"Invalid database type '{self._database_type}'. "
                f"Must be one of: {', '.join(sorted(valid_types))}"
            )

        # Validate timeout
        if self._timeout <= 0:
            errors.append("Timeout must be greater than 0")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the SQL query.

        The query configuration is determined by:
        1. Input port values (if provided)
        2. Configured properties (as fallback)

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'rows': List of result rows as dictionaries
                - 'row_count': Number of rows returned or affected
                - 'columns': List of column names
                - 'success': Boolean indicating if the query succeeded
                - 'error_message': Error message if failed (empty string if success)
                - 'last_insert_id': Last inserted row ID for INSERT statements
                - 'rows_affected': Number of rows affected for UPDATE/DELETE

        Raises:
            ValueError: If no connection string or query is specified.
        """
        import sqlite3

        # Determine the connection string to use
        connection_string = inputs.get("connection_string", self._connection_string)
        if not connection_string:
            raise ValueError("No connection string specified")

        # Determine the query to use
        query = inputs.get("query", self._query)
        if not query:
            raise ValueError("No SQL query specified")

        # Determine parameters (merge configured with input)
        parameters = self._parameters.copy()
        input_parameters = inputs.get("parameters")
        if input_parameters and isinstance(input_parameters, dict):
            parameters.update(input_parameters)

        # Determine timeout
        timeout = inputs.get("timeout", self._timeout)
        if not timeout or timeout <= 0:
            timeout = self.DEFAULT_TIMEOUT

        try:
            # Currently we only support SQLite natively
            # Other database types would require additional drivers
            if self._database_type == "sqlite":
                return self._execute_sqlite(connection_string, query, parameters, timeout)
            else:
                # For non-SQLite databases, attempt to use generic DB-API approach
                # This requires the appropriate driver to be installed
                return self._execute_generic(
                    connection_string, query, parameters, timeout
                )

        except sqlite3.Error as e:
            logger.error("Database query failed: %s", e, exc_info=True)
            return {
                "rows": [],
                "row_count": 0,
                "columns": [],
                "success": False,
                "error_message": f"SQLite Error: {str(e)}",
                "last_insert_id": 0,
                "rows_affected": 0,
            }

        except Exception as e:
            logger.error("Database query failed: %s", e, exc_info=True)
            return {
                "rows": [],
                "row_count": 0,
                "columns": [],
                "success": False,
                "error_message": str(e),
                "last_insert_id": 0,
                "rows_affected": 0,
            }

    def _execute_sqlite(
        self,
        connection_string: str,
        query: str,
        parameters: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """
        Execute a query against a SQLite database.

        Args:
            connection_string: Path to the SQLite database file.
            query: The SQL query to execute.
            parameters: Query parameters.
            timeout: Query timeout in seconds.

        Returns:
            Dictionary with query results.
        """
        import sqlite3

        # Connect to SQLite database
        conn = sqlite3.connect(connection_string, timeout=timeout)
        conn.row_factory = sqlite3.Row  # Enable dict-like access to rows

        try:
            cursor = conn.cursor()

            # Execute the query with parameters
            if parameters:
                cursor.execute(query, parameters)
            else:
                cursor.execute(query)

            # Determine if this is a SELECT or data modification query
            query_upper = query.strip().upper()
            is_select = query_upper.startswith("SELECT") or query_upper.startswith("WITH")

            if is_select:
                # Fetch results
                if self._fetch_size > 0:
                    raw_rows = cursor.fetchmany(self._fetch_size)
                else:
                    raw_rows = cursor.fetchall()

                # Get column names
                columns = [description[0] for description in cursor.description] if cursor.description else []

                # Convert rows to list of dicts
                rows = [dict(row) for row in raw_rows]

                return {
                    "rows": rows,
                    "row_count": len(rows),
                    "columns": columns,
                    "success": True,
                    "error_message": "",
                    "last_insert_id": 0,
                    "rows_affected": 0,
                }
            else:
                # Data modification query (INSERT, UPDATE, DELETE, etc.)
                conn.commit()

                return {
                    "rows": [],
                    "row_count": cursor.rowcount,
                    "columns": [],
                    "success": True,
                    "error_message": "",
                    "last_insert_id": cursor.lastrowid or 0,
                    "rows_affected": cursor.rowcount,
                }

        finally:
            conn.close()

    def _execute_generic(
        self,
        connection_string: str,
        query: str,
        parameters: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """
        Execute a query using a generic DB-API approach.

        This method attempts to connect using the connection string format
        and execute the query. Requires appropriate database drivers.

        Args:
            connection_string: Database connection string.
            query: The SQL query to execute.
            parameters: Query parameters.
            timeout: Query timeout in seconds.

        Returns:
            Dictionary with query results.
        """
        # For non-SQLite databases, we need external drivers
        # This is a placeholder that returns an informative error
        return {
            "rows": [],
            "row_count": 0,
            "columns": [],
            "success": False,
            "error_message": (
                f"Database type '{self._database_type}' requires external driver. "
                f"Currently only SQLite is supported natively. "
                f"For other databases, install the appropriate driver "
                f"(psycopg2 for PostgreSQL, mysql-connector for MySQL, etc.)"
            ),
            "last_insert_id": 0,
            "rows_affected": 0,
        }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get database query node specific properties for serialization.

        Returns:
            Dictionary containing the connection string, query, parameters, etc.
        """
        return {
            "connection_string": self._connection_string,
            "database_type": self._database_type,
            "query": self._query,
            "parameters": self._parameters,
            "timeout": self._timeout,
            "fetch_size": self._fetch_size,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load database query node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._connection_string = properties.get("connection_string", "")
        self._database_type = properties.get("database_type", "sqlite")
        self._query = properties.get("query", "")
        self._parameters = properties.get("parameters", {})
        self._timeout = properties.get("timeout", self.DEFAULT_TIMEOUT)
        self._fetch_size = properties.get("fetch_size", self.DEFAULT_FETCH_SIZE)

    def __repr__(self) -> str:
        """Get a detailed string representation of the database query node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"database_type='{self._database_type}', "
            f"query='{self._query[:30]}...', "
            f"state={self._execution_state.name})"
        )
