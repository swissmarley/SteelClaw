# Trello Integration

List boards, list cards, and create cards via the Trello API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: trello, boards, cards, kanban, tasks, project management

## System Prompt
You can interact with Trello. Use the Trello tools to list boards, view cards on a board, or create new cards. Credentials must be configured via `steelclaw skills configure trello`.

## Tools

### list_boards
List all boards for the authenticated Trello user.

### list_cards
List all cards on a Trello board.

**Parameters:**
- `board_id` (string, required): The Trello board ID

### create_card
Create a new card on a Trello list.

**Parameters:**
- `list_id` (string, required): The Trello list ID to add the card to
- `name` (string, required): The card name
- `desc` (string, optional): Card description
- `due` (string, optional): Due date in ISO 8601 format
