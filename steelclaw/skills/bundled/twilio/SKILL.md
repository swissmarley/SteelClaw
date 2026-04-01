# Twilio Integration

Send SMS messages and initiate phone calls via the Twilio API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: twilio, sms, phone, call, text message

## System Prompt
You can send SMS messages and make phone calls via Twilio. Use the Twilio tools to send text messages or initiate calls. Credentials must be configured via `steelclaw skills configure twilio`.

## Tools

### send_sms
Send an SMS message via Twilio.

**Parameters:**
- `to` (string, required): Recipient phone number (E.164 format)
- `body` (string, required): SMS message body

### make_call
Initiate a phone call via Twilio.

**Parameters:**
- `to` (string, required): Recipient phone number (E.164 format)
- `twiml` (string, optional): TwiML instructions for the call (default: simple message)
