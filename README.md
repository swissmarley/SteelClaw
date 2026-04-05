# SteelClaw

Self-hosted personal AI assistant that runs locally on your machine. Connects to any LLM (Claude, OpenAI, DeepSeek), communicates across 10+ messaging platforms, executes commands securely, and learns through a modular skill system with 60+ bundled integrations.

**Key highlights:** Premium glassmorphism UI, streaming LLM responses with real-time token display, voice chat with streaming TTS, file upload in chat (images, PDFs, audio), 60+ skill integrations with credential management, real-time web search, persistent memory, multi-agent support, usage analytics, and a scheduler for proactive tasks.

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

SteelClaw resolves all paths relative to its installation directory, so you can run `python3 -m steelclaw start` from any working directory.

**Open the Control UI dashboard:**

Navigate to [http://localhost:8000/](http://localhost:8000/) in your browser. The dashboard features a premium glassmorphism design with 10 pages: Chat, Settings, Sessions, Agents, Persona, Analytics, Connectors, Skills, Security, and Scheduler.

**Or chat from the terminal (TUI):**

```bash
steelclaw chat
```

The TUI chat supports streaming responses — text appears token-by-token as the LLM generates it, with live tool-call status indicators. Uses Rich for styled panels and Markdown rendering. Commands: `/help`, `/clear`, `/status`, `/history`, `/quit`.

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
| **Control UI** | `http://localhost:8000/` | Glassmorphism dashboard with streaming chat, voice, settings, skills, analytics |
| **Voice Chat** | Dashboard microphone button | Streaming voice conversation with animated waveform |
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
| Slack | Ready | `gateway.connectors.slack` |
| WhatsApp | Ready | `gateway.connectors.whatsapp` |
| Signal | Ready | `gateway.connectors.signal` |
| iMessage | Ready | `gateway.connectors.imessage` |
| Mattermost | Ready | `gateway.connectors.mattermost` |
| Matrix | Ready | `gateway.connectors.matrix` |
| Microsoft Teams | Ready | `gateway.connectors.teams` |

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

## Voice Chat

SteelClaw supports real-time voice interaction via the OpenAI Realtime API over WebRTC — direct browser-to-OpenAI connection with sub-2-second latency and true interruption support (like ChatGPT Voice).

- **WebRTC peer connection** — browser connects directly to OpenAI's Realtime API without server audio relay
- **Sub-2-second latency** — real-time speech-to-text, LLM response, and text-to-speech pipeline
- **Interruption support** — speak at any time during agent response to naturally interrupt and redirect conversation
- **Server-side VAD** — voice activity detection and silence thresholds for automatic turn-taking
- **Full-screen overlay UI** — animated visual state (IDLE → CONNECTING → LISTENING → AGENT_SPEAKING → INTERRUPTED) with animated orb, rings, and waveform
- **Voice selection** — choose from 6 voice options (alloy, echo, fable, onyx, nova, shimmer) via integrated chip selector
- **Configurable realtime settings** — VAD threshold, silence duration, prefix audio padding for natural conversation flow

**How to use:**
1. Click the microphone button (🎧) in the chat header to start
2. Speak naturally — your voice is streamed and processed in real-time
3. Agent responds with voice — you can interrupt at any time by speaking
4. Click the microphone button again or press Escape to stop

**Configuration:** Set your OpenAI API key in Settings > Voice/Audio, then enable voice. The system uses OpenAI's `gpt-4o-realtime-preview` model by default, fully configurable.

**Advanced settings (Settings > Voice/Audio):**
- Realtime model selection (defaults to `gpt-4o-realtime-preview`)
- VAD threshold (0.0-1.0, default 0.5)
- Silence timeout in milliseconds (default 600ms)
- Prefix padding for audio continuity (default 300ms)

## Streaming Responses

SteelClaw streams LLM responses in real time across all interfaces:

- **Web UI** — tokens appear character-by-character via WebSocket with a typing indicator and live tool-call status
- **TUI chat** — Rich live display updates as tokens arrive, with tool execution progress
- **WebSocket API** — structured streaming events (`chunk`, `tool_start`, `tool_end`, `done`, `error`) for programmatic clients

Streaming is used by default for all new conversations. Token usage and model metadata are captured from the streaming response for accurate analytics and billing.

## File Uploads in Chat

Attach files directly in the chat to have SteelClaw analyze their content:

- **Images** (JPEG, PNG, GIF, WebP) — sent as inline vision to the LLM for visual analysis
- **Documents** (PDF, TXT, CSV, JSON, Markdown, HTML, XML) — text extracted and included in the message context
- **Audio** (MP3, WAV, WebM, OGG) — automatically transcribed via the voice system and included as text

**How to attach files:**
- Click the paperclip button next to the text input
- Drag and drop files onto the chat area
- Paste images from your clipboard (Ctrl/Cmd+V)

Files are uploaded to the server, processed, and sent alongside your message. Attachment previews appear above the input before sending, and image thumbnails are displayed inline in sent messages.

## Dashboard UI

The Control UI uses a premium glassmorphism design with:

- Semi-transparent frosted glass panels with `backdrop-filter: blur(20px)`
- Deep purple/blue gradient color scheme optimized for dark mode
- Animated sidebar with 10 navigation pages
- Command palette (Ctrl/Cmd+K) for quick actions
- Responsive layout with glass-effect cards and soft glow accents
- Tabbed settings page: Appearance, Voice/Audio, Agent, Skills, Gateway, Scheduler

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

Token usage and cost are tracked across all tool-calling rounds in both standard and streaming agent pipelines.

### Analytics API

```bash
curl http://localhost:8000/api/analytics/summary
curl http://localhost:8000/api/analytics/usage-over-time?granularity=day
curl http://localhost:8000/api/analytics/by-model
curl http://localhost:8000/api/analytics/export?format=csv
```

## Skills

Skills are modular capabilities loaded from directories. Each skill has a `SKILL.md` file defining metadata, tools, and a system prompt. SteelClaw ships with **61 bundled skills** covering productivity, development, communication, CRM, cloud storage, and more.

**Default behaviour:** Core skills (no credentials needed) are enabled out of the box. Integration skills that require API keys are disabled by default — enable them from the Skills page once you've configured their credentials. Enable/disable state persists across restarts. Tools from unconfigured skills are automatically hidden from the LLM, so the agent only uses tools it can actually call.

### Bundled Skills

**Core (no credentials needed):**

| Skill | Tools | Description |
|-------|-------|-------------|
| Calculator | `evaluate`, `convert_units` | Math evaluation and unit conversion |
| File Manager | `read_file`, `write_file`, `list_directory` | File system operations |
| Shell | `execute` | Sandboxed command execution |
| System Info | `cpu_info`, `memory_info`, `disk_info` | System monitoring |
| Notes | `create_note`, `list_notes`, `search_notes`, `delete_note` | Note management |
| Reminder | `set_reminder`, `list_reminders`, `cancel_reminder` | Reminders |
| Web Search | `search`, `fetch_url` | DuckDuckGo search and page fetching (default-enabled) |
| Cron Manager | `schedule_task`, `list_scheduled`, `cancel_task` | Scheduled task management |
| Browser | `browse_url`, `screenshot`, `extract_text` | Playwright-based web browsing |
| Code Runner | `run_code` | Execute code snippets |
| CSV Analyst | `analyze_csv` | CSV data analysis |
| PDF Reader | `read_pdf` | PDF text extraction |
| Screenshot | `take_screenshot` | Screen capture |
| Image Analyzer | `analyze_image` | Image description |
| File Organizer | `organize` | Smart file organization |
| Markdown Exporter | `export_markdown` | Convert to Markdown |
| Docker Manager | `docker_run`, `docker_list` | Docker container management |
| System Monitor | `monitor` | Extended system monitoring |
| Web Scraper | `scrape` | Structured web scraping |

**Integrations (API key required — configure via UI or CLI):**

| Category | Skills |
|----------|--------|
| **Communication** | Slack, Discord, Telegram, Twilio, SendGrid, Mailchimp |
| **Development** | GitHub, GitLab, Jira, Linear, n8n, Zapier, Make (Integromat) |
| **Productivity** | Notion, Trello, Airtable, Google Calendar, Outlook Calendar, Google Sheets |
| **Cloud Storage** | Google Drive, Dropbox, OneDrive, AWS S3, Supabase, Firebase |
| **CRM & Sales** | Salesforce, HubSpot, Pipedrive, Shopify, Stripe |
| **AI & Search** | OpenAI, Perplexity, Serper, ElevenLabs |
| **Social & Media** | Twitter/X, LinkedIn, Spotify, YouTube, NewsAPI |
| **CMS** | WordPress |
| **Translation** | Google Translate |
| **Weather** | OpenWeatherMap |

### Skill Credential Management

Configure API keys through the dashboard (Skills page > Configure button) or CLI:

```bash
steelclaw skills list                    # List all skills with credential status
steelclaw skills install ./my-skill      # Install from directory
steelclaw skills enable my-skill         # Enable a disabled skill
steelclaw skills disable my-skill        # Disable a skill
steelclaw skills configure my-skill      # Set skill credentials interactively
```

The dashboard credential modal shows each skill's required fields with secure input, saved-state indicators, and a Verify button that tests connectivity against the provider's API.

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

**`__init__.py` — register tool executors and declare credentials:**

```python
from steelclaw.skills.credential_store import get_all_credentials

# Credentials declared here appear in the dashboard Configure modal
required_credentials = [
    {"key": "api_key", "label": "My Service API Key", "type": "password"},
    {"key": "base_url", "label": "Service URL", "type": "text"},
]

# Set True to prevent users from disabling this skill
default_enabled = False

def _config():
    return get_all_credentials("my_skill")

async def tool_my_tool(param1: str, param2: int = 10) -> str:
    # Functions prefixed with tool_ are auto-discovered
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured."
    return f"Result: {param1}, {param2}"
```

**Note:** If `required_credentials` are declared but not configured by the user, the skill's tools are automatically hidden from the LLM. This prevents the agent from calling tools that would fail due to missing API keys.

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
| `/api/skills` | GET | List skills (with credential status) |
| `/api/skills/{name}/credentials` | GET/PUT | Read/write skill credentials |
| `/api/skills/{name}/verify` | POST | Test credential connectivity |
| `/api/skills/{name}/enable` | POST | Enable a skill |
| `/api/skills/{name}/disable` | POST | Disable a skill |
| `/api/skills/reload` | POST | Hot-reload all skills |
| `/api/persona` | GET/POST | Read/write persona config |
| `/api/files/upload` | POST | Upload file attachment for chat (images, docs, audio) |
| `/api/voice/transcribe` | POST | Speech-to-text (Whisper) |
| `/api/voice/synthesize` | POST | Text-to-speech (single response) |
| `/api/voice/synthesize-stream` | POST | Chunked TTS streaming |
| `/api/voice/realtime-session` | POST | Create ephemeral OpenAI Realtime API session token (WebRTC) |
| `/api/voice/status` | GET | Voice service status |
| `/api/config/voice` | GET/PUT | Voice settings |
| `/api/config/skills` | GET/PUT | Skill settings |
| `/api/config/scheduler` | GET/PUT | Scheduler settings |
| `/api/scheduler/jobs` | GET/DELETE | List/remove scheduled jobs |
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
  paths.py            Central path resolution (CWD-independent)
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
    loader.py         Skill loader (SKILL.md + __init__.py discovery)
    parser.py         SKILL.md parser
    registry.py       Skill registry + tool routing + credential filtering
    credential_store.py Secure credential storage (config.json)
    bundled/          61 built-in skills
  security/           Approvals, permissions, sandbox
  scheduler/          APScheduler background tasks
  agents/
    router.py         LLM agent loop with tool calling (max 10 rounds)
    persona_loader.py Persona prompt builder
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
