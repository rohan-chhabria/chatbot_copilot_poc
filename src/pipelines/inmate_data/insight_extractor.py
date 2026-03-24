"""
Insight Extractor — Extracts structured insights from query results.

Computes key statistics from raw data rows without using LLM.
These insights are then passed to the ResponseSummarizer for natural language generation.

Design:
  - Fast: Pure Python computation, no external calls
  - Accurate: Numbers come from code, not hallucinated
  - Deterministic: Same input always produces same output
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from src.shared.constants import HIGHLIGHTER_MAP
from src.shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class QueryInsights:
    """Structured insights extracted from query results."""

    query_type: str  # count, ranked, notes, movement, status_change, inmates, officers, facilities, generic
    total_count: int
    
    # Date context
    date_range: tuple[date | None, date | None] = (None, None)
    peak_day: tuple[date | None, int] = (None, 0)
    
    # Top categories (name -> count)
    top_categories: list[tuple[str, int]] = field(default_factory=list)
    top_officers: list[tuple[str, int]] = field(default_factory=list)
    top_facilities: list[tuple[str, int]] = field(default_factory=list)
    top_statuses: list[tuple[str, int]] = field(default_factory=list)
    top_inmates: list[tuple[str, int]] = field(default_factory=list)
    
    # Flags and outliers
    red_flag_count: int = 0
    unique_inmates: int = 0
    unique_officers: int = 0
    unique_facilities: int = 0
    
    # Aggregate values (for count queries)
    aggregate_values: dict[str, Any] = field(default_factory=dict)
    
    # Sample data for context
    sample_descriptions: list[str] = field(default_factory=list)


class InsightExtractor:
    """
    Extracts structured insights from database query results.
    
    Analyzes rows to compute statistics, trends, and notable patterns
    that can be summarized into natural language.
    """

    def extract(
        self,
        rows: list[dict[str, Any]],
        question: str,
    ) -> QueryInsights:
        """Extract insights from query results."""
        if not rows:
            return QueryInsights(query_type="empty", total_count=0)
        
        cols = self._lower_keys(rows[0])
        query_type = self._detect_query_type(rows, cols, question)
        
        logger.debug(
            "Extracting insights: type=%s, rows=%d",
            query_type, len(rows),
        )
        
        insights = QueryInsights(
            query_type=query_type,
            total_count=len(rows),
        )
        
        # Extract type-specific insights
        extractors = {
            "count": self._extract_count_insights,
            "ranked": self._extract_ranked_insights,
            "notes": self._extract_notes_insights,
            "movement": self._extract_movement_insights,
            "status_change": self._extract_status_insights,
            "inmates": self._extract_inmates_insights,
            "officers": self._extract_officers_insights,
            "facilities": self._extract_facilities_insights,
        }
        
        extractor = extractors.get(query_type, self._extract_generic_insights)
        extractor(rows, question, insights)
        
        # Common extractions for all types
        self._extract_common_insights(rows, insights)
        
        return insights

    def _detect_query_type(
        self,
        rows: list[dict[str, Any]],
        cols: set[str],
        question: str,
    ) -> str:
        """Detect the type of query from result structure."""
        if len(rows) == 1 and self._is_aggregate(rows[0]):
            return "count"
        if self._has_count_col(rows) and len(rows) <= 100:
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

    def _extract_count_insights(
        self,
        rows: list[dict[str, Any]],
        question: str,
        insights: QueryInsights,
    ) -> None:
        """Extract insights from aggregate/count queries."""
        row = rows[0]
        for k, v in row.items():
            insights.aggregate_values[k] = v

    def _extract_ranked_insights(
        self,
        rows: list[dict[str, Any]],
        question: str,
        insights: QueryInsights,
    ) -> None:
        """Extract insights from ranked/leaderboard queries."""
        count_key = self._find_count_key(rows[0])
        total = sum(self._safe_int(r.get(count_key, 0)) for r in rows)
        insights.aggregate_values["total"] = total
        
        # Build top list
        name_keys = {
            "firstname", "lastname", "first_name", "last_name", "username",
            "emp_first_name", "emp_last_name", "inmate_name", "keyword_name",
            "facility", "facility_name",
        }
        
        top_items = []
        for r in rows[:10]:
            name = self._extract_display_name(r, name_keys, count_key)
            count = self._safe_int(r.get(count_key, 0))
            if name:
                top_items.append((name, count))
        
        # Determine what's being ranked
        q_lower = question.lower()
        if "officer" in q_lower or "user" in q_lower:
            insights.top_officers = top_items
        elif "keyword" in q_lower or "categor" in q_lower:
            insights.top_categories = top_items
        elif "facilit" in q_lower:
            insights.top_facilities = top_items
        elif "inmate" in q_lower:
            insights.top_inmates = top_items
        else:
            insights.top_categories = top_items

    def _extract_notes_insights(
        self,
        rows: list[dict[str, Any]],
        question: str,
        insights: QueryInsights,
    ) -> None:
        """Extract insights from notes queries."""
        # Date range
        dates = self._extract_dates(rows, "note_date", "date_added")
        if dates:
            insights.date_range = (min(dates), max(dates))
            
            # Peak day
            day_counts = Counter(d for d in dates)
            if day_counts:
                peak = day_counts.most_common(1)[0]
                insights.peak_day = peak
        
        # Categories (keywords)
        kw_counts = self._count_field(rows, "keyword_name")
        if kw_counts:
            insights.top_categories = kw_counts.most_common(5)
        
        # Officers
        officer_counts = self._count_field(rows, "officer_name")
        if not officer_counts:
            for key in ("user_id", "username", "firstname"):
                officer_counts = self._count_field(rows, key)
                if officer_counts:
                    break
        if officer_counts:
            insights.top_officers = officer_counts.most_common(5)
            insights.unique_officers = len(officer_counts)
        
        # Red flags (highlighted entries)
        red_count = sum(
            1 for r in rows
            if r.get("highlighter_id") == 11 or "red" in str(r.get("highlighter", "")).lower()
        )
        insights.red_flag_count = red_count
        
        # Sample descriptions
        for r in rows[:3]:
            desc = str(r.get("notes_description", ""))[:100]
            if desc:
                insights.sample_descriptions.append(desc)

    def _extract_movement_insights(
        self,
        rows: list[dict[str, Any]],
        question: str,
        insights: QueryInsights,
    ) -> None:
        """Extract insights from movement queries."""
        # Date range
        dates = self._extract_dates(rows, "date_added")
        if dates:
            insights.date_range = (min(dates), max(dates))
        
        # Unique inmates
        inmates = set()
        for r in rows:
            name = self._get_inmate_name(r)
            if name and name.lower() != "inmate":
                inmates.add(name)
        insights.unique_inmates = len(inmates)
        if inmates:
            insights.top_inmates = [(name, 1) for name in list(inmates)[:5]]
        
        # Facilities involved
        facilities = set()
        for r in rows:
            old_fac = r.get("old_facility") or r.get("old_facilities_id")
            new_fac = r.get("new_facility") or r.get("new_facilities_id")
            if old_fac:
                facilities.add(str(old_fac))
            if new_fac:
                facilities.add(str(new_fac))
        insights.unique_facilities = len(facilities)

    def _extract_status_insights(
        self,
        rows: list[dict[str, Any]],
        question: str,
        insights: QueryInsights,
    ) -> None:
        """Extract insights from status change queries."""
        # Date range
        dates = self._extract_dates(rows, "note_date", "date_added")
        if dates:
            insights.date_range = (min(dates), max(dates))
        
        # Status distribution
        status_counts = (
            self._count_field(rows, "status")
            or self._count_field(rows, "status_name")
            or self._count_field(rows, "tag_status_name")
        )
        if status_counts:
            insights.top_statuses = status_counts.most_common(5)

    def _extract_inmates_insights(
        self,
        rows: list[dict[str, Any]],
        question: str,
        insights: QueryInsights,
    ) -> None:
        """Extract insights from inmate queries."""
        # Facility distribution
        fac_counts = self._count_field(rows, "facility") or self._count_field(rows, "facility_name")
        if fac_counts:
            insights.top_facilities = fac_counts.most_common(5)
            insights.unique_facilities = len(fac_counts)
        
        # Status distribution
        status_counts = (
            self._count_field(rows, "current_status")
            or self._count_field(rows, "status_name")
            or self._count_field(rows, "tag_status_name")
            or self._count_field(rows, "name")
        )
        if status_counts:
            insights.top_statuses = status_counts.most_common(5)

    def _extract_officers_insights(
        self,
        rows: list[dict[str, Any]],
        question: str,
        insights: QueryInsights,
    ) -> None:
        """Extract insights from officer queries."""
        # Facility distribution
        fac_counts = (
            self._count_field(rows, "facility")
            or self._count_field(rows, "facility_name")
            or self._count_field(rows, "default_facilities_id")
        )
        if fac_counts:
            insights.top_facilities = fac_counts.most_common(5)

    def _extract_facilities_insights(
        self,
        rows: list[dict[str, Any]],
        question: str,
        insights: QueryInsights,
    ) -> None:
        """Extract insights from facility queries."""
        # Just list facility names
        names = []
        for r in rows[:10]:
            name = r.get("facility") or r.get("facility_name") or r.get("facilities_id")
            if name:
                names.append((str(name), 1))
        insights.top_facilities = names

    def _extract_generic_insights(
        self,
        rows: list[dict[str, Any]],
        question: str,
        insights: QueryInsights,
    ) -> None:
        """Extract insights from unrecognized query types."""
        # Just provide column summary
        if rows:
            cols = list(rows[0].keys())[:6]
            insights.aggregate_values["columns"] = cols

    def _extract_common_insights(
        self,
        rows: list[dict[str, Any]],
        insights: QueryInsights,
    ) -> None:
        """Extract insights common to all query types."""
        # Red flags if not already counted
        if insights.red_flag_count == 0:
            red_count = sum(
                1 for r in rows
                if r.get("highlighter_id") == 11 or "red" in str(r.get("highlighter", "")).lower()
            )
            insights.red_flag_count = red_count

    # ─────────────────────────────────────────────────────────────────────────
    #  Helper methods
    # ─────────────────────────────────────────────────────────────────────────

    def _lower_keys(self, row: dict[str, Any]) -> set[str]:
        return {k.lower() for k in row.keys()}

    def _is_aggregate(self, row: dict[str, Any]) -> bool:
        for k in row.keys():
            kl = k.lower()
            if any(w in kl for w in ("count", "total", "sum", "avg", "min", "max")):
                return True
        if len(row) <= 2 and all(isinstance(v, (int, float)) for v in row.values()):
            return True
        return False

    def _has_count_col(self, rows: list[dict[str, Any]]) -> bool:
        if not rows:
            return False
        count_names = {
            "cnt", "count", "total", "note_count", "notes_count", "total_notes",
            "count(*)", "movement_count", "entry_count", "record_count",
        }
        for k in rows[0].keys():
            if k.lower() in count_names or k.lower().endswith("_count") or k.lower().endswith("_total"):
                return True
        return False

    def _find_count_key(self, row: dict[str, Any]) -> str:
        count_names = {
            "cnt", "count", "total", "note_count", "notes_count", "total_notes",
            "count(*)", "movement_count", "entry_count", "record_count",
        }
        for k in row.keys():
            if k.lower() in count_names or k.lower().endswith("_count") or k.lower().endswith("_total"):
                return k
        for k, v in row.items():
            if isinstance(v, (int, float)):
                return k
        return list(row.keys())[-1]

    def _count_field(self, rows: list[dict[str, Any]], field: str) -> Counter:
        c: Counter = Counter()
        for r in rows:
            val = r.get(field)
            if val is not None and str(val).strip():
                c[str(val)] += 1
        return c

    def _extract_dates(self, rows: list[dict[str, Any]], *fields: str) -> list[date]:
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

    def _get_inmate_name(self, row: dict[str, Any]) -> str:
        combined = row.get("inmate_name")
        if combined and str(combined).strip():
            return self._clean_name(str(combined))
        first = self._clean_name(row.get("emp_first_name", ""))
        last = self._clean_name(row.get("emp_last_name", ""))
        if first or last:
            return f"{first} {last}".strip()
        return "Inmate"

    def _extract_display_name(
        self,
        row: dict[str, Any],
        name_keys: set[str],
        skip_key: str,
    ) -> str:
        first = row.get("firstname") or row.get("first_name") or row.get("emp_first_name") or ""
        last = row.get("lastname") or row.get("last_name") or row.get("emp_last_name") or ""
        if first or last:
            return self._clean_name(f"{first} {last}".strip())
        combined = row.get("inmate_name") or row.get("keyword_name") or row.get("username")
        if combined:
            return self._clean_name(str(combined))
        for k, v in row.items():
            if k != skip_key and k not in name_keys and v is not None and str(v).strip():
                return str(v)
        return ""

    def _clean_name(self, val: str) -> str:
        if not val:
            return ""
        s = str(val).strip()
        return s.title() if s == s.upper() and len(s) > 1 else s

    def _safe_int(self, val: Any) -> int:
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0
