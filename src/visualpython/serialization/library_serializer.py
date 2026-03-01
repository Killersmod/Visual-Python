"""
Library serialization for exporting and importing reusable node collections.

This module provides the LibrarySerializer class and convenience functions
for serializing collections of nodes (with their connections) as reusable
libraries that can be shared and imported into other projects.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from visualpython.serialization.project_serializer import SerializationError


@dataclass
class LibraryMetadata:
    """
    Metadata for a node library.

    Attributes:
        name: Human-readable name for the library.
        description: Detailed description of the library's contents.
        author: Author of the library.
        version: Version string for the library.
        created_at: Timestamp when the library was created.
        tags: List of tags for categorization and searching.
    """

    name: str = "Untitled Library"
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "created_at": self.created_at,
            "tags": self.tags.copy(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LibraryMetadata:
        """Deserialize metadata from dictionary."""
        return cls(
            name=data.get("name", "Untitled Library"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            version=data.get("version", "1.0.0"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            tags=data.get("tags", []).copy(),
        )


@dataclass
class LibraryData:
    """
    Data structure for a node library.

    Attributes:
        metadata: Library metadata (name, author, etc.).
        nodes: List of serialized node dictionaries.
        connections: List of serialized connection dictionaries (internal only).
    """

    metadata: LibraryMetadata
    nodes: List[Dict[str, Any]]
    connections: List[Dict[str, str]]

    @property
    def node_count(self) -> int:
        """Get the number of nodes in the library."""
        return len(self.nodes)

    @property
    def connection_count(self) -> int:
        """Get the number of connections in the library."""
        return len(self.connections)

    def get_node_types(self) -> List[str]:
        """Get a list of unique node types in the library."""
        return list(set(node.get("type", "unknown") for node in self.nodes))


class LibrarySerializer:
    """
    Handles serialization and deserialization of node libraries.

    The LibrarySerializer exports and imports collections of nodes with their
    internal connections as reusable library files (.vnl).

    Example:
        >>> serializer = LibrarySerializer()
        >>> library = serializer.export_nodes(graph, selected_node_ids, metadata)
        >>> serializer.save(library, "my_library.vnl")
        >>> loaded = serializer.load("my_library.vnl")
        >>> new_nodes = serializer.import_nodes(graph, loaded)

    Attributes:
        FILE_FORMAT_VERSION: Current version of the library format.
        FILE_EXTENSION: Default file extension for library files.
    """

    FILE_FORMAT_VERSION = "1.0.0"
    FILE_EXTENSION = ".vnl"

    def __init__(self) -> None:
        """Initialize the library serializer."""
        pass

    def export_nodes(
        self,
        nodes: List[Any],  # List of BaseNode
        connections: List[Any],  # List of Connection
        metadata: Optional[LibraryMetadata] = None,
    ) -> LibraryData:
        """
        Export a collection of nodes and their internal connections as a library.

        Args:
            nodes: List of nodes to export.
            connections: List of all connections in the graph.
            metadata: Optional metadata for the library.

        Returns:
            LibraryData containing the serialized nodes and connections.
        """
        if not nodes:
            raise SerializationError("Cannot create library from empty node selection")

        # Build set of node IDs for filtering connections
        node_ids: Set[str] = {node.id for node in nodes}

        # Serialize nodes
        serialized_nodes: List[Dict[str, Any]] = []
        for node in nodes:
            serialized_nodes.append(node.to_dict())

        # Filter to only internal connections (both endpoints in selection)
        serialized_connections: List[Dict[str, str]] = []
        for connection in connections:
            if (connection.source_node_id in node_ids and
                connection.target_node_id in node_ids):
                serialized_connections.append(connection.to_dict())

        # Create default metadata if not provided
        if metadata is None:
            metadata = LibraryMetadata(
                name=f"Library ({len(nodes)} nodes)",
                description=f"Exported library containing {len(nodes)} nodes",
            )

        return LibraryData(
            metadata=metadata,
            nodes=serialized_nodes,
            connections=serialized_connections,
        )

    def save(
        self,
        library: LibraryData,
        file_path: Union[str, Path],
        pretty: bool = True,
    ) -> None:
        """
        Save a library to a file.

        Args:
            library: The library data to save.
            file_path: Path to the output file.
            pretty: If True, format the JSON with indentation for readability.

        Raises:
            SerializationError: If the file cannot be written.
        """
        try:
            data = self.serialize(library)
            path = Path(file_path)

            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                if pretty:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(data, f, ensure_ascii=False)

        except (OSError, IOError) as e:
            raise SerializationError(f"Failed to save library to '{file_path}': {e}") from e

    def load(self, file_path: Union[str, Path]) -> LibraryData:
        """
        Load a library from a file.

        Args:
            file_path: Path to the input file.

        Returns:
            The loaded LibraryData object.

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
            raise SerializationError(f"Failed to load library from '{file_path}': {e}") from e

    def serialize(self, library: LibraryData) -> Dict[str, Any]:
        """
        Serialize a library to a dictionary.

        Args:
            library: The library to serialize.

        Returns:
            Dictionary representation of the library with format metadata.
        """
        return {
            "format_version": self.FILE_FORMAT_VERSION,
            "file_type": "visualpython_library",
            "library": {
                "metadata": library.metadata.to_dict(),
                "nodes": library.nodes,
                "connections": library.connections,
            },
        }

    def deserialize(self, data: Dict[str, Any]) -> LibraryData:
        """
        Deserialize a library from a dictionary.

        Args:
            data: Dictionary containing serialized library data.

        Returns:
            The deserialized LibraryData object.

        Raises:
            SerializationError: If the data is invalid or incompatible.
        """
        # Validate format
        file_type = data.get("file_type")
        if file_type != "visualpython_library":
            raise SerializationError(
                f"Invalid file type: expected 'visualpython_library', got '{file_type}'"
            )

        format_version = data.get("format_version", "1.0.0")
        self._check_version_compatibility(format_version)

        library_data = data.get("library")
        if library_data is None:
            raise SerializationError("Missing 'library' field in data")

        # Parse metadata
        metadata_data = library_data.get("metadata", {})
        metadata = LibraryMetadata.from_dict(metadata_data)

        # Get nodes and connections
        nodes = library_data.get("nodes", [])
        connections = library_data.get("connections", [])

        return LibraryData(
            metadata=metadata,
            nodes=nodes,
            connections=connections,
        )

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
                    f"Incompatible library format version: {version}. "
                    f"Current version is {self.FILE_FORMAT_VERSION}"
                )

        except (ValueError, AttributeError) as e:
            raise SerializationError(f"Invalid format version: {version}") from e

    def prepare_nodes_for_import(
        self,
        library: LibraryData,
        position_offset: tuple = (50.0, 50.0),
    ) -> tuple:
        """
        Prepare library nodes for import by generating new IDs and offsetting positions.

        This method creates copies of the node data with new unique IDs and
        offset positions, ready to be instantiated in the target graph.

        Args:
            library: The library data to prepare.
            position_offset: Tuple of (x, y) offset to apply to node positions.

        Returns:
            Tuple of (prepared_nodes, prepared_connections, id_mapping) where:
            - prepared_nodes: List of node dictionaries with new IDs
            - prepared_connections: List of connection dictionaries with mapped IDs
            - id_mapping: Dict mapping old IDs to new IDs
        """
        id_mapping: Dict[str, str] = {}
        prepared_nodes: List[Dict[str, Any]] = []
        prepared_connections: List[Dict[str, str]] = []

        # Process nodes
        for node_data in library.nodes:
            old_id = node_data.get("id")
            new_id = str(uuid.uuid4())
            id_mapping[old_id] = new_id

            # Create copy with new ID and offset position
            new_node_data = node_data.copy()
            new_node_data["id"] = new_id

            # Offset position
            if "position" in new_node_data:
                new_node_data["position"] = {
                    "x": new_node_data["position"].get("x", 0) + position_offset[0],
                    "y": new_node_data["position"].get("y", 0) + position_offset[1],
                }

            # Clear port connections (they'll be recreated)
            for port_data in new_node_data.get("input_ports", []):
                port_data["connection"] = None
            for port_data in new_node_data.get("output_ports", []):
                port_data["connections"] = []

            prepared_nodes.append(new_node_data)

        # Remap connections
        for conn_data in library.connections:
            old_source_id = conn_data.get("source_node_id")
            old_target_id = conn_data.get("target_node_id")

            if old_source_id in id_mapping and old_target_id in id_mapping:
                prepared_connections.append({
                    "source_node_id": id_mapping[old_source_id],
                    "source_port_name": conn_data.get("source_port_name"),
                    "target_node_id": id_mapping[old_target_id],
                    "target_port_name": conn_data.get("target_port_name"),
                })

        return prepared_nodes, prepared_connections, id_mapping


# Module-level convenience functions


def export_library(
    nodes: List[Any],
    connections: List[Any],
    file_path: Union[str, Path],
    metadata: Optional[LibraryMetadata] = None,
    pretty: bool = True,
) -> None:
    """
    Export nodes and their connections to a library file.

    This is a convenience function that creates a LibrarySerializer and exports.

    Args:
        nodes: List of nodes to export.
        connections: List of all connections in the graph.
        file_path: Path to the output file.
        metadata: Optional metadata for the library.
        pretty: If True, format the JSON with indentation.

    Raises:
        SerializationError: If export fails.

    Example:
        >>> from visualpython.serialization import export_library
        >>> export_library(selected_nodes, graph.connections, "utils.vnl")
    """
    serializer = LibrarySerializer()
    library = serializer.export_nodes(nodes, connections, metadata)
    serializer.save(library, file_path, pretty)


def load_library(
    file_path: Union[str, Path],
) -> LibraryData:
    """
    Load a library from a file.

    This is a convenience function that creates a LibrarySerializer and loads.

    Args:
        file_path: Path to the library file.

    Returns:
        The loaded LibraryData object.

    Raises:
        SerializationError: If loading fails.

    Example:
        >>> from visualpython.serialization import load_library
        >>> library = load_library("utils.vnl")
        >>> print(f"Loaded {library.node_count} nodes")
    """
    serializer = LibrarySerializer()
    return serializer.load(file_path)
