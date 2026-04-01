# Spotify Integration

Search tracks, get playlists, and check now playing via the Spotify Web API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: spotify, music, tracks, playlist, now playing

## System Prompt
You can interact with Spotify. Use the Spotify tools to search tracks, get playlist details, or check what is currently playing. Credentials must be configured via `steelclaw skills configure spotify`.

## Tools

### search_tracks
Search for tracks on Spotify.

**Parameters:**
- `query` (string, required): The search query
- `limit` (integer, optional): Maximum number of results to return (default 10)

### get_playlist
Get details and tracks of a Spotify playlist.

**Parameters:**
- `playlist_id` (string, required): The Spotify playlist ID

### get_now_playing
Get the currently playing track on Spotify.
