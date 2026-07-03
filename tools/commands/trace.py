"""``trace`` subcommand: fetch Home Assistant automation traces via WebSocket."""

import argparse
import json
import re
import sys

from tools.common import (
    HARequestError,
    add_output_shape_args,
    resolve_max_chars,
    resolve_summary,
)
from tools.ha.client import HAWSClient
from tools.output_shape import apply_output_shape

_ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``trace`` subparser."""
    parser = subparsers.add_parser(
        "trace",
        help="Fetch Home Assistant automation traces.",
        description=(
            "Fetch automation trace data from Home Assistant via WebSocket. "
            "With an entity_id, shows the trace for that automation; "
            "without one, lists all available traces."
        ),
    )
    parser.add_argument(
        "entity_id",
        nargs="?",
        default=None,
        help="Automation entity ID (e.g. automation.morning_routine)",
    )
    add_output_shape_args(parser)
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output with indent=2 (default: compact)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Compact output; auto-detected when stdout is not a TTY",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Force verbose output even when stdout is piped",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``trace`` subcommand. Returns exit code."""
    summary = resolve_summary(args)

    if args.entity_id is not None and not _ENTITY_RE.fullmatch(args.entity_id):
        print(f"\u274c Invalid entity_id: {args.entity_id!r}", file=sys.stderr)
        return 1

    # Validate --first early, before any API call.
    if args.first is not None and args.first < 1:
        print("\u274c --first must be >= 1", file=sys.stderr)
        return 1

    if args.entity_id and args.first is not None and not summary:
        print(
            "\u26a0\ufe0f  --first is ignored when fetching a single automation trace",
            file=sys.stderr,
        )

    try:
        client = HAWSClient.from_env()
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    try:
        if args.entity_id:
            # Two-step lookup: list traces to find run_id, then get detail.
            # Opens two WebSocket connections (~200ms overhead).
            traces = client.command("trace/list", domain="automation")
            item_id = args.entity_id.split(".", 1)[1]
            matching = [t for t in traces if t.get("item_id") == item_id]
            if not matching:
                print(
                    f"\u274c No traces found for {args.entity_id}",
                    file=sys.stderr,
                )
                return 1
            # Sort by timestamp start (most recent first) — list may not be ordered.
            matching.sort(
                key=lambda t: t.get("timestamp", {}).get("start", ""),
                reverse=True,
            )
            latest = matching[0]
            data = client.command(
                "trace/get",
                domain="automation",
                item_id=latest["item_id"],
                run_id=latest["run_id"],
            )
        else:
            data = client.command("trace/list", domain="automation")
            # Summary-mode projection: compact fields for non-TTY agents.
            if summary and not args.pretty:
                # Project to compact fields first.
                compact = [
                    {
                        "item_id": t.get("item_id"),
                        "state": t.get("state"),
                        "trigger": t.get("trigger"),
                        "timestamp": (t.get("timestamp") or {}).get("start"),
                    }
                    for t in data
                ]
                # Sort newest-first, then dedupe by item_id keeping most-recent.
                compact.sort(
                    key=lambda x: x.get("timestamp") or "",
                    reverse=True,
                )
                seen: dict[str, dict] = {}
                run_counts: dict[str, int] = {}
                for entry in compact:
                    iid = entry.get("item_id") or ""
                    run_counts[iid] = run_counts.get(iid, 0) + 1
                    if iid not in seen:
                        seen[iid] = entry
                data = list(seen.values())
                # Add runs field only when there's actual duplication.
                for entry in data:
                    n = run_counts.get(entry.get("item_id") or "", 1)
                    if n > 1:
                        entry["runs"] = n
    except HARequestError as e:
        print(f"\u274c {e}", file=sys.stderr)
        return 1

    # Summary-mode single-entity: drop verbose fields (config is redundant,
    # blueprint_inputs rarely needed).  Respects --pretty override.
    if args.entity_id and summary and not args.pretty and isinstance(data, dict):
        data = {
            k: v for k, v in data.items() if k not in ("config", "blueprint_inputs")
        }
        if isinstance(data.get("trace"), dict):
            data["trace"] = _prune_trace_entries(data["trace"])

    # Apply output shaping (--first, --pick, --max-chars).
    if not args.entity_id:
        # List mode: full output shaping.
        # NOTE: single-entity mode returns a dict; apply_output_shape does not
        # truncate dicts (only lists). Single-entity traces may exceed --max-chars;
        # --pick still works.
        data = apply_output_shape(
            data,
            first=args.first,
            pick=args.pick,
            max_chars=resolve_max_chars(args, summary),
        )
    else:
        # Single-entity dict: only --pick applies.
        data = apply_output_shape(data, pick=args.pick)

    if args.pretty:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))

    return 0


def _prune_trace_entries(trace: dict) -> dict:
    """Drop changed_variables.this.attributes from trace entries.

    Keeps this.entity_id and this.state for debugging context.
    Defensive against malformed entries (non-list values, missing keys).
    Mutates nothing — returns a new dict.
    """
    pruned: dict = {}
    for step_key, entries in trace.items():
        if not isinstance(entries, list):
            pruned[step_key] = entries
            continue
        new_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                new_entries.append(entry)
                continue
            cv = entry.get("changed_variables")
            if isinstance(cv, dict) and isinstance(cv.get("this"), dict):
                this = dict(cv["this"])
                this.pop("attributes", None)
                entry = {**entry, "changed_variables": {**cv, "this": this}}
            new_entries.append(entry)
        pruned[step_key] = new_entries
    return pruned
