"""
Inmate Data Pipeline — SQL-based queries via Vanna.

This pipeline handles all data queries about inmates, notes, officers,
facilities, keywords, and other correctional facility operations.

Components:
  - InmateDataPipeline: Main pipeline class (auto-registers with ScopeRegistry)
  - InsightExtractor: Extracts structured stats from query results
  - ResponseSummarizer: Generates natural language summaries via LLM

Auto-registers with ScopeRegistry on import.
"""

from src.pipelines.inmate_data.insight_extractor import InsightExtractor, QueryInsights
from src.pipelines.inmate_data.pipeline import InmateDataPipeline
from src.pipelines.inmate_data.response_summarizer import ResponseSummarizer

__all__ = [
    "InmateDataPipeline",
    "InsightExtractor",
    "QueryInsights",
    "ResponseSummarizer",
]
