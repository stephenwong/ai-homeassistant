#!/usr/bin/env python3
"""``validate`` subcommand: in-process validator runner.

Runs YAML/reference/HA-official validators in parallel threads (no subprocess
spawn) and aggregates results. Replaces the old ValidationTestRunner.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import time
from dataclasses import dataclass
from typing import Any

from tools.cache import compute_hash, load_cache, save_cache
from tools.common import get_env_int
from tools.validators.ha_official import HAOfficialValidator
from tools.validators.references import ReferenceValidator
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
    (HAOfficialValidator, "Official Home Assistant Configuration Validation"),
]


def _run_one(
    cls: type,
    description: str,
    config_dir: str,
    quiet: bool,
    force: bool,
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
    instance = cls(config_dir, quiet=quiet)
    name = cls.__name__

    # Compute hash once — reuse for both cache check and cache save.
    fhash: str | None = None
    with contextlib.suppress(Exception):
        fhash = compute_hash(instance.config_dir, instance.file_deps())

    # --- cache check (skip when --force) ---
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
        except Exception:
            pass  # cache failures are non-fatal; fall through to real run

    # --- cache miss or forced — actually run the validator ---
    try:
        passed = bool(instance.validate_all())
        detail_lines: list[str] = []
        for err in getattr(instance, "errors", []):
            detail_lines.append(f"ERROR: {err}")
        for warn in getattr(instance, "warnings", []):
            detail_lines.append(f"WARN: {warn}")
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
        with contextlib.suppress(Exception):
            save_cache(instance.config_dir, name, description, fhash, True, duration)

    return ValidatorResult(
        description=description,
        passed=passed,
        stdout="",
        stderr=stderr,
        duration=duration,
    )


def run_validators(
    config_dir: str, quiet: bool = False, force: bool = False
) -> list[ValidatorResult]:
    """Run all default-suite validators in parallel threads.

    The three validators each touch different files, so contention is minimal.
    ``ReferenceValidator`` itself spawns an inner ThreadPoolExecutor for its
    five-file entity extraction — total active threads peak around 8-15.
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(_run_one, cls, desc, config_dir, quiet, force)
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
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``validate`` subcommand. Returns exit code."""
    config_dir = args.config_dir
    quiet = bool(getattr(args, "quiet", False))
    force = bool(getattr(args, "force", False))

    if not quiet:
        print("\U0001f50d Running Home Assistant Configuration Validation Tests")
        print("=" * 60)
        print()
        if force:
            print("Re-running all validators (cache ignored, will be refreshed)...")
        else:
            print("Running all validators in parallel...")
        print()

    overall_start = time.time()
    results = run_validators(config_dir, quiet=quiet, force=force)
    overall_duration = time.time() - overall_start

    all_passed = True
    for r in results:
        if r.passed:
            suffix = " (cached)" if r.cached else f" ({r.duration:.2f}s)"
            if not quiet:
                print(f"  \u2705 {r.description}: PASSED{suffix}")
        else:
            print(f"  \u274c {r.description}: FAILED ({r.duration:.2f}s)")
            all_passed = False

    if not quiet:
        print()
        print(f"Total execution time: {overall_duration:.2f}s (parallel)")
        print("=" * 60)

    # Print detailed output for failed validators (even in --quiet mode).
    if not all_passed:
        for r in results:
            if r.passed:
                continue
            print(f"\n\U0001f4cb {r.description}")
            print("-" * 50)
            print("Status: \u274c FAILED")
            print(f"Duration: {r.duration:.2f}s")
            if r.stdout.strip():
                print("\nOutput:")
                for line in r.stdout.strip().splitlines():
                    print(f"  {line}")
            if r.stderr.strip():
                print("\nErrors:")
                for line in r.stderr.strip().splitlines():
                    print(f"  {line}")
            print()

    if not quiet:
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        print("\n\U0001f4ca TEST SUMMARY")
        print("=" * 30)
        print(f"Total tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        if failed == 0:
            print(
                "\n\U0001f389 All tests passed! "
                "Your Home Assistant configuration is valid."
            )
        else:
            print(
                f"\n\u26a0\ufe0f  {failed} test(s) failed. "
                "Please review the errors above."
            )
        print()

    return 0 if all_passed else 1


# Backwards-compat: external callers (e.g. CI) sometimes read this constant.
DEFAULT_VALIDATOR_TIMEOUT = get_env_int("HA_RUNNER_TIMEOUT", 120)[0]
