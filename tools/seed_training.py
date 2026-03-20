"""
Seed Training — One-time script to populate ChromaDB with training data.

Usage:
    python -m tools.seed_training
    python -m tools.seed_training --examples path/to/examples.json
    python -m tools.seed_training --docs path/to/documentation.json
"""

from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.training.trainer import (
    get_training_stats,
    train_documentation,
    train_examples,
    train_from_defaults,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed ChromaDB training data")
    parser.add_argument("--examples", type=str, help="Path to examples JSON file")
    parser.add_argument("--docs", type=str, help="Path to documentation JSON file")
    parser.add_argument("--defaults", action="store_true", help="Load default training data")
    args = parser.parse_args()

    if args.defaults or (not args.examples and not args.docs):
        print("Loading default training data...")
        result = train_from_defaults()
        print(f"Trained: {result['examples']} examples, {result['documentation']} docs")
    else:
        if args.examples:
            count = train_examples(args.examples)
            print(f"Trained {count} examples from {args.examples}")

        if args.docs:
            count = train_documentation(args.docs)
            print(f"Trained {count} documentation entries from {args.docs}")

    stats = get_training_stats()
    print(f"\nTraining stats: {stats}")


if __name__ == "__main__":
    main()
