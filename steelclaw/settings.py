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
        "Always search first, then answer based on what you find."
    )
    provider_keys: dict[str, str] = {}  # {"anthropic": "sk-...", "openai": "sk-..."}
    streaming: bool = True
    timeout: int = 120


class SkillSettings(BaseModel):
    """Skill system configuration."""

    bundled_dir: str = "steelclaw/skills/bundled"
    global_dir: str = "~/.steelclaw/skills"
    workspace_dir: str = ".steelclaw/skills"
    enabled: bool = True
    disabled_skills: list[str] = []
    enabled_skills: list[str] = []  # skills user explicitly enabled (overrides auto-disable)
    skill_configs: dict[str, dict[str, str]] = {}  # per-skill credentials/settings


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

    # OpenViking subprocess management
    openviking_auto_start: bool = True  # Auto-start server when backend=openviking
    openviking_port: int = 1933  # Port for OpenViking server
    openviking_log_level: str = "info"  # Log level for OpenViking server


class SessionLifecycleSettings(BaseModel):
    """Session heartbeat and lifecycle configuration."""

    idle_timeout_minutes: int = 30
    close_timeout_minutes: int = 1440  # 24 hours
    heartbeat_interval_seconds: int = 60


class SecuritySettings(BaseModel):
    """Execution security configuration."""

    approvals_file: str = "exec-approvals.json"
    default_permission: str = "ask"  # "ask" | "record" | "ignore"
    sandbox_enabled: bool = True
    max_command_timeout: int = 30
    blocked_commands: list[str] = ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"]


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
    llm: LLMSettings = LLMSettings()
    skills: SkillSettings = SkillSettings()
    security: SecuritySettings = SecuritySettings()
    scheduler: SchedulerSettings = SchedulerSettings()
    voice: VoiceSettings = VoiceSettings()
    memory: MemorySettings = MemorySettings()
    session_lifecycle: SessionLifecycleSettings = SessionLifecycleSettings()


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
