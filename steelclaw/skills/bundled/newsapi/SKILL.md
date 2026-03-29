# NewsAPI

Get top headlines and search news articles via NewsAPI.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: news, headlines, newsapi, articles, current events

## System Prompt
You can use NewsAPI. Credentials must be configured via `steelclaw skills configure newsapi`.

## Tools

### get_headlines
Get top headlines.

**Parameters:**
- `country` (string): Country code (default: "us")
- `category` (string): Category — business, entertainment, general, health, science, sports, technology
- `max_results` (integer): Maximum articles (default: 10)

### search_news
Search news articles.

**Parameters:**
- `query` (string, required): Search query
- `sort_by` (string): Sort by — "relevancy", "popularity", or "publishedAt" (default: "publishedAt")
- `max_results` (integer): Maximum articles (default: 10)
