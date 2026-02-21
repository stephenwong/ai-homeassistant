#!/usr/bin/env python3
"""Home Assistant Configuration Reload Tool.

Calls the Home Assistant API to reload configuration after config files
have been pushed to the instance. Uses git to detect which files changed
and calls only the relevant reload services.
"""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from tools.common import load_env_file

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


def detect_changed_services(config_dir="config") -> set[str] | None:
    """Detect which HA reload services are needed based on git-changed files.

    Returns a set of service strings (e.g. {"automation/reload"}),
    an empty set if nothing changed, or None if git is unavailable/fails.
    """
    repo_root = Path(__file__).parent.parent
    changed_files: set[str] = set()

    try:
        r = subprocess.run(
            ["git", "diff", "HEAD", "--name-only", "--", config_dir],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return None
        for line in r.stdout.splitlines():
            if line.strip():
                p = Path(line.strip())
                if len(p.parts) == 2 and p.parts[0] == config_dir:
                    changed_files.add(p.name)
    except (FileNotFoundError, OSError):
        return None

    # Also check git status for untracked files not shown by git diff HEAD
    try:
        r2 = subprocess.run(
            ["git", "status", "--short", "--", config_dir],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r2.returncode == 0:
            for line in r2.stdout.splitlines():
                if len(line) > 3:
                    p = Path(line[3:].strip())
                    if len(p.parts) == 2 and p.parts[0] == config_dir:
                        changed_files.add(p.name)
    except (FileNotFoundError, OSError):
        pass

    services: set[str] = set()
    for fname in changed_files:
        if fname.endswith((".yaml", ".yml")):
            services.add(FILE_TO_SERVICE.get(fname, "homeassistant/reload_core_config"))
    return services


def reload_service(service: str, ha_url: str, headers: dict) -> tuple[str, bool]:
    """Call a single HA reload service. Returns (service, success)."""
    url = f"{ha_url}/api/services/{service}"
    try:
        response = requests.post(url, headers=headers, timeout=30)
        return (service, response.status_code == 200)
    except Exception:
        return (service, False)


def reload_config() -> bool:
    """Reload Home Assistant configuration via API."""
    load_env_file()

    ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123")
    token = os.getenv("HA_TOKEN", "")

    if not token:
        print("❌ Error: HA_TOKEN not found in environment or .env file")
        print("   Create a .env file with: HA_TOKEN=your_long_lived_access_token")
        print("   Get your token from Home Assistant Profile page")
        return False

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    services = detect_changed_services()
    if not services:
        print("⚠️  No config changes detected, reloading all domains to be safe")
        services = ALL_SERVICES

    labels = sorted(SERVICE_LABELS.get(s, s) for s in services)
    print(f"🔄 Reloading: {', '.join(labels)}")

    with ThreadPoolExecutor() as executor:
        results = list(
            executor.map(lambda s: reload_service(s, ha_url, headers), services)
        )

    all_ok = True
    for service, ok in results:
        label = SERVICE_LABELS.get(service, service)
        if ok:
            print(f"  ✅ {label} reloaded")
        else:
            print(f"  ❌ {label} failed to reload")
            all_ok = False

    if all_ok:
        print("✅ All reloads completed successfully!")
    else:
        print("❌ Some reloads failed")

    return all_ok


if __name__ == "__main__":
    SUCCESS = reload_config()
    sys.exit(0 if SUCCESS else 1)
