# SteelClaw UI Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform SteelClaw into a premium glassmorphic AI assistant with reliable tool initialization, API key management with verification, chunked voice streaming, and an enhanced settings page.

**Architecture:** Five features implemented in order of dependency: (1) backend tool init defaults, (2) backend credential endpoints + skill declarations, (3) backend voice streaming, (4) complete frontend glassmorphism rewrite, (5) enhanced settings + credential modal + voice UI integrated into the new frontend. The frontend is a single `index.html` file — all CSS/JS/HTML lives there.

**Tech Stack:** Python/FastAPI backend, vanilla JS/CSS/HTML frontend, OpenAI TTS API, Web Audio API, CSS `backdrop-filter` for glass effects.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `steelclaw/skills/bundled/web_search/__init__.py` | Modify | Add `default_enabled = True`, `required_credentials = []` |
| `steelclaw/skills/registry.py` | Modify | Honor `default_enabled`, add credential helpers |
| `steelclaw/skills/loader.py` | Modify | Load `default_enabled` and `required_credentials` from skill modules |
| `steelclaw/app.py` | Modify | Post-load verification of critical skills |
| `steelclaw/api/skills.py` | Modify | Add 3 credential endpoints |
| `steelclaw/api/voice.py` | Modify | Add `synthesize-stream` endpoint |
| `steelclaw/web/static/index.html` | Rewrite | Glassmorphism UI, voice panel, settings overhaul, credential modal |
| `tests/test_skill_registry.py` | Modify | Tests for default_enabled + credential features |
| `tests/test_voice_stream.py` | Create | Tests for sentence chunking logic |

---

### Task 1: Skill Default-Enabled Flag

**Files:**
- Modify: `steelclaw/skills/loader.py`
- Modify: `steelclaw/skills/bundled/web_search/__init__.py`
- Modify: `steelclaw/skills/registry.py`
- Modify: `steelclaw/app.py`
- Test: `tests/test_skill_registry.py`

- [ ] **Step 1: Write failing test for default_enabled behavior**

```python
# tests/test_skill_registry.py — add this test

import pytest
from unittest.mock import MagicMock, patch
from steelclaw.skills.registry import SkillRegistry
from steelclaw.settings import SkillSettings


def _make_mock_skill(name, default_enabled=False):
    """Create a mock Skill object."""
    skill = MagicMock()
    skill.name = name
    skill.default_enabled = default_enabled
    skill.tools = []
    skill.metadata = MagicMock()
    skill.metadata.triggers = []
    return skill


def test_default_enabled_skill_not_disabled():
    """Skills with default_enabled=True should remain active even if not explicitly enabled."""
    settings = SkillSettings(disabled_skills=["web_search"])
    registry = SkillRegistry(settings)

    mock_web = _make_mock_skill("web_search", default_enabled=True)
    mock_other = _make_mock_skill("other_skill", default_enabled=False)

    with patch("steelclaw.skills.registry.discover_skills", return_value=[mock_web, mock_other]):
        registry.load_all()

    # web_search should be active because default_enabled=True
    assert registry.get_skill("web_search") is not None
    # other_skill should be disabled since it was in disabled_skills... wait, it wasn't
    # Let's test: a default_enabled skill survives being in disabled_skills
    assert "web_search" not in registry.disabled_skills


def test_non_default_skill_stays_disabled():
    """Skills without default_enabled should stay disabled when in disabled_skills list."""
    settings = SkillSettings(disabled_skills=["other_skill"])
    registry = SkillRegistry(settings)

    mock_other = _make_mock_skill("other_skill", default_enabled=False)

    with patch("steelclaw.skills.registry.discover_skills", return_value=[mock_other]):
        registry.load_all()

    assert registry.get_skill("other_skill") is None
    assert "other_skill" in registry.disabled_skills
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/SSD/ClaudeProjects/SteelClaw && python -m pytest tests/test_skill_registry.py::test_default_enabled_skill_not_disabled -v`
Expected: FAIL — `Skill` objects don't have `default_enabled` attribute yet

- [ ] **Step 3: Add `default_enabled` to Skill class in loader.py**

In `steelclaw/skills/loader.py`, modify the `Skill` class to accept and store `default_enabled`:

```python
# In the Skill class __init__ (or dataclass), add:
self.default_enabled: bool = default_enabled
```

And in `load_skill_from_directory`, after loading the module, read `default_enabled`:

```python
# After _load_executors call:
default_enabled = getattr(module, "default_enabled", False) if module else False
```

Pass it to the `Skill` constructor.

- [ ] **Step 4: Add `default_enabled = True` to web_search skill**

In `steelclaw/skills/bundled/web_search/__init__.py`, add at the top (after the docstring):

```python
default_enabled = True
```

- [ ] **Step 5: Modify `SkillRegistry.load_all()` to honor `default_enabled`**

In `steelclaw/skills/registry.py`, modify `load_all()`. Replace the disabled check:

```python
        for skill in skills:
            self._all_skills[skill.name] = skill
            # Skills with default_enabled=True cannot be disabled
            if skill.default_enabled and skill.name in self._disabled:
                self._disabled.discard(skill.name)
                logger.info("Skill '%s' is default-enabled — overriding disabled state", skill.name)
            if skill.name in self._disabled:
                logger.info("Skill '%s' is disabled — skipping", skill.name)
                continue
            self._skills[skill.name] = skill
            for tool in skill.tools:
                if tool.name in self._tool_index:
                    prev_skill = self._tool_index[tool.name]
                    logger.warning(
                        "Tool name collision: '%s' in skill '%s' overrides '%s'",
                        tool.name, skill.name, prev_skill.name,
                    )
                self._tool_index[tool.name] = skill
```

- [ ] **Step 6: Add post-load verification in `app.py`**

In `steelclaw/app.py`, after `skill_registry.load_all()`, add:

```python
    # Verify critical skills loaded
    for critical in ("web_search",):
        if skill_registry.get_skill(critical) is None:
            logger.warning("Critical skill '%s' failed to load — agent may lack web access", critical)
        else:
            logger.info("Critical skill '%s' loaded OK", critical)
```

- [ ] **Step 7: Run tests**

Run: `cd /Volumes/SSD/ClaudeProjects/SteelClaw && python -m pytest tests/test_skill_registry.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add steelclaw/skills/loader.py steelclaw/skills/registry.py steelclaw/skills/bundled/web_search/__init__.py steelclaw/app.py tests/test_skill_registry.py
git commit -m "feat: add default_enabled flag for critical skills like web_search"
```

---

### Task 2: Skill Credential Declaration & Backend Endpoints

**Files:**
- Modify: `steelclaw/skills/loader.py`
- Modify: `steelclaw/skills/registry.py`
- Modify: `steelclaw/api/skills.py`
- Modify: `steelclaw/settings.py`

- [ ] **Step 1: Add `required_credentials` loading to skill loader**

In `steelclaw/skills/loader.py`, in `load_skill_from_directory` (or `_load_executors`), after loading the module, read:

```python
required_credentials = getattr(module, "required_credentials", []) if module else []
```

Store it on the `Skill` object:

```python
self.required_credentials: list[dict] = required_credentials
```

Each dict has shape: `{"key": str, "label": str, "type": "password"|"text", "test_url": str|None}`

- [ ] **Step 2: Add credential helpers to SkillRegistry**

In `steelclaw/skills/registry.py`, add two methods:

```python
    def get_skill_credentials(self, name: str) -> list[dict] | None:
        """Return the skill's required_credentials with current values masked."""
        skill = self._all_skills.get(name)
        if skill is None:
            return None
        stored = self._settings.skill_configs.get(name, {})
        result = []
        for cred in skill.required_credentials:
            value = stored.get(cred["key"], "")
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

    def set_skill_credentials(self, name: str, credentials: dict[str, str]) -> bool:
        """Save credentials for a skill into skill_configs."""
        skill = self._all_skills.get(name)
        if skill is None:
            return False
        if name not in self._settings.skill_configs:
            self._settings.skill_configs[name] = {}
        for key, value in credentials.items():
            if value and not value.startswith("****"):
                self._settings.skill_configs[name][key] = value
        return True
```

- [ ] **Step 3: Add 3 credential API endpoints**

In `steelclaw/api/skills.py`, add:

```python
from pydantic import BaseModel


class CredentialUpdate(BaseModel):
    credentials: dict[str, str]


@router.get("/{skill_name}/credentials")
async def get_skill_credentials(skill_name: str, request: Request) -> dict:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    creds = registry.get_skill_credentials(skill_name)
    if creds is None:
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    return {"skill": skill_name, "credentials": creds}


@router.put("/{skill_name}/credentials")
async def update_skill_credentials(
    skill_name: str, body: CredentialUpdate, request: Request
) -> dict:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    if not registry.set_skill_credentials(skill_name, body.credentials):
        raise HTTPException(404, f"Skill '{skill_name}' not found")

    # Persist to config.json using existing config module helper
    from steelclaw.api.config import _read_config, _write_config

    settings = request.app.state.settings
    cfg = _read_config()
    skill_configs = cfg.setdefault("agents", {}).setdefault("skills", {}).setdefault("skill_configs", {})
    skill_configs[skill_name] = settings.agents.skills.skill_configs.get(skill_name, {})
    _write_config(cfg)
    return {"status": "saved", "skill": skill_name}


@router.post("/{skill_name}/verify")
async def verify_skill_credentials(skill_name: str, request: Request) -> dict:
    import httpx
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    skill = registry.all_skills.get(skill_name)
    if skill is None:
        raise HTTPException(404, f"Skill '{skill_name}' not found")

    stored = request.app.state.settings.agents.skills.skill_configs.get(skill_name, {})
    results = []
    for cred in skill.required_credentials:
        key = cred["key"]
        test_url = cred.get("test_url")
        value = stored.get(key, "")

        if not value:
            results.append({"key": key, "status": "error", "message": "Not set"})
            continue
        if not test_url:
            results.append({"key": key, "status": "ok", "message": "Saved (no test URL)"})
            continue

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    test_url,
                    headers={"Authorization": f"Bearer {value}"},
                )
                if resp.status_code < 400:
                    results.append({"key": key, "status": "ok", "message": f"OK ({resp.status_code})"})
                elif resp.status_code == 401:
                    results.append({"key": key, "status": "error", "message": "Invalid API key (401)"})
                else:
                    results.append({"key": key, "status": "error", "message": f"HTTP {resp.status_code}"})
        except Exception as e:
            results.append({"key": key, "status": "error", "message": str(e)})

    return {"skill": skill_name, "results": results}


    # Persist to config.json using existing config module helper
    from steelclaw.api.config import _read_config, _write_config

    cfg = _read_config()
    skill_configs = cfg.setdefault("agents", {}).setdefault("skills", {}).setdefault("skill_configs", {})
    skill_configs[skill_name] = settings.agents.skills.skill_configs.get(skill_name, {})
    _write_config(cfg)
```

- [ ] **Step 4: Add `required_credentials` to a few example skills**

In `steelclaw/skills/bundled/web_search/__init__.py` (no keys needed):

```python
required_credentials = []
```

For skills that need API keys, add declarations. For example, in a skill like `steelclaw/skills/bundled/github_skill/__init__.py`:

```python
required_credentials = [
    {"key": "api_token", "label": "GitHub Token", "type": "password", "test_url": "https://api.github.com/user"},
]
```

Add similar declarations to 3-5 key skills that have obvious API key needs (openai_skill, slack_skill, notion, etc.). Skills without declarations get an empty list by default in the loader.

- [ ] **Step 5: Run tests**

Run: `cd /Volumes/SSD/ClaudeProjects/SteelClaw && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add steelclaw/skills/loader.py steelclaw/skills/registry.py steelclaw/api/skills.py steelclaw/skills/bundled/
git commit -m "feat: add API key management with verification endpoints for skills"
```

---

### Task 3: Voice Streaming Endpoint

**Files:**
- Modify: `steelclaw/api/voice.py`
- Create: `tests/test_voice_stream.py`

- [ ] **Step 1: Write test for sentence chunking logic**

```python
# tests/test_voice_stream.py

from steelclaw.api.voice import split_into_chunks


def test_split_basic_sentences():
    text = "Hello world. How are you? I am fine!"
    chunks = split_into_chunks(text)
    assert chunks == ["Hello world.", "How are you?", "I am fine!"]


def test_split_merges_short_chunks():
    text = "Hi. OK. This is a longer sentence that should stand alone."
    chunks = split_into_chunks(text, min_length=10)
    # "Hi. OK." gets merged because both are < 10 chars
    assert chunks == ["Hi. OK.", "This is a longer sentence that should stand alone."]


def test_split_single_sentence():
    text = "Just one sentence here"
    chunks = split_into_chunks(text)
    assert chunks == ["Just one sentence here"]


def test_split_empty():
    assert split_into_chunks("") == []
    assert split_into_chunks("   ") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/SSD/ClaudeProjects/SteelClaw && python -m pytest tests/test_voice_stream.py -v`
Expected: FAIL — `split_into_chunks` doesn't exist yet

- [ ] **Step 3: Implement `split_into_chunks` and streaming endpoint**

In `steelclaw/api/voice.py`, add:

```python
import re
from fastapi.responses import StreamingResponse


def split_into_chunks(text: str, min_length: int = 10) -> list[str]:
    """Split text into sentence-sized chunks for progressive TTS."""
    text = text.strip()
    if not text:
        return []
    # Split after sentence-ending punctuation followed by whitespace
    parts = re.split(r"(?<=[.!?])\s+", text)
    # Merge short chunks with the next one
    merged = []
    buffer = ""
    for part in parts:
        if buffer:
            buffer += " " + part
        else:
            buffer = part
        if len(buffer) >= min_length:
            merged.append(buffer)
            buffer = ""
    if buffer:
        if merged:
            merged[-1] += " " + buffer
        else:
            merged.append(buffer)
    return merged


@router.post("/synthesize-stream")
async def synthesize_stream(request: Request, body: TTSRequest):
    """Stream TTS audio in sentence-sized chunks for low-latency playback."""
    settings = request.app.state.settings.agents.voice

    if not settings.enabled:
        raise HTTPException(400, "Voice mode is not enabled in settings")

    chunks = split_into_chunks(body.text)
    if not chunks:
        raise HTTPException(400, "No text to synthesize")

    async def generate():
        from steelclaw.voice.tts import TextToSpeech
        import tempfile
        import uuid
        from pathlib import Path

        tts = TextToSpeech(settings)
        for chunk_text in chunks:
            output = Path(tempfile.gettempdir()) / f"sc_tts_{uuid.uuid4().hex}.mp3"
            result = await tts.synthesize(chunk_text, str(output), voice=body.voice or None)
            if result.ok:
                audio_bytes = output.read_bytes()
                yield audio_bytes
                output.unlink(missing_ok=True)

    return StreamingResponse(generate(), media_type="audio/mpeg")
```

- [ ] **Step 4: Run tests**

Run: `cd /Volumes/SSD/ClaudeProjects/SteelClaw && python -m pytest tests/test_voice_stream.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add steelclaw/api/voice.py tests/test_voice_stream.py
git commit -m "feat: add chunked TTS streaming for low-latency voice responses"
```

---

### Task 4: Glassmorphism UI — Complete Frontend Rewrite

This is the largest task. The entire `index.html` (1385 lines) gets rewritten with the new design system. The structure (pages, sidebar, chat) stays the same but every visual element changes.

**Files:**
- Rewrite: `steelclaw/web/static/index.html`

- [ ] **Step 1: Write the complete new `index.html`**

The new file replaces the entire existing file. Key changes:

**CSS (top of file):**
- Replace all CSS variables with glassmorphism palette
- Add `@import` for Inter and JetBrains Mono from Google Fonts
- Add animated gradient background (2-3 radial-gradient circles with `@keyframes drift`)
- Replace all `background: var(--surface)` with glass: `rgba(255,255,255,0.05)` + `backdrop-filter: blur(20px)` + `border: 1px solid rgba(255,255,255,0.08)`
- Add `.glass` utility class for reuse
- Replace sidebar styling: frosted glass panel, active item = gradient pill with glow
- Replace chat messages: user = gradient accent pill, assistant = glass card with left border
- Replace inputs: glass background, focus glow ring `box-shadow: 0 0 0 2px rgba(139,92,246,0.3)`
- Replace buttons: primary = gradient `#8b5cf6→#6366f1` with glow on hover, secondary = glass
- Replace cards: glass panels with soft shadow `0 8px 32px rgba(0,0,0,0.3)`
- Replace toasts: slide from top-right, glass card with accent left border
- Replace command palette: glass modal with backdrop blur
- Add page transition animations: `@keyframes fadeInUp` (opacity 0→1, translateY 10px→0)
- Add hover lift on cards: `transform: translateY(-4px)` + brightness boost
- Add skeleton shimmer loading: `@keyframes shimmer`
- Custom scrollbar: thin, translucent, rounded
- Light mode: frosted white `rgba(255,255,255,0.6)` over soft lavender gradient

**HTML structure (same pages, updated classes):**
- Sidebar nav buttons use new active state
- All `.card` elements add `.glass` class
- Chat area adds voice panel overlay div
- Settings page gets tabbed layout structure
- Skills page cards get credential button

**JS (same logic, additions):**
- Page transitions: add `fadeInUp` class on page switch
- Voice panel: new voice overlay with orb animation, waveform canvas, transcript area
- Audio queue: `AudioContext` + chunk buffer queue for progressive playback
- Silence detection: `AnalyserNode` monitoring mic input for auto-submit
- Credential modal: open/close/save/verify functions
- Settings tabs: category navigation within settings page
- Appearance settings: accent color, font size, density stored in localStorage
- Voice settings additions: auto-submit toggle, silence threshold, playback speed

Write the COMPLETE new `index.html` file. It should be a fully working, self-contained file. All existing functionality must be preserved — every page, every API call, every loader function. The file will be roughly 2200-2500 lines.

**Key sections of the new file:**

1. `<head>` — Google Fonts link, all CSS
2. `<body>` — Animated background div, sidebar, main content area with all pages, command palette, shortcuts panel, voice overlay panel, credential modal, toast
3. `<script>` — All JS: helpers, WebSocket, theme, markdown, command palette, voice (with streaming + waveform + silence detection + audio queue), page loaders (settings with tabs, skills with credential modal, etc.), keyboard shortcuts

- [ ] **Step 2: Verify all existing pages still work**

Open the app in a browser and verify:
1. Chat — send a message, receive response, markdown renders
2. Settings — all sections load, save works
3. Connectors — all platforms show, save works
4. Skills — grid loads, enable/disable works
5. Sessions, Security, Agents, Persona, Analytics, Scheduler — all load correctly
6. Command palette (Ctrl+K) works
7. Theme toggle works
8. Voice buttons appear

- [ ] **Step 3: Commit**

```bash
git add steelclaw/web/static/index.html
git commit -m "feat: premium glassmorphism UI redesign with voice streaming and enhanced settings"
```

---

### Task 5: Add `required_credentials` to Key Bundled Skills

**Files:**
- Modify: Multiple skill `__init__.py` files

- [ ] **Step 1: Add credential declarations to skills that need API keys**

For each skill below, add a `required_credentials` list at the top of its `__init__.py`:

**`steelclaw/skills/bundled/github_skill/__init__.py`:**
```python
required_credentials = [
    {"key": "api_token", "label": "GitHub Personal Access Token", "type": "password", "test_url": "https://api.github.com/user"},
]
```

**`steelclaw/skills/bundled/slack_skill/__init__.py`:**
```python
required_credentials = [
    {"key": "bot_token", "label": "Slack Bot Token", "type": "password", "test_url": "https://slack.com/api/auth.test"},
]
```

**`steelclaw/skills/bundled/notion/__init__.py`:**
```python
required_credentials = [
    {"key": "api_key", "label": "Notion Integration Token", "type": "password", "test_url": "https://api.notion.com/v1/users/me"},
]
```

**`steelclaw/skills/bundled/openai_skill/__init__.py`:**
```python
required_credentials = [
    {"key": "api_key", "label": "OpenAI API Key", "type": "password", "test_url": "https://api.openai.com/v1/models"},
]
```

**`steelclaw/skills/bundled/google_calendar/__init__.py`:**
```python
required_credentials = [
    {"key": "api_key", "label": "Google API Key", "type": "password", "test_url": None},
    {"key": "client_id", "label": "OAuth Client ID", "type": "text", "test_url": None},
]
```

**`steelclaw/skills/bundled/sendgrid/__init__.py`:**
```python
required_credentials = [
    {"key": "api_key", "label": "SendGrid API Key", "type": "password", "test_url": "https://api.sendgrid.com/v3/user/profile"},
]
```

**`steelclaw/skills/bundled/stripe/__init__.py`:**
```python
required_credentials = [
    {"key": "api_key", "label": "Stripe Secret Key", "type": "password", "test_url": "https://api.stripe.com/v1/balance"},
]
```

**`steelclaw/skills/bundled/linear/__init__.py`:**
```python
required_credentials = [
    {"key": "api_key", "label": "Linear API Key", "type": "password", "test_url": "https://api.linear.app/graphql"},
]
```

All other skills get `required_credentials = []` by default via the loader (no changes needed).

- [ ] **Step 2: Commit**

```bash
git add steelclaw/skills/bundled/
git commit -m "feat: add required_credentials declarations to key bundled skills"
```

---

### Task 6: Final Integration Verification

- [ ] **Step 1: Start the app and test end-to-end**

Run: `cd /Volumes/SSD/ClaudeProjects/SteelClaw && python -m steelclaw serve`

Verify in browser at `http://localhost:8000`:

1. **Glassmorphism renders** — purple/blue gradient background, glass panels, frosted sidebar
2. **Chat works** — WebSocket connects (green dot), send messages, receive responses
3. **Voice panel** — click voice chat button, verify orb animation appears, recording works
4. **Settings tabs** — Appearance, Voice, Agent Behavior, Tool Management, Gateway, Database, Server, Security all navigate and save
5. **Accent color** — change accent in Appearance, verify it applies globally
6. **Skills page** — click a skill card, verify credential modal opens, verify/save works
7. **Web search default-on** — verify web_search appears in active skills without manual enabling
8. **Command palette** — Ctrl+K, navigate, execute commands
9. **Light mode** — toggle theme, verify light glassmorphism renders

- [ ] **Step 2: Run full test suite**

Run: `cd /Volumes/SSD/ClaudeProjects/SteelClaw && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration fixes from end-to-end verification"
```
