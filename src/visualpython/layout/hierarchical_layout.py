"""
Hierarchical (Sugiyama-style) layout algorithm for directed graphs.

This module implements a layered layout algorithm that arranges nodes
in levels based on their dependencies, with source nodes at the left/top
and sink nodes at the right/bottom.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, TYPE_CHECKING

from visualpython.layout.base_layout import (
    LayoutAlgorithm,
    LayoutOptions,
    LayoutResult,
    NodePosition,
)

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph
    from visualpython.nodes.models.base_node import BaseNode


class HierarchicalLayout(LayoutAlgorithm):
    """
    Hierarchical layout algorithm based on the Sugiyama method.

    This algorithm arranges nodes in layers based on their topological order,
    with edges flowing from left to right (or top to bottom). It's ideal for
    directed acyclic graphs (DAGs) like node-based programming graphs.

    The algorithm works in several phases:
    1. Layer assignment: Assign each node to a layer based on dependencies
    2. Ordering: Minimize edge crossings within each layer
    3. Positioning: Calculate final x, y coordinates
    """

    @property
    def name(self) -> str:
        """Get the name of this layout algorithm."""
        return "Hierarchical"

    @property
    def description(self) -> str:
        """Get a description of this layout algorithm."""
        return "Arranges nodes in layers based on data flow direction"

    def calculate(self, graph: "Graph") -> LayoutResult:
        """
        Calculate hierarchical layout positions for all nodes.

        Args:
            graph: The graph to calculate layout for.

        Returns:
            LayoutResult containing new positions for all nodes.
        """
        result = LayoutResult(algorithm_name=self.name)

        if graph.is_empty:
            return result

        nodes = graph.nodes

        # Handle disconnected nodes and graphs with cycles
        if graph.has_cycle():
            # Fall back to simple layout for graphs with cycles
            return self._simple_layout(graph, result)

        # Phase 1: Assign nodes to layers
        layers = self._assign_layers(graph)

        if not layers:
            # Fallback if layer assignment fails
            return self._simple_layout(graph, result)

        # Phase 2: Order nodes within layers to minimize crossings
        layers = self._order_layers(graph, layers)

        # Phase 3: Calculate positions
        positions = self._calculate_positions(graph, layers)

        # Center the layout
        positions = self._center_positions(positions)

        result.positions = positions
        result.calculate_bounds()
        result.success = True

        return result

    def _assign_layers(self, graph: "Graph") -> Dict[int, List[str]]:
        """
        Assign nodes to layers based on their longest path from source nodes.

        Args:
            graph: The graph to process.

        Returns:
            Dictionary mapping layer index to list of node IDs.
        """
        layers: Dict[int, List[str]] = defaultdict(list)

        # Use the graph's execution levels if available
        execution_levels = graph.get_execution_levels()

        if execution_levels:
            for level, nodes in execution_levels.items():
                for node in nodes:
                    layers[level].append(node.id)
            return dict(layers)

        # Fallback: Manual layer assignment using BFS from source nodes
        source_nodes = graph.get_source_nodes()
        if not source_nodes:
            # If no source nodes, use all nodes
            for i, node in enumerate(graph.nodes):
                layers[0].append(node.id)
            return dict(layers)

        # BFS to assign layers
        node_layer: Dict[str, int] = {}
        visited: Set[str] = set()
        queue: List[tuple[str, int]] = [(node.id, 0) for node in source_nodes]

        while queue:
            node_id, layer = queue.pop(0)

            if node_id in visited:
                # Update to maximum layer if already visited
                if node_id in node_layer and layer > node_layer[node_id]:
                    node_layer[node_id] = layer
                continue

            visited.add(node_id)
            node_layer[node_id] = max(node_layer.get(node_id, 0), layer)

            # Add connected nodes
            outgoing = graph.get_outgoing_connections(node_id)
            for conn in outgoing:
                if conn.target_node_id not in visited:
                    queue.append((conn.target_node_id, layer + 1))

        # Handle any unvisited nodes (disconnected)
        for node in graph.nodes:
            if node.id not in node_layer:
                node_layer[node.id] = 0

        # Build layers dictionary
        for node_id, layer in node_layer.items():
            layers[layer].append(node_id)

        return dict(layers)

    def _order_layers(
        self, graph: "Graph", layers: Dict[int, List[str]]
    ) -> Dict[int, List[str]]:
        """
        Order nodes within each layer to minimize edge crossings.

        Uses the barycenter heuristic for ordering.

        Args:
            graph: The graph to process.
            layers: Dictionary mapping layer index to node IDs.

        Returns:
            Reordered layers dictionary.
        """
        if not layers:
            return layers

        max_layer = max(layers.keys())

        # Multiple sweeps to improve ordering
        for _ in range(min(self._options.max_iterations, 10)):
            # Forward sweep (left to right)
            for layer_idx in range(1, max_layer + 1):
                if layer_idx not in layers:
                    continue
                layers[layer_idx] = self._order_layer_by_barycenter(
                    graph, layers, layer_idx, forward=True
                )

            # Backward sweep (right to left)
            for layer_idx in range(max_layer - 1, -1, -1):
                if layer_idx not in layers:
                    continue
                layers[layer_idx] = self._order_layer_by_barycenter(
                    graph, layers, layer_idx, forward=False
                )

        return layers

    def _order_layer_by_barycenter(
        self,
        graph: "Graph",
        layers: Dict[int, List[str]],
        layer_idx: int,
        forward: bool,
    ) -> List[str]:
        """
        Order a single layer using the barycenter heuristic.

        Args:
            graph: The graph to process.
            layers: Current layer assignments.
            layer_idx: The layer to order.
            forward: If True, use connections to previous layer; else next layer.

        Returns:
            Ordered list of node IDs for this layer.
        """
        current_layer = layers.get(layer_idx, [])
        if len(current_layer) <= 1:
            return current_layer

        # Get reference layer
        ref_layer_idx = layer_idx - 1 if forward else layer_idx + 1
        ref_layer = layers.get(ref_layer_idx, [])

        if not ref_layer:
            return current_layer

        # Create position lookup for reference layer
        ref_positions = {node_id: i for i, node_id in enumerate(ref_layer)}

        # Calculate barycenter for each node in current layer
        barycenters: Dict[str, float] = {}

        for node_id in current_layer:
            positions_sum = 0.0
            count = 0

            if forward:
                # Look at incoming connections from previous layer
                incoming = graph.get_incoming_connections(node_id)
                for conn in incoming:
                    if conn.source_node_id in ref_positions:
                        positions_sum += ref_positions[conn.source_node_id]
                        count += 1
            else:
                # Look at outgoing connections to next layer
                outgoing = graph.get_outgoing_connections(node_id)
                for conn in outgoing:
                    if conn.target_node_id in ref_positions:
                        positions_sum += ref_positions[conn.target_node_id]
                        count += 1

            if count > 0:
                barycenters[node_id] = positions_sum / count
            else:
                # Keep original position for unconnected nodes
                barycenters[node_id] = current_layer.index(node_id)

        # Sort by barycenter
        return sorted(current_layer, key=lambda n: barycenters.get(n, 0))

    def _calculate_positions(
        self, graph: "Graph", layers: Dict[int, List[str]]
    ) -> Dict[str, NodePosition]:
        """
        Calculate final x, y coordinates for all nodes.

        Args:
            graph: The graph to process.
            layers: Ordered layer assignments.

        Returns:
            Dictionary mapping node ID to calculated position.
        """
        positions: Dict[str, NodePosition] = {}

        if not layers:
            return positions

        h_spacing = self._options.horizontal_spacing
        v_spacing = self._options.vertical_spacing
        margin = self._options.margin
        is_horizontal = self._options.layout_direction == "horizontal"

        # Get node dimensions for centering within layers
        node_dims: Dict[str, tuple[float, float]] = {}
        for node in graph.nodes:
            node_dims[node.id] = self._get_node_dimensions(node)

        # Calculate layer positions
        max_layer = max(layers.keys()) if layers else 0

        for layer_idx in range(max_layer + 1):
            nodes_in_layer = layers.get(layer_idx, [])
            if not nodes_in_layer:
                continue

            # Calculate total height/width of this layer
            if is_horizontal:
                # Horizontal layout: x varies by layer, y varies within layer
                layer_x = margin + layer_idx * h_spacing

                # Calculate total height needed
                total_height = sum(
                    node_dims.get(nid, (150, 100))[1] for nid in nodes_in_layer
                )
                total_height += (len(nodes_in_layer) - 1) * v_spacing

                # Start y position (centered around 0)
                current_y = -total_height / 2

                for node_id in nodes_in_layer:
                    _, node_height = node_dims.get(node_id, (150, 100))

                    x, y = self._snap_to_grid(layer_x, current_y)
                    positions[node_id] = NodePosition(node_id, x, y)

                    current_y += node_height + v_spacing
            else:
                # Vertical layout: y varies by layer, x varies within layer
                layer_y = margin + layer_idx * v_spacing

                # Calculate total width needed
                total_width = sum(
                    node_dims.get(nid, (150, 100))[0] for nid in nodes_in_layer
                )
                total_width += (len(nodes_in_layer) - 1) * h_spacing

                # Start x position (centered around 0)
                current_x = -total_width / 2

                for node_id in nodes_in_layer:
                    node_width, _ = node_dims.get(node_id, (150, 100))

                    x, y = self._snap_to_grid(current_x, layer_y)
                    positions[node_id] = NodePosition(node_id, x, y)

                    current_x += node_width + h_spacing

        return positions

    def _simple_layout(
        self, graph: "Graph", result: LayoutResult
    ) -> LayoutResult:
        """
        Simple fallback layout for graphs with cycles or other issues.

        Arranges nodes in a grid pattern.

        Args:
            graph: The graph to process.
            result: The result object to populate.

        Returns:
            LayoutResult with simple grid positions.
        """
        nodes = graph.nodes
        if not nodes:
            return result

        h_spacing = self._options.horizontal_spacing
        v_spacing = self._options.vertical_spacing

        # Calculate grid dimensions
        num_nodes = len(nodes)
        cols = max(1, int(num_nodes ** 0.5))
        rows = (num_nodes + cols - 1) // cols

        positions: Dict[str, NodePosition] = {}

        for i, node in enumerate(nodes):
            col = i % cols
            row = i // cols

            x = col * h_spacing
            y = row * v_spacing

            x, y = self._snap_to_grid(x, y)
            positions[node.id] = NodePosition(node.id, x, y)

        result.positions = self._center_positions(positions)
        result.calculate_bounds()
        result.success = True

        return result
