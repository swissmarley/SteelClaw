# Twitter/X

Post tweets, search tweets, and get user profiles via the Twitter/X API v2.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: twitter, x, tweet, tweets, social media

## System Prompt
You can use Twitter/X. Credentials must be configured via `steelclaw skills configure twitter_x`.

## Tools

### post_tweet
Post a new tweet.

**Parameters:**
- `text` (string, required): Tweet text (max 280 characters)

### search_tweets
Search recent tweets.

**Parameters:**
- `query` (string, required): Search query
- `max_results` (integer): Maximum results (10-100, default: 10)

### get_user
Get a Twitter user profile by username.

**Parameters:**
- `username` (string, required): Twitter username (without @)
