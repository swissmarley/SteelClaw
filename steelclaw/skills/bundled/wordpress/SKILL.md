# WordPress

Manage WordPress sites via the REST API — create posts, list content, and upload media.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: wordpress, blog, post

## System Prompt
You can manage WordPress sites. Use the WordPress tools to create posts, list existing posts, or upload media. Credentials must be configured via `steelclaw skills configure wordpress`.

## Tools

### create_post
Create a new WordPress post.

**Parameters:**
- `title` (string, required): Post title
- `content` (string, required): Post content (HTML)
- `status` (string, optional): Post status (draft, publish, pending). Default: draft

### list_posts
List recent WordPress posts.

**Parameters:**
- `count` (integer, optional): Number of posts to retrieve. Default: 10

### upload_media
Upload a media file to WordPress.

**Parameters:**
- `file_path` (string, required): Local path to the file to upload
