---
name: home-assistant-debugging
description: Use when investigating Home Assistant issues - entity behavior problems, automation failures, unexpected states after restart, template sensor bugs. Also use when user says "X isn't working", "X stopped working", "why does X do Y", or "something broke".
---

# Home Assistant Debugging

## Overview

Systematic approach to debugging Home Assistant issues. Find root cause before proposing fixes.

**Core principle:** Trace the problem to its source - whether in templates, automations, or entity configuration.

## CRITICAL: Context Management

**NEVER read these files directly:**
- `config/.storage/core.entity_registry` (1.7MB JSON)
- `config/.storage/core.device_registry` (96KB JSON)
- `config/automations.yaml` (48KB / 1,756 lines — targeted grep only)

**Entity lookup — pick ONE primary path, don't double-query:**
- **Live (HA running):** `ha_search` MCP tool — one call searches the entity registry AND automation/script/scene/helper configs.
- **Offline (no HA):** `uv run python tools/ha_cli.py entities --search "keyword" --json` (compact short-key output).
- **Known exact entity_id only:** `grep "exact.id" config/.storage/core.entity_registry` as a last-resort fallback.

**Shrink MCP responses to save tokens:**
- `ha_get_overview` with `fields=["system_info"]` to project one section (diagnostics are always retained).
- `ha_search` with `fields=["entities"]` and `limit=5` instead of the full payload.
- Prefer `detail_level="minimal"` (the default) — escalate to `standard`/`full` only when you need attributes.

## When to Use

- Entity shows wrong state after HA restart
- Automation not triggering or triggering incorrectly
- Template sensor returning unexpected values
- "unavailable" → wrong state transitions
- User reports "X stopped working" or "X behaves strangely"
- User asks "why does X do Y" or "something broke"

**When NOT to use:**
- Creating new automations (use home-assistant-automation)
- Dashboard layout issues
- Pure configuration questions with no malfunction

## Workflow

1. **Identify** — Find the entity, note domain/class
2. **Locate** — Find where entity is defined in config
3. **Analyze** — Trace logic, identify failure mode
4. **Fix** — Propose minimal fix, validate, deploy
5. **Reflect** — Capture learnings via `reflect` skill

| Phase | Tools/Commands | Purpose |
|-------|----------------|---------|
| Identify | `ha_cli entities`, `ha_search` MCP, `ha_cli curl /api/states/` | Find entity, check current state |
| Locate | `Grep` config files, `make backup-search` | Find definition and history |
| Analyze | `Read` (targeted lines), automation traces | Understand template/automation logic |
| Fix | `ha_cli edit`, `Edit`, `make validate`, `make push` | Apply and deploy fix |
| Reflect | `reflect` skill | Capture learnings (gotchas, corrections, patterns) |

## Phase 1: Identify the Entity

```bash
# Find the entity and its metadata
uv run python tools/ha_cli.py entities --search "shower"
uv run python tools/ha_cli.py entities --search "occupancy"
```

**Quick state checks via API:**
```bash
# Check current entity state and attributes
ha_cli curl /api/states/sensor.entity_name --pretty

# Check automation status — look for "last_triggered" attribute
ha_cli curl /api/states/automation.automation_name --pretty

# Check when an entity last changed state
# The "last_changed" and "last_updated" fields show timestamps
ha_cli curl /api/states/binary_sensor.entity_name --pretty
```

**`last_triggered` and `last_changed` are your fastest debugging tools:**
- If `last_triggered` is `null` or old, the automation never fired → check triggers
- If `last_triggered` is recent but nothing happened → check conditions/actions
- If `last_changed` is old, the entity state isn't updating → check source

**Note:**
- Device class (moisture, occupancy, presence) hints at sensor type
- Domain (binary_sensor, sensor, input_boolean) indicates definition location

## Phase 2: Locate the Definition

```bash
# Search for entity definition in configuration files
Grep "entity_name" config/configuration.yaml
Grep "entity_name" config/automations.yaml
```

**Where entities are defined by type:**

| Entity Pattern | Defined In | Modifiable |
|----------------|------------|------------|
| `binary_sensor.*` / `sensor.*` (template) | `configuration.yaml` (`template:` section) | Yes |
| `input_boolean.*`, `timer.*`, `input_datetime.*` | `configuration.yaml` (helpers section) | Yes |
| Automations | `automations.yaml` | Yes |
| `binary_sensor.*` / `sensor.*` (integration) | Integration (e.g., Z2M, Frigate) | No* |

*Integration entities can only be modified via integration config. For debugging integration entities, see "Integration Debugging" below.

### Integration Debugging

When the problem entity comes from an integration (Zigbee2MQTT, Frigate, etc.):

```bash
# Check integration logs via SSH
ssh homeassistant "ha apps logs 45df7312_zigbee2mqtt" | tail -50   # Z2M
ssh homeassistant "ha apps logs ccab4aaf_frigate-fa-beta" | tail -50  # Frigate

# Z2M web UI: check device status, interview, reconfigure
# Frigate web UI: check camera feeds, detection zones

# Verify MQTT connectivity
ha_cli curl /api/states/binary_sensor.zigbee2mqtt_bridge_connection_state
```

### Finding When a Change Was Introduced

If the user says "this worked before" or "this broke recently", use backup search to find when it changed:

```bash
# Search all backups for a specific pattern
make backup-search PATTERN='media_player.play_media'

# Check changelogs for what changed in each backup
cat backups/ha_config_YYYYMMDD_HHMMSS.changelog
```

## Phase 3: Analyze Root Cause

### Common Failure Patterns

| Symptom | Likely Cause | Where to Look |
|---------|--------------|---------------|
| Wrong state after restart | Template doesn't handle `unavailable` | `configuration.yaml` template |
| Automation not triggering | Trigger condition never met | `automations.yaml` triggers |
| Entity always "on" | Template logic flaw | `configuration.yaml` template |
| "unavailable" persists | Source entity offline | Check source entity status |
| State flip-flops | Missing debounce/delay_off | Template or automation |

### Template Sensor Debugging

**Trigger-based templates** are especially vulnerable after HA restart. When HA restarts, all entities transition from `unavailable` → first reading, which means:
- `trigger.from_state.state` = "unavailable"
- `| float(0)` converts "unavailable" to 0
- Large delta from 0 to real value triggers false positives

```yaml
# PROBLEM: Doesn't handle unavailable → available transition
- trigger:
    - trigger: state
      entity_id: sensor.humidity
  binary_sensor:
    - name: "Shower Occupancy"
      state: >
        {% set old = trigger.from_state.state | float(0) %}
        {% set new = trigger.to_state.state | float(0) %}
        # BUG: "unavailable" becomes 0, causing false triggers
```

**Fix pattern - always guard trigger-based templates:**

```yaml
state: >
  {% set current = this.state if this.state in ['on', 'off'] else 'off' %}
  {% if trigger.from_state.state in ['unavailable', 'unknown'] %}
    {{ current }}
  {% else %}
    {# Normal logic here #}
  {% endif %}
```

### Automation Debugging

```bash
# Find the automation
Grep "automation_name_or_keyword" config/automations.yaml
```

**Check automation traces** for execution history:
- HA UI: Settings > Automations > find automation > three-dot menu > Traces
- CLI: `ha_cli trace automation.<name>` — fetch trace data as JSON via the WebSocket API
- CLI: `ha_cli trace` — list all automations with available traces
- Traces show each step: trigger matched, conditions evaluated, actions executed
- If no traces exist, the trigger never fired
- If traces show condition failure, read the condition values at that timestamp

**Common automation issues:**
- `for:` duration prevents quick triggers
- `condition: state` blocks when entity unavailable
- Wrong `entity_id` (typo or renamed entity)
- `mode: single` ignores triggers while running

## Phase 4: Fix and Deploy

1. **Propose minimal fix** - explain the change to user
2. **Get approval** - don't fix without confirmation
3. **Make targeted edit** - smallest change that fixes the issue
4. **Validate:** `make validate`
5. **Deploy:** `make push`

## Debugging Workflow for Service Failures

When a service call doesn't work as expected:

1. **Test the service directly** via API to isolate automation vs service issue
2. **Check entity states** - is the target in expected state?
3. **Check automation traces** (Settings > Automations > Traces) - did the automation run? Did each step succeed?
4. **Check HA logs** — two approaches:

```bash
# Option A: CLI (structured JSON via WebSocket)
ha_cli logs
ha_cli logs --level ERROR

# Option B: SSH (full logs with follow)
ssh homeassistant "ha core logs" | tail -100
```


# Follow logs in real-time (useful for reproducing issues)
ssh homeassistant "ha core logs --follow"

# Addon-specific logs
ssh homeassistant "ha apps logs 45df7312_zigbee2mqtt"   # Z2M
ssh homeassistant "ha apps logs ccab4aaf_frigate-fa-beta"  # Frigate
```

This isolates whether the problem is:
- The service itself (500 error, not supported)
- The automation logic (service works manually but not via automation)
- Entity state conditions (automation not triggering)

## Direct HA API Access for Debugging

Use `ha_cli` dedicated subcommands for common debugging tasks:

```bash
# Check entity state and attributes (last_changed, last_triggered)
ha_cli curl /api/states/sensor.entity_name --pretty

# Query entity history over a period
ha_cli history sensor.name                        # last 24 hours (empty = stderr hint)
ha_cli history sensor.name --since 2026-06-27T00:00:00Z  # since timestamp
ha_cli history sensor.name --first 20             # first 20 state records only
ha_cli history sensor.name --pick state,last_changed  # keep only those fields (saves tokens)

# Fetch automation trace (summary dedupes, strips verbose fields)
ha_cli trace automation.name                      # specific automation
ha_cli trace                                      # list all traces (deduped in summary)

# Fetch system log (structured JSON, WebSocket)
ha_cli logs                                       # summary: count + first_occurred included

# Query logbook for recent events (ISO 8601 UTC)
# Example: ha_cli curl "/api/logbook/YYYY-MM-DDT00:00:00Z"
# Use today's UTC date — e.g. 2026-06-27 for June 27, 2026
ha_cli curl "/api/logbook/2026-06-27T00:00:00Z"
```

### Bypass Validation for New Entities

**LAST RESORT** - only when `make push` validation fails because new helpers/templates don't exist yet (chicken-and-egg with reload):

```bash
# DANGER: Bypasses all local validation. Only use if:
# 1. Official HA validation (`make validate`) passed
# 2. Errors are ONLY for entities that will exist after reload
# Risk: Pushing invalid config can break HA startup
rsync -avz config/ homeassistant:/config/
# Then reload the specific domains:
ha_cli curl --post /api/services/automation/reload
ha_cli curl --post /api/services/template/reload
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Reading entire entity_registry | Use `ha_search` MCP, `ha_cli entities`, or `Grep` |
| Proposing fix before finding root cause | Complete Phase 3 first |
| Guessing the problem | Trace the actual logic |
| Fixing symptoms not cause | Ask "why does this happen?" |
| Large rewrites | Minimal targeted changes only |
| Not checking for unavailable states | Templates must handle unavailable |

## Red Flags - You're Doing It Wrong

- Proposing fixes without reading the entity definition
- Reading large registry files directly
- "I think the problem might be..." without evidence
- Changing multiple things at once
- Skipping validation before push
- Not explaining root cause to user

**All of these mean: Go back to Phase 2 and trace the actual code.**

## Phase 5: Reflect & Learn

After fixing the issue, use the `reflect` skill to capture any learnings — new failure patterns, documentation gaps, or gotchas discovered during debugging.

**Quick self-check before completing:**
- [ ] Root cause identified and explained to user
- [ ] Fix deployed and validated
- [ ] User confirmed issue is resolved
- [ ] Any learnings documented (if applicable)
