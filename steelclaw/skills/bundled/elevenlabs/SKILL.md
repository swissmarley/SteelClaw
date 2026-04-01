# ElevenLabs Integration

Text-to-speech synthesis and voice listing via the ElevenLabs API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: elevenlabs, tts, text to speech, voice, audio, speech

## System Prompt
You can interact with ElevenLabs. Use the ElevenLabs tools to convert text to speech or list available voices. Credentials must be configured via `steelclaw skills configure elevenlabs`.

## Tools

### text_to_speech
Convert text to speech using ElevenLabs. Returns base64-encoded audio.

**Parameters:**
- `text` (string, required): The text to convert to speech
- `voice_id` (string, optional): The voice ID to use (default "21m00Tcm4TlvDq8ikWAM")
- `model_id` (string, optional): The model ID to use (default "eleven_monolingual_v1")

### list_voices
List all available voices on ElevenLabs.
