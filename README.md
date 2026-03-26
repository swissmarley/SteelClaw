# SteelClaw

Self-hosted personal AI assistant that runs locally on your machine. Connects to any LLM (Claude, OpenAI, DeepSeek), communicates across 10+ messaging platforms, executes commands securely, and learns through a modular skill system.

## Quick Start

### 1. Install

```bash
git clone https://github.com/swissmarley/SteelClaw.git
cd SteelClaw
pip install -e ".[dev]"
```

### 2. Configure

**Option A — Interactive setup wizard (recommended):**

```bash
steelclaw setup
# or
python -m steelclaw setup
```

The wizard walks you through LLM provider selection, server settings, messaging platforms, security, and optional features. It writes `config.json` for you.

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

**Start the server:**

```bash
steelclaw serve
# or
python -m steelclaw serve
```

**Open the Control UI dashboard:**

Navigate to [http://localhost:8000/](http://localhost:8000/) in your browser. The dashboard includes chat, settings management, connector status, skills, sessions, security, and scheduler pages — all in one interface.

**Or chat from the terminal (TUI):**

```bash
# In a second terminal:
steelclaw chat
```

The TUI chat uses Rich for styled panels, Markdown rendering, and a spinner while the assistant is thinking. Commands: `/help`, `/clear`, `/status`, `/history`, `/quit`.

## Access Methods

| Method | How to Access | Description |
|--------|--------------|-------------|
| **Control UI** | `http://localhost:8000/` | Full dashboard with chat, settings, connectors, skills, sessions, security, scheduler |
| **TUI Chat** | `steelclaw chat` | Rich-powered interactive terminal client |
| **Setup Wizard** | `steelclaw setup` | Interactive onboarding for first-time configuration |
| **REST API** | `http://localhost:8000/docs` | Full Swagger/OpenAPI docs |
| **WebSocket** | `ws://localhost:8000/gateway/ws` | Programmatic WebSocket access |

## LLM Providers

SteelClaw supports any provider via [LiteLLM](https://docs.litellm.ai/docs/providers). Set the model in `config.json`:

| Provider | Model Example | API Key Env Var |
|----------|--------------|-----------------|
| Anthropic (Claude) | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-4o` | `OPENAI_API_KEY` |
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

## Skills

Skills are modular capabilities loaded from directories. Each skill has a `SKILL.md` file defining metadata, tools, and a system prompt.

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

### Managing Skills via API

```bash
# List loaded skills
curl http://localhost:8000/api/skills

# Reload skills (hot-reload after changes)
curl -X POST http://localhost:8000/api/skills/reload

# Get skill details
curl http://localhost:8000/api/skills/shell
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
| `/chat` | GET | Web chat UI (redirects to dashboard) |
| `/gateway/ws` | WS | WebSocket chat |
| `/gateway/webhook/{platform}` | POST | Platform webhooks |
| `/api/config` | GET/PUT | Full configuration (secrets masked) |
| `/api/config/llm` | GET/PUT | LLM provider settings |
| `/api/config/gateway` | GET/PUT | Gateway settings |
| `/api/config/security` | GET/PUT | Security settings |
| `/api/config/server` | GET/PUT | Server settings |
| `/api/config/connectors` | GET | Connector config + live status |
| `/api/config/approvals` | GET/POST | Approval rules management |
| `/api/config/approvals/{pattern}` | DELETE | Remove an approval rule |
| `/api/sessions` | GET | List sessions |
| `/api/history/{session_id}` | GET | Message history |
| `/api/skills` | GET | List skills |
| `/api/skills/reload` | POST | Hot-reload skills |
| `/api/scheduler/jobs` | GET | List scheduled jobs |
| `/api/scheduler/status` | GET | Scheduler engine status |

## Project Structure

```
steelclaw/
  __main__.py         CLI entry point (serve / chat / setup)
  app.py              FastAPI app factory + lifespan
  settings.py         Pydantic configuration
  cli/
    chat.py           Rich TUI chat client
    setup.py          Interactive onboarding wizard
  web/static/         Control UI dashboard (HTML/JS/CSS)
  db/                 SQLite database (SQLAlchemy async)
  llm/                LLM provider abstraction (LiteLLM)
  skills/             Skill system (parser, loader, registry)
  security/           Approvals, permissions, sandbox
  scheduler/          APScheduler background tasks
  voice/              Whisper transcription + TTS
  gateway/            Messaging platform connectors
  agents/             LLM-powered agent with tool calling
  api/                REST API + config management endpoints
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
