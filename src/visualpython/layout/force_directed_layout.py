"""
Force-directed layout algorithm for organic node arrangement.

This module implements a physics-based simulation where nodes repel each other
and edges act as springs, resulting in a natural-looking layout.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
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


@dataclass
class Vector2D:
    """Simple 2D vector for physics calculations."""

    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vector2D") -> "Vector2D":
        return Vector2D(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vector2D":
        return Vector2D(self.x * scalar, self.y * scalar)

    def __truediv__(self, scalar: float) -> "Vector2D":
        if scalar == 0:
            return Vector2D(0, 0)
        return Vector2D(self.x / scalar, self.y / scalar)

    def length(self) -> float:
        """Calculate the length/magnitude of the vector."""
        return math.sqrt(self.x * self.x + self.y * self.y)

    def normalized(self) -> "Vector2D":
        """Return a unit vector in the same direction."""
        length = self.length()
        if length == 0:
            return Vector2D(0, 0)
        return self / length


@dataclass
class NodeState:
    """State of a node during simulation."""

    node_id: str
    position: Vector2D
    velocity: Vector2D
    width: float
    height: float


class ForceDirectedLayout(LayoutAlgorithm):
    """
    Force-directed layout using a physics simulation.

    This algorithm treats nodes as charged particles that repel each other,
    and edges as springs that attract connected nodes. The simulation runs
    until it reaches equilibrium or the maximum number of iterations.

    This is useful for creating organic, aesthetically pleasing layouts
    especially for graphs with complex interconnections.
    """

    # Physics constants
    REPULSION_STRENGTH = 10000.0
    """Strength of repulsion between nodes (Coulomb's constant)."""

    ATTRACTION_STRENGTH = 0.1
    """Strength of spring attraction between connected nodes."""

    DAMPING = 0.9
    """Velocity damping to ensure convergence."""

    MIN_DISTANCE = 50.0
    """Minimum distance between nodes to prevent overlap."""

    CONVERGENCE_THRESHOLD = 0.5
    """Threshold for considering the simulation converged."""

    @property
    def name(self) -> str:
        """Get the name of this layout algorithm."""
        return "Force-Directed"

    @property
    def description(self) -> str:
        """Get a description of this layout algorithm."""
        return "Physics-based simulation for organic node arrangement"

    def calculate(self, graph: "Graph") -> LayoutResult:
        """
        Calculate force-directed layout positions for all nodes.

        Args:
            graph: The graph to calculate layout for.

        Returns:
            LayoutResult containing new positions for all nodes.
        """
        result = LayoutResult(algorithm_name=self.name)

        if graph.is_empty:
            return result

        nodes = graph.nodes
        connections = graph.connections

        # Initialize node states with random positions
        node_states = self._initialize_states(graph)

        # Run simulation
        for iteration in range(self._options.max_iterations):
            # Calculate forces
            forces = self._calculate_forces(node_states, connections)

            # Apply forces and update positions
            max_movement = self._apply_forces(node_states, forces)

            # Check for convergence
            if max_movement < self.CONVERGENCE_THRESHOLD:
                break

        # Convert to positions
        positions: Dict[str, NodePosition] = {}
        for node_id, state in node_states.items():
            x, y = self._snap_to_grid(state.position.x, state.position.y)
            positions[node_id] = NodePosition(node_id, x, y)

        # Center the layout
        positions = self._center_positions(positions)

        result.positions = positions
        result.calculate_bounds()
        result.success = True

        return result

    def _initialize_states(self, graph: "Graph") -> Dict[str, NodeState]:
        """
        Initialize node states with positions.

        Uses a smart initial layout based on graph structure.

        Args:
            graph: The graph to process.

        Returns:
            Dictionary mapping node ID to NodeState.
        """
        states: Dict[str, NodeState] = {}
        nodes = graph.nodes

        # Calculate spread based on number of nodes
        spread = math.sqrt(len(nodes)) * self._options.horizontal_spacing

        # Use execution levels for initial positioning if available
        execution_levels = graph.get_execution_levels()

        if execution_levels:
            # Place nodes based on execution level
            max_level = max(execution_levels.keys()) if execution_levels else 0

            for level, level_nodes in execution_levels.items():
                for i, node in enumerate(level_nodes):
                    # Horizontal position based on level
                    x = (level / max(max_level, 1)) * spread - spread / 2

                    # Vertical position spread within level
                    num_in_level = len(level_nodes)
                    y = ((i + 0.5) / num_in_level - 0.5) * spread

                    # Add some randomness
                    x += random.uniform(-20, 20)
                    y += random.uniform(-20, 20)

                    width, height = self._get_node_dimensions(node)

                    states[node.id] = NodeState(
                        node_id=node.id,
                        position=Vector2D(x, y),
                        velocity=Vector2D(0, 0),
                        width=width,
                        height=height,
                    )
        else:
            # Random initial positions in a circle
            for i, node in enumerate(nodes):
                angle = (2 * math.pi * i) / len(nodes)
                radius = spread / 2

                x = radius * math.cos(angle)
                y = radius * math.sin(angle)

                # Add randomness
                x += random.uniform(-50, 50)
                y += random.uniform(-50, 50)

                width, height = self._get_node_dimensions(node)

                states[node.id] = NodeState(
                    node_id=node.id,
                    position=Vector2D(x, y),
                    velocity=Vector2D(0, 0),
                    width=width,
                    height=height,
                )

        return states

    def _calculate_forces(
        self,
        states: Dict[str, NodeState],
        connections: List,
    ) -> Dict[str, Vector2D]:
        """
        Calculate net force on each node.

        Args:
            states: Current node states.
            connections: List of connections.

        Returns:
            Dictionary mapping node ID to force vector.
        """
        forces: Dict[str, Vector2D] = {
            node_id: Vector2D(0, 0) for node_id in states
        }

        # Repulsion forces between all pairs of nodes
        node_ids = list(states.keys())
        for i, node_id_1 in enumerate(node_ids):
            for node_id_2 in node_ids[i + 1:]:
                state_1 = states[node_id_1]
                state_2 = states[node_id_2]

                # Calculate direction and distance
                delta = state_1.position - state_2.position
                distance = delta.length()

                # Prevent division by zero and enforce minimum distance
                if distance < self.MIN_DISTANCE:
                    distance = self.MIN_DISTANCE
                    # Add slight randomness to separate overlapping nodes
                    delta = Vector2D(
                        random.uniform(-1, 1),
                        random.uniform(-1, 1),
                    )

                # Coulomb repulsion: F = k / d^2
                direction = delta.normalized()
                repulsion_force = self.REPULSION_STRENGTH / (distance * distance)
                force = direction * repulsion_force

                # Apply equal and opposite forces
                forces[node_id_1] = forces[node_id_1] + force
                forces[node_id_2] = forces[node_id_2] - force

        # Attraction forces along edges (spring forces)
        for conn in connections:
            source_id = conn.source_node_id
            target_id = conn.target_node_id

            if source_id not in states or target_id not in states:
                continue

            state_source = states[source_id]
            state_target = states[target_id]

            # Calculate direction and distance
            delta = state_target.position - state_source.position
            distance = delta.length()

            if distance < 1:
                continue

            # Hooke's law: F = k * d (linear spring)
            ideal_distance = self._options.horizontal_spacing
            displacement = distance - ideal_distance
            attraction_force = self.ATTRACTION_STRENGTH * displacement

            direction = delta.normalized()
            force = direction * attraction_force

            # Apply forces
            forces[source_id] = forces[source_id] + force
            forces[target_id] = forces[target_id] - force

        return forces

    def _apply_forces(
        self,
        states: Dict[str, NodeState],
        forces: Dict[str, Vector2D],
    ) -> float:
        """
        Apply forces to update node velocities and positions.

        Args:
            states: Current node states (modified in place).
            forces: Force vectors for each node.

        Returns:
            Maximum movement magnitude (for convergence checking).
        """
        max_movement = 0.0
        time_step = 0.5

        for node_id, state in states.items():
            force = forces.get(node_id, Vector2D(0, 0))

            # Update velocity (F = ma, assume m = 1)
            state.velocity = (state.velocity + force * time_step) * self.DAMPING

            # Limit velocity to prevent instability
            velocity_magnitude = state.velocity.length()
            max_velocity = 50.0
            if velocity_magnitude > max_velocity:
                state.velocity = state.velocity.normalized() * max_velocity

            # Update position
            movement = state.velocity * time_step
            state.position = state.position + movement

            # Track maximum movement
            movement_magnitude = movement.length()
            if movement_magnitude > max_movement:
                max_movement = movement_magnitude

        return max_movement
