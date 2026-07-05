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
- `config/automations.yaml` (59KB / 1,815 lines — targeted grep only)

### Common mistakes

**Anti-pattern:** checking an entity's state with BOTH `ha_cli curl
/api/states/X` AND `ha_get_state("X")`. They return the same data; pick one
(prefer `ha_get_state` with `fields=["state","last_changed"]` — ~65 tokens vs
curl's ~670 unprojected).

**Shrink MCP responses to save tokens:**
- `ha_get_overview` with `fields=["system_info"]` to project one section (diagnostics are always retained).
- `ha_search` with `fields=["entities"]` and `limit=5` instead of the full payload.
- `ha_get_state` with `fields=["state","last_changed"]` instead of full attributes.
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
| Identify | `ha_search` MCP, `ha_get_state` MCP | Find entity, check current state |
| Locate | `Grep` config files, `make backup-search` | Find definition and history |
| Analyze | `Read` (targeted lines), automation traces | Understand template/automation logic |
| Fix | `ha_cli edit`, `Edit`, `make validate`, `make push` | Apply and deploy fix |
| Reflect | `reflect` skill | Capture learnings (gotchas, corrections, patterns) |

## Phase 1: Identify the Entity

**Quick state checks via MCP ha_get_state:**
1. **Check current entity state and attributes:**
   `ha_get_state("sensor.entity_name")`

2. **Check automation status — look for "last_triggered":**
   `ha_get_state("automation.automation_name", fields=["state", "attributes.last_triggered"])`

3. **Check when an entity last changed state:**
   `ha_get_state("binary_sensor.entity_name", fields=["state", "last_changed", "last_updated"])`

**`last_triggered` and `last_changed` are your fastest debugging tools:**
- If `last_triggered` is `null` or old, the automation never fired → check triggers
- If `last_triggered` is recent but nothing happened → check conditions/actions
- If `last_changed` is old, the entity state isn't updating → check source
- If `last_changed == last_updated` and both are old, the sensor is **frozen** — reporting a plausible value but never updating (still shows "available", often healthy battery).     Confirm with `ha_get_state("<id>", fields=["state","last_changed","last_updated"])`. See Common Failure Patterns: "Sensor value frozen"

**Note:**
- Device class (moisture, occupancy, presence) hints at sensor type
- Domain (binary_sensor, sensor, input_boolean) indicates definition location

## Phase 2: Locate the Definition

1. **Find where an entity is defined or referenced:**
   `ha_search("entity_name")` — searches config bodies (configuration.yaml, automations.yaml, helpers)

2. **Narrow to a specific config type:**
   `ha_search("entity_name", search_types=["automation", "helper"])`

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
ha_get_state("binary_sensor.zigbee2mqtt_bridge_connection_state")
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
| Sensor value frozen (plausible reading, never updates; battery reports healthy) | Stale Zigbee/mesh sensor — dropped offline while reporting a value (common after restart) | `ha_get_state("<id>", fields=["state","last_changed","last_updated"])`; if `last_changed == last_updated` and old, it's frozen. Re-interview/re-pair in Z2M (see CLAUDE.md → Zigbee Stale Sensors) |
| State flip-flops | Missing debounce/delay_off | Template or automation |
| User says "X on all day" but recorder shows off | Post-restart Zigbee actuator desync (bulb on, HA off — Z2M didn't resync) | Physical light; `core.restore_state`; add startup reconciliation automation (see CLAUDE.md → Post-restart Zigbee actuator desync) |

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

**Find the automation:** `ha_search("automation_name_or_keyword")`

**Check automation traces** for execution history:
- HA UI: Settings > Automations > find automation > three-dot menu > Traces
- **MCP: `ha_get_automation_traces("automation.<name>")`** — preferred. Returns recent runs; pass a `run_id` for full step-by-step detail (trigger matched, conditions evaluated, actions executed).
- CLI: `ha_cli trace` (no arg) — lists traces across ALL automations. `ha_cli trace automation.<name>` — fetch a specific automation's trace.
- If no traces exist, the trigger never fired
- If traces show condition failure, read the condition values at that timestamp
- **(HA 2026.7+)** Traces now *always* include template errors, so a clean trace means templates didn't error — not that templates weren't evaluated.

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

1. **Test the service directly** via MCP `ha_call_service` to isolate automation vs service issue
2. **Check entity states** via `ha_get_state` - is the target in expected state?
3. **Check automation traces** (Settings > Automations > Traces) - did the automation run? Did each step succeed?
4. **Check HA logs** — via SSH (full logs with follow):

```bash
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

## Direct HA API Access (Fallback)

**Prefer MCP for normal debugging.** Use `ha_cli` when MCP is unavailable:

| Task | MCP (preferred) | ha_cli (fallback) |
|------|-----------------|-------------------|
| Check entity state | `ha_get_state("X", fields=["state","last_changed"])` | `ha_cli curl /api/states/X --pretty` |
| Fetch automation trace | `ha_get_automation_traces("automation.X")` | `ha_cli trace automation.X` |
| List all traces | No MCP equivalent | `ha_cli trace` (no arg) |
| Fetch system logs | `ha_get_logs(source="system", level="ERROR", limit=30)` | `ha_cli curl "/api/logbook/YYYY-MM-DDT00:00:00Z"` |

### Bypass Validation for New Entities

**LAST RESORT** - only when `make push` validation fails because new helpers/templates don't exist yet (chicken-and-egg with reload):

```bash
# DANGER: Bypasses all local validation. Only use if:
# 1. Official HA validation (`make validate`) passed
# 2. Errors are ONLY for entities that will exist after reload
# Risk: Pushing invalid config can break HA startup
rsync -avz config/ homeassistant:/config/
# Then reload the specific domains via MCP:
ha_call_service("automation", "reload")
ha_call_service("template", "reload")
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Reading entire entity_registry | Use `ha_search` MCP or `Grep` |
| Proposing fix before finding root cause | Complete Phase 3 first |
| Guessing the problem | Trace the actual logic |
| Fixing symptoms not cause | Ask "why does this happen?" |
| Large rewrites | Minimal targeted changes only |
| Not checking for unavailable states | Templates must handle unavailable |

### Tool Efficiency

| Inefficiency | Better path |
|--------------|-------------|
| Looping a light group's members serially | Query the group entity once (e.g. `light.outside_downlights`) — covers all members |
| Post-deploy entity verification via MCP `ha_search` | Go straight to `ha_get_state("<guessed_slug>")` — the search index lags right after a reload, so direct state lookup is reliable when the slug is predictable from the alias |
| Inline `uv run python -c "..."` to filter JSON | Use the CLI's `--pick` / `--first` / `--max-chars` flags — avoids spawning a full interpreter per filter |
| Speculative MCP `/api/logbook` calls with no hypothesis | Skip unless you have a specific question; they usually return noise |
| Pulling `ha_get_history` for an entity you have no hypothesis about (e.g., the light's on/off log while diagnosing a *guard* sensor failure) | Skip it — `history` answers "when did X change," so only pull it for the entity your hypothesis targets. For a "is this sensor stale?" question, lead with `ha_get_state("<id>", fields=["state","last_changed","last_updated"])` (the `last_changed == last_updated` tell), then use `ha_get_history` only to find *when* it froze |

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
