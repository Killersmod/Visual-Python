"""
Case context for per-execution shared state management.

This module defines the Case class, which provides a per-execution context
for sharing variables across all nodes during a single graph execution.
Unlike GlobalVariableStore (which is a singleton for persistent state),
Case is instantiated fresh for each execution run.

The Case class supports both method-based access (case.get("x"), case.set("x", 1))
and attribute-based access (case.x = 1, case.x) for convenient use in custom code.

Thread Safety:
    All operations on the Case class are thread-safe through the use of a
    reentrant lock (RLock). This allows safe concurrent access from multiple
    threads during parallel execution scenarios. For atomic read-modify-write
    operations, use the provided atomic methods like `increment()`, `decrement()`,
    or `update_with()`.

Example:
    >>> case = Case()
    >>> case.set("counter", 0)
    >>> case.get("counter")
    0
    >>> case.counter = 10  # Attribute access
    >>> case.counter
    10
    >>> # Atomic increment
    >>> case.increment("counter")
    11
"""

from __future__ import annotations

import keyword
import threading
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Type, Union


class InvalidVariableNameError(ValueError):
    """
    Exception raised when an invalid variable name is used.

    This exception is raised when a user attempts to set a case variable
    with a name that is not a valid Python identifier (e.g., contains spaces,
    starts with a number, or is a Python keyword).

    Attributes:
        name: The invalid variable name that was attempted.
        reason: A description of why the name is invalid.

    Example:
        >>> case = Case()
        >>> case.set("invalid name", 123)  # Raises InvalidVariableNameError
        >>> case.set("123start", 456)  # Raises InvalidVariableNameError
        >>> case.set("for", 789)  # Raises InvalidVariableNameError (Python keyword)
    """

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason
        super().__init__(f"Invalid variable name '{name}': {reason}")


def validate_variable_name(name: str) -> None:
    """
    Validate that a variable name is a valid Python identifier.

    A valid variable name must:
    1. Not be empty
    2. Not contain spaces
    3. Be a valid Python identifier (starts with letter or underscore,
       contains only letters, numbers, and underscores)
    4. Not be a Python keyword (like 'if', 'for', 'class', etc.)

    Args:
        name: The variable name to validate.

    Raises:
        InvalidVariableNameError: If the name is not a valid Python identifier.

    Example:
        >>> validate_variable_name("valid_name")  # OK
        >>> validate_variable_name("_private")  # OK
        >>> validate_variable_name("name123")  # OK
        >>> validate_variable_name("invalid name")  # Raises InvalidVariableNameError
        >>> validate_variable_name("123start")  # Raises InvalidVariableNameError
        >>> validate_variable_name("for")  # Raises InvalidVariableNameError
    """
    if not name:
        raise InvalidVariableNameError(name, "Variable name cannot be empty")

    if " " in name:
        raise InvalidVariableNameError(
            name, "Variable name cannot contain spaces"
        )

    if not name.isidentifier():
        raise InvalidVariableNameError(
            name,
            "Variable name must be a valid Python identifier "
            "(start with letter or underscore, contain only letters, numbers, and underscores)"
        )

    if keyword.iskeyword(name):
        raise InvalidVariableNameError(
            name, f"Variable name cannot be a Python keyword ('{name}' is reserved)"
        )


class TypeValidationError(TypeError):
    """
    Exception raised when a type validation fails.

    This exception is raised when type validation is enabled and a user attempts
    to set a case variable with a value that doesn't match the expected type
    for that variable.

    Attributes:
        name: The variable name.
        expected_type: The expected type(s) for the variable.
        actual_type: The actual type of the value that was attempted.
        value: The value that failed type validation.

    Example:
        >>> case = Case(type_validation=True)
        >>> case.set_type("counter", int)
        >>> case.set("counter", "not an int")  # Raises TypeValidationError
    """

    def __init__(
        self,
        name: str,
        expected_type: Union[Type, Tuple[Type, ...]],
        actual_type: Type,
        value: Any
    ) -> None:
        self.name = name
        self.expected_type = expected_type
        self.actual_type = actual_type
        self.value = value

        # Format expected type(s) for error message
        if isinstance(expected_type, tuple):
            type_names = ", ".join(t.__name__ for t in expected_type)
            expected_str = f"one of ({type_names})"
        else:
            expected_str = expected_type.__name__

        super().__init__(
            f"Type validation failed for variable '{name}': "
            f"expected {expected_str}, got {actual_type.__name__}"
        )


class Case:
    """
    Per-execution context for sharing variables across nodes.

    The Case class provides a dictionary-like storage for variables that need
    to be shared across all nodes during a single graph execution. It supports
    both method-based access (get/set/delete) and attribute-based access for
    convenient use in custom Python code within CodeNodes.

    Unlike GlobalVariableStore, Case is not a singleton - a new instance is
    created for each execution run and is automatically cleared when the
    execution context is reset.

    Thread Safety:
        All methods in this class are thread-safe. A reentrant lock (RLock)
        is used to protect all operations, allowing safe concurrent access
        from multiple threads. The RLock allows the same thread to acquire
        the lock multiple times (reentrant), which is useful for nested calls.

        For atomic read-modify-write operations, use the provided atomic
        methods like `increment()`, `decrement()`, `get_and_set()`, or
        `update_with()`.

    Type Validation:
        Optional type validation can be enabled to ensure variables are set
        with the correct types. Type validation is disabled by default.
        When enabled, you can specify expected types for variables using
        `set_type()`, and the Case will validate values when setting variables.

        Example:
            >>> case = Case(type_validation=True)
            >>> case.set_type("counter", int)
            >>> case.set("counter", 10)  # OK
            >>> case.set("counter", "not an int")  # Raises TypeValidationError

    Attributes:
        _variables: Internal dictionary storing variable name-value pairs.
        _lock: Instance-level lock for thread-safe operations.
        _type_validation: Whether type validation is enabled.
        _type_constraints: Dictionary of type constraints for variables.

    Example:
        >>> case = Case()
        >>> # Method-based access
        >>> case.set("x", 10)
        >>> case.get("x")
        10
        >>> # Attribute-based access
        >>> case.y = 20
        >>> case.y
        20
        >>> # Atomic increment
        >>> case.increment("y")
        21
        >>> # List all variables
        >>> case.list_names()
        ['x', 'y']
        >>> # Type validation example
        >>> case.enable_type_validation()
        >>> case.set_type("name", str)
        >>> case.name = "Alice"  # OK
    """

    # Internal attributes that should not be treated as case variables
    _INTERNAL_ATTRS = frozenset({
        "_variables", "_lock", "_type_validation", "_type_constraints"
    })

    def __init__(
        self,
        initial_values: Optional[Dict[str, Any]] = None,
        type_validation: bool = False,
        type_constraints: Optional[Dict[str, Union[Type, Tuple[Type, ...]]]] = None
    ) -> None:
        """
        Initialize a new Case instance.

        Args:
            initial_values: Optional dictionary of initial variable values.
                All variable names must be valid Python identifiers.
            type_validation: Whether to enable type validation. When enabled,
                setting variables will check against registered type constraints.
                Defaults to False.
            type_constraints: Optional dictionary mapping variable names to their
                expected types. Each type can be a single type or a tuple of types.
                Only used when type_validation is enabled.

        Raises:
            InvalidVariableNameError: If any initial variable name is not a valid
                Python identifier.
            TypeValidationError: If type_validation is enabled and any initial value
                doesn't match its type constraint.

        Example:
            >>> case = Case({"x": 1, "y": 2})
            >>> case.x
            1
            >>> case = Case({"invalid name": 1})  # Raises InvalidVariableNameError
            >>> # With type validation
            >>> case = Case(
            ...     initial_values={"counter": 0},
            ...     type_validation=True,
            ...     type_constraints={"counter": int}
            ... )
        """
        # Use object.__setattr__ to avoid triggering our custom __setattr__
        object.__setattr__(self, "_variables", {})
        object.__setattr__(self, "_lock", threading.RLock())
        object.__setattr__(self, "_type_validation", type_validation)
        object.__setattr__(self, "_type_constraints", type_constraints.copy() if type_constraints else {})

        if initial_values:
            # Validate all variable names before adding
            for name in initial_values:
                validate_variable_name(name)

            # If type validation is enabled, validate initial values
            if type_validation and type_constraints:
                for name, value in initial_values.items():
                    if name in type_constraints:
                        self._validate_type(name, value)

            self._variables.update(initial_values)

    def _validate_type(self, name: str, value: Any) -> None:
        """
        Internal method to validate a value's type against registered constraints.

        Args:
            name: The variable name.
            value: The value to validate.

        Raises:
            TypeValidationError: If the value's type doesn't match the constraint.
        """
        if name in self._type_constraints:
            expected_type = self._type_constraints[name]
            if not isinstance(value, expected_type):
                raise TypeValidationError(
                    name=name,
                    expected_type=expected_type,
                    actual_type=type(value),
                    value=value
                )

    # Type validation management methods

    def enable_type_validation(self) -> None:
        """
        Enable type validation for this Case instance.

        When type validation is enabled, setting variables will check their
        values against registered type constraints (if any). Variables without
        constraints can still be set to any type.

        This method is thread-safe.

        Example:
            >>> case = Case()
            >>> case.set_type("counter", int)
            >>> case.enable_type_validation()
            >>> case.counter = 10  # OK
            >>> case.counter = "not an int"  # Raises TypeValidationError
        """
        with self._lock:
            object.__setattr__(self, "_type_validation", True)

    def disable_type_validation(self) -> None:
        """
        Disable type validation for this Case instance.

        When type validation is disabled, variables can be set to any type
        regardless of registered type constraints. The constraints are
        preserved and will be enforced again if validation is re-enabled.

        This method is thread-safe.

        Example:
            >>> case = Case(type_validation=True)
            >>> case.set_type("counter", int)
            >>> case.disable_type_validation()
            >>> case.counter = "now any type is allowed"  # OK, validation disabled
        """
        with self._lock:
            object.__setattr__(self, "_type_validation", False)

    def is_type_validation_enabled(self) -> bool:
        """
        Check if type validation is currently enabled.

        This method is thread-safe.

        Returns:
            True if type validation is enabled, False otherwise.

        Example:
            >>> case = Case()
            >>> case.is_type_validation_enabled()
            False
            >>> case.enable_type_validation()
            >>> case.is_type_validation_enabled()
            True
        """
        with self._lock:
            return self._type_validation

    def set_type(
        self,
        name: str,
        expected_type: Union[Type, Tuple[Type, ...]]
    ) -> None:
        """
        Set the expected type for a variable.

        This registers a type constraint for the variable. When type validation
        is enabled, setting this variable will validate that the value matches
        the expected type.

        This method is thread-safe.

        Args:
            name: The variable name to constrain.
            expected_type: The expected type(s). Can be a single type (e.g., int)
                or a tuple of types (e.g., (int, float)) for multiple allowed types.

        Raises:
            InvalidVariableNameError: If the name is not a valid Python identifier.

        Example:
            >>> case = Case(type_validation=True)
            >>> case.set_type("counter", int)
            >>> case.set_type("value", (int, float))  # Allow int or float
            >>> case.counter = 10  # OK
            >>> case.value = 3.14  # OK
            >>> case.counter = "string"  # Raises TypeValidationError
        """
        validate_variable_name(name)
        with self._lock:
            self._type_constraints[name] = expected_type

    def get_type(self, name: str) -> Optional[Union[Type, Tuple[Type, ...]]]:
        """
        Get the expected type constraint for a variable.

        This method is thread-safe.

        Args:
            name: The variable name to look up.

        Returns:
            The type constraint if one is set, None otherwise.

        Example:
            >>> case = Case()
            >>> case.set_type("counter", int)
            >>> case.get_type("counter")
            <class 'int'>
            >>> case.get_type("unconstrained") is None
            True
        """
        with self._lock:
            return self._type_constraints.get(name)

    def remove_type(self, name: str) -> bool:
        """
        Remove the type constraint for a variable.

        This method is thread-safe.

        Args:
            name: The variable name to remove the constraint for.

        Returns:
            True if a constraint was removed, False if no constraint existed.

        Example:
            >>> case = Case()
            >>> case.set_type("counter", int)
            >>> case.remove_type("counter")
            True
            >>> case.remove_type("counter")  # Already removed
            False
        """
        with self._lock:
            if name in self._type_constraints:
                del self._type_constraints[name]
                return True
            return False

    def clear_types(self) -> None:
        """
        Remove all type constraints.

        This removes all registered type constraints but does not disable
        type validation. After calling this, no variables will have type
        constraints until new ones are set.

        This method is thread-safe.

        Example:
            >>> case = Case(type_validation=True)
            >>> case.set_type("x", int)
            >>> case.set_type("y", str)
            >>> case.clear_types()
            >>> case.get_type("x") is None
            True
        """
        with self._lock:
            self._type_constraints.clear()

    def list_types(self) -> Dict[str, Union[Type, Tuple[Type, ...]]]:
        """
        Get a copy of all type constraints.

        This method is thread-safe.

        Returns:
            A dictionary mapping variable names to their type constraints.

        Example:
            >>> case = Case()
            >>> case.set_type("x", int)
            >>> case.set_type("y", str)
            >>> case.list_types()
            {'x': <class 'int'>, 'y': <class 'str'>}
        """
        with self._lock:
            return self._type_constraints.copy()

    def set(self, name: str, value: Any) -> None:
        """
        Set a case variable value.

        This method is thread-safe. If type validation is enabled and a type
        constraint is registered for this variable, the value's type will be
        validated before setting.

        Args:
            name: The name of the variable.
            value: The value to store. Can be any Python object.

        Raises:
            InvalidVariableNameError: If the name is not a valid Python identifier.
            TypeValidationError: If type validation is enabled and the value's type
                doesn't match the registered constraint for this variable.

        Example:
            >>> case = Case()
            >>> case.set("my_var", [1, 2, 3])
            >>> case.get("my_var")
            [1, 2, 3]
            >>> case.set("invalid name", 123)  # Raises InvalidVariableNameError
            >>> # With type validation
            >>> case.enable_type_validation()
            >>> case.set_type("counter", int)
            >>> case.set("counter", 10)  # OK
            >>> case.set("counter", "string")  # Raises TypeValidationError
        """
        validate_variable_name(name)
        with self._lock:
            if self._type_validation:
                self._validate_type(name, value)
            self._variables[name] = value

    def get(self, name: str, default: Any = None) -> Any:
        """
        Get a case variable value.

        This method is thread-safe.

        Args:
            name: The name of the variable to retrieve.
            default: The value to return if the variable doesn't exist.
                Defaults to None.

        Returns:
            The variable value if it exists, otherwise the default value.

        Example:
            >>> case = Case()
            >>> case.set("exists", 42)
            >>> case.get("exists")
            42
            >>> case.get("not_exists", "default")
            'default'
        """
        with self._lock:
            return self._variables.get(name, default)

    def delete(self, name: str) -> bool:
        """
        Delete a case variable.

        This method is thread-safe.

        Args:
            name: The name of the variable to delete.

        Returns:
            True if the variable was deleted, False if it didn't exist.

        Example:
            >>> case = Case()
            >>> case.set("to_delete", 123)
            >>> case.delete("to_delete")
            True
            >>> case.delete("to_delete")
            False
        """
        with self._lock:
            if name in self._variables:
                del self._variables[name]
                return True
            return False

    def exists(self, name: str) -> bool:
        """
        Check if a case variable exists.

        This method is thread-safe.

        Args:
            name: The name of the variable to check.

        Returns:
            True if the variable exists, False otherwise.

        Example:
            >>> case = Case()
            >>> case.set("test", "value")
            >>> case.exists("test")
            True
            >>> case.exists("nonexistent")
            False
        """
        with self._lock:
            return name in self._variables

    def clear(self, clear_types: bool = False) -> None:
        """
        Clear all case variables.

        This removes all variables from the case, resetting it to
        an empty state. Optionally, type constraints can also be cleared.
        This method is thread-safe.

        Args:
            clear_types: If True, also clear all type constraints. Defaults to False.

        Example:
            >>> case = Case()
            >>> case.set("var1", 1)
            >>> case.set("var2", 2)
            >>> case.clear()
            >>> case.list_names()
            []
            >>> # Clear both variables and types
            >>> case.set_type("x", int)
            >>> case.set("x", 10)
            >>> case.clear(clear_types=True)
            >>> case.list_types()
            {}
        """
        with self._lock:
            self._variables.clear()
            if clear_types:
                self._type_constraints.clear()

    def list_names(self) -> List[str]:
        """
        Get a list of all variable names.

        This method is thread-safe.

        Returns:
            A list of all variable names currently stored.

        Example:
            >>> case = Case()
            >>> case.set("a", 1)
            >>> case.set("b", 2)
            >>> sorted(case.list_names())
            ['a', 'b']
        """
        with self._lock:
            return list(self._variables.keys())

    def list_all(self) -> Dict[str, Any]:
        """
        Get a copy of all variables.

        This method is thread-safe.

        Returns:
            A shallow copy of the internal variables dictionary.

        Example:
            >>> case = Case()
            >>> case.set("x", 10)
            >>> case.set("y", 20)
            >>> case.list_all()
            {'x': 10, 'y': 20}
        """
        with self._lock:
            return self._variables.copy()

    def count(self) -> int:
        """
        Get the number of stored variables.

        This method is thread-safe.

        Returns:
            The count of variables in the case.

        Example:
            >>> case = Case()
            >>> case.count()
            0
            >>> case.set("var", "value")
            >>> case.count()
            1
        """
        with self._lock:
            return len(self._variables)

    def update(self, variables: Dict[str, Any]) -> None:
        """
        Update multiple variables at once.

        This method is thread-safe and atomic - all variables are
        updated in a single lock acquisition. All variable names are
        validated before any updates are applied. If type validation is
        enabled, all types are validated before any updates are applied.

        Args:
            variables: A dictionary of variable names and values to set.
                All variable names must be valid Python identifiers.

        Raises:
            InvalidVariableNameError: If any variable name is not a valid
                Python identifier. No variables are updated if any name is invalid.
            TypeValidationError: If type validation is enabled and any value's type
                doesn't match its registered constraint. No variables are updated
                if any type validation fails.

        Example:
            >>> case = Case()
            >>> case.update({"a": 1, "b": 2, "c": 3})
            >>> case.get("b")
            2
            >>> case.update({"invalid name": 1})  # Raises InvalidVariableNameError
        """
        # Validate all variable names first (before acquiring lock)
        for name in variables:
            validate_variable_name(name)
        with self._lock:
            # Validate all types before updating (if validation enabled)
            if self._type_validation:
                for name, value in variables.items():
                    self._validate_type(name, value)
            self._variables.update(variables)

    def items(self) -> List[Tuple[str, Any]]:
        """
        Get all variable name-value pairs.

        This method is thread-safe. It returns a list (not an iterator)
        to ensure thread-safety by creating a snapshot of the data.

        Returns:
            A list of tuples of (name, value) for each variable.

        Example:
            >>> case = Case()
            >>> case.set("key", "value")
            >>> for name, val in case.items():
            ...     print(f"{name}: {val}")
            key: value
        """
        with self._lock:
            return list(self._variables.items())

    def keys(self) -> List[str]:
        """
        Get all variable names.

        This method is thread-safe.

        Returns:
            A list of all variable names.

        Example:
            >>> case = Case()
            >>> case.set("a", 1)
            >>> case.set("b", 2)
            >>> sorted(case.keys())
            ['a', 'b']
        """
        with self._lock:
            return list(self._variables.keys())

    def values(self) -> List[Any]:
        """
        Get all variable values.

        This method is thread-safe.

        Returns:
            A list of all variable values.

        Example:
            >>> case = Case()
            >>> case.set("a", 1)
            >>> case.set("b", 2)
            >>> sorted(case.values())
            [1, 2]
        """
        with self._lock:
            return list(self._variables.values())

    # Attribute-based access support

    def __getattr__(self, name: str) -> Any:
        """
        Get a case variable via attribute access.

        This method is called when an attribute is accessed that doesn't exist
        on the object itself. It allows `case.myvar` syntax for getting variables.
        This method is thread-safe.

        Args:
            name: The name of the attribute/variable.

        Returns:
            The variable value if it exists.

        Raises:
            AttributeError: If the variable doesn't exist.

        Example:
            >>> case = Case()
            >>> case.set("x", 42)
            >>> case.x
            42
            >>> case.nonexistent  # Raises AttributeError
        """
        # Check if this is an internal attribute
        if name.startswith("_"):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        # Get from variables dict with lock
        lock = object.__getattribute__(self, "_lock")
        variables = object.__getattribute__(self, "_variables")
        with lock:
            if name in variables:
                return variables[name]

        raise AttributeError(
            f"Case variable '{name}' does not exist. "
            f"Use case.get('{name}', default) to get with a default value."
        )

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Set a case variable via attribute access.

        This method is called for all attribute assignments. It allows
        `case.myvar = value` syntax for setting variables.
        This method is thread-safe.

        Args:
            name: The name of the attribute/variable.
            value: The value to set.

        Raises:
            InvalidVariableNameError: If the name is not a valid Python identifier.
            TypeValidationError: If type validation is enabled and the value's type
                doesn't match the registered constraint for this variable.

        Example:
            >>> case = Case()
            >>> case.x = 42
            >>> case.get("x")
            42
            >>> # With type validation
            >>> case.enable_type_validation()
            >>> case.set_type("y", int)
            >>> case.y = 10  # OK
            >>> case.y = "string"  # Raises TypeValidationError
        """
        # Handle internal attributes normally
        if name in self._INTERNAL_ATTRS:
            object.__setattr__(self, name, value)
        else:
            # Validate variable name before storing
            validate_variable_name(name)
            # Store as a case variable with lock
            with self._lock:
                if self._type_validation:
                    self._validate_type(name, value)
                self._variables[name] = value

    def __delattr__(self, name: str) -> None:
        """
        Delete a case variable via attribute deletion.

        This method allows `del case.myvar` syntax for deleting variables.
        This method is thread-safe.

        Args:
            name: The name of the attribute/variable to delete.

        Raises:
            AttributeError: If the variable doesn't exist.

        Example:
            >>> case = Case()
            >>> case.x = 42
            >>> del case.x
            >>> case.exists("x")
            False
        """
        if name in self._INTERNAL_ATTRS:
            raise AttributeError(
                f"Cannot delete internal attribute '{name}'"
            )

        with self._lock:
            if name in self._variables:
                del self._variables[name]
            else:
                raise AttributeError(
                    f"Case variable '{name}' does not exist"
                )

    # Container protocol support

    def __getitem__(self, name: str) -> Any:
        """
        Get a case variable via dictionary-style access.

        This method allows `case['myvar']` syntax for getting variables.
        This method is thread-safe.

        Args:
            name: The name of the variable.

        Returns:
            The variable value.

        Raises:
            KeyError: If the variable doesn't exist.

        Example:
            >>> case = Case()
            >>> case.set("x", 42)
            >>> case['x']
            42
            >>> case['nonexistent']  # Raises KeyError
        """
        with self._lock:
            if name in self._variables:
                return self._variables[name]
        raise KeyError(
            f"Case variable '{name}' does not exist. "
            f"Use case.get('{name}', default) to get with a default value."
        )

    def __setitem__(self, name: str, value: Any) -> None:
        """
        Set a case variable via dictionary-style access.

        This method allows `case['myvar'] = value` syntax for setting variables.
        This method is thread-safe.

        Args:
            name: The name of the variable.
            value: The value to set.

        Raises:
            InvalidVariableNameError: If the name is not a valid Python identifier.
            TypeValidationError: If type validation is enabled and the value's type
                doesn't match the registered constraint for this variable.

        Example:
            >>> case = Case()
            >>> case['x'] = 42
            >>> case.get("x")
            42
        """
        validate_variable_name(name)
        with self._lock:
            if self._type_validation:
                self._validate_type(name, value)
            self._variables[name] = value

    def __delitem__(self, name: str) -> None:
        """
        Delete a case variable via dictionary-style access.

        This method allows `del case['myvar']` syntax for deleting variables.
        This method is thread-safe.

        Args:
            name: The name of the variable to delete.

        Raises:
            KeyError: If the variable doesn't exist.

        Example:
            >>> case = Case()
            >>> case['x'] = 42
            >>> del case['x']
            >>> case.exists("x")
            False
        """
        with self._lock:
            if name in self._variables:
                del self._variables[name]
            else:
                raise KeyError(f"Case variable '{name}' does not exist")

    def __contains__(self, name: str) -> bool:
        """
        Check if a variable exists using the 'in' operator.

        This method is thread-safe.

        Args:
            name: The name of the variable to check.

        Returns:
            True if the variable exists, False otherwise.

        Example:
            >>> case = Case()
            >>> case.set("test", 1)
            >>> "test" in case
            True
            >>> "missing" in case
            False
        """
        with self._lock:
            return name in self._variables

    def __len__(self) -> int:
        """
        Get the number of variables using len().

        This method is thread-safe.

        Returns:
            The count of variables in the case.

        Example:
            >>> case = Case()
            >>> len(case)
            0
            >>> case.x = 1
            >>> len(case)
            1
        """
        with self._lock:
            return len(self._variables)

    def __iter__(self) -> Iterator[str]:
        """
        Iterate over variable names.

        This method is thread-safe. It creates a snapshot of the keys
        to ensure safe iteration even if the case is modified.

        Returns:
            An iterator over variable names.

        Example:
            >>> case = Case()
            >>> case.set("a", 1)
            >>> case.set("b", 2)
            >>> sorted(list(case))
            ['a', 'b']
        """
        with self._lock:
            return iter(list(self._variables.keys()))

    def __bool__(self) -> bool:
        """
        Check if the case has any variables.

        This method is thread-safe.

        Returns:
            True if there are variables, False if empty.

        Example:
            >>> case = Case()
            >>> bool(case)
            False
            >>> case.x = 1
            >>> bool(case)
            True
        """
        with self._lock:
            return bool(self._variables)

    # String representations

    def __repr__(self) -> str:
        """Get a detailed string representation of the case."""
        with self._lock:
            var_count = len(self._variables)
            if var_count == 0:
                return "Case()"
            elif var_count <= 3:
                items = ", ".join(f"{k}={v!r}" for k, v in self._variables.items())
                return f"Case({items})"
            else:
                return f"Case({var_count} variables)"

    def __str__(self) -> str:
        """Get a simple string representation of the case."""
        with self._lock:
            var_count = len(self._variables)
        if var_count == 0:
            return "Case (empty)"
        return f"Case with {var_count} variable(s)"

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

        Raises:
            InvalidVariableNameError: If the name is not a valid Python identifier.
            TypeValidationError: If type validation is enabled and the value's type
                doesn't match the registered constraint for this variable.

        Example:
            >>> case = Case()
            >>> case.set("counter", 5)
            >>> old_value = case.get_and_set("counter", 10)
            >>> print(old_value)  # 5
            5
            >>> print(case.get("counter"))  # 10
            10
        """
        validate_variable_name(name)
        with self._lock:
            if self._type_validation:
                self._validate_type(name, value)
            old_value = self._variables.get(name)
            self._variables[name] = value
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

        Raises:
            InvalidVariableNameError: If the name is not a valid Python identifier.
            TypeValidationError: If type validation is enabled, the variable doesn't
                exist, and the value's type doesn't match the registered constraint.

        Example:
            >>> case = Case()
            >>> case.set_if_absent("counter", 0)  # Returns 0, sets counter
            0
            >>> case.set_if_absent("counter", 100)  # Returns 0, doesn't change
            0
        """
        validate_variable_name(name)
        with self._lock:
            if name not in self._variables:
                if self._type_validation:
                    self._validate_type(name, value)
                self._variables[name] = value
                return value
            return self._variables[name]

    def increment(self, name: str, delta: Union[int, float] = 1) -> Union[int, float]:
        """
        Atomically increment a numeric variable.

        This method safely increments a variable by the given delta,
        initializing it to 0 if it doesn't exist.

        Note: Type validation is performed on the result, not the delta.
        If the variable has a type constraint of (int, float), the result
        must be numeric (which it will be after incrementing).

        Args:
            name: The name of the variable to increment.
            delta: The amount to increment by (default: 1).

        Returns:
            The new value after incrementing.

        Raises:
            InvalidVariableNameError: If the name is not a valid Python identifier.
            TypeError: If the current value is not numeric.
            TypeValidationError: If type validation is enabled and the result doesn't
                match the registered type constraint for this variable.

        Example:
            >>> case = Case()
            >>> case.set("counter", 5)
            >>> case.increment("counter")
            6
            >>> case.increment("counter", 10)
            16
            >>> # Works with floats too
            >>> case.set("value", 1.5)
            >>> case.increment("value", 0.5)
            2.0
        """
        validate_variable_name(name)
        with self._lock:
            current = self._variables.get(name, 0)
            if not isinstance(current, (int, float)):
                raise TypeError(
                    f"Cannot increment non-numeric value of type {type(current).__name__}"
                )
            new_value = current + delta
            if self._type_validation:
                self._validate_type(name, new_value)
            self._variables[name] = new_value
            return new_value

    def decrement(self, name: str, delta: Union[int, float] = 1) -> Union[int, float]:
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
            >>> case = Case()
            >>> case.set("counter", 10)
            >>> case.decrement("counter")
            9
            >>> case.decrement("counter", 5)
            4
        """
        return self.increment(name, -delta)

    def update_with(self, name: str, func: Callable[[Any], Any], default: Any = None) -> Any:
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

        Raises:
            InvalidVariableNameError: If the name is not a valid Python identifier.
            TypeValidationError: If type validation is enabled and the result doesn't
                match the registered type constraint for this variable.

        Example:
            >>> case = Case()
            >>> case.set("items", [1, 2, 3])
            >>> case.update_with("items", lambda x: x + [4])
            [1, 2, 3, 4]
            >>> # String manipulation
            >>> case.set("text", "hello")
            >>> case.update_with("text", lambda s: s.upper())
            'HELLO'
        """
        validate_variable_name(name)
        with self._lock:
            current = self._variables.get(name, default)
            new_value = func(current)
            if self._type_validation:
                self._validate_type(name, new_value)
            self._variables[name] = new_value
            return new_value

    def append_to_list(self, name: str, value: Any) -> List[Any]:
        """
        Atomically append a value to a list variable.

        If the variable doesn't exist, it creates a new list.

        Note: Type validation (if enabled) is performed when creating a new list.
        If the variable already exists as a list, no type validation is performed
        since the type is already known to be list.

        Args:
            name: The name of the list variable.
            value: The value to append.

        Returns:
            A copy of the list after appending.

        Raises:
            InvalidVariableNameError: If the name is not a valid Python identifier.
            TypeError: If the current value is not a list.
            TypeValidationError: If type validation is enabled, the variable doesn't
                exist, and 'list' doesn't match the registered type constraint.

        Example:
            >>> case = Case()
            >>> case.append_to_list("items", "first")
            ['first']
            >>> case.append_to_list("items", "second")
            ['first', 'second']
        """
        validate_variable_name(name)
        with self._lock:
            current = self._variables.get(name)
            if current is None:
                current = []
                # Validate type when creating a new list
                if self._type_validation:
                    self._validate_type(name, current)
                self._variables[name] = current
            elif not isinstance(current, list):
                raise TypeError(
                    f"Cannot append to non-list value of type {type(current).__name__}"
                )
            current.append(value)
            return current.copy()

    def get_lock(self) -> threading.RLock:
        """
        Get the internal lock for advanced synchronization scenarios.

        This allows users to perform multiple operations atomically by
        acquiring the lock manually. Use with caution and always release
        the lock properly (preferably using a context manager).

        Returns:
            The internal RLock instance.

        Example:
            >>> case = Case()
            >>> case.set("x", 10)
            >>> case.set("y", 20)
            >>> with case.get_lock():
            ...     # Multiple operations are atomic
            ...     x = case.get("x")
            ...     y = case.get("y")
            ...     case.set("sum", x + y)
            >>> case.get("sum")
            30
        """
        return self._lock
