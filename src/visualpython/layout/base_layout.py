"""
Base layout algorithm interface for automatic node arrangement.

This module defines the abstract base class and common data structures
that all layout algorithms must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph
    from visualpython.nodes.models.base_node import BaseNode


@dataclass
class NodePosition:
    """Represents a calculated position for a node."""

    node_id: str
    x: float
    y: float

    def to_dict(self) -> Dict[str, float]:
        """Convert position to dictionary."""
        return {"node_id": self.node_id, "x": self.x, "y": self.y}


@dataclass
class LayoutResult:
    """
    Result of a layout calculation.

    Contains the new positions for all nodes and metadata about the layout.
    """

    positions: Dict[str, NodePosition] = field(default_factory=dict)
    """Mapping of node ID to calculated position."""

    success: bool = True
    """Whether the layout calculation succeeded."""

    error_message: Optional[str] = None
    """Error message if layout failed."""

    bounds_width: float = 0.0
    """Width of the bounding box containing all nodes."""

    bounds_height: float = 0.0
    """Height of the bounding box containing all nodes."""

    algorithm_name: str = ""
    """Name of the algorithm used."""

    def get_position(self, node_id: str) -> Optional[NodePosition]:
        """Get the calculated position for a specific node."""
        return self.positions.get(node_id)

    def calculate_bounds(self) -> None:
        """Calculate the bounding box dimensions from positions."""
        if not self.positions:
            return

        min_x = min(pos.x for pos in self.positions.values())
        max_x = max(pos.x for pos in self.positions.values())
        min_y = min(pos.y for pos in self.positions.values())
        max_y = max(pos.y for pos in self.positions.values())

        self.bounds_width = max_x - min_x
        self.bounds_height = max_y - min_y


@dataclass
class LayoutOptions:
    """
    Configuration options for layout algorithms.

    These options allow customization of the layout behavior and appearance.
    """

    # Spacing options
    horizontal_spacing: float = 200.0
    """Horizontal spacing between nodes in the same level."""

    vertical_spacing: float = 100.0
    """Vertical spacing between different levels/layers."""

    margin: float = 50.0
    """Margin around the entire layout."""

    # Alignment options
    center_layout: bool = True
    """Whether to center the layout around the origin."""

    snap_to_grid: bool = True
    """Whether to snap final positions to the grid."""

    grid_size: float = 20.0
    """Grid size for snapping."""

    # Algorithm-specific options
    max_iterations: int = 100
    """Maximum iterations for iterative algorithms."""

    layout_direction: str = "horizontal"
    """Layout direction: 'horizontal' (left-to-right) or 'vertical' (top-to-bottom)."""


class LayoutAlgorithm(ABC):
    """
    Abstract base class for all layout algorithms.

    Subclasses must implement the calculate() method to provide
    specific layout logic.
    """

    def __init__(self, options: Optional[LayoutOptions] = None) -> None:
        """
        Initialize the layout algorithm.

        Args:
            options: Configuration options for the layout.
        """
        self._options = options or LayoutOptions()

    @property
    def options(self) -> LayoutOptions:
        """Get the layout options."""
        return self._options

    @options.setter
    def options(self, value: LayoutOptions) -> None:
        """Set the layout options."""
        self._options = value

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the name of this layout algorithm."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Get a description of this layout algorithm."""
        pass

    @abstractmethod
    def calculate(self, graph: "Graph") -> LayoutResult:
        """
        Calculate new positions for all nodes in the graph.

        Args:
            graph: The graph to calculate layout for.

        Returns:
            LayoutResult containing new positions for all nodes.
        """
        pass

    def _snap_to_grid(self, x: float, y: float) -> tuple[float, float]:
        """
        Snap coordinates to the grid.

        Args:
            x: X coordinate.
            y: Y coordinate.

        Returns:
            Tuple of snapped (x, y) coordinates.
        """
        if not self._options.snap_to_grid:
            return (x, y)

        grid = self._options.grid_size
        snapped_x = round(x / grid) * grid
        snapped_y = round(y / grid) * grid
        return (snapped_x, snapped_y)

    def _center_positions(
        self, positions: Dict[str, NodePosition]
    ) -> Dict[str, NodePosition]:
        """
        Center the positions around the origin.

        Args:
            positions: Dictionary of node positions.

        Returns:
            New dictionary with centered positions.
        """
        if not positions or not self._options.center_layout:
            return positions

        # Calculate center of current positions
        avg_x = sum(pos.x for pos in positions.values()) / len(positions)
        avg_y = sum(pos.y for pos in positions.values()) / len(positions)

        # Offset all positions to center around origin
        centered = {}
        for node_id, pos in positions.items():
            new_x = pos.x - avg_x
            new_y = pos.y - avg_y
            if self._options.snap_to_grid:
                new_x, new_y = self._snap_to_grid(new_x, new_y)
            centered[node_id] = NodePosition(node_id, new_x, new_y)

        return centered

    def _get_node_dimensions(self, node: "BaseNode") -> tuple[float, float]:
        """
        Estimate the dimensions of a node for layout purposes.

        Uses constants from NodeWidget for consistent sizing.

        Args:
            node: The node to get dimensions for.

        Returns:
            Tuple of (width, height).
        """
        # Default dimensions based on NodeWidget constants
        min_width = 150
        title_height = 28
        port_spacing = 24
        padding = 10

        # Estimate width (using minimum as conservative estimate)
        width = min_width

        # Calculate height based on ports
        num_input_ports = len(node.input_ports)
        num_output_ports = len(node.output_ports)
        max_ports = max(num_input_ports, num_output_ports, 1)
        body_height = max_ports * port_spacing + padding
        height = title_height + body_height

        return (width, height)
