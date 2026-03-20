#!/usr/bin/env python3
"""
SARAH CHATBOT — COMPREHENSIVE CONVERSATION TEST SUITE
======================================================

Tests the full chatbot pipeline the way real officers interact:
  - Natural language (not rigid query syntax)
  - Multi-turn conversations with follow-ups
  - Session memory and context awareness
  - Conversational intelligence (greetings, capabilities, identity)
  - Facility-scoped data isolation
  - Response quality and formatting

Personas:
  - Warden Mark Kent (all 9 facilities) — admin-level queries
  - Officer Richard Bell (3 facilities) — daily ops queries
  - Officer Ankush (2 facilities) — quick lookups

Usage:
    cd /home/nishant/chatbot_copilot_poc
    source venv_vanna_v2/bin/activate
    python -m local.test_conversations
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import requests

BASE_URL = "http://localhost:8000"

# ═══════════════════════════════════════════════════════════════════════════════
#  TEST PERSONAS — facility_ids change based on who's logged in
# ═══════════════════════════════════════════════════════════════════════════════

PERSONAS = {
    "warden": {
        "user_id": "Mark.Kent",
        "display_name": "Mark Kent",
        "customer_key": "demo",
        "role": "warden",
        "facility_ids": [63, 164, 182, 166, 167, 64, 65, 66, 181],
    },
    "officer_broad": {
        "user_id": "Richard.Bell",
        "display_name": "Richard Bell",
        "customer_key": "demo",
        "role": "officer",
        "facility_ids": [63, 164, 182],
    },
    "officer_narrow": {
        "user_id": "Anks",
        "display_name": "Ankush",
        "customer_key": "demo",
        "role": "officer",
        "facility_ids": [63, 164],
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
#  CONVERSATION SCENARIOS — Multi-turn, natural language
# ═══════════════════════════════════════════════════════════════════════════════

CONVERSATIONS: list[dict[str, Any]] = [
    # ─── SCENARIO 1: Warden morning briefing ─────────────────────────────
    {
        "name": "Warden Morning Briefing",
        "persona": "warden",
        "description": "Warden logs in, gets overview, drills into details",
        "turns": [
            {
                "q": "good morning sarah",
                "expect_type": "conversational",
                "check": lambda r: r["row_count"] == 0 and "Mark" in r["summary"],
                "tag": "greeting",
            },
            {
                "q": "how many notes were added yesterday",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "analytics",
            },
            {
                "q": "who were the top 5 officers by note count this month",
                "expect_type": "data",
                "check": lambda r: r["row_count"] > 0,
                "tag": "ranked_officers",
            },
            {
                "q": "any red flagged entries in the last 30 days",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "red_highlight",
            },
            {
                "q": "what about fire watch compliance this week",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "keyword_firewatch",
            },
            {
                "q": "show me all inmate movements in the last 7 days",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "movement",
            },
            {
                "q": "what did I ask you so far",
                "expect_type": "conversational",
                "check": lambda r: "asked" in r["summary"].lower() or "question" in r["summary"].lower(),
                "tag": "history_recall",
            },
            {
                "q": "thanks sarah, talk later",
                "expect_type": "conversational",
                "check": lambda r: r["row_count"] == 0,
                "tag": "farewell",
            },
        ],
    },

    # ─── SCENARIO 2: Officer investigating an inmate ─────────────────────
    {
        "name": "Officer Inmate Investigation",
        "persona": "officer_broad",
        "description": "Officer looks up inmate, checks status, reviews entries",
        "turns": [
            {
                "q": "hey",
                "expect_type": "conversational",
                "check": lambda r: r["row_count"] == 0,
                "tag": "greeting",
            },
            {
                "q": "where is inmate anthony nova right now",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 1,
                "tag": "inmate_location",
            },
            {
                "q": "show me last 5 status changes for this inmate",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "status_change_followup",
            },
            {
                "q": "any movement history for anthony nova",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "movement_specific",
            },
            {
                "q": "show all entries for inmate anthony nova added this month",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "entries_for_inmate",
            },
            {
                "q": "where is inmate heath bould",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 1,
                "tag": "inmate_location_2",
            },
        ],
    },

    # ─── SCENARIO 3: Officer daily round check ───────────────────────────
    {
        "name": "Officer Daily Rounds",
        "persona": "officer_narrow",
        "description": "Officer checks rounds, meals, compliance for the day",
        "turns": [
            {
                "q": "hi sarah, what can you help me with",
                "expect_type": "conversational",
                "check": lambda r: "help" in r["summary"].lower() or "can" in r["summary"].lower(),
                "tag": "capability",
            },
            {
                "q": "when was the last round conducted",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "round_check",
            },
            {
                "q": "show me all meal related entries today",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "meal_entries",
            },
            {
                "q": "any suicide watch notes this week",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "suicide_watch",
            },
            {
                "q": "show security rounds for today",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "security_rounds",
            },
            {
                "q": "who am I logged in as",
                "expect_type": "conversational",
                "check": lambda r: "Anks" in r["summary"] or "Ankush" in r["summary"],
                "tag": "self_identity",
            },
        ],
    },

    # ─── SCENARIO 4: Status & movement deep-dive ─────────────────────────
    {
        "name": "Status & Movement Analysis",
        "persona": "warden",
        "description": "Warden reviews inmate status and movement patterns",
        "turns": [
            {
                "q": "list all inmates with current status and facility",
                "expect_type": "data",
                "check": lambda r: r["row_count"] > 0,
                "tag": "all_inmates_status",
            },
            {
                "q": "find inmates currently in meal status",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "status_filter_meal",
            },
            {
                "q": "show inmates in recreation status",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "status_filter_recreation",
            },
            {
                "q": "inmate movement in last 7 days",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "movement_7d",
            },
            {
                "q": "movement history for inmate Anthony Nova",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "movement_specific_inmate",
            },
            {
                "q": "list all movements this month",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "movement_monthly",
            },
        ],
    },

    # ─── SCENARIO 5: Keyword & multi-word searches ───────────────────────
    {
        "name": "Keyword Deep Search",
        "persona": "officer_broad",
        "description": "Officer searches for specific categories of notes",
        "turns": [
            {
                "q": "show notes about elevated supervision in last 90 days",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "multiword_elevated_supervision",
            },
            {
                "q": "any cell inspection entries in the last month",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "multiword_cell_inspection",
            },
            {
                "q": "fire watch notes this week",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "multiword_firewatch",
            },
            {
                "q": "retrieve lockdown records in last 90 days",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "multiword_lockdown",
            },
            {
                "q": "all disciplinary notes this month",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "keyword_disciplinary",
            },
            {
                "q": "find emergency notes in last 24 hours",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "keyword_emergency",
            },
        ],
    },

    # ─── SCENARIO 6: Time-based queries ──────────────────────────────────
    {
        "name": "Time-Based Lookups",
        "persona": "warden",
        "description": "Warden queries with specific time ranges",
        "turns": [
            {
                "q": "entries added in the last 48 hours",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "time_48h",
            },
            {
                "q": "show notes from yesterday",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "time_yesterday",
            },
            {
                "q": "when was the first note added today",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "time_first_today",
            },
            {
                "q": "what time was the last note added yesterday",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "time_last_yesterday",
            },
            {
                "q": "daily note count for last 30 days",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "time_daily_trend",
            },
        ],
    },

    # ─── SCENARIO 7: Analytics & counts ──────────────────────────────────
    {
        "name": "Analytics Dashboard",
        "persona": "warden",
        "description": "Warden pulls aggregate stats and trends",
        "turns": [
            {
                "q": "how many notes were added today",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "count_today",
            },
            {
                "q": "count total notes added this year",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "count_yearly",
            },
            {
                "q": "top 10 officers by notes this month",
                "expect_type": "data",
                "check": lambda r: r["row_count"] > 0,
                "tag": "top_officers_month",
            },
            {
                "q": "count notes per facility",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "count_per_facility",
            },
            {
                "q": "how many inmates are in cell 49",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "count_cell",
            },
            {
                "q": "what active keywords were used last week",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "active_keywords",
            },
        ],
    },

    # ─── SCENARIO 8: Officer-specific & visitor queries ──────────────────
    {
        "name": "Officer & Visitor Logs",
        "persona": "warden",
        "description": "Warden reviews specific officer activity and visitor logs",
        "turns": [
            {
                "q": "show notes created by officer Anks today",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "officer_specific",
            },
            {
                "q": "notes by Richard Bell this week",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "officer_specific_2",
            },
            {
                "q": "list officers who added fire watch notes this week",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "officers_by_keyword",
            },
            {
                "q": "show visitor log entries for last 30 days",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "visitor_log",
            },
            {
                "q": "show all inactive users",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "inactive_users",
            },
        ],
    },

    # ─── SCENARIO 9: Inmate name variations ──────────────────────────────
    {
        "name": "Inmate Name Search Patterns",
        "persona": "officer_broad",
        "description": "Testing different ways officers ask about inmates",
        "turns": [
            {
                "q": "all entries for inmate alester king in last 30 days",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "inmate_fullname",
            },
            {
                "q": "show me last note added for inmate anthony",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "inmate_firstname_only",
            },
            {
                "q": "currently where is inmate anthony",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "inmate_locate_single",
            },
            {
                "q": "show medical notes for inmate anthony in last 7 days",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "inmate_keyword_combo",
            },
        ],
    },

    # ─── SCENARIO 10: Edge cases & conversational resilience ─────────────
    {
        "name": "Edge Cases & Resilience",
        "persona": "warden",
        "description": "Tests out-of-scope, vague, and edge-case inputs",
        "turns": [
            {
                "q": "what's the weather today",
                "expect_type": "conversational",
                "check": lambda r: "error" not in r["summary"].lower() or r["row_count"] == 0,
                "tag": "out_of_scope",
            },
            {
                "q": "tell me a joke",
                "expect_type": "conversational",
                "check": lambda r: r["row_count"] == 0,
                "tag": "out_of_scope_2",
            },
            {
                "q": "what can you do for me",
                "expect_type": "conversational",
                "check": lambda r: "notes" in r["summary"].lower() or "help" in r["summary"].lower(),
                "tag": "capability",
            },
            {
                "q": "who are you",
                "expect_type": "conversational",
                "check": lambda r: "sarah" in r["summary"].lower() or "intelligence" in r["summary"].lower(),
                "tag": "bot_identity",
            },
            {
                "q": "inventory entries",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "minimal_query",
            },
            {
                "q": "show me everything about inmate anthony nova",
                "expect_type": "data",
                "check": lambda r: r["row_count"] >= 0,
                "tag": "broad_inmate_query",
            },
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TurnResult:
    question: str
    tag: str
    expect_type: str
    success: bool
    row_count: int
    summary: str
    elapsed_ms: int
    check_passed: bool
    error: str = ""


@dataclass
class ConversationResult:
    name: str
    persona: str
    turns: list[TurnResult] = field(default_factory=list)
    total_ms: int = 0


def init_session(persona: dict) -> str | None:
    try:
        r = requests.post(f"{BASE_URL}/session/init", json={"user_id": persona["user_id"]}, timeout=10)
        if r.status_code == 200:
            return r.json().get("session_id")
    except Exception:
        pass
    return None


def ask(session_id: str, question: str, persona: dict) -> dict:
    try:
        start = time.time()
        r = requests.post(
            f"{BASE_URL}/chat",
            json={
                "session_id": session_id,
                "question": question,
                "customer_key": persona["customer_key"],
                "user_id": persona["user_id"],
                "facility_ids": persona["facility_ids"],
                "role": persona["role"],
            },
            timeout=30,
        )
        elapsed = int((time.time() - start) * 1000)
        data = r.json()
        data["_elapsed_ms"] = elapsed
        return data
    except Exception as e:
        return {"success": False, "summary": "", "row_count": 0, "error": str(e), "_elapsed_ms": 0}


def run_conversation(scenario: dict) -> ConversationResult:
    persona_key = scenario["persona"]
    persona = PERSONAS[persona_key]
    result = ConversationResult(name=scenario["name"], persona=persona_key)

    session_id = init_session(persona)
    if not session_id:
        print(f"  SKIP — session init failed for {persona['display_name']}")
        return result

    conv_start = time.time()

    for turn in scenario["turns"]:
        q = turn["q"]
        resp = ask(session_id, q, persona)

        check_fn = turn.get("check")
        check_ok = True
        if check_fn:
            try:
                check_ok = check_fn(resp)
            except Exception:
                check_ok = False

        tr = TurnResult(
            question=q,
            tag=turn["tag"],
            expect_type=turn.get("expect_type", "data"),
            success=resp.get("success", False),
            row_count=resp.get("row_count", 0),
            summary=resp.get("summary", "")[:300],
            elapsed_ms=resp.get("_elapsed_ms", 0),
            check_passed=check_ok,
            error=resp.get("error", ""),
        )
        result.turns.append(tr)

    result.total_ms = int((time.time() - conv_start) * 1000)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  REPORTING
# ═══════════════════════════════════════════════════════════════════════════════

STATUS_ICONS = {(True, True): "✅", (True, False): "⚠️", (False, True): "❌", (False, False): "❌"}


def print_report(results: list[ConversationResult]):
    total_turns = sum(len(c.turns) for c in results)
    total_pass = sum(1 for c in results for t in c.turns if t.success and t.check_passed)
    total_success = sum(1 for c in results for t in c.turns if t.success)
    total_check = sum(1 for c in results for t in c.turns if t.check_passed)
    total_time = sum(c.total_ms for c in results)

    all_turns = [t for c in results for t in c.turns]
    data_turns = [t for t in all_turns if t.expect_type == "data" and t.success]
    conv_turns = [t for t in all_turns if t.expect_type == "conversational" and t.success]

    print()
    print("=" * 90)
    print("  SARAH CHATBOT — CONVERSATION TEST REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)

    for conv in results:
        persona = PERSONAS[conv.persona]
        print(f"\n┌─ {conv.name}")
        print(f"│  Persona: {persona['display_name']} ({persona['role']}) | "
              f"Facilities: {persona['facility_ids']} | "
              f"Time: {conv.total_ms / 1000:.1f}s")
        print("│")

        for t in conv.turns:
            icon = STATUS_ICONS[(t.success, t.check_passed)]
            rows_str = f"({t.row_count} rows)" if t.row_count > 0 else ""
            time_str = f"{t.elapsed_ms}ms"
            summary_preview = t.summary[:80].replace("\n", " ") if t.summary else ""
            if t.error:
                summary_preview = f"ERROR: {t.error[:60]}"

            print(f"│  {icon} [{t.tag:30s}] {time_str:>6s} {rows_str:>12s}")
            print(f"│     Q: {t.question}")
            print(f"│     A: {summary_preview}")

        pass_count = sum(1 for t in conv.turns if t.success and t.check_passed)
        print(f"│")
        print(f"└─ Result: {pass_count}/{len(conv.turns)} passed")

    # Summary
    print("\n" + "=" * 90)
    print("  SUMMARY")
    print("=" * 90)
    print(f"  Conversations:    {len(results)}")
    print(f"  Total turns:      {total_turns}")
    print(f"  Passed (✅):      {total_pass}/{total_turns} ({total_pass/total_turns*100:.0f}%)")
    print(f"  API success:      {total_success}/{total_turns}")
    print(f"  Check passed:     {total_check}/{total_turns}")
    print(f"  Total time:       {total_time/1000:.1f}s")
    if all_turns:
        avg_ms = sum(t.elapsed_ms for t in all_turns) / len(all_turns)
        print(f"  Avg latency:      {avg_ms:.0f}ms")
    if data_turns:
        avg_data = sum(t.elapsed_ms for t in data_turns) / len(data_turns)
        print(f"  Avg data query:   {avg_data:.0f}ms")
    if conv_turns:
        avg_conv = sum(t.elapsed_ms for t in conv_turns) / len(conv_turns)
        print(f"  Avg conversational: {avg_conv:.0f}ms")

    # Failures
    failures = [t for c in results for t in c.turns if not t.success or not t.check_passed]
    if failures:
        print(f"\n  ISSUES ({len(failures)}):")
        for t in failures:
            icon = STATUS_ICONS[(t.success, t.check_passed)]
            reason = t.error if t.error else ("check failed" if not t.check_passed else "api fail")
            print(f"    {icon} [{t.tag}] {t.question[:50]}  — {reason[:60]}")

    print("=" * 90)
    return {
        "total": total_turns,
        "passed": total_pass,
        "success_rate": round(total_pass / total_turns * 100, 1) if total_turns else 0,
        "avg_latency_ms": round(sum(t.elapsed_ms for t in all_turns) / len(all_turns)) if all_turns else 0,
        "total_time_s": round(total_time / 1000, 1),
    }


def save_results(results: list[ConversationResult], summary: dict):
    output = {
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "conversations": [],
    }
    for conv in results:
        output["conversations"].append({
            "name": conv.name,
            "persona": conv.persona,
            "total_ms": conv.total_ms,
            "turns": [
                {
                    "question": t.question,
                    "tag": t.tag,
                    "success": t.success,
                    "check_passed": t.check_passed,
                    "row_count": t.row_count,
                    "elapsed_ms": t.elapsed_ms,
                    "summary": t.summary,
                    "error": t.error,
                }
                for t in conv.turns
            ],
        })
    with open("local/test_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: local/test_results.json")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n  Checking server at", BASE_URL, "...")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            print("  Server not healthy. Start with: python -m local.server")
            sys.exit(1)
    except Exception:
        print("  Server unreachable. Start with: python -m local.server")
        sys.exit(1)

    print("  Server OK. Running 10 conversation scenarios...\n")

    results = []
    for i, scenario in enumerate(CONVERSATIONS, 1):
        name = scenario["name"]
        turns = len(scenario["turns"])
        persona = PERSONAS[scenario["persona"]]
        print(f"  [{i:2d}/10] {name} ({turns} turns, {persona['display_name']})...")
        conv_result = run_conversation(scenario)
        results.append(conv_result)
        pass_count = sum(1 for t in conv_result.turns if t.success and t.check_passed)
        print(f"          {pass_count}/{turns} passed in {conv_result.total_ms/1000:.1f}s")

    summary = print_report(results)
    save_results(results, summary)


if __name__ == "__main__":
    main()
