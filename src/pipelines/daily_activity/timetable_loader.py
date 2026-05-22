"""
Timetable Loader for Daily Activity Pipeline.

Loads timetable JSON files with fallback logic:
1. {TIMETABLE_DIR}/{customer_key}/{facility_id}.json — per-facility
2. {TIMETABLE_DIR}/{customer_key}/default.json — per-tenant default
3. {TIMETABLE_DIR}/default.json — global default
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


@lru_cache(maxsize=100)
def load_timetable(customer_key: str, facility_id: int) -> list[dict[str, Any]]:
    """
    Load timetable with fallback logic.

    Lookup order:
    1. {TIMETABLE_DIR}/{customer_key}/{facility_id}.json — per-facility
    2. {TIMETABLE_DIR}/{customer_key}/default.json — per-tenant default
    3. {TIMETABLE_DIR}/default.json — global default

    Args:
        customer_key: Tenant identifier
        facility_id: Facility ID

    Returns:
        Timetable as list of day schedules

    Raises:
        TimetableNotFoundError: If no timetable found at any level
    """
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
