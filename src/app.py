"""Flask application for RLM-GRAPH."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from src.graph_db import GraphDB
from src.importers import import_known_repositories, import_bridges

app = Flask(__name__)

DB_PATH = os.environ.get("RLM_GRAPH_DB", str(Path(__file__).resolve().parent.parent / "data" / "graph.duckdb"))
db = GraphDB(DB_PATH)


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


def bootstrap() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    if db.health().get("nodes", 0) == 0:
        import_known_repositories(db)
        import_bridges(db)


if __name__ == "__main__":
    bootstrap()
    app.run(host="0.0.0.0", port=8797)
