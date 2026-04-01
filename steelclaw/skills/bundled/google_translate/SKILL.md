# Google Translate Integration

Translate text and detect language via the Google Cloud Translation API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: translate, translation, language, google translate, detect language

## System Prompt
You can interact with Google Cloud Translation. Use the translation tools to translate text between languages or detect the language of a given text. Credentials must be configured via `steelclaw skills configure google_translate`.

## Tools

### translate_text
Translate text to a target language using Google Cloud Translation.

**Parameters:**
- `text` (string, required): The text to translate
- `target_language` (string, required): Target language code (e.g. en, es, fr, de, ja)
- `source_language` (string, optional): Source language code; auto-detected if omitted

### detect_language
Detect the language of a given text.

**Parameters:**
- `text` (string, required): The text to detect the language of
