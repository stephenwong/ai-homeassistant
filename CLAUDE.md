# Home Assistant Configuration Management

This repository manages Home Assistant configuration files with automated validation, testing, and deployment.

## User Preferences

- **Timezone:** AEST/AEDT (Australian Eastern Time). Always interpret user times as AEST/AEDT.
  - AEST = UTC+10, AEDT = UTC+11 (Oct-Apr). Example: "7:15am AEDT" = 20:15 UTC previous day

## Project Structure

> **Note:** `AGENTS.md` and `GEMINI.md` are gitignored symlinks to `CLAUDE.md` so other AI tools read the same context.

### HA Configuration Files
- `config/automations.yaml` - **Primary file for automation work** (use `ha_cli edit automations` to list/show specific entries; use MCP tools for live analysis)
- `config/scripts.yaml` - Reusable scripts
- `config/scripts/` - Shell helper scripts (e.g., `debug_log.sh`)
- `config/configuration.yaml` - Main HA config (integrations, includes, helpers)
- `config/blueprints/` - HA blueprints (automation/, script/, template/)
- `config/.storage/core.entity_registry` - **Entity registry** (large JSON — use MCP tools for live queries, `ha_cli entities` for local searches, targeted `grep` for known IDs)
- `frigate/config.yml` - Frigate NVR configuration (addon slug: `ccab4aaf_frigate-fa-beta`)

### Tools Package (`tools/`)
- `tools/ha_cli.py` - **Single CLI entry point** (e.g. `uv run python tools/ha_cli.py validate`)
- `tools/commands/` - CLI subcommand implementations (`validate`, `reload`, `entities`, `curl`, `edit`)
- `tools/ha/client.py` - `HAClient` — shared HA REST API client (importable: `from tools.ha.client import HAClient`)
- `tools/ha/yaml_editor.py` - `YAMLEditor` — round-trip YAML editing with comment preservation (importable: `from tools.ha.yaml_editor import YAMLEditor`)
- `tools/validators/` - Validator implementations (`yaml.py`, `references.py`, `ha_official.py`)
- `tools/cache.py` - SHA256 file-hash caching for validator results
- `tools/common.py` - Shared utilities (env loading, path helpers)
- `tools/{run_tests,yaml_validator,reference_validator,ha_official_validator,reload_config,entity_explorer}.py` - **Backward-compat shims** that delegate to the new package. Old scripts/Makefile targets still work; prefer `ha_cli` for new work.
- `tools/_dev/api_diagnostic.py` - Dev-only API diagnostic (archived; excluded from lint/wheel)
- `Makefile` - Commands for pulling/pushing configuration
- `Makefile.dev` - Dev-only commands (see `README-DEV.md`)

## Environment Setup

Copy `.env.example` to `.env` and configure:
- `HA_TOKEN` - Long-lived access token (Profile → Security → Create Token)
- `HA_URL` - e.g., `http://homeassistant.local:8123`
- `HA_HOST` - SSH host for rsync (must match `~/.ssh/config`)
- `HA_MCP_URL` - ha-mcp MCP server URL from add-on logs

## Commands

| Command | Purpose |
|---------|---------|
| `make pull` | Sync config from HA (includes Z2M config) |
| `make push` | Push config (with validation) |
| `make backup` | Create timestamped backup (with auto-changelog) |
| `make validate` | Validate YAML syntax, entity refs, device IDs, HA config |
| `make setup` | Install Python dependencies via uv |
| `make status` | Show config status and entity examples |
| `make reload` | Reload HA config (API call, no push) |
| `make entities` | Explore available entities |
| `make entities ARGS='--search TERM'` | Search entities by name |
| `make backup-search PATTERN='text'` | Search all backups for a pattern |
| `make changelog BACKUP='path'` | Generate changelog for a backup |
| `make lint` | Run Python linting and format checks (ruff) |
| `make lint-fix` | Auto-fix Python lint and formatting issues |
| `make test-ssh` | Test SSH connection to HA |
| `make clean` | Remove temp files and caches |
| `tools/ha-curl.sh` | Curl wrapper with auto-auth (see below) |
| `tools/ha_cli.py` | Single CLI entry: `uv run python tools/ha_cli.py {validate\|reload\|entities\|curl\|edit}` |
| `tools/_dev/api_diagnostic.py` | Dev-only comprehensive HA API endpoint testing (archived from main flow) |

### HA API Access — Three Tiers

| Need | Tool | Example |
|------|------|---------|
| **Live HA interaction** (read entities, call services) | **MCP tools** (ha-mcp) | Ask in natural language (see MCP Server section below) |
| **Scripted API calls** | `ha_cli curl` or `tools/ha-curl.sh` | `uv run python tools/ha_cli.py curl /api/states/sensor.test` |
| **Importable client** | `HAClient` | `from tools.ha.client import HAClient` |

#### ha_cli curl (wraps ha-curl.sh)
```bash
# GET with jq filter
uv run python tools/ha_cli.py curl /api/states --filter '. | length'

# POST
uv run python tools/ha_cli.py curl /api/services/light/turn_on --post --data '{"entity_id": "light.kitchen"}'
```

#### ha-curl.sh (direct, auto-loads .env credentials)
```bash
tools/ha-curl.sh /api/states/sensor.test
tools/ha-curl.sh -X POST /api/services/light/turn_on -d '{"entity_id": "light.kitchen"}'
```
Auto-approved via `Bash(tools/ha-curl.sh *)` in `~/.claude/settings.json`.

### Validator Caching

Validators cache results in `config/.cache/validators/<ClassName>.json` keyed by SHA256 of all files each validator depends on (`file_deps()` glob patterns). Cached results are reused on subsequent runs when file contents haven't changed.

- **Automatic:** Caching is transparent — unchanged files return cached results instantly.
- **Force refresh:** `uv run python tools/ha_cli.py validate --force` re-runs all validators and refreshes cache.
- **Only successful results cached:** Validation failures always re-run.
- **Cleared by:** Deleting `config/.cache/validators/` (or `git clean -fdX config/.cache/` since `.cache/` is gitignored).

### Safe YAML Editing (ha_cli edit)

**Prefer `ha_cli edit` over manual YAML editing** — it uses `ruamel.yaml` for round-trip editing that preserves comments, formatting, and key ordering. Operates on `automations.yaml` (list) and `scripts.yaml` (dict).

```bash
# List all automation aliases
uv run python tools/ha_cli.py edit automations

# Show a specific automation
uv run python tools/ha_cli.py edit automations "Turn on Alarm"

# Add a new automation from JSON
uv run python tools/ha_cli.py edit automations --add '{"alias": "New Automation", "trigger": [], "action": []}'

# Update fields on an existing automation
uv run python tools/ha_cli.py edit automations "Turn on Alarm" --set mode=single icon=mdi:shield

# Remove an automation
uv run python tools/ha_cli.py edit automations "Old Automation" --remove
```

**Programmatic editing:** `from tools.ha.yaml_editor import YAMLEditor` — use `add_automation`, `update_automation`, `remove_automation`, `add_script`, `update_script`, `remove_script`.

### Importable Modules

For Python scripts/tests, import from the package directly:

```python
from tools.ha.client import HAClient        # REST API client
from tools.ha.yaml_editor import YAMLEditor  # Round-trip YAML editing
from tools.validators.yaml import YAMLValidator
from tools.validators.references import ReferenceValidator
from tools.validators.ha_official import HAOfficialValidator
```

`HAClient` is constructed via `HAClient.from_env()` (reads `.env` for `HA_TOKEN`/`HA_URL`).

### MCP Server (ha-mcp)

The `ha-mcp` add-on provides 88+ MCP tools for natural-language HA control (entity listing, service calls, history, config inspection). Configured in `opencode.json` as a remote MCP server. Includes the `home-assistant-best-practices` skill (triggers on automation/script/dashboard work).

**Setup:** Install the "Home Assistant MCP Server" add-on (repo: `https://github.com/homeassistant-ai/ha-mcp`), start it, copy the MCP URL from add-on logs (format: `http://<ip>:9583/private_<token>`), add to `opencode.json` under `mcp.ha-mcp` with `type: "remote"` and `"url": "{env:HA_MCP_URL}"`, set `HA_MCP_URL` in `.env`, and restart opencode.

**Troubleshooting:** Verify add-on is running (`ha addon info` via SSH); check HA host IP and port 9583 accessibility; ensure `opencode.json` has `$schema` field and restart after changes.

## Development Workflow

**Before feature work:** Use `home-assistant-backup` skill (pull → backup → prune)
**Creating automations:** Use `home-assistant-automation` skill
**Debugging issues:** Use `home-assistant-debugging` skill
**Python changes:** **Always use TDD** — write tests first, confirm red, then implement. No exceptions. This reduces AI slop by forcing concrete specifications before implementation.
**Editing YAML:** Prefer `ha_cli edit` over manual editing — it uses `ruamel.yaml` for round-trip editing that preserves comments and formatting. Use MCP tools for live entity/service queries instead of manual curl.
**Before committing Python changes:** Run `make lint` (or `make lint-fix` to auto-fix)
**After any changes with concurrency, parallel API calls, multi-step error handling, or HA automation state transitions:** Run `code-review:code-review` skill as "State Machine Auditor" (ordering deps, race conditions, exception handler completeness)
**Rubber duck review:** Before considering work done, run a review pass in a separate agent at least once. After each review, ask the user if they want to review again. Keep asking — do not assume one pass is enough.
**Before committing/finishing:** Use `reflect` skill to capture learnings (gotchas, corrections, new patterns)

### Python Tooling Patterns
- **`contextlib.redirect_stdout` is NOT thread-safe.** It mutates `sys.stdout` globally. Three concurrent threads each entering `redirect_stdout(buf)` will deadlock silently. When running validators in parallel threads, read `instance.errors`/`warnings`/`info` lists directly instead of capturing stdout.
- **Backward-compat shim pattern for `patch()` targets:** `from X import *` re-exports module-level names so `patch("old_module.subprocess.run")` still resolves — `subprocess` is a singleton module object shared between shim and original. **But** this breaks silently if anyone adds `__all__` to the new module. Always pair shims with a `test_shim_compatibility.py` regression test that imports each old path and asserts the expected attributes resolve.
- **`load_env_file()` in tests:** `HAClient.from_env()` calls it, which reads the project's real `.env` and overrides monkeypatched values. In `HAClient` tests, patch `tools.ha.client.load_env_file` to a no-op fixture so env-var assertions hold.
- **Subclass `__init__` kwarg forwarding:** When adding a new kwarg (like `quiet`) to a base class, every subclass that overrides `__init__` must explicitly accept and forward the kwarg via `super().__init__(config_dir, quiet=quiet)`. Otherwise `TypeError: __init__() got an unexpected keyword argument 'quiet'`. Check all subclasses when changing base class signatures.
- **`pyproject.toml` exclude sections:** Adding a `tools/_dev/` directory requires updating FOUR exclude locations: `[tool.ruff] exclude`, `[tool.mypy] exclude`, `[tool.coverage.run] omit` (path pattern: `"*/tools/_dev/*"`), and `[tool.hatch.build] exclude`. Pre-commit's mypy hook has its OWN regex exclude (`.pre-commit-config.yaml`) separate from pyproject's `[tool.mypy] exclude`.
- **Python 3.14 unparenthesized `except A, B, C:` is canonical, NOT a bug.** Python 3.14 relaxed the grammar to accept comma-separated exception types without parens (compiles identically to `except (A, B, C):`). `ruff format` targeting `py314` actively *removes* the parens as "unnecessary." Do NOT flag `except OSError, ValueError:` as a syntax error in review — it's the formatter-enforced style. Only applies on 3.14+; on older Python it's a `SyntaxError`.

### Git Commit Trailers

**Every commit message you create must end with these trailer lines** (separated from the body by a blank line):

```
Model used: <current-model-name>
Co-authored-by: <current-tool> <noreply email>
```

- **Model name:** use your actual current model as shown in your system prompt (e.g. `glm-5.2`, `claude-sonnet-4-5`). This keeps attribution correct as models change.
- **Tool + email:** attribute to whichever tool you're actually running in (identify it from your system prompt / identity, not from this file's name):
  - Claude Code → `Claude <noreply@anthropic.com>`
  - opencode → `opencode <noreply@opencode.ai>`
  - Antigravity → `Antigravity <noreply@antigravity.google>`
  - Other → `<tool-name> <noreply@<tool-domain>>`

Only append for commits you create; do not add to commits authored by other tools or manual `git commit` runs.

## Backups as Version History

Config changes are often **not in git history** - they get pushed to HA and pulled back without commits. The `backups/` directory is the real historical record. See `home-assistant-backup` skill for full workflow.

- **Extract a specific file:** `tar -xzOf backups/ha_config_<timestamp>.tar.gz config/automations.yaml`
- **Compare backup versions:** Extract to temp files (`tar -xzOf backups/ha_config_<ts>.tar.gz config/automations.yaml > /tmp/old.yaml`), then diff or read both
- **When reverting:** Don't blindly restore - ask about individual settings (e.g., timer durations) that may have been tuned independently of the change being reverted

## CI/CD

GitHub Actions runs on push/PR to main:

**`.github/workflows/test.yml`:**
- **lint**: `ruff format --check` and `ruff check` (on `tools/`+`tests/`), `mypy` (on `tools/`)
- **test**: `pytest tests/`

**`.github/workflows/codeql.yml`:** CodeQL Python analysis (weekly + on push/PR)

Run `make lint` locally before pushing to catch CI failures early. Use `make lint-fix` to auto-fix.

## Hardware

**Host:** Dell OptiPlex 7010 Micro Plus (i5-13600, 32GB DDR5, Hailo-8 26 TOPS, Intel QuickSync)
**Zigbee:** SMLIGHT SLZB-06Mg24 (Ethernet-attached, PoE)

Implications: Frigate can use aggressive detection (Hailo), streams use hardware transcoding (QuickSync).

## Integrations

- **Zigbee2MQTT**: `config/zigbee2mqtt/configuration.yaml` + `coordinator_backup.json` (addon slug: `45df7312_zigbee2mqtt`) — pulled locally via `make pull`, excluded from push except `configuration.yaml`
- **Frigate**: Camera notifications via automations, config at `frigate/config.yml`
- **Recorder**: 7-day retention

## Entity Naming Convention

Format: `location_room_device_sensor`
- **location**: `home`, `office`, `cabin`
- **room**: `basement`, `kitchen`, `driveway`
- **device**: `motion`, `heatpump`, `lock`
- **sensor**: `battery`, `temperature`, `status`

Examples: `binary_sensor.home_basement_motion_battery`, `climate.office_living_room_thermostat`

## Streaming Frigate to Cast/Nest

**NEVER use `camera.play_stream`** — returns 500 errors with Frigate. Requires go2rtc port 1984 exposed in Frigate addon.

- **Start:** `media_player.play_media` with `media_content_id: "http://<go2rtc>:1984/api/stream.mp4?src=<stream>"` and `media_content_type: "video/mp4"`
- **Stop:** `media_player.turn_off` (not `media_stop`, which doesn't return to ambient)
- **Do NOT check `media_content_id` to detect if a Cast stream is active** — HA's Google Cast integration never reliably populates this attribute after `play_media`. The media player often reports `off` with empty `content_id` even while physically showing the stream. For timer-based cleanup, call `turn_off` unconditionally (the start automation's idle/off guard prevents interrupting legitimate user media).

## Frigate Sensor Naming & False Positive Tuning

### Sensor Naming Convention

| Pattern | Example | Meaning |
|---------|---------|---------|
| `sensor.<camera>_<zone>_<object>_count` | `sensor.driveway_driveway_car_count` | Objects in **specific zone** |
| `sensor.<camera>_<object>_count` | `sensor.driveway_car_count` | Objects **anywhere on camera** |

Alert automations typically use **zoned** sensors. An object detected on camera but outside the zone won't trigger zoned sensors.

### Zone Tuning (False Positives)

| Parameter | Default | Effect |
|-----------|---------|--------|
| `inertia` | 1 | Frames object must be in zone before counting |
| `loitering_time` | 0 | Seconds object must remain before triggering |

Increase both for false alerts (passing cars, jitter). After changes: `make push` then restart Frigate addon.

## Critical Gotchas

### Zigbee Command Timing
When sending multiple commands to the same Zigbee device in an automation sequence, add **250ms delays** between each command. Without delays, later commands may not take effect before an action (e.g., alarm activation) fires. This applies to any mix of `select.select_option`, `switch.turn_on/off`, `number.set_value`, etc. targeting the same device.

### Rsync Architecture
This project uses **separate exclude files** for pull vs push:

| File | Used By | Purpose |
|------|---------|---------|
| `.rsync-excludes-pull` | `make pull` | Less restrictive - allows pulling `.storage/` for local reference |
| `.rsync-excludes-push` | `make push` | More restrictive - protects HA runtime state |

**What this repo can manage (YAML files):** `automations.yaml`, `scripts.yaml`, `scenes.yaml`, `configuration.yaml`, `secrets.yaml`

**`.storage/` files are read-only reference** — managed by HA at runtime. Never modify locally; use the HA UI for entity/device changes. Reading them for analysis is fine — use MCP tools for live queries, or targeted `grep` for known IDs.

### HA Jinja2 Filter Availability
HA uses a **curated subset of Jinja2 filters** — standard Jinja2 filters like `hash` are NOT available. Common available filters: `lower`, `upper`, `replace`, `truncate`, `length`, `int`, `float`, `round`, `default`, `select`, `map`, `join`, `sort`.

When you need a content-change fingerprint for `value_template` (e.g., in `command_line` sensors), use `| length` rather than a hash — it changes whenever the content grows.

### Template Whitespace
**NEVER use multi-line templates for URLs/entity IDs** - they add whitespace:
```yaml
# BAD - adds whitespace
stream_name: >
  {% if x %}a{% else %}b{% endif %}

# GOOD - single line
stream_name: "{% if x %}a{% else %}b{% endif %}"
```

### Frigate required_zones
**ALWAYS use list format:**
```yaml
# BAD - silently fails
required_zones: driveway_zone

# GOOD
required_zones:
  - driveway_zone
```

### Helper Entity Reload
New helpers in `configuration.yaml` require "Reload all YAML configuration" (Developer Tools > YAML), not just `make push`.

### Shell Commands
HA's `shell_command` doesn't run through a shell by default - it executes directly via subprocess. To use shell features (`>>`, `&&`, `$()`), either:
- Wrap with `/bin/sh -c "..."`
- Use a helper script file (preferred for complex commands)

**BusyBox limitations:** HA uses BusyBox, so `date +%N` (nanoseconds) doesn't work. Use `date +%H:%M:%S` only.

### Helper Scripts Location
Shell scripts in `config/scripts/` must exist in the local repo, not just on the server. Rsync push will **delete** server files that don't exist locally.

### Lovelace Storage Changes
`.storage/lovelace` is excluded from rsync push. To edit Lovelace views:
1. SSH to HA and edit `/config/.storage/lovelace.lovelace` directly (note: actual filename is `lovelace.lovelace`, not `lovelace`)
2. Restart HA (required for storage changes)

**The HA Lovelace REST API (`GET/POST /api/lovelace/config`) returns 404 in storage mode** — don't attempt it. SSH + direct file edit is the only approach.

### DashCast Gotchas
- **Login screen instead of dashboard:** Need `trusted_users` (not just `allow_bypass_login`) in `auth_providers` when multiple HA users exist. Find user IDs via MCP tools or `ha_cli curl /api/users` (or `grep -A5 '"name":' config/.storage/auth`)
- **Stopping DashCast on Nest Hub:** Use `homeassistant.turn_off`, NOT `media_player.turn_off` (which doesn't reliably close DashCast)

### HACS / Lovelace Cards
- **"Configuration error":** Verify card is actually *installed* (not just known to HACS) — check `installed: True` in `.storage/hacs.repositories`. Test with minimal config first, check browser console (F12).
- **advanced-camera-card + go2rtc:** Keep config minimal. No trailing slash on go2rtc URL. Don't add `modes:` array — use defaults.

## Troubleshooting

1. **Validation fails**: Check YAML syntax first, then entity references
2. **SSH issues**: `chmod 600 ~/.ssh/key`, test with `make test-ssh`
3. **Missing deps**: `uv sync`
4. **Run tests**: `uv run pytest tests/`
5. **View HA logs**: `ssh homeassistant "ha core logs" | tail -100` (or `--follow` for real-time)
6. **False Frigate alerts**: Check zoned vs unzoned sensors, increase `inertia`/`loitering_time` in zone config
7. **Restart Frigate addon**: Use SSH: `ssh homeassistant "ha apps restart ccab4aaf_frigate-fa-beta"`. The Supervisor API returns 401 with long-lived access tokens — use SSH instead.
8. **Z2M entity_ids stuck as hex after recovery**: HA's `deleted_entities` preserves old entity_ids. Stop HA, clean Z2M entries from both `entities` and `deleted_entities` in `core.entity_registry` (and `devices`/`deleted_devices` in `core.device_registry`), then restart.
9. **"Incorrect config" / package install errors in `make validate` output**: Expected when `[tool.uv] override-dependencies` forces newer versions than HA's exact pins. HA's `check_config` tries to install integration packages via pip; pip fails because the overridden version conflicts with HA's metadata. These errors are filtered as false positives in `ha_official_validator.py` — "Successful config (partial)" with exit 0 is the correct result. `make pull`/`make validate` still exit 0 successfully.
