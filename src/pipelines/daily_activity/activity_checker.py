"""
Activity Checker — Core logic for checking daily activities against timetable.

Compares scheduled activities from the timetable against actual database records
to determine missed activities (lookback) and upcoming activities (lookahead).
Supports multi-facility aggregation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from src.pipelines.daily_activity import db_adapter
from src.pipelines.daily_activity.timetable_loader import (
    get_day_schedule,
    load_timetable,
)
from src.shared.logger import get_logger
from src.tenant.tenant_router import TenantContext

logger = get_logger(__name__)


def parse_time_to_timedelta(time_str: str) -> timedelta:
    """Convert time string (HH:MM:SS) to timedelta from midnight."""
    parts = time_str.split(":")
    return timedelta(
        hours=int(parts[0]),
        minutes=int(parts[1]),
        seconds=int(parts[2]) if len(parts) > 2 else 0,
    )


def format_time(dt: datetime) -> str:
    """Format datetime to HH:MM string."""
    return dt.strftime("%H:%M")


def format_datetime(dt: datetime) -> str:
    """Format datetime as MM-DD-YYYY HH:MM."""
    return dt.strftime("%m-%d-%Y %H:%M")


def calculate_time_range(given_dt: datetime, n: float) -> tuple[datetime, datetime]:
    """
    Calculate the time range based on given datetime and n hours.

    Args:
        given_dt: The reference datetime
        n: Hours to look back (if negative) or ahead (if positive)

    Returns:
        Tuple of (start_dt, end_dt)
    """
    delta = timedelta(hours=abs(n))

    if n < 0:
        start_dt = given_dt - delta
        end_dt = given_dt
    else:
        start_dt = given_dt
        end_dt = given_dt + delta

    return start_dt, end_dt


def get_tasks_in_range(
    timetable: list[dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict[str, Any]]:
    """
    Get all tasks from timetable that overlap with the given datetime range.

    Handles midnight-crossing tasks and multi-day ranges.

    Returns:
        List of task dicts with added 'task_start_dt' and 'task_end_dt' fields
    """
    tasks_in_range = []
    seen_tasks: set[tuple[datetime, str]] = set()

    current_date = (start_dt - timedelta(days=1)).date()
    end_date = end_dt.date()

    while current_date <= end_date:
        day_name = current_date.strftime("%A")
        day_tasks = get_day_schedule(timetable, day_name)

        for task in day_tasks:
            start_time = parse_time_to_timedelta(task["start_time"])
            end_time = parse_time_to_timedelta(task["end_time"])

            task_start_dt = datetime.combine(current_date, datetime.min.time()) + start_time

            if end_time < start_time:
                task_end_dt = (
                    datetime.combine(current_date + timedelta(days=1), datetime.min.time())
                    + end_time
                )
            else:
                task_end_dt = datetime.combine(current_date, datetime.min.time()) + end_time

            if task_start_dt < end_dt and task_end_dt > start_dt:
                task_key = (task_start_dt, task["task"])

                if task_key not in seen_tasks:
                    seen_tasks.add(task_key)
                    task_info = task.copy()
                    task_info["task_start_dt"] = task_start_dt
                    task_info["task_end_dt"] = task_end_dt
                    tasks_in_range.append(task_info)

        current_date += timedelta(days=1)

    tasks_in_range.sort(key=lambda t: t["task_start_dt"])
    return tasks_in_range


def parse_task_keywords(keywords_str: str) -> list[str]:
    """Parse comma-separated keywords from timetable."""
    if not keywords_str:
        return []
    return [kw.strip() for kw in keywords_str.split(",") if kw.strip()]


def record_matches_task(record: dict[str, Any], task: dict[str, Any]) -> bool:
    """
    Check if a database record matches a task based on keywords or statuses.
    """
    record_type = record.get("Status_Keyword", "")

    if record_type == "Keyword":
        task_keywords = parse_task_keywords(task.get("keywords", ""))
        record_keyword = record.get("keyword_name", "")

        if record_keyword:
            for kw in task_keywords:
                if kw == record_keyword:
                    return True

    elif record_type == "Status":
        task_statuses = task.get("statuses", {})
        record_status = record.get("tag_status_name", "")
        record_substatus = record.get("tag_status_ids", "")

        if record_status and record_status in task_statuses:
            substatuses = task_statuses[record_status]
            if not substatuses:
                return True
            elif record_substatus in substatuses:
                return True

    return False


def resolve_ids_from_lookup(
    task: dict[str, Any],
    lookup: dict[str, dict[str, int]] | None,
) -> tuple[int | None, int | None]:
    """Resolve keyword_id and tag_status_id from lookup."""
    if lookup is None:
        return None, None

    keyword_id = None
    tag_status_id = None

    task_keywords = parse_task_keywords(task.get("keywords", ""))
    if task_keywords and lookup.get("keywords"):
        for kw in task_keywords:
            if kw in lookup["keywords"]:
                keyword_id = lookup["keywords"][kw]
                break

    task_statuses = task.get("statuses", {})
    if task_statuses and lookup.get("statuses"):
        for status_name in task_statuses.keys():
            if status_name in lookup["statuses"]:
                tag_status_id = lookup["statuses"][status_name]
                break

    return keyword_id, tag_status_id


def categorize_task(task_name: str) -> str:
    """Categorize a task by type based on its name."""
    task_name_lower = task_name.lower()

    if "count" in task_name_lower:
        return "Count"
    elif "program" in task_name_lower or "block" in task_name_lower:
        return "Program"
    elif "chow" in task_name_lower or "kitchen" in task_name_lower:
        return "Meal/Kitchen"
    elif "medical" in task_name_lower or "pill" in task_name_lower or "insulin" in task_name_lower:
        return "Medical"
    elif "recreation" in task_name_lower or "gym" in task_name_lower or "yard" in task_name_lower:
        return "Recreation"
    elif "sanitation" in task_name_lower or "laundry" in task_name_lower:
        return "Sanitation"
    elif "visitation" in task_name_lower:
        return "Visitation"
    else:
        return "Other"


def _build_empty_missed_section() -> dict[str, Any]:
    """Return an empty missed section structure."""
    return {
        "period": None,
        "total_missed_activities": 0,
        "activities": [],
        "activities_by_type": {},
        "insights": {
            "first_missed": None,
            "last_missed": None,
            "missed_types": [],
        },
    }


def _build_empty_upcoming_section() -> dict[str, Any]:
    """Return an empty upcoming section structure."""
    return {
        "period": None,
        "total_upcoming_activities": 0,
        "activities": [],
        "activities_by_type": {},
        "insights": {
            "first_upcoming": None,
            "last_upcoming": None,
            "upcoming_types": [],
        },
    }


def get_missed_activities(
    timetable: list[dict[str, Any]],
    cached_records: pd.DataFrame,
    given_dt: datetime,
    lookback_hours: float,
    tolerance_minutes: int,
    lookup: dict[str, dict[str, int]] | None,
) -> dict[str, Any]:
    """
    Get missed activities for the lookback period.

    Args:
        timetable: Loaded timetable data
        cached_records: Pre-fetched DB records for the window
        given_dt: Reference datetime
        lookback_hours: Hours to look back (negative value)
        tolerance_minutes: Additional tolerance after task end time
        lookup: Lookup dict for resolving keyword_id and tag_status_id
    """
    if lookback_hours == 0:
        return _build_empty_missed_section()

    start_dt, end_dt = calculate_time_range(given_dt, lookback_hours)
    scheduled_tasks = get_tasks_in_range(timetable, start_dt, end_dt)

    logger.debug(
        "Checking %d scheduled tasks for missed activities from %s to %s",
        len(scheduled_tasks),
        start_dt,
        end_dt,
    )

    result: dict[str, Any] = {
        "period": {"start": format_datetime(start_dt), "end": format_datetime(end_dt)},
        "total_missed_activities": 0,
        "activities": [],
        "activities_by_type": {},
        "insights": {
            "first_missed": None,
            "last_missed": None,
            "missed_types": [],
        },
    }

    if not scheduled_tasks:
        return result

    missed_activities = []
    missed_types: set[str] = set()

    for task in scheduled_tasks:
        task_start = task["task_start_dt"]
        task_end = task["task_end_dt"] + timedelta(minutes=tolerance_minutes)

        if not cached_records.empty:
            slot_records = cached_records[
                (cached_records["date_added"] >= task_start)
                & (cached_records["date_added"] <= task_end)
            ]
        else:
            slot_records = pd.DataFrame()

        task_happened = False
        if not slot_records.empty:
            for _, record in slot_records.iterrows():
                if record_matches_task(record.to_dict(), task):
                    task_happened = True
                    break

        if not task_happened:
            task_type = categorize_task(task["task"])
            missed_types.add(task_type)
            keyword_id, tag_status_id = resolve_ids_from_lookup(task, lookup)

            task_info = {
                "name": task["task"],
                "start_time": format_time(task["task_start_dt"]),
                "end_time": format_time(task["task_end_dt"]),
                "keywords": parse_task_keywords(task.get("keywords", "")),
                "keyword_id": keyword_id,
                "statuses": task.get("statuses", {}),
                "tag_status_id": tag_status_id,
            }
            missed_activities.append(task_info)

            if task_type not in result["activities_by_type"]:
                result["activities_by_type"][task_type] = []
            result["activities_by_type"][task_type].append(
                f"{task['task']} ({task_info['start_time']}-{task_info['end_time']})"
            )

    result["activities"] = missed_activities
    result["total_missed_activities"] = len(missed_activities)

    if missed_activities:
        first_task = missed_activities[0]
        last_task = missed_activities[-1]
        result["insights"]["first_missed"] = f"{first_task['name']} ({first_task['start_time']}-{first_task['end_time']})"
        result["insights"]["last_missed"] = f"{last_task['name']} ({last_task['start_time']}-{last_task['end_time']})"
        result["insights"]["missed_types"] = sorted(list(missed_types))

    return result


def get_upcoming_activities(
    timetable: list[dict[str, Any]],
    given_dt: datetime,
    lookahead_hours: float,
    lookup: dict[str, dict[str, int]] | None,
) -> dict[str, Any]:
    """
    Get upcoming scheduled activities for the lookahead period.
    """
    if lookahead_hours == 0:
        return _build_empty_upcoming_section()

    start_dt, end_dt = calculate_time_range(given_dt, lookahead_hours)
    scheduled_tasks = get_tasks_in_range(timetable, start_dt, end_dt)

    logger.debug(
        "Found %d scheduled tasks for upcoming activities from %s to %s",
        len(scheduled_tasks),
        start_dt,
        end_dt,
    )

    result: dict[str, Any] = {
        "period": {"start": format_datetime(start_dt), "end": format_datetime(end_dt)},
        "total_upcoming_activities": 0,
        "activities": [],
        "activities_by_type": {},
        "insights": {
            "first_upcoming": None,
            "last_upcoming": None,
            "upcoming_types": [],
        },
    }

    if not scheduled_tasks:
        return result

    upcoming_types: set[str] = set()

    for task in scheduled_tasks:
        task_type = categorize_task(task["task"])
        upcoming_types.add(task_type)
        keyword_id, tag_status_id = resolve_ids_from_lookup(task, lookup)

        task_info = {
            "name": task["task"],
            "start_time": format_time(task["task_start_dt"]),
            "end_time": format_time(task["task_end_dt"]),
            "keywords": parse_task_keywords(task.get("keywords", "")),
            "keyword_id": keyword_id,
            "statuses": task.get("statuses", {}),
            "tag_status_id": tag_status_id,
        }
        result["activities"].append(task_info)

        if task_type not in result["activities_by_type"]:
            result["activities_by_type"][task_type] = []
        result["activities_by_type"][task_type].append(
            f"{task['task']} ({task_info['start_time']}-{task_info['end_time']})"
        )

    result["total_upcoming_activities"] = len(result["activities"])

    if result["activities"]:
        first_task = result["activities"][0]
        last_task = result["activities"][-1]
        result["insights"]["first_upcoming"] = f"{first_task['name']} ({first_task['start_time']}-{first_task['end_time']})"
        result["insights"]["last_upcoming"] = f"{last_task['name']} ({last_task['start_time']}-{last_task['end_time']})"
        result["insights"]["upcoming_types"] = sorted(list(upcoming_types))

    return result


def process_facility_activity(
    tenant: TenantContext,
    facility_id: int,
    given_dt: datetime,
    lookback_hours: float,
    lookahead_hours: float,
    tolerance_minutes: int,
) -> dict[str, Any]:
    """
    Process activity check for a single facility.

    Args:
        tenant: Tenant context
        facility_id: Facility ID
        given_dt: Reference datetime
        lookback_hours: Hours to look back (positive value)
        lookahead_hours: Hours to look ahead (positive value)
        tolerance_minutes: Tolerance in minutes

    Returns:
        Dict with 'missed' and 'upcoming' sections
    """
    logger.info(
        "Processing activity for facility=%d, lookback=%sh, lookahead=%sh",
        facility_id,
        lookback_hours,
        lookahead_hours,
    )

    timetable = load_timetable(tenant.customer_key, facility_id)
    lookup = db_adapter.get_keyword_status_lookup(tenant, facility_id)

    lookback_negative = -lookback_hours
    start_dt, end_dt = calculate_time_range(given_dt, lookback_negative)
    cache_end = end_dt + timedelta(minutes=tolerance_minutes)

    logger.debug("Fetching records from %s to %s", start_dt, cache_end)
    cached_records = db_adapter.get_records(tenant, facility_id, start_dt, cache_end)
    logger.debug("Fetched %d records for facility=%d", len(cached_records), facility_id)

    missed_section = get_missed_activities(
        timetable=timetable,
        cached_records=cached_records,
        given_dt=given_dt,
        lookback_hours=lookback_negative,
        tolerance_minutes=tolerance_minutes,
        lookup=lookup,
    )

    upcoming_section = get_upcoming_activities(
        timetable=timetable,
        given_dt=given_dt,
        lookahead_hours=lookahead_hours,
        lookup=lookup,
    )

    return {
        "missed": missed_section,
        "upcoming": upcoming_section,
    }


async def process_activity(
    tenant: TenantContext,
    facility_ids: list[int],
    facility_names: dict[int, str],
    lookback_hours: float,
    lookahead_hours: float,
    tolerance_minutes: int,
) -> dict[str, Any]:
    """
    Process activity check for multiple facilities, aggregating results.

    Args:
        tenant: Tenant context
        facility_ids: List of facility IDs to check
        facility_names: Mapping of facility_id to facility name
        lookback_hours: Hours to look back (positive value)
        lookahead_hours: Hours to look ahead (positive value)
        tolerance_minutes: Tolerance in minutes

    Returns:
        Aggregated result with per-facility breakdown
    """
    given_dt = datetime.now()

    logger.info(
        "Processing activity for %d facilities: lookback=%sh, lookahead=%sh, reference=%s",
        len(facility_ids),
        lookback_hours,
        lookahead_hours,
        given_dt.strftime("%Y-%m-%d %H:%M:%S"),
    )

    by_facility: dict[str, dict[str, Any]] = {}
    total_missed = 0
    total_upcoming = 0

    for facility_id in facility_ids:
        try:
            result = process_facility_activity(
                tenant=tenant,
                facility_id=facility_id,
                given_dt=given_dt,
                lookback_hours=lookback_hours,
                lookahead_hours=lookahead_hours,
                tolerance_minutes=tolerance_minutes,
            )

            facility_key = str(facility_id)
            by_facility[facility_key] = {
                "facility_name": facility_names.get(facility_id, f"Facility {facility_id}"),
                "missed": result["missed"],
                "upcoming": result["upcoming"],
            }

            total_missed += result["missed"]["total_missed_activities"]
            total_upcoming += result["upcoming"]["total_upcoming_activities"]

        except Exception as e:
            logger.error("Failed to process facility %d: %s", facility_id, str(e))
            by_facility[str(facility_id)] = {
                "facility_name": facility_names.get(facility_id, f"Facility {facility_id}"),
                "error": str(e),
                "missed": _build_empty_missed_section(),
                "upcoming": _build_empty_upcoming_section(),
            }

    return {
        "total_missed": total_missed,
        "total_upcoming": total_upcoming,
        "facility_count": len(facility_ids),
        "by_facility": by_facility,
        "given_date_time": given_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_hours": lookback_hours,
        "lookahead_hours": lookahead_hours,
    }
