"""Integration tests for API endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.handler import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_health_has_environment(self, client):
        response = client.get("/health")
        data = response.json()
        assert "environment" in data


class TestChatEndpoint:
    @patch("src.api.routes._get_state_machine")
    @patch("src.api.routes._get_session_store")
    def test_chat_creates_session(self, mock_store_fn, mock_sm_fn, client):
        mock_store = MagicMock()
        mock_store.get.return_value = None
        mock_store_fn.return_value = mock_store

        mock_sm = MagicMock()
        mock_sm.handle_message = AsyncMock(return_value={
            "summary": "Found 10 records.",
            "data": [{"notes_id": 1}],
            "row_count": 10,
            "scope": "inmate_data",
        })
        mock_sm_fn.return_value = mock_sm

        response = client.post("/chat", json={
            "question": "How many inmates are active?",
            "customer_key": "demo",
            "user_id": "Test.Officer",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "session_id" in data
        assert data["row_count"] == 10

    @patch("src.api.routes._get_state_machine")
    @patch("src.api.routes._get_session_store")
    def test_chat_resumes_session(self, mock_store_fn, mock_sm_fn, client, session):
        mock_store = MagicMock()
        mock_store.get.return_value = session
        mock_store_fn.return_value = mock_store

        mock_sm = MagicMock()
        mock_sm.handle_message = AsyncMock(return_value={
            "summary": "5 records.",
            "data": [],
            "row_count": 5,
            "scope": "inmate_data",
        })
        mock_sm_fn.return_value = mock_sm

        response = client.post("/chat", json={
            "question": "Show more details",
            "customer_key": "demo",
            "user_id": "Test.Officer",
            "session_id": session.session_id,
        })

        assert response.status_code == 200
        mock_store.get.assert_called_with(session.session_id)

    def test_chat_with_nonexistent_tenant(self, client):
        # V2 no longer validates tenant in /chat; it's handled per-pipeline
        # This test verifies the chat endpoint accepts the request
        # (pipeline-level tenant errors would occur during scope selection)
        response = client.post("/chat", json={
            "question": "Hello",
            "customer_key": "nonexistent_tenant_xyz",
            "user_id": "Test.Officer",
        })
        # V2 returns 200 with greeting since no scope is selected yet
        assert response.status_code == 200

    def test_chat_missing_question(self, client):
        response = client.post("/chat", json={
            "customer_key": "demo",
            "user_id": "Test.Officer",
        })
        assert response.status_code == 422

    @patch("src.api.routes._get_session_store")
    def test_chat_with_missing_session_id_returns_session_expired(self, mock_store_fn, client):
        mock_store = MagicMock()
        mock_store.get.return_value = None
        mock_store_fn.return_value = mock_store

        response = client.post(
            "/chat",
            json={
                "question": "hello",
                "customer_key": "demo",
                "user_id": "Test.Officer",
                "session_id": "missing-session",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "session_expired"


class TestSessionEndpoint:
    @patch("src.api.routes._get_session_store")
    def test_get_session(self, mock_store_fn, client, session):
        mock_store = MagicMock()
        mock_store.get.return_value = session
        mock_store_fn.return_value = mock_store

        response = client.get(f"/session/{session.session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session.session_id
        assert data["customer_key"] == "demo"

    @patch("src.api.routes._get_session_store")
    def test_session_not_found(self, mock_store_fn, client):
        mock_store = MagicMock()
        mock_store.get.return_value = None
        mock_store_fn.return_value = mock_store

        response = client.get("/session/nonexistent-id")
        assert response.status_code == 404


class TestHistoryEndpoint:
    @patch("src.api.routes._get_conversation_store")
    def test_get_history(self, mock_store_fn, client):
        mock_store = MagicMock()
        mock_store.get_history.return_value = [
            {"content": "How many?", "role": "user"},
            {"content": "There are 10.", "role": "assistant"},
        ]
        mock_store_fn.return_value = mock_store

        response = client.get("/history?customer_key=demo&user_id=Test.Officer")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2


class TestChatStreamEndpoint:
    @patch("src.api.routes._get_state_machine")
    @patch("src.api.routes._get_session_store")
    def test_chat_stream_greeting_active_scope_uses_cross_scope(
        self,
        mock_store_fn,
        mock_sm_fn,
        client,
        session,
    ):
        session.active_scope = "inmate_data"

        mock_store = MagicMock()
        mock_store.get.return_value = session
        mock_store_fn.return_value = mock_store

        async def fake_dispatch_stream(*, message, session):
            _ = message
            _ = session
            yield {
                "event": "result",
                "data": {
                    "summary": "Hi there! I'm currently helping you with Inmate Data. What would you like to know?",
                    "is_greeting": True,
                    "scope": "inmate_data",
                    "row_count": 0,
                },
            }

        mock_sm = MagicMock()
        mock_sm.dispatch_stream = fake_dispatch_stream
        mock_sm_fn.return_value = mock_sm

        response = client.post(
            "/chat/stream",
            json={
                "question": "hello",
                "customer_key": "demo",
                "user_id": "Test.Officer",
                "session_id": session.session_id,
            },
        )

        assert response.status_code == 200
        body = response.text
        assert "event: result" in body
        payload_lines = [line for line in body.splitlines() if line.startswith("data: ")]
        assert payload_lines
        result_payload = None
        for line in payload_lines:
            payload = json.loads(line.replace("data: ", ""))
            if isinstance(payload, dict) and payload.get("is_greeting"):
                result_payload = payload
                break
        assert result_payload is not None
        assert result_payload["is_greeting"] is True

    @patch("src.api.routes._get_session_store")
    def test_chat_stream_missing_session_id_emits_session_expired(self, mock_store_fn, client):
        mock_store = MagicMock()
        mock_store.get.return_value = None
        mock_store_fn.return_value = mock_store

        response = client.post(
            "/chat/stream",
            json={
                "question": "hello",
                "customer_key": "demo",
                "user_id": "Test.Officer",
                "session_id": "missing-session",
            },
        )

        assert response.status_code == 200
        body = response.text
        assert "session_expired" in body


class TestScopeSessionContracts:
    @patch("src.api.routes._get_session_store")
    def test_scope_select_with_missing_session_returns_session_expired(self, mock_store_fn, client):
        mock_store = MagicMock()
        mock_store.get.return_value = None
        mock_store_fn.return_value = mock_store

        response = client.post(
            "/scope/select",
            json={"session_id": "missing-session", "scope": "inmate_data"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "session_expired"

    @patch("src.api.routes._get_session_store")
    def test_scope_options_with_missing_session_returns_session_expired(self, mock_store_fn, client):
        mock_store = MagicMock()
        mock_store.get.return_value = None
        mock_store_fn.return_value = mock_store

        response = client.get("/scope/options?session_id=missing-session")
        assert response.status_code == 404
        assert response.json()["detail"] == "session_expired"
