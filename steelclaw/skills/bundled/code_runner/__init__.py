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
