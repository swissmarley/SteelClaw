"""Central path resolution — ensures all relative paths work regardless of CWD.

The project root is determined from the installed package location, not the
current working directory.  Every component that needs config.json, the database,
skill directories, or other project-relative paths should import from here.
"""

from __future__ import annotations

from pathlib import Path

# The package lives at <project_root>/steelclaw/, so go up one level
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


def resolve_path(path_str: str) -> Path:
    """Resolve a path that may be relative to the project root.

    - Absolute paths are returned as-is.
    - Paths starting with ~ are expanded.
    - Relative paths are resolved relative to PROJECT_ROOT.
    """
    p = Path(path_str)
    if p.is_absolute():
        return p
    expanded = Path(path_str).expanduser()
    if expanded.is_absolute():
        return expanded
    return (PROJECT_ROOT / p).resolve()
