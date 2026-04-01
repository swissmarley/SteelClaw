# SteelClaw UI Overhaul & Feature Enhancement — Design Spec

**Date:** 2026-03-29
**Status:** Approved
**Scope:** 5 features — tool init, API key management, voice streaming, glassmorphism redesign, enhanced settings

---

## 1. Tool Initialization & Web Search Default-On

### Problem
Web search/browse tools can throw initialization errors if the skill isn't loaded or enabled at startup.

### Design
- In `app.py` lifespan, after `SkillRegistry.load_all()`, explicitly verify `web_search` and `web_scraper` skills are loaded and enabled. If they failed to load, log a warning but don't crash.
- Add a `default_enabled` flag to the skill manifest pattern. `web_search` and `web_scraper` set this to `True`.
- In `SkillRegistry.load_all()`, skills with `default_enabled=True` are never added to `disabled_skills` on first run.
- Web search already uses DuckDuckGo (no API key needed), so always-on is safe.

### Files touched
- `steelclaw/app.py` — startup verification
- `steelclaw/skills/registry.py` — `default_enabled` flag handling
- `steelclaw/skills/bundled/web_search/__init__.py` — add `default_enabled = True`
- `steelclaw/skills/bundled/web_scraper/__init__.py` — add `default_enabled = True`

---

## 2. API Key Management & Verification

### Skill-side declaration
Each skill that needs API keys exports a `required_credentials` list:
```python
required_credentials = [
    {"key": "api_key", "label": "API Key", "type": "password", "test_url": "https://api.example.com/v1/me"},
    {"key": "workspace_id", "label": "Workspace ID", "type": "text", "test_url": None}
]
```

### Backend
- `GET /api/skills/{skill_name}/credentials` — returns declared `required_credentials` with values masked (`****last4` if set, empty if not).
- `PUT /api/skills/{skill_name}/credentials` — saves key-value pairs into `settings.agents.skills.skill_configs[skill_name]`.
- `POST /api/skills/{skill_name}/verify` — for each credential with a `test_url`, makes a lightweight authenticated request. Returns per-key `{key, status: "ok"|"error", message}`.
- Storage: `config.json` under `skill_configs` (existing mechanism).

### Frontend
- Skills Management modal — click a skill card to open.
- Shows skill metadata, then form with each declared credential field.
- Each field has a "Verify" button → green checkmark or red X.
- "Save" button persists all values.
- Skills without `required_credentials` show "No configuration needed."

### Security
- API keys never returned in full — only masked.
- Verify endpoint tests connectivity server-side; keys never leave backend.

### Files touched
- `steelclaw/api/skills.py` — 3 new endpoints
- `steelclaw/skills/registry.py` — credential lookup helpers
- `steelclaw/web/static/index.html` — credential modal UI
- Individual skill `__init__.py` files — add `required_credentials` declarations

---

## 3. Voice Interaction — Chunked TTS Streaming

### Backend
- New endpoint `POST /api/voice/synthesize-stream` — splits text into sentence-sized chunks using regex `r'(?<=[.!?])\s+'` (split after sentence-ending punctuation followed by whitespace), calls TTS per chunk, returns chunked HTTP response (`Transfer-Encoding: chunked`, `Content-Type: audio/mpeg`). Chunks smaller than 10 characters are merged with the next chunk to avoid choppy short fragments.
- Each chunk is a complete decodable MP3 segment.
- First chunk generates on first sentence — no waiting for full response.

### Frontend voice flow
When voice mode is active, the frontend collects streamed text tokens from WebSocket. As each sentence completes, fires request to `synthesize-stream` for that sentence batch. Pipelines TTS with text generation.

### Visual states (smooth transitions)
1. **Idle** — subtle pulsing orb (purple/blue gradient), "Tap to speak" label
2. **Listening** — orb expands, real-time waveform visualizer (`AnalyserNode`), ring pulses with mic amplitude
3. **Speaking** — orb morphs into flowing wave, audio chunks play via `AudioContext` buffer queue, crossfade between chunks

### Voice chat panel
- Slides up from bottom as glassmorphic overlay (not full page).
- Animated orb center-stage, transcript text scrolling below, stop/close button.

### Chunk playback engine
- Client-side audio queue: MP3 chunks decoded via `AudioContext.decodeAudioData()` and queued.
- Next chunk plays when current ends. Preloads 1-2 chunks ahead.

### Silence detection
- Web Audio API detects 500ms silence → auto-submits recording.

### Latency improvement
- Before: ~5-8s (full response + full TTS)
- After: ~1-2s (first sentence gen + first chunk TTS)

### Files touched
- `steelclaw/api/voice.py` — new streaming endpoint
- `steelclaw/web/static/index.html` — voice UI overhaul, audio queue, waveform visualizer

---

## 4. Premium Glassmorphism UI Redesign

### Color system
| Token | Dark | Light |
|-------|------|-------|
| Background | `#0a0a1a` → `#1a0a2e` → `#0a1628` gradient mesh | Soft lavender/blue gradient |
| Glass surface | `rgba(255,255,255,0.05)` + `blur(20px)` + `1px solid rgba(255,255,255,0.08)` | `rgba(255,255,255,0.6)` + `blur(20px)` |
| Elevated glass | `rgba(255,255,255,0.08)` | `rgba(255,255,255,0.8)` |
| Primary accent | `#8b5cf6` → `#6366f1` gradient | Same |
| Secondary accent | `#06b6d4` (cyan) | Same |
| Text primary | `rgba(255,255,255,0.9)` | `rgba(0,0,0,0.85)` |
| Text secondary | `rgba(255,255,255,0.5)` | `rgba(0,0,0,0.5)` |
| Danger | `#ef4444` | Same |

### Typography
- Body: `Inter, -apple-system, system-ui, sans-serif` (Google Fonts)
- Headings: 600 weight, slight letter-spacing
- Code: `JetBrains Mono, monospace`

### Layout
- **Sidebar:** Frosted glass, icons + labels fade on hover, active = glow pill
- **Top bar:** Transparent, status as glowing dots
- **Content:** Glass cards with `0 8px 32px rgba(0,0,0,0.3)` shadows
- **Chat:** User = accent pill (right). Agent = glass card (left) with border accent
- **Inputs:** Glass fields, focus glow `box-shadow: 0 0 0 2px rgba(139,92,246,0.3)`
- **Buttons:** Primary = gradient + glow. Secondary = glass + border

### Animations
- Page transitions: fade-in with upward motion
- Hover: cards lift with increased blur/brightness
- Loading: skeleton shimmer with glass gradient
- Toasts: slide from top-right as glass cards
- Scrollbars: thin, translucent, rounded
- Command palette: centered glass modal with backdrop blur

### Background
- 2-3 large blurred radial-gradient circles drifting slowly (CSS animation, GPU-accelerated `transform`)

### Files touched
- `steelclaw/web/static/index.html` — complete CSS and layout overhaul

---

## 5. Enhanced Settings Page

### Layout
Tabbed interface: glass sidebar with vertical category pills, main area shows selected category.

### Categories

#### 5.1 Appearance (NEW — frontend-only, localStorage)
- Theme: Dark / Light
- Accent color: Violet (default), Cyan, Emerald, Amber, Rose
- Font size: Small / Medium / Large
- Animations: on/off (respects `prefers-reduced-motion`)
- Chat density: Comfortable / Compact

#### 5.2 Voice & Audio (expanded)
- Enable/disable voice (existing)
- STT/TTS provider + model + voice (existing)
- Voice auto-submit: on/off (silence detection)
- Silence threshold: slider 300ms–1500ms
- Audio output device: dropdown (`navigator.mediaDevices.enumerateDevices()`)
- Playback speed: 0.75x / 1x / 1.25x / 1.5x

#### 5.3 Agent Behavior (expanded)
- Temperature: slider 0.0–2.0 (Precise → Creative)
- Max tokens: numeric
- Max context messages: numeric
- Streaming: on/off
- Default model: dropdown
- API base URL: text
- Timeout: numeric (seconds)

#### 5.4 Tool Management (NEW — consolidates skill management)
- All loaded skills with enable/disable toggles
- Per-skill credential config button → opens credential modal (Section 2)
- Default-enabled skills marked with badge
- "Reload Skills" button

#### 5.5–5.8 Gateway, Database, Server, Security (existing, restyled)
Same fields, new glass card styling.

### Persistence
- Frontend settings (appearance, density, playback speed): `localStorage`
- Backend settings: existing `PUT /api/config/*` endpoints
- Save per-section with success checkmark animation

### Files touched
- `steelclaw/web/static/index.html` — settings page overhaul
- `steelclaw/settings.py` — no changes needed (existing endpoints cover backend settings)

---

## Architecture Notes

- **No new dependencies.** All frontend work is vanilla JS/CSS in the single `index.html`. Voice streaming uses native `AudioContext`. Waveform uses `AnalyserNode`. Font loaded via Google Fonts CDN link.
- **Backward compatible.** Existing API endpoints unchanged. New endpoints are additive. Config format unchanged.
- **Performance.** Glass effects use `backdrop-filter` (GPU-accelerated). Animations use `transform`/`opacity` only. Background gradient circles use CSS animation with `will-change: transform`.
