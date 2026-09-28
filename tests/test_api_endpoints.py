import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.services.db import init_db

@pytest.fixture(autouse=True)
def setup_api_test(tmp_path):
    settings.database_path = tmp_path / "api_test.db"
    settings.trace_log_path = tmp_path / "api_traces.jsonl"
    settings.workflow_log_path = tmp_path / "api_workflow.jsonl"
    init_db()

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "restaurant-support-agent"

def test_get_order_details_success():
    response = client.get("/api/orders/ORD-1001", headers={"X-Customer-Id": "CUST-001"})
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == "ORD-1001"
    assert data["customer_id"] == "CUST-001"
    assert data["status"] == "delivered"

def test_get_order_details_unauthorized():
    # CUST-002 trying to fetch CUST-001's order ORD-1001
    response = client.get("/api/orders/ORD-1001", headers={"X-Customer-Id": "CUST-002"})
    assert response.status_code == 403

def test_get_order_status_success():
    response = client.get("/api/orders/ORD-1002/status", headers={"X-Customer-Id": "CUST-001"})
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == "ORD-1002"
    assert data["status"] == "out_for_delivery"

def test_create_and_list_tickets():
    # Create ticket
    payload = {
        "category": "Delivery",
        "priority": "Medium",
        "summary": "Driver took wrong turn and food arrived 10 mins late.",
        "order_id": "ORD-1002"
    }
    create_res = client.post("/api/support/tickets", json=payload, headers={"X-Customer-Id": "CUST-001"})
    assert create_res.status_code == 200
    ticket_data = create_res.json()
    assert ticket_data["ticket_id"].startswith("TCK-")
    assert ticket_data["customer_id"] == "CUST-001"

    # List tickets
    list_res = client.get("/api/support/tickets?customer_id=CUST-001")
    assert list_res.status_code == 200
    tickets = list_res.json()
    assert len(tickets) >= 1
    assert tickets[0]["ticket_id"] == ticket_data["ticket_id"]

def test_chat_endpoint_and_trace_retrieval():
    chat_payload = {
        "customer_id": "CUST-002",
        "message": "Where is my order ORD-1005?"
    }
    chat_res = client.post("/api/agent/chat", json=chat_payload, headers={"X-Customer-Id": "CUST-002"})
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert "reply" in chat_data
    assert "trace_id" in chat_data
    trace_id = chat_data["trace_id"]

    # Verify trace endpoint
    trace_res = client.get(f"/api/traces/{trace_id}")
    assert trace_res.status_code == 200
    trace_obj = trace_res.json()
    assert trace_obj["trace_id"] == trace_id
    assert trace_obj["success"] is True

def test_complaint_workflow_endpoint():
    wf_payload = {
        "customer_id": "CUST-003",
        "order_id": "ORD-1007",
        "complaint_text": "I was charged $32 but my order failed on payment gateway screen!"
    }
    wf_res = client.post("/api/workflows/complaint", json=wf_payload)
    assert wf_res.status_code == 200
    wf_data = wf_res.json()
    assert wf_data["computed_priority"] == "High"
    assert wf_data["ticket_id"].startswith("TCK-")
    assert wf_data["status"] == "completed"
