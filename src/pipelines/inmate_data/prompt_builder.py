"""
Prompt Builder — Context-aware prompt construction for the Vanna agent.

Builds prompts that include conversation history, user context (facility scope,
role), and system instructions for concise, actionable responses.
"""

from __future__ import annotations

from src.session.models import Session

SYSTEM_CONTEXT = (
    "You are an intelligent assistant for correctional facility officers. "
    "Answer questions about inmate data, officer notes, facility operations, "
    "and compliance metrics. Be concise and actionable — officers need quick answers. "
    "When data is returned, summarize key findings in 2-3 sentences before showing details. "
    "Always prioritize safety-related information (Fire Watch, Suicide Watch, Segregation)."
)

FOLLOW_UP_HINT = (
    "The user may ask follow-up questions referencing previous results. "
    "Use conversation history to understand context. "
    'For example, "show me more details" refers to the last query results.'
)


def build_question_prompt(question: str, session: Session | None = None) -> str:
    parts = [SYSTEM_CONTEXT]

    if session:
        parts.append(_build_user_context(session))

        history = session.get_history_prompt()
        if history:
            parts.append(f"Conversation history:\n{history}")
            parts.append(FOLLOW_UP_HINT)

    parts.append(f"Current question: {question}")

    return "\n\n".join(parts)


_STATUS_NAMES = {
    "cell": "In the Cell", "in the cell": "In the Cell", "in cell": "In the Cell",
    "recreation": "Recreation", "rec": "Recreation",
    "medical": "Medical", "med": "Medical",
    "meal": "Meal", "meals": "Meal",
    "transit": "In Transit", "in transit": "In Transit",
    "segregation": "Segregation", "seg": "Segregation",
    "work detail": "Work Detail", "work": "Work Detail",
    "education": "Education", "court": "Video Court Hearing",
    "visitation": "Visitation", "visit": "Visitation",
    "hospital": "Hospital- Emergency Room",
    "shower": "Shower", "yard": "Yard Call", "yard call": "Yard Call",
    "phone": "Phone", "attorney": "Attorney Visit",
    "laundry": "Laundry", "programming": "Programming",
    "refused": "Refused", "restriction": "Restriction",
    "movement": "Movement", "disciplinary": "Disciplinary Hearing",
    "grooming": "Grooming/Hygiene", "hygiene": "Grooming/Hygiene",
    "agency": "Agency Visit", "table time": "Table Time",
    "classification": "Classification Board",
}


def build_sql_context(question: str, session: Session | None = None) -> str:
    import re
    context_parts = []
    q_lower = question.lower()

    has_notes_intent = bool(re.search(
        r"(entries|notes|log|entry)\s+(for|of|about|related|by)",
        question, re.IGNORECASE,
    ))

    is_inmate_direct = not has_notes_intent and (
        bool(re.search(
            r"(where\s+is|locate|current\s*ly|which\s+facility"
            r"|inmate\s+movement|movement|moved|transfer|room\s+change"
            r"|status\s+change|list\s+(all\s+)?inmates|all\s+inmates"
            r"|who\s+is\s+inmate)",
            question, re.IGNORECASE,
        )) or bool(re.search(
            r"(inmate|prisoner).{0,20}(where|location|current|status|room|cell|bed|moved)",
            question, re.IGNORECASE,
        ))
    )

    is_locate = bool(re.search(
        r"(where\s+is|locate|find|current\s*ly|which\s+facility|who\s+is)",
        question, re.IGNORECASE,
    )) and bool(re.search(r"(inmate|prisoner)", question, re.IGNORECASE))

    is_status_filter = bool(re.search(
        r"(inmates?\s+(?:with|in|at|having|whose)\s+status|status\s+(?:in|is|=)\s"
        r"|in\s+the\s+cell|in\s+(?:recreation|medical|meal|transit|segregation)"
        r"|inmates?\s+(?:in|at)\s+(?:the\s+)?(?:cell|rec|med|meal|seg)"
        r"|facility\s*wise|dorm\s*wise)",
        question, re.IGNORECASE,
    ))

    is_aggregate = bool(re.search(
        r"(daily\s+(?:note|entry)|(?:note|entry)\s+count\s+(?:per|by|for)\s+(?:day|facility|officer)"
        r"|per\s+(?:day|facility)|count\s+(?:per|by)\s+(?:facility|officer|day)"
        r"|notes?\s+per\s+facility|how\s+many\s+notes?\s+per)",
        question, re.IGNORECASE,
    ))
    if is_aggregate:
        context_parts.append(
            "AGGREGATE QUERY: This question asks for grouped/summarized data. "
            "Use GROUP BY in the SQL. For daily counts: GROUP BY DATE(n.date_added). "
            "For per-facility: GROUP BY f.facility with JOIN dg_facilities. "
            "Always include COUNT(*) or COUNT(n.notes_id) AS note_count. "
            "Do NOT return individual rows — return aggregated results."
        )

    is_officer_ranking = bool(re.search(
        r"(top\s+(?:\d+\s+)?(?:officer|user)|officer.*(?:by|most|max)|user.*(?:by|most|max)"
        r"|who\s+(?:added|created|wrote).*(?:most|max))",
        question, re.IGNORECASE,
    ))
    if is_officer_ranking:
        context_parts.append(
            "OFFICER RANKING: Always JOIN dg_user u ON u.username = n.user_id. "
            "SELECT CONCAT(u.firstname, ' ', u.lastname) AS officer_name, COUNT(*) AS note_count. "
            "GROUP BY u.firstname, u.lastname. "
            "Do NOT select n.user_id alone — always resolve to officer's full name."
        )

    is_latest_query = bool(re.search(
        r"(when\s+was\s+(?:the\s+)?last|(?:the\s+)?last\s+(?:round|entry|note|meal)"
        r"|most\s+recent|latest\s+(?:round|entry|note|meal))",
        question, re.IGNORECASE,
    ))
    if is_latest_query:
        context_parts.append(
            "LATEST/LAST QUERY: User wants the single most recent record. "
            "Use ORDER BY n.date_added DESC LIMIT 1. "
            "Include n.notes_description, n.date_added, n.user_id in SELECT."
        )

    is_login_query = bool(re.search(r"(logged\s+in|login|first.*logged|who.*logged)", q_lower))
    if is_login_query:
        context_parts.append(
            "LOGIN QUERY: Search dg_notes for notes_description containing 'logged into'. "
            "Do NOT apply facility filter — logins are cross-facility. "
            "Use MIN(n.date_added) for 'first login', MAX(n.date_added) for 'last login'."
        )

    _KEYWORD_TERMS = [
        "fire watch", "firewatch", "suicide watch", "medical",
        "security rounds", "security", "rounds", "census", "lockdown", "lock down",
        "shower", "meal", "incident", "visitor", "voip", "education",
        "zone check", "bed check", "use of force", "sight and sound",
        "elevated supervision", "cell inspection", "post acceptance",
        "inventory", "alert", "fire",
    ]
    matched_keywords = [kw for kw in _KEYWORD_TERMS if kw in q_lower]
    is_keyword_query = bool(matched_keywords) and not bool(
        re.search(r"(inmate|prisoner)\s+\w+", question, re.IGNORECASE)
    )

    if is_keyword_query and not is_status_filter and not is_locate and not is_inmate_direct and not is_aggregate:
        unique_kws = list(dict.fromkeys(matched_keywords))
        kw_likes = []
        for kw in unique_kws[:4]:
            kw_likes.append(f"LOWER(knw.keyword_name) LIKE '%{kw}%'")
            kw_likes.append(f"LOWER(n.notes_description) LIKE '%{kw}%'")
        where_clause = " OR ".join(kw_likes) if kw_likes else ""
        context_parts.append(
            "KEYWORD/CATEGORY QUERY: Search dg_notes n LEFT JOIN dg_notes_by_keyword knw "
            "ON n.notes_id = knw.notes_id. "
            "Do NOT join dg_notes_tags or dg_tags — this is a keyword search, not inmate-specific. "
            "Do NOT filter on n.visitor_log column — always use keyword/description search. "
            f"MANDATORY WHERE filter: ({where_clause}). "
            "Use OR between different keywords. "
            "IMPORTANT: Wrap the entire OR block in parentheses before AND-ing with n.status=1 and date filters."
        )

    if is_status_filter:
        matched_status = None
        for trigger, status_name in _STATUS_NAMES.items():
            if trigger in q_lower:
                matched_status = status_name
                break
        status_hint = ""
        if matched_status:
            status_hint = (
                f" Filter by ts.name = '{matched_status}' (from dg_tag_status)."
            )
        context_parts.append(
            "INMATE STATUS QUERY: Query dg_tags t "
            "JOIN dg_tag_status ts ON t.role_call = ts.tag_status_id "
            "JOIN dg_facilities f ON t.facilities_id = f.facilities_id. "
            "SELECT inmate name, ts.name AS current_status, f.facility, t.room, t.bed_number. "
            "Filter t.status = 1 AND ts.status = 1."
            f"{status_hint} "
            "Group by facility if 'facility wise' is mentioned. "
            "Do NOT join dg_notes or dg_notes_tags."
        )
    elif is_locate:
        context_parts.append(
            "LOCATION QUERY: Use dg_tags (NOT dg_tags_movement) to find current location. "
            "SELECT inmate_name, room, bed_number, current_status, facility FROM dg_tags "
            "with LEFT JOIN dg_tag_status ON role_call and LEFT JOIN dg_facilities. "
            "Do NOT join dg_tags_movement — this is NOT a movement query. "
            "Do NOT add facility filter. Search ALL facilities."
        )
    elif session and session.facility_ids:
        ids_str = ", ".join(str(fid) for fid in session.facility_ids)
        if is_inmate_direct:
            context_parts.append(
                "For inmate/movement/status queries: query dg_tags, dg_tags_movement directly. "
                "Do NOT join dg_notes or dg_notes_tags unless notes content is needed. "
                "Do NOT add facility filter. Search across ALL facilities."
            )
        elif is_login_query:
            pass
        else:
            context_parts.append(
                f"User's facility scope: n.facilities_id IN ({ids_str}). "
                "Apply this filter when querying dg_notes."
            )

    has_specific_date = bool(re.search(
        r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{4}\b"
        r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2},?\s+\d{4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b",
        question, re.IGNORECASE,
    ))
    if has_specific_date:
        context_parts.append(
            "DATE FILTER: When filtering by a specific date, use DATE(n.date_added) = 'YYYY-MM-DD', "
            "NOT n.date_added = 'YYYY-MM-DD' (since date_added is datetime, exact match will miss records)."
        )

    context_parts.append(f"Question: {question}")

    return "\n\n".join(context_parts)


def build_response_prompt(question: str, sql: str, row_count: int, sample_data: str) -> str:
    return (
        f"The officer asked: \"{question}\"\n\n"
        f"SQL executed: {sql}\n"
        f"Rows returned: {row_count}\n\n"
        f"Sample data:\n{sample_data}\n\n"
        "Provide a concise summary (2-3 sentences) of the results. "
        "Highlight key numbers, patterns, or safety concerns. "
        "If no data was returned, explain what that means."
    )


def _build_user_context(session: Session) -> str:
    parts = [
        f"User: {session.user_id}",
        f"Role: {session.role}",
        f"Tenant: {session.customer_key}",
    ]

    if session.facility_ids:
        parts.append(f"Facility scope: {session.facility_ids}")

    return "User context: " + " | ".join(parts)
