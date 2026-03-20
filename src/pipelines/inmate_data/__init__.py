"""
Inmate Data Pipeline — SQL-based queries via Vanna.

This pipeline handles all data queries about inmates, notes, officers,
facilities, keywords, and other correctional facility operations.

Auto-registers with ScopeRegistry on import.
"""

from src.pipelines.inmate_data.pipeline import InmateDataPipeline

__all__ = ["InmateDataPipeline"]
