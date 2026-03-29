# LinkedIn

Get LinkedIn profile info and share posts via the LinkedIn API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: linkedin, professional, networking, linkedin post, profile

## System Prompt
You can use LinkedIn. Credentials must be configured via `steelclaw skills configure linkedin`.

## Tools

### get_profile
Get the authenticated user's LinkedIn profile.

**Parameters:**
(none)

### share_post
Share a text post on LinkedIn.

**Parameters:**
- `text` (string, required): Post text content
