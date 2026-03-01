"""
Dependency scanner for analyzing workflow subgraph references.

Provides algorithms for:
- Forward dependency scanning (recursive subgraph discovery)
- Reverse dependency scanning (which workflows use this one)
- Dependency tree hashing for change detection
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from visualpython.utils.logging import get_logger

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph

logger = get_logger(__name__)


@dataclass
class DependencyNode:
    """Represents a single node in a dependency tree."""

    name: str
    file_path: Optional[str]
    node_type: str  # "reference", "embedded", "circular"
    version: Optional[str] = None
    is_broken: bool = False
    children: List["DependencyNode"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for hashing and storage."""
        return {
            "name": self.name,
            "file_path": self.file_path,
            "node_type": self.node_type,
            "version": self.version,
            "is_broken": self.is_broken,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DependencyNode":
        """Deserialize from dict."""
        return cls(
            name=data["name"],
            file_path=data.get("file_path"),
            node_type=data.get("node_type", "reference"),
            version=data.get("version"),
            is_broken=data.get("is_broken", False),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )


@dataclass
class ReverseDependency:
    """A project/graph that uses the current workflow as a subgraph."""

    name: str
    file_path: str
    node_name: str
    version: Optional[str] = None


class DependencyScanner:
    """Scans workflows to build forward and reverse dependency trees."""

    def scan_forward(
        self,
        graph: "Graph",
        visited: Optional[Set[str]] = None,
    ) -> List[DependencyNode]:
        """
        Recursively scan a graph for all subgraph dependencies.

        Iterates all nodes, finds SubgraphNode instances, and recurses
        into their internal graphs. Uses a visited set to prevent infinite
        recursion on circular references.
        """
        if visited is None:
            visited = set()

        dependencies: List[DependencyNode] = []

        for node in graph.nodes:
            if node.node_type != "subgraph":
                continue

            sub_path = node.subgraph_path
            is_ref = node.is_reference_based
            is_broken = getattr(node, "is_reference_broken", False)

            dep = DependencyNode(
                name=node.subgraph_name or node.name,
                file_path=sub_path,
                node_type="reference" if is_ref else "embedded",
                version=getattr(node, "reference_version", None),
                is_broken=is_broken,
            )

            visit_key = str(Path(sub_path).resolve()) if sub_path else node.subgraph_id
            if visit_key in visited:
                dep.node_type = "circular"
                dep.name += " (circular)"
                dependencies.append(dep)
                continue

            visited.add(visit_key)

            child_graph_data = self._load_subgraph_data(node)
            if child_graph_data:
                dep.children = self._scan_graph_data(child_graph_data, visited)

            dependencies.append(dep)

        return dependencies

    def scan_reverse(
        self,
        current_file_path: str,
        scan_paths: List[Path],
    ) -> List[ReverseDependency]:
        """
        Scan .vpy files in scan_paths to find which reference current_file_path.
        """
        reverse_deps: List[ReverseDependency] = []
        try:
            current_resolved = Path(current_file_path).resolve()
        except (ValueError, OSError):
            return reverse_deps

        seen_files: Set[str] = set()
        for vpy_file in self._collect_vpy_files(scan_paths):
            resolved = str(vpy_file.resolve())
            if resolved in seen_files or vpy_file.resolve() == current_resolved:
                continue
            seen_files.add(resolved)

            refs = self._find_subgraph_references(vpy_file, current_resolved)
            reverse_deps.extend(refs)

        return reverse_deps

    @staticmethod
    def compute_tree_hash(tree: List[DependencyNode]) -> str:
        """Compute a SHA-256 hash of the dependency tree."""
        data = json.dumps(
            [node.to_dict() for node in tree],
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _load_subgraph_data(self, node: Any) -> Optional[Dict[str, Any]]:
        """Load the internal graph data from a SubgraphNode."""
        try:
            return node.get_internal_graph_data()
        except Exception as e:
            logger.debug("Failed to load subgraph data for %s: %s", node.name, e)
            return None

    def _scan_graph_data(
        self,
        graph_data: Dict[str, Any],
        visited: Set[str],
    ) -> List[DependencyNode]:
        """
        Scan raw graph data (dict) for nested subgraph nodes.

        This avoids needing to fully instantiate a Graph object —
        it parses the JSON structure directly.
        """
        children: List[DependencyNode] = []
        nodes_data = graph_data.get("nodes", [])

        for node_data in nodes_data:
            if node_data.get("type") != "subgraph":
                continue

            props = node_data.get("properties", {})
            sub_path = props.get("subgraph_path")
            is_ref = props.get("is_reference_based", False)
            sub_name = props.get("subgraph_name", node_data.get("name", "Subgraph"))
            version = props.get("reference_version")

            is_broken = False
            if is_ref and sub_path:
                is_broken = not Path(sub_path).exists()

            dep = DependencyNode(
                name=sub_name,
                file_path=sub_path,
                node_type="reference" if is_ref else "embedded",
                version=version,
                is_broken=is_broken,
            )

            visit_key = str(Path(sub_path).resolve()) if sub_path else props.get("subgraph_id", "")
            if visit_key in visited:
                dep.node_type = "circular"
                dep.name += " (circular)"
                children.append(dep)
                continue

            visited.add(visit_key)

            nested_data = self._load_nested_graph_data(props)
            if nested_data:
                dep.children = self._scan_graph_data(nested_data, visited)

            children.append(dep)

        return children

    def _load_nested_graph_data(self, props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Load graph data from serialized subgraph node properties."""
        is_ref = props.get("is_reference_based", False)
        sub_path = props.get("subgraph_path")

        if is_ref and sub_path:
            return self._load_vpy_graph_data(Path(sub_path))

        embedded = props.get("embedded_graph_data")
        if embedded:
            return embedded

        return None

    def _load_vpy_graph_data(self, path: Path) -> Optional[Dict[str, Any]]:
        """Load and unwrap graph data from a .vpy file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "graph" in data:
                return data["graph"]
            if "subgraph" in data:
                return data["subgraph"]
            return data
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.debug("Failed to load .vpy file %s: %s", path, e)
            return None

    def _collect_vpy_files(self, paths: List[Path]) -> List[Path]:
        """Recursively collect all .vpy files from the given paths."""
        result: List[Path] = []
        for path in paths:
            if not path.exists():
                continue
            if path.is_file() and path.suffix == ".vpy":
                result.append(path)
            elif path.is_dir():
                result.extend(path.rglob("*.vpy"))
        return result

    def _find_subgraph_references(
        self,
        vpy_file: Path,
        target_resolved: Path,
    ) -> List[ReverseDependency]:
        """Check if a .vpy file contains subgraph nodes referencing the target."""
        refs: List[ReverseDependency] = []
        try:
            with open(vpy_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return refs

        graph_data = data.get("graph", data)
        metadata = graph_data.get("metadata", {})
        graph_name = metadata.get("name", vpy_file.stem)
        graph_version = metadata.get("version")

        for node_data in graph_data.get("nodes", []):
            if node_data.get("type") != "subgraph":
                continue

            props = node_data.get("properties", {})
            sub_path = props.get("subgraph_path")
            if not sub_path:
                continue

            try:
                if Path(sub_path).resolve() == target_resolved:
                    refs.append(
                        ReverseDependency(
                            name=graph_name,
                            file_path=str(vpy_file),
                            node_name=props.get("subgraph_name", node_data.get("name", "Subgraph")),
                            version=graph_version,
                        )
                    )
            except (ValueError, OSError):
                continue

        return refs
