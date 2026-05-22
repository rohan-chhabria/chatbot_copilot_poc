"""
Daily Activity Pipeline — Check missed and upcoming scheduled activities.

This pipeline auto-executes on scope selection and supports the "refresh"
keyword for re-runs. Uses template-based summaries (no LLM).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, AsyncGenerator

from src.orchestrator.scope_registry import register_pipeline
from src.pipelines.base import Pipeline
from src.pipelines.daily_activity import activity_checker, response_formatter
from src.pipelines.daily_activity.timetable_loader import (
    TimetableNotFoundError,
    get_activity_config,
)
from src.shared.logger import get_logger

if TYPE_CHECKING:
    from src.session.models import ScopeContext, Session

logger = get_logger(__name__)


@register_pipeline(
    scope_id="daily_activity",
    label="Daily Activity",
    icon="📅",
    description="Check missed and upcoming scheduled activities",
    category="Compliance",
)
class DailyActivityPipeline(Pipeline):
    """
    Daily Activity Pipeline — Check missed and upcoming scheduled activities.

    Features:
    - Auto-executes on scope selection (supports_auto_execute=True)
    - Supports "refresh" keyword for re-runs
    - Template-based summaries (no LLM)
    - Multi-facility aggregation
    """

    supports_auto_execute = True

    async def process(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> dict[str, Any]:
        """
        Process an activity check request.

        - Empty question or "refresh": Run activity check
        - Any other input: Return instruction message
        """
        question_normalized = question.strip().lower()

        logger.debug(
            "DailyActivityPipeline.process: question=%r, user=%s, tenant=%s",
            question[:100] if question else "(empty)",
            session.user_id,
            session.customer_key,
        )

        if question_normalized and question_normalized != "refresh":
            return {
                "summary": response_formatter.format_instruction_message(),
                "row_count": 0,
            }

        return await self._run_activity_check(session)

    async def process_stream(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream activity check response (minimal streaming, mostly status updates)."""
        question_normalized = question.strip().lower()

        if question_normalized and question_normalized != "refresh":
            yield {
                "event": "result",
                "data": {
                    "summary": response_formatter.format_instruction_message(),
                    "row_count": 0,
                },
            }
            return

        yield {"event": "status", "data": "Checking missed activities..."}
        yield {"event": "status", "data": "Checking upcoming activities..."}

        result = await self._run_activity_check(session)

        yield {"event": "result", "data": result}

    async def health(self) -> dict[str, Any]:
        """Check pipeline health."""
        # Get default config (will use env vars if no customer specified)
        from src.shared.config import (
            DAILY_ACTIVITY_LOOKAHEAD_HOURS,
            DAILY_ACTIVITY_LOOKBACK_HOURS,
        )
        return {
            "status": "healthy",
            "lookback_hours": DAILY_ACTIVITY_LOOKBACK_HOURS,
            "lookahead_hours": DAILY_ACTIVITY_LOOKAHEAD_HOURS,
            "config_source": "env_vars_default",
        }

    async def _run_activity_check(self, session: Session) -> dict[str, Any]:
        """
        Run the activity check for all user facilities.

        Returns formatted response with summary and detailed data.
        """
        from src.tenant.tenant_router import resolve_tenant

        tenant = resolve_tenant(session.customer_key)

        if not tenant:
            logger.error("No tenant found for customer_key=%s", session.customer_key)
            return {
                "summary": response_formatter.format_error_response(
                    "Unable to resolve tenant configuration."
                ),
                "row_count": 0,
            }

        facility_ids = session.facility_ids or []
        if not facility_ids:
            logger.warning("No facilities assigned for user=%s", session.user_id)
            return {
                "summary": response_formatter.format_no_facilities_error(),
                "row_count": 0,
            }

        facility_names = self._get_facility_names(session)

        # Get activity config from customer config (DynamoDB in production)
        activity_config = get_activity_config(session.customer_key)
        lookback_hours = activity_config["lookback_hours"]
        lookahead_hours = activity_config["lookahead_hours"]
        tolerance_minutes = activity_config["tolerance_minutes"]

        logger.info(
            "Running activity check: user=%s, tenant=%s, facilities=%s, lookback=%sh, lookahead=%sh",
            session.user_id,
            session.customer_key,
            facility_ids,
            lookback_hours,
            lookahead_hours,
        )

        try:
            result = await activity_checker.process_activity(
                tenant=tenant,
                facility_ids=facility_ids,
                facility_names=facility_names,
                lookback_hours=lookback_hours,
                lookahead_hours=lookahead_hours,
                tolerance_minutes=tolerance_minutes,
            )

            logger.info(
                "Daily Activity response: missed=%d, upcoming=%d, facilities=%d\n%s",
                result.get("total_missed", 0),
                result.get("total_upcoming", 0),
                len(facility_ids),
                json.dumps(result, indent=2, default=str),
            )

            summary = response_formatter.format_activity_response(result)

            # Extract activities with IDs for API response
            all_missed = []
            all_upcoming = []
            for fid, fdata in result.get("by_facility", {}).items():
                missed_section = fdata.get("missed", {})
                upcoming_section = fdata.get("upcoming", {})
                for act in missed_section.get("activities", []):
                    all_missed.append({
                        "facility_id": int(fid),
                        "name": act.get("name"),
                        "start_time": act.get("start_time"),
                        "end_time": act.get("end_time"),
                        "keyword_id": act.get("keyword_id"),
                        "tag_status_id": act.get("tag_status_id"),
                        "keywords": act.get("keywords", []),
                        "statuses": act.get("statuses", {}),
                    })
                for act in upcoming_section.get("activities", []):
                    all_upcoming.append({
                        "facility_id": int(fid),
                        "name": act.get("name"),
                        "start_time": act.get("start_time"),
                        "end_time": act.get("end_time"),
                        "keyword_id": act.get("keyword_id"),
                        "tag_status_id": act.get("tag_status_id"),
                        "keywords": act.get("keywords", []),
                        "statuses": act.get("statuses", {}),
                    })

            return {
                "summary": summary,
                "row_count": result.get("total_missed", 0) + result.get("total_upcoming", 0),
                "total_missed": result.get("total_missed", 0),
                "total_upcoming": result.get("total_upcoming", 0),
                "missed_activities": all_missed,
                "upcoming_activities": all_upcoming,
                "by_facility": result.get("by_facility", {}),
                "given_date_time": result.get("given_date_time"),
                "config": {
                    "lookback_hours": lookback_hours,
                    "lookahead_hours": lookahead_hours,
                    "tolerance_minutes": tolerance_minutes,
                },
            }

        except TimetableNotFoundError as e:
            logger.error("Timetable not found: %s", str(e))
            return {
                "summary": response_formatter.format_error_response(
                    "No timetable configured for your facility."
                ),
                "row_count": 0,
            }

        except Exception as e:
            logger.exception("Activity check failed: %s", str(e))
            return {
                "summary": response_formatter.format_error_response(
                    "Unable to fetch activity data. Please try again."
                ),
                "row_count": 0,
            }

    def _get_facility_names(self, session: Session) -> dict[int, str]:
        """Get facility ID to name mapping from session."""
        facility_names: dict[int, str] = {}
        for fid in session.facility_ids or []:
            facility_names[fid] = f"Facility {fid}"
        return facility_names

    def get_welcome_message(self, is_returning: bool = False) -> str:
        """Get welcome message when entering this scope."""
        if is_returning:
            return "Welcome back! Here's your updated activity status:"
        return "Here's your current activity status:"
