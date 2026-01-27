# Home Assistant Configuration Management

This repository manages Home Assistant configuration files with automated validation, testing, and deployment.

## User Preferences

- **Timezone:** AEST/AEDT (Australian Eastern Time). Always interpret user times as AEST/AEDT.
  - AEST = UTC+10, AEDT = UTC+11 (Oct-Apr). Example: "7:15am AEDT" = 20:15 UTC previous day

## Project Structure

- `config/automations.yaml` - **Primary file for automation work**
- `config/scripts.yaml` - Reusable scripts
- `config/configuration.yaml` - Main HA config (integrations, includes, helpers)
- `config/.storage/core.entity_registry` - **Entity registry** (search for entity IDs, device IDs)
- `tools/` - Validation and testing scripts
- `Makefile` - Commands for pulling/pushing configuration

## Commands

| Command | Purpose |
|---------|---------|
| `make pull` | Sync config from HA instance |
| `make push` | Push config (with validation) |
| `make backup` | Create timestamped backup |
| `make validate` | Run all validation tests |
| `make entities` | Explore available entities |
| `python tools/entity_explorer.py --search TERM` | Search entities |

All python tools: `source venv/bin/activate && python <tool_path>`

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

### Rsync Safety
**NEVER use rsync `--delete` without `--filter='protect'` for excluded directories.**
```bash
rsync --delete --exclude-from=.rsync-excludes \
  --filter='protect .storage/' --filter='protect custom_components/'
```

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
    media_content_id: "http://192.168.1.10:1984/api/stream.mp4?src=front_door_rmtp"
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

## Integrations

- **Zigbee2MQTT**: `config/zigbee2mqtt/configuration.yaml`
- **Frigate**: Camera notifications via automations, config at `frigate/config.yml`
- **Recorder**: 7-day retention

## Troubleshooting

1. **Validation fails**: Check YAML syntax first, then entity references
2. **SSH issues**: `chmod 600 ~/.ssh/key`, test with `ssh homeassistant`
3. **Missing deps**: `source venv/bin/activate && pip install homeassistant voluptuous pyyaml`
