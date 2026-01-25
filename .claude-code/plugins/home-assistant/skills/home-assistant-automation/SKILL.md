---
name: home-assistant-automation
description: Use when creating, modifying, or troubleshooting Home Assistant automations - guides entity discovery, design, implementation, and validation workflow
---

# Home Assistant Automation Creation

## Overview

Structured workflow for creating and modifying Home Assistant automations with entity validation, user clarification, and safe deployment.

## When to Use

- Creating new automations
- Modifying existing automations
- Adding new triggers/conditions/actions
- Troubleshooting automation issues
- User asks to "add an automation" or "make something happen when..."

**When NOT to use:**
- Simple entity lookups (use entity_explorer directly)
- Dashboard-only changes (no automation involved)
- Integration setup (configuration.yaml changes)

## Workflow

```dot
digraph automation_flow {
    rankdir=TB;

    subgraph cluster_discovery {
        label="1. DISCOVERY";
        style=filled;
        color=lightblue;
        "Read automations.yaml" -> "Search entity registry";
        "Search entity registry" -> "Identify candidate entities";
    }

    subgraph cluster_clarify {
        label="2. CLARIFY";
        style=filled;
        color=lightyellow;
        "Identify candidate entities" -> "Multiple options?";
        "Multiple options?" -> "Ask user to choose" [label="yes"];
        "Multiple options?" -> "Confirm understanding" [label="no"];
        "Ask user to choose" -> "Confirm understanding";
    }

    subgraph cluster_design {
        label="3. DESIGN";
        style=filled;
        color=lightgreen;
        "Confirm understanding" -> "Plan trigger/condition/action";
        "Plan trigger/condition/action" -> "Check for helpers needed";
        "Check for helpers needed" -> "Need new helper?" [shape=diamond];
        "Need new helper?" -> "Add to configuration.yaml" [label="yes"];
        "Need new helper?" -> "Draft automation YAML" [label="no"];
        "Add to configuration.yaml" -> "Draft automation YAML";
    }

    subgraph cluster_implement {
        label="4. IMPLEMENT";
        style=filled;
        color=lightpink;
        "Draft automation YAML" -> "Edit automations.yaml";
        "Edit automations.yaml" -> "make validate";
    }

    subgraph cluster_deploy {
        label="5. DEPLOY";
        style=filled;
        color=lightgray;
        "make validate" -> "Validation passed?";
        "Validation passed?" -> "make push" [label="yes"];
        "Validation passed?" -> "Fix errors" [label="no"];
        "Fix errors" -> "make validate";
        "make push" -> "Done";
    }
}
```

## Quick Reference

| Phase | Tools/Commands | Purpose |
|-------|----------------|---------|
| Discovery | `Glob`, `Grep`, `Read` | Find entities, existing automations |
| Clarify | `AskUserQuestion` | Resolve ambiguity, confirm intent |
| Design | `Read` registry files | Plan structure, identify helpers |
| Implement | `Edit` | Modify YAML files |
| Deploy | `make validate`, `make push` | Test and deploy |

## Phase 1: Discovery

**Always start here.** Before writing ANY automation:

```bash
# 1. Read current automations to understand patterns
Read config/automations.yaml

# 2. Search entity registry for relevant entities
Grep "keyword" config/.storage/core.entity_registry

# 3. Use entity explorer for complex searches
source venv/bin/activate && python tools/entity_explorer.py --search "motion"
```

**Key files to check:**
- `config/automations.yaml` - Existing automations (patterns, IDs)
- `config/.storage/core.entity_registry` - All entities and IDs
- `config/.storage/core.device_registry` - Device IDs for triggers
- `config/configuration.yaml` - Helpers, integrations, templates

**Entity naming convention:** `location_room_device_sensor`
- Example: `binary_sensor.home_basement_motion_battery`

## Phase 2: Clarify

**ALWAYS ask when:**
- Multiple sensors could work (which motion sensor?)
- Multiple locations involved (which room?)
- Timing is ambiguous (day only? always?)
- Behavior has options (toggle vs always-on?)

**Example clarification questions:**
- "I found 3 motion sensors in the basement. Which should trigger this?"
- "Should this run only during certain hours?"
- "What automation mode: single (ignore new triggers) or restart?"

**DO NOT assume.** Even if one option seems obvious, confirm with user.

## Phase 3: Design

### Automation Structure

```yaml
- id: unique_snake_case_id
  alias: Human-Readable Name
  description: What this automation does
  triggers:
    - trigger: state|device|time|numeric_state|sun|event|zone
      # trigger-specific fields
  conditions:
    - condition: state|numeric_state|time|template
      # condition-specific fields
  actions:
    - action: domain.service
      target:
        entity_id: entity.id
      data: {}
  mode: single|queued|restart|parallel
```

### Common Patterns

**Motion-activated with timer:**
```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.room_motion
    to: 'on'
actions:
  - action: light.turn_on
    target:
      entity_id: light.room
  - action: timer.start
    target:
      entity_id: timer.room_timer
```

**Multi-trigger with choose:**
```yaml
triggers:
  - trigger: device
    device_id: xxx
    subtype: single
    id: single_press
  - trigger: device
    device_id: xxx
    subtype: double
    id: double_press
actions:
  - choose:
    - conditions:
      - condition: trigger
        id: single_press
      sequence:
        - action: light.toggle
    - conditions:
      - condition: trigger
        id: double_press
      sequence:
        - action: scene.turn_on
```

**Toggle-gated automation:**
```yaml
conditions:
  - condition: state
    entity_id: input_boolean.feature_toggle
    state: 'on'
```

### Helper Entities

If automation needs state tracking, add helpers to `configuration.yaml`:

```yaml
input_boolean:
  feature_toggle:
    name: Feature Toggle
    icon: mdi:toggle-switch

timer:
  room_timer:
    name: Room Timer
    duration: "00:10:00"
```

**Note:** New helpers require "Reload all YAML configuration" in HA to appear.

## Phase 4: Implement

**Rules for editing:**
1. Make focused, targeted edits (not wholesale rewrites)
2. Preserve existing automation IDs
3. Use exact string matching for Edit tool
4. One logical change per edit when possible

**Validation runs automatically** via post-edit hooks. Watch for errors.

## Phase 5: Deploy

```bash
# Validate all changes
make validate

# If validation passes, deploy
make push
```

**Validation checks:**
- YAML syntax
- Entity reference existence
- Device ID validity
- Official HA configuration validation

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using entity without verifying existence | Always check registry first |
| Assuming which sensor to use | Ask user when multiple options |
| Creating automation before reading existing | Read automations.yaml first |
| Large wholesale file rewrites | Use targeted Edit calls |
| Skipping validation | Always run `make validate` |
| Not checking for needed helpers | Review if timers/toggles needed |

## Red Flags - You're Doing It Wrong

- Writing automation without reading automations.yaml first
- Not searching entity registry before using entity IDs
- Assuming entity exists without verification
- Not asking when multiple sensors/devices could work
- Pushing without validation
- Adding helpers without mentioning reload requirement

**All of these mean: Go back to Phase 1 and follow the workflow.**

## Trigger Types Quick Reference

| Type | Use For | Key Fields |
|------|---------|------------|
| `state` | Entity state changes | `entity_id`, `to`, `from` |
| `numeric_state` | Thresholds | `entity_id`, `above`, `below` |
| `device` | Buttons, physical events | `device_id`, `type`, `subtype` |
| `time` | Scheduled | `at` |
| `time_pattern` | Recurring | `hours`, `minutes`, `seconds` |
| `sun` | Sunrise/sunset | `event`, `offset` |
| `event` | HA events | `event_type`, `event_data` |
| `zone` | Location | `entity_id`, `zone`, `event` |

## Automation Modes

| Mode | When to Use |
|------|-------------|
| `single` | Default - ignore triggers while running |
| `queued` | Process all triggers in order |
| `restart` | Cancel current, start fresh on new trigger |
| `parallel` | Run multiple instances simultaneously |

## Finding Entity/Device IDs

```bash
# Search by name
python tools/entity_explorer.py --search "bathroom"

# List domain
python tools/entity_explorer.py --domain binary_sensor

# Device IDs (for device triggers)
Grep "device_id" config/.storage/core.entity_registry

# Or search by device name
Grep "Bathroom Button" config/.storage/core.device_registry
```
