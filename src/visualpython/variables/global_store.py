"""
Global variable store for shared state management across nodes.

This module defines the GlobalVariableStore class, which provides an in-memory
dictionary-based storage system for global variables. It implements a singleton
pattern to ensure all nodes access the same variable store.

Thread Safety:
    All operations on the GlobalVariableStore are thread-safe through the use
    of a reentrant lock (RLock). This allows safe concurrent access from multiple
    threads during parallel execution scenarios (e.g., ThreadNode execution).

Type Annotations:
    The store supports optional type annotations for variables. When type
    validation is enabled, values are validated against their declared types
    before being stored. This helps catch type errors early.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from visualpython.variables.type_registry import (
        TypeAnnotation,
        TypeValidationError,
        VariableTypeRegistry,
    )
    from visualpython.nodes.models.port import PortType


class GlobalVariableStore:
    """
    An in-memory dictionary-based storage for global variables.

    This class provides a centralized store for variables that need to be
    shared across multiple nodes during graph execution. It implements
    the singleton pattern to ensure a single source of truth for all
    global variables.

    The store supports basic dictionary-like operations including get, set,
    delete, and iteration, along with additional utility methods for
    variable management.

    Thread Safety:
        All methods in this class are thread-safe. A reentrant lock (RLock)
        is used to protect all operations, allowing safe concurrent access
        from multiple threads. The RLock allows the same thread to acquire
        the lock multiple times (reentrant), which is useful for nested calls.

        For atomic read-modify-write operations, use the provided atomic
        methods like `increment()`, `get_and_set()`, or `update_with()`.

    Attributes:
        _instance: The singleton instance of the store.
        _instance_lock: Class-level lock for singleton creation.
        _variables: The internal dictionary storing variable name-value pairs.
        _lock: Instance-level lock for thread-safe operations.

    Example:
        >>> store = GlobalVariableStore.get_instance()
        >>> store.set("counter", 0)
        >>> store.get("counter")
        0
        >>> # For thread-safe increment, use the atomic method:
        >>> store.increment("counter")
        1
        >>> store.clear()
    """

    _instance: Optional[GlobalVariableStore] = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        """
        Initialize a new GlobalVariableStore instance.

        Note:
            This constructor should not be called directly. Use
            get_instance() to obtain the singleton instance.
        """
        self._variables: Dict[str, Any] = {}
        self._lock: threading.RLock = threading.RLock()
        self._type_validation_enabled: bool = False
        self._strict_validation: bool = False

    @classmethod
    def get_instance(cls) -> GlobalVariableStore:
        """
        Get the singleton instance of the GlobalVariableStore.

        This method is thread-safe through double-checked locking pattern.

        Returns:
            The single GlobalVariableStore instance.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store2 = GlobalVariableStore.get_instance()
            >>> store is store2
            True
        """
        if cls._instance is None:
            with cls._instance_lock:
                # Double-check after acquiring lock
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

    def set(self, name: str, value: Any, validate: Optional[bool] = None) -> None:
        """
        Set a global variable value.

        This method is thread-safe. If type validation is enabled and the
        variable has a type annotation, the value will be validated before
        being stored.

        Args:
            name: The name of the variable.
            value: The value to store. Can be any Python object.
            validate: Override the default validation behavior. If None,
                     uses the store's type_validation_enabled setting.

        Raises:
            ValueError: If strict validation is enabled and the value
                       doesn't match the type annotation.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("my_var", [1, 2, 3])
            >>> store.get("my_var")
            [1, 2, 3]
        """
        should_validate = validate if validate is not None else self._type_validation_enabled

        if should_validate:
            self._validate_type(name, value)

        with self._lock:
            self._variables[name] = value

    def get(self, name: str, default: Any = None) -> Any:
        """
        Get a global variable value.

        This method is thread-safe.

        Args:
            name: The name of the variable to retrieve.
            default: The value to return if the variable doesn't exist.
                Defaults to None.

        Returns:
            The variable value if it exists, otherwise the default value.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("exists", 42)
            >>> store.get("exists")
            42
            >>> store.get("not_exists", "default")
            'default'
        """
        with self._lock:
            return self._variables.get(name, default)

    def delete(self, name: str) -> bool:
        """
        Delete a global variable.

        This method is thread-safe.

        Args:
            name: The name of the variable to delete.

        Returns:
            True if the variable was deleted, False if it didn't exist.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("to_delete", 123)
            >>> store.delete("to_delete")
            True
            >>> store.delete("to_delete")
            False
        """
        with self._lock:
            if name in self._variables:
                del self._variables[name]
                return True
            return False

    def exists(self, name: str) -> bool:
        """
        Check if a global variable exists.

        This method is thread-safe.

        Args:
            name: The name of the variable to check.

        Returns:
            True if the variable exists, False otherwise.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("test", "value")
            >>> store.exists("test")
            True
            >>> store.exists("nonexistent")
            False
        """
        with self._lock:
            return name in self._variables

    def clear(self) -> None:
        """
        Clear all global variables.

        This removes all variables from the store, resetting it to
        an empty state. This method is thread-safe.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("var1", 1)
            >>> store.set("var2", 2)
            >>> store.clear()
            >>> store.list_names()
            []
        """
        with self._lock:
            self._variables.clear()

    def list_names(self) -> List[str]:
        """
        Get a list of all variable names.

        This method is thread-safe.

        Returns:
            A list of all variable names currently stored.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("a", 1)
            >>> store.set("b", 2)
            >>> sorted(store.list_names())
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
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("x", 10)
            >>> store.set("y", 20)
            >>> store.list_all()
            {'x': 10, 'y': 20}
        """
        with self._lock:
            return self._variables.copy()

    def count(self) -> int:
        """
        Get the number of stored variables.

        This method is thread-safe.

        Returns:
            The count of variables in the store.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.clear()
            >>> store.count()
            0
            >>> store.set("var", "value")
            >>> store.count()
            1
        """
        with self._lock:
            return len(self._variables)

    def update(self, variables: Dict[str, Any]) -> None:
        """
        Update multiple variables at once.

        This method is thread-safe and atomic - all variables are
        updated in a single lock acquisition.

        Args:
            variables: A dictionary of variable names and values to set.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.update({"a": 1, "b": 2, "c": 3})
            >>> store.get("b")
            2
        """
        with self._lock:
            self._variables.update(variables)

    def items(self) -> List[Tuple[str, Any]]:
        """
        Get all variable name-value pairs.

        This method is thread-safe. It returns a list (not an iterator)
        to ensure thread-safety by creating a snapshot of the data.

        Returns:
            A list of tuples of (name, value) for each variable.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("key", "value")
            >>> for name, val in store.items():
            ...     print(f"{name}: {val}")
            key: value
        """
        with self._lock:
            return list(self._variables.items())

    def __contains__(self, name: str) -> bool:
        """
        Check if a variable exists using the 'in' operator.

        This method is thread-safe.

        Args:
            name: The name of the variable to check.

        Returns:
            True if the variable exists, False otherwise.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("test", 1)
            >>> "test" in store
            True
        """
        with self._lock:
            return name in self._variables

    def __len__(self) -> int:
        """
        Get the number of variables using len().

        This method is thread-safe.

        Returns:
            The count of variables in the store.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.clear()
            >>> len(store)
            0
        """
        with self._lock:
            return len(self._variables)

    def __repr__(self) -> str:
        """Get a detailed string representation of the store."""
        with self._lock:
            var_count = len(self._variables)
        return f"GlobalVariableStore(variables={var_count})"

    def __str__(self) -> str:
        """Get a simple string representation of the store."""
        with self._lock:
            var_count = len(self._variables)
        return f"GlobalVariableStore with {var_count} variable(s)"

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
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("counter", 5)
            >>> old_value = store.get_and_set("counter", 10)
            >>> print(old_value)  # 5
            >>> print(store.get("counter"))  # 10
        """
        with self._lock:
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

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set_if_absent("counter", 0)  # Returns 0, sets counter
            >>> store.set_if_absent("counter", 100)  # Returns 0, doesn't change
        """
        with self._lock:
            if name not in self._variables:
                self._variables[name] = value
                return value
            return self._variables[name]

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
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("counter", 5)
            >>> store.increment("counter")
            6
            >>> store.increment("counter", 10)
            16
        """
        with self._lock:
            current = self._variables.get(name, 0)
            if not isinstance(current, (int, float)):
                raise TypeError(
                    f"Cannot increment non-numeric value of type {type(current).__name__}"
                )
            new_value = current + delta
            self._variables[name] = new_value
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
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("counter", 10)
            >>> store.decrement("counter")
            9
            >>> store.decrement("counter", 5)
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

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set("items", [1, 2, 3])
            >>> store.update_with("items", lambda x: x + [4])
            [1, 2, 3, 4]
        """
        with self._lock:
            current = self._variables.get(name, default)
            new_value = func(current)
            self._variables[name] = new_value
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
            >>> store = GlobalVariableStore.get_instance()
            >>> store.append_to_list("items", "first")
            ['first']
            >>> store.append_to_list("items", "second")
            ['first', 'second']
        """
        with self._lock:
            current = self._variables.get(name)
            if current is None:
                current = []
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
        the lock properly.

        Returns:
            The internal RLock instance.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> with store.get_lock():
            ...     # Multiple operations are atomic
            ...     x = store.get("x")
            ...     y = store.get("y")
            ...     store.set("sum", x + y)
        """
        return self._lock

    # Type annotation and validation methods

    def enable_type_validation(self, strict: bool = False) -> None:
        """
        Enable type validation for variable assignments.

        When enabled, values are validated against their type annotations
        before being stored.

        Args:
            strict: If True, type mismatches raise ValueError.
                   If False, mismatches are logged but don't raise.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.enable_type_validation(strict=True)
        """
        with self._lock:
            self._type_validation_enabled = True
            self._strict_validation = strict

    def disable_type_validation(self) -> None:
        """
        Disable type validation for variable assignments.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.disable_type_validation()
        """
        with self._lock:
            self._type_validation_enabled = False
            self._strict_validation = False

    @property
    def type_validation_enabled(self) -> bool:
        """Check if type validation is enabled."""
        with self._lock:
            return self._type_validation_enabled

    @property
    def strict_validation(self) -> bool:
        """Check if strict validation mode is enabled."""
        with self._lock:
            return self._strict_validation

    def get_type_registry(self) -> "VariableTypeRegistry":
        """
        Get the VariableTypeRegistry singleton instance.

        Returns:
            The VariableTypeRegistry instance.
        """
        from visualpython.variables.type_registry import VariableTypeRegistry
        return VariableTypeRegistry.get_instance()

    def set_type_annotation(
        self,
        variable_name: str,
        expected_type: "PortType",
        allow_none: bool = False,
        description: str = "",
    ) -> "TypeAnnotation":
        """
        Set a type annotation for a variable.

        Args:
            variable_name: The name of the variable to annotate.
            expected_type: The expected PortType for the variable.
            allow_none: Whether None is an acceptable value.
            description: Optional description of the expected type.

        Returns:
            The created TypeAnnotation.

        Example:
            >>> from visualpython.nodes.models.port import PortType
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set_type_annotation("counter", PortType.INTEGER)
        """
        from visualpython.variables.type_registry import (
            VariableTypeRegistry,
            TypeValidationSeverity,
        )
        registry = VariableTypeRegistry.get_instance()
        return registry.set_annotation(
            variable_name=variable_name,
            expected_type=expected_type,
            severity=TypeValidationSeverity.ERROR if self._strict_validation else TypeValidationSeverity.WARNING,
            description=description,
            allow_none=allow_none,
        )

    def set_type_annotation_from_python_type(
        self,
        variable_name: str,
        python_type: type,
        allow_none: bool = False,
        description: str = "",
    ) -> "TypeAnnotation":
        """
        Set a type annotation using a Python type.

        Args:
            variable_name: The name of the variable to annotate.
            python_type: The expected Python type (e.g., int, str, list).
            allow_none: Whether None is an acceptable value.
            description: Optional description of the expected type.

        Returns:
            The created TypeAnnotation.

        Example:
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set_type_annotation_from_python_type("counter", int)
            >>> store.set_type_annotation_from_python_type("name", str, allow_none=True)
        """
        from visualpython.variables.type_registry import (
            VariableTypeRegistry,
            TypeValidationSeverity,
        )
        registry = VariableTypeRegistry.get_instance()
        return registry.set_annotation_from_type(
            variable_name=variable_name,
            python_type=python_type,
            severity=TypeValidationSeverity.ERROR if self._strict_validation else TypeValidationSeverity.WARNING,
            description=description,
            allow_none=allow_none,
        )

    def get_type_annotation(self, variable_name: str) -> Optional["TypeAnnotation"]:
        """
        Get the type annotation for a variable.

        Args:
            variable_name: The name of the variable.

        Returns:
            The TypeAnnotation if one exists, None otherwise.
        """
        from visualpython.variables.type_registry import VariableTypeRegistry
        return VariableTypeRegistry.get_instance().get_annotation(variable_name)

    def has_type_annotation(self, variable_name: str) -> bool:
        """
        Check if a variable has a type annotation.

        Args:
            variable_name: The name of the variable.

        Returns:
            True if the variable has an annotation, False otherwise.
        """
        from visualpython.variables.type_registry import VariableTypeRegistry
        return VariableTypeRegistry.get_instance().has_annotation(variable_name)

    def remove_type_annotation(self, variable_name: str) -> bool:
        """
        Remove the type annotation for a variable.

        Args:
            variable_name: The name of the variable.

        Returns:
            True if an annotation was removed, False if none existed.
        """
        from visualpython.variables.type_registry import VariableTypeRegistry
        return VariableTypeRegistry.get_instance().remove_annotation(variable_name)

    def validate_type(self, variable_name: str, value: Any) -> Optional["TypeValidationError"]:
        """
        Validate a value against the type annotation for a variable.

        This can be called manually without setting the value.

        Args:
            variable_name: The name of the variable.
            value: The value to validate.

        Returns:
            A TypeValidationError if validation fails, None if valid.
        """
        from visualpython.variables.type_registry import VariableTypeRegistry
        return VariableTypeRegistry.get_instance().validate(variable_name, value)

    def _validate_type(self, name: str, value: Any) -> None:
        """
        Internal method to validate a value and handle errors.

        Args:
            name: The name of the variable.
            value: The value to validate.

        Raises:
            ValueError: If strict validation is enabled and validation fails.
        """
        from visualpython.variables.type_registry import VariableTypeRegistry
        registry = VariableTypeRegistry.get_instance()

        if self._strict_validation:
            registry.validate_strict(name, value)
        else:
            registry.validate(name, value)

    def list_type_annotations(self) -> Dict[str, "TypeAnnotation"]:
        """
        Get all type annotations.

        Returns:
            A dictionary mapping variable names to their TypeAnnotations.
        """
        from visualpython.variables.type_registry import VariableTypeRegistry
        return VariableTypeRegistry.get_instance().list_annotations()

    def clear_type_annotations(self) -> None:
        """
        Clear all type annotations.

        Note: This does not affect the stored variables, only their
        type annotations.
        """
        from visualpython.variables.type_registry import VariableTypeRegistry
        VariableTypeRegistry.get_instance().clear()

    def set_validated(
        self,
        name: str,
        value: Any,
        expected_type: "PortType",
        allow_none: bool = False,
    ) -> None:
        """
        Set a variable with type annotation and validation in one call.

        This is a convenience method that:
        1. Sets a type annotation for the variable
        2. Validates the value against the annotation
        3. Sets the value if validation passes

        Args:
            name: The name of the variable.
            value: The value to store.
            expected_type: The expected PortType for the variable.
            allow_none: Whether None is an acceptable value.

        Raises:
            ValueError: If validation fails (always raises, regardless of strict mode).

        Example:
            >>> from visualpython.nodes.models.port import PortType
            >>> store = GlobalVariableStore.get_instance()
            >>> store.set_validated("counter", 42, PortType.INTEGER)
        """
        from visualpython.variables.type_registry import (
            VariableTypeRegistry,
            TypeValidationSeverity,
        )
        registry = VariableTypeRegistry.get_instance()

        # Set the annotation with ERROR severity
        registry.set_annotation(
            variable_name=name,
            expected_type=expected_type,
            severity=TypeValidationSeverity.ERROR,
            allow_none=allow_none,
        )

        # Validate strictly (raises on error)
        registry.validate_strict(name, value)

        # Set the value
        with self._lock:
            self._variables[name] = value
