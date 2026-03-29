# SendGrid Integration

Send transactional emails via the SendGrid API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: sendgrid, email, send email, transactional

## System Prompt
You can send emails via SendGrid. Use the SendGrid tool to send transactional emails. Credentials must be configured via `steelclaw skills configure sendgrid`.

## Tools

### send_email
Send an email via SendGrid.

**Parameters:**
- `to_email` (string, required): Recipient email address
- `subject` (string, required): Email subject
- `content` (string, required): Email body (plain text)
- `content_type` (string, optional): Content type — text/plain or text/html (default text/plain)
