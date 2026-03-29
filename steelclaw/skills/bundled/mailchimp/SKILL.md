# Mailchimp Integration

Manage audiences and add members via the Mailchimp Marketing API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: mailchimp, email marketing, audience, newsletter

## System Prompt
You can interact with Mailchimp. Use the Mailchimp tools to list audiences or add members to an audience. Credentials must be configured via `steelclaw skills configure mailchimp`.

## Tools

### list_audiences
List all audiences (lists) in the Mailchimp account.

### add_member
Add a member to a Mailchimp audience.

**Parameters:**
- `list_id` (string, required): The audience/list ID
- `email` (string, required): Email address of the member
- `status` (string, optional): Subscription status — subscribed, unsubscribed, pending (default subscribed)
