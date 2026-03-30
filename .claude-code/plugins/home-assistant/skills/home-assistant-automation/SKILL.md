---
name: home-assistant-automation
description: Use when creating, modifying, or designing Home Assistant automations or scripts — also use when the user describes desired behavior like "when X happens do Y", "notify me when...", "turn on X when...", "schedule X", or any request that implies triggers, conditions, or automated actions
---

# Home Assistant Automation & Script Creation

## Overview

Structured workflow for creating and modifying Home Assistant automations and scripts with entity validation, user clarification, and safe deployment.

## CRITICAL: Context Management

**NEVER read these files directly:**
- `config/.storage/core.entity_registry` (90k+ lines)
- `config/.storage/core.device_registry` (7k+ lines)
- `config/automations.yaml` (1600+ lines)

**Instead:** Use `Grep` or `uv run python tools/entity_explorer.py --search "keyword"`

## When to Use

- Creating new automations or scripts
- Modifying existing automations or scripts
- Adding new triggers/conditions/actions
- User describes desired behavior in natural language:
  - "when X happens, do Y"
  - "notify/alert me when..."
  - "turn on/off X when..."
  - "schedule X to..."
  - "I want X to automatically..."
  - "play camera when doorbell rings"
  - "can you make it so the lights..."
- Editing `config/automations.yaml` or `config/scripts.yaml`

**When NOT to use:**
- Dashboard-only changes (no automation involved)
- Integration setup (configuration.yaml changes without automations)
- Debugging broken automations — use `home-assistant-debugging` skill instead

## Workflow

1. **DISCOVERY** — Search existing automations/scripts and find relevant entities
2. **CLARIFY** — Resolve ambiguity, confirm intent with user
3. **DESIGN** — Plan trigger/condition/action structure, check for needed helpers
4. **IMPLEMENT** — Edit YAML files with targeted changes
5. **DEPLOY** — Validate, push, verify deployment
6. **REFLECT** — Capture learnings via `reflect` skill

| Phase | Tools/Commands | Purpose |
|-------|----------------|---------|
| Discovery | `Grep`, `uv run python tools/entity_explorer.py` | Find entities, existing automations/scripts |
| Clarify | `AskUserQuestion` | Resolve ambiguity, confirm intent |
| Design | `Read configuration.yaml` | Check helpers (small file, safe to read) |
| Implement | `Edit` | Modify YAML files |
| Deploy | `make validate`, `make push` | Test and deploy |
| Reflect | `reflect` skill | Capture learnings (gotchas, corrections, patterns) |

## Phase 1: Discovery

**Always start here.** Before writing ANY automation or script:

**Always** use `home-assistant-backup` skill first (pull, backup, prune) — even for small changes. No exceptions.

```bash
# 1. Find similar automations/scripts by keyword
Grep "motion" config/automations.yaml
Grep "motion" config/scripts.yaml
Grep "- id:" config/automations.yaml   # List all automation IDs

# 2. Read a specific existing automation (find it, then read with offset)
Grep -n "id: doorbell_notification" config/automations.yaml  # Get line number
Read config/automations.yaml offset=<line> limit=50          # Read just that automation

# 3. Use entity explorer for entity lookups (preferred method)
uv run python tools/entity_explorer.py --search "bathroom"
uv run python tools/entity_explorer.py --domain light

# 4. For device IDs (device triggers), search by device name
Grep "Bathroom Button" config/.storage/core.device_registry

# 5. Validate specific entity exists
Grep "bathroom_motion" config/.storage/core.entity_registry
```

**Safe to read directly:**
- `config/configuration.yaml` — Small, contains helpers/integrations

**Entity naming convention:** `location_room_device_sensor`
- Example: `binary_sensor.home_basement_motion_battery`

## Phase 2: Clarify

**ALWAYS ask when:**
- Multiple sensors could work (which motion sensor?)
- Multiple locations involved (which room?)
- Timing is ambiguous (day only? always?)
- Behavior has options (toggle vs always-on?)
- Automation mode matters (see Phase 3)

**Example clarification questions:**
- "I found 3 motion sensors in the basement. Which should trigger this?"
- "Should this run only during certain hours?"
- "What automation mode: single (ignore new triggers), restart, or queued?"

**DO NOT assume.** Even if one option seems obvious, confirm with user.

## Phase 3: Design

### Automation ID Convention

Use descriptive slugs for automation IDs:
```yaml
- id: doorbell_camera_to_nest_hub
- id: basement_motion_lights
- id: nightly_porch_light_off
```

### Automation Mode

Choose `mode:` based on behavior needs (default is `single`):

| Mode | Behavior | Use When |
|------|----------|----------|
| `single` | Ignores new triggers while running | One-shot actions (notifications) |
| `restart` | Cancels current run, starts over | Motion-activated timers (re-trigger extends) |
| `queued` | Queues triggers, runs sequentially | Sequential processing needed |
| `parallel` | Runs multiple instances simultaneously | Independent per-trigger actions |

**Common gotcha:** Motion-activated lights with timers almost always want `mode: restart` so re-triggering extends the timer instead of being ignored.

### Trigger Gotchas

**`from:` constraint drops post-restart events:** After HA restarts, entities start in `unknown`/`unavailable`. Triggers with `from: ['off']` miss the first transition (e.g., `unknown -> on`). Only use `from:` when you specifically need to ignore startup transitions. For motion sensors, omit `from:`.

**`for:` duration on triggers:** The entity must remain in the target state for the entire duration. If state flickers, the timer resets. Useful for "door open for 5 minutes" alerts, not for instant triggers.

### Common Patterns

**Motion-activated with timer:**
```yaml
mode: restart  # Re-trigger extends timer
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

### Scripts

Scripts live in `config/scripts.yaml` and follow the same validation/deployment workflow. Use scripts for reusable action sequences called from multiple automations:

```yaml
# scripts.yaml
debug_log:
  alias: Debug Log
  fields:
    message:
      description: Log message
  sequence:
    - action: system_log.write
      data:
        message: "{{ message }}"
```

**Parameter name gotcha:** Parameter names must match exactly between automation `data:` and script `fields:`. With `| default(omit)` patterns, mismatches silently fail.

## Phase 4: Implement

**Rules for editing:**
1. Make focused, targeted edits (not wholesale rewrites)
2. Preserve existing automation IDs
3. Use exact string matching for Edit tool
4. One logical change per edit when possible

**Validation runs automatically** via post-edit hooks. Watch for errors.

## Phase 5: Deploy & Verify

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

**Post-deploy verification:**
- Check `last_triggered` timestamp updated after testing
- Confirm expected behavior with user
- For time-based triggers, verify next scheduled run

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Reading entire entity_registry (90k lines) | Use `entity_explorer.py` or `Grep` |
| Reading entire automations.yaml | Use `Grep` to find specific sections |
| Using entity without verifying existence | Use entity_explorer to validate |
| Assuming which sensor to use | Ask user when multiple options |
| Large wholesale file rewrites | Use targeted Edit calls |
| Skipping validation | Always run `make validate` |
| Not checking for needed helpers | Review if timers/toggles needed |
| Using `camera.play_stream` for Frigate | Use `media_player.play_media` with go2rtc (see CLAUDE.md) |
| Multi-line Jinja for URLs/IDs | Use single-line templates to avoid whitespace |
| Using `media_player.media_stop` for Cast | Use `turn_off` to return to ambient mode |
| Wrong `mode:` for motion timers | Use `restart` so re-triggers extend the timer |
| Using `from:` on motion triggers | Omit `from:` so post-restart transitions aren't missed |
| Mismatched script parameter names | Compare automation `data:` keys with script `fields:` keys exactly |
| Rapid-fire Zigbee commands to same device | Add 250ms `delay` between each command (see CLAUDE.md → Zigbee Command Timing) |

## Red Flags - You're Doing It Wrong

- Writing automation without searching automations.yaml first
- Assuming entity exists without verification
- Not asking when multiple sensors/devices could work
- Pushing without validation
- Adding helpers without mentioning reload requirement

**All of these mean: Go back to Phase 1 and follow the workflow.**

## Phase 6: Reflect & Learn

After deployment, use the `reflect` skill to capture any learnings — new gotchas, corrections, or patterns discovered during this work.

**Quick self-check before completing:**
- [ ] Automation/script deployed and validated
- [ ] User confirmed behavior is correct
- [ ] Any learnings documented (if applicable)
