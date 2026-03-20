"""
Vanna Agent — Core text-to-SQL agent orchestrating the full query pipeline.

Uses Vanna 2.0's async OpenAI LLM service and ChromaDB agent memory for
context-aware SQL generation. All Vanna 2.0 APIs are async; this module
exposes both sync wrappers (for scripts) and native async methods (for FastAPI).

Pipeline: Question → Validate → Enrich (history) → Generate SQL → Validate SQL
          → Inject Filters → Execute → Format Response → Save Turn
"""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, AsyncGenerator

from src.pipelines.inmate_data.prompt_builder import build_sql_context
from src.pipelines.inmate_data.response_formatter import (
    format_analytics_response,
    format_data_response,
    format_empty_response,
    format_error_response,
)
from src.pipelines.inmate_data.guardrails.question_validator import validate_question
from src.pipelines.inmate_data.guardrails.sql_validator import inject_filters, validate_and_fix_sql
from src.memory.conversation_store import ConversationStore
from src.session.models import ConversationTurn, Session
from src.shared.config import (
    CHROMA_STORAGE_DIR,
    ENABLE_GUARDRAILS,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    MAX_QUERY_RESULTS,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    VANNA_COLLECTION_NAME,
)
from src.shared.logger import get_logger
from src.tenant.db_registry import execute_query
from src.tenant.tenant_router import TenantContext

logger = get_logger(__name__)

_llm_service = None
_agent_memory = None

SQL_SYSTEM_PROMPT = (
    "You are a MySQL SQL expert for a prison management system. "
    "Generate ONLY a valid MySQL SELECT query. No explanations, no markdown fences, "
    "no commentary — just the raw SQL.\n\n"

    "MANDATORY RULES:\n"
    "- Filter status = 1 for active records on main tables (n, t, u, f, ts).\n"
    "- Include LIMIT (default 500). Use LOWER(col) LIKE '%term%' for text search.\n"
    "- NEVER return: password, salt, notes_pin, ssn, signature, latitude, longitude.\n"
    "- Default date range: last 30 days if none specified.\n\n"

    "TABLE CATALOG (aliases in parens):\n"
    "CORE: dg_notes (n) — officer logs, central table. "
    "Key cols: notes_id, notes_description, note_date, date_added, user_id, "
    "facilities_id, highlighter_id, shift_id, visitor_log, notetime, status.\n"
    "KEYWORDS: dg_notes_by_keyword (knw) — active notes/keywords per note. "
    "Key cols: notes_id, keyword_name, keyword_id, facilities_id, date_added.\n"
    "INMATE LINK: dg_notes_tags (ntg) — note-to-inmate linkage. "
    "Key cols: notes_id, tags_id, emp_tag_id, tag_status_id, facilities_id.\n"
    "STATUS-KEYWORD: dg_notes_status_keyword (nsk) — status + keywords per note. "
    "Key cols: tags_id, notes_id, tag_status_id, tag_status_name, keyword_id, "
    "keyword_name, facilities_id, facility, Status_Keyword, date_added.\n"
    "INMATES: dg_tags (t) — inmate master. "
    "Key cols: tags_id, emp_first_name, emp_last_name, emp_tag_id, "
    "facilities_id, room, bed_number, role_call, status, date_added, dob, gender.\n"
    "MOVEMENT: dg_tags_movement (tm) — inmate movement history. "
    "Key cols: tags_movement_id, tags_id, old_room, new_room, "
    "old_facilities_id, new_facilities_id, date_added, is_move.\n"
    "STATUS LOOKUP: dg_tag_status (ts) — status type definitions. "
    "Key cols: tag_status_id, name, facilities_id, status.\n"
    "STATUS HISTORY: dg_tagstatus — inmate status records over time. "
    "Key cols: tags_id, notes_id, tag_status_id.\n"
    "FACILITIES: dg_facilities (f) — facility/dorm names. "
    "Key cols: facilities_id, facility (NAME column, NOT facility_name), status.\n"
    "OFFICERS: dg_user (u) — officers. "
    "Key cols: user_id (INT PK), username, firstname, lastname, "
    "default_facilities_id, status.\n"
    "SHIFTS: dg_shift (s) — shift_id, shift_name, shift_starttime, shift_endtime.\n"
    "HIGHLIGHTER: dg_highlighter (h) — highlighter_id, highlighter_name, status. "
    "IDs: 11=Red, 12=LightGreen, 13=Blue, 14=Yellow, 15=Pink, 21=White, 22=Orange.\n"
    "COMMENTS: dg_notes_by_comment (c) — notes_id, comment, user_id, date_added.\n"
    "LOCATIONS: dg_notes_by_location (loc) — notes_id, location_name.\n"
    "MULTI-KEYWORD: dg_notes_by_multikeyword — form field values per note.\n"
    "FORMS: dg_forms — form_type, custom_form_type, notes_id.\n\n"

    "CRITICAL JOIN RULES:\n"
    "1) OFFICER-NOTES JOIN: dg_notes.user_id is VARCHAR (e.g. 'Anks','Richard.Bell'). "
    "dg_user.user_id is INT. To join: u.username = n.user_id (NOT u.user_id).\n"
    "2) INMATE CURRENT STATUS: dg_tags.role_call → dg_tag_status.tag_status_id. "
    "NEVER use tags_status (always 0). ALWAYS use role_call for current status.\n"
    "3) INMATE STATUS HISTORY: dg_notes_tags.tag_status_id → dg_tag_status.\n"
    "4) LOCATION vs MOVEMENT: 'Where is inmate X' / 'locate' → query dg_tags (current location/status). "
    "'movement', 'moved', 'room change', 'transfer' → use dg_tags_movement (tm). "
    "NEVER use dg_tags.is_movement. "
    "JOIN: tm INNER JOIN dg_tags t ON tm.tags_id = t.tags_id "
    "INNER JOIN dg_facilities old_f ON tm.old_facilities_id = old_f.facilities_id "
    "INNER JOIN dg_facilities new_f ON tm.new_facilities_id = new_f.facilities_id "
    "LEFT JOIN dg_tag_status ts ON t.role_call = ts.tag_status_id.\n"
    "5) INMATE NAME: Use CONCAT(t.emp_first_name,' ',t.emp_last_name) AS inmate_name. "
    "Single name → OR between first/last. Two-word name 'X Y' → search BOTH orderings: "
    "WHERE (LOWER(emp_first_name) LIKE '%x%' AND LOWER(emp_last_name) LIKE '%y%') "
    "OR (LOWER(emp_first_name) LIKE '%y%' AND LOWER(emp_last_name) LIKE '%x%'). "
    "DB may store names in either order.\n"
    "6) STATUS CHANGE for inmate: Use dg_notes n "
    "JOIN dg_notes_tags ntg ON n.notes_id = ntg.notes_id "
    "JOIN dg_tags t ON ntg.tags_id = t.tags_id "
    "LEFT JOIN dg_tag_status ts ON ntg.tag_status_id = ts.tag_status_id. "
    "Return ts.name AS status, ordered by n.date_added DESC.\n"
    "7) KEYWORD SEARCH: LEFT JOIN dg_notes_by_keyword knw ON n.notes_id = knw.notes_id. "
    "Multi-word keywords: split with AND (fire watch → LIKE '%fire%' AND LIKE '%watch%').\n"
    "8) FACILITY NAME column is 'facility', NOT 'facility_name'.\n"
    "9) OFFICER NAME columns: 'firstname','lastname' (NOT first_name, last_name).\n"
    "10) Red-highlighted notes: n.highlighter_id = 11.\n"
    "11) Visitor log notes: n.visitor_log = 1.\n"
    "12) Inactive users: u.status = 0.\n"
    "13) NO tables exist: dg_keywords, dg_inmates. "
    "dg_tags has NO tag_name/tag_id columns.\n"
)


def _make_user(user_id: str = "system") -> Any:
    from vanna.core.user import User
    return User(id=user_id, username=user_id)


def _make_tool_context(user_id: str = "system", conversation_id: str = "") -> Any:
    from vanna.core.tool.models import ToolContext
    memory = get_agent_memory()
    if memory is None:
        raise RuntimeError("Agent memory not initialised")
    return ToolContext(
        user=_make_user(user_id),
        conversation_id=conversation_id or str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        agent_memory=memory,
    )


def get_llm_service():
    global _llm_service
    if _llm_service is None:
        provider = LLM_PROVIDER.lower().strip()
        if provider == "gemini":
            from vanna.integrations.google import GeminiLlmService
            _llm_service = GeminiLlmService(
                model=GEMINI_MODEL,
                api_key=GEMINI_API_KEY,
                temperature=LLM_TEMPERATURE,
            )
            logger.info("Vanna 2.0 LLM: Gemini %s", GEMINI_MODEL)
        else:
            from vanna.integrations.openai import OpenAILlmService
            _llm_service = OpenAILlmService(
                model=OPENAI_MODEL, api_key=OPENAI_API_KEY,
            )
            logger.info("Vanna 2.0 LLM: OpenAI %s", OPENAI_MODEL)
    return _llm_service


def get_agent_memory():
    global _agent_memory
    if _agent_memory is None:
        try:
            from vanna.integrations.chromadb import ChromaAgentMemory
            _agent_memory = ChromaAgentMemory(
                persist_directory=CHROMA_STORAGE_DIR,
                collection_name=VANNA_COLLECTION_NAME,
            )
            logger.info("ChromaDB memory: %s", CHROMA_STORAGE_DIR)
        except Exception as e:
            logger.warning("ChromaDB unavailable (%s), no memory", str(e))
            _agent_memory = None
    return _agent_memory


async def _search_memory(question: str, user_id: str) -> str:
    """Search ChromaDB for similar training examples (async)."""
    memory = get_agent_memory()
    if not memory:
        return ""
    try:
        ctx = _make_tool_context(user_id)
        results = await memory.search_text_memories(question, ctx, limit=5)
        if results:
            parts = ["\n\nRelevant training examples:"]
            for r in results:
                parts.append(f"- {r.memory.content}")
            return "\n".join(parts)
    except Exception as e:
        logger.warning("Memory search failed: %s", str(e))
    return ""


async def generate_sql_via_llm(
    question: str,
    context: str = "",
    user_id: str = "system",
) -> str | None:
    """Generate SQL from a natural language question via Vanna 2.0 LLM + memory."""
    llm = get_llm_service()
    memory_context = await _search_memory(question, user_id)

    from vanna import LlmMessage, LlmRequest
    messages = [
        LlmMessage(role="system", content=SQL_SYSTEM_PROMPT + memory_context),
        LlmMessage(role="user", content=context or question),
    ]

    try:
        request = LlmRequest(
            messages=messages,
            user=_make_user(user_id),
            temperature=LLM_TEMPERATURE,
        )
        response = await llm.send_request(request)
        raw = response.content.strip() if response and response.content else None
        if raw:
            raw = _strip_markdown_fences(raw)
        return raw
    except Exception as e:
        logger.error("LLM SQL generation failed: %s", str(e))
        return None


def generate_sql_via_llm_sync(
    question: str,
    context: str = "",
    user_id: str = "system",
) -> str | None:
    """Sync wrapper for scripts/tests that need to call the LLM."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                generate_sql_via_llm(question, context, user_id),
            ).result()
    return asyncio.run(generate_sql_via_llm(question, context, user_id))


def _strip_markdown_fences(sql: str) -> str:
    """Extract raw SQL from LLM output — handles fences anywhere in the text."""
    import re
    match = re.search(r"```(?:sql)?\s*\n?(.*?)```", sql, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    select_match = re.search(r"(SELECT\s.+)", sql, re.DOTALL | re.IGNORECASE)
    if select_match and not sql.strip().upper().startswith("SELECT"):
        return select_match.group(1).strip()

    return sql.strip()


class AgentPipeline:
    """Orchestrates the full question → answer pipeline (async).

    Flow:
      1. Classify intent (fast pattern match)
      2. Non-data intents → Sarah's brain (no SQL)
      3. Data intents → SQL pipeline (generate → validate → execute → format)
    """

    def __init__(
        self,
        session_store: SessionStore,
        conversation_store: ConversationStore,
    ) -> None:
        self._session_store = session_store
        self._conversation_store = conversation_store

    async def process_question(
        self,
        question: str,
        session: Session,
        tenant: TenantContext,
    ) -> dict[str, Any]:
        from src.pipelines.inmate_data.intent_engine import Intent, classify_intent
        from src.pipelines.inmate_data.sarah_brain import enrich_data_response, generate_response

        has_history = len(session.turns) > 0
        last_content = session.turns[-1].content if session.turns else ""
        intent_result = classify_intent(question, has_history, last_content)
        logger.info(
            "Intent: %s (%.0f%%) for: %s",
            intent_result.intent.value,
            intent_result.confidence * 100,
            question[:80],
        )

        if intent_result.intent not in (Intent.DATA_QUERY, Intent.FOLLOW_UP):
            response = generate_response(intent_result, session)
            self._save_conversational_turn(session, question, response)
            return response

        if intent_result.intent == Intent.FOLLOW_UP and _is_history_recall(question):
            response = self._handle_history_recall(session, question)
            self._save_conversational_turn(session, question, response)
            return response

        question = intent_result.rewritten_question

        if intent_result.intent == Intent.FOLLOW_UP:
            question = _rewrite_follow_up(question, session)
            logger.info("Rewritten follow-up: %s", question[:120])

        if ENABLE_GUARDRAILS:
            validation = validate_question(question)
            if not validation.is_valid:
                return self._save_and_return_error(session, question, validation.error)
            question = validation.cleaned_question

        self._enrich_session_from_history(session)

        sql = await self._generate_sql(question, session)
        if not sql:
            return self._save_and_return_error(
                session, question, "Could not generate SQL for this question."
            )

        sql_result = validate_and_fix_sql(sql)
        if not sql_result.is_valid:
            retry_sql = await self._retry_with_feedback(
                question, sql, sql_result.error, session
            )
            if not retry_sql:
                return self._save_and_return_error(
                    session, question, f"SQL validation failed: {sql_result.error}"
                )
            sql = retry_sql
        else:
            sql = sql_result.sql

        sql = inject_filters(sql, session.facility_ids)

        try:
            rows = execute_query(tenant, sql, limit=MAX_QUERY_RESULTS)
        except Exception as e:
            retry_result = await self._retry_on_execution_error(
                question, sql, str(e), session, tenant
            )
            if retry_result is not None:
                return retry_result
            return self._save_and_return_error(
                session, question, f"Query execution failed: {str(e)}"
            )

        response = self._build_response(rows, question, sql)
        response = enrich_data_response(response, question, session)
        self._save_turn(session, question, sql, response)
        return response

    async def process_question_stream(
        self,
        question: str,
        session: Session,
        tenant: TenantContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yields incremental SSE events as the pipeline progresses."""
        from src.pipelines.inmate_data.intent_engine import Intent, classify_intent
        from src.pipelines.inmate_data.sarah_brain import enrich_data_response, generate_response

        has_history = len(session.turns) > 0
        last_content = session.turns[-1].content if session.turns else ""
        intent_result = classify_intent(question, has_history, last_content)
        logger.info(
            "Stream intent: %s (%.0f%%) for: %s",
            intent_result.intent.value,
            intent_result.confidence * 100,
            question[:80],
        )

        if intent_result.intent not in (Intent.DATA_QUERY, Intent.FOLLOW_UP):
            response = generate_response(intent_result, session)
            self._save_conversational_turn(session, question, response)
            yield {"event": "result", "data": response}
            return

        if intent_result.intent == Intent.FOLLOW_UP and _is_history_recall(question):
            response = self._handle_history_recall(session, question)
            self._save_conversational_turn(session, question, response)
            yield {"event": "result", "data": response}
            return

        question = intent_result.rewritten_question

        if intent_result.intent == Intent.FOLLOW_UP:
            question = _rewrite_follow_up(question, session)
            logger.info("Rewritten follow-up (stream): %s", question[:120])

        yield {"event": "status", "data": "Understanding your question..."}

        if ENABLE_GUARDRAILS:
            validation = validate_question(question)
            if not validation.is_valid:
                yield {"event": "error", "data": validation.error}
                return
            question = validation.cleaned_question

        self._enrich_session_from_history(session)

        yield {"event": "status", "data": "Generating query..."}
        sql = await self._generate_sql(question, session)
        if not sql:
            self._save_and_return_error(session, question, "Could not generate SQL.")
            yield {"event": "error", "data": "Could not generate SQL for this question."}
            return

        sql_result = validate_and_fix_sql(sql)
        if not sql_result.is_valid:
            yield {"event": "status", "data": "Refining query..."}
            retry_sql = await self._retry_with_feedback(
                question, sql, sql_result.error, session
            )
            if not retry_sql:
                yield {"event": "error", "data": f"SQL validation failed: {sql_result.error}"}
                return
            sql = retry_sql
        else:
            sql = sql_result.sql

        sql = inject_filters(sql, session.facility_ids)

        yield {"event": "status", "data": "Fetching results..."}
        try:
            rows = execute_query(tenant, sql, limit=MAX_QUERY_RESULTS)
        except Exception as e:
            yield {"event": "error", "data": f"Query failed: {str(e)}"}
            return

        yield {"event": "status", "data": "Preparing response..."}
        response = self._build_response(rows, question, sql)
        response = enrich_data_response(response, question, session)
        self._save_turn(session, question, sql, response)
        yield {"event": "result", "data": response}

    def _enrich_session_from_history(self, session: Session) -> None:
        """For returning users with no turns yet, load prior patterns from DynamoDB."""
        if session.turns:
            return
        try:
            history = self._conversation_store.get_history(
                session.customer_key, session.user_id, limit=10
            )
            if not history:
                return
            topics = set()
            for item in history:
                if item.get("role") == "user" and item.get("content"):
                    topics.add(item["content"])
            if topics:
                summary = "; ".join(list(topics)[:5])
                hint = ConversationTurn(
                    role="system",
                    content=f"Returning user. Past queries: {summary}",
                )
                session.turns.insert(0, hint)
                logger.info(
                    "Enriched session with %d prior topics for %s",
                    len(topics), session.user_id,
                )
        except Exception as e:
            logger.warning("History enrichment failed: %s", str(e))

    async def _generate_sql(self, question: str, session: Session) -> str | None:
        context = build_sql_context(question, session)
        sql = await generate_sql_via_llm(question, context, user_id=session.user_id)
        if sql and not _is_error_message(sql):
            sql = _fix_inmate_name_order(sql)
            return sql
        return None

    async def _retry_with_feedback(
        self, question: str, failed_sql: str, error: str, session: Session,
    ) -> str | None:
        feedback = (
            f"Previous SQL had an error: {error}\n"
            f"Failed SQL: {failed_sql}\n"
            f"Original question: {question}\n"
            "Generate a corrected MySQL SELECT query."
        )
        sql = await generate_sql_via_llm(question, feedback, user_id=session.user_id)
        if sql and not _is_error_message(sql):
            result = validate_and_fix_sql(sql)
            return result.sql if result.is_valid else None
        return None

    async def _retry_on_execution_error(
        self, question: str, failed_sql: str, error: str,
        session: Session, tenant: TenantContext,
    ) -> dict[str, Any] | None:
        logger.info("Retrying after execution error: %s", error[:200])
        retry_sql = await self._retry_with_feedback(
            question, failed_sql, error, session
        )
        if not retry_sql:
            return None
        retry_sql = inject_filters(retry_sql, session.facility_ids)
        try:
            rows = execute_query(tenant, retry_sql, limit=MAX_QUERY_RESULTS)
        except Exception:
            return None
        response = self._build_response(rows, question, retry_sql)
        self._save_turn(session, question, retry_sql, response)
        return response

    def _build_response(
        self, rows: list[dict], question: str, sql: str,
    ) -> dict[str, Any]:
        if not rows:
            return format_empty_response(question, sql)
        if _is_analytics_query(rows):
            return format_analytics_response(rows, question, sql)
        return format_data_response(rows, question, sql)

    def _save_turn(
        self, session: Session, question: str, sql: str, response: dict[str, Any],
    ) -> None:
        user_turn = ConversationTurn(role="user", content=question)
        assistant_turn = ConversationTurn(
            role="assistant",
            content=response.get("summary", ""),
            sql=sql,
            row_count=response.get("row_count", 0),
        )
        session.add_turn(user_turn)
        session.add_turn(assistant_turn)
        self._session_store.save(session)
        self._conversation_store.save_turn(session, user_turn)
        self._conversation_store.save_turn(session, assistant_turn)

    def _save_conversational_turn(
        self, session: Session, question: str, response: dict[str, Any],
    ) -> None:
        """Save non-SQL conversational turns (greetings, capabilities, etc.)."""
        user_turn = ConversationTurn(role="user", content=question)
        assistant_turn = ConversationTurn(
            role="assistant",
            content=response.get("summary", "")[:200],
        )
        session.add_turn(user_turn)
        session.add_turn(assistant_turn)
        self._session_store.save(session)

    def _handle_history_recall(
        self, session: Session, question: str,
    ) -> dict[str, Any]:
        """Respond to 'what did I ask earlier' by summarizing conversation history."""
        user_turns = [t for t in session.turns if t.role == "user"]
        if not user_turns:
            return {
                "summary": "This is the beginning of our conversation — you haven't asked anything yet! What would you like to know?",
                "is_conversational": True,
                "row_count": 0,
            }
        lines = ["Here's what you've asked so far in this session:\n"]
        for i, t in enumerate(user_turns[-10:], 1):
            lines.append(f"  {i}. {t.content}")
        lines.append(f"\nTotal: {len(user_turns)} question{'s' if len(user_turns) != 1 else ''}. Want me to revisit any of these?")
        return {
            "summary": "\n".join(lines),
            "is_conversational": True,
            "row_count": 0,
        }

    def _save_and_return_error(
        self, session: Session, question: str, error: str,
    ) -> dict[str, Any]:
        user_turn = ConversationTurn(role="user", content=question)
        error_turn = ConversationTurn(role="assistant", content=f"Error: {error}")
        session.add_turn(user_turn)
        session.add_turn(error_turn)
        self._session_store.save(session)
        return format_error_response(error, question)


def _is_history_recall(question: str) -> bool:
    import re
    return bool(re.search(
        r"(what\s+(did\s+)?i\s+ask|what\s+was\s+my|my\s+(earlier|previous|last)\s+question"
        r"|repeat\s+that|what\s+have\s+we\s+discussed)",
        question, re.IGNORECASE,
    ))


def _rewrite_follow_up(question: str, session: Session) -> str:
    """Resolve pronouns and implicit references using conversation history.

    Extracts entities (inmate name, facility, time range, keyword) from prior turns
    and substitutes 'this inmate', 'list out names', etc. into a self-contained question.
    """
    prior_entities = _extract_prior_entities(session)

    q_lower = question.lower()
    inmate_name = prior_entities.get("inmate_name", "")
    last_topic = prior_entities.get("last_topic", "")

    pronoun_ref = re.search(
        r"\b(this|that|the)\s+(inmate|officer|person|prisoner)\b", q_lower,
    )
    if pronoun_ref and inmate_name:
        replacement = f"inmate {inmate_name}"
        question = re.sub(
            r"\b(this|that|the)\s+(inmate|officer|person|prisoner)\b",
            replacement, question, flags=re.IGNORECASE,
        )
        return question

    if re.search(r"\b(for\s+(?:him|her|them))\b", q_lower) and inmate_name:
        question = re.sub(
            r"\b(for\s+(?:him|her|them))\b",
            f"for inmate {inmate_name}", question, flags=re.IGNORECASE,
        )
        return question

    short_follow = re.match(
        r"^(list\s+out\s+names?|show\s+names?|just\s+names?|names?\s+only)$",
        q_lower,
    )
    if short_follow and last_topic:
        return f"{last_topic} — show inmate names"

    if not re.search(r"(inmate|officer|notes?|entries)", q_lower) and last_topic:
        question = f"{question} (context: {last_topic})"

    return question


def _extract_prior_entities(session: Session) -> dict[str, str]:
    """Scan recent turns to find the last referenced inmate name, topic, etc."""
    entities: dict[str, str] = {}
    user_turns = [t for t in session.turns if t.role == "user"]
    assistant_turns = [t for t in session.turns if t.role == "assistant"]

    for turn in reversed(user_turns[-5:]):
        content = turn.content
        name_match = re.search(
            r"(?:inmate|prisoner)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)",
            content, re.IGNORECASE,
        )
        if name_match and "inmate_name" not in entities:
            entities["inmate_name"] = name_match.group(1).strip()

        if "last_topic" not in entities and len(content) > 8:
            entities["last_topic"] = content

    for turn in reversed(assistant_turns[-3:]):
        content = turn.content
        if "inmate_name" not in entities:
            bold_match = re.search(r"\*\*([A-Z][a-z]+ [A-Z][a-z]+)\*\*", content)
            if bold_match:
                entities["inmate_name"] = bold_match.group(1)

    return entities


def _fix_inmate_name_order(sql: str) -> str:
    """For two-word inmate name searches, ensure SQL checks both first/last orderings.

    DB may store names in either order (e.g., first='NOVA', last='ANTHONY' for 'Anthony Nova').
    """
    pattern = re.compile(
        r"LOWER\((\w+\.emp_first_name)\)\s+LIKE\s+'%(\w+)%'"
        r"\s+AND\s+"
        r"LOWER\((\w+\.emp_last_name)\)\s+LIKE\s+'%(\w+)%'",
        re.IGNORECASE,
    )
    match = pattern.search(sql)
    if match:
        col_first, name1, col_last, name2 = match.groups()
        if name1.lower() != name2.lower():
            original = match.group(0)
            reversed_clause = (
                f"(({original}) OR "
                f"(LOWER({col_first}) LIKE '%{name2}%' AND LOWER({col_last}) LIKE '%{name1}%'))"
            )
            sql = sql.replace(original, reversed_clause)
        return sql

    concat_pattern = re.compile(
        r"LOWER\(CONCAT\((\w+)\.emp_first_name,\s*'?\s*'?,?\s*(\w+)\.emp_last_name\)\)\s+"
        r"LIKE\s+'%(\w+)\s+(\w+)%'",
        re.IGNORECASE,
    )
    cmatch = concat_pattern.search(sql)
    if cmatch:
        alias1, alias2, name1, name2 = cmatch.groups()
        if name1.lower() != name2.lower():
            replacement = (
                f"((LOWER({alias1}.emp_first_name) LIKE '%{name1}%' "
                f"AND LOWER({alias2}.emp_last_name) LIKE '%{name2}%') OR "
                f"(LOWER({alias1}.emp_first_name) LIKE '%{name2}%' "
                f"AND LOWER({alias2}.emp_last_name) LIKE '%{name1}%'))"
            )
            sql = sql.replace(cmatch.group(0), replacement)
        return sql

    return sql


def _is_error_message(sql: str) -> bool:
    indicators = [
        "i don't know", "i cannot", "i'm not sure", "unable to",
        "no relevant", "insufficient", "sorry",
    ]
    lower = sql.lower().strip()
    return any(ind in lower for ind in indicators)


def _is_analytics_query(rows: list[dict]) -> bool:
    if not rows:
        return False
    if len(rows) <= 5:
        keys = set(rows[0].keys())
        data_columns = {"notes_id", "notes_description", "note_date", "date_added"}
        if not keys & data_columns:
            return True
    return False
