---
name: home-assistant-debugging
description: Use when investigating Home Assistant issues - entity behavior problems, automation failures, unexpected states after restart, template sensor bugs
---

# Home Assistant Debugging

## Overview

Systematic approach to debugging Home Assistant issues. Find root cause before proposing fixes.

**Core principle:** Trace the problem to its source - whether in templates, automations, or entity configuration.

## CRITICAL: Context Management

**Large files that will exhaust context if read fully:**
- `config/.storage/core.entity_registry` - 90k+ lines - **NEVER read directly**
- `config/.storage/core.device_registry` - 7k+ lines - **NEVER read directly**
- `config/automations.yaml` - 1600+ lines - **Use Grep to find specific automations**

**Always use targeted searches:**
- Use `Grep` with specific entity/keyword, not `Read` on large files
- Use `python tools/entity_explorer.py --search "keyword"` for entity lookups
- When reading automations.yaml, use `Grep` first, then `Read` with line offsets

## When to Use

- Entity shows wrong state after HA restart
- Automation not triggering or triggering incorrectly
- Template sensor returning unexpected values
- "unavailable" → wrong state transitions
- User reports "X stopped working" or "X behaves strangely"

**When NOT to use:**
- Creating new automations (use home-assistant-automation)
- Simple entity lookups
- Dashboard layout issues

## Workflow

```dot
digraph debug_flow {
    rankdir=TB;

    subgraph cluster_identify {
        label="1. IDENTIFY";
        style=filled;
        color=lightblue;
        "Get entity name" -> "Search entity_explorer";
        "Search entity_explorer" -> "Note device class and domain";
    }

    subgraph cluster_locate {
        label="2. LOCATE DEFINITION";
        style=filled;
        color=lightyellow;
        "Note device class and domain" -> "Grep config files for entity";
        "Grep config files for entity" -> "Found in configuration.yaml?" [shape=diamond];
        "Found in configuration.yaml?" -> "Read template/sensor definition" [label="yes"];
        "Found in configuration.yaml?" -> "Check automations.yaml" [label="no"];
        "Check automations.yaml" -> "Read automation definition";
    }

    subgraph cluster_analyze {
        label="3. ANALYZE ROOT CAUSE";
        style=filled;
        color=lightgreen;
        "Read template/sensor definition" -> "Trace logic flow";
        "Read automation definition" -> "Trace logic flow";
        "Trace logic flow" -> "Identify failure mode";
        "Identify failure mode" -> "Document root cause";
    }

    subgraph cluster_fix {
        label="4. FIX AND DEPLOY";
        style=filled;
        color=lightpink;
        "Document root cause" -> "Propose minimal fix";
        "Propose minimal fix" -> "User approves?";
        "User approves?" -> "Edit configuration" [label="yes"];
        "Edit configuration" -> "make validate";
        "make validate" -> "make push";
    }
}
```

## Quick Reference

| Phase | Tools/Commands | Purpose |
|-------|----------------|---------|
| Identify | `entity_explorer.py --search` | Find entity, note domain/class |
| Locate | `Grep`, `bash grep -r` | Find where entity is defined |
| Analyze | `Read` (targeted lines) | Understand template/automation logic |
| Fix | `Edit`, `make validate`, `make push` | Apply and deploy fix |

## Phase 1: Identify the Entity

```bash
# Find the entity and its metadata
source venv/bin/activate && python tools/entity_explorer.py --search "shower"
source venv/bin/activate && python tools/entity_explorer.py --search "occupancy"
```

**Note:**
- Device class (moisture, occupancy, presence) hints at sensor type
- Domain (binary_sensor, sensor, input_boolean) indicates definition location

## Phase 2: Locate the Definition

```bash
# Search all config files for entity definition
grep -r "entity_name" config/ 2>/dev/null

# Common locations by type:
# - Template sensors: config/configuration.yaml (template: section)
# - Automations: config/automations.yaml
# - Helpers: config/configuration.yaml (input_boolean:, timer:, etc.)
# - Integration entities: config/.storage/core.entity_registry (read-only)
```

**Integration entities** (created by integrations like Zigbee2MQTT) cannot be modified in config - their behavior comes from the integration.

**Template entities** are defined in `configuration.yaml` under `template:` section.

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

**Trigger-based templates** (common issue source):

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

**Fix pattern - always check for unavailable/unknown:**

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

# Check triggers - are conditions ever met?
# Check conditions - are they blocking execution?
# Check actions - is the right service called?
```

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

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Reading entire entity_registry | Use entity_explorer or Grep |
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

## Restart-Related Issues

HA restart causes all entities to transition: `unavailable` → first reading

**Template sensors with triggers** are especially vulnerable:
- `trigger.from_state.state` = "unavailable"
- `| float(0)` converts "unavailable" to 0
- Large delta from 0 to real value triggers false positives

**Fix:** Always guard trigger-based templates:

```yaml
{% if trigger.from_state.state in ['unavailable', 'unknown'] %}
  {{ this.state | default('off') }}
{% else %}
  {# normal logic #}
{% endif %}
```

## Entity Types and Where Defined

| Entity Pattern | Defined In | Modifiable |
|----------------|------------|------------|
| `binary_sensor.name` (template) | configuration.yaml | Yes |
| `sensor.name` (template) | configuration.yaml | Yes |
| `input_boolean.name` | configuration.yaml | Yes |
| `timer.name` | configuration.yaml | Yes |
| `binary_sensor.device_name` (integration) | Integration | No* |
| `sensor.device_name` (integration) | Integration | No* |

*Integration entities can only be modified via integration config (e.g., Zigbee2MQTT config).

## Direct HA API Access for Debugging

When you need real-time state checks or to test services without full deployment, use the HA API directly.

**Prerequisites:** `.env` file with `HA_URL` and `HA_TOKEN` configured.

### Check Entity State
```bash
source .env
curl -s "${HA_URL}/api/states/sensor.entity_name" \
  -H "Authorization: Bearer ${HA_TOKEN}"
```

### Check Automation Status (was it triggered?)
```bash
source .env
curl -s "${HA_URL}/api/states/automation.automation_name" \
  -H "Authorization: Bearer ${HA_TOKEN}"
# Look for "last_triggered" in attributes
```

### Test Service Calls Directly
```bash
source .env
curl -s -X POST "${HA_URL}/api/services/light/turn_on" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "light.room_light"}'
```

### Reload Specific Domains
When `make push` validation blocks due to new entities that will exist after reload:

```bash
source .env
# Reload automations
curl -s -X POST "${HA_URL}/api/services/automation/reload" \
  -H "Authorization: Bearer ${HA_TOKEN}" -H "Content-Type: application/json"

# Reload timers
curl -s -X POST "${HA_URL}/api/services/timer/reload" \
  -H "Authorization: Bearer ${HA_TOKEN}" -H "Content-Type: application/json"

# Reload template entities
curl -s -X POST "${HA_URL}/api/services/template/reload" \
  -H "Authorization: Bearer ${HA_TOKEN}" -H "Content-Type: application/json"
```

### Push Directly When Validation Blocks on New Entities

When validation fails because new helpers/templates don't exist yet (expected - they're created on reload):

```bash
# Check official HA validation passed (most important)
# If only entity reference validation fails for NEW entities, push directly:
source .env
rsync -avz config/ ${HA_HOST}:/config/

# Then reload the specific domains
```

**Only bypass validation when:**
- Official HA validation passed
- Entity reference errors are for NEW entities defined in the same change
- You understand why validation is failing

## Debugging Workflow for Service Failures

When a service call doesn't work as expected:

1. **Test the service directly** via API to isolate automation vs service issue
2. **Check entity states** - is the target in expected state?
3. **Check automation traces** - did the automation run?
4. **Check HA logs** - `config/home-assistant.log` after `make pull`

### Example: Debugging camera streaming failure

```bash
# 1. Test service directly
curl -s -X POST "${HA_URL}/api/services/camera/play_stream" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "camera.front_door", "media_player": "media_player.nest_hub"}'
# If 500 error → service doesn't work with this camera type

# 2. Try alternative service
curl -s -X POST "${HA_URL}/api/services/media_player/play_media" \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.nest_hub", "media_content_id": "http://...", "media_content_type": "video/mp4"}'
```

This isolates whether the problem is:
- The service itself (500 error, not supported)
- The automation logic (service works manually but not via automation)
- Entity state conditions (automation not triggering)
