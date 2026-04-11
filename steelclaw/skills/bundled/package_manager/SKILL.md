# Package Manager

Install and manage packages for Python, Node.js, and system-level packages.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: install, package, pip, npm, yarn, dependency, requirements, apt

## System Prompt
You can install packages using pip, npm, yarn, or apt.
Always check if a package is already installed before installing.
System packages require elevated permissions — explain what will be installed.
After installing packages, verify the installation was successful.

## Tools

### pip_install
Install Python packages using pip.

**Parameters:**
- `packages` (array, required): Package names to install (e.g., ["requests", "flask"])
- `upgrade` (boolean): Upgrade if already installed (default: false)

### npm_install
Install Node.js packages using npm or yarn.

**Parameters:**
- `packages` (array, required): Package names to install (e.g., ["express", "lodash"])
- `dev` (boolean): Install as dev dependency (default: false)
- `yarn` (boolean): Use yarn instead of npm (default: false)

### apt_install
Install system packages using apt (Linux only, requires sudo approval).

**Parameters:**
- `packages` (array, required): Package names to install (e.g., ["git", "curl"])

### check_installed
Check if a package is already installed.

**Parameters:**
- `package` (string, required): Package name to check
- `manager` (string): Package manager to check (pip, npm, yarn, apt) - default: auto-detect