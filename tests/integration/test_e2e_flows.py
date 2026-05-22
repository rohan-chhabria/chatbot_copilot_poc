"""
End-to-End API Flow Tests — Validates complete user journeys.

Run: pytest tests/integration/test_e2e_flows.py -v
Requires: Redis running locally, SESSION_BACKEND=redis or memory
"""

import pytest
from fastapi.testclient import TestClient

from src.api.handler import app


@pytest.fixture(scope="module")
def client():
    """Test client with pipelines registered."""
    import src.pipelines.daily_activity  # noqa: F401
    import src.pipelines.inmate_data  # noqa: F401
    import src.pipelines.document_qa  # noqa: F401
    
    with TestClient(app) as c:
        yield c


class TestHealthEndpoints:
    """Health check validation."""

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_pipeline_health_inmate_data(self, client):
        resp = client.get("/pipelines/health/inmate_data")
        assert resp.status_code == 200

    def test_pipeline_health_document_qa(self, client):
        resp = client.get("/pipelines/health/document_qa")
        assert resp.status_code == 200

    def test_pipeline_health_daily_activity(self, client):
        resp = client.get("/pipelines/health/daily_activity")
        assert resp.status_code == 200

    def test_pipeline_health_invalid_scope(self, client):
        resp = client.get("/pipelines/health/invalid_scope")
        assert resp.status_code == 404


class TestNewSessionFlow:
    """New user session creation and scope selection."""

    def test_first_chat_creates_session(self, client):
        resp = client.post("/chat", json={
            "question": "hello",
            "customer_key": "demo",
            "user_id": "test.user",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "session_id" in data
        assert len(data["session_id"]) > 0

    def test_scope_options_returns_all_scopes(self, client):
        resp = client.get("/scope/options")
        assert resp.status_code == 200
        data = resp.json()
        assert "options" in data
        scope_ids = [o["id"] for o in data["options"]]
        assert "daily_activity" in scope_ids
        assert "inmate_data" in scope_ids
        assert "document_qa" in scope_ids

    def test_select_scope_returns_welcome(self, client):
        # Create session first
        create_resp = client.post("/chat", json={
            "question": "hi",
            "customer_key": "demo",
            "user_id": "test.scope",
        })
        session_id = create_resp.json()["session_id"]

        # Select scope
        resp = client.post("/scope/select", json={
            "session_id": session_id,
            "scope": "inmate_data",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["scope"] == "inmate_data"
        assert "summary" in data


class TestSessionExpiry:
    """Session expiration handling."""

    def test_expired_session_chat_returns_error(self, client):
        resp = client.post("/chat", json={
            "question": "test",
            "customer_key": "demo",
            "user_id": "test.user",
            "session_id": "nonexistent-session-id-12345",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "session_expired"

    def test_expired_session_scope_select_returns_404(self, client):
        resp = client.post("/scope/select", json={
            "session_id": "nonexistent-session-id-12345",
            "scope": "inmate_data",
        })
        assert resp.status_code == 404
        assert "session_expired" in resp.json()["detail"]


class TestCrossScopeHandlers:
    """Cross-scope message handling (greetings, help, recall)."""

    def test_greeting_returns_scope_options(self, client):
        resp = client.post("/chat", json={
            "question": "hello",
            "customer_key": "demo",
            "user_id": "test.greeting",
        })
        data = resp.json()
        assert data["success"] is True
        # Should prompt for scope or return greeting

    def test_help_request(self, client):
        # Create session with scope
        create_resp = client.post("/chat", json={
            "question": "hi",
            "customer_key": "demo",
            "user_id": "test.help",
        })
        session_id = create_resp.json()["session_id"]

        # Select scope
        client.post("/scope/select", json={
            "session_id": session_id,
            "scope": "inmate_data",
        })

        # Ask for help
        resp = client.post("/chat", json={
            "question": "what can you do?",
            "customer_key": "demo",
            "user_id": "test.help",
            "session_id": session_id,
        })
        data = resp.json()
        assert data["success"] is True
        assert len(data["summary"]) > 0


class TestInmateDataPipeline:
    """Inmate data pipeline basic validation."""

    @pytest.fixture
    def session_with_inmate_scope(self, client):
        """Create session and select inmate_data scope."""
        create_resp = client.post("/chat", json={
            "question": "hi",
            "customer_key": "demo",
            "user_id": "test.inmate",
        })
        session_id = create_resp.json()["session_id"]

        client.post("/scope/select", json={
            "session_id": session_id,
            "scope": "inmate_data",
        })
        return session_id

    def test_simple_query_returns_response(self, client, session_with_inmate_scope):
        resp = client.post("/chat", json={
            "question": "how many notes today?",
            "customer_key": "demo",
            "user_id": "test.inmate",
            "session_id": session_with_inmate_scope,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data


class TestDailyActivityPipeline:
    """Daily activity pipeline auto-execute validation."""

    def test_scope_select_auto_executes(self, client):
        # Create session
        create_resp = client.post("/chat", json={
            "question": "hi",
            "customer_key": "demo",
            "user_id": "test.daily",
            "facility_ids": [63],
        })
        session_id = create_resp.json()["session_id"]

        # Select daily_activity (should auto-execute)
        resp = client.post("/scope/select", json={
            "session_id": session_id,
            "scope": "daily_activity",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "daily_activity"
        # Auto-execute should add activity status to summary
        assert len(data["summary"]) > 0


class TestDocumentQAPipeline:
    """Document QA pipeline basic validation."""

    @pytest.fixture
    def session_with_doc_scope(self, client):
        """Create session and select document_qa scope."""
        create_resp = client.post("/chat", json={
            "question": "hi",
            "customer_key": "demo",
            "user_id": "test.docs",
        })
        session_id = create_resp.json()["session_id"]

        client.post("/scope/select", json={
            "session_id": session_id,
            "scope": "document_qa",
        })
        return session_id

    def test_doc_query_returns_response(self, client, session_with_doc_scope):
        resp = client.post("/chat", json={
            "question": "what is the fire drill procedure?",
            "customer_key": "demo",
            "user_id": "test.docs",
            "session_id": session_with_doc_scope,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data


class TestStreamingEndpoint:
    """SSE streaming endpoint validation."""

    def test_stream_returns_events(self, client):
        # Create session with scope
        create_resp = client.post("/chat", json={
            "question": "hi",
            "customer_key": "demo",
            "user_id": "test.stream",
        })
        session_id = create_resp.json()["session_id"]

        client.post("/scope/select", json={
            "session_id": session_id,
            "scope": "inmate_data",
        })

        # Stream request
        with client.stream("POST", "/chat/stream", json={
            "question": "hello",
            "customer_key": "demo",
            "user_id": "test.stream",
            "session_id": session_id,
        }) as resp:
            assert resp.status_code == 200
            # Should receive SSE events
            content = b""
            for chunk in resp.iter_bytes():
                content += chunk
            assert b"event:" in content or b"data:" in content


class TestSessionPersistence:
    """Session state persistence across requests."""

    def test_session_remembers_scope(self, client):
        # Create and set scope
        create_resp = client.post("/chat", json={
            "question": "hi",
            "customer_key": "demo",
            "user_id": "test.persist",
        })
        session_id = create_resp.json()["session_id"]

        client.post("/scope/select", json={
            "session_id": session_id,
            "scope": "inmate_data",
        })

        # Get session details
        resp = client.get(f"/session/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_scope"] == "inmate_data"

    def test_scope_switch_preserves_history(self, client):
        # Create session
        create_resp = client.post("/chat", json={
            "question": "hi",
            "customer_key": "demo",
            "user_id": "test.switch",
        })
        session_id = create_resp.json()["session_id"]

        # Select first scope
        client.post("/scope/select", json={
            "session_id": session_id,
            "scope": "inmate_data",
        })

        # Switch to second scope
        client.post("/scope/select", json={
            "session_id": session_id,
            "scope": "document_qa",
        })

        # Check scope history
        resp = client.get(f"/session/{session_id}")
        data = resp.json()
        assert "inmate_data" in data["scope_history"]
        assert "document_qa" in data["scope_history"]
