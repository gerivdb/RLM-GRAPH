"""Tests for RLM-GRAPH."""

from pathlib import Path

from src.graph_db import GraphDB, Node
from src.importers import import_known_repositories, import_bridges


def test_graph_db_roundtrip() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "test.duckdb"
    db = GraphDB(str(db_path))
    db.add_node(
        Node(
            node_id="gerivdb/RLM-GRAPH",
            kind="repo",
            label="RLM-GRAPH",
            layer="L2-PLATFORM",
            status="active",
            meta={"role": "test"},
        )
    )
    deps = db.get_dependencies("gerivdb/RLM-GRAPH")
    assert deps == []


def test_importers_bootstrap_governance_hub() -> None:
    db_path = Path(__file__).resolve().parent.parent / "data" / "test.duckdb"
    db = GraphDB(str(db_path))
    count = import_known_repositories(db)
    assert count > 0
