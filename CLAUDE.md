# Home Assistant Configuration Management

This repository manages Home Assistant configuration files with automated validation, testing, and deployment.

## User Preferences

- **Timezone:** AEST/AEDT (Australian Eastern Time). Always interpret user times as AEST/AEDT.
  - AEST = UTC+10, AEDT = UTC+11 (Oct-Apr). Example: "7:15am AEDT" = 20:15 UTC previous day

## Project Structure

- `config/automations.yaml` - **Primary file for automation work**
- `config/scripts.yaml` - Reusable scripts
- `config/scripts/` - Shell helper scripts (e.g., `debug_log.sh`)
- `config/configuration.yaml` - Main HA config (integrations, includes, helpers)
- `config/blueprints/` - HA blueprints (automation/, script/, template/)
- `config/.storage/core.entity_registry` - **Entity registry** (search for entity IDs, device IDs)
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
| `make pull` | Sync config from HA instance |
| `make push` | Push config (with validation) |
| `make backup` | Create timestamped backup (with auto-changelog) |
| `make validate` | Run all validation tests |
| `make setup` | Install Python dependencies via uv |
| `make status` | Show config status and entity counts |
| `make reload` | Reload HA config (API call, no push) |
| `make entities` | Explore available entities |
| `make entities ARGS='--search TERM'` | Search entities by name |
| `make backup-search PATTERN='text'` | Search all backups for a pattern |
| `make changelog BACKUP='path'` | Generate changelog for a specific backup |
| `make changelog-all` | Backfill changelogs for all backups |
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
This wrapper auto-approves in Claude Code (compound commands with `&&` require manual approval).

## Hardware

**Host:** Dell OptiPlex 7010 Micro Plus (i5-13600, 32GB DDR5, Hailo-8 26 TOPS, Intel QuickSync)
**Zigbee:** SMLIGHT SLZB-06Mg24 (Ethernet-attached, PoE)

Implications: Frigate can use aggressive detection (Hailo), streams use hardware transcoding (QuickSync).

## Development Workflow

**Before feature work:** Use `home-assistant-backup` skill (pull → backup → prune)
**Creating automations:** Use `home-assistant-automation` skill
**Debugging issues:** Use `home-assistant-debugging` skill
**Before committing Python changes:** Run `make lint` (or `make lint-fix` to auto-fix)
**Before committing/finishing:** Use `reflect` skill to capture learnings (gotchas, corrections, new patterns)

## Backups as Version History

Config changes are often **not in git history** - they get pushed to HA and pulled back without commits. The `backups/` directory is the real historical record.

- **Backup format:** `ha_config_YYYYMMDD_HHMMSS.tar.gz` with matching `.changelog`
- **Find when a change was introduced:** `make backup-search PATTERN='media_player.play_media'`
- **See what changed in a backup:** `cat backups/ha_config_YYYYMMDD_HHMMSS.changelog`
- **Extract a specific file:** `tar -xzOf backups/ha_config_<timestamp>.tar.gz config/automations.yaml`
- **Backfill changelogs:** `make changelog-all` (generates missing `.changelog` files)
- **When reverting:** Don't blindly restore - ask about individual settings (e.g., timer durations) that may have been tuned independently of the change being reverted

## Critical Gotchas

### Rsync Architecture
This project uses **separate exclude files** for pull vs push:

| File | Used By | Purpose |
|------|---------|---------|
| `.rsync-excludes-pull` | `make pull` | Less restrictive - allows pulling `.storage/` for local reference |
| `.rsync-excludes-push` | `make push` | More restrictive - protects HA runtime state |

**What this repo can manage (YAML files):** `automations.yaml`, `scripts.yaml`, `scenes.yaml`, `configuration.yaml`, `secrets.yaml`

**Never modify locally (runtime state):** `.storage/` files are managed by HA at runtime. Use the HA UI for entity/device changes.

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

### Script Parameter Names
**Parameter names must match exactly between automation and script.** With `| default(omit)` patterns, mismatches silently fail:
```yaml
# automation calls with:
data:
  forced_mode: day   # WRONG - typo

# script expects:
fields:
  force_mode:        # RIGHT - no 'd'
```
**Debug tip:** If automation triggers and script runs but doesn't produce expected result, compare parameter names immediately.

### Shell Commands
HA's `shell_command` doesn't run through a shell by default - it executes directly via subprocess. To use shell features (`>>`, `&&`, `$()`), either:
- Wrap with `/bin/sh -c "..."`
- Use a helper script file (preferred for complex commands)

**BusyBox limitations:** HA uses BusyBox, so `date +%N` (nanoseconds) doesn't work. Use `date +%H:%M:%S` only.

### Helper Scripts Location
Shell scripts in `config/scripts/` must exist in the local repo, not just on the server. Rsync push will **delete** server files that don't exist locally.

### Lovelace Storage Changes
`.storage/lovelace` is excluded from rsync push. To edit Lovelace views:
1. SSH to HA and edit `/config/.storage/lovelace` directly
2. Restart HA (required for storage changes)

### DashCast Login Screen Issue
If DashCast shows HA login screen instead of dashboard, you need `trusted_users` (not just `allow_bypass_login`) when multiple HA users exist:
```yaml
auth_providers:
  - type: homeassistant
  - type: trusted_networks
    trusted_networks:
      - 192.168.1.0/24
    trusted_users:
      192.168.1.0/24:
        - USER_ID_HERE  # Find in .storage/auth
    allow_bypass_login: true
```
**Find user IDs:** `grep -A5 '"name":' config/.storage/auth | grep -E '"id"|"name"'`

### Stopping DashCast on Nest Hub
`media_player.turn_off` does NOT reliably close DashCast on Google Nest Hubs. Use `homeassistant.turn_off` instead:
```yaml
# BAD - doesn't close DashCast
- action: media_player.turn_off
  target:
    entity_id: media_player.nest_hub

# GOOD - reliably closes DashCast
- action: homeassistant.turn_off
  target:
    entity_id: media_player.nest_hub
```

### HACS Custom Card "Configuration error"
When a Lovelace card shows "Configuration error":
1. **Verify card is installed** (not just known to HACS):
   ```bash
   ssh homeassistant 'python3 -c "import json; d=json.load(open(\"/config/.storage/hacs.repositories\")); print([(v[\"full_name\"],v.get(\"installed\",False)) for v in d[\"data\"].values() if \"card-name\" in v.get(\"full_name\",\"\").lower()])"'
   ```
2. **Test with minimal config first**, then add options back incrementally
3. **Check browser console** (F12) for specific error messages

### advanced-camera-card + go2rtc
Keep config simple - avoid unnecessary options:
```yaml
# GOOD - minimal working config
type: custom:advanced-camera-card
cameras:
  - camera_entity: camera.front_door
    live_provider: go2rtc
    go2rtc:
      stream: front_door_rmtp
      url: http://192.168.1.100:1984  # No trailing slash

# BAD - over-complicated, can cause errors
go2rtc:
  modes: [webrtc, mse, mp4]  # Skip this
  stream: front_door_rmtp
  url: http://192.168.1.100:1984/  # No trailing slash
```

## Entity Naming Convention

Format: `location_room_device_sensor`
- **location**: `home`, `office`, `cabin`
- **room**: `basement`, `kitchen`, `driveway`
- **device**: `motion`, `heatpump`, `lock`
- **sensor**: `battery`, `temperature`, `status`

Examples: `binary_sensor.home_basement_motion_battery`, `climate.office_living_room_thermostat`

## Streaming Frigate to Cast/Nest

**NEVER use `camera.play_stream`** - returns 500 errors with Frigate.

Prerequisites: Expose go2rtc port 1984 in Frigate addon settings.

```yaml
# Start stream
- action: media_player.play_media
  target:
    entity_id: media_player.nest_hub
  data:
    media_content_id: "http://192.168.1.100:1984/api/stream.mp4?src=front_door_rmtp"
    media_content_type: "video/mp4"

# Stop stream (use turn_off, not media_stop)
- action: media_player.turn_off
  target:
    entity_id: media_player.nest_hub
```

## Frigate Sensor Naming & False Positive Tuning

### Sensor Naming Convention
Frigate creates two types of count/occupancy sensors:

| Pattern | Example | Meaning |
|---------|---------|---------|
| `sensor.<camera>_<zone>_<object>_count` | `sensor.driveway_driveway_car_count` | Objects in **specific zone** |
| `sensor.<camera>_<object>_count` | `sensor.driveway_car_count` | Objects **anywhere on camera** |

**Important:** Alert automations typically use **zoned** sensors (e.g., `sensor.anyone_outside` sums zoned counts). An object detected on camera but outside the zone won't trigger zoned sensors.

### Zone Tuning Parameters
When getting false alerts from brief detections (cars passing, detection jitter):

| Parameter | Default | Effect |
|-----------|---------|--------|
| `inertia` | 1 | Frames object must be in zone before counting (higher = more filtering) |
| `loitering_time` | 0 | Seconds object must remain in zone before triggering (higher = more filtering) |

```yaml
# frigate/config.yml - Example zone with filtering
zones:
  driveway_driveway:
    coordinates: ...
    inertia: 3           # Must be detected for 3 frames
    loitering_time: 3    # Must stay for 3 seconds
```

### When to Adjust
- **Brief false alerts (passing cars):** Increase `inertia` and `loitering_time`
- **Alerts at zone edges:** Adjust zone coordinates to exclude problem areas
- **Missing real detections:** Decrease values or expand zone

After changes: `make push` then restart Frigate addon.

## Automation Quick Reference

For full automation reference (structure, modes, triggers, patterns), see the `home-assistant-automation` skill.

### Key Templates
```yaml
states('entity_id')              # Get state
is_state('entity_id', 'value')   # Boolean check
| float(0)                       # Convert with default
| default(omit)                  # Omit if undefined (for optional script params)
```

### Debug Logging
```yaml
- action: script.debug_log
  data:
    message: "Camera started streaming"
    severity: info  # info (default), warn, error
    entity: camera.front_door  # optional context
```

## CI/CD

GitHub Actions (`.github/workflows/test.yml`) runs on push/PR:
- **rsync-excludes-tests**: Validates rsync exclude file consistency
- **lint**: Runs `ruff format --check` and `ruff check`

Run `make lint` locally before pushing to catch CI failures early. Use `make lint-fix` to auto-fix issues.

## Integrations

- **Zigbee2MQTT**: `config/zigbee2mqtt/configuration.yaml`
- **Frigate**: Camera notifications via automations, config at `frigate/config.yml`
- **Recorder**: 7-day retention

## Troubleshooting

1. **Validation fails**: Check YAML syntax first, then entity references
2. **SSH issues**: `chmod 600 ~/.ssh/key`, test with `make test-ssh`
3. **Missing deps**: `uv sync`
4. **Run tests**: `uv run pytest tests/`
5. **DashCast shows login**: Add `trusted_users` mapping (see gotcha above)
6. **Lovelace "Configuration error"**: Verify HACS card is installed, test minimal config
7. **Camera card not loading**: Check `installed: True` in `.storage/hacs.repositories`
8. **False Frigate alerts**: Check zoned vs unzoned sensors, increase `inertia`/`loitering_time` in zone config
