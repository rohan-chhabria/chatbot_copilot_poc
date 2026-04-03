"""
Response Formatter for Daily Activity Pipeline.

Generates template-based natural language summaries (no LLM).
Handles single and multi-facility cases with various edge cases.
"""

from __future__ import annotations

from typing import Any


REFRESH_INSTRUCTION = '💡 Type "refresh" to update.'


def _format_activity_list(activities: list[dict[str, Any]], max_items: int = 10) -> str:
    """Format a list of activities as bullet points with full duration."""
    lines = []
    for activity in activities[:max_items]:
        name = activity["name"]
        start = activity["start_time"]
        end = activity["end_time"]
        lines.append(f"- {name} ({start}-{end})")

    if len(activities) > max_items:
        lines.append(f"- ... and {len(activities) - max_items} more")

    return "\n".join(lines)


def _format_activity_inline(activities: list[dict[str, Any]], max_items: int = 5) -> str:
    """Format activities inline with commas for compact display."""
    items = []
    for activity in activities[:max_items]:
        name = activity["name"]
        start = activity["start_time"]
        end = activity["end_time"]
        items.append(f"{name} ({start}-{end})")

    result = ", ".join(items)
    if len(activities) > max_items:
        result += f", +{len(activities) - max_items} more"

    return result


def format_single_facility_response(
    facility_name: str,
    missed: dict[str, Any],
    upcoming: dict[str, Any],
    lookback_hours: float,
    lookahead_hours: float,
) -> str:
    """
    Format response for a single facility.

    Templates:
    - Both missed and upcoming
    - Only missed
    - Only upcoming
    - All clear (no missed, has upcoming)
    - Nothing scheduled
    """
    missed_count = missed.get("total_missed_activities", 0)
    upcoming_count = upcoming.get("total_upcoming_activities", 0)
    missed_activities = missed.get("activities", [])
    upcoming_activities = upcoming.get("activities", [])

    lines = []

    if missed_count == 0 and upcoming_count == 0:
        lines.append(f"✅ No missed or upcoming activities for {facility_name}.")
        lines.append("")
        lines.append(REFRESH_INSTRUCTION)
        return "\n".join(lines)

    if missed_count == 0 and upcoming_count > 0:
        lines.append(
            f"✅ No missed activities for {facility_name} in the last {int(lookback_hours)} hours."
        )
        lines.append("")
        lines.append(f"📌 **{upcoming_count} upcoming** in the next {int(lookahead_hours)} hours:")
        lines.append(_format_activity_list(upcoming_activities))
        lines.append("")
        lines.append(REFRESH_INSTRUCTION)
        return "\n".join(lines)

    if missed_count > 0 and upcoming_count == 0:
        lines.append(f"You have **{missed_count} missed** activities for {facility_name}.")
        lines.append("")
        lines.append(f"⚠️ **Missed (last {int(lookback_hours)}h):**")
        lines.append(_format_activity_list(missed_activities))
        lines.append("")
        lines.append(f"No upcoming activities in the next {int(lookahead_hours)} hours.")
        lines.append("")
        lines.append(REFRESH_INSTRUCTION)
        return "\n".join(lines)

    lines.append(
        f"You have **{missed_count} missed** and **{upcoming_count} upcoming** "
        f"activities for {facility_name}."
    )
    lines.append("")
    lines.append(f"⚠️ **Missed (last {int(lookback_hours)}h):**")
    lines.append(_format_activity_list(missed_activities))
    lines.append("")
    lines.append(f"📌 **Upcoming (next {int(lookahead_hours)}h):**")
    lines.append(_format_activity_list(upcoming_activities))
    lines.append("")
    lines.append(REFRESH_INSTRUCTION)

    return "\n".join(lines)


def format_multi_facility_response(
    by_facility: dict[str, dict[str, Any]],
    total_missed: int,
    total_upcoming: int,
    lookback_hours: float,
    lookahead_hours: float,
) -> str:
    """
    Format response for multiple facilities with aggregated summary.
    """
    facility_count = len(by_facility)
    lines = []

    if total_missed == 0 and total_upcoming == 0:
        lines.append(f"✅ No missed or upcoming activities across {facility_count} facilities.")
        lines.append("")
        lines.append(REFRESH_INSTRUCTION)
        return "\n".join(lines)

    lines.append(
        f"Across **{facility_count} facilities**, you have "
        f"**{total_missed} missed** and **{total_upcoming} upcoming** activities."
    )
    lines.append("")

    for facility_id, data in by_facility.items():
        facility_name = data.get("facility_name", f"Facility {facility_id}")
        missed = data.get("missed", {})
        upcoming = data.get("upcoming", {})
        missed_count = missed.get("total_missed_activities", 0)
        upcoming_count = upcoming.get("total_upcoming_activities", 0)
        missed_activities = missed.get("activities", [])
        upcoming_activities = upcoming.get("activities", [])

        if "error" in data:
            lines.append(f"🏢 **{facility_name}** — Error: {data['error']}")
            lines.append("")
            continue

        lines.append(f"🏢 **{facility_name}** — {missed_count} missed, {upcoming_count} upcoming")

        if missed_count > 0:
            lines.append(f"⚠️ Missed: {_format_activity_inline(missed_activities)}")

        if upcoming_count > 0:
            lines.append(f"📌 Upcoming: {_format_activity_inline(upcoming_activities)}")

        lines.append("")

    lines.append(REFRESH_INSTRUCTION)

    return "\n".join(lines)


def format_activity_response(result: dict[str, Any]) -> str:
    """
    Main formatting function that chooses single or multi-facility template.

    Args:
        result: Result from process_activity()

    Returns:
        Formatted summary string
    """
    by_facility = result.get("by_facility", {})
    total_missed = result.get("total_missed", 0)
    total_upcoming = result.get("total_upcoming", 0)
    lookback_hours = result.get("lookback_hours", 8.0)
    lookahead_hours = result.get("lookahead_hours", 4.0)

    if len(by_facility) == 0:
        return f"⚠️ No facilities found.\n\n{REFRESH_INSTRUCTION}"

    if len(by_facility) == 1:
        facility_id, data = next(iter(by_facility.items()))
        facility_name = data.get("facility_name", f"Facility {facility_id}")
        missed = data.get("missed", {})
        upcoming = data.get("upcoming", {})

        if "error" in data:
            return (
                f"⚠️ Error checking activities for {facility_name}: {data['error']}\n\n"
                f"{REFRESH_INSTRUCTION}"
            )

        return format_single_facility_response(
            facility_name=facility_name,
            missed=missed,
            upcoming=upcoming,
            lookback_hours=lookback_hours,
            lookahead_hours=lookahead_hours,
        )

    return format_multi_facility_response(
        by_facility=by_facility,
        total_missed=total_missed,
        total_upcoming=total_upcoming,
        lookback_hours=lookback_hours,
        lookahead_hours=lookahead_hours,
    )


def format_error_response(error_message: str) -> str:
    """Format an error response."""
    return f"⚠️ {error_message}\n\n{REFRESH_INSTRUCTION}"


def format_no_facilities_error() -> str:
    """Format response when user has no facilities assigned."""
    return "⚠️ No facilities assigned to your profile.\n\nPlease contact your administrator."


def format_instruction_message() -> str:
    """Format the instruction message for non-refresh input."""
    return 'Type "refresh" to update your activity status.'
