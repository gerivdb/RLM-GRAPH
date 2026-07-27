"""Graph database schema and operations (SQLite/DuckDB)."""

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

import duckdb


@dataclass
class Node:
    node_id: str
    kind: str  # repo, artifact, run, release
    label: str
    layer: Optional[str] = None
    status: str = "active"
    meta: Optional[dict[str, Any]] = None
    created_at: str = ""


@dataclass
class Edge:
    src: str
    dst: str
    kind: str  # depends_on, lineage, triggers
    meta: Optional[dict[str, Any]] = None
    created_at: str = ""


class GraphDB:
    """Thin wrapper over DuckDB/SQLite for graph storage."""

    def __init__(self, db_path: str | Path = "graph.duckdb") -> None:
        self.db_path = str(db_path)
        self._local = threading.local()
        self._init_schema()

    def _conn(self) -> duckdb.DuckDBPyConnection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = duckdb.connect(self.db_path, read_only=False)
        return self._local.conn

    @contextmanager
    def transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    layer TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    meta TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    meta TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (src, dst, kind)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lineage (
                    artifact_id TEXT NOT NULL,
                    parent_artifact_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    meta TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (artifact_id, parent_artifact_id, relation)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dependencies (
                    repo_id TEXT NOT NULL,
                    depends_on TEXT NOT NULL,
                    constraint_type TEXT NOT NULL,
                    meta TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (repo_id, depends_on, constraint_type)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lineage_artifact ON lineage(artifact_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dependencies_repo ON dependencies(repo_id)"
            )

    def add_node(self, node: Node) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO nodes (node_id, kind, label, layer, status, meta, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.node_id,
                    node.kind,
                    node.label,
                    node.layer,
                    node.status,
                    __import__("json").dumps(node.meta or {}),
                    node.created_at or __import__("datetime").datetime.utcnow().isoformat(),
                ),
            )

    def add_edge(self, edge: Edge) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO edges (src, dst, kind, meta, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    edge.src,
                    edge.dst,
                    edge.kind,
                    __import__("json").dumps(edge.meta or {}),
                    edge.created_at or __import__("datetime").datetime.utcnow().isoformat(),
                ),
            )

    def get_dependencies(self, repo_id: str) -> list[dict[str, Any]]:
        with self.transaction() as conn:
                rows = conn.execute(
                    """
                    SELECT depends_on, constraint_type, meta, created_at
                    FROM dependencies
                    WHERE repo_id = ?
                    """,
                    (repo_id,),
                ).fetchall()
                return [
                    {
                        "repo": row[0],
                    "constraint_type": row[1],
                    "meta": __import__("json").loads(row[2] or "{}"),
                    "created_at": row[3],
                }
                for row in rows
            ]

    def get_lineage(self, artifact_id: str) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute(
                """
                SELECT parent_artifact_id, relation, meta, created_at
                FROM lineage
                WHERE artifact_id = ?
                """,
                (artifact_id,),
            ).fetchall()
            return [
                {
                    "parent": row[0],
                    "relation": row[1],
                    "meta": __import__("json").loads(row[2] or "{}"),
                    "created_at": row[3],
                }
                for row in rows
            ]

    def health(self) -> dict[str, Any]:
        try:
            with self.transaction() as conn:
                node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
                lineage_count = conn.execute(
                    "SELECT COUNT(*) FROM lineage"
                ).fetchone()[0]
                dep_count = conn.execute(
                    "SELECT COUNT(*) FROM dependencies"
                ).fetchone()[0]
            return {
                "status": "ok",
                "db_path": self.db_path,
                "nodes": node_count,
                "edges": edge_count,
                "lineage": lineage_count,
                "dependencies": dep_count,
                "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
