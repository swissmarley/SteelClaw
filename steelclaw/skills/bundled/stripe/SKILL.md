# Stripe Integration

List charges, create invoices, and check balance via the Stripe API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: stripe, payment, invoice, billing, charges

## System Prompt
You can interact with Stripe. Use the Stripe tools to list charges, create invoices, or check account balance. Credentials must be configured via `steelclaw skills configure stripe`.

## Tools

### list_charges
List recent charges on the Stripe account.

**Parameters:**
- `limit` (integer, optional): Maximum number of charges to return (default 10)

### create_invoice
Create a draft invoice for a Stripe customer.

**Parameters:**
- `customer_id` (string, required): The Stripe customer ID
- `description` (string, optional): Invoice description

### get_balance
Get the current Stripe account balance.
