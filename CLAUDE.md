# Home Assistant Configuration Management

This repository manages Home Assistant configuration files with automated validation, testing, and deployment.

## User Preferences

- **Timezone:** AEST/AEDT (Australian Eastern Time). Always interpret user times as AEST/AEDT.
  - AEST = UTC+10, AEDT = UTC+11 (Oct-Apr). Example: "7:15am AEDT" = 20:15 UTC previous day

## Project Structure

- `config/automations.yaml` - **Primary file for automation work** (can be large — use Gemini CLI for full-file analysis)
- `config/scripts.yaml` - Reusable scripts
- `config/scripts/` - Shell helper scripts (e.g., `debug_log.sh`)
- `config/configuration.yaml` - Main HA config (integrations, includes, helpers)
- `config/blueprints/` - HA blueprints (automation/, script/, template/)
- `config/.storage/core.entity_registry` - **Entity registry** (large JSON — use Gemini CLI for full searches, targeted `grep` for known IDs)
- `frigate/config.yml` - Frigate NVR configuration (addon slug: `ccab4aaf_frigate-fa-beta`)
- `tools/` - Validation and testing scripts
- `Makefile` - Commands for pulling/pushing configuration
- `Makefile.dev` - Dev-only commands (see `README-DEV.md`)

## Environment Setup

Copy `.env.example` to `.env` and configure:
- `HA_TOKEN` - Long-lived access token (Profile → Security → Create Token)
- `HA_URL` - e.g., `http://homeassistant.local:8123`
- `HA_HOST` - SSH host for rsync (must match `~/.ssh/config`)

## Commands

| Command | Purpose |
|---------|---------|
| `make pull` | Sync config from HA (includes Z2M config) |
| `make push` | Push config (with validation) |
| `make backup` | Create timestamped backup (with auto-changelog) |
| `make validate` | Validate YAML syntax, entity refs, device IDs, HA config |
| `make setup` | Install Python dependencies via uv |
| `make status` | Show config status and entity counts |
| `make reload` | Reload HA config (API call, no push) |
| `make entities` | Explore available entities |
| `make entities ARGS='--search TERM'` | Search entities by name |
| `make backup-search PATTERN='text'` | Search all backups for a pattern |
| `make format-yaml` | Format YAML files (`FILES='...'` for specific files) |
| `make lint` | Run Python linting and format checks (ruff) |
| `make lint-fix` | Auto-fix Python lint and formatting issues |
| `make test-ssh` | Test SSH connection to HA |
| `make clean` | Remove temp files and caches |
| `tools/ha-curl.sh` | Curl wrapper with auto-auth (see below) |
| `tools/ha_api_diagnostic.py` | Comprehensive HA API endpoint testing |
| `tools/ha_config_validator.py` | Deep validation using HA's `check_config` |

### HA API Curl Wrapper
Use `tools/ha-curl.sh` for HA API calls - it auto-loads credentials from `.env`:
```bash
# GET request
tools/ha-curl.sh /api/states/sensor.test

# POST request
tools/ha-curl.sh -X POST /api/states/sensor.test -d '{"state": "on"}'

# With extra curl options
tools/ha-curl.sh -X POST /api/services/light/turn_on -d '{"entity_id": "light.kitchen"}'
```
Auto-approved via `Bash(tools/ha-curl.sh *)` in `~/.claude/settings.json`.

### Gemini CLI (Large File Analysis)

Use `gemini -p` with `@path` syntax when files exceed context limits or you need cross-file analysis.

**Shared Context:** Global and project-level `GEMINI.md` files are symlinked to `CLAUDE.md`. Project-specific memory at `~/.gemini/tmp/claude-homeassistant/memory/` is symlinked to Claude's memory at `~/.claude/projects/-home-stephen-code-claude-homeassistant/memory/`. Both tools share the same unified context and learning history.

```bash
# Analyze automations + scripts together
gemini -p "@config/automations.yaml @config/scripts.yaml Find all automations that reference the doorbell"

# Search the entity registry (too large to read directly)
gemini -p "@config/.storage/core.entity_registry Find all entities for device 'motion' in the basement"

# Cross-reference entities against config
gemini -p "@config/.storage/core.entity_registry @config/automations.yaml Find entity references that may be broken"

# Full config directory analysis
gemini -p "@config/ Summarize all helpers defined across configuration files"

# Compare backup contents
gemini -p "@/tmp/old_automations.yaml @config/automations.yaml What changed between these versions?"

# Whole project overview
gemini --all_files -p "Analyze the automation architecture and identify patterns"
```

**When to use over direct file reads:** Full `automations.yaml` analysis, entity registry searches (>100KB JSON), cross-referencing multiple large YAML files, comparing backup extracts, `.storage/` file analysis.

## Development Workflow

**Before feature work:** Use `home-assistant-backup` skill (pull → backup → prune)
**Creating automations:** Use `home-assistant-automation` skill
**Debugging issues:** Use `home-assistant-debugging` skill
**Python changes:** Follow TDD — write tests first, confirm red, then implement
**Before committing Python changes:** Run `make lint` (or `make lint-fix` to auto-fix)
**After any changes with concurrency, parallel API calls, multi-step error handling, or HA automation state transitions:** Run `code-review:code-review` skill as "State Machine Auditor" (ordering deps, race conditions, exception handler completeness)
**Before committing/finishing:** Use `reflect` skill to capture learnings (gotchas, corrections, new patterns)

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
- **Compare backup versions:** Extract to temp files, then use Gemini CLI: `gemini -p "@/tmp/old.yaml @/tmp/new.yaml What changed?"`
- **When reverting:** Don't blindly restore - ask about individual settings (e.g., timer durations) that may have been tuned independently of the change being reverted

## CI/CD

GitHub Actions runs on push/PR to main:

**`.github/workflows/test.yml`:**
- **lint**: `ruff format --check`, `ruff check`, and `mypy` (on `tools/` and `tests/`)
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

**`.storage/` files are read-only reference** — managed by HA at runtime. Never modify locally; use the HA UI for entity/device changes. Reading them for analysis is fine — use Gemini CLI for large files like `core.entity_registry`, or targeted `grep` for known IDs.

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
- **Login screen instead of dashboard:** Need `trusted_users` (not just `allow_bypass_login`) in `auth_providers` when multiple HA users exist. Find user IDs via Gemini CLI: `gemini -p "@config/.storage/auth List all user names and IDs"` (or `grep -A5 '"name":' config/.storage/auth`)
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
8. **Z2M entity_ids stuck as hex after recovery**: HA's `deleted_entities` preserves old entity_ids. Stop HA, clean Z2M entries from both `entities` and `deleted_entities` in `core.entity_registry` (and `devices`/`deleted_devices` in `core.device_registry`), then restart. See MEMORY.md for full Z2M recovery notes.
9. **"Incorrect config" / package install errors in `make validate` output**: Expected when `[tool.uv] override-dependencies` forces newer versions (e.g., `aiohttp>=3.13.4`) than HA's exact pins (`aiohttp==3.13.3`). HA's `check_config` tries to install integration packages via pip; pip fails because the overridden version conflicts with HA's metadata. These errors are filtered as false positives in `ha_official_validator.py` — "Successful config (partial)" with exit 0 is the correct result. `make pull`/`make validate` still exit 0 successfully.
