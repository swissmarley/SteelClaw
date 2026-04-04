# Design Spec: Voice Memory/Persona, Skill Credential Sync, Slack Connector Fix

**Date:** 2026-04-04  
**Branch:** develop  
**Status:** Approved

---

## Overview

Three independent bugs and enhancements:

1. **Task 1** — Voice Talk Mode (Realtime API WebRTC) is initialized without persona or memory context, so the agent can't answer "What is my name?" in voice mode.
2. **Task 2** — Skill credentials written via CLI are invisible to the running server (split-brain between `config.json` on disk and in-memory `settings`); and there is no interactive skill configuration menu.
3. **Task 3** — Enabling a Slack connector in the Web UI shows "enabled" (orange) but never starts the listener; no live start/stop API exists; and there is no CLI connector management.

---

## Task 1 — Voice Talk Mode Missing Memory & Persona

### Root Cause

`POST /api/voice/realtime-session` (`steelclaw/api/voice.py`) builds the OpenAI Realtime API `instructions` field from the raw `AgentProfile.system_prompt` only. It never calls:
- `build_persona_system_prompt()` — which injects user name, tone, goals from `~/.steelclaw/persona.json`
- `memory_retriever.retrieve_relevant()` — which injects relevant past context

The normal chat path (`agents/router.py` `_run_agent_loop`) does both on every turn.

### Fix

In `create_realtime_session`, after loading `system_prompt`:

1. Call `build_persona_system_prompt()` (reads `~/.steelclaw/persona.json`).
2. Access `request.app.state.memory_retriever`; if present, call:
   ```python
   retrieve_relevant(
       query_text="user name preferences goals",
       namespace="memory_main",
       limit=5,
   )
   ```
   then `format_for_prompt()` on the result.
3. Build:
   ```python
   full_instructions = persona_prompt
   if system_prompt:
       full_instructions += f"\n\n{system_prompt}"
   if memory_context:
       full_instructions += f"\n\n{memory_context}"
   ```
4. Use `full_instructions` as `instructions` in the Realtime API payload.

Memory retrieval errors are swallowed (non-critical) — session still starts without memory context rather than failing.

### Test

In `tests/test_voice_stream.py`: mock `memory_retriever` and `build_persona_system_prompt`, call the endpoint, assert:
- The payload `instructions` field contains the persona user_name string.
- The payload `instructions` field contains the memory context string.

---

## Task 2 — Skill Credential Sync + Interactive CLI

### Part A — Root Cause: Split-Brain Credential State

The running server's `SkillRegistry._settings.skill_configs` is loaded once at startup from `config.json`. When the CLI runs `steelclaw skills configure <skill>`, it writes new credentials to `config.json` on disk but the running server never re-reads the file. Result: credentials are in `config.json` but `_is_skill_configured()` returns `False` because it only checks the stale in-memory dict.

### Fix A — Disk Fallback in `_is_skill_configured`

In `steelclaw/skills/registry.py`, `_is_skill_configured()`:

```python
def _is_skill_configured(self, skill: "Skill") -> bool:
    if not skill.required_credentials:
        return True
    stored = self._settings.skill_configs.get(skill.name, {})
    for cred in skill.required_credentials:
        value = stored.get(cred["key"])
        if not value:
            from steelclaw.skills.credential_store import get_credential
            value = get_credential(skill.name, cred["key"])
        if not value:
            return False
    return True
```

Same fallback added to `get_skill_credentials()` so the Web UI shows CLI-set credentials as already configured.

No changes to credential storage paths — both CLI and Web UI already write to `config.json`.

### Part B — Interactive Skill Configuration CLI

**`steelclaw/cli/skills_cmd.py` — `_configure_skill(name: str | None)`:**

- If `name` is provided: existing key=value prompt behavior (unchanged).
- If `name` is `None`:
  1. Fetch skill list from `GET /api/skills`.
  2. Build choices: `"skill_name  ✓ configured"` or `"skill_name  ✗ not configured"`.
  3. `questionary.select("Select a skill to configure:", choices=choices)`.
  4. For each field in `required_credentials`:
     - Type `"password"` → `questionary.password(label)`
     - Other types → `questionary.text(label)`
  5. `PUT /api/skills/{name}/credentials` with collected values.
  6. Print `"✓ Credentials saved for <skill>."`.

**`argparse`:** `name` becomes `nargs="?"` (optional positional).

**Dependency:** Add `questionary` to `pyproject.toml` dependencies.

**Test:** Mock API calls + questionary; assert `PUT` is called with the correct credential payload when name is omitted.

---

## Task 3 — Slack Connector Fix + Connector CLI

### Part A — Root Cause: No Live Connector Start/Stop

`ConnectorRegistry.start_all()` runs once in the FastAPI lifespan. `PUT /api/config/connectors/{platform}` only updates `config.json` and says "restart required." There is no API endpoint to start/stop a connector at runtime.

When Slack's `_run()` encounters a missing token, it logs an error and `return`s — the asyncio task finishes immediately. `_task.done()` becomes `True` → `GET /api/config/connectors` reports `"enabled_not_running"`.

### Fix A — `BaseConnector` Error Tracking

Add to `steelclaw/gateway/base.py`:
```python
last_error: str | None = None  # instance variable, set on fatal startup failure

@property
def is_running(self) -> bool:
    return self._task is not None and not self._task.done()
```

### Fix B — `ConnectorRegistry` Live Control

Add to `steelclaw/gateway/registry.py`:
```python
async def start_connector(self, name: str, conf: ConnectorConfig) -> None:
    """Import, instantiate, and start a single connector."""
    ...

async def stop_connector(self, name: str) -> None:
    """Stop and remove a single connector."""
    ...
```

### Fix C — Auto-Start on Enable (`steelclaw/api/config.py`)

`PUT /api/config/connectors/{platform}`:
- After writing config.json, if `body.get("enabled")`:
  - Call `registry.start_connector(platform, conf)`
  - If connector's `last_error` is set after start, return `{"status": "error", "message": connector.last_error}`
  - Otherwise return `{"status": "running"}`
- If `not body.get("enabled")`:
  - Call `registry.stop_connector(platform)`
  - Return `{"status": "disabled"}`

### Fix D — Slack Health Check (`steelclaw/gateway/connectors/slack.py`)

At the top of `_run()`, before the retry loop:
```python
async with httpx.AsyncClient() as client:
    resp = await client.post(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    if not data.get("ok"):
        self.last_error = f"auth.test failed: {data.get('error', 'unknown')}"
        logger.error("Slack auth.test failed: %s", self.last_error)
        return
    logger.info("Slack connected as %s (team: %s)", data.get("user"), data.get("team"))
```

### Fix E — Status Endpoint Update

`GET /api/config/connectors` includes `"last_error": connector.last_error` for each connector name present in `registry._connectors` (i.e., `start()` was called on it). If the connector is not in `_connectors` at all (never started), `last_error` is omitted. Web UI displays this string in the error state.

### Part F — Connector CLI (`steelclaw/cli/connectors_cmd.py`)

New file. `handle_connectors(args)` routes to:

| Subcommand | Implementation |
|---|---|
| `list` | `GET /api/config/connectors` → Rich table: Name \| Status \| Error |
| `configure [name]` | If name omitted: `questionary.select` from connector list. For each connector, a static per-connector field definition dict maps connector name → list of `{key, label, type}` entries (e.g., Slack: `token`, `app_token`; Telegram: `token`; Discord: `token`). Prompts each field with `questionary.password()` for secret types. Saves via `PUT /api/config/connectors/{name}`. Confirms success. |
| `enable <name>` | `PUT /api/config/connectors/{name}` with `{"enabled": true}` → live-starts. Prints status. |
| `disable <name>` | `PUT /api/config/connectors/{name}` with `{"enabled": false}` → live-stops. |
| `status <name>` | `GET /api/config/connectors` → prints status, last_error, masked config for named connector. |

Each subcommand supports `--help`. All secret values masked as `****<last4>` in output.

Wire into `steelclaw/cli/__init__.py` main argparse under `steelclaw connectors`.

**Test:** Mock `ConnectorRegistry.start_connector`; assert `PUT` with `enabled: true` returns `{"status": "running"}` and triggers `start_connector`.

---

## Shared Constraints

- `questionary` added as a dependency — used by both skills interactive config and connectors configure.
- All secret fields masked in CLI output and Web UI (show `****<last4>`).
- Existing `steelclaw skills configure <skill>` (named form) behavior is unchanged.
- All new CLI subcommands print short help on `--help`.
- No changes to credential storage paths — `config.json` remains the single global store for both CLI and Web UI.
