#!/usr/bin/env python3
"""Remove an entity reference from a Home Assistant Lovelace storage file."""

import argparse
import json
from pathlib import Path
from typing import Any

from tools.common import atomic_write_text, fail_stderr


def remove_entity_from_lovelace(
    data: dict[str, Any], target_entity: str
) -> tuple[dict[str, Any], int]:
    """Remove all occurrences of *target_entity* from Lovelace entity cards."""
    removed_count = 0
    views = data.get("data", {}).get("config", {}).get("views", [])
    for view in views:
        for card in view.get("cards", []):
            if "entities" in card and isinstance(card["entities"], list):
                new_entities = []
                for e in card["entities"]:
                    eid = e if isinstance(e, str) else e.get("entity")
                    if eid == target_entity:
                        removed_count += 1
                    else:
                        new_entities.append(e)
                card["entities"] = new_entities
    return data, removed_count


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove an entity reference from a Lovelace JSON storage file."
    )
    parser.add_argument("target_file", type=Path, help="Path to Lovelace JSON file")
    parser.add_argument("entity_id", help="Entity ID to remove")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on success, 1 on error."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code in (0, None) else 1

    file_path: Path = args.target_file
    target_entity: str = args.entity_id

    if not file_path.is_file():
        return fail_stderr(f"{file_path} does not exist")

    try:
        with file_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return fail_stderr(f"Error reading JSON from {file_path}: {e}")

    data, count = remove_entity_from_lovelace(data, target_entity)
    print(f"Removed {count} occurrence(s) of '{target_entity}' from {file_path}")

    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if not atomic_write_text(file_path, payload):
        return fail_stderr(f"Failed to write {file_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
