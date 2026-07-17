"""Shared utilities for HA configuration tools."""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from tools.validators.base import (  # noqa: F401 — re-exported
    HAYamlLoader,
    ValidatorBase,
)

DEFAULT_HA_URL = "http://homeassistant.local:8123"
DEFAULT_SUMMARY_MAX_CHARS = 8000


def load_env_file(path: Path | None = None) -> None:
    """Load environment variables from .env file.

    Does NOT override variables already present in ``os.environ`` (standard
    python-dotenv convention) — shell-set values win, so a freshly rotated
    HA_TOKEN isn't silently overwritten by a stale .env entry.

    Args:
        path: Optional explicit path to the .env file. Defaults to
            ``<project_root>/.env``.
    """
    env_file = path or (Path(__file__).parent.parent / ".env")
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                if key and key not in os.environ:
                    os.environ[key] = value.strip().strip('"').strip("'")


def get_env_int(name: str, default: int, *, minimum: int = 1) -> tuple[int, str | None]:
    """Read an integer env var with validation and fallback.

    Returns:
        A tuple of (value, warning). warning is None when the parsed value is valid.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default, None

    try:
        value = int(raw)
    except ValueError:
        return default, f"{name} must be an integer, got {raw!r}; using {default}"

    if value < minimum:
        return (
            default,
            f"{name} must be >= {minimum}, got {value}; using {default}",
        )

    return value, None


def validate_ha_url(ha_url: str) -> str | None:
    """Validate HA URL format and return an error message when invalid."""
    parsed = urlparse(ha_url)
    if parsed.scheme not in {"http", "https"}:
        return "HA_URL must start with http:// or https://"
    if not parsed.netloc:
        return "HA_URL must include a hostname"
    return None


def _is_tty() -> bool:
    """Check if stdout is connected to a terminal.

    Returns False when stdout is piped, redirected to a file, or absent
    (e.g. when called from an agent or CI runner). Never raises.
    """
    try:
        return sys.stdout is not None and sys.stdout.isatty()
    except AttributeError, OSError, TypeError:
        return False


def _has_transform_flags(args: argparse.Namespace) -> bool:
    """Check if the curl command has any output-transforming flags active.

    Used by the bare-endpoint guardrail to detect whether the user has
    explicitly requested transformed output.  Returning True means the
    guardrail should not fire.

    Flags checked: count, keys, first, raw, pick, entity, domain,
    max_chars.
    """
    return bool(
        args.count
        or args.keys
        or args.first is not None
        or args.raw
        or bool(args.pick)
        or bool(args.entity)
        or bool(args.domain)
        or args.max_chars is not None
    )


def positive_int(value: str) -> int:
    """Argparse type: reject values < 1."""
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return n


def non_negative_int(value: str) -> int:
    """Argparse type: reject values < 0."""
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return n


def positive_float(value: str) -> float:
    """Argparse type: reject values <= 0."""
    f = float(value)
    if f <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return f


def resolve_summary(args: argparse.Namespace) -> bool:
    """Resolve summary/verbose mode from argparse --summary/--no-summary flags.

    Logic:
        --summary       → True
        --no-summary    → False
        both            → warn on stderr, treat as --summary
        neither         → True when non-TTY, False when TTY

    Returns:
        True for compact/summary output, False for verbose.
    """
    explicit_summary = bool(getattr(args, "summary", False))
    explicit_no_summary = bool(getattr(args, "no_summary", False))
    if explicit_summary and explicit_no_summary:
        print(
            "WARN: conflicting --summary / --no-summary; using --summary",
            file=sys.stderr,
        )
    if explicit_summary:
        return True
    if explicit_no_summary:
        return False
    return not _is_tty()


def resolve_max_chars(args: argparse.Namespace, summary: bool) -> int | None:
    """Resolve effective --max-chars: explicit flag > HA_CLI_MAX_CHARS env > default.

    Returns None when no cap should apply. ``--max-chars 0`` always disables.
    """
    explicit = getattr(args, "max_chars", None)
    if explicit is not None:
        return explicit if explicit > 0 else None

    env_val = os.getenv("HA_CLI_MAX_CHARS")
    if env_val:
        try:
            n = int(env_val)
            if n > 0:
                return n
        except ValueError:
            pass

    if summary:
        return DEFAULT_SUMMARY_MAX_CHARS
    return None


def add_output_shape_args(
    parser: argparse.ArgumentParser,
    *,
    first: bool = True,
    pick: bool = True,
    max_chars: bool = True,
) -> None:
    """Attach the standard token-reduction flags to *parser*."""
    if first:
        parser.add_argument(
            "--first",
            metavar="N",
            type=positive_int,
            help="Keep only the first N items",
        )
    if pick:
        parser.add_argument(
            "--pick",
            metavar="FIELDS",
            help="Keep only specified JSON keys (comma-separated)",
        )
    if max_chars:
        parser.add_argument(
            "--max-chars",
            metavar="N",
            type=non_negative_int,
            help="Truncate JSON above N chars (0 disables; default 8000 in summary)",
        )


class HARequestError(Exception):
    """Raised when a Home Assistant REST API request fails."""
