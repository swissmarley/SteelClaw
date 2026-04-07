"""Code Runner skill — execute Python/JS/Bash in a subprocess with timeout."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import os


_LANGUAGE_CONFIG = {
    "python": {"cmd": ["python3", "-u"], "ext": ".py"},
    "javascript": {"cmd": ["node"], "ext": ".js"},
    "bash": {"cmd": ["bash"], "ext": ".sh"},
}

TIMEOUT_SECONDS = 30


async def tool_run_code(code: str, language: str) -> str:
    """Execute code in a subprocess and return the output."""
    try:
        language = language.lower().strip()
        if language not in _LANGUAGE_CONFIG:
            return f"Error: Unsupported language '{language}'. Supported: python, javascript, bash"

        config = _LANGUAGE_CONFIG[language]
        binary = config["cmd"][0]

        if not shutil.which(binary):
            return f"Error: '{binary}' not found on this system. Please install it first."

        # Write code to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=config["ext"], delete=False
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                config["cmd"] + [tmp_path],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tempfile.gettempdir(),
            )

            output_parts = []
            if result.stdout:
                output_parts.append(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")
            if result.returncode != 0:
                output_parts.append(f"Exit code: {result.returncode}")

            if not output_parts:
                return "(no output)"

            return "\n".join(output_parts)

        finally:
            os.unlink(tmp_path)

    except subprocess.TimeoutExpired:
        return f"Error: Code execution timed out after {TIMEOUT_SECONDS} seconds."
    except Exception as e:
        return f"Error running code: {e}"


async def tool_scaffold_project(
    name: str,
    files: dict[str, str],
    requirements: list[str] | None = None,
) -> str:
    """Create a project directory structure with multiple files.

    Args:
        name: Project name (used as directory name)
        files: Dictionary mapping file paths to their content
        requirements: Optional list of Python packages for requirements.txt

    Returns:
        Summary of created files and directories
    """
    from pathlib import Path

    if not name:
        return "Error: Project name is required"
    if not files:
        return "Error: No files specified"

    # Create project directory within the current workspace
    # Security: Validate that the path stays within the workspace to prevent
    # path traversal attacks (e.g., "../../../etc/passwd" or "/etc/cron.d/evil")
    try:
        base_path = Path.cwd().resolve()
        project_path = (base_path / name).resolve()
        project_path.relative_to(base_path)
    except ValueError:
        return f"Error: Invalid project name '{name}' (must be a relative path within the workspace)"
    except Exception as e:
        return f"Error: Invalid project name '{name}': {e}"

    try:
        project_path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return f"Error: Directory '{name}' already exists. Choose a different project name."

    created_files = []
    created_dirs = set()

    # Create all files
    for file_path, content in files.items():
        full_path = (project_path / file_path).resolve()
        # Security: Ensure the resolved path stays within the project directory
        # This prevents path traversal attacks like "../../../etc/passwd"
        try:
            full_path.relative_to(project_path)
        except ValueError:
            # Clean up the created directory on error
            import shutil
            shutil.rmtree(project_path, ignore_errors=True)
            return f"Error: Invalid file path '{file_path}' (outside project directory)"
        parent_dir = full_path.parent

        # Create parent directories if needed
        if parent_dir != project_path:
            rel_parent = str(parent_dir.relative_to(project_path))
            if rel_parent not in created_dirs:
                parent_dir.mkdir(parents=True, exist_ok=True)
                created_dirs.add(rel_parent)

        # Write the file
        full_path.write_text(content, encoding="utf-8")
        created_files.append(file_path)

    # Create requirements.txt if specified
    if requirements:
        req_path = project_path / "requirements.txt"
        req_path.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        created_files.append("requirements.txt")

    # Summarize
    summary = [f"Created project '{name}' with {len(created_files)} files:"]
    for f in sorted(created_files):
        summary.append(f"  {f}")
    summary.append(f"\nProject directory: {project_path}")

    return "\n".join(summary)