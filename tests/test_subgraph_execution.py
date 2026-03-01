"""Tests for subgraph creation and execution."""

from __future__ import annotations

import io
import json
import sys

import pytest

from visualpython.graph.graph import Graph
from visualpython.nodes.models.base_node import Position
from visualpython.nodes.models.start_node import StartNode
from visualpython.nodes.models.print_node import PrintNode
from visualpython.nodes.models.subgraph_node import SubgraphNode
from visualpython.nodes.registry import NodeRegistry, get_node_registry
from visualpython.execution.engine import ExecutionEngine
from visualpython.execution.context import ExecutionStatus


@pytest.fixture(autouse=True)
def _ensure_registry():
    """Make sure the node registry has default nodes registered."""
    registry = get_node_registry()
    if not registry.get_all_node_types():
        registry.register_default_nodes()


# ── Test 1: Subgraph executes internal nodes ────────────────────────────


def test_subgraph_executes_internal_nodes():
    """A SubgraphNode with embedded data and flow_entry_points should
    execute its internal Print node when the main graph runs."""

    # Internal print node that lives inside the subgraph
    internal_print_id = "internal_print_1"

    # Build embedded graph data for the SubgraphNode
    embedded_graph_data = {
        "nodes": [
            {
                "id": internal_print_id,
                "type": "print",
                "name": "Inner Print",
                "position": {"x": 0, "y": 0},
                "properties": {"message": "from_subgraph"},
            },
        ],
        "connections": [],
        "metadata": {
            "name": "TestSub",
            "flow_entry_points": [
                {"node_id": internal_print_id, "port_name": "exec_in"},
            ],
            "flow_exit_points": [],
        },
    }

    # Build the main graph: Start → SubgraphNode
    graph = Graph()

    start = StartNode(node_id="start_1", position=Position(0, 0))
    graph.add_node(start)

    subgraph = SubgraphNode(name="Test Sub")
    subgraph._embedded_graph_data = embedded_graph_data
    subgraph._subgraph_loaded = True
    subgraph.position = Position(200, 0)
    graph.add_node(subgraph)

    graph.connect(start.id, "exec_out", subgraph.id, "exec_in")

    # Capture stdout to verify the internal print runs
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured

    try:
        engine = ExecutionEngine(graph)
        result = engine.execute()
    finally:
        sys.stdout = old_stdout

    assert result.status == ExecutionStatus.COMPLETED, (
        f"Expected COMPLETED, got {result.status}: {result.error}"
    )
    assert "from_subgraph" in captured.getvalue()


# ── Test 2: Subgraph creation replaces nodes ─────────────────────────────


def test_subgraph_creation_replaces_nodes(app_setup, qtbot):
    """'From Selection' should remove the original nodes and insert a
    connected SubgraphNode in their place."""

    window, controller = app_setup
    graph = controller._graph

    # Identify the print nodes added by the fixture
    print_nodes = [n for n in graph.nodes if n.node_type == "print"]
    assert len(print_nodes) == 2, "Fixture should create 2 print nodes"
    print_ids = [n.id for n in print_nodes]

    # Create subworkflow from the two print nodes
    controller._create_subworkflow_from_nodes(print_ids, "TestSub")

    # Original print nodes should be gone
    for pid in print_ids:
        assert graph.get_node(pid) is None, f"Print node {pid} should be removed"

    # A subgraph node should now exist
    subgraph_nodes = [n for n in graph.nodes if n.node_type == "subgraph"]
    assert len(subgraph_nodes) == 1, "Expected exactly one SubgraphNode"

    sg = subgraph_nodes[0]

    # The SubgraphNode should be reachable from the Start node
    start_nodes = graph.get_nodes_by_type("start")
    assert start_nodes, "Start node must still exist"

    start = start_nodes[0]
    exec_out_conns = graph.get_connections_for_port(
        start.id, "exec_out", is_input=False
    )
    target_ids = {c.target_node_id for c in exec_out_conns}
    assert sg.id in target_ids, (
        "SubgraphNode should be connected to Start's exec_out"
    )


# ── Test 3: Library save preserves flow metadata ─────────────────────────


def test_library_save_preserves_flow_metadata(app_setup, qtbot, tmp_path):
    """save_embedded_subgraph_to_library must keep flow_entry_points and
    flow_exit_points in the saved .vpy file."""

    window, _ = app_setup

    embedded_graph_data = {
        "nodes": [
            {
                "id": "p1",
                "type": "print",
                "name": "P1",
                "position": {"x": 0, "y": 0},
                "properties": {"message": "hello"},
            },
        ],
        "connections": [],
        "metadata": {
            "name": "MetadataTest",
            "flow_entry_points": [
                {"node_id": "p1", "port_name": "exec_in"},
            ],
            "flow_exit_points": [
                {"node_id": "p1", "port_name": "exec_out"},
            ],
        },
    }

    library = window.workflow_library

    # Point the library save path to a temp directory
    library._library_paths = [tmp_path]

    saved_path = library.save_embedded_subgraph_to_library(
        embedded_graph_data=embedded_graph_data,
        name="MetadataTest",
        description="test",
        silent=True,
    )

    assert saved_path is not None, "Library save should succeed"

    with open(saved_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    metadata = data["graph"]["metadata"]
    assert metadata["flow_entry_points"] == [
        {"node_id": "p1", "port_name": "exec_in"},
    ]
    assert metadata["flow_exit_points"] == [
        {"node_id": "p1", "port_name": "exec_out"},
    ]
