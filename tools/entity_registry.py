"""
Home Assistant Entity Registry Explorer.

Parse entity registry and provide human-readable summary of entities,
organized by domain and area for easy automation creation.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from tools.cache import _blob_hash, load_blob, save_blob
from tools.common import resolve_summary


def load_entity_registry(config_path: Path) -> dict | None:
    """Load and parse the entity registry file."""
    registry_path = config_path / ".storage" / "core.entity_registry"

    if not registry_path.exists():
        print(f"❌ Entity registry not found at {registry_path}", file=sys.stderr)
        return None

    try:
        with open(registry_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"❌ Error reading entity registry: {e}", file=sys.stderr)
        return None


def load_area_registry(config_path: Path) -> dict[str, str]:
    """Load area names from area registry."""
    area_path = config_path / ".storage" / "core.area_registry"
    area_names = {}

    if area_path.exists():
        try:
            with open(area_path, encoding="utf-8") as f:
                area_data = json.load(f)
                for area in area_data.get("data", {}).get("areas", []):
                    area_names[area["id"]] = area["name"]
        except (OSError, json.JSONDecodeError, KeyError, AttributeError) as e:
            print(f"⚠️ Could not load area names: {e}", file=sys.stderr)

    return area_names


def get_entity_display_name(entity: dict) -> str:
    """Get the best display name for an entity."""
    if entity.get("name"):
        return entity["name"]
    elif entity.get("original_name"):
        return entity["original_name"]
    else:
        # Extract from entity_id
        return entity["entity_id"].split(".")[-1].replace("_", " ").title()


def categorize_entities(entities: list[dict], area_names: dict[str, str]) -> dict:
    """Categorize entities by domain and area."""
    by_domain = defaultdict(list)
    by_area = defaultdict(list)
    automation_relevant = defaultdict(list)

    # Domains that are commonly used in automations
    key_domains = {
        "climate",
        "switch",
        "light",
        "fan",
        "cover",
        "lock",
        "camera",
        "person",
        "device_tracker",
        "media_player",
        "scene",
        "script",
        "input_boolean",
        "input_select",
        "input_number",
    }

    for entity in entities:
        if entity.get("disabled_by") or entity.get("hidden_by"):
            continue

        entity_id = entity["entity_id"]
        domain = entity_id.split(".")[0]
        display_name = get_entity_display_name(entity)
        area_id = entity.get("area_id")
        area_name = area_names.get(area_id, "No Area") if area_id else "No Area"
        device_class = entity.get("original_device_class") or entity.get("device_class")

        entity_info = {
            "entity_id": entity_id,
            "name": display_name,
            "area": area_name,
            "device_class": device_class,
            "platform": entity.get("platform"),
            "unit": entity.get("unit_of_measurement"),
        }

        by_domain[domain].append(entity_info)
        by_area[area_name].append(entity_info)

        # Categorize automation-relevant entities
        if domain in key_domains:
            automation_relevant[domain].append(entity_info)
        elif domain == "sensor" and device_class in [
            "temperature",
            "humidity",
            "motion",
            "door",
            "window",
        ]:
            automation_relevant["sensor"].append(entity_info)
        elif domain == "binary_sensor" and device_class in [
            "motion",
            "door",
            "window",
            "occupancy",
        ]:
            automation_relevant["binary_sensor"].append(entity_info)

    return {
        "by_domain": dict(by_domain),
        "by_area": dict(by_area),
        "automation_relevant": dict(automation_relevant),
    }


def print_summary(categorized: dict):
    """Print a summary of available entities."""
    print("=" * 80)
    print("HOME ASSISTANT ENTITY REGISTRY SUMMARY")
    print("=" * 80)

    # Overall stats
    total_entities = sum(
        len(entities) for entities in categorized["by_domain"].values()
    )
    total_domains = len(categorized["by_domain"])
    total_areas = len(categorized["by_area"])

    print("\n📊 OVERVIEW:")
    print(f"   Total Entities: {total_entities}")
    print(f"   Domains: {total_domains}")
    print(f"   Areas: {total_areas}")

    # Automation-relevant entities
    print("\n🤖 AUTOMATION-RELEVANT ENTITIES:")
    for domain in sorted(categorized["automation_relevant"].keys()):
        entities = categorized["automation_relevant"][domain]
        print(f"   {domain.upper()}: {len(entities)} entities")

        # Show a few examples
        for entity in entities[:3]:
            area_str = f" ({entity['area']})" if entity["area"] != "No Area" else ""
            unit_str = f" [{entity['unit']}]" if entity.get("unit") else ""
            print(f"     • {entity['entity_id']}{area_str}{unit_str}")

        if len(entities) > 3:
            print(f"     ... and {len(entities) - 3} more")
        print()


def print_detailed_by_domain(categorized: dict, domain_filter: str | None = None):
    """Print detailed breakdown by domain."""
    print("\n" + "=" * 80)
    print("ENTITIES BY DOMAIN")
    print("=" * 80)

    domains_to_show = (
        [domain_filter] if domain_filter else sorted(categorized["by_domain"].keys())
    )

    for domain in domains_to_show:
        if domain not in categorized["by_domain"]:
            print(f"Domain '{domain}' not found", file=sys.stderr)
            continue

        entities = categorized["by_domain"][domain]
        print(f"\n🏷️  {domain.upper()} ({len(entities)} entities):")

        for entity in sorted(entities, key=lambda x: x["entity_id"]):
            area_str = f" | {entity['area']}" if entity["area"] != "No Area" else ""
            unit_str = f" [{entity['unit']}]" if entity.get("unit") else ""
            device_class_str = (
                f" ({entity['device_class']})" if entity.get("device_class") else ""
            )

            print(f"   {entity['entity_id']}{device_class_str}{unit_str}{area_str}")


def print_by_area(categorized: dict, area_filter: str | None = None):
    """Print entities organized by area."""
    print("\n" + "=" * 80)
    print("ENTITIES BY AREA")
    print("=" * 80)

    areas_to_show = (
        [area_filter] if area_filter else sorted(categorized["by_area"].keys())
    )

    for area in areas_to_show:
        if area not in categorized["by_area"]:
            print(f"Area '{area}' not found", file=sys.stderr)
            continue

        entities = categorized["by_area"][area]
        print(f"\n🏠 {area.upper()} ({len(entities)} entities):")

        # Group by domain within area
        by_domain_in_area = defaultdict(list)
        for entity in entities:
            domain = entity["entity_id"].split(".")[0]
            by_domain_in_area[domain].append(entity)

        for domain in sorted(by_domain_in_area.keys()):
            domain_entities = by_domain_in_area[domain]
            entity_ids = ", ".join(
                e["entity_id"]
                for e in sorted(domain_entities, key=lambda x: x["entity_id"])
            )
            print(f"   {domain}: {entity_ids}")


def search_entities(categorized: dict, query: str):
    """Search for entities matching a query."""
    print(f"\n🔍 SEARCH RESULTS for '{query}':")
    print("=" * 50)

    matches = []
    query_lower = query.lower()

    for domain_entities in categorized["by_domain"].values():
        for entity in domain_entities:
            if (
                query_lower in entity["entity_id"].lower()
                or query_lower in entity["name"].lower()
                or (
                    entity.get("device_class")
                    and query_lower in entity["device_class"].lower()
                )
            ):
                matches.append(entity)

    if not matches:
        print("No matches found", file=sys.stderr)
        return

    for entity in sorted(matches, key=lambda x: x["entity_id"]):
        area_str = f" | {entity['area']}" if entity["area"] != "No Area" else ""
        unit_str = f" [{entity['unit']}]" if entity.get("unit") else ""
        device_class_str = (
            f" ({entity['device_class']})" if entity.get("device_class") else ""
        )

        print(f"   {entity['entity_id']}{device_class_str}{unit_str}{area_str}")


def run(args: argparse.Namespace) -> int:
    """Run the entity registry explorer with parsed args.

    Args:
        args: Namespace with ``config``, ``domain``, ``area``, ``search``,
              ``full``, ``json``, ``summary``, ``no_summary``, ``force``.
    """
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Config directory not found: {config_path}", file=sys.stderr)
        return 1

    # Load data
    registry_data = load_entity_registry(config_path)
    if not registry_data:
        return 1

    area_names = load_area_registry(config_path)
    entities = registry_data.get("data", {}).get("entities", [])

    if not entities:
        print("No entities found in registry", file=sys.stderr)
        return 1

    # Resolve summary mode: --json forces JSON regardless of --no-summary;
    # --full forces verbose regardless of summary mode.
    summary = resolve_summary(args)
    want_json = args.json or (summary and not args.full)
    mode = "json" if want_json else "pretty"

    # Compute cache key from registry file content + selectors + mode
    cache_key_parts: list[str | bytes] = []
    for storage_file in (
        ".storage/core.entity_registry",
        ".storage/core.area_registry",
    ):
        p = config_path / storage_file
        if p.is_file():
            cache_key_parts.append(p.read_bytes())
        cache_key_parts.append(b"\x00")  # delimiter between file contents
    cache_key_parts.extend(
        [
            "\x00",  # delimiter between file hash and selectors
            args.domain or "",
            "\x00",
            args.area or "",
            "\x00",
            args.search or "",
            "\x00",
            str(args.full),
            "\x00",
            mode,
        ]
    )
    cache_key = _blob_hash(cache_key_parts)

    # Check cache (unless --force)
    if not args.force:
        cached = load_blob(config_path, cache_key)
        if cached is not None and isinstance(cached, dict) and "output" in cached:
            sys.stdout.write(cached["output"])
            return 0

    # Cache miss — categorize and compute output
    categorized = categorize_entities(entities, area_names)

    # Capture output for caching.
    # SAFE: entity_registry is CLI-only (not called from threaded validators),
    # so contextlib.redirect_stdout is acceptable here despite not being
    # thread-safe.
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if want_json:
            _emit_json(categorized, args)
        elif args.search:
            search_entities(categorized, args.search)
        elif args.domain:
            print_detailed_by_domain(categorized, args.domain)
        elif args.area:
            print_by_area(categorized, args.area)
        elif args.full:
            print_summary(categorized)
            print_detailed_by_domain(categorized)
            print_by_area(categorized)
        else:
            print_summary(categorized)
    output = buf.getvalue()

    # Save to cache and emit
    save_blob(config_path, cache_key, {"output": output})
    sys.stdout.write(output)

    return 0


def _emit_json(categorized: dict, args: argparse.Namespace) -> None:
    """Emit compact JSON output for machine consumption.

    Selectors (--domain, --area, --search) filter the same data the pretty
    printers see; the schema is a flat list of ``{entity_id, name, area,
    device_class, unit}`` dicts. Output goes to stdout as a single JSON array
    (no banners, no emojis) — ideal for piping to ``jq`` or pasting into LLM
    prompts where every byte costs tokens.
    """
    if args.search:
        query_lower = args.search.lower()
        rows = [
            e
            for domain_entities in categorized["by_domain"].values()
            for e in domain_entities
            if query_lower in e["entity_id"].lower()
            or query_lower in e["name"].lower()
            or (e.get("device_class") and query_lower in e["device_class"].lower())
        ]
    elif args.domain:
        rows = categorized["by_domain"].get(args.domain, [])
    elif args.area:
        rows = categorized["by_area"].get(args.area, [])
    else:
        # Default to automation-relevant set for compactness
        rows = [
            e
            for domain_entities in categorized["automation_relevant"].values()
            for e in domain_entities
        ]

    # Strip None values and shorten keys to keep payload compact.
    compact = []
    for e in sorted(rows, key=lambda x: x["entity_id"]):
        row = {"e": e["entity_id"], "n": e["name"]}
        if e.get("area") and e["area"] != "No Area":
            row["a"] = e["area"]
        if e.get("device_class"):
            row["dc"] = e["device_class"]
        if e.get("unit"):
            row["u"] = e["unit"]
        compact.append(row)

    print(json.dumps(compact, separators=(",", ":")))
