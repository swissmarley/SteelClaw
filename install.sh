#!/usr/bin/env bash
# SteelClaw installation script
# Usage: bash install.sh

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BOLD}SteelClaw Installer${NC}"
echo "================================"

# Check Python version
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
        major=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null)
        minor=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            PYTHON="$cmd"
            echo -e "${GREEN}Found Python $version ($cmd)${NC}"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}Error: Python 3.9+ is required but not found${NC}"
    echo "Install Python from https://python.org or via your package manager:"
    echo "  macOS: brew install python@3.11"
    echo "  Ubuntu: sudo apt install python3.11"
    exit 1
fi

# Install in editable mode with all extras
echo -e "\n${BOLD}Installing SteelClaw...${NC}"
"$PYTHON" -m pip install -e ".[all]" --quiet

# Create directory structure
echo -e "\n${BOLD}Setting up directories...${NC}"
mkdir -p ~/.steelclaw/logs
mkdir -p ~/.steelclaw/skills
mkdir -p ~/.steelclaw/chromadb

# Verify installation
if command -v steelclaw &>/dev/null; then
    echo -e "\n${GREEN}✓ SteelClaw installed successfully!${NC}"
    echo -e "  Version: $(steelclaw --help 2>&1 | head -1 || echo 'installed')"
else
    # Try to find the scripts directory
    SCRIPTS_DIR=$("$PYTHON" -c "import sysconfig; print(sysconfig.get_path('scripts'))" 2>/dev/null)
    echo -e "\n${YELLOW}SteelClaw installed but 'steelclaw' not found in PATH.${NC}"
    echo -e "Add this to your shell profile:"

    SHELL_NAME=$(basename "$SHELL")
    if [ "$SHELL_NAME" = "zsh" ]; then
        echo -e "  echo 'export PATH=\"$SCRIPTS_DIR:\$PATH\"' >> ~/.zshrc"
        echo -e "  source ~/.zshrc"
    else
        echo -e "  echo 'export PATH=\"$SCRIPTS_DIR:\$PATH\"' >> ~/.bashrc"
        echo -e "  source ~/.bashrc"
    fi
fi

echo -e "\n${BOLD}Quick start:${NC}"
echo "  steelclaw setup     # Interactive onboarding"
echo "  steelclaw serve     # Start server (foreground)"
echo "  steelclaw start     # Start server (background)"
echo "  steelclaw chat      # Connect via CLI chat"
echo ""
