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

from tools.common import HARequestError, MissingTokenError, get_env_int
from tools.ha.client import HAClient

_REPO_ROOT = Path(__file__).parent.parent
CORE_RELOAD_SERVICE = "homeassistant/reload_core_config"

FILE_TO_SERVICE = {
    "automations.yaml": "automation/reload",
    "scripts.yaml": "script/reload",
    "scenes.yaml": "scene/reload",
    "configuration.yaml": CORE_RELOAD_SERVICE,
}
ALL_SERVICES = frozenset(FILE_TO_SERVICE.values())
SERVICE_LABELS = {
    "automation/reload": "automations",
    "script/reload": "scripts",
    "scene/reload": "scenes",
    CORE_RELOAD_SERVICE: "core config",
}


def _top_level_config_basename(path: str, config_dir: str) -> str | None:
    """Return a direct child basename of *config_dir*, otherwise ``None``."""
    try:
        relative = Path(path).relative_to(Path(config_dir))
    except ValueError:
        return None
    if len(relative.parts) != 1:
        return None
    return relative.name


def _run_git_diff(config_dir: str, git_timeout: int) -> set[str] | None:
    """Run ``git diff HEAD --name-only -z`` and return changed basenames.

    Returns ``None`` if git is unavailable or fails.
    """
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD", "--name-only", "-z", "--", config_dir],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=git_timeout,
        )
        if r.returncode != 0:
            return None
        changed: set[str] = set()
        for p_str in r.stdout.split("\0"):
            p_str = p_str.strip()
            if p_str:
                basename = _top_level_config_basename(p_str, config_dir)
                if basename is not None:
                    changed.add(basename)
        return changed
    except OSError, subprocess.TimeoutExpired:
        return None


def _run_git_status_untracked(config_dir: str, git_timeout: int) -> set[str]:
    """Run ``git status -z`` and return untracked/renamed basenames.

    Best-effort (errors silently return empty set).
    """
    changed: set[str] = set()
    try:
        r = subprocess.run(
            ["git", "status", "-z", "--", config_dir],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=git_timeout,
        )
        if r.returncode == 0:
            tokens = r.stdout.split("\0")
            i = 0
            while i < len(tokens):
                token = tokens[i].strip()
                if not token:
                    i += 1
                    continue
                if len(token) > 3 and token[2] == " ":
                    status = token[:2]
                    path = token[3:].strip()
                    basename = _top_level_config_basename(path, config_dir)
                    if basename is not None:
                        changed.add(basename)
                    if status[0] in ("R", "C"):
                        i += 2
                        continue
                i += 1
    except OSError, subprocess.TimeoutExpired:
        pass
    return changed


def _classify_changed_files(filenames: set[str]) -> set[str]:
    """Map changed YAML file basenames to HA reload services."""
    services: set[str] = set()
    for fname in filenames:
        if fname.endswith((".yaml", ".yml")):
            services.add(FILE_TO_SERVICE.get(fname, CORE_RELOAD_SERVICE))
    return services


def detect_changed_services(
    config_dir="config", git_timeout: int = 10
) -> set[str] | None:
    """Detect which HA reload services are needed based on git-changed files.

    Returns a set of service strings (e.g. {"automation/reload"}),
    an empty set if nothing changed, or None if git is unavailable/fails.
    """
    diff_files = _run_git_diff(config_dir, git_timeout)
    if diff_files is None:
        return None
    untracked_files = _run_git_status_untracked(config_dir, git_timeout)
    return _classify_changed_files(diff_files | untracked_files)


def reload_service(client: HAClient, service: str) -> tuple[str, bool, str | None]:
    """Call a single HA reload service. Returns (service, success, error_detail).

    Uses ``client.post`` directly (rather than ``call_service``) so the HTTP
    response body is available for error reporting on non-2xx replies.
    Network errors are caught so one failing service doesn't abort the batch.
    """
    domain, _, action = service.partition("/")
    path = f"/api/services/{domain}/{action}"
    try:
        response = client.post(path, json={})
        if 200 <= response.status_code < 300:
            return (service, True, None)
        detail = response.text[:200] if response.text else ""
        return (service, False, f"HTTP {response.status_code}: {detail}")
    except HARequestError as e:
        return (service, False, str(e))
    except Exception as e:  # isolation: never abort the batch
        return (service, False, f"{type(e).__name__}: {e}")


def reload_config(summary: bool = False) -> bool:
    """Reload Home Assistant configuration via API."""
    start = time.time()
    git_timeout, git_timeout_warning = get_env_int("HA_GIT_TIMEOUT", 10)
    reload_timeout, reload_timeout_warning = get_env_int("HA_RELOAD_TIMEOUT", 30)

    if not summary:
        for warning in [git_timeout_warning, reload_timeout_warning]:
            if warning:
                print(f"⚠️  {warning}", file=sys.stderr)

    try:
        client = HAClient.from_env()
    except MissingTokenError as e:
        print(f"\u274c Error: {e}", file=sys.stderr)
        print(
            "   Create a .env file with: HA_TOKEN=your_long_lived_access_token",
            file=sys.stderr,
        )
        print("   Get your token from Home Assistant Profile page", file=sys.stderr)
        return False
    except HARequestError as e:
        print(f"\u274c Error: {e}", file=sys.stderr)
        return False

    # Override client timeout with the reload-specific value (typically longer
    # than the default request timeout because reloads block on disk I/O).
    client.timeout = reload_timeout

    services = detect_changed_services(git_timeout=git_timeout)
    if not services:
        if not summary:
            print(
                "⚠️  No config changes detected, reloading all domains to be safe",
                file=sys.stderr,
            )
        services = set(ALL_SERVICES)

    if not summary:
        labels = sorted(SERVICE_LABELS.get(s, s) for s in services)
        print(f"🔄 Reloading: {', '.join(labels)}", file=sys.stderr)

    # reload_core_config must run before domain reloads — automations/scripts
    # reference helpers and integrations that core config sets up.
    core_service = CORE_RELOAD_SERVICE
    domain_services = services - {core_service}
    results = []

    if core_service in services:
        core_result = reload_service(client, core_service)
        results.append(core_result)

    # M15: if core config failed, skip domain reloads — they depend on helpers
    # and integrations that core sets up, so they'd just cascade the failure.
    core_ok = all(ok for _svc, ok, _err in results)

    if domain_services and core_ok:
        # NOTE: requests.Session is shared across workers — safe per urllib3's
        # thread-safe connection pool, but not guaranteed by requests' docs.
        # If a future requests version breaks this, switch to per-worker sessions.
        with ThreadPoolExecutor() as executor:
            results.extend(
                executor.map(
                    functools.partial(reload_service, client),
                    sorted(domain_services),
                )
            )
    elif domain_services and not core_ok and not summary:
        print(
            "⚠️  Skipping domain reloads because core config failed "
            "(fix configuration.yaml first)",
            file=sys.stderr,
        )

    all_ok = True
    for service, ok, error in results:
        label = SERVICE_LABELS.get(service, service)
        if ok:
            if not summary:
                print(f"  ✅ {label} reloaded", file=sys.stderr)
        else:
            suffix = f" ({error[:80]})" if error else ""
            if not summary:
                print(f"  ❌ {label} failed to reload{suffix}", file=sys.stderr)
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
            print("✅ All reloads completed successfully!", file=sys.stderr)
        else:
            print("❌ Some reloads failed", file=sys.stderr)

    return all_ok


if __name__ == "__main__":
    SUCCESS = reload_config()
    sys.exit(0 if SUCCESS else 1)
