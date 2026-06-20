"""Tests for the read-only workflow graph introspection endpoints."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_list_workflows_contains_registered_types():
    response = client.get("/workflows")
    assert response.status_code == 200
    workflows = response.json()["workflows"]
    assert "CUSTOMER_CARE" in workflows
    assert "CONTENT_PIPELINE" in workflows


def test_customer_care_graph_nodes_and_edges():
    response = client.get("/workflows/CUSTOMER_CARE/graph")
    assert response.status_code == 200
    body = response.json()

    assert set(body["nodes"]) == {
        "AnalyzeTicketNode",
        "TicketRouterNode",
        "GenerateResponseNode",
        "CloseTicketNode",
        "EscalateTicketNode",
        "ProcessInvoiceNode",
        "SendReplyNode",
    }

    assert {tuple(e) for e in body["edges"]} == {
        ("AnalyzeTicketNode", "TicketRouterNode"),
        ("TicketRouterNode", "CloseTicketNode"),
        ("TicketRouterNode", "EscalateTicketNode"),
        ("TicketRouterNode", "GenerateResponseNode"),
        ("TicketRouterNode", "ProcessInvoiceNode"),
        ("GenerateResponseNode", "SendReplyNode"),
    }


def test_unknown_workflow_type_returns_404():
    response = client.get("/workflows/NOPE/graph")
    assert response.status_code == 404
