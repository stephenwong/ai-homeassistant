# Home Assistant Configuration Management

This repository manages Home Assistant configuration files with automated validation, testing, and deployment.

## User Preferences

- **Git:** NEVER run `git push` in this repository. The user handles pushing manually.
- **Timezone:** AEST/AEDT (Australian Eastern Time). Always interpret user times as AEST/AEDT.
  - AEST = UTC+10, AEDT = UTC+11 (Oct-Apr). Example: "7:15am AEDT" = 20:15 UTC previous day

## Project Structure

- `config/automations.yaml` - **Primary file for automation work**
- `config/scripts.yaml` - Reusable scripts
- `config/scripts/` - Shell helper scripts (e.g., `debug_log.sh`)
- `config/configuration.yaml` - Main HA config (integrations, includes, helpers)
- `config/.storage/core.entity_registry` - **Entity registry** (search for entity IDs, device IDs)
- `tools/` - Validation and testing scripts
- `Makefile` - Commands for pulling/pushing configuration

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
| `make backup` | Create timestamped backup |
| `make validate` | Run all validation tests |
| `make setup` | Install Python dependencies via uv |
| `make status` | Show config status and entity counts |
| `make reload` | Reload HA config (API call, no push) |
| `make entities` | Explore available entities |
| `make entities ARGS='--search TERM'` | Search entities by name |
| `make test-ssh` | Test SSH connection to HA |
| `make clean` | Remove temp files and caches |

## Hardware

**Host:** Dell OptiPlex 7010 Micro Plus (i5-13600, 32GB DDR5, Hailo-8 26 TOPS, Intel QuickSync)
**Zigbee:** SMLIGHT SLZB-06Mg24 (Ethernet-attached, PoE)

Implications: Frigate can use aggressive detection (Hailo), streams use hardware transcoding (QuickSync).

## Development Workflow

**Before feature work:** Use `home-assistant-backup` skill (pull → backup → prune)
**Creating automations:** Use `home-assistant-automation` skill
**Debugging issues:** Use `home-assistant-debugging` skill
**After mistakes:** Use `learning-from-mistakes` skill

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
`.storage/lovelace` is excluded from rsync push. To add Lovelace views:
1. SSH to HA and edit `/config/.storage/lovelace` directly
2. Restart HA (required for storage changes)

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
    media_content_id: "http://192.168.50.10:1984/api/stream.mp4?src=front_door_rmtp"
    media_content_type: "video/mp4"

# Stop stream (use turn_off, not media_stop)
- action: media_player.turn_off
  target:
    entity_id: media_player.nest_hub
```

## Automation Quick Reference

### Structure
```yaml
- id: unique_id
  alias: Human-readable name
  triggers:
    - trigger: state|time|device|event|numeric_state|sun|zone
  conditions: []
  actions:
    - action: domain.service
      target:
        entity_id: entity.name
  mode: single|queued|restart|parallel
```

### Modes
| Mode | Behavior |
|------|----------|
| `single` | Ignores new triggers while running (default) |
| `queued` | Queues triggers, runs sequentially |
| `restart` | Cancels current run, starts fresh |
| `parallel` | Runs multiple instances simultaneously |

### Common Templates
```yaml
states('entity_id')              # Get state
state_attr('entity_id', 'attr')  # Get attribute
is_state('entity_id', 'value')   # Boolean check
| float(0)                       # Convert with default
| default(omit)                  # Omit if undefined (for optional script params)
```

### Device Triggers (buttons/switches)
```yaml
triggers:
  - trigger: device
    domain: mqtt
    device_id: <id>  # Find via: python tools/entity_explorer.py --search "name"
    type: action
    subtype: single|double|long_press
```

### Debug Logging
Use `script.debug_log` to add timestamped entries to the Debug tab in Lovelace:
```yaml
- action: script.debug_log
  data:
    message: "Camera started streaming"
    severity: info  # info (default), warn, error
    entity: camera.front_door  # optional context
```
Output: `ℹ️ 14:32:05 [camera.front_door] Camera started streaming` (emojis: ℹ️/⚠️/❌)

## Integrations

- **Zigbee2MQTT**: `config/zigbee2mqtt/configuration.yaml`
- **Frigate**: Camera notifications via automations, config at `frigate/config.yml`
- **Recorder**: 7-day retention

## Troubleshooting

1. **Validation fails**: Check YAML syntax first, then entity references
2. **SSH issues**: `chmod 600 ~/.ssh/key`, test with `make test-ssh`
3. **Missing deps**: `uv sync`
4. **Run tests**: `uv run pytest tests/`
