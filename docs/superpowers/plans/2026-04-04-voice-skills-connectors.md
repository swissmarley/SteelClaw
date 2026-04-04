# Voice Memory/Persona + Skill Credential Sync + Slack Connector Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three bugs: voice sessions missing persona/memory context, skill credentials not syncing between CLI and running server, and the Slack connector showing "enabled" without starting — plus add interactive CLI menus for skills and connector management.

**Architecture:** Minimal, targeted changes to existing files. No new abstractions beyond what's necessary. The three task groups are independent and can be worked sequentially. Group A touches `api/voice.py`. Group B touches `skills/registry.py` and `cli/skills_cmd.py`. Group C touches `gateway/base.py`, `gateway/registry.py`, `gateway/connectors/slack.py`, `api/config.py`, and adds a new `cli/connectors_cmd.py`.

**Tech Stack:** Python 3.9+, FastAPI, SQLAlchemy async, `questionary` (already in deps), `httpx`, `rich`, `pytest-asyncio`.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `steelclaw/api/voice.py` | Modify | Inject persona + memory into realtime session instructions |
| `steelclaw/skills/registry.py` | Modify | Disk fallback in `_is_skill_configured` and `get_skill_credentials` |
| `steelclaw/cli/skills_cmd.py` | Modify | Add interactive configure flow when no skill name given |
| `steelclaw/gateway/base.py` | Modify | Add `last_error`, `is_running`, and `verify()` to `BaseConnector` |
| `steelclaw/gateway/registry.py` | Modify | Add `start_connector()` and `stop_connector()` |
| `steelclaw/gateway/connectors/slack.py` | Modify | Override `verify()` with `auth.test`, set `last_error` on fatal errors |
| `steelclaw/api/config.py` | Modify | Auto-start/stop connector in `PUT /connectors/{platform}`, include `last_error` in status |
| `steelclaw/cli/connectors_cmd.py` | Create | New CLI: `list`, `configure`, `enable`, `disable`, `status` |
| `steelclaw/__main__.py` | Modify | Wire `connectors` subcommand; make `skills configure name` optional |
| `tests/test_voice_stream.py` | Modify | Tests for persona + memory injection |
| `tests/test_skill_registry.py` | Modify | Tests for disk fallback |
| `tests/test_connectors_cmd.py` | Create | Tests for connector API behaviour |

---

## GROUP A — Voice Talk Mode Memory & Persona

### Task 1: Inject persona into voice realtime-session

**Files:**
- Modify: `tests/test_voice_stream.py`
- Modify: `steelclaw/api/voice.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_voice_stream.py`:

```python
async def test_realtime_session_injects_persona(voice_client):
    """Instructions must include the persona user name."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "sess_p1",
        "client_secret": {"value": "ek_p1"},
        "model": "gpt-4o-realtime-preview",
    }
    captured = {}

    async def capture_post(url, **kwargs):
        captured["payload"] = kwargs.get("json", {})
        return mock_resp

    with patch(
        "steelclaw.api.voice.build_persona_system_prompt",
        return_value="Your user's name is Alice. Address them by name.",
    ), patch("steelclaw.api.voice.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.post.side_effect = capture_post

        resp = await voice_client.post(
            "/api/voice/realtime-session",
            json={},
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    instructions = captured.get("payload", {}).get("instructions", "")
    assert "Alice" in instructions
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_voice_stream.py::test_realtime_session_injects_persona -v
```

Expected: FAIL — `"Alice"` not found in instructions (persona not yet injected).

- [ ] **Step 3: Implement persona injection in `steelclaw/api/voice.py`**

At the top of the file, after existing imports, add:

```python
from steelclaw.agents.persona_loader import build_persona_system_prompt
```

In `create_realtime_session`, replace the line:

```python
system_prompt = (
    agent.system_prompt if agent else settings.agents.llm.system_prompt
)
```

with:

```python
system_prompt = (
    agent.system_prompt if agent else settings.agents.llm.system_prompt
)

persona_prompt = build_persona_system_prompt()
parts = [persona_prompt]
if system_prompt:
    parts.append(system_prompt)
full_instructions = "\n\n".join(parts)
```

Then in the `payload` dict change `"instructions": system_prompt` to `"instructions": full_instructions`.

- [ ] **Step 4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_voice_stream.py::test_realtime_session_injects_persona -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite to check for regressions**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all 96 tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_voice_stream.py steelclaw/api/voice.py
git commit -m "fix: inject persona into voice realtime-session instructions"
```

---

### Task 2: Inject memory context into voice realtime-session

**Files:**
- Modify: `tests/test_voice_stream.py`
- Modify: `steelclaw/api/voice.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_voice_stream.py` — a new fixture that exposes both app and client:

```python
@pytest.fixture()
async def voice_app_and_client():
    """Like voice_client but also yields the app so we can set state."""
    from steelclaw.app import create_app
    app = create_app(_make_voice_settings())
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield app, ac
```

Then add the test:

```python
async def test_realtime_session_injects_memory(voice_app_and_client):
    """Instructions must include formatted memory context when retriever is set."""
    app, ac = voice_app_and_client

    mock_retriever = MagicMock()
    mock_retriever.retrieve_relevant.return_value = ["m1"]
    mock_retriever.format_for_prompt.return_value = "Memory: user prefers brevity."
    app.state.memory_retriever = mock_retriever

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "sess_m1",
        "client_secret": {"value": "ek_m1"},
        "model": "gpt-4o-realtime-preview",
    }
    captured = {}

    async def capture_post(url, **kwargs):
        captured["payload"] = kwargs.get("json", {})
        return mock_resp

    with patch(
        "steelclaw.api.voice.build_persona_system_prompt",
        return_value="Persona prefix.",
    ), patch("steelclaw.api.voice.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.post.side_effect = capture_post

        resp = await ac.post(
            "/api/voice/realtime-session",
            json={},
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    instructions = captured.get("payload", {}).get("instructions", "")
    assert "Memory: user prefers brevity." in instructions
    mock_retriever.retrieve_relevant.assert_called_once_with(
        query_text="user name preferences goals",
        namespace="memory_main",
        limit=5,
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_voice_stream.py::test_realtime_session_injects_memory -v
```

Expected: FAIL — memory context not in instructions.

- [ ] **Step 3: Implement memory injection in `steelclaw/api/voice.py`**

In `create_realtime_session`, after the `persona_prompt = build_persona_system_prompt()` line you added in Task 1, insert:

```python
memory_context = ""
memory_retriever = getattr(request.app.state, "memory_retriever", None)
if memory_retriever:
    try:
        memories = memory_retriever.retrieve_relevant(
            query_text="user name preferences goals",
            namespace="memory_main",
            limit=5,
        )
        memory_context = memory_retriever.format_for_prompt(memories)
    except Exception:
        logger.debug("Memory retrieval failed for voice session (non-critical)", exc_info=True)
```

Then change the `parts` list to include `memory_context`:

```python
parts = [persona_prompt]
if system_prompt:
    parts.append(system_prompt)
if memory_context:
    parts.append(memory_context)
full_instructions = "\n\n".join(parts)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_voice_stream.py::test_realtime_session_injects_memory -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all 97 tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_voice_stream.py steelclaw/api/voice.py
git commit -m "fix: inject memory context into voice realtime-session instructions"
```

---

## GROUP B — Skill Credential Sync + Interactive CLI

### Task 3: Disk fallback in SkillRegistry credential checks

**Files:**
- Modify: `tests/test_skill_registry.py`
- Modify: `steelclaw/skills/registry.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_skill_registry.py`. First, read the existing file to understand what fixtures exist, then add after the last test:

```python
def test_is_skill_configured_disk_fallback(tmp_path, monkeypatch):
    """_is_skill_configured falls back to disk when in-memory setting is empty."""
    from steelclaw.skills.registry import SkillRegistry
    from steelclaw.settings import SkillSettings
    from steelclaw.skills.loader import Skill, SkillMetadata, SkillTool

    # Build a minimal skill with one required credential
    meta = SkillMetadata(name="myskill", description="test", version="1.0")
    skill = Skill(
        name="myskill",
        metadata=meta,
        tools=[],
        path=tmp_path,
        scope="global",
        required_credentials=[{"key": "api_key", "label": "API Key", "type": "password"}],
    )

    settings = SkillSettings()
    # In-memory skill_configs is empty (simulating server loaded before CLI set creds)
    assert "myskill" not in settings.skill_configs

    registry = SkillRegistry(settings)
    registry._all_skills["myskill"] = skill
    registry._skills["myskill"] = skill

    # Write credential to disk (as CLI would)
    config_path = tmp_path / "config.json"
    import json
    config_path.write_text(json.dumps({
        "agents": {"skills": {"skill_configs": {"myskill": {"api_key": "sk-diskvalue"}}}}
    }))

    # Patch PROJECT_ROOT so credential_store reads from tmp_path
    monkeypatch.setattr("steelclaw.skills.credential_store.PROJECT_ROOT", tmp_path, raising=False)
    import steelclaw.skills.credential_store as cs
    monkeypatch.setattr(cs, "PROJECT_ROOT", tmp_path)

    # Should find the credential via disk fallback
    assert registry._is_skill_configured(skill) is True


def test_get_skill_credentials_disk_fallback(tmp_path, monkeypatch):
    """get_skill_credentials shows is_set=True when cred is on disk but not in memory."""
    from steelclaw.skills.registry import SkillRegistry
    from steelclaw.settings import SkillSettings
    from steelclaw.skills.loader import Skill, SkillMetadata

    meta = SkillMetadata(name="myskill", description="test", version="1.0")
    skill = Skill(
        name="myskill",
        metadata=meta,
        tools=[],
        path=tmp_path,
        scope="global",
        required_credentials=[{"key": "api_key", "label": "API Key", "type": "password"}],
    )

    settings = SkillSettings()
    registry = SkillRegistry(settings)
    registry._all_skills["myskill"] = skill

    import json
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "agents": {"skills": {"skill_configs": {"myskill": {"api_key": "sk-xyz1234"}}}}
    }))
    import steelclaw.skills.credential_store as cs
    monkeypatch.setattr(cs, "PROJECT_ROOT", tmp_path)

    creds = registry.get_skill_credentials("myskill")
    assert creds is not None
    assert creds[0]["is_set"] is True
    assert creds[0]["value"] == "****1234"
```

- [ ] **Step 2: Check what `SkillMetadata` and `Skill` look like in the loader**

```bash
python3 -c "from steelclaw.skills.loader import Skill, SkillMetadata; help(SkillMetadata.__init__)"
```

Read `steelclaw/skills/loader.py` if the above fails, and adjust the `SkillMetadata` constructor in the test to match the actual signature.

- [ ] **Step 3: Run the failing tests**

```bash
python3 -m pytest tests/test_skill_registry.py::test_is_skill_configured_disk_fallback tests/test_skill_registry.py::test_get_skill_credentials_disk_fallback -v
```

Expected: FAIL — no disk fallback implemented yet.

- [ ] **Step 4: Implement disk fallback in `steelclaw/skills/registry.py`**

Replace `_is_skill_configured`:

```python
def _is_skill_configured(self, skill: "Skill") -> bool:
    """Check if a skill's required credentials are all set.

    Checks in-memory settings first, then falls back to the on-disk credential
    store so credentials written by the CLI are visible without a server restart.
    """
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

Replace `get_skill_credentials`:

```python
def get_skill_credentials(self, name: str) -> list[dict] | None:
    """Return the skill's required_credentials with current values masked.

    Checks in-memory settings first, then falls back to the on-disk credential
    store so CLI-written credentials appear as configured in the Web UI.
    """
    skill = self._all_skills.get(name)
    if skill is None:
        return None
    stored = self._settings.skill_configs.get(name, {})
    result = []
    for cred in skill.required_credentials:
        value = stored.get(cred["key"], "")
        if not value:
            from steelclaw.skills.credential_store import get_credential
            value = get_credential(name, cred["key"]) or ""
        masked = ""
        if value:
            masked = "****" + value[-4:] if len(value) > 4 else "****"
        result.append({
            "key": cred["key"],
            "label": cred.get("label", cred["key"]),
            "type": cred.get("type", "password"),
            "test_url": cred.get("test_url"),
            "value": masked,
            "is_set": bool(value),
        })
    return result
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_skill_registry.py::test_is_skill_configured_disk_fallback tests/test_skill_registry.py::test_get_skill_credentials_disk_fallback -v
```

Expected: PASS.

- [ ] **Step 6: Run full suite**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_skill_registry.py steelclaw/skills/registry.py
git commit -m "fix: skill credential disk fallback so CLI-set creds visible without restart"
```

---

### Task 4: Interactive skill configure CLI

**Files:**
- Modify: `tests/test_skill_registry.py` (add CLI test)
- Modify: `steelclaw/cli/skills_cmd.py`
- Modify: `steelclaw/__main__.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_skill_registry.py`:

```python
def test_configure_skill_interactive_no_server(monkeypatch):
    """Interactive configure exits gracefully when server is not running."""
    import sys
    from unittest.mock import patch
    import httpx
    from steelclaw.cli.skills_cmd import _configure_skill

    with patch("steelclaw.cli.skills_cmd.httpx.get", side_effect=httpx.ConnectError("no server")):
        with pytest.raises(SystemExit):
            _configure_skill(None)


def test_configure_skill_named_writes_key_value(tmp_path, monkeypatch):
    """Named configure writes key=value pairs to config.json."""
    import json
    from unittest.mock import patch
    from steelclaw.cli.skills_cmd import _configure_skill

    config_path = tmp_path / "config.json"
    monkeypatch.setattr("steelclaw.cli.skills_cmd.PROJECT_ROOT", tmp_path, raising=False)
    # Patch paths module used inside skills_cmd
    import steelclaw.paths as paths_mod
    monkeypatch.setattr(paths_mod, "PROJECT_ROOT", tmp_path)

    inputs = iter(["api_key=sk-testvalue", ""])
    with patch("steelclaw.cli.skills_cmd.console") as mock_console:
        mock_console.input.side_effect = lambda _: next(inputs)
        _configure_skill("testskill")

    cfg = json.loads(config_path.read_text())
    assert cfg["agents"]["skills"]["skill_configs"]["testskill"]["api_key"] == "sk-testvalue"
```

- [ ] **Step 2: Run the failing tests**

```bash
python3 -m pytest tests/test_skill_registry.py::test_configure_skill_interactive_no_server tests/test_skill_registry.py::test_configure_skill_named_writes_key_value -v
```

Expected: `test_configure_skill_interactive_no_server` FAIL (no interactive path yet), `test_configure_skill_named_writes_key_value` may pass already.

- [ ] **Step 3: Implement interactive configure in `steelclaw/cli/skills_cmd.py`**

Replace `_configure_skill` (the single function that currently requires a name) with two functions:

```python
def _configure_skill(name: str | None) -> None:
    if name is not None:
        _configure_skill_named(name)
        return
    _configure_skill_interactive()


def _configure_skill_interactive() -> None:
    """Show a questionary skill-selection menu, then prompt for credentials."""
    import questionary

    try:
        resp = httpx.get(f"{BASE_URL}/api/skills", timeout=10)
        resp.raise_for_status()
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)

    skills = resp.json()
    skills_with_creds = [s for s in skills if s.get("required_credentials")]
    if not skills_with_creds:
        console.print("[dim]No skills require credentials[/dim]")
        return

    choices = []
    for s in skills_with_creds:
        # Fetch live credential status for this skill
        try:
            cred_resp = httpx.get(f"{BASE_URL}/api/skills/{s['name']}/credentials", timeout=10)
            creds = cred_resp.json().get("credentials", [])
            all_set = all(c.get("is_set") for c in creds) if creds else False
        except Exception:
            all_set = False
        status = "✓ configured" if all_set else "✗ not configured"
        choices.append(questionary.Choice(title=f"{s['name']}  [{status}]", value=s["name"]))

    selected = questionary.select(
        "Select a skill to configure:",
        choices=choices,
    ).ask()
    if not selected:
        return

    _configure_skill_named(selected)


def _configure_skill_named(name: str) -> None:
    """Configure a specific skill by prompting for each credential field."""
    # Try to fetch credential fields from the live server
    cred_fields: list[dict] = []
    try:
        cred_resp = httpx.get(f"{BASE_URL}/api/skills/{name}/credentials", timeout=10)
        if cred_resp.status_code == 200:
            cred_fields = cred_resp.json().get("credentials", [])
    except httpx.ConnectError:
        pass  # Fall through to manual key=value entry

    if cred_fields:
        import questionary
        console.print(f"[bold]Configure skill: {name}[/bold]")
        collected: dict[str, str] = {}
        for field in cred_fields:
            key = field["key"]
            label = field.get("label", key)
            is_secret = field.get("type") == "password"
            current_masked = field.get("value", "")
            if current_masked:
                label = f"{label} (currently set — leave blank to keep)"
            value = (
                questionary.password(f"{label}:").ask()
                if is_secret
                else questionary.text(f"{label}:").ask()
            )
            if value:
                collected[key] = value
        if not collected:
            console.print("[dim]No changes made[/dim]")
            return
        try:
            put_resp = httpx.put(
                f"{BASE_URL}/api/skills/{name}/credentials",
                json={"credentials": collected},
                timeout=10,
            )
            put_resp.raise_for_status()
            console.print(f"[green]✓ Credentials saved for {name}.[/green]")
        except httpx.ConnectError:
            console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
            sys.exit(1)
    else:
        # Fallback: manual key=value entry (server not running or skill not found)
        from steelclaw.paths import PROJECT_ROOT
        config_path = PROJECT_ROOT / "config.json"
        config = {}
        if config_path.exists():
            config = json.loads(config_path.read_text())

        agents = config.setdefault("agents", {})
        skills = agents.setdefault("skills", {})
        skill_configs = skills.setdefault("skill_configs", {})
        current = skill_configs.get(name, {})

        console.print(f"[bold]Configure skill: {name}[/bold]")
        if current:
            console.print(f"Current config: {json.dumps(current, indent=2)}")

        console.print("Enter key=value pairs (empty line to finish):")
        while True:
            line = console.input("> ").strip()
            if not line:
                break
            if "=" not in line:
                console.print("[red]Format: key=value[/red]")
                continue
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()

        skill_configs[name] = current
        config_path.write_text(json.dumps(config, indent=2))
        console.print(f"[green]Skill '{name}' configuration saved[/green]")
```

Also add `import json` at the top of `skills_cmd.py` if not already present.

- [ ] **Step 4: Make `name` optional in `__main__.py`**

Find this block in `steelclaw/__main__.py`:

```python
    skills_configure_p = skills_sub.add_parser("configure", help="Configure skill credentials")
    skills_configure_p.add_argument("name", help="Skill name")
```

Change to:

```python
    skills_configure_p = skills_sub.add_parser(
        "configure",
        help="Configure skill credentials (interactive menu if no name given)",
    )
    skills_configure_p.add_argument(
        "name", nargs="?", default=None, help="Skill name (omit for interactive menu)"
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_skill_registry.py::test_configure_skill_interactive_no_server tests/test_skill_registry.py::test_configure_skill_named_writes_key_value -v
```

Expected: PASS.

- [ ] **Step 6: Run full suite**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_skill_registry.py steelclaw/cli/skills_cmd.py steelclaw/__main__.py
git commit -m "feat: interactive skill configure menu + fix name optional arg"
```

---

## GROUP C — Slack Connector Fix + Connector CLI

### Task 5: Add `last_error`, `is_running`, and `verify()` to BaseConnector

**Files:**
- Modify: `tests/test_gateway.py`
- Modify: `steelclaw/gateway/base.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gateway.py`:

```python
def test_base_connector_last_error_default():
    """BaseConnector starts with last_error=None and is_running=False."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.base import BaseConnector
    from steelclaw.settings import ConnectorConfig

    class _DummyConnector(BaseConnector):
        platform_name = "dummy"
        async def _run(self): pass
        async def send(self, message): pass

    conn = _DummyConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=AsyncMock(),
    )
    assert conn.last_error is None
    assert conn.is_running is False


async def test_base_connector_verify_returns_none():
    """Default verify() returns None (no error)."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.base import BaseConnector
    from steelclaw.settings import ConnectorConfig

    class _DummyConnector(BaseConnector):
        platform_name = "dummy"
        async def _run(self): pass
        async def send(self, message): pass

    conn = _DummyConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=AsyncMock(),
    )
    result = await conn.verify()
    assert result is None
```

- [ ] **Step 2: Run the failing tests**

```bash
python3 -m pytest tests/test_gateway.py::test_base_connector_last_error_default tests/test_gateway.py::test_base_connector_verify_returns_none -v
```

Expected: FAIL — `last_error`, `is_running`, `verify` not defined yet.

- [ ] **Step 3: Implement in `steelclaw/gateway/base.py`**

In `BaseConnector.__init__`, add after the `_typing_tasks` line:

```python
        self.last_error: str | None = None
```

Add `is_running` property and `verify()` method after the `stop()` method:

```python
    @property
    def is_running(self) -> bool:
        """True if the connector task is active and has not finished."""
        return self._task is not None and not self._task.done()

    async def verify(self) -> str | None:
        """Pre-flight health check. Return None if OK, an error string if not.

        Subclasses override this to validate tokens before the connector starts.
        Called by ConnectorRegistry.start_connector() before creating the asyncio task.
        """
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_gateway.py::test_base_connector_last_error_default tests/test_gateway.py::test_base_connector_verify_returns_none -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_gateway.py steelclaw/gateway/base.py
git commit -m "feat: add last_error, is_running, verify() to BaseConnector"
```

---

### Task 6: Add live start_connector/stop_connector to ConnectorRegistry

**Files:**
- Modify: `tests/test_gateway.py`
- Modify: `steelclaw/gateway/registry.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gateway.py`:

```python
async def test_registry_start_connector():
    """start_connector starts a connector and adds it to _connectors."""
    from unittest.mock import AsyncMock, patch
    from steelclaw.gateway.registry import ConnectorRegistry
    from steelclaw.settings import ConnectorConfig, GatewaySettings

    settings = GatewaySettings()
    registry = ConnectorRegistry(settings)
    registry.set_handler(AsyncMock())

    conf = ConnectorConfig(enabled=True, token="tok-test")

    mock_connector = AsyncMock()
    mock_connector.last_error = None
    mock_connector.verify = AsyncMock(return_value=None)

    with patch.object(registry, "_import_connector", return_value=lambda **kw: mock_connector):
        result, error = await registry.start_connector("telegram", conf)

    assert error is None
    assert "telegram" in registry._connectors
    mock_connector.start.assert_called_once()


async def test_registry_start_connector_verify_failure():
    """start_connector returns error without starting task when verify() fails."""
    from unittest.mock import AsyncMock, patch
    from steelclaw.gateway.registry import ConnectorRegistry
    from steelclaw.settings import ConnectorConfig, GatewaySettings

    settings = GatewaySettings()
    registry = ConnectorRegistry(settings)
    registry.set_handler(AsyncMock())

    conf = ConnectorConfig(enabled=True, token="bad-tok")

    mock_connector = AsyncMock()
    mock_connector.last_error = None
    mock_connector.verify = AsyncMock(return_value="auth.test failed: invalid_auth")

    with patch.object(registry, "_import_connector", return_value=lambda **kw: mock_connector):
        result, error = await registry.start_connector("telegram", conf)

    assert error == "auth.test failed: invalid_auth"
    assert mock_connector.last_error == "auth.test failed: invalid_auth"
    mock_connector.start.assert_not_called()


async def test_registry_stop_connector():
    """stop_connector stops and removes a connector from _connectors."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.registry import ConnectorRegistry
    from steelclaw.settings import GatewaySettings

    settings = GatewaySettings()
    registry = ConnectorRegistry(settings)

    mock_connector = AsyncMock()
    registry._connectors["slack"] = mock_connector

    await registry.stop_connector("slack")

    mock_connector.stop.assert_called_once()
    assert "slack" not in registry._connectors
```

- [ ] **Step 2: Run the failing tests**

```bash
python3 -m pytest tests/test_gateway.py::test_registry_start_connector tests/test_gateway.py::test_registry_start_connector_verify_failure tests/test_gateway.py::test_registry_stop_connector -v
```

Expected: FAIL — `start_connector` / `stop_connector` not defined.

- [ ] **Step 3: Implement in `steelclaw/gateway/registry.py`**

Add these two methods to `ConnectorRegistry`, after `stop_all`:

```python
    async def start_connector(
        self, name: str, conf: "ConnectorConfig"
    ) -> tuple["BaseConnector | None", "str | None"]:
        """Import, verify, and start a single connector.

        Returns (connector, None) on success, (connector, error_string) if verify fails.
        If the connector name is unknown or import fails, returns (None, error_string).
        """
        if name not in _CONNECTOR_CLASSES:
            return None, f"Unknown connector: {name}"

        # Stop existing instance if running
        if name in self._connectors:
            await self._connectors[name].stop()
            del self._connectors[name]

        try:
            cls = self._import_connector(_CONNECTOR_CLASSES[name])
        except (ImportError, AttributeError) as exc:
            return None, f"Failed to import connector {name}: {exc}"

        connector = cls(config=conf, handler=self._handler or self._noop_handler)

        # Pre-flight check before creating asyncio task
        error = await connector.verify()
        if error:
            connector.last_error = error
            logger.error("Connector %s verify failed: %s", name, error)
            return connector, error

        await connector.start()
        self._connectors[name] = connector
        logger.info("Connector %s live-started", name)
        return connector, None

    async def stop_connector(self, name: str) -> None:
        """Stop and remove a single connector."""
        connector = self._connectors.pop(name, None)
        if connector:
            await connector.stop()
            logger.info("Connector %s stopped", name)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_gateway.py::test_registry_start_connector tests/test_gateway.py::test_registry_start_connector_verify_failure tests/test_gateway.py::test_registry_stop_connector -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_gateway.py steelclaw/gateway/registry.py
git commit -m "feat: add live start_connector/stop_connector to ConnectorRegistry"
```

---

### Task 7: Slack verify() + last_error on fatal errors

**Files:**
- Modify: `tests/test_gateway.py`
- Modify: `steelclaw/gateway/connectors/slack.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gateway.py`:

```python
async def test_slack_verify_missing_token():
    """verify() returns error string when bot token is missing."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.settings import ConnectorConfig

    conn = SlackConnector(
        config=ConnectorConfig(enabled=True, token=""),
        handler=AsyncMock(),
    )
    error = await conn.verify()
    assert error is not None
    assert "token" in error.lower()


async def test_slack_verify_missing_app_token():
    """verify() returns error string when app-level token is missing."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.settings import ConnectorConfig

    conn = SlackConnector(
        config=ConnectorConfig(enabled=True, token="xoxb-valid"),
        handler=AsyncMock(),
    )
    error = await conn.verify()
    assert error is not None
    assert "app" in error.lower() or "app_token" in error.lower()


async def test_slack_verify_auth_test_failure():
    """verify() returns error string when auth.test returns ok=false."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.settings import ConnectorConfig

    conn = SlackConnector(
        config=ConnectorConfig(enabled=True, token="xoxb-bad", app_token="xapp-test"),
        handler=AsyncMock(),
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": False, "error": "invalid_auth"}

    with patch("steelclaw.gateway.connectors.slack.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.post.return_value = mock_resp
        error = await conn.verify()

    assert error is not None
    assert "invalid_auth" in error


async def test_slack_verify_success():
    """verify() returns None when auth.test returns ok=true."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.settings import ConnectorConfig

    conn = SlackConnector(
        config=ConnectorConfig(enabled=True, token="xoxb-valid", app_token="xapp-valid"),
        handler=AsyncMock(),
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "user": "testbot", "team": "TestTeam"}

    with patch("steelclaw.gateway.connectors.slack.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.post.return_value = mock_resp
        error = await conn.verify()

    assert error is None
```

- [ ] **Step 2: Run the failing tests**

```bash
python3 -m pytest tests/test_gateway.py::test_slack_verify_missing_token tests/test_gateway.py::test_slack_verify_missing_app_token tests/test_gateway.py::test_slack_verify_auth_test_failure tests/test_gateway.py::test_slack_verify_success -v
```

Expected: FAIL — `verify()` not overridden on `SlackConnector`.

- [ ] **Step 3: Implement `verify()` in `steelclaw/gateway/connectors/slack.py`**

Add the following method to `SlackConnector`, between the class body and `_run`:

```python
    async def verify(self) -> str | None:
        """Validate Slack tokens via auth.test before starting the connector."""
        token = self.config.token
        app_token = self.config.extra.get("app_token", "")

        if not token:
            return "Slack bot token not configured (expected xoxb-...)"
        if not app_token:
            return "Slack app-level token not configured (expected xapp-...)"

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0,
                )
                data = resp.json()
                if not data.get("ok"):
                    return f"auth.test failed: {data.get('error', 'unknown')}"
                logger.info(
                    "Slack auth.test OK — bot: %s, team: %s",
                    data.get("user"),
                    data.get("team"),
                )
        except Exception as exc:
            return f"Slack connection error: {exc}"

        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_gateway.py::test_slack_verify_missing_token tests/test_gateway.py::test_slack_verify_missing_app_token tests/test_gateway.py::test_slack_verify_auth_test_failure tests/test_gateway.py::test_slack_verify_success -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_gateway.py steelclaw/gateway/connectors/slack.py
git commit -m "fix: add Slack verify() with auth.test health check"
```

---

### Task 8: Auto-start/stop connector on enable/disable in config API

**Files:**
- Create: `tests/test_connectors_cmd.py`
- Modify: `steelclaw/api/config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_connectors_cmd.py`:

```python
"""Tests for connector live-start/stop via the config API."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from steelclaw.settings import (
    AgentSettings, DatabaseSettings, GatewaySettings,
    LLMSettings, Settings,
)


def _make_settings():
    return Settings(
        database=DatabaseSettings(url="sqlite+aiosqlite://", echo=False),
        gateway=GatewaySettings(dm_allowlist_enabled=False),
        agents=AgentSettings(llm=LLMSettings(api_key="sk-test")),
    )


@pytest.fixture()
async def config_app_client():
    from steelclaw.app import create_app
    app = create_app(_make_settings())
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield app, ac


async def test_enable_connector_calls_start(config_app_client):
    """PUT /api/config/connectors/slack with enabled=true calls start_connector."""
    app, ac = config_app_client

    mock_connector = MagicMock()
    mock_connector.last_error = None
    mock_connector.verify = AsyncMock(return_value=None)
    mock_connector.start = AsyncMock()

    with patch.object(
        app.state.registry, "start_connector", return_value=(mock_connector, None)
    ) as mock_start:
        resp = await ac.put(
            "/api/config/connectors/slack",
            json={
                "enabled": True,
                "token": "xoxb-test",
                "app_token": "xapp-test",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    mock_start.assert_called_once()


async def test_enable_connector_returns_error_on_verify_fail(config_app_client):
    """PUT with enabled=true returns status=error when verify fails."""
    app, ac = config_app_client

    mock_connector = MagicMock()
    mock_connector.last_error = "auth.test failed: invalid_auth"

    with patch.object(
        app.state.registry,
        "start_connector",
        return_value=(mock_connector, "auth.test failed: invalid_auth"),
    ):
        resp = await ac.put(
            "/api/config/connectors/slack",
            json={"enabled": True, "token": "bad"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "invalid_auth" in data["message"]


async def test_disable_connector_calls_stop(config_app_client):
    """PUT /api/config/connectors/slack with enabled=false calls stop_connector."""
    app, ac = config_app_client

    with patch.object(app.state.registry, "stop_connector", new_callable=AsyncMock) as mock_stop:
        resp = await ac.put(
            "/api/config/connectors/slack",
            json={"enabled": False},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"
    mock_stop.assert_called_once_with("slack")


async def test_connectors_status_includes_last_error(config_app_client):
    """GET /api/config/connectors includes last_error for failed connectors."""
    app, ac = config_app_client

    mock_connector = MagicMock()
    mock_connector._task = MagicMock()
    mock_connector._task.done.return_value = True  # task finished (failed)
    mock_connector.last_error = "auth.test failed: invalid_auth"
    app.state.registry._connectors["slack"] = mock_connector

    # Also add slack to gateway config so it appears in the response
    import json
    from steelclaw.api.config import CONFIG_PATH
    cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    cfg.setdefault("gateway", {}).setdefault("connectors", {})["slack"] = {
        "enabled": True, "token": "xoxb-test"
    }
    CONFIG_PATH.write_text(json.dumps(cfg))

    resp = await ac.get("/api/config/connectors")
    assert resp.status_code == 200
    slack_info = resp.json()["connectors"].get("slack", {})
    assert slack_info.get("last_error") == "auth.test failed: invalid_auth"
```

- [ ] **Step 2: Run the failing tests**

```bash
python3 -m pytest tests/test_connectors_cmd.py -v
```

Expected: FAIL — auto-start/stop logic not yet in config API.

- [ ] **Step 3: Implement in `steelclaw/api/config.py`**

Replace the `update_connector_config` endpoint:

```python
@router.put("/connectors/{platform}")
async def update_connector_config(platform: str, request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data.setdefault("gateway", {}).setdefault("connectors", {})[platform] = body
    _write_config(data)

    from steelclaw.gateway.registry import ConnectorRegistry
    from steelclaw.settings import ConnectorConfig

    registry: ConnectorRegistry = request.app.state.registry

    if body.get("enabled"):
        try:
            conf = ConnectorConfig.model_validate(body)
        except Exception:
            conf = ConnectorConfig(enabled=True, token=body.get("token"))
        connector, error = await registry.start_connector(platform, conf)
        if error:
            return {"status": "error", "message": error, "section": f"connectors.{platform}"}
        return {"status": "running", "section": f"connectors.{platform}"}
    else:
        await registry.stop_connector(platform)
        return {"status": "disabled", "section": f"connectors.{platform}"}
```

Update `get_connectors_status` to include `last_error`:

```python
@router.get("/connectors")
async def get_connectors_status(request: Request) -> dict:
    """Return connector config + live status."""
    from steelclaw.gateway.registry import ConnectorRegistry

    registry: ConnectorRegistry = request.app.state.registry
    data = _read_config()
    connectors_cfg = data.get("gateway", {}).get("connectors", {})

    result = {}
    for name, cfg in connectors_cfg.items():
        connector = registry.get(name)
        if connector and connector._task and not connector._task.done():
            status = "running"
        elif cfg.get("enabled"):
            status = "enabled_not_running"
        else:
            status = "disabled"
        entry = {
            "enabled": cfg.get("enabled", False),
            "status": status,
            "config": _mask_secrets(cfg),
        }
        if connector and connector.last_error:
            entry["last_error"] = connector.last_error
        result[name] = entry
    return {"connectors": result}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_connectors_cmd.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_connectors_cmd.py steelclaw/api/config.py
git commit -m "fix: auto-start/stop connector on enable/disable, expose last_error in status"
```

---

### Task 9: Create `steelclaw/cli/connectors_cmd.py`

**Files:**
- Create: `steelclaw/cli/connectors_cmd.py`
- Modify: `tests/test_connectors_cmd.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_connectors_cmd.py`:

```python
def test_connectors_list_no_server(monkeypatch):
    """connectors list exits gracefully when server is not running."""
    import sys, httpx
    from steelclaw.cli.connectors_cmd import _list_connectors
    with patch("steelclaw.cli.connectors_cmd.httpx.get", side_effect=httpx.ConnectError("no server")):
        with pytest.raises(SystemExit):
            _list_connectors()


def test_connectors_enable_calls_put(monkeypatch):
    """connectors enable calls PUT with enabled=true."""
    import httpx
    from unittest.mock import MagicMock
    from steelclaw.cli.connectors_cmd import _enable_connector

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "running"}
    mock_resp.raise_for_status = MagicMock()

    with patch("steelclaw.cli.connectors_cmd.httpx.get") as mock_get, \
         patch("steelclaw.cli.connectors_cmd.httpx.put", return_value=mock_resp) as mock_put:
        # Need existing config so PUT has something to merge
        mock_get.return_value = MagicMock(
            json=lambda: {"connectors": {"slack": {"enabled": False, "token": "tok"}}}
        )
        _enable_connector("slack")

    mock_put.assert_called_once()
    call_json = mock_put.call_args.kwargs.get("json") or mock_put.call_args[1].get("json", {})
    assert call_json.get("enabled") is True


def test_connectors_disable_calls_put(monkeypatch):
    """connectors disable calls PUT with enabled=false."""
    from unittest.mock import MagicMock
    from steelclaw.cli.connectors_cmd import _disable_connector

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "disabled"}
    mock_resp.raise_for_status = MagicMock()

    with patch("steelclaw.cli.connectors_cmd.httpx.get") as mock_get, \
         patch("steelclaw.cli.connectors_cmd.httpx.put", return_value=mock_resp) as mock_put:
        mock_get.return_value = MagicMock(
            json=lambda: {"connectors": {"slack": {"enabled": True, "token": "tok"}}}
        )
        _disable_connector("slack")

    mock_put.assert_called_once()
    call_json = mock_put.call_args.kwargs.get("json") or mock_put.call_args[1].get("json", {})
    assert call_json.get("enabled") is False
```

- [ ] **Step 2: Run the failing tests**

```bash
python3 -m pytest tests/test_connectors_cmd.py::test_connectors_list_no_server tests/test_connectors_cmd.py::test_connectors_enable_calls_put tests/test_connectors_cmd.py::test_connectors_disable_calls_put -v
```

Expected: FAIL — `connectors_cmd` module doesn't exist yet.

- [ ] **Step 3: Create `steelclaw/cli/connectors_cmd.py`**

```python
"""CLI connector management — list, configure, enable, disable, status."""

from __future__ import annotations

import json
import sys

import httpx
from rich.console import Console
from rich.table import Table

console = Console()
BASE_URL = "http://localhost:8000"

# Per-connector credential field definitions.
# Each entry: list of {key, label, type} where type is "password" or "text".
_CONNECTOR_FIELDS: dict[str, list[dict]] = {
    "slack": [
        {"key": "token", "label": "Bot Token (xoxb-...)", "type": "password"},
        {"key": "app_token", "label": "App-Level Token (xapp-...)", "type": "password"},
    ],
    "telegram": [
        {"key": "token", "label": "Bot Token", "type": "password"},
    ],
    "discord": [
        {"key": "token", "label": "Bot Token", "type": "password"},
    ],
    "whatsapp": [
        {"key": "token", "label": "API Token", "type": "password"},
    ],
    "signal": [
        {"key": "token", "label": "API Token", "type": "password"},
    ],
    "matrix": [
        {"key": "token", "label": "Access Token", "type": "password"},
        {"key": "homeserver", "label": "Homeserver URL (e.g. https://matrix.org)", "type": "text"},
    ],
    "mattermost": [
        {"key": "token", "label": "Bot Token", "type": "password"},
    ],
    "teams": [
        {"key": "token", "label": "Bot Token", "type": "password"},
        {"key": "signing_secret", "label": "Signing Secret", "type": "password"},
    ],
    "imessage": [
        {"key": "token", "label": "API Token", "type": "password"},
    ],
}


def handle_connectors(args) -> None:
    action = getattr(args, "connectors_action", None)
    if action == "list":
        _list_connectors()
    elif action == "configure":
        _configure_connector(getattr(args, "name", None))
    elif action == "enable":
        _enable_connector(args.name)
    elif action == "disable":
        _disable_connector(args.name)
    elif action == "status":
        _status_connector(args.name)
    else:
        _list_connectors()


def _get_connectors() -> dict:
    """Fetch connector status from the running server."""
    try:
        resp = httpx.get(f"{BASE_URL}/api/config/connectors", timeout=10)
        resp.raise_for_status()
        return resp.json().get("connectors", {})
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _list_connectors() -> None:
    connectors = _get_connectors()
    if not connectors:
        console.print("[dim]No connectors configured[/dim]")
        return

    table = Table(title="Connectors")
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("Error", style="red")

    for name, info in connectors.items():
        status = info.get("status", "unknown")
        if status == "running":
            status_str = "[green]running[/green]"
        elif status == "enabled_not_running":
            status_str = "[yellow]enabled (not running)[/yellow]"
        else:
            status_str = "[dim]disabled[/dim]"
        error = info.get("last_error", "")
        table.add_row(name, status_str, error or "")

    console.print(table)


def _configure_connector(name: str | None) -> None:
    if name is None:
        _configure_connector_interactive()
    else:
        _configure_connector_named(name)


def _configure_connector_interactive() -> None:
    import questionary

    connectors = _get_connectors()
    all_names = list(_CONNECTOR_FIELDS.keys())

    choices = []
    for cname in all_names:
        info = connectors.get(cname, {})
        status = info.get("status", "disabled")
        status_label = "running" if status == "running" else ("enabled" if "enabled" in status else "disabled")
        choices.append(questionary.Choice(title=f"{cname}  [{status_label}]", value=cname))

    selected = questionary.select("Select a connector to configure:", choices=choices).ask()
    if not selected:
        return
    _configure_connector_named(selected)


def _configure_connector_named(name: str) -> None:
    import questionary

    fields = _CONNECTOR_FIELDS.get(name)
    if not fields:
        console.print(f"[red]Unknown connector '{name}'. Known: {', '.join(_CONNECTOR_FIELDS)}[/red]")
        return

    # Fetch current config to pre-populate non-secret fields
    connectors = _get_connectors()
    current_cfg = connectors.get(name, {}).get("config", {})

    console.print(f"[bold]Configure connector: {name}[/bold]")
    collected: dict = {"enabled": current_cfg.get("enabled", False)}

    for field in fields:
        key = field["key"]
        label = field["label"]
        is_secret = field["type"] == "password"
        current_val = current_cfg.get(key, "")

        if is_secret and current_val:
            prompt_label = f"{label} (currently set — leave blank to keep)"
        else:
            prompt_label = label

        value = (
            questionary.password(f"{prompt_label}:").ask()
            if is_secret
            else questionary.text(f"{prompt_label}:", default=current_val or "").ask()
        )
        if value:
            collected[key] = value
        elif current_val and is_secret:
            pass  # keep existing masked value — don't overwrite

    try:
        resp = httpx.put(
            f"{BASE_URL}/api/config/connectors/{name}",
            json=collected,
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == "error":
            console.print(f"[red]Error: {result.get('message')}[/red]")
        else:
            console.print(f"[green]✓ Connector '{name}' configured.[/green]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _enable_connector(name: str) -> None:
    connectors = _get_connectors()
    current_cfg = connectors.get(name, {}).get("config", {})
    payload = dict(current_cfg)
    payload["enabled"] = True

    try:
        resp = httpx.put(
            f"{BASE_URL}/api/config/connectors/{name}",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == "error":
            console.print(f"[red]Connector '{name}' failed to start: {result.get('message')}[/red]")
        elif result.get("status") == "running":
            console.print(f"[green]Connector '{name}' is now running.[/green]")
        else:
            console.print(f"[yellow]Connector '{name}' status: {result.get('status')}[/yellow]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _disable_connector(name: str) -> None:
    connectors = _get_connectors()
    current_cfg = connectors.get(name, {}).get("config", {})
    payload = dict(current_cfg)
    payload["enabled"] = False

    try:
        resp = httpx.put(
            f"{BASE_URL}/api/config/connectors/{name}",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        console.print(f"[yellow]Connector '{name}' disabled.[/yellow]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _status_connector(name: str) -> None:
    connectors = _get_connectors()
    info = connectors.get(name)
    if info is None:
        console.print(f"[red]Connector '{name}' not found in config.[/red]")
        return

    status = info.get("status", "unknown")
    console.print(f"[bold]{name}[/bold]")
    console.print(f"  Status:  {status}")
    if info.get("last_error"):
        console.print(f"  Error:   [red]{info['last_error']}[/red]")
    cfg = info.get("config", {})
    if cfg:
        console.print("  Config:")
        for k, v in cfg.items():
            if k == "enabled":
                continue
            console.print(f"    {k}: {v}")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_connectors_cmd.py::test_connectors_list_no_server tests/test_connectors_cmd.py::test_connectors_enable_calls_put tests/test_connectors_cmd.py::test_connectors_disable_calls_put -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add steelclaw/cli/connectors_cmd.py tests/test_connectors_cmd.py
git commit -m "feat: add connectors_cmd CLI with list/configure/enable/disable/status"
```

---

### Task 10: Wire `connectors` subcommand into `__main__.py`

**Files:**
- Modify: `steelclaw/__main__.py`

- [ ] **Step 1: Add `cmd_connectors` function**

In `steelclaw/__main__.py`, add this function after `cmd_gateway`:

```python
def cmd_connectors(args: argparse.Namespace) -> None:
    """Manage gateway connectors (list, configure, enable, disable, status)."""
    from steelclaw.cli.connectors_cmd import handle_connectors
    handle_connectors(args)
```

- [ ] **Step 2: Add connectors subparser**

In the `main()` function, after the `gateway` subparser block, add:

```python
    # connectors
    connectors_p = sub.add_parser("connectors", help="Manage gateway connectors")
    connectors_sub = connectors_p.add_subparsers(dest="connectors_action")
    connectors_sub.add_parser("list", help="List all connectors with status")
    connectors_configure_p = connectors_sub.add_parser(
        "configure",
        help="Configure connector credentials (interactive if no name given)",
    )
    connectors_configure_p.add_argument(
        "name", nargs="?", default=None, help="Connector name (omit for interactive menu)"
    )
    connectors_enable_p = connectors_sub.add_parser("enable", help="Enable and start a connector")
    connectors_enable_p.add_argument("name", help="Connector name")
    connectors_disable_p = connectors_sub.add_parser("disable", help="Stop and disable a connector")
    connectors_disable_p.add_argument("name", help="Connector name")
    connectors_status_p = connectors_sub.add_parser("status", help="Show connector status and config")
    connectors_status_p.add_argument("name", help="Connector name")
```

- [ ] **Step 3: Register handler in the commands dict**

In the `commands` dict in `main()`, add:

```python
        "connectors": cmd_connectors,
```

- [ ] **Step 4: Verify the CLI is wired correctly**

```bash
python3 -m steelclaw connectors --help
python3 -m steelclaw connectors list --help
python3 -m steelclaw connectors enable --help
```

Expected: help text printed for each without errors.

- [ ] **Step 5: Run full suite one final time**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass (should be ~110+ tests at this point).

- [ ] **Step 6: Commit**

```bash
git add steelclaw/__main__.py
git commit -m "feat: wire connectors CLI subcommand into steelclaw __main__"
```

---

## Self-Review Checklist (run before declaring done)

- [ ] All spec requirements mapped to tasks:
  - Task 1+2: voice persona + memory ✓
  - Task 3: skill credential disk fallback ✓
  - Task 4: interactive skill configure CLI ✓
  - Task 5: BaseConnector `last_error`/`is_running`/`verify()` ✓
  - Task 6: `start_connector`/`stop_connector` ✓
  - Task 7: Slack `verify()` with `auth.test` ✓
  - Task 8: config API auto-start/stop + `last_error` in status ✓
  - Task 9: `connectors_cmd.py` ✓
  - Task 10: CLI wiring ✓
- [ ] `questionary` already in `pyproject.toml` — no change needed ✓
- [ ] Existing `steelclaw skills configure <skill>` still works (name is now `nargs="?"`) ✓
- [ ] Secret masking in connector status output (via existing `_mask_secrets`) ✓
- [ ] `--help` on all new subcommands works (argparse handles this automatically) ✓
