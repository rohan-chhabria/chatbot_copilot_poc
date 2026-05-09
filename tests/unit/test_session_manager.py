"""Tests for session_manager module."""

from __future__ import annotations

import time

from src.session.session_manager import (
    ConversationTurn,
    Session,
    create_session,
)


class TestSessionCreation:
    def test_create_session(self):
        session = create_session(
            customer_key="demo",
            user_id="Test.Officer",
            facility_ids=[101, 102],
            role="officer",
        )
        assert session.customer_key == "demo"
        assert session.user_id == "Test.Officer"
        assert session.facility_ids == [101, 102]
        assert session.role == "officer"
        assert len(session.session_id) == 36
        assert session.turns == []

    def test_create_session_defaults(self):
        session = create_session(customer_key="demo", user_id="Admin")
        assert session.facility_ids == []
        assert session.role == "officer"


class TestSessionTurns:
    def test_add_turn(self, session: Session):
        turn = ConversationTurn(role="user", content="How many inmates?")
        session.add_turn(turn)
        assert len(session.turns) == 1
        assert session.turns[0].content == "How many inmates?"

    def test_turn_limit(self, session: Session):
        for i in range(20):
            session.add_turn(ConversationTurn(role="user", content=f"Question {i}"))
        assert len(session.turns) == 15

    def test_turn_limit_is_per_scope(self, session: Session):
        session.switch_scope("inmate_data")
        for i in range(20):
            session.add_turn(ConversationTurn(role="user", content=f"Inmate {i}"))

        session.switch_scope("document_qa")
        for i in range(20):
            session.add_turn(ConversationTurn(role="user", content=f"Document {i}"))

        inmate_turns = session.get_turns_for_scope("inmate_data")
        docs_turns = session.get_turns_for_scope("document_qa")
        assert len(inmate_turns) == 15
        assert len(docs_turns) == 15

    def test_history_prompt(self, session_with_history: Session):
        prompt = session_with_history.get_history_prompt()
        assert "Fire Watch" in prompt
        assert "user:" in prompt
        assert "assistant:" in prompt


class TestSessionSerialization:
    def test_to_dict(self, session: Session):
        data = session.to_dict()
        assert data["customer_key"] == "demo"
        assert isinstance(data["turns"], list)
        assert isinstance(data["created_at"], float)

    def test_roundtrip(self, session_with_history: Session):
        data = session_with_history.to_dict()
        restored = Session.from_dict(data)
        assert restored.session_id == session_with_history.session_id
        assert restored.customer_key == session_with_history.customer_key
        assert len(restored.turns) == len(session_with_history.turns)
        assert restored.turns[0].content == session_with_history.turns[0].content


class TestInMemoryStore:
    def test_save_and_get(self, memory_session_store, session):
        memory_session_store.save(session)
        retrieved = memory_session_store.get(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_get_nonexistent(self, memory_session_store):
        assert memory_session_store.get("nonexistent") is None

    def test_delete(self, memory_session_store, session):
        memory_session_store.save(session)
        memory_session_store.delete(session.session_id)
        assert memory_session_store.get(session.session_id) is None

    def test_expiration(self, memory_session_store, session):
        session.last_active = time.time() - 7200
        memory_session_store._store[session.session_id] = session.to_dict()
        assert memory_session_store.get(session.session_id) is None
