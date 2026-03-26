# Notes

Create, read, list, and search personal notes stored locally.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: note, notes, remember, memo, save

## System Prompt
You can manage the user's personal notes.
Use create_note to save information, list_notes to see what's saved,
read_note to view a specific note, and search_notes to find notes by keyword.
Notes are stored as plain text files in the data/notes/ directory.

## Tools

### create_note
Create or overwrite a note.

**Parameters:**
- `title` (string, required): The note title (used as filename)
- `content` (string, required): The note content

### read_note
Read a specific note by title.

**Parameters:**
- `title` (string, required): The note title to read

### list_notes
List all saved notes.

### search_notes
Search notes by keyword.

**Parameters:**
- `query` (string, required): The search term
