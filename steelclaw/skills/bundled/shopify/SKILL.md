# Shopify Integration

List products, list orders, and get order details from a Shopify store via the Admin API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: shopify, store, products, orders, ecommerce

## System Prompt
You can interact with Shopify stores. Use the Shopify tools to list products, list orders, or get order details. Credentials must be configured via `steelclaw skills configure shopify`.

## Tools

### list_products
List products from the Shopify store.

**Parameters:**
- `limit` (integer, optional): Maximum number of products to return (default 20)

### list_orders
List recent orders from the Shopify store.

**Parameters:**
- `status` (string, optional): Filter by status — open, closed, any (default any)
- `limit` (integer, optional): Maximum number of orders to return (default 20)

### get_order
Get details of a specific Shopify order.

**Parameters:**
- `order_id` (string, required): The Shopify order ID
