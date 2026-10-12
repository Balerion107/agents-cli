# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared language configuration and utilities for CLI commands.

This module centralizes language-specific configuration (Python, Go, Java, TypeScript)
used by enhance and upgrade commands. It provides:

- LANGUAGE_CONFIGS: Configuration dict for each supported language
- get_language_config(): Get config dict for a language
"""

import logging
import pathlib
import tomllib
from collections.abc import Callable, Mapping
from typing import Any

import click


def _read_python_version(root: pathlib.Path) -> str:
    """Return the ``[project].version`` from ``pyproject.toml`` or raise."""
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found in {root}")
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)  # PEP 621 [project] section
    version = data.get("project", {}).get("version")
    if version and isinstance(version, str):
        return version
    raise KeyError(f"no [project].version in {pyproject_path}")


# =============================================================================
# Language Configuration
# =============================================================================
# To add a new language, add an entry with the required keys.


LANGUAGE_CONFIGS: dict[str, dict[str, Any]] = {
    "python": {
        "lock_file": "uv.lock",
        "lock_command": ["uv", "lock"],
        "lock_command_name": "uv lock",
        "display_name": "Python",
        "agent_file": "agent.py",
        "agent_variable": "root_agent",
        "agent_in_subdirectory": False,
        "version_reader": _read_python_version,
        "api_base_path": "",
        "a2a_base_path_factory": lambda app_name: f"/a2a/{app_name}",
    },
    "go": {
        "lock_file": "go.sum",
        "lock_command": ["go", "mod", "tidy"],
        "lock_command_name": "go mod tidy",
        "display_name": "Go",
        "agent_file": "agent.go",
        "agent_variable": "RootAgent",
        "agent_in_subdirectory": False,
        "version_reader": None,
        "api_base_path": "",
        "a2a_base_path_factory": lambda _app_name: "",
    },
    "java": {
        "lock_file": None,  # Maven doesn't have a separate lock file
        "lock_command": ["mvn", "dependency:resolve"],
        "lock_command_name": "mvn dependency:resolve",
        "display_name": "Java",
        "agent_file": "Agent.java",
        "agent_file_pattern": "**/Agent.java",
        "agent_variable": "ROOT_AGENT",
        "agent_in_subdirectory": True,  # Java uses package subdirectories
        "version_reader": None,
        "api_base_path": "",
        "a2a_base_path_factory": None,
    },
    "typescript": {
        "lock_file": "package-lock.json",
        "lock_command": ["npm", "install", "--package-lock-only"],
        "lock_command_name": "npm install --package-lock-only",
        "display_name": "TypeScript",
        "agent_file": "agent.ts",
        "agent_variable": "rootAgent",
        "agent_in_subdirectory": False,
        "version_reader": None,
        "api_base_path": "",
        "a2a_base_path_factory": None,
    },
}


def get_language_config(language: str) -> dict[str, Any]:
    """Get the configuration dict for a language.

    Args:
        language: Language key (e.g., 'python', 'go')

    Returns:
        The language configuration dict, or Python config as fallback
    """
    return LANGUAGE_CONFIGS.get(language, LANGUAGE_CONFIGS["python"])


class UnsupportedLanguageError(click.ClickException):
    """Raised when a command has no handler for the project's language."""


def dispatch_language(
    command_name: str,
    handlers: Mapping[str, Callable | None],
    language: str,
) -> Callable:
    """Return the handler for ``language``, or raise a clear error.

    A ``None`` entry (or a missing key) means the command is intentionally not
    wired up for that language yet, so the user gets an actionable message
    instead of the command silently doing the wrong thing.

    Args:
        command_name: The user-facing command (e.g. ``"install"``) for messages.
        handlers: Map of language -> handler callable (or ``None`` if the
            command doesn't support that language yet).
        language: The project's language.

    Returns:
        The handler callable for ``language``.

    Raises:
        UnsupportedLanguageError: If no handler is registered for ``language``.
    """
    handler = handlers.get(language)
    if handler is None:
        supported = ", ".join(sorted(k for k, v in handlers.items() if v is not None))
        raise UnsupportedLanguageError(
            f"`agents-cli {command_name}` isn't supported for '{language}' "
            f"projects.\n  Supported languages: {supported}."
        )
    return handler


def find_agent_file(
    project_dir: pathlib.Path,
    language: str,
    agent_directory: str,
) -> pathlib.Path | None:
    """Find the primary agent file for a language.

    For Python: {agent_directory}/agent.py
    For Go: {agent_directory}/agent.go
    For Java: {agent_directory}/**/Agent.java (searches package subdirectories)
    For TypeScript: {agent_directory}/agent.ts

    Args:
        project_dir: Project root directory
        language: Language key ('python', 'go', 'java', 'typescript')
        agent_directory: Agent directory relative to project root

    Returns:
        Path to agent file if found, None otherwise
    """
    lang_config = get_language_config(language)
    agent_folder = project_dir / agent_directory

    if not agent_folder.exists():
        return None

    # Check for YAML config agent first (all languages)
    yaml_agent = agent_folder / "root_agent.yaml"
    if yaml_agent.exists():
        return yaml_agent

    agent_file_name = lang_config.get("agent_file")
    if not agent_file_name:
        return None

    # For languages with agent in subdirectory (Java package structure)
    if lang_config.get("agent_in_subdirectory"):
        for found in agent_folder.rglob(agent_file_name):
            return found
        return None

    # Standard case: agent file directly in agent directory
    agent_file = agent_folder / agent_file_name
    return agent_file if agent_file.exists() else None


def validate_agent_file(
    agent_file: pathlib.Path,
    language: str,
) -> tuple[bool, str | None]:
    """Validate that the agent file contains the required variable.

    Args:
        agent_file: Path to the agent file
        language: Language key

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    lang_config = get_language_config(language)
    required_var = lang_config.get("agent_variable", "root_agent")

    # YAML config agents are always valid
    if agent_file.name == "root_agent.yaml":
        return True, None

    try:
        content = agent_file.read_text(encoding="utf-8")

        if required_var in content:
            return True, None
        else:
            return False, f"Missing '{required_var}' variable in {agent_file.name}"
    except Exception as e:
        return False, f"Could not read {agent_file.name}: {e}"


def get_agent_file_hint(
    dir_path: pathlib.Path,
    language: str | None = None,
) -> str:
    """Get hint string for directory selection.

    Args:
        dir_path: Directory to check
        language: Optional language hint

    Returns:
        Hint string like ' (has Agent.java)' or ''
    """
    if not dir_path.is_dir():
        return ""

    # Check YAML config agent first
    if (dir_path / "root_agent.yaml").exists():
        return " (has root_agent.yaml)"

    # Check for Java Agent.java (in subdirectories)
    if any(dir_path.rglob("Agent.java")):
        return " (has Agent.java)"

    # Check for Go agent.go
    if (dir_path / "agent.go").exists():
        return " (has agent.go)"

    # Check for TypeScript agent.ts
    if (dir_path / "agent.ts").exists():
        return " (has agent.ts)"

    # Check for Python agent.py
    if (dir_path / "agent.py").exists():
        return " (has agent.py)"

    return ""


def get_project_version(
    project_dir: str | pathlib.Path,
    default_version: str = "0.0.0",
) -> str:
    """Extract the project version, falling back to ``default_version``.
    Dispatches on the project language to its config ``version_reader``. Languages with no reader take the default silently.

    Args:
        project_dir: The project root directory.
        default_version: The fallback version to return if not found.
    Returns:
        The extracted version string, or default_version.
    """
    from google.agents.cli._project import read_project_config

    root = pathlib.Path(project_dir)
    language = read_project_config(str(root)).language
    reader = get_language_config(language).get("version_reader")
    if reader is None:
        return default_version

    try:
        return reader(root)
    except Exception as e:
        logging.warning(
            "Could not read the project version (%s). Falling back to %s — set "
            "the version in your project, or pass AGENT_VERSION via "
            "--env-vars to override.",
            e,
            default_version,
        )
    return default_version
