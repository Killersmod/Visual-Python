"""
Project serialization for saving and loading VisualPython graphs to JSON.

This module provides the ProjectSerializer class and convenience functions
for serializing the entire graph (nodes, connections, properties) to JSON format,
enabling saving and loading of projects.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from visualpython.graph.graph import Graph
from visualpython.nodes.registry import NodeRegistry, get_node_registry
from visualpython.nodes.models.base_node import Position
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class SerializationError(Exception):
    """Exception raised when serialization or deserialization fails."""

    pass


class ProjectSerializer:
    """
    Handles serialization and deserialization of VisualPython projects.

    The ProjectSerializer converts Graph objects to and from JSON format,
    managing the complete state including nodes, connections, and metadata.

    Example:
        >>> serializer = ProjectSerializer()
        >>> serializer.save(graph, "my_project.vpy")
        >>> loaded_graph = serializer.load("my_project.vpy")

    Attributes:
        FILE_FORMAT_VERSION: Current version of the serialization format.
    """

    FILE_FORMAT_VERSION = "1.0.0"

    def __init__(self, registry: Optional[NodeRegistry] = None) -> None:
        """
        Initialize the project serializer.

        Args:
            registry: Optional NodeRegistry to use for creating nodes during
                     deserialization. If not provided, uses the global registry.
        """
        self._registry = registry or get_node_registry()
        # Ensure default nodes are registered
        if not self._registry.get_all_node_types():
            self._registry.register_default_nodes()

    @staticmethod
    def increment_version(version_str: str) -> str:
        """
        Increment the patch component of a semver version string.

        Args:
            version_str: Version string like "1.0.0".

        Returns:
            Incremented version string like "1.0.1".
        """
        try:
            parts = version_str.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            return ".".join(parts)
        except (ValueError, IndexError):
            logger.debug("Version parse fallback", exc_info=True)
            return "1.0.1"

    def save(
        self,
        graph: Graph,
        file_path: Union[str, Path],
        pretty: bool = True,
    ) -> None:
        """
        Save a graph to a JSON file.

        Auto-increments the workflow version and updates modified_at timestamp.

        Args:
            graph: The graph to save.
            file_path: Path to the output file.
            pretty: If True, format the JSON with indentation for readability.

        Raises:
            SerializationError: If the file cannot be written.
        """
        try:
            # Auto-increment version on save
            graph.metadata.version = self.increment_version(graph.metadata.version)
            graph.metadata.modified_at = datetime.now().isoformat()

            # Auto-detect flow entry/exit points from Start nodes so
            # the file works correctly when used as a subgraph.
            if not graph.metadata.flow_entry_points:
                for node in graph.nodes:
                    if node.node_type == "start":
                        graph.metadata.flow_entry_points = [{"node_id": node.id}]
                        break

            data = self.serialize(graph)
            path = Path(file_path)

            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                if pretty:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(data, f, ensure_ascii=False)

            # Mark the graph as saved
            graph.mark_saved()

        except (OSError, IOError) as e:
            raise SerializationError(f"Failed to save project to '{file_path}': {e}") from e

    def load(self, file_path: Union[str, Path]) -> Graph:
        """
        Load a graph from a JSON file.

        Args:
            file_path: Path to the input file.

        Returns:
            The loaded Graph object.

        Raises:
            SerializationError: If the file cannot be read or parsed.
        """
        try:
            path = Path(file_path)

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return self.deserialize(data)

        except json.JSONDecodeError as e:
            raise SerializationError(f"Invalid JSON in '{file_path}': {e}") from e
        except (OSError, IOError) as e:
            raise SerializationError(f"Failed to load project from '{file_path}': {e}") from e

    def serialize(self, graph: Graph) -> Dict[str, Any]:
        """
        Serialize a graph to a dictionary.

        Args:
            graph: The graph to serialize.

        Returns:
            Dictionary representation of the graph with format metadata.
        """
        graph_data = graph.to_dict()

        # Add format version and file type for future compatibility
        return {
            "format_version": self.FILE_FORMAT_VERSION,
            "file_type": "visualpython_project",
            "graph": graph_data,
        }

    def deserialize(self, data: Dict[str, Any]) -> Graph:
        """
        Deserialize a graph from a dictionary.

        Args:
            data: Dictionary containing serialized project data.

        Returns:
            The deserialized Graph object.

        Raises:
            SerializationError: If the data is invalid or incompatible.
        """
        # Validate format — also accept legacy library files that have
        # a "graph" key but were saved without file_type metadata.
        file_type = data.get("file_type")
        if file_type is None and "graph" in data:
            # Legacy workflow library file; treat as a valid project
            pass
        elif file_type != "visualpython_project":
            raise SerializationError(
                f"Invalid file type: expected 'visualpython_project', got '{file_type}'"
            )

        format_version = data.get("format_version", "1.0.0")
        self._check_version_compatibility(format_version)

        graph_data = data.get("graph")
        if graph_data is None:
            raise SerializationError("Missing 'graph' field in project data")

        # Use Graph.from_dict with our node factory
        return Graph.from_dict(graph_data, self._create_node_from_dict)

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

            # Warn about minor version differences (but still load)
            if file_minor > current_minor:
                # Future minor versions may have additional features
                # but should be backwards compatible
                pass

        except (ValueError, AttributeError) as e:
            raise SerializationError(f"Invalid format version: {version}") from e

    def _create_node_from_dict(self, node_data: Dict[str, Any]) -> Any:
        """
        Create a node instance from serialized data.

        This is the node factory function passed to Graph.from_dict.

        Args:
            node_data: Dictionary containing serialized node data.

        Returns:
            A new node instance.

        Raises:
            SerializationError: If the node type is unknown.
        """
        node_type = node_data.get("type")
        if not node_type:
            raise SerializationError("Node data missing 'type' field")

        node_type_info = self._registry.get_node_type(node_type)
        if node_type_info is None:
            raise SerializationError(f"Unknown node type: '{node_type}'")

        # Use the node class's from_dict method
        node_class = node_type_info.node_class
        return node_class.from_dict(node_data)


# Module-level convenience functions


def save_project(
    graph: Graph,
    file_path: Union[str, Path],
    pretty: bool = True,
    registry: Optional[NodeRegistry] = None,
) -> None:
    """
    Save a graph to a JSON file.

    This is a convenience function that creates a ProjectSerializer and saves the graph.

    Args:
        graph: The graph to save.
        file_path: Path to the output file.
        pretty: If True, format the JSON with indentation for readability.
        registry: Optional NodeRegistry to use.

    Raises:
        SerializationError: If the file cannot be written.

    Example:
        >>> from visualpython.serialization import save_project
        >>> save_project(graph, "my_program.vpy")
    """
    serializer = ProjectSerializer(registry)
    serializer.save(graph, file_path, pretty)


def load_project(
    file_path: Union[str, Path],
    registry: Optional[NodeRegistry] = None,
) -> Graph:
    """
    Load a graph from a JSON file.

    This is a convenience function that creates a ProjectSerializer and loads the graph.

    Args:
        file_path: Path to the input file.
        registry: Optional NodeRegistry to use for creating nodes.

    Returns:
        The loaded Graph object.

    Raises:
        SerializationError: If the file cannot be read or parsed.

    Example:
        >>> from visualpython.serialization import load_project
        >>> graph = load_project("my_program.vpy")
    """
    serializer = ProjectSerializer(registry)
    return serializer.load(file_path)
