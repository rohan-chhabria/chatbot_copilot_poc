"""Tests for STM/LTM backend factory selection and local sqlite behavior."""

from __future__ import annotations

import pytest

from src.memory import conversation_store as conv_store
from src.session import session_manager as session_mgr
from src.session.models import ConversationTurn, create_session


class TestSessionStoreFactory:
    def test_explicit_redis_backend(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(session_mgr, "SESSION_BACKEND", "redis")
        monkeypatch.setattr(session_mgr, "_build_redis_store", lambda *args, **kwargs: sentinel)

        store = session_mgr.create_session_store()
        assert store is sentinel

    def test_auto_uses_local_backend(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(session_mgr, "SESSION_BACKEND", "auto")
        monkeypatch.setattr(session_mgr, "IS_PRODUCTION_ENV", False)
        monkeypatch.setattr(session_mgr, "LOCAL_SESSION_BACKEND", "redis")
        monkeypatch.setattr(session_mgr, "_build_redis_store", lambda *args, **kwargs: sentinel)

        store = session_mgr.create_session_store()
        assert store is sentinel

    def test_backend_unavailable_raises(self, monkeypatch):
        monkeypatch.setattr(session_mgr, "SESSION_BACKEND", "redis")

        def _raise(*args, **kwargs):
            raise ConnectionError("refused")

        monkeypatch.setattr(session_mgr, "_build_redis_store", _raise)

        with pytest.raises(RuntimeError, match="Session backend 'redis' is unavailable"):
            session_mgr.create_session_store()

    def test_unsupported_backend_raises(self, monkeypatch):
        monkeypatch.setattr(session_mgr, "SESSION_BACKEND", "unsupported")
        with pytest.raises(RuntimeError, match="Session backend 'unsupported' is unavailable"):
            session_mgr.create_session_store()


class TestConversationStoreFactory:
    def test_explicit_sqlite_backend(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(conv_store, "LTM_BACKEND", "sqlite")
        monkeypatch.setattr(conv_store, "SQLiteConversationStore", lambda: sentinel)

        store = conv_store.create_conversation_store()
        assert store is sentinel

    def test_explicit_dynamodb_backend(self, monkeypatch):
        class _Table:
            table_status = "ACTIVE"

        class _Store:
            _table = _Table()

        sentinel = _Store()
        monkeypatch.setattr(conv_store, "LTM_BACKEND", "dynamodb")
        monkeypatch.setattr(conv_store, "DynamoConversationStore", lambda: sentinel)

        store = conv_store.create_conversation_store()
        assert store is sentinel

    def test_backend_unavailable_raises(self, monkeypatch):
        monkeypatch.setattr(conv_store, "LTM_BACKEND", "dynamodb")

        def _raise():
            raise RuntimeError("table missing")

        monkeypatch.setattr(conv_store, "DynamoConversationStore", _raise)

        with pytest.raises(RuntimeError, match="Conversation backend 'dynamodb' is unavailable"):
            conv_store.create_conversation_store()


class TestSQLiteConversationStore:
    def test_persist_and_fetch_turns(self, tmp_path):
        db_path = tmp_path / "conversation.db"
        store = conv_store.SQLiteConversationStore(db_path=str(db_path))
        session = create_session(customer_key="demo", user_id="Test.Officer")

        user_turn = ConversationTurn(
            role="user",
            content="Where is inmate John Doe?",
            scope="inmate_data",
            timestamp=1700000000.0,
        )
        assistant_turn = ConversationTurn(
            role="assistant",
            content="Inmate John Doe is in Facility A.",
            scope="inmate_data",
            row_count=1,
            timestamp=1700000001.0,
        )
        store.save_turn(session, user_turn)
        store.save_turn(session, assistant_turn)

        history = store.get_history("demo", "Test.Officer", limit=10)
        assert len(history) == 2
        assert history[0]["role"] == "assistant"
        assert history[1]["role"] == "user"

        session_turns = store.get_session_turns(session.session_id)
        assert len(session_turns) == 2
        assert session_turns[0]["content"] == "Where is inmate John Doe?"

        user_turns = store.get_user_turns("demo", "Test.Officer", limit=10, scope="inmate_data")
        assert len(user_turns) == 1
        assert user_turns[0]["content"] == "Where is inmate John Doe?"
