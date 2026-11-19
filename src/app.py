"""Flask application for RLM-GRAPH."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is importable regardless of how this script is invoked
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from flask import Flask, jsonify, request

from src.graph_db import GraphDB
from src.importers import import_known_repositories, import_bridges

from rlm_common import (
    causal_validator,
    curriculum_validator,
    meta_coherence_fixer,
    narrative_generator,
    rootx_client,
)

app = Flask(__name__)

DB_PATH = os.environ.get("RLM_GRAPH_DB", str(Path(__file__).resolve().parent.parent / "data" / "graph.duckdb"))
db = GraphDB(DB_PATH)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health() -> Any:
    return jsonify(db.health())


@app.get("/metrics")
def metrics() -> Any:
    health = db.health()
    return jsonify(
        {
            "service": "rlm-graph",
            "port": 8797,
            "db": health,
            "nodes": health.get("nodes", 0),
            "edges": health.get("edges", 0),
        }
    )


@app.get("/vote")
def vote() -> Any:
    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT kind, COUNT(*) as total
            FROM nodes
            GROUP BY kind
            ORDER BY total DESC
            """
        ).fetchall()
    return jsonify(
        {
            "vote": "functional",
            "by_kind": [{"kind": r[0], "total": r[1]} for r in row],
        }
    )


@app.get("/graph/deps/<string:repo_id>")
def graph_deps(repo_id: str) -> Any:
    deps = db.get_dependencies(repo_id)
    if not deps:
        return jsonify({"repo": repo_id, "dependencies": [], "count": 0})
    return jsonify({"repo": repo_id, "dependencies": deps, "count": len(deps)})


@app.get("/graph/lineage/<string:artifact_id>")
def graph_lineage(artifact_id: str) -> Any:
    lineage = db.get_lineage(artifact_id)
    if not lineage:
        return jsonify(
            {"artifact": artifact_id, "lineage": [], "count": 0}
        )
    return jsonify(
        {"artifact": artifact_id, "lineage": lineage, "count": len(lineage)}
    )


# ==================== NEW ENDPOINTS FOR P2 ====================
@app.post("/graph/live")
def graph_live() -> Any:
    """
    Return a live view of the semantic graph with optional delta.
    Body format:
    {
        "service": "RLM-GRAPH",
        "delta": "t+1"  # optional time delta for projection
    }
    """
    data = request.get_json(silent=True) or {}
    service = data.get("service", "RLM-GRAPH")
    delta = data.get("delta", "t+0")
    
    try:
        # Get current graph state
        health = db.health()
        nodes_count = health.get("nodes", 0)
        edges_count = health.get("edges", 0)
        
        # Get all nodes with their kinds
        with db.transaction() as conn:
            nodes = conn.execute(
                """
                SELECT node_id, kind, label, meta
                FROM nodes
                ORDER BY kind, label
                """
            ).fetchall()
        
        # Build node list
        node_list = []
        for row in nodes:
            node_data = {
                "id": row[0],
                "kind": row[1],
                "label": row[2],
            }
            # Parse metadata if available
            if row[3]:
                try:
                    node_data["metadata"] = json.loads(row[3])
                except (json.JSONDecodeError, TypeError):
                    node_data["metadata"] = {}
            else:
                node_data["metadata"] = {}
            node_list.append(node_data)
        
        # Get edges
        with db.transaction() as conn:
            edges = conn.execute(
                """
                SELECT src, dst, kind, meta
                FROM edges
                """
            ).fetchall()
        
        edge_list = []
        for row in edges:
            edge_list.append({
                "source": row[0],
                "target": row[1],
                "type": row[2],
                "weight": 1.0
            })
        
        # Build adjacency map for quick lookup
        adjacency = {}
        for edge in edge_list:
            src = edge["source"]
            if src not in adjacency:
                adjacency[src] = []
            adjacency[src].append({
                "target": edge["target"],
                "type": edge["type"],
                "weight": edge["weight"]
            })
        
        # Compute projections based on delta
        projection = {
            "delta": delta,
            "nodes_projected": len(node_list),
            "edges_projected": len(edge_list),
            "layers": _compute_layers(node_list)
        }
        
        return jsonify({
            "service": service,
            "timestamp": _utcnow(),
            "delta": delta,
            "graph": {
                "nodes": node_list,
                "edges": edge_list,
                "adjacency": adjacency
            },
            "projection": projection,
            "stats": {
                "total_nodes": nodes_count,
                "total_edges": edges_count,
                "node_kinds": _count_by_kind(node_list),
                "edge_types": _count_by_edge_type(edge_list)
            }
        })
    except Exception as e:
        return jsonify({
            "service": service,
            "error": f"Internal server error: {str(e)}",
            "timestamp": _utcnow()
        }), 500


def _compute_layers(nodes: list[dict[str, Any]]) -> dict[str, int]:
    """Compute layer distribution from nodes."""
    layers = {}
    for node in nodes:
        kind = node.get("kind", "unknown")
        layers[kind] = layers.get(kind, 0) + 1
    return layers


def _count_by_kind(nodes: list[dict[str, Any]]) -> dict[str, int]:
    """Count nodes by kind."""
    counts = {}
    for node in nodes:
        kind = node.get("kind", "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _count_by_edge_type(edges: list[dict[str, Any]]) -> dict[str, int]:
    """Count edges by type."""
    counts = {}
    for edge in edges:
        etype = edge.get("type", "unknown")
        counts[etype] = counts.get(etype, 0) + 1
    return counts


@app.get("/graph/live")
def graph_live_get() -> Any:
    """GET variant of /graph/live for simple polling."""
    # Handle GET request with optional query parameters
    service = request.args.get("service", "RLM-GRAPH")
    delta = request.args.get("delta", "t+0")
    
    # Use the same logic as POST for consistency
    return graph_live()


def bootstrap() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    if db.health().get("nodes", 0) == 0:
        import_known_repositories(db)
        import_bridges(db)


if __name__ == "__main__":
    bootstrap()
    app.run(host="0.0.0.0", port=8797)
