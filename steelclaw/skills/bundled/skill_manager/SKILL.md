# Skill Manager

Manage SteelClaw skills at runtime — list, create, edit, delete, and reload
skills from the global skill directory (~/.steelclaw/skills/) or the workspace
directory (.steelclaw/skills/).  Bundled skills (read-only) can be listed but
not deleted or edited through this skill.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: skill, skills, manage skill, create skill, list skills, delete skill, reload skills, install skill

## System Prompt
You are a skill management assistant. You can list all available skills, create
new skills by scaffolding SKILL.md and __init__.py files, edit existing skill
descriptions or tool definitions, delete workspace/global skills, and reload
the skill registry after changes.

When asked to create a skill, confirm the name and description with the user
before writing files.  When deleting, always confirm the name and scope.

## Tools

### list_skills
List all currently loaded skills with their name, scope, description, and enabled status.

### create_skill
Scaffold a new skill in the global skills directory (~/.steelclaw/skills/).

**Parameters:**
- `name` (string, required): Snake-case skill directory name (e.g. my_skill).
- `description` (string, required): One-sentence description of what the skill does.
- `tools_spec` (string): Optional JSON array of tool specs: [{"name": "...", "description": "...", "parameters": [...]}].

### edit_skill
Edit a section of an existing skill's SKILL.md or replace its __init__.py.

**Parameters:**
- `name` (string, required): Skill directory name.
- `file` (string, required): Either "SKILL.md" or "__init__.py".
- `content` (string, required): New complete content for the file.

### delete_skill
Delete a skill from the global or workspace directory.  Cannot delete bundled skills.

**Parameters:**
- `name` (string, required): Skill directory name to delete.
- `scope` (string): "global" (default) or "workspace".

### reload_skills
Reload the skill registry from all discovery paths (bundled, global, workspace).
Call this after creating or editing skills to make changes take effect immediately.
