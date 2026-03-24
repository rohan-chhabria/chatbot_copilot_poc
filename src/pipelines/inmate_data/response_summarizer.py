"""
Response Summarizer — Generates natural language summaries from structured insights.

Uses LLM to convert pre-computed statistics into dense, officer-friendly summaries.
The insights are computed by InsightExtractor (fast, deterministic), then polished
here into natural language.

Design:
  - Accuracy: Numbers come from code (InsightExtractor), not hallucinated
  - Speed: Small LLM payload (~200-300 tokens) → ~1s latency
  - Consistency: Same prompt structure for all query types
  - Engagement: Suggests follow-up questions to encourage conversation
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from src.pipelines.inmate_data.insight_extractor import QueryInsights
from src.shared.config import LLM_TEMPERATURE, OPENAI_API_KEY, OPENAI_MODEL
from src.shared.logger import get_logger

logger = get_logger(__name__)

# System prompt for summarization
SUMMARIZER_SYSTEM_PROMPT = """You are Sarah, a helpful assistant for correctional officers.

Your job is to summarize database query results into clear, dense natural language.
Officers are busy — they need quick, scannable answers.

RULES:
1. Be CONCISE: 2-3 sentences max for the summary.
2. Lead with the KEY NUMBER (total count, main finding).
3. Highlight NOTABLE PATTERNS (top categories, peak days, outliers).
4. Mention RED FLAGS if present (these need attention).
5. Use markdown sparingly: **bold** for key numbers only.
6. NEVER invent numbers — only use what's provided in the stats.
7. Format for chat — short paragraphs, no bullet lists unless 3+ items.

TONE: Professional, direct, helpful. Like a knowledgeable colleague."""
# 5. End with ONE short follow-up question to encourage conversation.

class ResponseSummarizer:
    """
    Summarizes query insights into natural language using LLM.
    
    Takes structured insights from InsightExtractor and generates
    a conversational summary suitable for chat interface.
    """

    def __init__(self):
        self._openai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self._model = OPENAI_MODEL

    async def summarize(
        self,
        insights: QueryInsights,
        question: str,
    ) -> str:
        """Generate a natural language summary from insights."""
        # For simple counts, skip LLM entirely
        if insights.query_type == "count" and len(insights.aggregate_values) <= 2:
            return self._format_simple_count(insights, question)
        
        # For empty results, use template
        if insights.total_count == 0:
            return self._format_empty(question)
        
        # Build structured stats for LLM
        stats_text = self._build_stats_text(insights, question)
        
        logger.debug(
            "Summarizing insights: type=%s, count=%d, stats_len=%d",
            insights.query_type,
            insights.total_count,
            len(stats_text),
        )
        
        messages = [
            {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"QUESTION: {question}\n\nSTATS:\n{stats_text}\n\nSummarize these stats for the officer.",
            },
        ]
        
        try:
            response = await self._openai.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=LLM_TEMPERATURE,
                max_tokens=256,
            )
            
            summary = response.choices[0].message.content or ""
            logger.debug("LLM summary: %d chars", len(summary))
            return summary.strip()
            
        except Exception as e:
            logger.error("LLM summarization failed: %s", str(e))
            # Fallback to template-based summary
            return self._fallback_summary(insights, question)

    async def summarize_stream(
        self,
        insights: QueryInsights,
        question: str,
    ) -> AsyncGenerator[str, None]:
        """Stream summary generation token by token."""
        # For simple counts, yield immediately
        if insights.query_type == "count" and len(insights.aggregate_values) <= 2:
            yield self._format_simple_count(insights, question)
            return
        
        if insights.total_count == 0:
            yield self._format_empty(question)
            return
        
        stats_text = self._build_stats_text(insights, question)
        
        logger.debug(
            "Streaming summary: type=%s, count=%d",
            insights.query_type,
            insights.total_count,
        )
        
        messages = [
            {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"QUESTION: {question}\n\nSTATS:\n{stats_text}\n\nSummarize these stats for the officer.",
            },
        ]
        
        try:
            stream = await self._openai.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=LLM_TEMPERATURE,
                max_tokens=256,
                stream=True,
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error("LLM stream failed: %s", str(e))
            yield self._fallback_summary(insights, question)

    def _build_stats_text(self, insights: QueryInsights, question: str) -> str:
        """Build a compact stats representation for the LLM."""
        lines = []
        
        # Total count
        lines.append(f"- Total: {insights.total_count} records")
        
        # Date range
        if insights.date_range[0] and insights.date_range[1]:
            start = insights.date_range[0].strftime("%b %d")
            end = insights.date_range[1].strftime("%b %d")
            if start != end:
                lines.append(f"- Date range: {start} to {end}")
            else:
                lines.append(f"- Date: {start}")
        
        # Peak day
        if insights.peak_day[0] and insights.peak_day[1] > 1:
            peak_date = insights.peak_day[0].strftime("%b %d")
            lines.append(f"- Peak day: {peak_date} ({insights.peak_day[1]} records)")
        
        # Top categories
        if insights.top_categories:
            total = insights.total_count or sum(c for _, c in insights.top_categories)
            cats = ", ".join(
                f"{name} ({count}, {count*100//total}%)" 
                for name, count in insights.top_categories[:3]
            )
            lines.append(f"- Top categories: {cats}")
        
        # Top officers
        if insights.top_officers:
            officers = ", ".join(
                f"{name} ({count})" for name, count in insights.top_officers[:3]
            )
            lines.append(f"- Top officers: {officers}")
        
        # Top facilities
        if insights.top_facilities:
            facs = ", ".join(
                f"{name} ({count})" for name, count in insights.top_facilities[:3]
            )
            lines.append(f"- Facilities: {facs}")
        
        # Top statuses
        if insights.top_statuses:
            statuses = ", ".join(
                f"{name} ({count})" for name, count in insights.top_statuses[:3]
            )
            lines.append(f"- Statuses: {statuses}")
        
        # Red flags
        if insights.red_flag_count > 0:
            lines.append(f"- RED FLAGS: {insights.red_flag_count} entries need attention")
        
        # Unique counts
        if insights.unique_inmates > 1:
            lines.append(f"- Unique inmates: {insights.unique_inmates}")
        if insights.unique_officers > 1:
            lines.append(f"- Unique officers: {insights.unique_officers}")
        
        # Aggregate values (for count/ranked queries)
        for k, v in insights.aggregate_values.items():
            if k not in ("columns", "total") and v is not None:
                label = k.replace("_", " ").title()
                if isinstance(v, (int, float)):
                    lines.append(f"- {label}: {v:,}")
        
        return "\n".join(lines)

    def _format_simple_count(self, insights: QueryInsights, question: str) -> str:
        """Format simple count queries without LLM."""
        q_lower = question.lower()
        
        # Determine subject from question
        subject = "records"
        if "note" in q_lower:
            subject = "notes"
        elif "movement" in q_lower:
            subject = "movements"
        elif "inmate" in q_lower:
            subject = "inmates"
        elif "officer" in q_lower:
            subject = "officers"
        
        # Extract the count value
        values = list(insights.aggregate_values.values())
        if len(values) == 1:
            count = values[0]
            if isinstance(count, (int, float)):
                return f"**{count:,}** {subject} found."
        
        # Multiple values
        parts = []
        for k, v in insights.aggregate_values.items():
            label = k.replace("_", " ").replace("count(*)", "total").title()
            if isinstance(v, (int, float)):
                parts.append(f"**{label}**: {v:,}")
            else:
                parts.append(f"**{label}**: {v}")
        
        return " | ".join(parts)

    def _format_empty(self, question: str) -> str:
        """Format empty result message."""
        import re
        
        # Check for inmate/officer name
        name_match = re.search(
            r"(?:inmate|officer)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)",
            question, re.IGNORECASE,
        )
        
        if name_match:
            return (
                f"No records found for \"{name_match.group(1)}\". "
                "Try checking the spelling or using a partial name."
            )
        
        if re.search(r"(today|last\s+\d+\s+hour)", question, re.IGNORECASE):
            return "No results for that timeframe. Try a wider date range?"
        
        return "No matching records found. Try broadening your search criteria."

    def _fallback_summary(self, insights: QueryInsights, question: str) -> str:
        """Generate a basic summary without LLM (fallback)."""
        parts = [f"Found **{insights.total_count:,}** records"]
        
        if insights.date_range[0] and insights.date_range[1]:
            start = insights.date_range[0].strftime("%b %d")
            end = insights.date_range[1].strftime("%b %d")
            if start != end:
                parts.append(f"from {start} to {end}")
        
        summary = " ".join(parts) + "."
        
        if insights.top_categories:
            top = insights.top_categories[0]
            summary += f" Top category: **{top[0]}** ({top[1]})."
        
        if insights.red_flag_count > 0:
            summary += f" ⚠️ {insights.red_flag_count} red-flagged entries."
        
        return summary
