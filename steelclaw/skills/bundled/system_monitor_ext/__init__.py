"""System Monitor Extended skill — CPU, memory, disk, and process monitoring."""

from __future__ import annotations

import platform
import subprocess


def _run_cmd(cmd: list[str]) -> str:
    """Run a system command and return output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception as e:
        return f"(command failed: {e})"


async def tool_get_system_stats() -> str:
    """Get current CPU, memory, and system load statistics."""
    try:
        try:
            import psutil

            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            load = os.getloadavg() if hasattr(os, "getloadavg") else None

            lines = [
                "=== System Stats ===",
                f"Platform: {platform.system()} {platform.release()}",
                f"CPU: {cpu_count} cores, {cpu_percent}% usage",
            ]
            if cpu_freq:
                lines.append(f"CPU Freq: {cpu_freq.current:.0f} MHz")
            lines.extend([
                f"Memory: {mem.used / (1024**3):.1f} GB / {mem.total / (1024**3):.1f} GB ({mem.percent}%)",
                f"Swap: {swap.used / (1024**3):.1f} GB / {swap.total / (1024**3):.1f} GB ({swap.percent}%)",
            ])
            if load:
                lines.append(f"Load avg: {load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}")

            import datetime
            boot = datetime.datetime.fromtimestamp(psutil.boot_time())
            lines.append(f"Boot time: {boot.strftime('%Y-%m-%d %H:%M:%S')}")

            return "\n".join(lines)

        except ImportError:
            # Fallback to system commands
            lines = [
                "=== System Stats (psutil not available) ===",
                f"Platform: {platform.system()} {platform.release()}",
                "",
            ]
            system = platform.system()
            if system == "Darwin":
                lines.append("Memory:\n" + _run_cmd(["vm_stat"]))
                lines.append("\nLoad:\n" + _run_cmd(["sysctl", "-n", "vm.loadavg"]))
            elif system == "Linux":
                lines.append("Memory:\n" + _run_cmd(["free", "-h"]))
                lines.append("\nLoad:\n" + _run_cmd(["cat", "/proc/loadavg"]))
            else:
                lines.append("Install psutil for detailed stats: pip install psutil")

            return "\n".join(lines)

    except Exception as e:
        return f"Error getting system stats: {e}"


async def tool_get_process_list(count: int = 10) -> str:
    """List the top processes by CPU or memory usage."""
    try:
        try:
            import psutil

            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    info = p.info
                    procs.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort by CPU then memory
            procs.sort(key=lambda x: (x.get("cpu_percent") or 0), reverse=True)
            top = procs[:count]

            lines = [f"{'PID':>7}  {'CPU%':>6}  {'MEM%':>6}  NAME"]
            lines.append("-" * 50)
            for p in top:
                lines.append(
                    f"{p['pid']:>7}  {p.get('cpu_percent', 0):>5.1f}%  "
                    f"{p.get('memory_percent', 0):>5.1f}%  {p.get('name', '?')}"
                )
            return "\n".join(lines)

        except ImportError:
            system = platform.system()
            if system in ("Darwin", "Linux"):
                output = _run_cmd(["ps", "aux", "--sort=-pcpu"])
                lines = output.split("\n")[:count + 1]
                return "\n".join(lines)
            return "Install psutil for process listing: pip install psutil"

    except Exception as e:
        return f"Error listing processes: {e}"


async def tool_get_disk_usage() -> str:
    """Get disk usage information for all mounted filesystems."""
    try:
        try:
            import psutil

            partitions = psutil.disk_partitions()
            lines = [f"{'Device':<25} {'Mount':<20} {'Total':>8} {'Used':>8} {'Free':>8} {'Use%':>5}"]
            lines.append("-" * 90)

            for part in partitions:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    lines.append(
                        f"{part.device:<25} {part.mountpoint:<20} "
                        f"{usage.total / (1024**3):>7.1f}G "
                        f"{usage.used / (1024**3):>7.1f}G "
                        f"{usage.free / (1024**3):>7.1f}G "
                        f"{usage.percent:>4.1f}%"
                    )
                except (PermissionError, OSError):
                    lines.append(f"{part.device:<25} {part.mountpoint:<20} (access denied)")

            return "\n".join(lines)

        except ImportError:
            return "Disk usage (via df):\n\n" + _run_cmd(["df", "-h"])

    except Exception as e:
        return f"Error getting disk usage: {e}"


# Needed for the os.getloadavg fallback
import os
