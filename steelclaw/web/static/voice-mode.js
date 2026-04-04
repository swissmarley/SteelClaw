/**
 * VoiceModeManager — WebRTC voice mode using the OpenAI Realtime API.
 *
 * FSM states: IDLE → CONNECTING → LISTENING → AGENT_SPEAKING → INTERRUPTED → STOPPING → IDLE
 *
 * Usage (global singleton exposed as `voiceMode`):
 *   voiceMode.start()          // opens overlay, connects WebRTC
 *   voiceMode.stop()           // tears down connection, appends transcript to chat
 *   voiceMode.interrupt()      // cancels agent speech, resumes listening
 *   voiceMode.mute()           // toggles mic without ending session
 *   voiceMode.setVoice('nova') // changes preferred voice (persisted in localStorage)
 */
class VoiceModeManager {
  constructor() {
    /** @type {'IDLE'|'CONNECTING'|'LISTENING'|'AGENT_SPEAKING'|'INTERRUPTED'|'STOPPING'} */
    this._state = 'IDLE';

    /** @type {RTCPeerConnection|null} */
    this._pc = null;

    /** @type {RTCDataChannel|null} */
    this._dc = null;

    /** @type {MediaStream|null} */
    this._micStream = null;

    /** @type {HTMLAudioElement|null} */
    this._audioEl = null;

    /** @type {ReturnType<typeof setTimeout>|null} */
    this._safetyTimer = null;

    /** @type {Array<{role:'user'|'agent', text:string}>} */
    this._transcript = [];

    /** @type {string} Accumulates current agent turn text */
    this._currentAgentTurn = '';

    /** @type {string} Model name resolved from session response */
    this._model = 'gpt-4o-realtime-preview';

    this._voice = localStorage.getItem('steelclaw-realtime-voice') || 'alloy';

    // Escape key closes voice mode from any active state
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this._state !== 'IDLE') this.stop();
    });
  }

  /** Current FSM state (read-only). */
  get state() { return this._state; }

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Start voice mode: check permissions, fetch ephemeral token, connect WebRTC.
   * Transitions: IDLE → CONNECTING → LISTENING
   */
  async start() {
    if (this._state !== 'IDLE') return;

    // Check microphone permission before opening overlay
    try {
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach(t => t.stop());
    } catch (_) {
      this._showError(
        'Microphone access denied. ' +
        'Click the camera icon in your browser address bar to allow mic access.'
      );
      return;
    }

    // Check WebRTC support
    if (typeof RTCPeerConnection === 'undefined') {
      this._showError(
        'WebRTC is not supported in this browser. Use Chrome, Firefox, or Safari 15+.'
      );
      return;
    }

    this._setState('CONNECTING');

    try {
      const { clientSecret, model } = await this._fetchEphemeralToken();
      this._model = model;
      await this._connectWebRTC(clientSecret);
    } catch (err) {
      console.error('[VoiceModeManager] start() failed:', err);
      this._showError(err.message || 'Could not connect to voice mode. Try again.');
      await this._teardown();
      this._setState('IDLE');
    }
  }

  /**
   * Stop voice mode: cancel any response, release all resources, append transcript.
   * Transitions: any → STOPPING → IDLE
   */
  async stop() {
    if (this._state === 'IDLE') return;
    this._setState('STOPPING');
    await this._teardown();
    this._appendTranscriptToChat();
    this._transcript = [];
    this._currentAgentTurn = '';
    this._setState('IDLE');
  }

  /**
   * Interrupt the agent while speaking: cancel response, flush audio, resume listening.
   * Transitions: AGENT_SPEAKING → INTERRUPTED → LISTENING
   */
  async interrupt() {
    if (this._state !== 'AGENT_SPEAKING') return;
    this._setState('INTERRUPTED');

    // Tell OpenAI to stop the current response
    if (this._dc && this._dc.readyState === 'open') {
      this._dc.send(JSON.stringify({ type: 'response.cancel' }));
    }

    // Flush buffered audio immediately
    if (this._audioEl) {
      this._audioEl.srcObject = null;
    }

    // Re-attach audio track so future responses still play
    if (this._pc) {
      for (const receiver of this._pc.getReceivers()) {
        if (receiver.track && receiver.track.kind === 'audio') {
          if (!this._audioEl) {
            this._audioEl = document.createElement('audio');
            this._audioEl.autoplay = true;
            document.body.appendChild(this._audioEl);
          }
          this._audioEl.srcObject = new MediaStream([receiver.track]);
          break;
        }
      }
    }

    // Brief debounce before returning to LISTENING to avoid state bounce
    setTimeout(() => {
      if (this._state === 'INTERRUPTED') this._setState('LISTENING');
    }, 200);
  }

  /**
   * Toggle microphone mute without ending the session.
   */
  mute() {
    if (!this._micStream) return;
    const track = this._micStream.getAudioTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    const btn = document.getElementById('voice-mute-btn');
    if (btn) {
      btn.textContent = track.enabled ? '🔇 Mute' : '🔊 Unmute';
      btn.setAttribute('aria-pressed', String(!track.enabled));
    }
  }

  /**
   * Set the preferred TTS voice and persist it to localStorage.
   * @param {string} voice - One of: alloy, echo, fable, onyx, nova, shimmer
   */
  setVoice(voice) {
    this._voice = voice;
    localStorage.setItem('steelclaw-realtime-voice', voice);
  }

  // ── Private: Token Fetch ───────────────────────────────────────────────────

  /**
   * Fetch an ephemeral Realtime API session token from the backend.
   * @returns {Promise<{clientSecret: string, model: string, sessionId: string}>}
   */
  async _fetchEphemeralToken() {
    const resp = await fetch('/api/voice/realtime-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice: this._voice }),
    });

    if (!resp.ok) {
      let detail = `Session creation failed (${resp.status})`;
      try { const d = await resp.json(); if (d.detail) detail = d.detail; } catch (_) {}
      throw new Error(detail);
    }

    const data = await resp.json();
    if (!data.client_secret?.value) {
      throw new Error('Invalid session response from server');
    }
    return {
      clientSecret: data.client_secret.value,
      model: data.model || 'gpt-4o-realtime-preview',
      sessionId: data.session_id || '',
    };
  }

  // ── Private: WebRTC ────────────────────────────────────────────────────────

  /**
   * Establish WebRTC connection to the OpenAI Realtime API.
   * @param {string} ephemeralToken
   */
  async _connectWebRTC(ephemeralToken) {
    const pc = new RTCPeerConnection();
    this._pc = pc;

    // Remote audio: attach incoming track to an <audio> element for immediate playback
    const audioEl = document.createElement('audio');
    audioEl.autoplay = true;
    document.body.appendChild(audioEl);
    this._audioEl = audioEl;

    pc.ontrack = (event) => { audioEl.srcObject = event.streams[0]; };

    // Mic capture
    const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this._micStream = micStream;
    micStream.getTracks().forEach(track => pc.addTrack(track, micStream));

    // Data channel for Realtime API events
    const dc = pc.createDataChannel('oai-events');
    this._dc = dc;
    dc.addEventListener('message', (e) => {
      try { this._handleRealtimeEvent(JSON.parse(e.data)); }
      catch (err) { console.warn('[VoiceModeManager] Failed to parse event:', e.data, err); }
    });

    // Handle mid-session connection loss
    pc.onconnectionstatechange = () => {
      if (
        (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') &&
        this._state !== 'IDLE' && this._state !== 'STOPPING'
      ) {
        console.warn('[VoiceModeManager] WebRTC state:', pc.connectionState);
        this._showError('Voice connection lost. The session has ended.');
        this.stop();
      }
    };

    // SDP offer / answer exchange with OpenAI
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const sdpResp = await fetch(
      `https://api.openai.com/v1/realtime?model=${encodeURIComponent(this._model)}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${ephemeralToken}`,
          'Content-Type': 'application/sdp',
        },
        body: offer.sdp,
      }
    );

    if (!sdpResp.ok) {
      throw new Error(
        `WebRTC handshake failed (${sdpResp.status}). Check your OpenAI API key.`
      );
    }

    await pc.setRemoteDescription({ type: 'answer', sdp: await sdpResp.text() });
    // session.created event (from data channel) will transition us to LISTENING
  }

  // ── Private: Event Handling ────────────────────────────────────────────────

  /**
   * Handle a single event from the OpenAI Realtime API data channel.
   * @param {Object} event
   */
  _handleRealtimeEvent(event) {
    switch (event.type) {

      case 'session.created':
        this._setState('LISTENING');
        break;

      case 'input_audio_buffer.speech_started':
        if (this._state === 'AGENT_SPEAKING') this.interrupt();
        break;

      case 'response.audio.delta':
        if (this._state === 'LISTENING' || this._state === 'INTERRUPTED') {
          this._setState('AGENT_SPEAKING');
        }
        break;

      case 'response.audio_transcript.delta': {
        const delta = event.delta || '';
        this._currentAgentTurn += delta;
        this._updateTranscriptDisplay(this._currentAgentTurn);
        break;
      }

      case 'response.audio_transcript.done': {
        const text = (event.transcript || this._currentAgentTurn).trim();
        if (text) this._transcript.push({ role: 'agent', text });
        this._currentAgentTurn = '';
        break;
      }

      case 'conversation.item.input_audio_transcription.completed': {
        const text = (event.transcript || '').trim();
        if (text) {
          this._transcript.push({ role: 'user', text });
          this._updateTranscriptDisplay(text);
        }
        break;
      }

      case 'response.done':
        if (this._state === 'AGENT_SPEAKING') this._setState('LISTENING');
        break;

      case 'error':
        console.error('[VoiceModeManager] Realtime API error:', event.error);
        this._showError(`Voice error: ${event.error?.message || 'Unknown error'}`);
        this.stop();
        break;

      default:
        // Ignore unhandled event types (session.updated, rate_limits.updated, etc.)
        break;
    }
  }

  // ── Private: Teardown ──────────────────────────────────────────────────────

  /**
   * Release all audio/WebRTC resources. Safe to call multiple times.
   */
  async _teardown() {
    if (this._safetyTimer !== null) {
      clearTimeout(this._safetyTimer);
      this._safetyTimer = null;
    }

    if (this._dc && this._dc.readyState === 'open') {
      try { this._dc.send(JSON.stringify({ type: 'response.cancel' })); } catch (_) {}
    }

    if (this._micStream) {
      this._micStream.getTracks().forEach(t => t.stop());
      this._micStream = null;
    }

    if (this._audioEl) {
      this._audioEl.srcObject = null;
      this._audioEl.remove();
      this._audioEl = null;
    }

    if (this._pc) {
      this._pc.close();
      this._pc = null;
    }

    this._dc = null;
  }

  // ── Private: UI Updates ────────────────────────────────────────────────────

  /**
   * Transition FSM state, update UI, and arm safety timer.
   * @param {string} state
   */
  _setState(state) {
    this._state = state;
    this._applyStateToUI(state);
    this._armSafetyTimer(state);
  }

  /**
   * Apply data-voice-state attribute and derived UI changes to the overlay.
   * @param {string} state
   */
  _applyStateToUI(state) {
    const overlay = document.getElementById('voice-overlay');
    if (!overlay) return;

    overlay.style.display = state === 'IDLE' ? 'none' : 'flex';
    overlay.dataset.voiceState = state;

    const labelEl = document.getElementById('voice-state-label');
    const labels = {
      CONNECTING: 'Connecting...',
      LISTENING: 'Listening',
      AGENT_SPEAKING: 'SteelClaw is speaking',
      INTERRUPTED: 'Interrupted',
      STOPPING: 'Ending...',
    };
    if (labelEl) labelEl.textContent = labels[state] || '';

    const iconEl = document.getElementById('voice-orb-icon');
    const icons = {
      CONNECTING: '⟳',
      LISTENING: '🎙',
      AGENT_SPEAKING: '🔊',
      INTERRUPTED: '✋',
      STOPPING: '⏹',
    };
    if (iconEl) iconEl.textContent = icons[state] || '🎙';

    // Clear transcript display when starting a new session
    if (state === 'CONNECTING') this._updateTranscriptDisplay('');

    // Trap focus inside overlay while active
    if (state !== 'IDLE') {
      const firstFocusable = overlay.querySelector('button');
      if (firstFocusable) setTimeout(() => firstFocusable.focus(), 50);
    }
  }

  /**
   * Update the live transcript text element.
   * @param {string} text
   */
  _updateTranscriptDisplay(text) {
    const el = document.getElementById('voice-transcript-text');
    if (el) el.textContent = text;
  }

  /**
   * Arm a watchdog timer that auto-recovers from stuck states.
   * CONNECTING: 8s. INTERRUPTED / STOPPING: 30s.
   * LISTENING and AGENT_SPEAKING have no timeout (normal operating states).
   * @param {string} state
   */
  _armSafetyTimer(state) {
    if (this._safetyTimer !== null) {
      clearTimeout(this._safetyTimer);
      this._safetyTimer = null;
    }
    const ms = { CONNECTING: 8000, INTERRUPTED: 30000, STOPPING: 30000 }[state];
    if (!ms) return;
    this._safetyTimer = setTimeout(() => {
      if (this._state === state) {
        console.warn('[VoiceModeManager] Safety timer fired in state', state);
        this.stop();
      }
    }, ms);
  }

  // ── Private: Transcript → Chat ─────────────────────────────────────────────

  /**
   * Append the voice session transcript to the main chat message list.
   * No-op if no turns were captured.
   */
  _appendTranscriptToChat() {
    if (this._transcript.length === 0) return;

    const msgEl = document.getElementById('chat-messages');
    if (!msgEl) return;

    const block = document.createElement('div');
    block.className = 'msg voice-session-block fade-in-up';

    const header = document.createElement('div');
    header.className = 'lbl';
    header.textContent = '🎙 Voice Session';

    const turns = document.createElement('div');
    turns.className = 'voice-turns';

    for (const turn of this._transcript) {
      const row = document.createElement('div');
      row.className = `voice-turn voice-turn-${turn.role}`;

      const label = document.createElement('span');
      label.className = 'voice-turn-label';
      label.textContent = turn.role === 'user' ? 'You:' : 'SteelClaw:';

      const text = document.createElement('span');
      text.className = 'voice-turn-text';
      text.textContent = ' ' + turn.text;

      row.appendChild(label);
      row.appendChild(text);
      turns.appendChild(row);
    }

    block.appendChild(header);
    block.appendChild(turns);
    msgEl.appendChild(block);
    msgEl.scrollTop = msgEl.scrollHeight;
  }

  // ── Private: Error Display ─────────────────────────────────────────────────

  /**
   * Show a user-friendly error. Uses the app's toast() if available.
   * @param {string} message
   */
  _showError(message) {
    if (typeof toast === 'function') {
      toast(message, 'error');
    } else {
      console.error('[VoiceModeManager]', message);
    }
  }
}

// ── Helper for voice chip button active state ──────────────────────────────

/**
 * Update aria-pressed and active class on voice chip buttons after selection.
 * @param {HTMLElement} selectedBtn
 */
function updateVoiceChips(selectedBtn) {
  document.querySelectorAll('#voice-selector .voice-chip').forEach(btn => {
    const active = btn === selectedBtn;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
}

// ── Global singleton ────────────────────────────────────────────────────────
const voiceMode = new VoiceModeManager();
