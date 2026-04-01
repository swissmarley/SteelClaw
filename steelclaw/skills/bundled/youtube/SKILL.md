# YouTube Integration

Search videos and get video details via the YouTube Data API v3.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: youtube, video, search, watch, stream

## System Prompt
You can interact with YouTube. Use the YouTube tools to search for videos or get detailed video information. Credentials must be configured via `steelclaw skills configure youtube`.

## Tools

### search_videos
Search for YouTube videos by query.

**Parameters:**
- `query` (string, required): The search query
- `max_results` (integer, optional): Maximum number of results to return (default 5)

### get_video_details
Get detailed information about a YouTube video.

**Parameters:**
- `video_id` (string, required): The YouTube video ID
