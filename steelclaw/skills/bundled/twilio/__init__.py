"""Twilio integration — send SMS and make phone calls."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "account_sid", "label": "Twilio Account SID", "type": "text"},
    {"key": "auth_token", "label": "Twilio Auth Token", "type": "password"},
    {"key": "from_number", "label": "Twilio Phone Number", "type": "text"},
]


def _config() -> dict:
    return get_all_credentials("twilio")


def _base_url(account_sid: str) -> str:
    return f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"


async def tool_send_sms(to: str, body: str) -> str:
    """Send an SMS message via Twilio."""
    config = _config()
    account_sid = config.get("account_sid", "")
    auth_token = config.get("auth_token", "")
    from_number = config.get("from_number", "")
    if not all([account_sid, auth_token, from_number]):
        return "Error: account_sid, auth_token, and from_number must be configured. Run: steelclaw skills configure twilio"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base_url(account_sid)}/Messages.json",
                auth=(account_sid, auth_token),
                data={"To": to, "From": from_number, "Body": body},
            )
            resp.raise_for_status()
            msg = resp.json()
            return f"SMS sent. SID: {msg.get('sid', 'N/A')}, Status: {msg.get('status', 'N/A')}"
    except Exception as e:
        return f"Error: {e}"


async def tool_make_call(to: str, twiml: str = "") -> str:
    """Initiate a phone call via Twilio."""
    config = _config()
    account_sid = config.get("account_sid", "")
    auth_token = config.get("auth_token", "")
    from_number = config.get("from_number", "")
    if not all([account_sid, auth_token, from_number]):
        return "Error: account_sid, auth_token, and from_number must be configured. Run: steelclaw skills configure twilio"
    if not twiml:
        twiml = "<Response><Say>Hello, this is an automated call from SteelClaw.</Say></Response>"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base_url(account_sid)}/Calls.json",
                auth=(account_sid, auth_token),
                data={"To": to, "From": from_number, "Twiml": twiml},
            )
            resp.raise_for_status()
            call = resp.json()
            return f"Call initiated. SID: {call.get('sid', 'N/A')}, Status: {call.get('status', 'N/A')}"
    except Exception as e:
        return f"Error: {e}"
