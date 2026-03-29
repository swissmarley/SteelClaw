# Weather API

Get current weather and forecasts via OpenWeatherMap API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: weather, forecast, temperature, openweathermap, climate

## System Prompt
You can use Weather API. Credentials must be configured via `steelclaw skills configure weather_api`.

## Tools

### get_weather
Get current weather for a location.

**Parameters:**
- `city` (string, required): City name (e.g. "London" or "London,UK")
- `units` (string): Units — "metric", "imperial", or "standard" (default: "metric")

### get_forecast
Get 5-day weather forecast for a location.

**Parameters:**
- `city` (string, required): City name
- `units` (string): Units — "metric", "imperial", or "standard" (default: "metric")
