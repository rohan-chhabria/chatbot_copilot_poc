"""
Daily Activity Pipeline — Check missed and upcoming scheduled activities.

This pipeline auto-executes on scope selection and supports "refresh" keyword
for subsequent re-runs. Uses template-based summaries (no LLM).
"""

from src.pipelines.daily_activity.pipeline import DailyActivityPipeline

__all__ = ["DailyActivityPipeline"]
