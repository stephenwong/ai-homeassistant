# Home Assistant Configuration Management

This repository manages Home Assistant configuration files with automated validation, testing, and deployment.

## Project Structure

- `config/automations.yaml` - **Primary file for automation work** (read this first for any automation tasks)
- `config/scripts.yaml` - Reusable scripts (called from automations or dashboard buttons)
- `config/configuration.yaml` - Main HA config (integrations, includes, helpers)
- `config/.storage/core.entity_registry` - **Entity registry** (search here to find entity IDs, device IDs, and entity metadata)
- `config/.storage/lovelace` - Dashboard configuration (JSON format)
- `config/` - Contains all Home Assistant configuration files (synced from HA instance)
- `tools/` - Validation and testing scripts
- `venv/` - Python virtual environment with dependencies
- `temp/` - Temporary directory for Claude to write and test code before moving to final locations
- `Makefile` - Commands for pulling/pushing configuration
- `.claude-code/` - Project-specific Claude Code settings and hooks
  - `hooks/` - Validation hooks that run automatically
  - `settings.json` - Project configuration

## Available Commands

### Configuration Management
- `make pull` - Pull latest config from Home Assistant instance
- `make push` - Push local config to Home Assistant (with validation)
- `make backup` - Create timestamped backup of current config
- `python tools/prune_backups.py` - Prune old backups per retention rules
- `make validate` - Run all validation tests

### Validation Tools
- `python tools/run_tests.py` - Run complete validation suite
- `python tools/yaml_validator.py` - YAML syntax validation only
- `python tools/reference_validator.py` - Entity/device reference validation
- `python tools/ha_official_validator.py` - Official HA configuration validation

### Entity Discovery Tools
- `make entities` - Explore available Home Assistant entities
- `python tools/entity_explorer.py` - Entity registry parser and explorer
  - `--search TERM` - Search entities by name, ID, or device class
  - `--domain DOMAIN` - Show entities from specific domain (e.g., climate, sensor)
  - `--area AREA` - Show entities from specific area
  - `--full` - Show complete detailed output

## Validation System

This project includes comprehensive validation to prevent invalid configurations:

1. **YAML Syntax Validation** - Ensures proper YAML syntax with HA-specific tags
2. **Entity Reference Validation** - Checks that all referenced entities/devices exist
3. **Official HA Validation** - Uses Home Assistant's own validation tools

### Automated Validation Hooks

- **Post-Edit Hook**: Runs validation after editing any YAML files in `config/`
- **Pre-Push Hook**: Validates configuration before pushing to Home Assistant
- **Blocks invalid pushes**: Prevents uploading broken configurations

## Home Assistant Instance Details

- **Host**: Configure in Makefile `HA_HOST` variable
- **User**: Configure SSH access as needed
- **SSH Key**: Configure SSH key authentication
- **Config Path**: /config/ (standard HA path)
- **Version**: Compatible with Home Assistant Core 2024.x+

## Entity Registry

The system tracks entities across these domains:
- alarm_control_panel, binary_sensor, button, camera, climate
- device_tracker, event, image, light, lock, media_player
- number, person, scene, select, sensor, siren, switch
- time, tts, update, vacuum, water_heater, weather, zone

## Development Workflow

**IMPORTANT: Before starting any new feature work:**

Use the `home-assistant-backup` skill (automated 3-step process):
1. **Pull Latest**: `make pull` to sync latest config from Home Assistant
2. **Create Backup**: `make backup` to create a timestamped backup
3. **Prune Backups**: `python tools/prune_backups.py` to apply retention rules

**Then proceed with development:**
4. **Edit Locally**: Modify files in `config/` directory
5. **Auto-Validation**: Hooks automatically validate on edits
6. **Test Changes**: `make validate` for full test suite
7. **Deploy**: `make push` to upload (blocked if validation fails)

**Backup Retention:**
- Backups stored in `backups/` directory (gitignored)
- Format: `ha_config_YYYYMMDD_HHMMSS.tar.gz`
- Automatic pruning: Keep all (0-7 days), one/day (7-30 days), one/week (30+ days)

## Learning from Mistakes

When a mistake is identified (by you or the user), use the `learning-from-mistakes` skill to:

1. **Reflect**: Identify the root cause and failed assumption
2. **Abstract**: Generalize the specific error into a pattern
3. **Document**: Update the relevant skill or CLAUDE.md to prevent recurrence

**When to invoke:**
- After catching an error in work
- When user points out a mistake
- After failed deployment or validation
- When a better approach becomes apparent

**Documentation targets:**
- Workflow-specific learnings → Add to relevant skill's "Common Mistakes" or "Red Flags"
- Project-wide practices → Add to CLAUDE.md
- New processes needed → Consider creating a new skill

### Writing Effective Guidelines

When adding new rules to this document, follow these principles:

**Core Principles (Always Apply):**
1. Use absolute directives - Start with "NEVER" or "ALWAYS"
2. Lead with why - Explain the problem before the solution (1-3 bullets max)
3. Be concrete - Include actual commands/code
4. Minimize examples - One clear point per code block
5. Bullets over paragraphs - Keep explanations concise

**Optional Enhancements (Use Strategically):**
- ❌/✅ examples: Only when the antipattern is subtle
- "Warning Signs" section: Only for gradual mistakes
- "General Principle": Only when abstraction is non-obvious

**Anti-Bloat Rules:**
- ❌ Don't add "Warning Signs" to obvious rules
- ❌ Don't show bad examples for trivial mistakes
- ❌ Don't write paragraphs explaining what bullets can convey

## Key Features

- ✅ **Safe Deployments**: Pre-push validation prevents broken configs
- ✅ **Entity Validation**: Ensures all references point to real entities
- ✅ **Entity Discovery**: Advanced tools to explore and search available entities
- ✅ **Official HA Tools**: Uses Home Assistant's own validation
- ✅ **YAML Support**: Handles HA-specific tags (!include, !secret, !input)
- ✅ **Comprehensive Testing**: Multiple validation layers
- ✅ **Automated Hooks**: Validation runs automatically on file changes

## Important Notes

- **Never push without validation**: The hooks prevent this, but be aware
- **Blueprint files** use `!input` tags which are normal and expected
- **Secrets are skipped** during validation for security
- **SSH access required** for pull/push operations
- **Python venv required** for validation tools

### Rsync Safety

**NEVER use rsync `--delete` without `--filter='protect'` for excluded directories.**

- Directories excluded from `pull` don't exist locally
- `--delete` on `push` removes anything not local → deletes excluded dirs on server
- `.storage/` deletion breaks HACS, auth, entity registry
- Always pair excludes with protect filters:
```bash
rsync --delete --exclude-from=.rsync-excludes \
  --filter='protect .storage/' \
  --filter='protect custom_components/' \
  ...
```

## Troubleshooting

### Validation Fails
1. Check YAML syntax errors first
2. Verify entity references exist in `.storage/` files
3. Run individual validators to isolate issues
4. Check HA logs if official validation fails

### SSH Issues
1. Verify SSH key permissions: `chmod 600 ~/.ssh/your_key`
2. Test connection: `ssh your_homeassistant_host`
3. Check SSH config in `~/.ssh/config`

### Missing Dependencies
1. Activate venv: `source venv/bin/activate`
2. Install requirements: `pip install homeassistant voluptuous pyyaml`

## Security

- **SSH keys** are used for secure access
- **Secrets.yaml** is excluded from validation (contains sensitive data)
- **No credentials** are stored in this repository
- **Access tokens** in config are for authorized integrations

This system ensures you can confidently manage Home Assistant configurations with Claude while maintaining safety and reliability.

## Entity Naming Convention

This Home Assistant setup uses a **standardized entity naming convention** for multi-location deployments:

### **Format: `location_room_device_sensor`**

**Structure:**
- **location**: `home`, `office`, `cabin`, etc.
- **room**: `basement`, `kitchen`, `living_room`, `main_bedroom`, `guest_bedroom`, `driveway`, etc.
- **device**: `motion`, `heatpump`, `sonos`, `lock`, `vacuum`, `water_heater`, `alarm`, etc.
- **sensor**: `battery`, `tamper`, `status`, `temperature`, `humidity`, `door`, `running`, etc.

### **Examples:**
```
binary_sensor.home_basement_motion_battery
binary_sensor.home_basement_motion_tamper
media_player.home_kitchen_sonos
media_player.office_main_bedroom_sonos
climate.home_living_room_heatpump
climate.office_living_room_thermostat
lock.home_front_door_august
sensor.office_driveway_camera_battery
vacuum.home_roborock
vacuum.office_roborock
```

### **Benefits:**
- **Clear location identification** - no ambiguity between properties
- **Consistent structure** - easy to predict entity names
- **Automation-friendly** - simple to target location-specific devices
- **Scalable** - supports additional locations or rooms

### **Implementation:**
- All location-based entities follow this convention
- Legacy entities have been systematically renamed
- New entities should follow this pattern
- Vendor prefixes (aquanta_, august_, etc.) are replaced with descriptive device names

### **Claude Code Integration:**
- **REQUIRED:** Use the `home-assistant-backup` skill when starting any feature work (pull + backup + prune retention)
- **REQUIRED:** Use the `home-assistant-automation` skill when creating or modifying automations (discovery → clarify → design → implement → deploy)
- **Check `config/.storage/core.entity_registry`** to find entity IDs, device IDs, and verify entities exist
- **Check `config/configuration.yaml`** for integration setup, includes, and customizations
- When creating automations, always ask the user for input if there are multiple choices for sensors or devices
- Use the entity explorer tools to discover available entities before writing automations
- Follow the naming convention when suggesting entity names in automations

## Automation Structure

### Basic Structure
```yaml
- id: unique_id
  alias: Human-readable name
  description: What it does
  triggers:
    - trigger: state|time|device|event|numeric_state|sun|zone
  conditions: []
  actions:
    - action: domain.service
      target:
        entity_id: entity.name
      data: {}
  mode: single|queued|restart|parallel
```

### Trigger Types
- `state` - Entity state changes
- `numeric_state` - Above/below thresholds
- `time` - Specific time or time pattern
- `device` - Device-specific events (buttons, sensors)
- `event` - HA events
- `sun` - Sunrise/sunset
- `zone` - Enter/leave zones

### Automation Modes

| Mode | Behavior |
|------|----------|
| `single` | Ignores new triggers while running (default) |
| `queued` | Queues triggers, runs sequentially |
| `restart` | Cancels current run, starts fresh |
| `parallel` | Runs multiple instances simultaneously |

## Template Syntax (Jinja2)

### Common Functions
- `states('entity_id')` - Get state value
- `state_attr('entity_id', 'attribute')` - Get attribute
- `is_state('entity_id', 'value')` - Boolean check
- `now()` - Current datetime
- `today_at('HH:MM')` - Time today
- `this.state` - Current entity state (in template sensors)

### Filters
- `| float(default)` - Convert to float
- `| int(default)` - Convert to integer
- `| default(value)` - Fallback value
- `| timestamp_custom('%H:%M')` - Format timestamp

### Example
```yaml
state: >
  {% set humidity = states('sensor.bathroom_humidity') | float(0) %}
  {% if humidity > 70 %}on{% else %}off{% endif %}
```

### Template Whitespace Warning

**NEVER use multi-line templates for values that need exact formatting (URLs, entity IDs, etc.).**

Multi-line Jinja templates add whitespace that breaks URLs and identifiers:
```yaml
# BAD - adds whitespace around the value
stream_name: >
  {% if condition %}front_door{% else %}driveway{% endif %}
# Results in: "  front_door  " (with newlines/spaces)

# GOOD - single line, no extra whitespace
stream_name: "{% if condition %}front_door{% else %}driveway{% endif %}"
```

Use multi-line templates only for display text where whitespace doesn't matter.

## Helper Entities

| Type | Purpose | Example Use |
|------|---------|-------------|
| `input_boolean` | Toggle switches | `input_boolean.alarm_toggle` |
| `input_datetime` | Store date/time | Track when garage opened |
| `input_select` | Dropdown options | Scene selection |
| `input_number` | Numeric values | Threshold settings |
| `timer` | Countdown timers | Motion-activated lights |
| `counter` | Increment/decrement | Count events |

**Important**: New helper entities defined in `configuration.yaml` require "Reload all YAML configuration" in HA (Developer Tools > YAML > All YAML Configuration) to appear in the entity registry. A simple `make push` reload is not sufficient.

## Scripts

Scripts are defined in `config/scripts.yaml`. They can accept parameters and be called from automations or dashboard buttons.

```yaml
# Example script with parameters
disable_alarm_timed:
  alias: Disable Alarm for Duration
  fields:
    duration:
      description: How long to disable (HH:MM:SS format)
      example: "01:00:00"
  sequence:
    - action: input_boolean.turn_off
      target:
        entity_id: input_boolean.alarm_toggle
    - action: timer.start
      target:
        entity_id: timer.alarm_on_timer
      data:
        duration: "{{ duration }}"
  mode: single
```

### Calling Scripts from Dashboard Buttons

```json
{
  "type": "button",
  "name": "1 hour",
  "icon": "mdi:timer",
  "tap_action": {
    "action": "perform-action",
    "perform_action": "script.disable_alarm_timed",
    "data": {
      "duration": "01:00:00"
    }
  }
}
```

## Common Service Calls

```yaml
# Notifications
- action: notify.mobile_devices
  data:
    title: "Alert"
    message: "Something happened"

# Lights
- action: light.turn_on
  target:
    entity_id: light.living_room
  data:
    brightness_pct: 80
    color_temp_kelvin: 3000

# Switches
- action: switch.turn_on
  target:
    entity_id: switch.device_name

# Timers
- action: timer.start
  target:
    entity_id: timer.bathroom_timer
  data:
    duration: "00:10:00"

# Scenes
- action: scene.turn_on
  target:
    entity_id: scene.movie_night

# Scripts
- action: script.turn_on
  target:
    entity_id: script.morning_routine
```

## Device Triggers

Used for physical buttons, switches with firmware events:
```yaml
triggers:
  - trigger: device
    domain: mqtt
    device_id: <device_id>
    type: action
    subtype: single|double|long_press
```

Note: Device IDs can be found using `python tools/entity_explorer.py --search "device name"`

## Conditional Actions (Choose)

```yaml
actions:
  - choose:
    - conditions:
      - condition: trigger
        id: button_single
      sequence:
        - action: light.turn_on
          target:
            entity_id: light.room
    - conditions:
      - condition: state
        entity_id: input_boolean.night_mode
        state: 'on'
      sequence:
        - action: light.turn_off
    default:
      - action: notify.mobile_devices
        data:
          message: "Default action"
```

## Condition Types

```yaml
# State condition
- condition: state
  entity_id: input_boolean.away_mode
  state: 'on'

# Numeric state
- condition: numeric_state
  entity_id: sensor.temperature
  above: 20
  below: 30

# Time condition
- condition: time
  after: '08:00:00'
  before: '22:00:00'
  weekday:
    - mon
    - tue
    - wed

# Sun condition
- condition: sun
  after: sunset
  after_offset: '-01:00:00'

# Template condition
- condition: template
  value_template: "{{ states('sensor.temperature') | float > 25 }}"
```

## Integrations in Use

- **Zigbee2MQTT**: Config at `config/zigbee2mqtt/configuration.yaml`
- **Frigate**: Camera notifications via automations
- **Yeelight**: Custom effects defined in `configuration.yaml`
- **Recorder**: Configured with 7-day retention, excludes energy sensors

## Streaming Frigate Cameras to Cast/Nest Displays

**NEVER use `camera.play_stream`** - it doesn't work with Frigate cameras and returns 500 errors.

### Prerequisites
1. **Expose go2rtc port 1984** in Frigate addon settings (Settings → Add-ons → Frigate → Network)
2. go2rtc streams must be defined in `frigate/config.yml` under `go2rtc.streams`

### Streaming to Cast devices
Use `media_player.play_media` with go2rtc's MP4 stream:
```yaml
- action: media_player.play_media
  target:
    entity_id: media_player.nest_hub
  data:
    media_content_id: "http://192.168.1.10:1984/api/stream.mp4?src=front_door_rmtp"
    media_content_type: "video/mp4"
```

### Stopping streams / returning to ambient mode
```yaml
# BAD - leaves blank screen with cast icon
- action: media_player.media_stop

# GOOD - returns to ambient/photo frame mode
- action: media_player.turn_off
  target:
    entity_id: media_player.nest_hub
```

### Checking if display is available (not playing content)
```yaml
- condition: state
  entity_id: media_player.nest_hub
  state:
    - idle
    - 'off'
```

## Testing Automations

1. **Trigger manually**: Developer Tools > Services > `automation.trigger`
2. **Check traces**: Settings > Automations > [automation] > Traces
3. **View logs**: `make pull` then check `config/home-assistant.log`
4. **Dry run**: Use `make validate` before pushing

## Direct HA API Access for Debugging

Use the HA API directly for real-time debugging. Requires `.env` with `HA_URL` and `HA_TOKEN`.

```bash
source .env

# Check entity state
curl -s "${HA_URL}/api/states/sensor.entity_name" -H "Authorization: Bearer ${HA_TOKEN}"

# Test service call directly
curl -s -X POST "${HA_URL}/api/services/light/turn_on" \
  -H "Authorization: Bearer ${HA_TOKEN}" -H "Content-Type: application/json" \
  -d '{"entity_id": "light.room"}'

# Reload specific domains (when make push blocked by new entities)
curl -s -X POST "${HA_URL}/api/services/automation/reload" -H "Authorization: Bearer ${HA_TOKEN}" -H "Content-Type: application/json"
curl -s -X POST "${HA_URL}/api/services/timer/reload" -H "Authorization: Bearer ${HA_TOKEN}" -H "Content-Type: application/json"
curl -s -X POST "${HA_URL}/api/services/template/reload" -H "Authorization: Bearer ${HA_TOKEN}" -H "Content-Type: application/json"
```

**Bypassing validation for new entities:** When validation fails because new helpers/templates don't exist yet (they're created on reload), push directly with rsync if official HA validation passed:
```bash
source .env && rsync -avz config/ ${HA_HOST}:/config/
# Then reload the specific domains
```

## Common Patterns

### Motion-Activated Light with Timer
```yaml
- id: motion_light
  alias: Motion Light
  triggers:
    - trigger: state
      entity_id: binary_sensor.motion
      to: 'on'
  actions:
    - action: light.turn_on
      target:
        entity_id: light.room
    - action: timer.start
      target:
        entity_id: timer.room_timer

- id: motion_light_off
  alias: Motion Light Off
  triggers:
    - trigger: event
      event_type: timer.finished
      event_data:
        entity_id: timer.room_timer
  actions:
    - action: light.turn_off
      target:
        entity_id: light.room
```

### Button with Multiple Actions
```yaml
- id: button_control
  alias: Button Control
  triggers:
    - trigger: device
      device_id: <id>
      type: action
      subtype: single
      id: single_press
    - trigger: device
      device_id: <id>
      type: action
      subtype: double
      id: double_press
  actions:
    - choose:
      - conditions:
        - condition: trigger
          id: single_press
        sequence:
          - action: light.toggle
            target:
              entity_id: light.room
      - conditions:
        - condition: trigger
          id: double_press
        sequence:
          - action: scene.turn_on
            target:
              entity_id: scene.bright
```

- All python tools need to be run with  `source venv/bin/activate && python <tool_path>`
