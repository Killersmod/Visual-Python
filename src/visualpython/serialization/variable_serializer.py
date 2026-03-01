"""
Variable serialization for saving and loading global variables to JSON.

This module provides the VariableSerializer class and convenience functions
for serializing global variables to JSON format, enabling persistence of
application state across sessions.

Type Annotations:
    The serializer also supports saving and loading type annotations for
    variables, allowing declared types to persist across sessions.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from visualpython.serialization.project_serializer import SerializationError
from visualpython.variables.global_store import GlobalVariableStore
from visualpython.variables.type_registry import VariableTypeRegistry
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class VariableSerializer:
    """
    Handles serialization and deserialization of global variables.

    The VariableSerializer converts global variables to and from JSON format,
    enabling persistence of application state across sessions.

    Example:
        >>> serializer = VariableSerializer()
        >>> serializer.save("my_variables.json")
        >>> serializer.load("my_variables.json")

    Attributes:
        FILE_FORMAT_VERSION: Current version of the serialization format.
    """

    FILE_FORMAT_VERSION = "1.1.0"

    def __init__(
        self,
        store: Optional[GlobalVariableStore] = None,
        type_registry: Optional[VariableTypeRegistry] = None,
        include_type_annotations: bool = True,
    ) -> None:
        """
        Initialize the variable serializer.

        Args:
            store: Optional GlobalVariableStore to use. If not provided,
                   uses the singleton instance.
            type_registry: Optional VariableTypeRegistry to use. If not provided,
                          uses the singleton instance.
            include_type_annotations: Whether to include type annotations in
                                     serialization. Default is True.
        """
        self._store = store or GlobalVariableStore.get_instance()
        self._type_registry = type_registry or VariableTypeRegistry.get_instance()
        self._include_type_annotations = include_type_annotations

    def save(
        self,
        file_path: Union[str, Path],
        pretty: bool = True,
    ) -> None:
        """
        Save global variables to a JSON file.

        Args:
            file_path: Path to the output file.
            pretty: If True, format the JSON with indentation for readability.

        Raises:
            SerializationError: If the file cannot be written or variables
                               cannot be serialized.
        """
        try:
            data = self.serialize()
            path = Path(file_path)

            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                if pretty:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                else:
                    json.dump(data, f, ensure_ascii=False, default=str)

        except (OSError, IOError) as e:
            raise SerializationError(f"Failed to save variables to '{file_path}': {e}") from e
        except (TypeError, ValueError) as e:
            raise SerializationError(
                f"Failed to serialize variables: {e}. "
                "Some variable values may not be JSON-serializable."
            ) from e

    def load(self, file_path: Union[str, Path], merge: bool = False) -> int:
        """
        Load global variables from a JSON file.

        Args:
            file_path: Path to the input file.
            merge: If True, merge loaded variables with existing ones.
                   If False (default), clear existing variables first.

        Returns:
            Number of variables loaded.

        Raises:
            SerializationError: If the file cannot be read or parsed.
        """
        try:
            path = Path(file_path)

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return self.deserialize(data, merge=merge)

        except json.JSONDecodeError as e:
            raise SerializationError(f"Invalid JSON in '{file_path}': {e}") from e
        except (OSError, IOError) as e:
            raise SerializationError(f"Failed to load variables from '{file_path}': {e}") from e

    def serialize(self) -> Dict[str, Any]:
        """
        Serialize global variables to a dictionary.

        Returns:
            Dictionary representation of the variables with format metadata.
            Includes type annotations if include_type_annotations is True.
        """
        variables = self._store.list_all()

        # Serialize each variable with type information for better restoration
        serialized_vars: Dict[str, Any] = {}
        for name, value in variables.items():
            serialized_vars[name] = self._serialize_value(value)

        result: Dict[str, Any] = {
            "format_version": self.FILE_FORMAT_VERSION,
            "file_type": "visualpython_variables",
            "saved_at": datetime.now().isoformat(),
            "variable_count": len(serialized_vars),
            "variables": serialized_vars,
        }

        # Include type annotations if enabled
        if self._include_type_annotations:
            type_annotations = self._type_registry.to_dict()
            if type_annotations:
                result["type_annotations"] = type_annotations
                result["type_annotation_count"] = len(type_annotations)

        return result

    def deserialize(self, data: Dict[str, Any], merge: bool = False) -> int:
        """
        Deserialize variables from a dictionary into the store.

        Args:
            data: Dictionary containing serialized variable data.
            merge: If True, merge with existing variables.
                   If False, clear existing variables first.

        Returns:
            Number of variables loaded.

        Raises:
            SerializationError: If the data is invalid or incompatible.
        """
        # Validate format
        file_type = data.get("file_type")
        if file_type != "visualpython_variables":
            raise SerializationError(
                f"Invalid file type: expected 'visualpython_variables', got '{file_type}'"
            )

        format_version = data.get("format_version", "1.0.0")
        self._check_version_compatibility(format_version)

        variables_data = data.get("variables")
        if variables_data is None:
            raise SerializationError("Missing 'variables' field in data")

        if not isinstance(variables_data, dict):
            raise SerializationError("'variables' field must be a dictionary")

        # Clear existing variables and type annotations if not merging
        if not merge:
            self._store.clear()
            if self._include_type_annotations:
                self._type_registry.clear()

        # Deserialize type annotations first (so validation works during variable loading)
        if self._include_type_annotations:
            type_annotations_data = data.get("type_annotations", {})
            if type_annotations_data:
                self._type_registry.from_dict(type_annotations_data, merge=merge)

        # Deserialize each variable
        loaded_count = 0
        for name, value_data in variables_data.items():
            try:
                value = self._deserialize_value(value_data)
                # Set without validation during loading to preserve data
                self._store.set(name, value, validate=False)
                loaded_count += 1
            except Exception:
                # Log warning but continue with other variables
                logger.warning("Variable deserialization failed", exc_info=True)
                pass

        return loaded_count

    def _serialize_value(self, value: Any) -> Any:
        """
        Serialize a single value with type information.

        Args:
            value: The value to serialize.

        Returns:
            A JSON-serializable representation of the value.
        """
        type_name = type(value).__name__

        # Handle common types
        if value is None:
            return {"_type": "NoneType", "value": None}
        elif isinstance(value, bool):
            # bool must be checked before int (bool is subclass of int)
            return {"_type": "bool", "value": value}
        elif isinstance(value, int):
            return {"_type": "int", "value": value}
        elif isinstance(value, float):
            return {"_type": "float", "value": value}
        elif isinstance(value, str):
            return {"_type": "str", "value": value}
        elif isinstance(value, list):
            return {"_type": "list", "value": [self._serialize_value(v) for v in value]}
        elif isinstance(value, tuple):
            return {"_type": "tuple", "value": [self._serialize_value(v) for v in value]}
        elif isinstance(value, dict):
            serialized_dict = {}
            for k, v in value.items():
                # JSON requires string keys
                serialized_dict[str(k)] = self._serialize_value(v)
            return {"_type": "dict", "value": serialized_dict}
        elif isinstance(value, set):
            return {"_type": "set", "value": [self._serialize_value(v) for v in value]}
        elif isinstance(value, frozenset):
            return {"_type": "frozenset", "value": [self._serialize_value(v) for v in value]}
        elif isinstance(value, bytes):
            # Encode bytes as base64 string
            import base64
            return {"_type": "bytes", "value": base64.b64encode(value).decode("ascii")}
        else:
            # For other types, try to convert to string representation
            return {"_type": type_name, "value": str(value), "_raw": True}

    def _deserialize_value(self, data: Any) -> Any:
        """
        Deserialize a single value from its stored representation.

        Args:
            data: The stored representation of the value.

        Returns:
            The deserialized Python value.
        """
        # Handle simple values (for backwards compatibility or manually edited files)
        if not isinstance(data, dict) or "_type" not in data:
            return data

        type_name: str = data["_type"]
        value: Any = data.get("value")

        if type_name == "NoneType":
            return None
        elif type_name == "bool":
            return bool(value) if value is not None else False
        elif type_name == "int":
            return int(value) if value is not None else 0
        elif type_name == "float":
            return float(value) if value is not None else 0.0
        elif type_name == "str":
            return str(value) if value is not None else ""
        elif type_name == "list":
            if value is None:
                return []
            return [self._deserialize_value(v) for v in value]
        elif type_name == "tuple":
            if value is None:
                return ()
            return tuple(self._deserialize_value(v) for v in value)
        elif type_name == "dict":
            if value is None:
                return {}
            return {k: self._deserialize_value(v) for k, v in value.items()}
        elif type_name == "set":
            if value is None:
                return set()
            return {self._deserialize_value(v) for v in value}
        elif type_name == "frozenset":
            if value is None:
                return frozenset()
            return frozenset(self._deserialize_value(v) for v in value)
        elif type_name == "bytes":
            import base64
            if value is None:
                return b""
            return base64.b64decode(value.encode("ascii"))
        else:
            # For unknown types, return the string value
            if data.get("_raw"):
                return value
            return value

    def _check_version_compatibility(self, version: str) -> None:
        """
        Check if the file format version is compatible.

        Args:
            version: The format version from the file.

        Raises:
            SerializationError: If the version is incompatible.
        """
        try:
            file_major, file_minor, _ = map(int, version.split("."))
            current_major, current_minor, _ = map(int, self.FILE_FORMAT_VERSION.split("."))

            # Major version must match
            if file_major != current_major:
                raise SerializationError(
                    f"Incompatible file format version: {version}. "
                    f"Current version is {self.FILE_FORMAT_VERSION}"
                )

            # Minor version differences are acceptable (backwards compatible)

        except (ValueError, AttributeError) as e:
            raise SerializationError(f"Invalid format version: {version}") from e


# Module-level convenience functions


def save_variables(
    file_path: Union[str, Path],
    pretty: bool = True,
    store: Optional[GlobalVariableStore] = None,
) -> None:
    """
    Save global variables to a JSON file.

    This is a convenience function that creates a VariableSerializer and saves.

    Args:
        file_path: Path to the output file.
        pretty: If True, format the JSON with indentation for readability.
        store: Optional GlobalVariableStore to use.

    Raises:
        SerializationError: If the file cannot be written.

    Example:
        >>> from visualpython.serialization import save_variables
        >>> save_variables("my_variables.json")
    """
    serializer = VariableSerializer(store)
    serializer.save(file_path, pretty)


def load_variables(
    file_path: Union[str, Path],
    merge: bool = False,
    store: Optional[GlobalVariableStore] = None,
) -> int:
    """
    Load global variables from a JSON file.

    This is a convenience function that creates a VariableSerializer and loads.

    Args:
        file_path: Path to the input file.
        merge: If True, merge with existing variables.
        store: Optional GlobalVariableStore to use.

    Returns:
        Number of variables loaded.

    Raises:
        SerializationError: If the file cannot be read or parsed.

    Example:
        >>> from visualpython.serialization import load_variables
        >>> count = load_variables("my_variables.json")
        >>> print(f"Loaded {count} variables")
    """
    serializer = VariableSerializer(store)
    return serializer.load(file_path, merge)
