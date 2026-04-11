"""Pydantic Settings — single config.json + STEELCLAW_* env var overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple, Type

from pydantic import BaseModel
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class DatabaseSettings(BaseModel):
    url: str = "sqlite+aiosqlite:///./data/steelclaw.db"
    echo: bool = False


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"


class ConnectorConfig(BaseModel):
    """Per-connector configuration. Extra fields are allowed for platform-specific options."""

    model_config = {"extra": "allow"}

    enabled: bool = False
    token: str | None = None


class GatewaySettings(BaseModel):
    mention_keywords: list[str] = ["@steelclaw", "@sc"]
    dm_allowlist_enabled: bool = True
    connectors: dict[str, ConnectorConfig] = {}


# ── Phase 2 Settings ────────────────────────────────────────────────────────


class LLMSettings(BaseModel):
    """LLM provider configuration via LiteLLM."""

    default_model: str = "gpt-4o-mini"
    api_key: str | None = None  # primary API key (or set via env: OPENAI_API_KEY etc.)
    api_base: str | None = None  # custom base URL for self-hosted models
    temperature: float = 0.7
    max_tokens: int = 4096
    max_context_messages: int = 50  # how many history messages to include in prompt
    system_prompt: str = (
        "You are SteelClaw, a helpful personal AI assistant. "
        "You can execute commands, browse the web, manage tasks, and communicate across platforms. "
        "Be concise, accurate, and proactive. "
        "IMPORTANT: When a user asks about current events, real-time data, recent news, prices, weather, "
        "or anything that requires up-to-date information, you MUST use the web_search tool to find the "
        "latest information. Then use fetch_url to read relevant pages for details. "
        "Never say you cannot access the internet — you have web_search and fetch_url tools available. "
        "Always search first, then answer based on what you find.\n\n"
        "CRITICAL — Permission system: The platform has a built-in approval popup for sensitive actions. "
        "NEVER ask the user for text confirmation before calling a tool (e.g. do NOT say 'Should I delete X? '). "
        "NEVER wait for the user to say 'yes', 'confirm', or 'go ahead' before executing. "
        "Instead, call the tool directly — the system will automatically show an approval popup to the user "
        "if the action requires permission. Asking first and then calling the tool causes a double-confirmation "
        "that confuses users. Execute immediately and let the permission system handle safety.\n\n"
        "When handling complex requests:\n"
        "1. First decompose the task into clear steps using create_plan\n"
        "2. For unfamiliar libraries or APIs, use fetch_docs to search documentation before implementing\n"
        "3. Verify each step before proceeding to the next\n"
        "4. Only ask clarifying questions when truly ambiguous — make reasonable assumptions for routine sub-tasks\n"
        "5. After successfully completing a complex task, store the experience for future reference\n"
        "6. Use pip_install, npm_install, or apt_install to install missing packages when needed"
    )
    provider_keys: dict[str, str] = {}  # {"anthropic": "sk-...", "openai": "sk-..."}
    streaming: bool = True
    timeout: int = 120


class ToolSettings(BaseModel):
    """Tool system configuration."""

    bundled_dir: str = "steelclaw/skills/bundled"
    global_dir: str = "~/.steelclaw/skills"
    workspace_dir: str = ".steelclaw/skills"
    enabled: bool = True
    disabled_tools: list[str] = []
    enabled_tools: list[str] = []  # tools user explicitly enabled (overrides auto-disable)
    tool_configs: dict[str, dict[str, str]] = {}  # per-tool credentials/settings

    # Deprecated aliases — config.json may still use old names
    disabled_skills: list[str] = []
    enabled_skills: list[str] = []
    skill_configs: dict[str, dict[str, str]] = {}

    def model_post_init(self, __context) -> None:
        """Migrate deprecated field names to new names at load time."""
        if self.disabled_skills and not self.disabled_tools:
            self.disabled_tools = list(self.disabled_skills)
        if self.enabled_skills and not self.enabled_tools:
            self.enabled_tools = list(self.enabled_skills)
        if self.skill_configs and not self.tool_configs:
            self.tool_configs = dict(self.skill_configs)


class SkillSettings(BaseModel):
    """Skills system configuration (Claude-compatible skills)."""

    global_dir: str = "~/.steelclaw/claude-skills"
    workspace_dir: str = ".claude-skills"
    enabled: bool = True
    disabled_skills: list[str] = []
    enabled_skills: list[str] = []


class MemorySettings(BaseModel):
    """Persistent memory configuration (ChromaDB vector store or OpenViking)."""

    enabled: bool = True
    chromadb_path: str = "~/.steelclaw/chromadb"
    collection_name: str = "steelclaw_memory"
    top_k: int = 5  # number of relevant memories to inject

    # Backend selection — defaults to chromadb for backward compatibility
    backend: str = "chromadb"  # "chromadb" | "openviking"
    openviking_server_url: str = "http://localhost:1933"
    openviking_workspace: str = "steelclaw"
    openviking_context_tier: str = "L1"  # "L0" | "L1" | "L2"

    # OpenViking subprocess management
    openviking_auto_start: bool = True  # Auto-start server when backend=openviking
    openviking_port: int = 1933  # Port for OpenViking server
    openviking_log_level: str = "info"  # Log level for OpenViking server


class SessionLifecycleSettings(BaseModel):
    """Session heartbeat and lifecycle configuration."""

    idle_timeout_minutes: int = 30
    close_timeout_minutes: int = 1440  # 24 hours
    heartbeat_interval_seconds: int = 60


class SudoSettings(BaseModel):
    """Sudo command execution configuration (disabled by default for safety)."""

    enabled: bool = False
    whitelist: list[str] = []  # glob patterns of pre-approved sudo commands
    audit_log: str = "~/.steelclaw/sudo_audit.log"
    session_timeout: int = 30  # seconds before sudo session expires


class ExtendedPermissionsSettings(BaseModel):
    """YAML-based capability permission toggles."""

    permissions_file: str = "~/.steelclaw/permissions.yaml"
    auto_create_file: bool = True  # write default permissions.yaml if absent


class ReflectionSettings(BaseModel):
    """Agent self-reflection and autonomous tool creation."""

    enabled: bool = False
    threshold: int = 5  # minimum tool calls before triggering reflection
    tool_auto_create: bool = False  # actually write generated tool files to disk
    skill_auto_create: bool = False  # deprecated alias for tool_auto_create


class MemoryFTSSettings(BaseModel):
    """SQLite FTS5 keyword-search memory layer."""

    enabled: bool = False
    db_path: str = "~/.steelclaw/memory_fts.db"
    nudge_limit: int = 3  # number of recent memories to include in nudge prompt


class SecuritySettings(BaseModel):
    """Execution security configuration."""

    approvals_file: str = "exec-approvals.json"
    default_permission: str = "ask"  # "ask" | "record" | "ignore"
    sandbox_enabled: bool = True
    max_command_timeout: int = 30
    blocked_commands: list[str] = ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"]
    permission_timeout: int = 300  # Seconds to wait for interactive permission response
    sudo: SudoSettings = SudoSettings()
    extended_permissions: ExtendedPermissionsSettings = ExtendedPermissionsSettings()


class SchedulerSettings(BaseModel):
    """Proactive task engine configuration."""

    enabled: bool = True
    timezone: str = "UTC"
    max_concurrent_jobs: int = 5


class VoiceSettings(BaseModel):
    """Voice capabilities configuration."""

    transcription_model: str = "whisper-1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    stt_provider: str = "openai"
    tts_provider: str = "openai"
    enabled: bool = False
    realtime_model: str = "gpt-realtime-1.5"
    realtime_voice: str = "alloy"
    realtime_vad_type: str = "semantic_vad"
    realtime_vad_eagerness: str = "auto"
    realtime_vad_threshold: float = 0.5
    realtime_silence_ms: int = 600
    realtime_prefix_padding_ms: int = 300


class AgentSettings(BaseModel):
    default_agent: str = "general"
    max_tool_rounds: int = 25  # Maximum tool-calling iterations per message (raised from 10 for autonomous operation)
    llm: LLMSettings = LLMSettings()
    tools: ToolSettings = ToolSettings()
    skills: SkillSettings = SkillSettings()  # Phase 2: Claude-compatible skills
    security: SecuritySettings = SecuritySettings()
    scheduler: SchedulerSettings = SchedulerSettings()
    voice: VoiceSettings = VoiceSettings()
    memory: MemorySettings = MemorySettings()
    session_lifecycle: SessionLifecycleSettings = SessionLifecycleSettings()
    reflection: ReflectionSettings = ReflectionSettings()
    memory_fts: MemoryFTSSettings = MemoryFTSSettings()


class Settings(BaseSettings):
    model_config = {
        "env_prefix": "STEELCLAW_",
        "env_nested_delimiter": "__",
    }

    database: DatabaseSettings = DatabaseSettings()
    server: ServerSettings = ServerSettings()
    gateway: GatewaySettings = GatewaySettings()
    agents: AgentSettings = AgentSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        from steelclaw.paths import PROJECT_ROOT

        sources = [init_settings, env_settings]
        try:
            from pydantic_settings import JsonConfigSettingsSource

            json_path = PROJECT_ROOT / "config.json"
            if json_path.exists():
                sources.append(JsonConfigSettingsSource(settings_cls, json_file=json_path))
        except ImportError:
            pass
        return tuple(sources)
