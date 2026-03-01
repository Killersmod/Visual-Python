"""
Subgraph node model that represents a reusable subgraph callable like a function.

This module defines the SubgraphNode class, which allows users to encapsulate
a collection of nodes as a reusable component that can be called from other
graphs, enabling modular script composition.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph


class SubgraphNode(BaseNode):
    """
    A node that encapsulates a reusable subgraph that can be called like a function.

    The SubgraphNode represents a self-contained subgraph with defined inputs and
    outputs. When executed, it runs the internal graph with the provided inputs and
    returns the outputs. This enables modular composition of visual scripts.

    Subgraphs can be:
    - Created by selecting nodes and converting them to a subgraph
    - Loaded from workflow library files (.vpy files) as references
    - Loaded from legacy embedded graph data (backward compatibility)

    The SubgraphNode dynamically creates input/output ports based on the
    SubgraphInput and SubgraphOutput nodes within the internal graph.

    Attributes:
        subgraph_id: Unique identifier for the subgraph definition.
        subgraph_name: Human-readable name for the subgraph.
        subgraph_path: Optional path to external subgraph file.
        embedded_graph_data: Optional embedded graph data (for inline subgraphs).
        input_mappings: Maps external port names to internal SubgraphInput node IDs.
        output_mappings: Maps internal SubgraphOutput node IDs to external port names.

    Example:
        >>> node = SubgraphNode(name="MyFunction")
        >>> node.load_subgraph_from_file("my_function.vns")
        >>> # Or create from embedded data
        >>> node.load_subgraph_from_data(graph_data)
    """

    # Class-level metadata
    node_type: str = "subgraph"
    """Unique identifier for subgraph nodes."""

    node_category: str = "Subgraphs"
    """Category for organizing in the UI."""

    node_color: str = "#9C27B0"
    """Purple color to distinguish subgraph nodes."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        subgraph_name: Optional[str] = None,
        subgraph_path: Optional[str] = None,
    ) -> None:
        """
        Initialize a new SubgraphNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Subgraph'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            subgraph_name: Optional name for the subgraph definition.
            subgraph_path: Optional path to an external subgraph file.
        """
        # Initialize subgraph-specific attributes before calling super().__init__
        # because _setup_ports() is called during super().__init__
        self._subgraph_id: str = str(uuid.uuid4())
        self._subgraph_name: str = subgraph_name or "Untitled Subgraph"
        self._subgraph_path: Optional[str] = subgraph_path
        self._embedded_graph_data: Optional[Dict[str, Any]] = None

        # Reference-based architecture: workflow library is the source of truth
        self._is_reference_based: bool = False
        self._reference_version: Optional[str] = None
        # In-memory cache (NOT serialized) - used as fallback if file unavailable
        self._cached_graph_data: Optional[Dict[str, Any]] = None

        # Mappings between external ports and internal nodes
        self._input_mappings: Dict[str, str] = {}  # port_name -> SubgraphInput node ID
        self._output_mappings: Dict[str, str] = {}  # port_name -> SubgraphOutput node ID

        # Dynamic port definitions (name, type, description)
        self._dynamic_inputs: List[Dict[str, Any]] = []
        self._dynamic_outputs: List[Dict[str, Any]] = []

        # Flag to indicate if subgraph is loaded
        self._subgraph_loaded: bool = False

        super().__init__(node_id, name or "Subgraph", position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the subgraph node.

        The subgraph node always has:
        - An execution flow input port (exec_in)
        - An execution flow output port (exec_out)

        Additional data input/output ports are dynamically created based on
        the SubgraphInput and SubgraphOutput nodes within the embedded graph.
        """
        logger.debug(
            "SubgraphNode._setup_ports: Setting up ports for node id=%s, name=%s",
            self._id, self._name
        )

        # Execution flow input - triggers subgraph execution
        exec_in_port = InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input - triggers subgraph execution",
            required=False,
        )
        self.add_input_port(exec_in_port)
        logger.debug(
            "SubgraphNode._setup_ports: Added exec_in port, port.node=%s (expected=%s)",
            exec_in_port.node.id if exec_in_port.node else None, self._id
        )

        # Execution flow output - continues after subgraph completes
        exec_out_port = OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output - continues after subgraph completes",
        )
        self.add_output_port(exec_out_port)
        logger.debug(
            "SubgraphNode._setup_ports: Added exec_out port, port.node=%s (expected=%s)",
            exec_out_port.node.id if exec_out_port.node else None, self._id
        )

        # Add any dynamic ports that were defined before setup
        for input_def in self._dynamic_inputs:
            self._add_dynamic_input_port(
                input_def["name"],
                input_def.get("port_type", PortType.ANY),
                input_def.get("description", ""),
                input_def.get("default_value"),
            )

        for output_def in self._dynamic_outputs:
            self._add_dynamic_output_port(
                output_def["name"],
                output_def.get("port_type", PortType.ANY),
                output_def.get("description", ""),
            )

    def _add_dynamic_input_port(
        self,
        name: str,
        port_type: PortType = PortType.ANY,
        description: str = "",
        default_value: Any = None,
    ) -> None:
        """
        Add a dynamic input port to the subgraph node.

        Args:
            name: Name of the input port.
            port_type: Type of data the port accepts.
            description: Human-readable description.
            default_value: Default value if not connected.
        """
        logger.debug(
            "SubgraphNode._add_dynamic_input_port: Adding port '%s' to node id=%s, name=%s",
            name, self._id, self._name
        )

        # Don't add if port already exists
        if self.get_input_port(name) is not None:
            logger.debug(
                "SubgraphNode._add_dynamic_input_port: Port '%s' already exists, skipping",
                name
            )
            return

        port = InputPort(
            name=name,
            port_type=port_type,
            description=description or f"Subgraph input: {name}",
            required=False,
            default_value=default_value,
        )
        self.add_input_port(port)

        # Explicitly ensure port.node is set to this SubgraphNode
        # This is a defensive measure to guarantee the port references the correct node,
        # not an internal SubgraphInput/SubgraphOutput node from the embedded graph
        if port.node is not self:
            logger.warning(
                "SubgraphNode._add_dynamic_input_port: port.node was %s, expected %s. Fixing.",
                port.node.id if port.node else None,
                self._id
            )
            port.node = self

        # Verify port.node is correctly set after add_input_port
        logger.debug(
            "SubgraphNode._add_dynamic_input_port: Port '%s' added, port.node=%s (expected=%s), match=%s",
            name,
            port.node.id if port.node else None,
            self._id,
            port.node is self if port.node else False
        )

    def _add_dynamic_output_port(
        self,
        name: str,
        port_type: PortType = PortType.ANY,
        description: str = "",
    ) -> None:
        """
        Add a dynamic output port to the subgraph node.

        Args:
            name: Name of the output port.
            port_type: Type of data the port produces.
            description: Human-readable description.
        """
        logger.debug(
            "SubgraphNode._add_dynamic_output_port: Adding port '%s' to node id=%s, name=%s",
            name, self._id, self._name
        )

        # Don't add if port already exists
        if self.get_output_port(name) is not None:
            logger.debug(
                "SubgraphNode._add_dynamic_output_port: Port '%s' already exists, skipping",
                name
            )
            return

        port = OutputPort(
            name=name,
            port_type=port_type,
            description=description or f"Subgraph output: {name}",
        )
        self.add_output_port(port)

        # Explicitly ensure port.node is set to this SubgraphNode
        # This is a defensive measure to guarantee the port references the correct node,
        # not an internal SubgraphInput/SubgraphOutput node from the embedded graph
        if port.node is not self:
            logger.warning(
                "SubgraphNode._add_dynamic_output_port: port.node was %s, expected %s. Fixing.",
                port.node.id if port.node else None,
                self._id
            )
            port.node = self

        # Verify port.node is correctly set after add_output_port
        logger.debug(
            "SubgraphNode._add_dynamic_output_port: Port '%s' added, port.node=%s (expected=%s), match=%s",
            name,
            port.node.id if port.node else None,
            self._id,
            port.node is self if port.node else False
        )

    # Properties
    @property
    def subgraph_id(self) -> str:
        """Get the unique identifier for the subgraph definition."""
        return self._subgraph_id

    @property
    def subgraph_name(self) -> str:
        """Get the name of the subgraph."""
        return self._subgraph_name

    @subgraph_name.setter
    def subgraph_name(self, value: str) -> None:
        """Set the name of the subgraph."""
        self._subgraph_name = value

    @property
    def subgraph_path(self) -> Optional[str]:
        """Get the path to the external subgraph file, if any."""
        return self._subgraph_path

    @subgraph_path.setter
    def subgraph_path(self, value: Optional[str]) -> None:
        """Set the path to the external subgraph file."""
        self._subgraph_path = value

    @property
    def embedded_graph_data(self) -> Optional[Dict[str, Any]]:
        """Get the embedded graph data, if any."""
        return self._embedded_graph_data

    @property
    def input_mappings(self) -> Dict[str, str]:
        """Get a copy of the input port to internal node mappings."""
        return self._input_mappings.copy()

    @property
    def output_mappings(self) -> Dict[str, str]:
        """Get a copy of the output port to internal node mappings."""
        return self._output_mappings.copy()

    @property
    def is_subgraph_loaded(self) -> bool:
        """Check if a subgraph definition has been loaded."""
        return self._subgraph_loaded

    @property
    def is_reference_based(self) -> bool:
        """Check if this node references a workflow library file."""
        return self._is_reference_based

    @property
    def reference_version(self) -> Optional[str]:
        """Get the last-known version of the referenced workflow."""
        return self._reference_version

    @property
    def is_reference_broken(self) -> bool:
        """Check if the referenced library file is missing."""
        if not self._is_reference_based or not self._subgraph_path:
            return False
        return not os.path.exists(self._subgraph_path)

    def sync_ports_from_graph(self) -> None:
        """
        Synchronize dynamic ports using the existing mappings and embedded graph data.

        This method creates dynamic input/output ports based on the pre-configured
        `_input_mappings` and `_output_mappings` attributes. It's intended to be called
        after the mappings and embedded graph data have been set directly on the node
        (e.g., during subworkflow creation).

        Unlike `load_subgraph_from_data()`, which parses graph data to extract mappings
        from SubgraphInput/SubgraphOutput nodes, this method uses the mappings that
        have already been configured on the node instance.

        The method will:
        1. Look up port type information from the embedded graph data if available
        2. Create dynamic input ports for each entry in `_input_mappings`
        3. Create dynamic output ports for each entry in `_output_mappings`
        """
        logger.debug(
            "SubgraphNode.sync_ports_from_graph: Syncing ports for node id=%s, name=%s, "
            "input_mappings=%s, output_mappings=%s",
            self._id, self._name, list(self._input_mappings.keys()),
            list(self._output_mappings.keys())
        )

        # Build a lookup of node properties from embedded graph data
        node_properties: Dict[str, Dict[str, Any]] = {}
        if self._embedded_graph_data:
            for node_data in self._embedded_graph_data.get("nodes", []):
                node_id = node_data.get("id")
                if node_id:
                    node_properties[node_id] = node_data.get("properties", {})

        # Create dynamic input ports based on existing mappings
        for port_name, internal_node_id in self._input_mappings.items():
            # Skip if port already exists
            if self.get_input_port(port_name) is not None:
                continue

            # Try to get port type from the node properties
            props = node_properties.get(internal_node_id, {})
            port_type_str = props.get("port_type", "ANY")
            description = props.get("description", "")
            default_value = props.get("default_value")

            try:
                port_type = PortType[port_type_str]
            except KeyError:
                port_type = PortType.ANY

            self._dynamic_inputs.append({
                "name": port_name,
                "port_type": port_type,
                "description": description,
                "default_value": default_value,
            })
            self._add_dynamic_input_port(port_name, port_type, description, default_value)

        # Create dynamic output ports based on existing mappings
        for port_name, internal_node_id in self._output_mappings.items():
            # Skip if port already exists
            if self.get_output_port(port_name) is not None:
                continue

            # Try to get port type from the node properties
            props = node_properties.get(internal_node_id, {})
            port_type_str = props.get("port_type", "ANY")
            description = props.get("description", "")

            try:
                port_type = PortType[port_type_str]
            except KeyError:
                port_type = PortType.ANY

            self._dynamic_outputs.append({
                "name": port_name,
                "port_type": port_type,
                "description": description,
            })
            self._add_dynamic_output_port(port_name, port_type, description)

        # Verify and fix port.node references after syncing all ports
        # This is critical to ensure connections work correctly - port.node must
        # reference this SubgraphNode, not any internal SubgraphInput/SubgraphOutput nodes
        self._verify_and_fix_port_node_references()

        # Log final port state after syncing
        logger.debug(
            "SubgraphNode.sync_ports_from_graph: Finished syncing. "
            "input_ports=%s, output_ports=%s",
            [p.name for p in self.input_ports],
            [p.name for p in self.output_ports]
        )

    def load_subgraph_from_data(self, graph_data: Dict[str, Any]) -> None:
        """
        Load a subgraph from graph data (embedded or deserialized).

        This method parses the graph data and creates dynamic ports based on
        SubgraphInput and SubgraphOutput nodes found within.

        Args:
            graph_data: Dictionary containing serialized graph data.
        """
        logger.debug(
            "SubgraphNode.load_subgraph_from_data: Loading subgraph for node id=%s, name=%s",
            self._id, self._name
        )

        self._embedded_graph_data = graph_data
        self._subgraph_loaded = True

        # Clear existing dynamic ports and mappings
        self._clear_dynamic_ports()

        # Extract input/output nodes from the graph data
        nodes = graph_data.get("nodes", [])
        logger.debug(
            "SubgraphNode.load_subgraph_from_data: Found %d nodes in graph data",
            len(nodes)
        )

        for node_data in nodes:
            node_type = node_data.get("type")
            node_id = node_data.get("id")
            properties = node_data.get("properties", {})

            if node_type == "subgraph_input":
                # Create input port from SubgraphInput node
                port_name = properties.get("port_name", f"input_{len(self._input_mappings)}")
                port_type_str = properties.get("port_type", "ANY")
                description = properties.get("description", "")
                default_value = properties.get("default_value")

                logger.debug(
                    "SubgraphNode.load_subgraph_from_data: Found SubgraphInput node_id=%s, "
                    "creating port '%s' (internal_node_id=%s)",
                    node_id, port_name, node_id
                )

                try:
                    port_type = PortType[port_type_str]
                except KeyError:
                    port_type = PortType.ANY

                self._dynamic_inputs.append({
                    "name": port_name,
                    "port_type": port_type,
                    "description": description,
                    "default_value": default_value,
                })
                self._add_dynamic_input_port(port_name, port_type, description, default_value)
                self._input_mappings[port_name] = node_id

            elif node_type == "subgraph_output":
                # Create output port from SubgraphOutput node
                port_name = properties.get("port_name", f"output_{len(self._output_mappings)}")
                port_type_str = properties.get("port_type", "ANY")
                description = properties.get("description", "")

                logger.debug(
                    "SubgraphNode.load_subgraph_from_data: Found SubgraphOutput node_id=%s, "
                    "creating port '%s' (internal_node_id=%s)",
                    node_id, port_name, node_id
                )

                try:
                    port_type = PortType[port_type_str]
                except KeyError:
                    port_type = PortType.ANY

                self._dynamic_outputs.append({
                    "name": port_name,
                    "port_type": port_type,
                    "description": description,
                })
                self._add_dynamic_output_port(port_name, port_type, description)
                self._output_mappings[port_name] = node_id

        # Update subgraph name from metadata if available
        metadata = graph_data.get("metadata", {})
        if metadata.get("name"):
            self._subgraph_name = metadata["name"]

        # Verify and fix port.node references after loading all ports from data
        # This is critical to ensure connections work correctly - port.node must
        # reference this SubgraphNode, not any internal SubgraphInput/SubgraphOutput nodes
        # from the embedded graph data. While _add_dynamic_input_port and _add_dynamic_output_port
        # should set port.node correctly via add_input_port/add_output_port, this provides
        # an additional safety net for any edge cases.
        self._verify_and_fix_port_node_references()

        # Log final port state after loading
        logger.debug(
            "SubgraphNode.load_subgraph_from_data: Finished loading. "
            "input_ports=%s, output_ports=%s",
            [p.name for p in self.input_ports],
            [p.name for p in self.output_ports]
        )
        for port in self.input_ports:
            logger.debug(
                "SubgraphNode.load_subgraph_from_data: Input port '%s' node=%s (expected=%s)",
                port.name, port.node.id if port.node else None, self._id
            )
        for port in self.output_ports:
            logger.debug(
                "SubgraphNode.load_subgraph_from_data: Output port '%s' node=%s (expected=%s)",
                port.name, port.node.id if port.node else None, self._id
            )

    def load_subgraph_from_file(self, file_path: str) -> None:
        """
        Load a subgraph from an external file.

        Args:
            file_path: Path to the subgraph file (.vpy or .vns).

        Raises:
            FileNotFoundError: If the file doesn't exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Handle wrapped format (like library/project files)
        if "graph" in data:
            graph_data = data["graph"]
        elif "subgraph" in data:
            graph_data = data["subgraph"]
        else:
            graph_data = data

        self._subgraph_path = file_path
        self.load_subgraph_from_data(graph_data)

    def _clear_dynamic_ports(self) -> None:
        """Remove all dynamic input/output ports (keeping exec_in/exec_out)."""
        # Remove dynamic input ports
        for port_name in list(self._input_mappings.keys()):
            self.remove_input_port(port_name)

        # Remove dynamic output ports
        for port_name in list(self._output_mappings.keys()):
            self.remove_output_port(port_name)

        self._input_mappings.clear()
        self._output_mappings.clear()
        self._dynamic_inputs.clear()
        self._dynamic_outputs.clear()

    def add_input_definition(
        self,
        name: str,
        port_type: PortType = PortType.ANY,
        description: str = "",
        default_value: Any = None,
        internal_node_id: Optional[str] = None,
    ) -> None:
        """
        Add an input definition to the subgraph.

        This is used when manually defining subgraph interfaces.

        Args:
            name: Name of the input.
            port_type: Type of data the input accepts.
            description: Human-readable description.
            default_value: Default value if not connected.
            internal_node_id: ID of the internal SubgraphInput node, if known.
        """
        self._dynamic_inputs.append({
            "name": name,
            "port_type": port_type,
            "description": description,
            "default_value": default_value,
        })
        self._add_dynamic_input_port(name, port_type, description, default_value)

        if internal_node_id:
            self._input_mappings[name] = internal_node_id

    def add_output_definition(
        self,
        name: str,
        port_type: PortType = PortType.ANY,
        description: str = "",
        internal_node_id: Optional[str] = None,
    ) -> None:
        """
        Add an output definition to the subgraph.

        This is used when manually defining subgraph interfaces.

        Args:
            name: Name of the output.
            port_type: Type of data the output produces.
            description: Human-readable description.
            internal_node_id: ID of the internal SubgraphOutput node, if known.
        """
        self._dynamic_outputs.append({
            "name": name,
            "port_type": port_type,
            "description": description,
        })
        self._add_dynamic_output_port(name, port_type, description)

        if internal_node_id:
            self._output_mappings[name] = internal_node_id

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        if self._is_reference_based:
            # Reference-based: validate file reference
            if not self._subgraph_path:
                errors.append("Reference-based subgraph has no library path specified")
            elif not os.path.exists(self._subgraph_path):
                errors.append(
                    f"Referenced workflow file not found: {self._subgraph_path}"
                )
        else:
            # Legacy embedded: check if subgraph is loaded
            if not self._subgraph_loaded:
                if not self._subgraph_path:
                    errors.append("Subgraph has no definition loaded and no file path specified")

            # Validate that embedded data has at least one input, output, or flow entry point
            if self._embedded_graph_data:
                metadata = self._embedded_graph_data.get("metadata", {})
                has_flow_entries = bool(metadata.get("flow_entry_points"))
                has_data_ports = bool(self._input_mappings or self._output_mappings)
                has_internal_nodes = bool(self._embedded_graph_data.get("nodes"))
                if not has_data_ports and not has_flow_entries and not has_internal_nodes:
                    errors.append(
                        "Subgraph has no inputs or outputs defined. "
                        "Add SubgraphInput and/or SubgraphOutput nodes to the subgraph."
                    )

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the subgraph with the given inputs.

        During actual execution, this method returns placeholder outputs.
        The real execution is handled by the execution engine which
        instantiates and runs the internal graph.

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing output port values and exec_out signal.
        """
        # The actual subgraph execution is handled by the execution engine
        # This method provides a placeholder for direct node execution
        outputs: Dict[str, Any] = {"exec_out": None}

        # Pass through any input values as outputs (for testing)
        for port_name in self._output_mappings:
            outputs[port_name] = None

        return outputs

    def get_internal_graph_data(self) -> Optional[Dict[str, Any]]:
        """
        Get the internal graph data for execution or code generation.

        For reference-based nodes, reads from the library file.
        For legacy embedded nodes, returns the embedded data.

        Returns:
            The graph data, or None if not available.
        """
        if self._is_reference_based and self._subgraph_path:
            return self._load_from_library_file()
        return self._embedded_graph_data

    def _load_from_library_file(self) -> Optional[Dict[str, Any]]:
        """
        Load graph data from the referenced library file.

        Uses an in-memory cache as fallback if the file cannot be read.

        Returns:
            The graph data dict, or None if unavailable.
        """
        if not self._subgraph_path:
            return None

        try:
            with open(self._subgraph_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Handle wrapped format (project/library files)
            if "graph" in data:
                graph_data = data["graph"]
            elif "subgraph" in data:
                graph_data = data["subgraph"]
            else:
                graph_data = data

            # Update cache
            self._cached_graph_data = graph_data
            return graph_data
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.warning(
                "SubgraphNode._load_from_library_file: Failed to load '%s': %s",
                self._subgraph_path, e
            )
            return self._cached_graph_data

    def check_version_changed(self) -> tuple:
        """
        Check if the referenced workflow file has a newer version.

        Returns:
            Tuple of (has_changed: bool, new_version: Optional[str]).
        """
        if not self._is_reference_based or not self._subgraph_path:
            return False, None

        try:
            with open(self._subgraph_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "graph" in data:
                graph_data = data["graph"]
            elif "subgraph" in data:
                graph_data = data["subgraph"]
            else:
                graph_data = data

            file_version = graph_data.get("metadata", {}).get("version", "1.0.0")

            if file_version != self._reference_version:
                return True, file_version
            return False, None
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            logger.warning("Failed to check subgraph version", exc_info=True)
            return False, None

    def refresh_from_reference(self) -> bool:
        """
        Refresh ports and metadata from the referenced library file.

        Called when a version change is detected. Re-parses the library
        file to update dynamic ports, mappings, and the subgraph name.

        Returns:
            True if successfully refreshed.
        """
        if not self._is_reference_based or not self._subgraph_path:
            return False

        graph_data = self._load_from_library_file()
        if graph_data is None:
            return False

        # Clear and rebuild dynamic ports from the updated file
        self._clear_dynamic_ports()

        nodes = graph_data.get("nodes", [])
        for node_data in nodes:
            node_type = node_data.get("type")
            node_id = node_data.get("id")
            properties = node_data.get("properties", {})

            if node_type == "subgraph_input":
                port_name = properties.get("port_name", f"input_{len(self._input_mappings)}")
                port_type_str = properties.get("port_type", "ANY")
                description = properties.get("description", "")
                default_value = properties.get("default_value")

                try:
                    port_type = PortType[port_type_str]
                except KeyError:
                    port_type = PortType.ANY

                self._dynamic_inputs.append({
                    "name": port_name,
                    "port_type": port_type,
                    "description": description,
                    "default_value": default_value,
                })
                self._add_dynamic_input_port(port_name, port_type, description, default_value)
                self._input_mappings[port_name] = node_id

            elif node_type == "subgraph_output":
                port_name = properties.get("port_name", f"output_{len(self._output_mappings)}")
                port_type_str = properties.get("port_type", "ANY")
                description = properties.get("description", "")

                try:
                    port_type = PortType[port_type_str]
                except KeyError:
                    port_type = PortType.ANY

                self._dynamic_outputs.append({
                    "name": port_name,
                    "port_type": port_type,
                    "description": description,
                })
                self._add_dynamic_output_port(port_name, port_type, description)
                self._output_mappings[port_name] = node_id

        # Update version tracking and name
        metadata = graph_data.get("metadata", {})
        self._reference_version = metadata.get("version", "1.0.0")
        if metadata.get("name"):
            self._subgraph_name = metadata["name"]

        self._verify_and_fix_port_node_references()

        logger.info(
            "SubgraphNode.refresh_from_reference: Refreshed node id=%s from '%s' (version=%s)",
            self._id, self._subgraph_path, self._reference_version
        )
        return True

    @classmethod
    def create_reference(
        cls,
        library_path: str,
        name: Optional[str] = None,
        node_id: Optional[str] = None,
        position: Optional[Position] = None,
    ) -> "SubgraphNode":
        """
        Create a SubgraphNode that references a workflow library file.

        Args:
            library_path: Absolute path to the .vpy library file.
            name: Display name. If None, derived from file metadata.
            node_id: Optional node ID.
            position: Optional position.

        Returns:
            A new reference-based SubgraphNode.
        """
        node = cls(
            node_id=node_id,
            name=name or "Subgraph",
            position=position,
            subgraph_path=library_path,
        )
        node._is_reference_based = True

        # Load initial data to set up ports
        graph_data = node._load_from_library_file()
        if graph_data:
            node.load_subgraph_from_data(graph_data)
            node._reference_version = graph_data.get("metadata", {}).get("version", "1.0.0")
            # Clear embedded data - reference-based nodes don't store copies
            node._embedded_graph_data = None

        node._subgraph_loaded = True
        return node

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get subgraph-specific properties for serialization.

        Returns:
            Dictionary of serializable properties.
        """
        properties: Dict[str, Any] = {
            "subgraph_id": self._subgraph_id,
            "subgraph_name": self._subgraph_name,
            "input_mappings": self._input_mappings.copy(),
            "output_mappings": self._output_mappings.copy(),
            "dynamic_inputs": [
                {
                    "name": inp["name"],
                    "port_type": inp["port_type"].name if isinstance(inp["port_type"], PortType) else inp["port_type"],
                    "description": inp.get("description", ""),
                    "default_value": inp.get("default_value"),
                }
                for inp in self._dynamic_inputs
            ],
            "dynamic_outputs": [
                {
                    "name": out["name"],
                    "port_type": out["port_type"].name if isinstance(out["port_type"], PortType) else out["port_type"],
                    "description": out.get("description", ""),
                }
                for out in self._dynamic_outputs
            ],
            "is_reference_based": self._is_reference_based,
        }

        if self._is_reference_based:
            # Reference-based: store only path and version (no embedded data)
            if self._subgraph_path:
                properties["subgraph_path"] = self._subgraph_path
            if self._reference_version:
                properties["reference_version"] = self._reference_version
        else:
            # Legacy embedded: include everything for backward compatibility
            if self._subgraph_path:
                properties["subgraph_path"] = self._subgraph_path
            if self._embedded_graph_data:
                properties["embedded_graph_data"] = self._embedded_graph_data

        return properties

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load subgraph-specific properties from serialized data.

        Args:
            properties: Dictionary of serialized properties.
        """
        logger.debug(
            "SubgraphNode._load_serializable_properties: Loading properties for node id=%s",
            self._id
        )

        self._subgraph_id = properties.get("subgraph_id", str(uuid.uuid4()))
        self._subgraph_name = properties.get("subgraph_name", "Untitled Subgraph")
        self._subgraph_path = properties.get("subgraph_path")
        self._input_mappings = properties.get("input_mappings", {}).copy()
        self._output_mappings = properties.get("output_mappings", {}).copy()

        logger.debug(
            "SubgraphNode._load_serializable_properties: Loaded mappings - "
            "input_mappings=%s, output_mappings=%s",
            list(self._input_mappings.keys()), list(self._output_mappings.keys())
        )

        # Restore dynamic input definitions
        self._dynamic_inputs = []
        for inp_data in properties.get("dynamic_inputs", []):
            try:
                port_type = PortType[inp_data.get("port_type", "ANY")]
            except KeyError:
                port_type = PortType.ANY

            logger.debug(
                "SubgraphNode._load_serializable_properties: Restoring input port '%s'",
                inp_data["name"]
            )

            self._dynamic_inputs.append({
                "name": inp_data["name"],
                "port_type": port_type,
                "description": inp_data.get("description", ""),
                "default_value": inp_data.get("default_value"),
            })
            self._add_dynamic_input_port(
                inp_data["name"],
                port_type,
                inp_data.get("description", ""),
                inp_data.get("default_value"),
            )

        # Restore dynamic output definitions
        self._dynamic_outputs = []
        for out_data in properties.get("dynamic_outputs", []):
            try:
                port_type = PortType[out_data.get("port_type", "ANY")]
            except KeyError:
                port_type = PortType.ANY

            logger.debug(
                "SubgraphNode._load_serializable_properties: Restoring output port '%s'",
                out_data["name"]
            )

            self._dynamic_outputs.append({
                "name": out_data["name"],
                "port_type": port_type,
                "description": out_data.get("description", ""),
            })
            self._add_dynamic_output_port(
                out_data["name"],
                port_type,
                out_data.get("description", ""),
            )

        # Restore reference-based state
        self._is_reference_based = properties.get("is_reference_based", False)
        self._reference_version = properties.get("reference_version")

        if self._is_reference_based and self._subgraph_path:
            # Reference-based: load from library file
            try:
                graph_data = self._load_from_library_file()
                if graph_data:
                    self._subgraph_loaded = True
            except Exception:
                logger.warning(
                    "Failed to load referenced workflow from '%s'",
                    self._subgraph_path
                )
        elif "embedded_graph_data" in properties:
            # Legacy embedded
            self._embedded_graph_data = properties["embedded_graph_data"]
            self._subgraph_loaded = True
        elif self._subgraph_path:
            # Try to load from file path
            try:
                self.load_subgraph_from_file(self._subgraph_path)
            except (FileNotFoundError, json.JSONDecodeError):
                # File may not exist yet during deserialization
                logger.warning("Failed to load subgraph from file during deserialization", exc_info=True)
                pass

        # Verify and fix port.node references after restoring all ports
        # This is critical to ensure connections work correctly - port.node must
        # reference this SubgraphNode, not any internal SubgraphInput/SubgraphOutput nodes
        self._verify_and_fix_port_node_references()

    def _verify_and_fix_port_node_references(self) -> None:
        """
        Verify and fix port.node references for all ports on this SubgraphNode.

        This method ensures that all input and output ports have their `node` attribute
        correctly set to this SubgraphNode instance. This is critical for connection
        handling, as the connection code uses `port.node.id` to identify the target node.

        If any port has an incorrect or None node reference, it will be fixed and a
        warning will be logged. This can happen in certain deserialization scenarios
        or when ports are created/restored outside the normal add_input_port/add_output_port
        flow.
        """
        logger.debug(
            "SubgraphNode._verify_and_fix_port_node_references: Verifying ports for node id=%s",
            self._id
        )

        fixed_count = 0

        # Verify and fix input ports
        for port in self.input_ports:
            if port.node is not self:
                logger.warning(
                    "SubgraphNode._verify_and_fix_port_node_references: Input port '%s' had "
                    "incorrect node reference (was %s, expected %s). Fixing.",
                    port.name,
                    port.node.id if port.node else None,
                    self._id
                )
                port.node = self
                fixed_count += 1
            else:
                logger.debug(
                    "SubgraphNode._verify_and_fix_port_node_references: Input port '%s' "
                    "node reference OK (node=%s)",
                    port.name,
                    port.node.id if port.node else None
                )

        # Verify and fix output ports
        for port in self.output_ports:
            if port.node is not self:
                logger.warning(
                    "SubgraphNode._verify_and_fix_port_node_references: Output port '%s' had "
                    "incorrect node reference (was %s, expected %s). Fixing.",
                    port.name,
                    port.node.id if port.node else None,
                    self._id
                )
                port.node = self
                fixed_count += 1
            else:
                logger.debug(
                    "SubgraphNode._verify_and_fix_port_node_references: Output port '%s' "
                    "node reference OK (node=%s)",
                    port.name,
                    port.node.id if port.node else None
                )

        if fixed_count > 0:
            logger.info(
                "SubgraphNode._verify_and_fix_port_node_references: Fixed %d port(s) with "
                "incorrect node references on node id=%s",
                fixed_count,
                self._id
            )
        else:
            logger.debug(
                "SubgraphNode._verify_and_fix_port_node_references: All %d ports have correct "
                "node references on node id=%s",
                len(self.input_ports) + len(self.output_ports),
                self._id
            )

    def __repr__(self) -> str:
        """Get a detailed string representation of the subgraph node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"subgraph='{self._subgraph_name}', "
            f"inputs={len(self._input_mappings)}, "
            f"outputs={len(self._output_mappings)}, "
            f"state={self._execution_state.name})"
        )
