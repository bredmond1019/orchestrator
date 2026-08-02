"""Tests for the read-only workflow graph introspection endpoints."""

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_list_workflows_contains_registered_types():
    response = client.get("/workflows")
    assert response.status_code == 200
    workflows = response.json()["workflows"]
    assert "MEMORY_INGEST" in workflows
    assert "DOCUMENT_INGEST" in workflows


def test_memory_ingest_graph_nodes_and_edges():
    response = client.get("/workflows/MEMORY_INGEST/graph")
    assert response.status_code == 200
    body = response.json()

    assert set(body["nodes"]) == {
        "IngestTimeExtractionNode",
        "MemoryWriteNode",
    }

    assert {tuple(e) for e in body["edges"]} == {
        ("IngestTimeExtractionNode", "MemoryWriteNode"),
    }


def test_unknown_workflow_type_returns_404():
    response = client.get("/workflows/NOPE/graph")
    assert response.status_code == 404
