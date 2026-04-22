"""
Intent Engine — Classifies user intent BEFORE the SQL pipeline.

Two-layer classification:
  Layer 1 (Pattern):  Fast regex/keyword matching for obvious intents (<1ms)
  Layer 2 (LLM):      GPT-4o-mini classification for ambiguous inputs (~200ms)

Intent types:
  DATA_QUERY      — Needs SQL generation + execution
  FOLLOW_UP       — Context-dependent data query (references prior turn)
  GENERAL_DOMAIN  — Domain question answerable without SQL
  CLARIFICATION   — Ambiguous input, ask user for details
  OUT_OF_SCOPE    — Not related to correctional operations
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.shared.logger import get_logger

logger = get_logger(__name__)


class Intent(str, Enum):
    DATA_QUERY = "data_query"
    FOLLOW_UP = "follow_up"
    GENERAL_DOMAIN = "general_domain"
    CLARIFICATION = "clarification"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    entities: dict[str, Any]
    rewritten_question: str
    reasoning: str = ""


# ── Layer 1: Pattern-based fast classification ────────────────────────────

_FOLLOW_UP_PATTERNS = re.compile(
    r"(show\s+me\s+more|tell\s+me\s+more|more\s+details?|expand\s+on"
    r"|drill\s+down|break\s*down|what\s+about|and\s+(also|what\s+about)"
    r"|for\s+the\s+same|same\s+(but|for|query)|now\s+show|now\s+filter"
    r"|narrow\s+(it\s+)?down|instead\s+of|from\s+those|among\s+those"
    r"|out\s+of\s+those|from\s+(?:that|these|this)|previous\s+result"
    r"|what\s+(did\s+)?i\s+ask|what\s+was\s+my|my\s+(earlier|previous|last)\s+question"
    r"|repeat\s+that|do\s+that\s+again|same\s+again|again\s+please"
    r"|\bthis\s+inmate\b|\bthat\s+inmate\b|\bfor\s+(?:him|her|them)\b"
    r"|\bthe\s+same\s+inmate\b|\btheir\s+\w+\b"
    r"|\blist\s+out\s+names?\b|\bshow\s+names?\b"
    r"|\bfor\s+(?:this|that|these|those)\b"
    # Possessive pronouns followed by any word (catches "his status", "her notes", etc.)
    r"|\b(?:his|her)\s+\w+"
    # Common follow-up starters with pronouns
    r"|(?:list|show|get|what\s+(?:is|are))\s+(?:his|her)\b)",
    re.IGNORECASE,
)

_DATA_SIGNALS = re.compile(
    r"(how\s+many|count|list|show|find|get|fetch|retrieve|display|all\b"
    r"|top\s+\d|last\s+\d|total|average|avg|max|min|between"
    r"|yesterday|today|this\s+week|this\s+month|last\s+\d+\s+(day|week|month|hour)"
    r"|note[s]?|entr(y|ies)|inmate[s]?|officer[s]?|facilit(y|ies)"
    r"|movement|status\s+change|fire\s*watch|suicide\s*watch|round[s]?"
    r"|keyword[s]?|highlight|red\s+mark|visitor|shift|meal"
    r"|security|inventory|disciplin|emergency|fight|room|cell|bed"
    r"|active\b|inactive\b|who\s+(added|created|entered)|when\s+was"
    r"|where\s+is|current\s*(ly|status|location)|locate\b|booking\s*(number|#|no)"
    r"|transfer|discharge|moved?\b|check\s+on)",
    re.IGNORECASE,
)

_OUT_OF_SCOPE_PATTERNS = re.compile(
    r"(weather|sports?|stock|recipe|movie|music|game|joke|story|poem"
    r"|translate|calculate|math|homework|code\s+me|write\s+a\s+program"
    r"|what\s+is\s+the\s+capital|president|politics|news\b)",
    re.IGNORECASE,
)


_PRONOUN_REF_PATTERNS = re.compile(
    r"\b(this|that|the)\s+(inmate|officer|person|prisoner|user|facility)\b"
    r"|\b(for\s+(?:him|her|them))\b"
    r"|\b(the\s+same\s+(?:inmate|officer|person))\b"
    r"|\b(their\s+(?:movement|status|notes?|entries|history|location|last|cell|room|bed))\b"
    # Possessive pronouns: "his status", "her movements", "his last 5 notes"
    r"|\b(his|her)\s+(?:movement|status|notes?|entries|history|location|last|cell|room|bed|record)\b",
    re.IGNORECASE,
)

_SHORT_FOLLOW_UP = re.compile(
    r"^(list\s+out\s+names?|show\s+names?|just\s+names?|names?\s+only"
    r"|show\s+details?|more\s+info|expand|details?|breakdown"
    r"|who\s+are\s+they|which\s+ones?)$",
    re.IGNORECASE,
)


def classify_intent(
    question: str,
    has_history: bool = False,
    last_assistant_content: str = "",
) -> IntentResult:
    """Classify user intent using fast pattern matching (Layer 1)."""
    q = question.strip()

    oos_match = _OUT_OF_SCOPE_PATTERNS.search(q)
    if oos_match:
        data_match = _DATA_SIGNALS.search(q)
        has_domain_subject = bool(re.search(
            r"(inmate|officer|note|entry|facility|round|watch|shift|keyword|status|movement)",
            q, re.IGNORECASE,
        ))
        if not has_domain_subject:
            return IntentResult(
                intent=Intent.OUT_OF_SCOPE,
                confidence=0.9,
                entities={},
                rewritten_question=q,
                reasoning=f"Out-of-scope subject: {oos_match.group()}",
            )

    if has_history:
        if _FOLLOW_UP_PATTERNS.search(q) or _PRONOUN_REF_PATTERNS.search(q):
            return IntentResult(
                intent=Intent.FOLLOW_UP,
                confidence=0.85,
                entities={"references_prior": True},
                rewritten_question=q,
                reasoning="Follow-up referencing prior conversation",
            )
        if _SHORT_FOLLOW_UP.search(q):
            return IntentResult(
                intent=Intent.FOLLOW_UP,
                confidence=0.80,
                entities={"references_prior": True},
                rewritten_question=q,
                reasoning="Short follow-up on prior results",
            )

    if _DATA_SIGNALS.search(q):
        return IntentResult(
            intent=Intent.DATA_QUERY,
            confidence=0.9,
            entities=_extract_entities(q),
            rewritten_question=q,
            reasoning="Contains data query signals",
        )

    if has_history and len(q.split()) <= 4:
        return IntentResult(
            intent=Intent.FOLLOW_UP,
            confidence=0.6,
            entities={"references_prior": True},
            rewritten_question=q,
            reasoning="Short ambiguous input with history — treating as follow-up",
        )

    if len(q.split()) <= 3 and not _DATA_SIGNALS.search(q):
        return IntentResult(
            intent=Intent.CLARIFICATION,
            confidence=0.7,
            entities={},
            rewritten_question=q,
            reasoning="Very short input without clear data signals",
        )

    return IntentResult(
        intent=Intent.DATA_QUERY,
        confidence=0.6,
        entities=_extract_entities(q),
        rewritten_question=q,
        reasoning="Default to data query (no strong pattern match)",
    )


def _extract_entities(question: str) -> dict[str, Any]:
    """Pull structured entities from the question for enrichment."""
    entities: dict[str, Any] = {}
    q = question.lower()

    name_match = re.search(
        r"(?:inmate|officer|user)\s+([a-z]+(?:\s+[a-z]+)?)", q
    )
    if name_match:
        entities["person_name"] = name_match.group(1).title()

    time_match = re.search(
        r"(today|yesterday|last\s+\d+\s+(?:day|week|month|hour)s?"
        r"|this\s+(?:week|month|year)|in\s+last\s+\d+\s+(?:day|week|month)s?)",
        q,
    )
    if time_match:
        entities["time_range"] = time_match.group(0)

    limit_match = re.search(r"(?:top|last|first)\s+(\d+)", q)
    if limit_match:
        entities["limit"] = int(limit_match.group(1))

    for kw in ("fire watch", "suicide watch", "round", "meal", "medical",
               "security", "visitor", "inventory", "movement", "red mark",
               "highlight", "emergency", "fight", "disciplin"):
        if kw in q:
            entities.setdefault("keywords", []).append(kw)

    return entities
