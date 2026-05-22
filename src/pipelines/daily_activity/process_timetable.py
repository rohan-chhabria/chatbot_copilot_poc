"""
Process Timetable — Convert CSV timetable to JSON format.

Usage:
    python -m src.pipelines.daily_activity.process_timetable input.csv output.json

CSV Format:
    Time,Keywords,Statuses,Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday
    0300-0400,Official Count |,...,Count-Official,Count-Official,...

Time: HHMM-HHMM format (24-hour)
Keywords: Pipe-separated keywords (e.g., "Keyword1 |, Keyword2 |")
Statuses: Comma-separated status:substatus pairs (e.g., "Status1, Status2:Sub1")
Day columns: Task names for each day
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def format_statuses(statuses: str) -> dict[str, list[str]]:
    """Format statuses string into a dictionary structure."""
    if not statuses or not statuses.strip():
        return {}

    formatted_statuses: dict[str, list[str]] = {}
    for item in statuses.split(","):
        item = item.strip()
        if ":" in item:
            status, sub = (part.strip() for part in item.split(":", 1))
            formatted_statuses.setdefault(status, []).append(sub)
        else:
            formatted_statuses.setdefault(item, [])
    return formatted_statuses


def parse_keywords(keywords: str) -> str:
    """Return keywords string as is, preserving | characters."""
    return keywords.strip() if keywords else ""


def convert_to_time_format(time_str: str) -> str:
    """Convert time string (HHMM or HHMMSS format) to HH:MM:SS."""
    time_str = time_str.strip()
    if len(time_str) == 4:
        hour = int(time_str[:2])
        minute = int(time_str[2:])
        return f"{hour:02d}:{minute:02d}:00"
    elif len(time_str) == 6:
        hour = int(time_str[:2])
        minute = int(time_str[2:4])
        second = int(time_str[4:6])
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    elif ":" in time_str:
        return time_str
    return ""


def parse_time_range(time_range: str) -> tuple[str, str]:
    """Parse time range string (e.g., '0045-0100') into start and end times."""
    if not time_range or "-" not in time_range:
        return "", ""

    start_str, end_str = time_range.split("-")
    start_time = convert_to_time_format(start_str)
    end_time = convert_to_time_format(end_str)

    return start_time, end_time


def process_csv(input_file: str, output_file: str | None = None) -> str:
    """
    Process CSV file and convert to JSON format.

    Args:
        input_file: Path to input CSV file
        output_file: Path to output JSON file (defaults to input_file.json)

    Returns:
        Path to output file
    """
    input_path = Path(input_file)
    if output_file is None:
        output_file = str(input_path.with_suffix(".json"))

    day_columns: list[str] = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    day_tasks_map: dict[str, list[dict[str, Any]]] = {day: [] for day in day_columns}

    with open(input_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            time_range: str = row.get("Time", "")
            keywords_str: str = row.get("Keywords", "")
            statuses_str: str = row.get("Statuses", "")

            keywords: str = parse_keywords(keywords_str)
            statuses: dict[str, list[str]] = format_statuses(statuses_str)
            start_time, end_time = parse_time_range(time_range)

            for day in day_columns:
                task_name: str = row.get(day, "").strip()

                if task_name:
                    task_obj: dict[str, Any] = {
                        "keywords": keywords,
                        "statuses": statuses,
                        "start_time": start_time,
                        "end_time": end_time,
                        "task": task_name,
                    }
                    day_tasks_map[day].append(task_obj)

    result: list[dict[str, Any]] = []
    for day in day_columns:
        if day_tasks_map[day]:
            result.append({"day": day, "tasks": day_tasks_map[day]})

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    total_tasks: int = sum(len(tasks) for tasks in day_tasks_map.values())
    print(f"Successfully processed {input_file} -> {output_file}")
    print(f"Total days: {len(result)}, Total tasks: {total_tasks}")

    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert CSV timetable to JSON format for Daily Activity Pipeline",
        epilog="Example: python -m src.pipelines.daily_activity.process_timetable input.csv output.json",
    )
    parser.add_argument("input", help="Input CSV file path")
    parser.add_argument("output", nargs="?", help="Output JSON file path (optional)")

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    try:
        process_csv(args.input, args.output)
    except Exception as e:
        print(f"Error processing file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
