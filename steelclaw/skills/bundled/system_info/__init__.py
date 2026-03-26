"""System info skill — query host system status."""

from __future__ import annotations

import os
import platform
import shutil


async def tool_system_status() -> str:
    """Get a summary of system information."""
    lines = ["## System Status\n"]

    # OS info
    lines.append(f"**OS:** {platform.system()} {platform.release()} ({platform.machine()})")
    lines.append(f"**Hostname:** {platform.node()}")
    lines.append(f"**Python:** {platform.python_version()}")

    # Disk usage
    try:
        usage = shutil.disk_usage("/")
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        pct = (usage.used / usage.total) * 100
        lines.append(f"**Disk (/):** {used_gb:.1f}GB / {total_gb:.1f}GB ({pct:.0f}% used, {free_gb:.1f}GB free)")
    except Exception:
        pass

    # Try psutil for CPU/memory
    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        lines.append(f"**CPU:** {psutil.cpu_count()} cores, {cpu_pct}% usage")
        lines.append(f"**Memory:** {mem.used / (1024**3):.1f}GB / {mem.total / (1024**3):.1f}GB ({mem.percent}%)")

        # Uptime
        import time
        boot = psutil.boot_time()
        uptime_secs = time.time() - boot
        days = int(uptime_secs // 86400)
        hours = int((uptime_secs % 86400) // 3600)
        lines.append(f"**Uptime:** {days}d {hours}h")
    except ImportError:
        lines.append("\n*Install `psutil` for CPU/memory details.*")

    return "\n".join(lines)


async def tool_list_processes(sort_by: str = "cpu", limit: int = 15) -> str:
    """List running processes."""
    try:
        import psutil
    except ImportError:
        # Fallback to ps command
        import asyncio
        proc = await asyncio.create_subprocess_shell(
            f"ps aux --sort=-%{'cpu' if sort_by == 'cpu' else 'mem'} | head -{limit + 1}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode(errors="replace") if stdout else "Could not list processes. Install psutil for better support."

    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    procs.sort(key=lambda x: x.get(key, 0) or 0, reverse=True)

    lines = [f"{'PID':<8} {'CPU%':<7} {'MEM%':<7} NAME"]
    for p in procs[:limit]:
        lines.append(f"{p['pid']:<8} {p.get('cpu_percent', 0) or 0:<7.1f} {p.get('memory_percent', 0) or 0:<7.1f} {p['name']}")
    return "\n".join(lines)


async def tool_get_environment(names: str) -> str:
    """Get environment variable values."""
    results = []
    for name in names.split(","):
        name = name.strip()
        value = os.environ.get(name)
        if value is not None:
            # Truncate long values
            display = value if len(value) < 200 else value[:200] + "..."
            results.append(f"**{name}:** {display}")
        else:
            results.append(f"**{name}:** (not set)")
    return "\n".join(results)
