# SteelClaw

Self-hosted personal AI assistant that runs locally on your machine. Connects to any LLM (Claude, OpenAI, DeepSeek), communicates across 10+ messaging platforms, executes commands securely, and learns through a modular tool system with 60+ bundled integrations.

**Key highlights:** Premium glassmorphism UI, streaming LLM responses with real-time token display and live tool-call indicators, voice chat with streaming TTS, file upload in chat (images, PDFs, audio, DOCX, XLSX, PPTX), intelligent file & attachment handling across Telegram/Discord/Slack, 64 tool integrations with credential management, real-time web search, persistent memory (ChromaDB, OpenViking, or SQLite FTS5), hierarchical multi-agent orchestration with subagent delegation, extended system permissions with sudo support, self-improving autonomous tool creation, usage analytics, and a scheduler for proactive tasks.

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

SteelClaw resolves all paths relative to its installation directory, so you can run `steelclaw start` from any working directory. If you use a project-local virtual environment, the daemon automatically detects and uses the venv's Python so all optional dependencies (OpenViking, ChromaDB, etc.) are available.

**Open the Control UI dashboard:**

Navigate to [http://localhost:8000/](http://localhost:8000/) in your browser. The dashboard features a premium glassmorphism design with 10 navigation pages: Chat, Settings, Sessions, Agents, Persona, Analytics, Connectors, Tools, Security, and Scheduler.

**Or chat from the terminal (TUI):**

```bash
steelclaw chat
```

The TUI chat supports streaming responses — text appears token-by-token as the LLM generates it, with live tool-call status indicators and delegation banners for multi-agent workflows. Uses Rich for styled panels and Markdown rendering.

**Slash command autocomplete:** Type `/` in the prompt to open an interactive inline dropdown of all available commands grouped by category. Use arrow keys to navigate, Enter to select, Escape to dismiss. Typing narrows the list in real time (e.g. `/sc` matches `/scheduler`, `/security`). Falls back to plain input in non-interactive (piped/CI) environments.

#### Chat-native commands (resolved inside the TUI, no server round-trip)

| Command | Description |
|---------|-------------|
| `/help` | Show all commands, grouped by section |
| `/clear` | Clear conversation history |
| `/new` | Start a fresh conversation |
| `/history` | Show full conversation history |
| `/compact` | Show last 10 exchanges (compact) |
| `/status` | Connection info — probes the REST `/health` endpoint live |
| `/model` | Live LLM config (model, temperature, max tokens, streaming) |
| `/stats` | Session statistics |
| `/version` | SteelClaw package version and server URL |
| `/pricing` | Model pricing table grouped by provider |
| `/export [file]` | Export chat to a Markdown file |
| `/exit` / `/quit` | Exit the chat |

#### CLI passthrough commands (delegated to `steelclaw <subcommand>`)

Prefix any CLI subcommand with `/` to run it without leaving the chat. Quoted arguments and paths with spaces are handled correctly via shell-aware parsing.

| Command | Example | Description |
|---------|---------|-------------|
| `/serve` | `/serve` | Start the API server in foreground |
| `/start` / `/stop` / `/restart` | | Daemon management |
| `/app` | `/app restart` | Manage app components |
| `/config` | `/config get agents.llm.default_model` | View/edit configuration |
| `/sessions` | `/sessions list` | Manage sessions |
| `/memory` | `/memory search "error budget"` | Manage persistent memory |
| `/agents` | `/agents list` | Manage agents |
| `/tools` | `/tools configure github` | Manage tools |
| `/scheduler` | `/scheduler list` | Manage scheduled jobs |
| `/security` | `/security list-rules` | Manage security settings |
| `/sudo` | `/sudo enable` | Sudo mode shortcuts |
| `/connectors` | `/connectors status telegram` | Manage connectors |
| `/gateway` | `/gateway restart` | Manage gateway |
| `/logs` | `/logs -f` | Follow daemon logs |
| `/persona` | `/persona` | Configure agent persona |
| `/onboard` / `/setup` | | Onboarding wizard |
| `/migrate` | | Run database migrations |

**`/sudo` shortcuts:**

| Command | Maps to |
|---------|---------|
| `/sudo enable` | `steelclaw security sudo-enable true` |
| `/sudo disable` | `steelclaw security sudo-enable false` |
| `/sudo whitelist list` | `steelclaw security sudo-whitelist list` |
| `/sudo whitelist add <pattern>` | `steelclaw security sudo-whitelist add <pattern>` |
| `/sudo whitelist remove <pattern>` | `steelclaw security sudo-whitelist remove <pattern>` |
| `/sudo status` | `steelclaw security show` |

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
| `steelclaw config show\|get\|set` | View/edit `config.json` via dot-notation keys |
| `steelclaw sessions list\|reset\|delete` | Manage sessions |
| `steelclaw agents list\|add\|delete\|status` | Manage agents (supports `--parent`, `--system-prompt`) |
| `steelclaw tools list\|install\|enable\|disable\|configure` | Manage tools |
| `steelclaw skills list\|view\|create\|import\|export\|generate\|enable\|disable\|test` | Manage Claude-compatible skills |
| `steelclaw memory status\|search\|clear\|start\|stop\|migrate` | Manage persistent memory |
| `steelclaw persona` | Configure agent persona interactively |
| `steelclaw logs [-f] [--gateway] [--app]` | View daemon logs |
| `steelclaw migrate` | Run database migrations |
| `steelclaw scheduler list\|add\|remove\|run\|set-timezone` | Manage scheduled jobs |
| `steelclaw security show\|list-rules\|add-rule\|remove-rule\|sudo-*\|capabilities` | Manage security settings |
| `steelclaw gateway start\|stop\|restart` | Manage gateway connectors |
| `steelclaw connectors list\|configure\|enable\|disable\|status` | Manage individual connectors |
| `steelclaw app start\|stop\|restart\|reset` | Manage app components |

### `steelclaw config` — Configuration CLI

Read and write any `config.json` value without editing the file manually, using dot-notation keys:

```bash
# Show the full config with syntax highlighting
steelclaw config show

# Get a specific value
steelclaw config get agents.llm.default_model
steelclaw config get agents.security.sudo.enabled

# Set a value (JSON-parsed: use true/false for booleans, numbers stay numeric)
steelclaw config set agents.llm.default_model claude-sonnet-4-20250514
steelclaw config set agents.llm.temperature 0.5
steelclaw config set agents.security.sudo.enabled true
steelclaw config set server.port 9000
```

Changes take effect after restarting the server (`steelclaw restart`).

### `steelclaw scheduler` — Job Management

```bash
steelclaw scheduler list
steelclaw scheduler add daily-report --cron "0 9 * * *" --command "generate report"
steelclaw scheduler add heartbeat   --interval 300 --command "ping"
steelclaw scheduler remove daily-report
steelclaw scheduler run daily-report
steelclaw scheduler set-timezone America/New_York
```

### `steelclaw security` — Security Settings

```bash
steelclaw security show
steelclaw security list-rules
steelclaw security add-rule "git *" --permission ignore --note "All git commands"
steelclaw security remove-rule "git *"
steelclaw security set-default ask|record|ignore
steelclaw security sudo-enable true|false
steelclaw security sudo-whitelist list|add|remove <pattern>
steelclaw security capabilities
steelclaw security set-capability file_deletion allow
```

## Access Methods

| Method | How to Access | Description |
|--------|--------------|-------------|
| **Control UI** | `http://localhost:8000/` | Glassmorphism dashboard with streaming chat, voice, settings, tools, analytics |
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

### Slash Command Autocomplete in Connectors

Telegram, Discord, and Slack connectors register slash commands with their respective platforms on startup. Users can type `/` in any connected chat to see an inline list of available commands with descriptions — no configuration required.

- **Telegram** — commands registered via `setMyCommands` API; appear in the native Telegram command suggestion UI
- **Discord** — application commands registered via the Discord API; appear as slash command suggestions
- **Slack** — slash commands surfaced to workspace members

### File & Attachment Handling in Connectors

SteelClaw intelligently handles files sent through any messaging platform. When a user sends a file, the connector downloads it, classifies it, and forwards it to the LLM with appropriate context:

| File Type | Platforms | What happens |
|-----------|-----------|--------------|
| **Images** (JPEG, PNG, GIF, WebP, etc.) | Telegram, Discord, Slack | Downloaded and base64-encoded; sent as vision input to the LLM |
| **Documents** (PDF, TXT, Markdown, JSON, XML) | Telegram, Discord, Slack | Text extracted (PDF via pdfplumber/pypdf); included as a text block |
| **DOCX / DOC** | Telegram, Discord, Slack | Text extracted via python-docx and included in message context |
| **XLSX / XLS** | Telegram, Discord, Slack | Parsed via openpyxl; header + row preview included |
| **PPTX / PPT** | Telegram, Discord, Slack | Slide text extracted via python-pptx and included |
| **CSV files** | Telegram, Discord, Slack | Parsed; header + row preview included in the message context |
| **Audio** (MP3, OGG, WAV, etc.) | Telegram, Discord, Slack | Transcribed to text via Whisper and included in message context |
| **Video** (MP4, WebM, etc.) | Telegram, Discord, Slack | Metadata surfaced to the agent |
| **Stickers / Animations** | Telegram | Treated as image attachments |

**Telegram specifics:** Handles `photo`, `document`, `audio`, `video`, `animation`, and `sticker` message types. Caption text is preserved alongside the attachment. Bot @mentions in media captions (stored in `caption_entities`) are correctly detected.

**Discord specifics:** All `discord.Attachment` objects on a message are collected and forwarded through the same pipeline.

**Slack specifics:** Files attached to messages (the `files` array) are downloaded using the bot token. The `file_share` subtype is handled so file-only messages are no longer silently dropped.

When a file arrives without any caption or text, a descriptive placeholder (`[File attachment: filename]`) is used so the agent always has something to reason about.

### Session Behaviour

- **DMs** across all platforms are unified into a single conversation per user
- **Group chats** are isolated per group — SteelClaw only responds when @mentioned or triggered by keyword
- **Allowlist** controls who can DM the bot (enable/disable in config)
- **Session lifecycle** — sessions transition through `active` → `idle` → `closed` with configurable timeouts
- **Heartbeat** — background job auto-detects idle and stale sessions
- Sessions from all connectors (Telegram, Discord, Slack, etc.) are visible in the Sessions dashboard page and via the CLI

## Voice Chat

SteelClaw supports real-time voice interaction via the OpenAI Realtime API over WebRTC — direct browser-to-OpenAI connection with sub-2-second latency and true interruption support (like ChatGPT Voice).

- **WebRTC peer connection** — browser connects directly to OpenAI's Realtime API without server audio relay
- **Sub-2-second latency** — real-time speech-to-text, LLM response, and text-to-speech pipeline
- **Interruption support** — speak at any time during agent response to naturally interrupt and redirect conversation
- **Server-side VAD** — semantic voice activity detection for automatic turn-taking
- **Full-screen overlay UI** — animated visual state (IDLE → CONNECTING → LISTENING → AGENT_SPEAKING → INTERRUPTED) with animated orb, rings, and waveform
- **Voice selection** — choose from 6 voice options (alloy, echo, fable, onyx, nova, shimmer) via integrated chip selector
- **Configurable realtime settings** — VAD threshold, silence duration, prefix audio padding for natural conversation flow

**How to use:**
1. Click the microphone button (🎧) in the chat header to start
2. Speak naturally — your voice is streamed and processed in real-time
3. Agent responds with voice — you can interrupt at any time by speaking
4. Click the microphone button again or press Escape to stop

**Configuration:** Set your OpenAI API key in Settings > Voice/Audio, then enable voice. The system uses OpenAI's `gpt-realtime-1.5` model by default with semantic VAD for natural turn-taking.

**Advanced settings (Settings > Voice/Audio):**
- Realtime model selection (defaults to `gpt-realtime-1.5`)
- VAD threshold (0.0-1.0, default 0.5)
- Silence timeout in milliseconds (default 600ms)

## Streaming Responses

SteelClaw streams LLM responses in real time across all interfaces:

- **Web UI** — tokens appear character-by-character via WebSocket with a typing indicator and live tool-call status badges (glassmorphism style with slide-in animation)
- **TUI chat** — Rich live display updates as tokens arrive, with tool execution progress and duration
- **WebSocket API** — structured streaming events for programmatic clients

### Streaming Event Schema

```
{ "type": "chunk",      "content": "..." }
{ "type": "tool_start", "name": "web_search", "id": "call_abc", "tool": "Web Search", "label": "Search the web", "arguments": {...} }
{ "type": "tool_end",   "name": "web_search", "id": "call_abc", "duration_ms": 342 }
{ "type": "done",       "content": "...", "usage": { "model": "...", "prompt_tokens": 1200, "completion_tokens": 80 } }
{ "type": "error",      "content": "..." }
```

Delegation events are enriched with the specific sub-agent name:

```
{ "type": "tool_start", "name": "delegate_to_research-agent", "label": "Delegating to research-agent", "subagent": "research-agent" }
```

Token usage and model metadata are captured from the streaming response for accurate analytics and billing.

## File Uploads in Chat

Attach files directly in the chat to have SteelClaw analyze their content:

- **Images** (JPEG, PNG, GIF, WebP) — sent as inline vision to the LLM for visual analysis
- **Documents** (PDF, TXT, CSV, JSON, Markdown, HTML, XML) — text extracted and included in the message context
- **Office documents** (DOCX, XLSX, PPTX) — text/data extracted via python-docx, openpyxl, and python-pptx
- **Audio** (MP3, WAV, WebM, OGG) — automatically transcribed via Whisper and included as text

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
- Tabbed settings page: Appearance, Voice/Audio, Agent, Tools, Gateway, Scheduler
- Real-time tool-call indicators during agent execution (spinner badges with slide-in animation)

## Agent Personality & Multi-Agent

### Persona System

Configure how SteelClaw communicates — agent name, user's name, tone, style, and goals:

```bash
steelclaw persona
```

Or configure via the dashboard Persona page. Persona settings are injected into the system prompt for consistent behavior.

### Hierarchical Multi-Agent Orchestration

SteelClaw supports hierarchical multi-agent workflows. A main agent can delegate tasks to specialized sub-agents, each with their own model, system prompt, and memory namespace.

**Creating sub-agents:**

```bash
# Via CLI
steelclaw agents add --name researcher --model gpt-4o --system-prompt "You are a research specialist..."
steelclaw agents add --name coder --model claude-opus-4-6 --parent researcher

# List agents (shows parent relationships)
steelclaw agents list
```

The main agent is auto-created on first startup. Sub-agents appear in the Agents dashboard page with their parent relationship, model, and status.

**Delegation via LLM tools:**

When sub-agents exist, the main agent automatically gains access to these orchestration tools:

| Tool | Description |
|------|-------------|
| `delegate_to_subagent` | Send a task to a named sub-agent and get its response |
| `list_subagents` | List all active sub-agents with their configuration |
| `create_subagent` | Dynamically create a new sub-agent at runtime |
| `update_subagent` | Modify an existing sub-agent's prompt or model |
| `delete_subagent` | Remove a sub-agent (requires `confirm: true`) |

**Delegation display:** When the main agent delegates, the TUI and web UI show a live indicator identifying the specific sub-agent being called:

```
◈ Delegating → research-agent      (spinner)
✓ ◈ research-agent done  [1243ms]
```

**Agent hierarchy in DB:** The `agents` table includes a `parent_agent_id` self-referential foreign key, enabling full tree traversal of agent relationships via the API.

## Persistent Memory

SteelClaw supports three memory backends: **ChromaDB** (default, local vector store), **OpenViking** (agent-native context database), and **SQLite FTS5** (keyword search with Porter stemming).

### ChromaDB (default)

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

### OpenViking

OpenViking is an agent-native context database with structured memory tiers (L0/L1/L2), semantic search, and automatic memory decay.

**Install:**

```bash
pip install -e ".[openviking]"
# or for all extras:
pip install -e ".[all]"
```

**Configure `~/.openviking/ov.conf`:**

```json
{
  "default_account": "default",
  "default_user": "default",
  "default_agent": "default",
  "embedding": {
    "dense": {
      "api_base": "https://api.openai.com/v1",
      "api_key": "sk-...",
      "provider": "openai",
      "model": "text-embedding-3-small",
      "dimension": 1536
    }
  },
  "vlm": {
    "api_base": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "provider": "openai",
    "model": "gpt-4o",
    "max_retries": 2
  },
  "storage": {
    "workspace": "~/.openviking/data"
  }
}
```

**Enable in `config.json`:**

```json
{
  "agents": {
    "memory": {
      "backend": "openviking",
      "openviking_server_url": "http://localhost:1933",
      "openviking_workspace": "steelclaw",
      "openviking_context_tier": "L1",
      "openviking_auto_start": true,
      "openviking_port": 1933
    }
  }
}
```

With `openviking_auto_start: true`, the OpenViking server is started automatically as a subprocess when SteelClaw starts and shut down cleanly on exit. Server health is verified before the memory system is activated.

**CLI memory management:**

```bash
steelclaw memory status      # shows backend, server status, stored count
steelclaw memory start       # manually start the OpenViking server
steelclaw memory stop        # manually stop the OpenViking server
steelclaw memory migrate     # migrate from chromadb → openviking
```

### SQLite FTS5 (Keyword Search)

SteelClaw includes a built-in SQLite FTS5 memory layer for fast keyword and stemmed search, complementing the vector-based memory backends. This is useful for exact-term retrieval without requiring external dependencies.

**Features:**
- Porter stemming for better word matching (e.g., "running" matches "run")
- Full-text search across all stored memories
- Memory nudge prompts for system prompt injection
- Per-agent and per-session isolation

**Enable in `config.json`:**

```json
{
  "agents": {
    "memory_fts": {
      "enabled": true,
      "db_path": "~/.steelclaw/memory_fts.db",
      "nudge_limit": 5
    }
  }
}
```

**How it works:**
- Every message is automatically indexed in the FTS5 table
- `nudge_limit` controls how many recent relevant memories are injected into the agent's system prompt
- Works alongside ChromaDB/OpenViking for hybrid semantic + keyword search

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

## Tools

Tools are modular capabilities loaded from directories. Each tool has a `SKILL.md` file defining metadata, tools, and a system prompt. SteelClaw ships with **64 bundled tools** covering productivity, development, communication, CRM, cloud storage, and more.

**Default behaviour:** Core tools (no credentials needed) are enabled out of the box. Integration tools that require API keys are disabled by default — enable them from the Tools page once you've configured their credentials. Enable/disable state persists across restarts. Tools from unconfigured tools are automatically hidden from the LLM, so the agent only uses tools it can actually call.

### Bundled Tools

**Core (no credentials needed):**

| Tool | Tools | Description |
|-------|-------|-------------|
| Calculator | `evaluate`, `convert_units` | Math evaluation and unit conversion |
| File Manager | `read_file`, `write_file`, `list_directory`, `copy_file`, `move_file`, `create_directory`, `delete_file` | Full file system operations |
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
| Tool Manager | `list_skills`, `create_skill`, `edit_skill`, `delete_skill`, `reload_skills` | Autonomous tool management |

**Integrations (API key required — configure via UI or CLI):**

| Category | Tools |
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

### Tool Credential Management

Configure API keys through the dashboard (Tools page > Configure button) or CLI:

```bash
steelclaw tools list                    # List all tools with credential status
steelclaw tools install ./my-skill      # Install from directory
steelclaw tools enable my-skill         # Enable a disabled tool
steelclaw tools disable my-skill        # Disable a tool
steelclaw tools configure my-skill      # Set tool credentials interactively
```

The dashboard credential modal shows each tool's required fields with secure input, saved-state indicators, and a Verify button that tests connectivity against the provider's API.

### Tool Scoping (priority order)

1. **Workspace** (`.steelclaw/skills/`) — project-specific, highest priority
2. **Global** (`~/.steelclaw/skills/`) — user-wide
3. **Bundled** (`steelclaw/skills/bundled/`) — ships with SteelClaw

### Creating a Tool

```
my-skill/
  SKILL.md
  __init__.py    # optional: Python tool executors
```

**SKILL.md format:**

```markdown
# My Tool

Description of what this tool does.

## Metadata
- version: 1.0.0
- author: Your Name
- triggers: keyword1, keyword2

## System Prompt
Instructions for the LLM when this tool is active.

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

# Set True to prevent users from disabling this tool
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

**Note:** If `required_credentials` are declared but not configured by the user, the tool's functions are automatically hidden from the LLM. This prevents the agent from calling tools that would fail due to missing API keys.

## Skills

Skills are Claude-compatible instruction bundles that provide contextual guidance to the agent. Unlike **tools** (which have executable Python functions), skills are pure Markdown manifests that inject system-level instructions when activated — keeping chat history clean.

Skills are **100% compatible with Claude Skills format**: export from SteelClaw and import into Claude with zero modifications, and vice versa.

### Skill Format

```
my-skill/
  SKILL.md     # Skill manifest (required)
  scripts/     # Optional helper scripts
    run.sh
```

**SKILL.md:**

```markdown
# My Skill

Brief description for agent reasoning.

## Metadata
- version: 1.0.0
- author: username
- triggers: keyword1, keyword2

## System Prompt
Instructions for the LLM when this skill is active.
```

### Skill Activation

The agent matches skills in two ways:

- **Explicit:** User references a skill directly ("Use the code-review skill")
- **Implicit (trigger matching):** When a user's message contains a skill's trigger keywords, the skill's instructions are automatically injected as system context

### Skill Management

**Web UI:** Navigate to the Skills page (🧠 sidebar button) to create, import, export, generate, enable/disable, and delete skills using the Card Grid interface.

**CLI:**

```bash
steelclaw skills list                    # List installed skills
steelclaw skills view my-skill           # Show skill details + SKILL.md
steelclaw skills create                  # Interactive creation wizard
steelclaw skills import ./path/to/skill  # Import from .md, .zip, or directory
steelclaw skills export my-skill         # Export as Claude-compatible zip
steelclaw skills delete my-skill         # Delete a skill
steelclaw skills generate "description"  # AI-generate from natural language
steelclaw skills enable my-skill         # Enable a skill
steelclaw skills disable my-skill        # Disable a skill
steelclaw skills test "my message"       # Test trigger matching
```

**API:**

```bash
GET    /api/skills                        # List skills
GET    /api/skills/{name}                 # Skill detail
POST   /api/skills                        # Create skill
DELETE /api/skills/{name}                 # Delete skill
POST   /api/skills/{name}/enable          # Enable
POST   /api/skills/{name}/disable         # Disable
POST   /api/skills/import                 # Upload .md or .zip
POST   /api/skills/import-path            # Import from filesystem
GET    /api/skills/{name}/export          # Export as zip
POST   /api/skills/generate               # AI-generate from description
POST   /api/skills/reload                 # Hot-reload from disk
POST   /api/skills/test                   # Test trigger matching
```

### Skill Scoping

1. **Workspace** (`.claude-skills/`) — project-specific, highest priority
2. **Global** (`~/.steelclaw/claude-skills/`) — user-wide

## Self-Improving Architecture

SteelClaw can autonomously create and refine tools based on observed tool-call patterns. This feature is inspired by the Hermes Agent architecture and enables the agent to learn from experience.

### Autonomous Tool Creation

After completing a task with 5+ tool calls (configurable), the agent reflects on the execution pattern and may create a reusable tool:

1. **Reflection trigger** — Agent analyses recent tool calls for reusable patterns
2. **Tool generation** — LLM generates a `SKILL.md` + `__init__.py` scaffold
3. **Validation** — Generated tool is parsed and validated before writing
4. **Hot-reload** — New tool is immediately available without restart

**Configuration:**

```json
{
  "agents": {
    "reflection": {
      "enabled": true,
      "threshold": 5,
      "skill_auto_create": false
    }
  }
}
```

- `enabled`: Toggle reflection on/off (default: `true`)
- `threshold`: Minimum tool calls before reflection triggers (default: `5`)
- `skill_auto_create`: If `false`, reflections are only logged without writing files (safe default). Set to `true` to enable autonomous tool creation.

### Tool Management

The bundled `skill_manager` tool provides functions for managing tools at runtime:

| Tool | Description |
|------|-------------|
| `list_skills` | List all available tools with their status |
| `create_skill` | Scaffold a new tool in workspace or global directory |
| `edit_skill` | Modify an existing tool's SKILL.md or __init__.py |
| `delete_skill` | Remove a tool (workspace/global only, not bundled) |
| `reload_skills` | Hot-reload all tools from disk |

**Note:** Bundled tools cannot be edited or deleted — only workspace and global tools are mutable.

### Memory Nudge

The FTS5 memory layer periodically injects recent relevant memories into the agent's system prompt, grounding responses in past context without manual retrieval. This creates a continuous learning loop where insights from previous sessions influence current behavior.

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

### Extended System Permissions

Fine-grained capability controls via `~/.steelclaw/permissions.yaml`:

```yaml
# Auto-created on first run with safe defaults
filesystem:
  read: true
  write: true
  delete: false    # Requires explicit enable
processes:
  list: true
  kill: false      # Requires explicit enable
network:
  http: true
  dns: true
packages:
  install: false   # Requires explicit enable
environment:
  read: true
  write: false
cron:
  manage: false
```

Enable categories in `config.json`:

```json
{
  "agents": {
    "security": {
      "extended_permissions": {
        "permissions_file": "~/.steelclaw/permissions.yaml",
        "auto_create_file": true
      }
    }
  }
}
```

### Sudo Command Execution

Execute privileged commands with strict user confirmation:

**Configuration (`config.json`):**

```json
{
  "agents": {
    "security": {
      "sudo": {
        "enabled": false,           // Master toggle — disabled by default
        "whitelist": ["apt", "systemctl"],  // Auto-approved executables
        "audit_log": "~/.steelclaw/sudo_audit.log",
        "session_timeout": 30       // Seconds to wait for confirmation
      }
    }
  }
}
```

**Confirmation flow:**
1. Agent identifies a command requires sudo
2. If the executable matches a whitelist pattern → execute immediately
3. Otherwise, prompt the user with the full command
4. User must type **`YES`** (exactly, uppercase) to approve
5. All sudo commands are logged to an immutable append-only audit log

**Security guarantees:**
- Disabled by default — must be explicitly enabled
- Never auto-approves non-whitelisted commands
- Requires literal `YES` response (not `y`, `yes`, `ok`)
- Immutable audit trail at `~/.steelclaw/sudo_audit.log`
- Commands executed via `exec` (not shell) to prevent injection

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

Proactive task execution with cron expressions, fixed intervals, and event-based triggers (file watcher, RSS polling, API polling).

```bash
# Via CLI
steelclaw scheduler list
steelclaw scheduler add daily-report --cron "0 9 * * *" --command "generate daily report"
steelclaw scheduler add heartbeat --interval 300 --command "ping service"
steelclaw scheduler remove daily-report
steelclaw scheduler set-timezone America/New_York
steelclaw scheduler set-max-concurrent 5

# Via the chat TUI
/scheduler list
/scheduler add job1 --cron "0 9 * * *" --command "report"

# Via REST API
curl http://localhost:8000/api/scheduler/jobs
curl http://localhost:8000/api/scheduler/status
```

Jobs can also be added programmatically via the Python API or through LLM tool calls (the `cron_manager` tool provides `schedule_task`, `list_scheduled`, and `cancel_task` tools).

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
| `/api/agents` | GET/POST | List/create agents (with parent_agent_id support) |
| `/api/agents/{id}` | GET/PUT/DELETE | Agent CRUD |
| `/api/agents/{id}/persona` | PUT | Update agent persona |
| `/api/agents/{id}/subagents` | GET | List sub-agents of an agent |
| `/api/analytics/summary` | GET | Token/cost/session totals |
| `/api/analytics/usage-over-time` | GET | Time-series usage data |
| `/api/analytics/by-model` | GET | Usage grouped by model |
| `/api/analytics/by-agent` | GET | Usage grouped by agent |
| `/api/analytics/export` | GET | CSV export |
| `/api/tools` | GET | List tools (with credential status) |
| `/api/tools/{name}/credentials` | GET/PUT | Read/write tool credentials |
| `/api/tools/{name}/verify` | POST | Test credential connectivity |
| `/api/tools/{name}/enable` | POST | Enable a tool |
| `/api/tools/{name}/disable` | POST | Disable a tool |
| `/api/tools/reload` | POST | Hot-reload all tools |
| `/api/persona` | GET/POST | Read/write persona config |
| `/api/files/upload` | POST | Upload file attachment for chat (images, docs, audio, office) |
| `/api/voice/transcribe` | POST | Speech-to-text (Whisper) |
| `/api/voice/synthesize` | POST | Text-to-speech (single response) |
| `/api/voice/synthesize-stream` | POST | Chunked TTS streaming |
| `/api/voice/realtime-session` | POST | Create ephemeral OpenAI Realtime API session token (WebRTC) |
| `/api/voice/status` | GET | Voice service status |
| `/api/config/voice` | GET/PUT | Voice settings |
| `/api/config/tools` | GET/PUT | Tool settings |
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
| `agents` | Agent profiles (main + sub-agents with `parent_agent_id` hierarchy) |
| `user_facts` | Extracted user facts for personalization |
| `memory_entries` | Memory metadata (vector data in ChromaDB or OpenViking) |
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
    daemon.py         Background daemon management (auto-detects venv Python)
    logs.py           Log viewer
    sessions.py       Session management CLI
    memory.py         Memory management CLI (start/stop/migrate for OpenViking)
    agents.py         Agent management CLI (parent hierarchy, subagent flags)
    skills_cmd.py     Tool management CLI
    persona.py        Persona configuration wizard
    gateway_cmd.py    Gateway connector control
    app_cmd.py        App component management
    config_cmd.py     Configuration CLI (show/get/set via dot-notation)
    scheduler.py      Scheduler job management CLI
    security.py       Security settings CLI (rules, sudo, capabilities)
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
    viking_store.py   OpenViking HTTP backend (optional)
    openviking_manager.py OpenViking server subprocess lifecycle
    retrieval.py      Semantic memory retrieval
    ingestion.py      Memory ingestion pipeline
  skills/
    loader.py         Tool loader (SKILL.md + __init__.py discovery)
    parser.py         SKILL.md parser
    registry.py       Tool registry + tool routing + credential filtering
    credential_store.py Secure credential storage (config.json)
    bundled/          64 built-in tools
  security/           Approvals, permissions, sandbox
  scheduler/          APScheduler background tasks
  agents/
    router.py         LLM agent loop with tool calling (max 10 rounds)
    orchestrator.py   Multi-agent orchestrator (delegation, agent management tools)
    persona_loader.py Persona prompt builder
  gateway/
    attachments.py    File classification + download + text extraction (all connectors)
    base.py           BaseConnector abstract class
    connectors/       Platform connector implementations
    registry.py       Connector registry
    router.py         Central message pipeline (WebSocket + webhooks)
    session_manager.py Session resolution
  api/                REST API endpoints
```

## Configuration Reference

All settings can be set in `config.json` or via environment variables with prefix `STEELCLAW_` and `__` for nesting:

```bash
# Examples:
STEELCLAW_AGENTS__LLM__DEFAULT_MODEL=claude-sonnet-4-20250514
STEELCLAW_SERVER__PORT=9000
STEELCLAW_GATEWAY__DM_ALLOWLIST_ENABLED=false
STEELCLAW_AGENTS__MEMORY__BACKEND=openviking
```

## License

MIT
