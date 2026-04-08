"""Package manager skill — install and manage packages for Python, Node.js, and system."""

from __future__ import annotations

import shutil
from typing import Literal


async def _run_command(command: str, timeout: int = 120) -> str:
    """Execute a command via the security sandbox."""
    from steelclaw.security.sandbox import execute_command

    return await execute_command(command, timeout=timeout)


def _detect_package_manager() -> str:
    """Detect available package managers."""
    if shutil.which("pip") or shutil.which("pip3"):
        return "pip"
    if shutil.which("npm"):
        return "npm"
    return "pip"  # Default fallback


async def tool_pip_install(
    packages: list[str],
    upgrade: bool = False,
) -> str:
    """Install Python packages using pip.

    Args:
        packages: List of package names to install
        upgrade: Upgrade if already installed

    Returns:
        Installation result or error message
    """
    if not packages:
        return "Error: No packages specified"

    # Build pip command
    cmd_parts = ["pip install"]
    if upgrade:
        cmd_parts.append("--upgrade")
    cmd_parts.extend(packages)
    command = " ".join(cmd_parts)

    result = await _run_command(command, timeout=300)
    return f"Installed Python packages: {', '.join(packages)}\n{result}"


async def tool_npm_install(
    packages: list[str],
    dev: bool = False,
    yarn: bool = False,
) -> str:
    """Install Node.js packages using npm or yarn.

    Args:
        packages: List of package names to install
        dev: Install as dev dependency
        yarn: Use yarn instead of npm

    Returns:
        Installation result or error message
    """
    if not packages:
        return "Error: No packages specified"

    # Check if npm/yarn is available
    if yarn:
        if not shutil.which("yarn"):
            return "Error: yarn is not installed. Run: npm install -g yarn"
        cmd_parts = ["yarn add"]
        if dev:
            cmd_parts.append("--dev")
    else:
        if not shutil.which("npm"):
            return "Error: npm is not installed. Install Node.js first."
        cmd_parts = ["npm install"]
        if dev:
            cmd_parts.append("--save-dev")

    cmd_parts.extend(packages)
    command = " ".join(cmd_parts)

    result = await _run_command(command, timeout=300)
    manager = "yarn" if yarn else "npm"
    dep_type = "dev dependencies" if dev else "dependencies"
    return f"Installed Node.js {dep_type} via {manager}: {', '.join(packages)}\n{result}"


async def tool_apt_install(
    packages: list[str],
) -> str:
    """Install system packages using apt (Linux only, requires sudo).

    Args:
        packages: List of package names to install

    Returns:
        Installation result or error message
    """
    if not packages:
        return "Error: No packages specified"

    # Check if apt is available
    if not shutil.which("apt"):
        # Try apt-get as fallback
        if not shutil.which("apt-get"):
            return "Error: apt/apt-get is not available. This command is for Debian/Ubuntu Linux systems."
        apt_cmd = "apt-get"
    else:
        apt_cmd = "apt"

    from steelclaw.security.sandbox import execute_command
    # Build the apt command WITHOUT manually prepending sudo
    # Pass sudo=True to execute_command so it properly routes through SudoManager
    command = f"{apt_cmd} install -y {' '.join(packages)}"
    result = await execute_command(command, timeout=600, sudo=True)
    return f"Installed system packages: {', '.join(packages)}\n{result}"


async def tool_check_installed(
    package: str,
    manager: str | None = None,
) -> str:
    """Check if a package is already installed.

    Args:
        package: Package name to check
        manager: Package manager to check (pip, npm, yarn, apt). Auto-detects if not specified.

    Returns:
        Installation status and version info
    """
    if not package:
        return "Error: No package specified"

    # Auto-detect manager if not specified
    if manager is None:
        manager = _detect_package_manager()

    manager = manager.lower()

    if manager == "pip":
        command = f"pip show {package}"
        result = await _run_command(command, timeout=30)
        if "Name:" in result and "Version:" in result:
            # Extract version
            lines = result.split("\n")
            version = None
            for line in lines:
                if line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
                    break
            return f"✓ {package} is installed (version {version})\n{result}"
        return f"✗ {package} is not installed via pip\n{result}"

    elif manager in ("npm", "yarn"):
        if manager == "npm":
            if shutil.which("npm"):
                command = f"npm list {package} --depth=0"
                result = await _run_command(command, timeout=30)
                if package in result and "├──" in result or "└──" in result:
                    return f"✓ {package} is installed via npm\n{result}"
                return f"✗ {package} is not installed via npm\n{result}"
        else:  # yarn
            if shutil.which("yarn"):
                command = f"yarn list --pattern {package} --depth=0"
                result = await _run_command(command, timeout=30)
                if package in result:
                    return f"✓ {package} is installed via yarn\n{result}"
                return f"✗ {package} is not installed via yarn\n{result}"
        return f"Error: {manager} is not available"

    elif manager == "apt":
        command = f"dpkg -l {package}"
        result = await _run_command(command, timeout=30)
        if result and "ii" in result.split("\n")[0] if result.split("\n") else "":
            return f"✓ {package} is installed via apt\n{result}"
        return f"✗ {package} is not installed via apt\n{result}"

    else:
        return f"Error: Unknown package manager '{manager}'. Use: pip, npm, yarn, or apt"