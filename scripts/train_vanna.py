#!/usr/bin/env python
"""
Vanna Training Script — Load training data into ChromaDB for SQL generation.

This script trains the Vanna agent with question-SQL pairs and schema documentation
to improve SQL generation quality.

Usage:
    python scripts/train_vanna.py                          # Train from defaults
    python scripts/train_vanna.py --examples custom.json   # Custom examples
    python scripts/train_vanna.py --docs schema.json       # Custom documentation
    python scripts/train_vanna.py --stats                  # Show training stats

Examples:
    # Train from default files
    python scripts/train_vanna.py

    # Train with custom examples
    python scripts/train_vanna.py --examples ./my_examples.json

    # Check current training stats
    python scripts/train_vanna.py --stats

    # Train both examples and documentation
    python scripts/train_vanna.py --examples ex.json --docs docs.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.shared.config import TRAINING_DOCUMENTATION_PATH, TRAINING_EXAMPLES_PATH
from src.training.trainer import (
    get_training_stats,
    train_documentation,
    train_examples,
    train_from_defaults,
)


def show_stats():
    """Display current training statistics."""
    print("\n" + "=" * 50)
    print("Training Statistics")
    print("=" * 50)

    stats = get_training_stats()

    print(f"  Status:        {stats.get('status', 'unknown')}")
    print(f"  Total entries: {stats.get('total_entries', 0)}")

    if stats.get("error"):
        print(f"  Error:         {stats['error']}")

    print()


def validate_json_file(path: Path, expected_keys: list[str]) -> bool:
    """Validate a JSON file has the expected structure."""
    try:
        with open(path) as f:
            data = json.load(f)

        if not isinstance(data, list):
            print(f"Error: {path} must contain a JSON array")
            return False

        if data and not any(key in data[0] for key in expected_keys):
            print(f"Error: Items in {path} must have one of: {expected_keys}")
            return False

        return True
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {path}: {e}")
        return False
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return False


def train_custom_examples(path: Path) -> int:
    """Train from a custom examples file."""
    if not path.exists():
        print(f"Error: File not found: {path}")
        return 0

    if not validate_json_file(path, ["question", "sql"]):
        return 0

    print(f"\nTraining examples from: {path}")
    count = train_examples(str(path))
    print(f"  ✓ Trained {count} question-SQL pairs")
    return count


def train_custom_docs(path: Path) -> int:
    """Train from a custom documentation file."""
    if not path.exists():
        print(f"Error: File not found: {path}")
        return 0

    if not validate_json_file(path, ["documentation", "content"]):
        return 0

    print(f"\nTraining documentation from: {path}")
    count = train_documentation(str(path))
    print(f"  ✓ Trained {count} documentation entries")
    return count


def train_defaults() -> dict:
    """Train from default configuration files."""
    print("\nTraining from default files:")
    print(f"  Examples: {TRAINING_EXAMPLES_PATH}")
    print(f"  Docs:     {TRAINING_DOCUMENTATION_PATH}")

    result = train_from_defaults()

    print(f"\n  ✓ Trained {result['examples']} question-SQL pairs")
    print(f"  ✓ Trained {result['documentation']} documentation entries")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Train Vanna agent with question-SQL pairs and documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
File Formats:

Examples JSON (--examples):
[
  {"question": "How many notes today?", "sql": "SELECT COUNT(*) FROM dg_notes WHERE DATE(date_added) = CURDATE()"},
  {"question": "Show fire watch notes", "sql": "SELECT * FROM dg_notes n JOIN dg_notes_by_keyword k ON ..."}
]

Documentation JSON (--docs):
[
  {"documentation": "The dg_notes table stores officer notes. Key columns: notes_id, notes_description, ..."},
  {"documentation": "Join dg_notes.user_id = dg_user.username (NOT dg_user.user_id)"}
]
        """,
    )
    parser.add_argument(
        "--examples",
        type=Path,
        help="Path to custom examples JSON file",
    )
    parser.add_argument(
        "--docs",
        type=Path,
        help="Path to custom documentation JSON file",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show current training statistics",
    )
    parser.add_argument(
        "--defaults",
        action="store_true",
        help="Train from default files (src/training/data/)",
    )

    args = parser.parse_args()

    print("=" * 50)
    print("InmateCopilot — Vanna Training")
    print("=" * 50)

    # Show stats only
    if args.stats:
        show_stats()
        return

    # Train from custom files
    total_examples = 0
    total_docs = 0

    if args.examples:
        total_examples = train_custom_examples(args.examples)

    if args.docs:
        total_docs = train_custom_docs(args.docs)

    # If no custom files specified, train from defaults
    if not args.examples and not args.docs:
        result = train_defaults()
        total_examples = result["examples"]
        total_docs = result["documentation"]

    # Summary
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"  Examples trained:      {total_examples}")
    print(f"  Documentation trained: {total_docs}")
    print(f"  Total new entries:     {total_examples + total_docs}")

    # Show final stats
    show_stats()


if __name__ == "__main__":
    main()
