"""
Response Formatter — Converts raw query results into natural, officer-friendly responses.

This module provides two approaches:
1. Template-based formatting (sync, fast, for simple queries)
2. LLM-summarized formatting (async, for complex multi-row results)

The LLM approach uses InsightExtractor to compute stats from rows, then
ResponseSummarizer to polish them into natural language. This gives accurate
numbers (from code) with engaging summaries (from LLM).

Design:
  - Template functions remain for backward compatibility and simple cases
  - Async functions provide LLM-enhanced summaries for better UX
  - InsightExtractor ensures numbers are never hallucinated
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime
from typing import Any, AsyncGenerator

from src.shared.constants import HIGHLIGHTER_MAP, INTERNAL_COLUMNS, SENSITIVE_COLUMNS
from src.shared.logger import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  ASYNC LLM-ENHANCED FORMATTERS (Option 3: Pre-computed Insights + LLM Polish)
# ═══════════════════════════════════════════════════════════════════════════════


async def format_response_with_insights(
    rows: list[dict[str, Any]],
    question: str,
    sql: str,
    customer_key: str | None = None,
) -> dict[str, Any]:
    """
    Format response using insight extraction + LLM summarization.

    This is the primary formatter for complex queries. It:
    1. Extracts structured insights from rows (fast, deterministic)
    2. Sends insights to LLM for natural language summary (~1s)
    3. Returns a dense, officer-friendly summary

    For simple count queries, skips LLM entirely for speed.
    """
    from src.pipelines.inmate_data.insight_extractor import InsightExtractor
    from src.pipelines.inmate_data.response_summarizer import ResponseSummarizer

    # Filter sensitive columns first
    filtered = _filter_columns(rows)

    # Extract insights
    extractor = InsightExtractor()
    insights = extractor.extract(filtered, question)

    logger.debug(
        "Insights extracted: type=%s, count=%d, categories=%d",
        insights.query_type,
        insights.total_count,
        len(insights.top_categories),
    )

    # Generate summary
    summarizer = ResponseSummarizer(customer_key=customer_key)
    summary = await summarizer.summarize(insights, question)

    # Include first 100 rows for API consumers
    display_rows = filtered[:100] if len(filtered) > 100 else filtered

    return {
        "summary": summary,
        "row_count": len(rows),
        "truncated": len(rows) > 100,
        "insights": {
            "type": insights.query_type,
            "red_flags": insights.red_flag_count,
        },
        "rows": display_rows,
    }


async def format_response_stream(
    rows: list[dict[str, Any]],
    question: str,
    sql: str,
    customer_key: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream response generation for SSE.

    Yields status events during insight extraction, then streams
    the LLM-generated summary token by token.
    """
    from src.pipelines.inmate_data.insight_extractor import InsightExtractor
    from src.pipelines.inmate_data.response_summarizer import ResponseSummarizer

    yield {"event": "status", "data": "Analyzing results..."}

    # Filter and extract insights
    filtered = _filter_columns(rows)
    extractor = InsightExtractor()
    insights = extractor.extract(filtered, question)

    logger.debug(
        "Streaming insights: type=%s, count=%d",
        insights.query_type,
        insights.total_count,
    )

    yield {"event": "status", "data": "Generating summary..."}

    # Stream the summary
    summarizer = ResponseSummarizer(customer_key=customer_key)
    full_summary = ""

    async for token in summarizer.summarize_stream(insights, question):
        full_summary += token
        yield {"event": "token", "data": token}

    # Final result
    yield {
        "event": "result",
        "data": {
            "summary": full_summary,
            "row_count": len(rows),
            "truncated": len(rows) > 100,
            "insights": {
                "type": insights.query_type,
                "red_flags": insights.red_flag_count,
            },
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  SYNC TEMPLATE-BASED FORMATTERS (Legacy, fast fallback)
# ═══════════════════════════════════════════════════════════════════════════════


def format_data_response(
    rows: list[dict[str, Any]], question: str, sql: str,
) -> dict[str, Any]:
    """Legacy sync formatter using templates. Use format_response_with_insights for better UX."""
    filtered = _filter_columns(rows)
    summary = _smart_summary(filtered, question)
    return {
        "summary": summary,
        "row_count": len(rows),
        "truncated": len(rows) > 100,
    }


def format_analytics_response(
    rows: list[dict[str, Any]], question: str, sql: str,
) -> dict[str, Any]:
    """Legacy sync formatter for analytics queries."""
    summary = _smart_summary(rows, question)
    return {
        "summary": summary,
        "row_count": len(rows),
    }


def format_error_response(error: str, question: str) -> dict[str, Any]:
    friendly = error
    if "not related" in error.lower():
        friendly = (
            "I couldn't find data matching that question. "
            "Could you rephrase with more detail about what you're looking for?"
        )
    elif "sql" in error.lower():
        friendly = (
            "I had trouble understanding that question. Try rephrasing — "
            "for example, 'show notes for inmate John in last 7 days'."
        )
    return {"summary": friendly, "row_count": 0}


def format_empty_response(question: str, sql: str) -> dict[str, Any]:
    skip_words = {
        "movement", "notes", "entries", "log", "watch", "round", "meal",
        "security", "inventory", "medical", "all", "active", "inactive",
        "status", "last", "today", "yesterday", "this", "the", "in",
    }
    name_match = re.search(
        r"(?:inmate|officer)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)", question, re.IGNORECASE,
    )
    if name_match and name_match.group(1).lower().split()[0] not in skip_words:
        hint = f'No records found for "{name_match.group(1)}". Check the spelling or try a partial name.'
    elif re.search(r"(today|last\s+\d+\s+hour)", question, re.IGNORECASE):
        hint = "No results for that timeframe. Try a wider date range (e.g., last 7 days)."
    else:
        hint = "No results found. Try broadening the date range or adjusting your search terms."
    return {"summary": hint, "row_count": 0}


# ---------------------------------------------------------------------------
#  Smart summary engine
# ---------------------------------------------------------------------------

def _smart_summary(rows: list[dict[str, Any]], question: str) -> str:
    if not rows:
        return "No matching records."
    cols = _lower_keys(rows[0])
    qtype = _detect_type(rows, cols, question)

    formatters = {
        "count": _fmt_count,
        "ranked": _fmt_ranked,
        "movement": _fmt_movement,
        "status_change": _fmt_status_changes,
        "notes": _fmt_notes,
        "inmates": _fmt_inmates,
        "officers": _fmt_officers,
        "facilities": _fmt_facilities,
    }
    fn = formatters.get(qtype, _fmt_generic)
    if fn in (_fmt_facilities,):
        return fn(rows)
    return fn(rows, question)


def _detect_type(
    rows: list[dict[str, Any]], cols: set[str], question: str,
) -> str:
    if len(rows) == 1 and _is_aggregate(rows[0]):
        return "count"
    if _has_count_col(rows) and len(rows) <= 100:
        return "ranked"
    if cols & {"old_room", "new_room", "old_facilities_id", "new_facilities_id", "tags_movement_id"}:
        return "movement"
    if ("status" in cols or "status_name" in cols or "tag_status_name" in cols) and "notes_description" not in cols:
        if cols & {"note_date", "date_added", "inmate_name", "emp_first_name"}:
            return "status_change"
    if cols & {"notes_description", "notes_id", "note_date"}:
        return "notes"
    if cols & {"emp_first_name", "emp_last_name", "inmate_name"}:
        return "inmates"
    if (cols & {"firstname", "lastname", "first_name", "last_name"}) and "notes_id" not in cols:
        return "officers"
    if (cols & {"facility_name", "facility"}) and "notes_id" not in cols:
        return "facilities"
    return "generic"


# --------------- COUNT ---------------

def _fmt_count(rows: list[dict[str, Any]], question: str) -> str:
    row = rows[0]
    q_lower = question.lower()
    parts = []
    for k, v in row.items():
        parts.append((k, v))

    subject = "notes" if "note" in q_lower else "records"
    if re.search(r"(movement|transfer|move)", q_lower):
        subject = "movements"
    elif re.search(r"(inmate|prisoner)", q_lower):
        subject = "inmates"

    if len(parts) == 1:
        label, val = parts[0]
        val_str = _fmt_num(val) if isinstance(val, (int, float)) else str(val)
        if "how many" in q_lower or "count" in q_lower or "total" in q_lower:
            time_ctx = _extract_time_phrase(question)
            return f"There are **{val_str}** {subject}{time_ctx}."
        return f"**{val_str}** {subject}."

    lines = []
    for label, val in parts:
        nice_label = label.replace("_", " ").replace("count(*)", "total").title()
        lines.append(f"• **{nice_label}**: {_fmt_num(val)}")
    return "\n".join(lines)


# --------------- RANKED LIST ---------------

def _fmt_ranked(rows: list[dict[str, Any]], question: str) -> str:
    count_key = _find_count_key(rows[0])
    total = sum(_safe_int(r.get(count_key, 0)) for r in rows)
    name_keys = {
        "firstname", "lastname", "first_name", "last_name", "username",
        "emp_first_name", "emp_last_name", "inmate_name", "keyword_name",
    }

    time_ctx = _extract_time_phrase(question)
    subject = _extract_subject(question)
    intro = f"Here are the top **{len(rows)} {subject}** by activity{time_ctx}, totaling **{_fmt_num(total)}** entries."

    lines = [intro, ""]
    show = min(len(rows), 15)
    for i, r in enumerate(rows[:show], 1):
        name = _extract_display_name(r, name_keys, count_key) or f"#{i}"
        cnt = _safe_int(r.get(count_key, 0))
        bar = _bar(cnt, _safe_int(rows[0].get(count_key, 1)))
        lines.append(f"{i}. **{name}** — {_fmt_num(cnt)} {bar}")

    if len(rows) > show:
        lines.append(f"\n+{len(rows) - show} more")
    return "\n".join(lines)


# --------------- NOTES ---------------

def _fmt_notes(rows: list[dict[str, Any]], question: str) -> str:
    n = len(rows)
    dates = _extract_dates(rows, "note_date", "date_added")
    time_ctx = _extract_time_phrase(question)

    date_range = ""
    if dates:
        oldest, newest = min(dates), max(dates)
        if oldest != newest:
            date_range = f" from **{_fmt_date(oldest)}** to **{_fmt_date(newest)}**"
        else:
            date_range = f" on **{_fmt_date(oldest)}**"

    intro = f"Found **{_fmt_num(n)} note{'s' if n != 1 else ''}**{date_range}{time_ctx}."

    lines: list[str] = [intro]

    kw_counts = _count_field(rows, "keyword_name")
    if kw_counts:
        top_kw = kw_counts.most_common(5)
        kw_str = ", ".join(f"**{k}** ({v})" for k, v in top_kw)
        lines.append(f"Categories: {kw_str}")

    user_counts = _count_field(rows, "officer_name")
    if not user_counts:
        for name_key in ("user_id", "username", "firstname"):
            user_counts = _count_field(rows, name_key)
            if user_counts:
                break
    if user_counts and len(user_counts) > 1:
        top_users = user_counts.most_common(3)
        u_str = ", ".join(f"**{k}** ({v})" for k, v in top_users)
        lines.append(f"Officers: {u_str}")

    show_count = min(n, 5)
    lines.append("")
    for r in rows[:show_count]:
        desc_raw = str(r.get("notes_description", ""))
        desc = desc_raw[:90]
        if len(desc_raw) > 90:
            desc += "..."
        dt = r.get("note_date") or r.get("date_added")
        dt_str = _fmt_datetime(dt)
        hl = r.get("highlighter") or ""
        hl_tag = " 🔴" if hl and "red" in str(hl).lower() else ""
        lines.append(f"• **{dt_str}** — {desc}{hl_tag}")

    if n > show_count:
        lines.append(f"\n+{n - show_count} more entries")
    return "\n".join(lines)


# --------------- MOVEMENT ---------------

def _fmt_movement(rows: list[dict[str, Any]], question: str) -> str:
    n = len(rows)
    time_ctx = _extract_time_phrase(question)

    unique_inmates = set()
    for r in rows:
        name = _get_inmate_name(r)
        if name and name.lower() != "inmate":
            unique_inmates.add(name)

    if len(unique_inmates) == 1:
        inmate = list(unique_inmates)[0]
        intro = f"**{inmate}** has **{_fmt_num(n)} movement{'s' if n != 1 else ''}** on record{time_ctx}."
    elif unique_inmates:
        intro = f"**{_fmt_num(n)} movement{'s' if n != 1 else ''}** across **{len(unique_inmates)} inmates**{time_ctx}."
    else:
        intro = f"**{_fmt_num(n)} movement{'s' if n != 1 else ''}** recorded{time_ctx}."

    lines = [intro, ""]
    show = min(n, 15)
    for r in rows[:show]:
        name = _get_inmate_name(r)
        old_fac = r.get("old_facility") or r.get("old_facilities_id") or "?"
        new_fac = r.get("new_facility") or r.get("new_facilities_id") or "?"
        old_rm = r.get("old_room") or "?"
        new_rm = r.get("new_room") or "?"
        dt = r.get("date_added")
        dt_str = _fmt_datetime(dt)

        if str(old_fac) != str(new_fac):
            move_detail = f"{old_fac} Rm {old_rm} → {new_fac} Rm {new_rm}"
        else:
            move_detail = f"Rm {old_rm} → Rm {new_rm} ({old_fac})"

        if len(unique_inmates) == 1:
            lines.append(f"• **{dt_str}** — {move_detail}")
        else:
            lines.append(f"• **{name}** — {move_detail} ({dt_str})")

    if n > show:
        lines.append(f"\n+{n - show} more movements")
    return "\n".join(lines)


# --------------- STATUS CHANGES ---------------

def _fmt_status_changes(rows: list[dict[str, Any]], question: str) -> str:
    n = len(rows)
    time_ctx = _extract_time_phrase(question)
    statuses = _count_field(rows, "status") or _count_field(rows, "status_name") or _count_field(rows, "tag_status_name")

    intro = f"**{_fmt_num(n)} status change{'s' if n != 1 else ''}** recorded{time_ctx}."
    if statuses:
        top_s = statuses.most_common(3)
        s_str = ", ".join(f"**{k}** ({v})" for k, v in top_s)
        intro += f"\nTop statuses: {s_str}"

    lines = [intro, ""]
    for r in rows[:15]:
        name = _get_inmate_name(r) or ""
        status = r.get("status") or r.get("status_name") or r.get("tag_status_name") or "?"
        dt = r.get("note_date") or r.get("date_added")
        dt_str = _fmt_datetime(dt)
        name_part = f"**{name}** — " if name else ""
        lines.append(f"• {name_part}**{status}** ({dt_str})")

    if n > 15:
        lines.append(f"\n+{n - 15} more changes")
    return "\n".join(lines)


# --------------- INMATES ---------------

def _fmt_inmates(rows: list[dict[str, Any]], question: str) -> str:
    n = len(rows)
    fac_counts = _count_field(rows, "facility") or _count_field(rows, "facility_name")
    status_counts = (
        _count_field(rows, "current_status")
        or _count_field(rows, "status_name")
        or _count_field(rows, "tag_status_name")
        or _count_field(rows, "name")
    )

    if n == 1:
        intro = "Here's the inmate info:"
    else:
        intro = f"Found **{_fmt_num(n)} inmate{'s' if n != 1 else ''}** matching your query."
    if fac_counts and len(fac_counts) > 1 and max(fac_counts.values()) > 1:
        fac_str = ", ".join(f"**{k}** ({v})" for k, v in fac_counts.most_common(5))
        intro += f"\nBy facility: {fac_str}"
    elif fac_counts and len(fac_counts) > 1 and len(fac_counts) < n:
        intro += f" Across **{len(fac_counts)}** facilities."
    if status_counts and len(status_counts) > 1 and max(status_counts.values()) > 1:
        s_str = ", ".join(f"**{k}** ({v})" for k, v in status_counts.most_common(3))
        intro += f"\nStatuses: {s_str}"

    lines = [intro, ""]
    show = min(n, 20)
    for r in rows[:show]:
        combined = r.get("inmate_name")
        if combined:
            name = f"**{_clean_name(str(combined))}**"
        else:
            first = _clean_name(r.get("emp_first_name", ""))
            last = _clean_name(r.get("emp_last_name", ""))
            name = f"**{first} {last}**".strip() if (first or last) else "Unknown"

        detail_parts = []
        fac = r.get("facility") or r.get("facility_name")
        if fac:
            detail_parts.append(str(fac))
        cell = r.get("room") or r.get("cell_no") or r.get("room_no")
        if cell and str(cell) != "0":
            detail_parts.append(f"Rm {cell}")
        bed = r.get("bed_number") or r.get("bed_no")
        if bed and str(bed) != "0":
            detail_parts.append(f"Bed {bed}")
        status = (
            r.get("current_status") or r.get("status_name")
            or r.get("tag_status_name") or r.get("name")
        )
        if status and str(status).lower() not in ("none", "0", "null"):
            detail_parts.append(str(status))
        detail = " · ".join(detail_parts) if detail_parts else ""
        lines.append(f"• {name} — {detail}" if detail else f"• {name}")

    if n > show:
        lines.append(f"\n+{n - show} more inmates")
    return "\n".join(lines)


# --------------- OFFICERS ---------------

def _fmt_officers(rows: list[dict[str, Any]], question: str) -> str:
    n = len(rows)
    lines = [f"Found **{_fmt_num(n)} officer{'s' if n != 1 else ''}**.", ""]
    for r in rows[:20]:
        first = r.get("firstname") or r.get("first_name", "")
        last = r.get("lastname") or r.get("last_name", "")
        uname = r.get("username", "")
        name = f"**{first} {last}**".strip() if (first or last) else f"{uname or '?'}"
        parts = []
        fac = r.get("facility") or r.get("facility_name") or r.get("default_facilities_id")
        if fac:
            parts.append(str(fac))
        cnt = (
            r.get("note_count") or r.get("notes_count") or r.get("total_notes")
            or r.get("cnt") or r.get("total")
        )
        if cnt:
            parts.append(f"{cnt} notes")
        detail = " · ".join(parts)
        lines.append(f"• {name} — {detail}" if detail else f"• {name}")
    if n > 20:
        lines.append(f"\n+{n - 20} more")
    return "\n".join(lines)


# --------------- FACILITIES ---------------

def _fmt_facilities(rows: list[dict[str, Any]]) -> str:
    n = len(rows)
    lines = [f"There are **{_fmt_num(n)} facilit{'y' if n == 1 else 'ies'}** on record.", ""]
    for r in rows[:25]:
        name = r.get("facility") or r.get("facility_name") or r.get("facilities_id") or "?"
        lines.append(f"• {name}")
    if n > 25:
        lines.append(f"\n+{n - 25} more")
    return "\n".join(lines)


# --------------- GENERIC ---------------

def _fmt_generic(rows: list[dict[str, Any]], question: str) -> str:
    n = len(rows)
    lines = [f"Found **{_fmt_num(n)} record{'s' if n != 1 else ''}**.", ""]
    show = min(n, 15)
    cols_info = list(rows[0].keys())[:6]
    for r in rows[:show]:
        vals = [f"{_fmt_val(r.get(c))}" for c in cols_info]
        lines.append(f"• {' · '.join(v for v in vals if v != '-')}")
    if n > show:
        lines.append(f"\n+{n - show} more")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _get_inmate_name(row: dict[str, Any]) -> str:
    combined = row.get("inmate_name")
    if combined and str(combined).strip():
        return _clean_name(str(combined))
    first = _clean_name(row.get("emp_first_name", ""))
    last = _clean_name(row.get("emp_last_name", ""))
    if first or last:
        return f"{first} {last}".strip()
    return "Inmate"


def _extract_time_phrase(question: str) -> str:
    m = re.search(
        r"((?:in\s+)?(?:last|past)\s+\d+\s+(?:day|week|month|hour|year)s?"
        r"|this\s+(?:week|month|year)"
        r"|today|yesterday"
        r"|(?:in\s+)?(?:last|past)\s+(?:week|month|year))",
        question, re.IGNORECASE,
    )
    if m:
        phrase = m.group(0).strip()
        if not phrase.lower().startswith("in "):
            phrase = "in the " + phrase if phrase.lower().startswith("last") else phrase
        return f" {phrase}"
    return ""


def _extract_subject(question: str) -> str:
    if re.search(r"officer|user", question, re.IGNORECASE):
        return "officers"
    if re.search(r"inmate|prisoner", question, re.IGNORECASE):
        return "inmates"
    if re.search(r"keyword|categor", question, re.IGNORECASE):
        return "keywords"
    if re.search(r"facilit", question, re.IGNORECASE):
        return "facilities"
    return "results"


def _extract_display_name(row: dict[str, Any], name_keys: set[str], skip_key: str) -> str:
    first = row.get("firstname") or row.get("first_name") or row.get("emp_first_name") or ""
    last = row.get("lastname") or row.get("last_name") or row.get("emp_last_name") or ""
    if first or last:
        return _clean_name(f"{first} {last}".strip())
    combined = row.get("inmate_name") or row.get("keyword_name") or row.get("username")
    if combined:
        return _clean_name(str(combined))
    for k, v in row.items():
        if k != skip_key and k not in name_keys and v is not None and str(v).strip():
            return str(v)
    return ""


def _clean_name(val: str) -> str:
    if not val:
        return ""
    s = str(val).strip()
    return s.title() if s == s.upper() and len(s) > 1 else s


def _filter_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    excluded = SENSITIVE_COLUMNS | INTERNAL_COLUMNS
    allowed_keys = [k for k in rows[0].keys() if k.lower() not in excluded]
    result = []
    for row in rows:
        filtered: dict[str, Any] = {}
        for key in allowed_keys:
            val = row.get(key)
            if key == "highlighter_id" and isinstance(val, int):
                filtered["highlighter"] = HIGHLIGHTER_MAP.get(val, str(val))
            else:
                filtered[key] = _serialize_value(val)
        result.append(filtered)
    return result


def _serialize_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (int, float, str, bool)):
        return val
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _lower_keys(row: dict[str, Any]) -> set[str]:
    return {k.lower() for k in row.keys()}


def _is_aggregate(row: dict[str, Any]) -> bool:
    for k in row.keys():
        kl = k.lower()
        if any(w in kl for w in ("count", "total", "sum", "avg", "min", "max")):
            return True
    if len(row) <= 2 and all(isinstance(v, (int, float)) for v in row.values()):
        return True
    return False


def _has_count_col(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    _COUNT_NAMES = {
        "cnt", "count", "total", "note_count", "notes_count", "total_notes",
        "count(*)", "movement_count", "entry_count", "record_count",
    }
    for k in rows[0].keys():
        if k.lower() in _COUNT_NAMES or k.lower().endswith("_count") or k.lower().endswith("_total"):
            return True
    return False


def _find_count_key(row: dict[str, Any]) -> str:
    _COUNT_NAMES = {
        "cnt", "count", "total", "note_count", "notes_count", "total_notes",
        "count(*)", "movement_count", "entry_count", "record_count",
    }
    for k in row.keys():
        if k.lower() in _COUNT_NAMES or k.lower().endswith("_count") or k.lower().endswith("_total"):
            return k
    for k, v in row.items():
        if isinstance(v, (int, float)):
            return k
    return list(row.keys())[-1]


def _find_label_key(row: dict[str, Any], count_key: str) -> str:
    for k in row.keys():
        if k != count_key:
            return k
    return list(row.keys())[0]


def _count_field(rows: list[dict[str, Any]], field: str) -> Counter:
    c: Counter = Counter()
    for r in rows:
        val = r.get(field)
        if val is not None and str(val).strip():
            c[str(val)] += 1
    return c


def _extract_dates(rows: list[dict[str, Any]], *fields: str) -> list[date]:
    dates: list[date] = []
    for r in rows:
        for f in fields:
            v = r.get(f)
            if isinstance(v, datetime):
                dates.append(v.date())
            elif isinstance(v, date):
                dates.append(v)
            elif isinstance(v, str) and len(v) >= 10:
                try:
                    dates.append(datetime.fromisoformat(v[:10]).date())
                except ValueError:
                    pass
    return dates


def _safe_int(val: Any) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _fmt_num(val: Any) -> str:
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def _fmt_val(val: Any) -> str:
    if val is None:
        return "-"
    if hasattr(val, "strftime"):
        return val.strftime("%b %d, %Y %I:%M %p") if hasattr(val, "hour") else val.strftime("%b %d, %Y")
    s = str(val)
    return s[:80] + "..." if len(s) > 80 else s


def _fmt_date(d: date) -> str:
    return d.strftime("%b %d")


def _fmt_datetime(dt: Any) -> str:
    if hasattr(dt, "strftime"):
        if hasattr(dt, "hour"):
            return dt.strftime("%b %d, %I:%M %p")
        return dt.strftime("%b %d")
    if isinstance(dt, str) and len(dt) >= 10:
        try:
            parsed = datetime.fromisoformat(dt[:19])
            return parsed.strftime("%b %d, %I:%M %p")
        except ValueError:
            return dt[:10]
    return str(dt) if dt else ""


def _bar(val: int, max_val: int, width: int = 8) -> str:
    if max_val <= 0:
        return ""
    filled = max(1, round(val / max_val * width))
    return "\u2588" * filled + "\u2591" * (width - filled)


def rows_to_sample_text(rows: list[dict[str, Any]], max_rows: int = 5) -> str:
    if not rows:
        return "No data."
    sample = rows[:max_rows]
    return json.dumps(sample, indent=2, default=str)[:2000]
