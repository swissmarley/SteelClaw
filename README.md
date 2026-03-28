# SteelClaw

Self-hosted personal AI assistant that runs locally on your machine. Connects to any LLM (Claude, OpenAI, DeepSeek), communicates across 10+ messaging platforms, executes commands securely, and learns through a modular skill system.

## Quick Start

### 1. Install

```bash
git clone https://github.com/swissmarley/SteelClaw.git
cd SteelClaw
bash install.sh
# or manually:
pip install -e ".[all]"
```

### 2. Configure

**Option A — Interactive onboarding wizard (recommended):**

```bash
steelclaw onboard
# or
python -m steelclaw onboard
```

The wizard uses arrow-key selection for provider, model, connector, memory backend, permission tier, and temperature presets. It shows a confirmation summary before writing `config.json`.

**Option B — Manual configuration:**

```bash
cp config.example.json config.json
```

Edit `config.json` and set your LLM API key:

```json
{
  "agents": {
    "llm": {
      "default_model": "claude-sonnet-4-20250514",
      "api_key": "sk-ant-..."
    }
  }
}
```

Or use environment variables:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export OPENAI_API_KEY="sk-..."
```

### 3. Run

**Start the server (foreground):**

```bash
steelclaw serve
```

**Start as background daemon:**

```bash
steelclaw start
steelclaw status    # check if running
steelclaw stop      # stop the daemon
steelclaw restart   # restart
steelclaw logs -f   # follow logs
```

**Open the Control UI dashboard:**

Navigate to [http://localhost:8000/](http://localhost:8000/) in your browser. The dashboard includes chat, settings, sessions, agents, persona, analytics, connectors, skills, security, and scheduler pages.

**Or chat from the terminal (TUI):**

```bash
steelclaw chat
```

The TUI chat uses Rich for styled panels, Markdown rendering, and a spinner while the assistant is thinking. Commands: `/help`, `/clear`, `/status`, `/history`, `/quit`.

## CLI Commands

| Command | Description |
|---------|-------------|
| `steelclaw serve` | Start the API server (foreground) |
| `steelclaw start` | Start as background daemon |
| `steelclaw stop` | Stop the daemon |
| `steelclaw restart` | Restart the daemon |
| `steelclaw status` | Show daemon status |
| `steelclaw chat` | Interactive TUI chat |
| `steelclaw onboard` | Interactive onboarding wizard |
| `steelclaw setup` | Alias for `onboard` |
| `steelclaw sessions list\|reset\|delete` | Manage sessions |
| `steelclaw agents list\|add\|delete\|status` | Manage agents |
| `steelclaw skills list\|install\|enable\|disable\|configure` | Manage skills |
| `steelclaw memory status\|search\|clear` | Manage persistent memory |
| `steelclaw persona` | Configure agent persona interactively |
| `steelclaw logs [-f] [--gateway] [--app]` | View daemon logs |
| `steelclaw migrate` | Run database migrations |
| `steelclaw gateway start\|stop\|restart` | Manage gateway connectors |
| `steelclaw app start\|stop\|restart` | Manage app components |

## Access Methods

| Method | How to Access | Description |
|--------|--------------|-------------|
| **Control UI** | `http://localhost:8000/` | Full dashboard with chat, settings, sessions, agents, persona, analytics |
| **TUI Chat** | `steelclaw chat` | Rich-powered interactive terminal client |
| **Onboarding** | `steelclaw onboard` | Arrow-key guided setup wizard |
| **REST API** | `http://localhost:8000/docs` | Full Swagger/OpenAPI docs |
| **WebSocket** | `ws://localhost:8000/gateway/ws` | Programmatic WebSocket access |

## LLM Providers

SteelClaw supports any provider via [LiteLLM](https://docs.litellm.ai/docs/providers). The onboarding wizard offers grouped model selection:

| Provider | Models | API Key Env Var |
|----------|--------|-----------------|
| Anthropic (Claude) | Claude Sonnet/Opus 4.5/4.6, Haiku 4.5 | `ANTHROPIC_API_KEY` |
| OpenAI | GPT-5, GPT-5 Mini, GPT-4.1, o3/o4-mini | `OPENAI_API_KEY` |
| Google Gemini | Gemini Pro 3.1, Flash 3.0 | `GEMINI_API_KEY` |
| DeepSeek | `deepseek/deepseek-chat` | `DEEPSEEK_API_KEY` |
| Ollama (local) | `ollama/llama3` | None (runs locally) |
| Any LiteLLM provider | See [docs](https://docs.litellm.ai/docs/providers) | Varies |

Multiple provider keys can be set at once:

```json
{
  "agents": {
    "llm": {
      "default_model": "claude-sonnet-4-20250514",
      "provider_keys": {
        "anthropic": "sk-ant-...",
        "openai": "sk-..."
      }
    }
  }
}
```

## Messaging Platforms

Connect SteelClaw to your messaging apps by enabling connectors in `config.json`:

| Platform | Status | Config Key |
|----------|--------|-----------|
| WebSocket (built-in) | Ready | Always active |
| Telegram | Ready | `gateway.connectors.telegram` |
| Discord | Ready | `gateway.connectors.discord` |
| Slack | Stub | `gateway.connectors.slack` |
| WhatsApp | Stub | `gateway.connectors.whatsapp` |
| Signal | Stub | `gateway.connectors.signal` |
| iMessage | Stub | `gateway.connectors.imessage` |
| Mattermost | Stub | `gateway.connectors.mattermost` |
| Matrix | Stub | `gateway.connectors.matrix` |
| Microsoft Teams | Stub | `gateway.connectors.teams` |

Example — enable Telegram:

```json
{
  "gateway": {
    "connectors": {
      "telegram": {
        "enabled": true,
        "token": "123456:ABC-DEF..."
      }
    }
  }
}
```

### Session Behaviour

- **DMs** across all platforms are unified into a single conversation per user
- **Group chats** are isolated per group — SteelClaw only responds when @mentioned or triggered by keyword
- **Allowlist** controls who can DM the bot (enable/disable in config)
- **Session lifecycle** — sessions transition through `active` → `idle` → `closed` with configurable timeouts
- **Heartbeat** — background job auto-detects idle and stale sessions

## Agent Personality & Multi-Agent

### Persona System

Configure how SteelClaw communicates — agent name, user's name, tone, style, and goals:

```bash
steelclaw persona
```

Or configure via the dashboard Persona page. Persona settings are injected into the system prompt for consistent behavior.

### Multi-Agent Support

Create secondary agents with independent models, temperatures, system prompts, and memory namespaces:

```bash
steelclaw agents add --name researcher --model gpt-4o
steelclaw agents list
steelclaw agents delete researcher
```

Each agent gets an isolated memory namespace in ChromaDB. The main agent is auto-created on first startup.

## Persistent Memory

SteelClaw remembers past conversations using ChromaDB vector embeddings:

```bash
# Install with memory support
pip install -e ".[memory]"

# Check memory status
steelclaw memory status

# Search past conversations
steelclaw memory search "what we discussed about deployment"

# Clear memory
steelclaw memory clear
```

- Relevant past exchanges are retrieved and injected into the system prompt
- Memory is isolated per agent namespace
- Gracefully degrades if ChromaDB is not installed

## Usage Analytics

The dashboard Analytics page provides:

- **Summary cards** — total tokens, cost, active sessions, messages
- **Time-series charts** — tokens and cost over time (day/hour granularity)
- **Model breakdown** — usage by model (doughnut chart)
- **Agent breakdown** — usage by agent (bar chart)
- **Session histogram** — message distribution across sessions
- **CSV export** — download raw data for any date range

Token usage and cost are tracked across all tool-calling rounds in the agent pipeline.

### Analytics API

```bash
curl http://localhost:8000/api/analytics/summary
curl http://localhost:8000/api/analytics/usage-over-time?granularity=day
curl http://localhost:8000/api/analytics/by-model
curl http://localhost:8000/api/analytics/export?format=csv
```

## Skills

Skills are modular capabilities loaded from directories. Each skill has a `SKILL.md` file defining metadata, tools, and a system prompt.

### Bundled Skills

| Skill | Tools | Description |
|-------|-------|-------------|
| Calculator | `evaluate`, `convert_units` | Math evaluation and unit conversion |
| File Manager | `read_file`, `write_file`, `list_directory` | File system operations |
| Shell | `execute` | Sandboxed command execution |
| System Info | `cpu_info`, `memory_info`, `disk_info` | System monitoring |
| Notes | `create_note`, `list_notes`, `search_notes`, `delete_note` | Note management |
| Reminder | `set_reminder`, `list_reminders`, `cancel_reminder` | Reminders |
| Web Search | `search`, `fetch_url` | Web search and page fetching |
| Cron Manager | `schedule_task`, `list_scheduled`, `cancel_task` | Scheduled task management |
| n8n Integration | `trigger_webhook`, `list_workflows`, `execute_workflow` | n8n workflow automation |
| WordPress | `create_post`, `list_posts`, `upload_media` | WordPress content management |
| Browser | `browse_url`, `screenshot`, `extract_text` | Playwright-based web browsing |

### Skill Management

```bash
steelclaw skills list                    # List all skills
steelclaw skills install ./my-skill      # Install from directory
steelclaw skills enable my-skill         # Enable a disabled skill
steelclaw skills disable my-skill        # Disable a skill
steelclaw skills configure my-skill      # Set skill credentials
```

### Skill Scoping (priority order)

1. **Workspace** (`.steelclaw/skills/`) — project-specific, highest priority
2. **Global** (`~/.steelclaw/skills/`) — user-wide
3. **Bundled** (`steelclaw/skills/bundled/`) — ships with SteelClaw

### Creating a Skill

```
my-skill/
  SKILL.md
  __init__.py    # optional: Python tool executors
```

**SKILL.md format:**

```markdown
# My Skill

Description of what this skill does.

## Metadata
- version: 1.0.0
- author: Your Name
- triggers: keyword1, keyword2

## System Prompt
Instructions for the LLM when this skill is active.

## Tools

### my_tool
Description of the tool.

**Parameters:**
- `param1` (string, required): What this parameter does
- `param2` (integer): Optional parameter
```

**`__init__.py` — register tool executors:**

```python
async def tool_my_tool(param1: str, param2: int = 10) -> str:
    # Functions prefixed with tool_ are auto-discovered
    return f"Result: {param1}, {param2}"
```

## Security Model

### Command Approvals

When SteelClaw wants to run a shell command, the three-tier permission system decides:

| Tier | Behaviour |
|------|-----------|
| `ask` | Prompt the user for approval (default) |
| `record` | Log the command but allow execution |
| `ignore` | Auto-allow silently |

Approvals are persisted in `exec-approvals.json` with glob pattern support:

```json
{
  "version": 1,
  "rules": [
    {"pattern": "git *", "permission": "ignore", "note": "All git commands"},
    {"pattern": "ls *", "permission": "ignore", "note": "Directory listings"},
    {"pattern": "docker *", "permission": "record", "note": "Log docker usage"}
  ]
}
```

### Blocked Commands

Dangerous commands are always blocked regardless of approval rules. Configure in `config.json`:

```json
{
  "agents": {
    "security": {
      "blocked_commands": ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"]
    }
  }
}
```

## Scheduler

Proactive task execution with cron jobs and reminders:

```bash
# List scheduled jobs
curl http://localhost:8000/api/scheduler/jobs

# Check scheduler status
curl http://localhost:8000/api/scheduler/status
```

Jobs can be programmatically added via the Python API or through LLM tool calls.

## REST API

Full interactive API docs at [http://localhost:8000/docs](http://localhost:8000/docs).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/info` | GET | Server info + connector status |
| `/` | GET | Control UI dashboard |
| `/gateway/ws` | WS | WebSocket chat |
| `/gateway/webhook/{platform}` | POST | Platform webhooks |
| `/api/config` | GET/PUT | Full configuration (secrets masked) |
| `/api/config/llm` | GET/PUT | LLM provider settings |
| `/api/config/gateway` | GET/PUT | Gateway settings |
| `/api/config/security` | GET/PUT | Security settings |
| `/api/config/connectors` | GET | Connector config + live status |
| `/api/config/approvals` | GET/POST | Approval rules management |
| `/api/sessions` | GET | List sessions (filter by `?status=`) |
| `/api/sessions/{id}/status` | PATCH | Update session status |
| `/api/sessions/{id}/reset` | POST | Reset session (clear messages) |
| `/api/sessions/{id}` | DELETE | Delete session permanently |
| `/api/history/{session_id}` | GET | Message history |
| `/api/agents` | GET/POST | List/create agents |
| `/api/agents/{id}` | GET/PUT/DELETE | Agent CRUD |
| `/api/agents/{id}/persona` | PUT | Update agent persona |
| `/api/analytics/summary` | GET | Token/cost/session totals |
| `/api/analytics/usage-over-time` | GET | Time-series usage data |
| `/api/analytics/by-model` | GET | Usage grouped by model |
| `/api/analytics/by-agent` | GET | Usage grouped by agent |
| `/api/analytics/export` | GET | CSV export |
| `/api/skills` | GET | List skills |
| `/api/skills/reload` | POST | Hot-reload skills |
| `/api/scheduler/jobs` | GET | List scheduled jobs |
| `/api/scheduler/status` | GET | Scheduler engine status |

## Database & Migrations

SteelClaw uses SQLite with async SQLAlchemy (aiosqlite). Schema updates are applied automatically on startup.

To run migrations manually:

```bash
steelclaw migrate
```

### Models

| Table | Description |
|-------|-------------|
| `sessions` | Chat sessions with status lifecycle (active/idle/closed) |
| `messages` | Messages with token usage and cost tracking |
| `users` | User accounts |
| `platform_identities` | Platform-specific user identities |
| `agents` | Agent profiles (main + secondary agents) |
| `user_facts` | Extracted user facts for personalization |
| `memory_entries` | Memory metadata (vector data in ChromaDB) |
| `allowlist` | DM allowlist entries |

## Project Structure

```
steelclaw/
  __main__.py         CLI entry point (full subcommand tree)
  app.py              FastAPI app factory + lifespan
  settings.py         Pydantic configuration
  pricing.py          Model pricing constants
  session_heartbeat.py Session idle/close detection
  cli/
    chat.py           Rich TUI chat client
    setup.py          Interactive onboarding wizard (questionary)
    daemon.py         Background daemon management
    logs.py           Log viewer
    sessions.py       Session management CLI
    memory.py         Memory management CLI
    agents.py         Agent management CLI
    skills_cmd.py     Skill management CLI
    persona.py        Persona configuration wizard
    gateway_cmd.py    Gateway connector control
    app_cmd.py        App component management
  web/static/         Control UI dashboard (HTML/JS/CSS)
  db/
    engine.py         Async SQLAlchemy engine + auto-migration
    models.py         SQLModel table definitions
    migrations/       Alembic migrations
  llm/
    provider.py       LiteLLM multi-provider wrapper
    context.py        Context builder (persona + memory + history)
  memory/
    vector_store.py   ChromaDB wrapper (optional)
    retrieval.py      Semantic memory retrieval
    ingestion.py      Memory ingestion pipeline
  skills/
    loader.py         SKILL.md parser
    registry.py       Skill registry + tool routing
    credential_store.py Skill credential management
    bundled/          Built-in skills
  security/           Approvals, permissions, sandbox
  scheduler/          APScheduler background tasks
  agents/
    router.py         LLM agent loop with tool calling
    persona.py        Persona prompt builder
  gateway/            Messaging platform connectors
  api/                REST API endpoints
```

## Configuration Reference

All settings can be set in `config.json` or via environment variables with prefix `STEELCLAW_` and `__` for nesting:

```bash
# Examples:
STEELCLAW_AGENTS__LLM__DEFAULT_MODEL=claude-sonnet-4-20250514
STEELCLAW_SERVER__PORT=9000
STEELCLAW_GATEWAY__DM_ALLOWLIST_ENABLED=false
```

## License

MIT
