# Home Assistant Configuration Management Toolkit

A toolkit for managing Home Assistant configurations — automated validation, safe deployment, round-trip YAML editing, and entity discovery. Designed to work alongside AI coding assistants, but fully usable standalone.

## ✨ Features

- 🛡️ **Multi-Layer Validation** — YAML syntax, entity references, and official HA `check_config` — runs before any push
- ✏️ **Safe YAML Editing** — `ha_cli edit` preserves comments, formatting, and key ordering (ruamel.yaml round-trip)
- ⚡ **Validator Caching** — SHA256-based caching skips re-validation when files haven't changed
- 🚀 **Safe Deployments** — `make push` validates first, blocks invalid configs from reaching HA
- 🔍 **Entity Discovery** — Search and explore entities by name, domain, area, or state
- 🤖 **AI Assistant Ready** — MCP server integration, instruction files, and pre-built skills for AI coding assistants
- 📦 **Importable Python Modules** — `HAClient`, `YAMLEditor`, and validators for scripts and tests
- 💾 **Backup System** — Timestamped config backups with changelogs and full-text search

## 🚀 Quick Start

### 📥 1. Clone and Set Up
```bash
git clone git@github.com:stephenwong/claude-homeassistant.git
cd claude-homeassistant
make setup  # Installs dependencies via uv
```

### ⚙️ 2. Configure Connection
```bash
cp .env.example .env
# Edit .env with your actual Home Assistant details
```

The `.env` file should contain:
```bash
# Home Assistant API
HA_TOKEN=your_home_assistant_token
HA_URL=http://your_homeassistant_host:8123

# MCP Server (for AI assistant integration)
HA_MCP_URL=http://your_homeassistant_ip:9583/private_your_token_here

# SSH Configuration for rsync operations
HA_HOST=your_homeassistant_host
HA_REMOTE_PATH=/config/

# Local Configuration (optional — defaults provided)
LOCAL_CONFIG_PATH=config/
BACKUP_DIR=backups
```

### 🔑 3. Set Up SSH Access

Install the [Advanced SSH & Web Terminal](https://github.com/hassio-addons/addon-ssh) add-on for Home Assistant, which provides SSH/SFTP access needed for rsync operations.

<details>
<summary><strong>Click to expand SSH setup instructions</strong></summary>

##### Generate SSH Key Pair (if you don't have one)
```bash
ssh-keygen -t ed25519 -f ~/.ssh/homeassistant -C "your-email@example.com"
```

##### Configure Advanced SSH & Web Terminal Add-on

1. Install the add-on in Home Assistant
2. Configure with your public key:
```yaml
username: root
password: ""
authorized_keys:
  - >-
    ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... your-email@example.com
sftp: true
compatibility_mode: false
allow_agent_forwarding: false
allow_remote_port_forwarding: false
allow_tcp_forwarding: false
```
3. Start the add-on

##### Configure SSH Client

Create or edit `~/.ssh/config`:
```
Host homeassistant
  HostName homeassistant.local
  User root
  IdentityFile ~/.ssh/homeassistant
  StrictHostKeyChecking no
```

##### Test Connection
```bash
ssh homeassistant
```

</details>

### 🎫 4. Get Your Home Assistant Token

1. Home Assistant → Settings → People → Your Profile
2. Scroll to "Long-lived access tokens" → Create Token
3. Copy the token into `.env` as `HA_TOKEN`

### ⬇️ 5. Pull Your Configuration
```bash
make pull  # Downloads your actual HA config
```

### 🛠️ 6. Work with Your Configuration

Edit configs locally with full validation, push back when ready:
```bash
make push  # Validates then uploads to HA
```

## 📁 Project Structure

```
├── config/                      # Home Assistant configuration
│   ├── configuration.yaml
│   ├── automations.yaml         # Primary file for automation work
│   ├── scripts.yaml
│   ├── scripts/                 # Shell helper scripts
│   ├── blueprints/              # HA blueprints (automation/, script/, template/)
│   └── .storage/                # Entity registry (read-only reference)
├── frigate/                     # Frigate NVR configuration
├── tools/                       # Validation and management scripts
│   ├── ha_cli.py                # Single CLI entry point
│   ├── commands/                # CLI subcommands (validate, reload, entities, curl, edit)
│   ├── ha/                      # Shared modules
│   │   ├── client.py            # HAClient — REST API client
│   │   └── yaml_editor.py       # YAMLEditor — round-trip YAML editing
│   ├── validators/              # Validator implementations (yaml, references, ha_official)
│   ├── cache.py                 # SHA256 file-hash caching
│   ├── common.py                # Shared utilities
│   ├── generate_changelog.py    # Backup changelog generation
│   ├── search_backups.py        # Full-text search across backups
│   ├── prune_backups.py         # Smart backup retention pruning
│   └── ha-curl.sh               # Curl wrapper with auto-auth
├── tests/                       # Unit tests (pytest)
├── backups/                     # Timestamped config backups with changelogs
├── CLAUDE.md                    # AI assistant instructions (also AGENTS.md, GEMINI.md symlinks)
├── opencode.json                # Example MCP server configuration for opencode
├── .env.example                 # Environment configuration template
├── Makefile                     # Management commands (pull, push, validate, etc.)
├── Makefile.dev                 # Development-specific commands
└── pyproject.toml               # Python project configuration
```

## 🛠️ Commands

### 🎮 Primary CLI (`ha_cli`)
```bash
# Validation
uv run python tools/ha_cli.py validate              # Run all validators
uv run python tools/ha_cli.py validate --force      # Force re-run (skip cache)
uv run python tools/ha_cli.py validate --quiet      # Suppress success output

# YAML Editing
uv run python tools/ha_cli.py edit automations                 # List all automations
uv run python tools/ha_cli.py edit automations "Name"          # Show one automation
uv run python tools/ha_cli.py edit automations --add '{"alias":"...","trigger":[],"action":[]}'
uv run python tools/ha_cli.py edit automations "Name" --set mode=single icon=mdi:shield
uv run python tools/ha_cli.py edit automations "Name" --remove

# Entity Discovery
uv run python tools/ha_cli.py entities                        # Entity summary
uv run python tools/ha_cli.py entities --json                 # Compact JSON output
uv run python tools/ha_cli.py entities --domain light --json
uv run python tools/ha_cli.py entities --search motion

# API Calls
uv run python tools/ha_cli.py curl /api/states
uv run python tools/ha_cli.py curl /api/states --filter '. | length'
uv run python tools/ha_cli.py curl /api/services/light/turn_on --post --data '{"entity_id":"light.kitchen"}'

# Reload
uv run python tools/ha_cli.py reload
```

### 🏗️ Make Targets

| Command | Purpose |
|---------|---------|
| `make pull` | Sync config from HA (includes Z2M and Frigate configs) |
| `make push` | Push config (validates first, then rsyncs) |
| `make validate` | Run all validation tests |
| `make backup` | Create timestamped backup (with auto-changelog) |
| `make setup` | Install Python dependencies via uv |
| `make status` | Show config status and entity counts |
| `make reload` | Reload HA config via API (no push) |
| `make entities` | Explore entities (pass `ARGS='--search TERM'`) |
| `make lint` | Run ruff format check + lint |
| `make lint-fix` | Auto-fix ruff format and lint issues |
| `make backup-search PATTERN='text'` | Search all backups for a pattern |
| `make changelog BACKUP='path'` | Generate changelog for a backup |
| `make test-ssh` | Test SSH connection to HA |
| `make clean` | Remove temp files and caches |

## ✏️ YAML Editing (`ha_cli edit`)

**Prefer `ha_cli edit` over manual YAML editing** — it uses `ruamel.yaml` for round-trip editing that preserves comments, formatting, and key ordering. Operates on `automations.yaml` (list) and `scripts.yaml` (dict).

```bash
# List all automation aliases
uv run python tools/ha_cli.py edit automations

# Show a specific automation
uv run python tools/ha_cli.py edit automations "Turn on Alarm"

# Add a new automation
uv run python tools/ha_cli.py edit automations --add '{"alias":"New Automation","trigger":[],"action":[]}'

# Update fields on an existing automation
uv run python tools/ha_cli.py edit automations "Turn on Alarm" --set mode=single icon=mdi:shield

# Remove an automation
uv run python tools/ha_cli.py edit automations "Old Automation" --remove
```

Programmatic editing is also available:
```python
from tools.ha.yaml_editor import YAMLEditor
editor = YAMLEditor("config")
editor.add_automation({"alias": "...", "trigger": [...], "action": [...]})
```

## 🛡️ Validation System

Three layers run on every `make validate` (and before every `make push`):

### 📝 1. YAML Syntax
Validates YAML syntax with HA-specific tags (`!include`, `!secret`, `!input`), file encoding, and basic HA file structures.

### 🔗 2. Entity References
Verifies all entity references exist in your HA instance. Checks device and area references, warns about disabled entities, extracts entities from Jinja2 templates, and recognizes config-defined entities.

### 🏛️ 3. Official HA Validation
Uses Home Assistant's own `check_config`. **"Successful config (partial)"** is the normal local result — some integration packages can't install locally due to version pin differences, but this is expected and doesn't indicate a real config problem.

### ⚡ Validator Caching

Validators cache results in `config/.cache/validators/` keyed by SHA256 of dependent files. Unchanged files return cached results instantly.

- **Automatic:** Caching is transparent — no action needed
- **Force refresh:** `ha_cli validate --force` re-runs all validators
- **Only successful results cached:** Failures always re-run
- **Clear cache:** Delete `config/.cache/validators/` (or `git clean -fdX config/.cache/`)

## 📦 Importable Modules

For Python scripts and tests, import from the package directly:

```python
from tools.ha.client import HAClient              # REST API client
from tools.ha.yaml_editor import YAMLEditor        # Round-trip YAML editing
from tools.validators.yaml import YAMLValidator
from tools.validators.references import ReferenceValidator
from tools.validators.ha_official import HAOfficialValidator
```

`HAClient` is constructed via `HAClient.from_env()` (reads `.env` for `HA_TOKEN`/`HA_URL`).

## 🤖 AI Assistant Integration

This toolkit is designed to work with AI coding assistants. Three components enable this:

### 🔌 MCP Server (ha-mcp)

The [ha-mcp](https://github.com/homeassistant-ai/ha-mcp) add-on provides 88+ MCP tools for natural-language HA control — entity listing, service calls, history, config inspection, automation creation, and more.

**Setup:**
1. Install the "Home Assistant MCP Server" add-on
2. Start it and copy the MCP URL from add-on logs (format: `http://<ip>:9583/private_<token>`)
3. Set `HA_MCP_URL` in `.env`
4. Configure your AI tool's MCP settings to point to this URL

Compatible with any AI coding assistant that supports MCP (opencode, Claude Code, etc.).

### 📋 Instruction Files

`CLAUDE.md` provides comprehensive project context to AI assistants — entity naming conventions, critical gotchas, hardware details, integration info, and troubleshooting tips. `AGENTS.md` and `GEMINI.md` are symlinks so other AI tools read the same instructions.

### 🧩 Skills

Pre-built skill workflows in `.agents/skills/` guide AI assistants through common tasks:

| Skill | Purpose |
|-------|---------|
| **home-assistant-automation** | Structured workflow for creating and modifying automations |
| **home-assistant-backup** | Pull → backup → prune with smart retention |
| **home-assistant-debugging** | Systematic approach to investigating HA issues |
| **reflect** | Capture learnings after completing work to prevent recurrence |

### 📡 HA API Access Tiers

| Need | Tool |
|------|------|
| **Live HA interaction** (read entities, call services) | MCP tools (ha-mcp) |
| **Scripted API calls** | `ha_cli curl` or `tools/ha-curl.sh` |
| **Importable client** | `HAClient` (`from tools.ha.client import HAClient`) |

## 🏷️ Entity Naming Convention

Format: `location_room_device_sensor`
- **location**: `home`, `office`, `cabin`
- **room**: `basement`, `kitchen`, `driveway`
- **device**: `motion`, `heatpump`, `lock`
- **sensor**: `battery`, `temperature`, `status`

Examples: `binary_sensor.home_basement_motion_battery`, `climate.office_living_room_thermostat`

## 🔒 Security

- 🔐 **Secrets Management**: `secrets.yaml` is excluded from validation
- 🔑 **SSH Authentication**: Uses SSH keys for secure HA access
- 🕵️ **No Credentials Stored**: Repository contains no sensitive data
- 🛡️ **Pre-Push Validation**: Prevents broken configs from reaching HA
- 💾 **Backup System**: Automatic timestamped backups before changes

## 🔧 Troubleshooting

### ❌ Validation Errors
1. Check YAML syntax: `uv run python tools/ha_cli.py validate`
2. View HA logs: `ssh homeassistant "ha core logs" | tail -100`

### 🔌 SSH Connection Issues
```bash
# Test connection
ssh homeassistant

# Check key permissions
chmod 600 ~/.ssh/homeassistant

# Test with verbose output
ssh -v homeassistant
```

### 📦 Missing Dependencies
```bash
uv sync
```

### ✅ Before Pushing Code
```bash
make lint        # Check formatting and lint
make lint-fix    # Auto-fix issues
```

## 📄 License

Apache 2.0

## 🙏 Acknowledgments

- [Home Assistant](https://home-assistant.io) for the amazing platform
- [philippb/claude-homeassistant](https://github.com/philippb/claude-homeassistant) — the original project this fork builds upon
- The HA community for validation best practices
