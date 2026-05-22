"""
Timetable Loader for Daily Activity Pipeline.

Production: Loads timetable from DynamoDB customer config table.
Fallback: Local JSON files for development/testing.

Lookup order:
1. DynamoDB customer config (timetables field) — production
2. {TIMETABLE_DIR}/{customer_key}/{facility_id}.json — per-facility local
3. {TIMETABLE_DIR}/{customer_key}/default.json — per-tenant default local
4. {TIMETABLE_DIR}/default.json — global default local
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.shared.config import DAILY_ACTIVITY_TIMETABLE_DIR
from src.shared.logger import get_logger

logger = get_logger(__name__)


class TimetableNotFoundError(Exception):
    """Raised when no timetable can be found for the given parameters."""

    pass


def _get_timetable_dir() -> Path:
    """Get the base timetable directory path."""
    return Path(DAILY_ACTIVITY_TIMETABLE_DIR)


def _try_load_json(path: Path) -> list[dict[str, Any]] | None:
    """Try to load a JSON file, return None if not found."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug("Loaded timetable from %s", path)
            return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to load timetable from %s: %s", path, str(e))
        return None


def _load_from_customer_config(customer_key: str, facility_id: int) -> list[dict[str, Any]] | None:
    """
    Load timetable from DynamoDB customer config.

    Expected config structure:
    {
        "timetables": {
            "63": [...timetable data...],   # per-facility
            "default": [...timetable data...]  # fallback for all facilities
        }
    }
    """
    try:
        from src.tenant.customer_config import get_customer_config

        config = get_customer_config(customer_key)
        timetables = config.get("timetables", {})

        if not timetables:
            return None

        # Try facility-specific timetable first
        facility_key = str(facility_id)
        if facility_key in timetables:
            timetable = timetables[facility_key]
            if isinstance(timetable, str):
                timetable = json.loads(timetable)
            logger.info(
                "Loaded timetable from customer config for customer=%s facility=%s",
                customer_key,
                facility_id,
            )
            return timetable

        # Try default timetable for customer
        if "default" in timetables:
            timetable = timetables["default"]
            if isinstance(timetable, str):
                timetable = json.loads(timetable)
            logger.info(
                "Loaded default timetable from customer config for customer=%s",
                customer_key,
            )
            return timetable

        return None
    except Exception as e:
        logger.warning(
            "Failed to load timetable from customer config for customer=%s: %s",
            customer_key,
            str(e),
        )
        return None


def get_activity_config(customer_key: str) -> dict[str, Any]:
    """
    Get daily activity configuration from customer config.

    Returns:
        Dict with lookback_hours, lookahead_hours, tolerance_minutes
    """
    try:
        from src.tenant.customer_config import get_customer_config

        config = get_customer_config(customer_key)
        return {
            "lookback_hours": config.get("daily_activity_lookback_hours", 8.0),
            "lookahead_hours": config.get("daily_activity_lookahead_hours", 4.0),
            "tolerance_minutes": config.get("daily_activity_tolerance_minutes", 0),
        }
    except Exception as e:
        logger.warning("Failed to get activity config for customer=%s: %s", customer_key, str(e))
        from src.shared.config import (
            DAILY_ACTIVITY_LOOKAHEAD_HOURS,
            DAILY_ACTIVITY_LOOKBACK_HOURS,
            DAILY_ACTIVITY_TOLERANCE_MINUTES,
        )
        return {
            "lookback_hours": DAILY_ACTIVITY_LOOKBACK_HOURS,
            "lookahead_hours": DAILY_ACTIVITY_LOOKAHEAD_HOURS,
            "tolerance_minutes": DAILY_ACTIVITY_TOLERANCE_MINUTES,
        }


@lru_cache(maxsize=100)
def load_timetable(customer_key: str, facility_id: int) -> list[dict[str, Any]]:
    """
    Load timetable with fallback logic.

    Lookup order:
    1. DynamoDB customer config (timetables field) — production
    2. {TIMETABLE_DIR}/{customer_key}/{facility_id}.json — per-facility local
    3. {TIMETABLE_DIR}/{customer_key}/default.json — per-tenant default local
    4. {TIMETABLE_DIR}/default.json — global default local

    Args:
        customer_key: Tenant identifier
        facility_id: Facility ID

    Returns:
        Timetable as list of day schedules

    Raises:
        TimetableNotFoundError: If no timetable found at any level
    """
    # Try customer config (DynamoDB) first
    timetable = _load_from_customer_config(customer_key, facility_id)
    if timetable is not None:
        return timetable

    # Fallback to local JSON files
    base_dir = _get_timetable_dir()

    paths_to_try = [
        base_dir / customer_key / f"{facility_id}.json",
        base_dir / customer_key / "default.json",
        base_dir / "default.json",
    ]

    for path in paths_to_try:
        timetable = _try_load_json(path)
        if timetable is not None:
            logger.info(
                "Using timetable for customer=%s facility=%s from %s",
                customer_key,
                facility_id,
                path,
            )
            return timetable

    logger.error(
        "No timetable found for customer=%s facility=%s. Tried: %s",
        customer_key,
        facility_id,
        [str(p) for p in paths_to_try],
    )
    raise TimetableNotFoundError(
        f"No timetable found for customer_key={customer_key}, facility_id={facility_id}"
    )


def clear_timetable_cache() -> None:
    """Clear the timetable cache (useful for testing or after updates)."""
    load_timetable.cache_clear()
    logger.info("Timetable cache cleared")


def get_day_schedule(timetable: list[dict[str, Any]], day_name: str) -> list[dict[str, Any]]:
    """
    Get the schedule for a specific day.

    Args:
        timetable: Full timetable data
        day_name: Day name (e.g., 'Monday', 'Tuesday')

    Returns:
        List of tasks for the day, or empty list if not found
    """
    for day_schedule in timetable:
        if day_schedule.get("day") == day_name:
            return day_schedule.get("tasks", [])
    return []
