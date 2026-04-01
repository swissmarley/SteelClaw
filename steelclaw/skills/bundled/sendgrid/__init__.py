"""SendGrid integration — send transactional emails."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "api_key", "label": "SendGrid API Key", "type": "password", "test_url": "https://api.sendgrid.com/v3/user/profile"},
]

SEND_URL = "https://api.sendgrid.com/v3/mail/send"


def _config() -> dict:
    return get_all_credentials("sendgrid")


async def tool_send_email(to_email: str, subject: str, content: str, content_type: str = "text/plain") -> str:
    """Send an email via SendGrid."""
    config = _config()
    api_key = config.get("api_key", "")
    from_email = config.get("from_email", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure sendgrid"
    if not from_email:
        return "Error: from_email not configured. Run: steelclaw skills configure sendgrid"
    try:
        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": content_type, "value": content}],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                SEND_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code in (200, 201, 202):
                return f"Email sent to {to_email}. Status: {resp.status_code}"
            resp.raise_for_status()
            return f"Email sent. Status: {resp.status_code}"
    except Exception as e:
        return f"Error: {e}"
