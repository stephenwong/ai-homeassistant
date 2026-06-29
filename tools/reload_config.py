#!/usr/bin/env python3
"""Home Assistant Configuration Reload Tool.

Calls the Home Assistant API to reload configuration after config files
have been pushed to the instance. Uses git to detect which files changed
and calls only the relevant reload services.
"""

import functools
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tools.common import HARequestError, get_env_int
from tools.ha.client import HAClient

FILE_TO_SERVICE = {
    "automations.yaml": "automation/reload",
    "scripts.yaml": "script/reload",
    "scenes.yaml": "scene/reload",
    "configuration.yaml": "homeassistant/reload_core_config",
}
ALL_SERVICES = frozenset(FILE_TO_SERVICE.values())
SERVICE_LABELS = {
    "automation/reload": "automations",
    "script/reload": "scripts",
    "scene/reload": "scenes",
    "homeassistant/reload_core_config": "core config",
}


def detect_changed_services(
    config_dir="config", git_timeout: int = 10
) -> set[str] | None:
    """Detect which HA reload services are needed based on git-changed files.

    Returns a set of service strings (e.g. {"automation/reload"}),
    an empty set if nothing changed, or None if git is unavailable/fails.
    """
    repo_root = Path(__file__).parent.parent
    changed_files: set[str] = set()

    try:
        r = subprocess.run(
            ["git", "diff", "HEAD", "--name-only", "-z", "--", config_dir],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=git_timeout,
        )
        if r.returncode != 0:
            return None
        for p_str in r.stdout.split("\0"):
            p_str = p_str.strip()
            if p_str:
                p = Path(p_str)
                if len(p.parts) == 2 and p.parts[0] == config_dir:
                    changed_files.add(p.name)
    except FileNotFoundError, OSError, subprocess.TimeoutExpired:
        return None

    # Also check git status for untracked files not shown by git diff HEAD
    # Using -z (NUL-delimited) for robust path handling (spaces, special chars)
    try:
        r2 = subprocess.run(
            ["git", "status", "-z", "--", config_dir],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=git_timeout,
        )
        if r2.returncode == 0:
            tokens = r2.stdout.split("\0")
            i = 0
            while i < len(tokens):
                token = tokens[i].strip()
                if not token:
                    i += 1
                    continue
                # Status entries have format "XY path" (min 4 chars: XY + space + path)
                if len(token) > 3 and token[2] == " ":
                    status = token[:2]
                    path = token[3:].strip()
                    p = Path(path)
                    if len(p.parts) == 2 and p.parts[0] == config_dir:
                        changed_files.add(p.name)
                    # Renames/copies: format "R  NEW\0OLD\0" — skip the next (old) token
                    if status[0] in ("R", "C"):
                        i += 2
                        continue
                i += 1
    except FileNotFoundError, OSError, subprocess.TimeoutExpired:
        pass

    services: set[str] = set()
    for fname in changed_files:
        if fname.endswith((".yaml", ".yml")):
            services.add(FILE_TO_SERVICE.get(fname, "homeassistant/reload_core_config"))
    return services


def reload_service(client: HAClient, service: str) -> tuple[str, bool, str | None]:
    """Call a single HA reload service. Returns (service, success, error_detail).

    Uses the shared HAClient so auth/timeout/JSON handling is consistent
    with the rest of the codebase. Network errors are caught so one failing
    service doesn't abort the batch.
    """
    domain, _, action = service.partition("/")
    try:
        ok = client.call_service(domain, action)
    except HARequestError as e:
        ok = False
        return (service, ok, str(e))
    return (service, ok, None)


def reload_config(summary: bool = False) -> bool:
    """Reload Home Assistant configuration via API."""
    start = time.time()
    git_timeout, git_timeout_warning = get_env_int("HA_GIT_TIMEOUT", 10)
    reload_timeout, reload_timeout_warning = get_env_int("HA_RELOAD_TIMEOUT", 30)

    if not summary:
        for warning in [git_timeout_warning, reload_timeout_warning]:
            if warning:
                print(f"\u26a0\ufe0f  {warning}")

    try:
        client = HAClient.from_env()
    except HARequestError as e:
        print(f"\u274c Error: {e}")
        if "HA_TOKEN" in str(e):
            print("   Create a .env file with: HA_TOKEN=your_long_lived_access_token")
            print("   Get your token from Home Assistant Profile page")
        return False

    # Override client timeout with the reload-specific value (typically longer
    # than the default request timeout because reloads block on disk I/O).
    client.timeout = reload_timeout

    services = detect_changed_services(git_timeout=git_timeout)
    if not services:
        if not summary:
            print(
                "\u26a0\ufe0f  No config changes detected, "
                "reloading all domains to be safe"
            )
        services = set(ALL_SERVICES)

    if not summary:
        labels = sorted(SERVICE_LABELS.get(s, s) for s in services)
        print(f"\U0001f504 Reloading: {', '.join(labels)}")

    # reload_core_config must run before domain reloads — automations/scripts
    # reference helpers and integrations that core config sets up.
    core_service = "homeassistant/reload_core_config"
    domain_services = services - {core_service}
    results = []

    if core_service in services:
        results.append(reload_service(client, core_service))

    if domain_services:
        with ThreadPoolExecutor() as executor:
            results.extend(
                executor.map(
                    functools.partial(reload_service, client),
                    domain_services,
                )
            )

    all_ok = True
    for service, ok, error in results:
        label = SERVICE_LABELS.get(service, service)
        if ok:
            if not summary:
                print(f"  \u2705 {label} reloaded")
        else:
            suffix = f" ({error[:80]})" if error else ""
            if not summary:
                print(f"  \u274c {label} failed to reload{suffix}")
            all_ok = False

    elapsed = time.time() - start

    if summary:
        total = len(results)
        passed = sum(1 for _, ok, _ in results if ok)
        if all_ok:
            labels = ", ".join(sorted(SERVICE_LABELS.get(s, s) for s, _, _ in results))
            print(f"RELOADED {passed}/{total} ({labels}) {elapsed:.1f}s")
        else:
            failed_labels = ", ".join(
                sorted(SERVICE_LABELS.get(s, s) for s, ok, _ in results if not ok)
            )
            print(f"FAILED {passed}/{total} ({failed_labels} FAILED) {elapsed:.1f}s")
    else:
        if all_ok:
            print("\u2705 All reloads completed successfully!")
        else:
            print("\u274c Some reloads failed")

    return all_ok


if __name__ == "__main__":
    SUCCESS = reload_config()
    sys.exit(0 if SUCCESS else 1)
