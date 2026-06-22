#!/usr/bin/env python3
"""``validate`` subcommand: in-process validator runner.

Runs YAML/reference/HA-official validators in parallel threads (no subprocess
spawn) and aggregates results. Replaces the old ValidationTestRunner.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import time
from dataclasses import dataclass
from typing import Any

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


# (module_class, description) tuples for each validator in the default suite.
_VALIDATORS: list[tuple[type[Any], str]] = [
    (YAMLValidator, "YAML Syntax Validation"),
    (ReferenceValidator, "Entity/Device Reference Validation"),
    (HAOfficialValidator, "Official Home Assistant Configuration Validation"),
]


def _run_one(
    cls: type, description: str, config_dir: str, quiet: bool
) -> ValidatorResult:
    """Instantiate and run a single validator.

    Validator ``main()``s raise SystemExit; we catch it here so that the
    parallel executor doesn't kill sibling validators. ``validate_all()``
    itself does not raise SystemExit — only ``main()`` does — so this is
    defensive for validators that have been refactored to a callable form.

    Note: We do NOT use ``contextlib.redirect_stdout`` because it modifies
    ``sys.stdout`` globally and is not thread-safe — three concurrent
    redirects would deadlock. Validators don't print during ``validate_all()``
    anyway; all printing happens in ``print_results()`` which we don't call.
    Instead, we read ``instance.errors``/``warnings``/``info`` directly to
    surface failure detail.
    """
    start = time.time()
    try:
        instance = cls(config_dir, quiet=quiet)
        passed = bool(instance.validate_all())
        # Surface validator's error/warning lists as the "stderr" channel
        # so the failure-detail printer can show them.
        detail_lines: list[str] = []
        for err in getattr(instance, "errors", []):
            detail_lines.append(f"ERROR: {err}")
        for warn in getattr(instance, "warnings", []):
            detail_lines.append(f"WARN: {warn}")
        stderr = "\n".join(detail_lines)
    except SystemExit as e:
        # code 0 → success, anything else → failure; None → treat as success
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
    return ValidatorResult(
        description=description,
        passed=passed,
        stdout="",
        stderr=stderr,
        duration=time.time() - start,
    )


def run_validators(config_dir: str, quiet: bool = False) -> list[ValidatorResult]:
    """Run all default-suite validators in parallel threads.

    The three validators each touch different files, so contention is minimal.
    ``ReferenceValidator`` itself spawns an inner ThreadPoolExecutor for its
    five-file entity extraction — total active threads peak around 8-15.
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(_run_one, cls, desc, config_dir, quiet)
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
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Entry point for the ``validate`` subcommand. Returns exit code."""
    config_dir = args.config_dir
    quiet = bool(getattr(args, "quiet", False))

    if not quiet:
        print("\U0001f50d Running Home Assistant Configuration Validation Tests")
        print("=" * 60)
        print()
        print("Running all validators in parallel...")
        print()

    overall_start = time.time()
    results = run_validators(config_dir, quiet=quiet)
    overall_duration = time.time() - overall_start

    all_passed = True
    for r in results:
        if r.passed:
            if not quiet:
                print(f"  \u2705 {r.description}: PASSED ({r.duration:.2f}s)")
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
