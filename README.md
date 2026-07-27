# RLM-GRAPH

Dependency & lineage graph for the gerivdb ecosystem.
Port: **8797**

## Endpoints

- `GET /health`
- `GET /metrics`
- `GET /vote`
- `GET /graph/deps/<repo_id>`
- `GET /graph/lineage/<artifact_id>`

## Bootstrap

Auto-imports from `known_repositories.yaml` and `BRIDGES.yaml` on first run.

## Stack

- Python 3.12
- Flask
- DuckDB
