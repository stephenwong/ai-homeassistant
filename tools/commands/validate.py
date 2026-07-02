"""``validate`` subcommand: in-process validator runner.

Runs YAML/reference/HA-official validators in parallel threads (no subprocess
spawn) and aggregates results. Replaces the old ValidationTestRunner.
"""

import argparse
import concurrent.futures
import contextlib
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

from tools.cache import compute_hash, load_cache, save_cache
from tools.common import resolve_summary
from tools.validators.duplicate_ids import DuplicateIDValidator
from tools.validators.ha_official import HAOfficialValidator
from tools.validators.references import ReferenceValidator
from tools.validators.services import ServiceValidator
from tools.validators.stale_sensors import StaleSensorValidator
from tools.validators.templates import TemplateValidator
from tools.validators.yaml import YAMLValidator


@dataclass
class ValidatorResult:
    """Outcome of running one validator."""

    description: str
    passed: bool
    stdout: str
    stderr: str
    duration: float
    cached: bool = False


# (module_class, description) tuples for each validator in the default suite.
_VALIDATORS: list[tuple[type[Any], str]] = [
    (YAMLValidator, "YAML Syntax Validation"),
    (ReferenceValidator, "Entity/Device Reference Validation"),
    (DuplicateIDValidator, "Duplicate Automation ID Validation"),
    (ServiceValidator, "Service Reference Validation"),
    (TemplateValidator, "Jinja2 Template Validation"),
    (StaleSensorValidator, "Stale Sensor Validation"),
    (HAOfficialValidator, "Official Home Assistant Configuration Validation"),
]


def _run_one(
    cls: type,
    description: str,
    config_dir: str,
    quiet: bool,
    force: bool,
    summary: bool = False,
) -> ValidatorResult:
    """Instantiate and run a single validator; may return cached result.

    Validator ``main()``s raise SystemExit; we catch it here so that the
    parallel executor doesn't kill sibling validators. ``validate_all()``
    itself does not raise SystemExit — only ``main()`` does — so this is
    defensive for validators that have been refactored to a callable form.

    We do NOT use ``contextlib.redirect_stdout`` because it mutates
    ``sys.stdout`` globally and is not thread-safe.

    The file hash is computed once before validation and reused when
    saving the cache to avoid state-drift (e.g. HA writing .storage/
    while validation runs).
    """
    start = time.time()
    instance = cls(config_dir, quiet=quiet, summary=summary)
    name = cls.__name__

    # Compute hash once — reuse for both cache check and cache save.
    # Skip caching entirely if the validator declares no file dependencies
    # (e.g. HAOfficialValidator, whose result depends on the HA environment).
    file_deps = instance.file_deps()
    fhash: str | None = None
    if file_deps:
        with contextlib.suppress(OSError):
            fhash = compute_hash(instance.config_dir, file_deps)

    # --- cache check (skip when --force or when file_deps is empty) ---
    if not force and fhash is not None:
        try:
            cached = load_cache(instance.config_dir, name)
            if cached and cached["hash"] == fhash:
                return ValidatorResult(
                    description=description,
                    passed=bool(cached["passed"]),
                    stdout="",
                    stderr="",
                    duration=cached.get("duration", 0.0),
                    cached=True,
                )
        except OSError, json.JSONDecodeError, ValueError:
            pass  # cache failures are non-fatal; fall through to real run

    # --- cache miss or forced — actually run the validator ---
    try:
        passed = bool(instance.validate_all())
        detail_lines: list[str] = []
        for err in getattr(instance, "errors", []):
            detail_lines.append(f"ERROR: {err}")
        for warn in getattr(instance, "warnings", []):
            detail_lines.append(f"WARN: {warn}")
        for info in getattr(instance, "info", []):
            detail_lines.append(f"INFO: {info}")
        stderr = "\n".join(detail_lines)
    except SystemExit as e:
        passed = e.code in (0, None)
        stderr = f"Validator raised SystemExit({e.code!r})"
    except Exception as e:
        return ValidatorResult(
            description=description,
            passed=False,
            stdout="",
            stderr=f"Failed to run validator: {e}",
            duration=time.time() - start,
        )

    duration = time.time() - start

    # --- save to cache (only on success; failures always re-run) ---
    if passed and fhash is not None:
        with contextlib.suppress(OSError, TypeError, ValueError):
            save_cache(instance.config_dir, name, description, fhash, True, duration)

    return ValidatorResult(
        description=description,
        passed=passed,
        stdout="",
        stderr=stderr,
        duration=duration,
    )


def run_validators(
    config_dir: str, quiet: bool = False, force: bool = False, summary: bool = False
) -> list[ValidatorResult]:
    """Run all default-suite validators in parallel threads.

    The three validators each touch different files, so contention is minimal.
    ``ReferenceValidator`` itself spawns an inner ThreadPoolExecutor for its
    five-file entity extraction — total active threads peak around 8-15.
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(_run_one, cls, desc, config_dir, quiet, force, summary)
            for cls, desc in _VALIDATORS
        ]
        return [f.result() for f in futures]


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Wire the ``validate`` subparser."""
    parser = subparsers.add_parser(
        "validate",
        help="Run all configuration validators in-process.",
        description="Run YAML, reference, and HA-official validators in parallel.",
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-validator output on success. Errors still print.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run all validators ignoring cached results (cache is refreshed).",
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
    """Entry point for the ``validate`` subcommand. Returns exit code."""
    config_dir = args.config_dir
    quiet = bool(getattr(args, "quiet", False))
    force = bool(getattr(args, "force", False))

    summary = resolve_summary(args)

    if not quiet and not summary:
        print(
            "🔍 Running Home Assistant Configuration Validation Tests", file=sys.stderr
        )
        print("=" * 60, file=sys.stderr)
        print(file=sys.stderr)
        if force:
            print(
                "Re-running all validators (cache ignored, will be refreshed)...",
                file=sys.stderr,
            )
        else:
            print("Running all validators in parallel...", file=sys.stderr)
        print(file=sys.stderr)

    overall_start = time.time()
    results = run_validators(config_dir, quiet=quiet, force=force, summary=summary)
    overall_duration = time.time() - overall_start

    all_passed = True
    for r in results:
        if r.passed:
            if summary:
                if not quiet:
                    if r.cached:
                        print(f"PASS {r.description} C")
                    else:
                        print(f"PASS {r.description} ({r.duration:.2f}s)")
            else:
                suffix = " (cached)" if r.cached else f" ({r.duration:.2f}s)"
                if not quiet:
                    print(f"  ✅ {r.description}: PASSED{suffix}", file=sys.stderr)
        else:
            if summary:
                print(f"FAIL {r.description} ({r.duration:.2f}s)")
            else:
                print(
                    f"  ❌ {r.description}: FAILED ({r.duration:.2f}s)", file=sys.stderr
                )
            all_passed = False

    if not quiet and not summary:
        print(file=sys.stderr)
        print(
            f"Total execution time: {overall_duration:.2f}s (parallel)", file=sys.stderr
        )
        print("=" * 60, file=sys.stderr)

    # Print detailed output for failed validators.
    if not all_passed:
        for r in results:
            if r.passed:
                continue
            if summary:
                for line in r.stderr.strip().splitlines():
                    if line:
                        print(f"  {line}", file=sys.stderr)
            else:
                print(f"\n📋 {r.description}", file=sys.stderr)
                print("-" * 50, file=sys.stderr)
                print("Status: ❌ FAILED", file=sys.stderr)
                print(f"Duration: {r.duration:.2f}s", file=sys.stderr)
                if r.stdout.strip():
                    print("\nOutput:", file=sys.stderr)
                    for sline in r.stdout.strip().splitlines():
                        print(f"  {sline}", file=sys.stderr)
                if r.stderr.strip():
                    print("\nErrors:", file=sys.stderr)
                    for sline in r.stderr.strip().splitlines():
                        print(f"  {sline}", file=sys.stderr)
                print(file=sys.stderr)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    if summary:
        if all_passed:
            print(f"PASSED {passed}/{total} ({overall_duration:.2f}s)")
        else:
            print(f"FAILED {passed}/{total} ({overall_duration:.2f}s)")
    elif not quiet:
        print("\n📊 TEST SUMMARY", file=sys.stderr)
        print("=" * 30, file=sys.stderr)
        print(f"Total tests: {total}", file=sys.stderr)
        print(f"Passed: {passed}", file=sys.stderr)
        print(f"Failed: {failed}", file=sys.stderr)
        if failed == 0:
            print(
                "\n🎉 All tests passed! Your Home Assistant configuration is valid.",
                file=sys.stderr,
            )
        else:
            print(
                f"\n⚠️  {failed} test(s) failed. Please review the errors above.",
                file=sys.stderr,
            )
        print(file=sys.stderr)

    return 0 if all_passed else 1
