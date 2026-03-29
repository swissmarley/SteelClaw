"""Weather API skill — current weather and forecasts via OpenWeatherMap."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://api.openweathermap.org/data/2.5"


def _config() -> dict:
    return get_all_credentials("weather_api")


async def tool_get_weather(city: str, units: str = "metric") -> str:
    """Get current weather for a location."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure weather_api"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/weather",
                params={"q": city, "appid": api_key, "units": units},
            )
            resp.raise_for_status()
            data = resp.json()
        weather = data.get("weather", [{}])[0]
        main = data.get("main", {})
        wind = data.get("wind", {})
        unit_label = "C" if units == "metric" else ("F" if units == "imperial" else "K")
        lines = [
            f"Weather in **{data.get('name', city)}**:\n",
            f"- Condition: {weather.get('main', '')} — {weather.get('description', '')}",
            f"- Temperature: {main.get('temp', '')} {unit_label} (feels like {main.get('feels_like', '')} {unit_label})",
            f"- Humidity: {main.get('humidity', '')}%",
            f"- Wind: {wind.get('speed', '')} {'m/s' if units == 'metric' else 'mph'}",
            f"- Pressure: {main.get('pressure', '')} hPa",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_get_forecast(city: str, units: str = "metric") -> str:
    """Get 5-day weather forecast for a location."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure weather_api"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/forecast",
                params={"q": city, "appid": api_key, "units": units, "cnt": 40},
            )
            resp.raise_for_status()
            data = resp.json()
        forecasts = data.get("list", [])
        if not forecasts:
            return f"No forecast data for {city}."
        unit_label = "C" if units == "metric" else ("F" if units == "imperial" else "K")
        lines = [f"5-day forecast for **{data.get('city', {}).get('name', city)}**:\n"]
        # Show one entry per day (every 8th entry = 24h at 3h intervals)
        for entry in forecasts[::8]:
            dt = entry.get("dt_txt", "")
            main = entry.get("main", {})
            weather = entry.get("weather", [{}])[0]
            lines.append(
                f"- **{dt}**: {weather.get('description', '')} | "
                f"{main.get('temp_min', '')}–{main.get('temp_max', '')} {unit_label} | "
                f"Humidity: {main.get('humidity', '')}%"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
