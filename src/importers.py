"""Data importers from governance YAML files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.graph_db import GraphDB, Node, Edge


def _find_governance_hub() -> Path | None:
    """Best-effort discovery of the canonical GOVERNANCE-HUB checkout."""
    candidates = [
        Path(__file__).resolve().parents[2]
        / "L0-CANON"
        / "GOVERNANCE-HUB",
        Path(__file__).resolve().parents[3]
        / "L0-CANON"
        / "GOVERNANCE-HUB",
        Path(__file__).resolve().parents[4]
        / "GOVERNANCE-HUB",
    ]
    for candidate in candidates:
        if (candidate / "known_repositories.yaml").exists():
            return candidate
    return None


def import_known_repositories(db: GraphDB, hub_dir: Path | None = None) -> int:
    """Import nodes/edges from known_repositories.yaml.
    Returns number of nodes created.
    """
    if hub_dir is None:
        hub_dir = _find_governance_hub()
    if hub_dir is None:
        return 0

    repo_file = hub_dir / "known_repositories.yaml"
    if not repo_file.exists():
        return 0

    with open(repo_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    entries = []
    for section in data.values():
        if isinstance(section, list):
            entries.extend(section)

    count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        node_id = entry.get("full_name") or entry.get("name")
        if not node_id:
            continue
        db.add_node(
            Node(
                node_id=node_id,
                kind="repo",
                label=entry.get("name", node_id),
                layer=entry.get("layer"),
                status=entry.get("status", "active"),
                meta={
                    k: v
                    for k, v in entry.items()
                    if k not in {"name", "full_name", "layer", "status"}
                },
            )
        )
        count += 1

    return count


def import_bridges(db: GraphDB, hub_dir: Path | None = None) -> int:
    """Import dependency edges from BRIDGES.yaml.
    Returns number of edges created.
    """
    if hub_dir is None:
        hub_dir = _find_governance_hub()
    if hub_dir is None:
        return 0

    bridges_file = hub_dir / "BRIDGES.yaml"
    if not bridges_file.exists():
        return 0

    with open(bridges_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    edges: list[Edge] = []
    stack: list[tuple[str, dict[str, Any]]] = []

    def _walk(name: str, obj: Any) -> None:
        if isinstance(obj, dict):
            if "from" in obj and "to" in obj:
                edges.append(
                    Edge(
                        src=obj["from"],
                        dst=obj["to"],
                        kind=obj.get("kind", "depends_on"),
                        meta={
                            k: v
                            for k, v in obj.items()
                            if k not in {"from", "to", "kind"}
                        },
                    )
                )
            for key, value in obj.items():
                _walk(key, value)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    _walk(name, item)

    _walk("root", data)
    for edge in edges:
        db.add_edge(edge)
    return len(edges)
