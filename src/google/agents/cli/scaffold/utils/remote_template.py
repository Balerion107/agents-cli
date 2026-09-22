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

import logging
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from typing import Any, NamedTuple

import click

from google.agents.cli._output import Console


@dataclass
class RemoteTemplateSpec:
    """Parsed remote template specification."""

    repo_url: str
    template_path: str
    git_ref: str
    is_adk_samples: bool = False


class FetchedTemplate(NamedTuple):
    """Result of fetching a remote template.

    Attributes:
        template_dir: Path to the fetched template directory.
        temp_dir: Top-level temporary directory that should be cleaned up.
        repo_root: Root of the cloned repository.
    """

    template_dir: pathlib.Path
    temp_dir: pathlib.Path
    repo_root: pathlib.Path


def is_template_spec(value: str) -> bool:
    """True for a value naming a template to fetch rather than one this CLI ships."""
    return value.startswith("local@") or parse_agent_spec(value) is not None


def parse_agent_spec(agent_spec: str) -> RemoteTemplateSpec | None:
    """Parse agent specification to determine if it's a remote template.

    Args:
        agent_spec: Agent specification string

    Returns:
        RemoteTemplateSpec if remote template, None if local template
    """
    # Check for local@ prefix
    if agent_spec.startswith("local@"):
        return None

    # Check for adk@ shortcut
    if agent_spec.startswith("adk@"):
        sample_name = agent_spec[4:]  # Remove "adk@" prefix
        return RemoteTemplateSpec(
            repo_url="https://github.com/google/adk-samples",
            template_path=f"python/agents/{sample_name}",
            git_ref="main",
            is_adk_samples=True,
        )

    # GitHub /tree/ URL pattern
    tree_pattern = r"^(https?://[^/]+/[^/]+/[^/]+)/tree/([^/]+)/(.*)$"
    match = re.match(tree_pattern, agent_spec)
    if match:
        repo_url = match.group(1)
        git_ref = match.group(2)
        template_path = match.group(3)
        return RemoteTemplateSpec(
            repo_url=repo_url,
            template_path=template_path.strip("/"),
            git_ref=git_ref,
        )

    # General remote pattern: <repo_url>[/<path>][@<ref>]
    # Handles github.com, gitlab.com, etc.
    remote_pattern = r"^(https?://[^/]+/[^/]+/[^/@]+)(?:/(.*?))?(?:@([^/]+))?/?$"
    match = re.match(remote_pattern, agent_spec)
    if match:
        repo_url = match.group(1)
        template_path_with_ref = match.group(2) or ""
        git_ref_from_url = match.group(3)

        # Separate path and ref if ref is part of the path
        template_path = template_path_with_ref
        git_ref = git_ref_from_url or "main"

        if "@" in template_path:
            path_parts = template_path.split("@")
            template_path = path_parts[0]
            git_ref = path_parts[1]

        # Check if this is the ADK samples repository
        is_adk_samples = repo_url == "https://github.com/google/adk-samples"

        return RemoteTemplateSpec(
            repo_url=repo_url,
            template_path=template_path.strip("/"),
            git_ref=git_ref,
            is_adk_samples=is_adk_samples,
        )

    # GitHub shorthand: <org>/<repo>[/<path>][@<ref>]
    github_shorthand_pattern = r"^([^/]+)/([^/@]+)(?:/(.*?))?(?:@([^/]+))?/?$"
    match = re.match(github_shorthand_pattern, agent_spec)
    if match and "/" in agent_spec:  # Ensure it has at least one slash
        org = match.group(1)
        repo = match.group(2)
        template_path = match.group(3) or ""
        git_ref = match.group(4) or "main"

        # Check if this is the ADK samples repository
        is_adk_samples = org == "google" and repo == "adk-samples"

        return RemoteTemplateSpec(
            repo_url=f"https://github.com/{org}/{repo}",
            template_path=template_path,
            git_ref=git_ref,
            is_adk_samples=is_adk_samples,
        )

    return None


def check_and_execute_with_version_lock(
    template_dir: pathlib.Path,
    original_agent_spec: str | None = None,
    locked: bool = False,
    project_name: str | None = None,
) -> bool:
    """Check if remote template has agents-cli version lock.

    Since the ACLI code is vendored into agents-cli, version locking
    is no longer needed — we always use the vendored version. This
    function now simply logs the version info and returns False to let
    the caller proceed with the vendored code.

    Returns:
        Always False (proceed with vendored code).
    """
    if locked or os.environ.get("ACLI_SKIP_VERSION_LOCK") == "1":
        return False

    uv_lock_path = template_dir / "uv.lock"
    version = parse_acli_version_from_lock(uv_lock_path)

    if version:
        logging.debug(
            "Remote template specifies agents-cli version %s; using vendored code instead.",
            version,
        )

    return False


def fetch_remote_template(
    spec: RemoteTemplateSpec,
    original_agent_spec: str | None = None,
    locked: bool = False,
    project_name: str | None = None,
) -> FetchedTemplate:
    """Fetch remote template and return path to template directory.

    Uses Git to clone the remote repository. If the template contains a uv.lock
    with agents-cli version constraint, will execute nested uvx command.

    Args:
        spec: Remote template specification
        original_agent_spec: Original agent spec string (used to prevent recursion)
        locked: Whether this is already a locked execution (prevents recursion)
        project_name: Project name (may have been entered interactively)

    Returns:
        A ``FetchedTemplate`` with the fetched template directory, the top-level
        temporary directory to clean up, and the cloned repository root.
    """
    temp_dir = tempfile.mkdtemp(prefix="acli_remote_template_")
    temp_path = pathlib.Path(temp_dir)
    repo_path = temp_path / "repo"

    # Attempt Git Clone
    try:
        clone_url = spec.repo_url

        # Build clone command with --single-branch (optimized for branches)
        clone_cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--branch",
            spec.git_ref,
            clone_url,
            str(repo_path),
        ]

        from google.agents.cli._runner import run_resolved

        logging.debug(
            "Attempting to clone remote template with Git: %s", shlex.join(clone_cmd)
        )
        # GIT_TERMINAL_PROMPT=0 prevents git from prompting for credentials
        result = run_resolved(
            clone_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )

        # If clone with --single-branch fails, retry without it (for tags)
        if result.returncode != 0:
            # Check if the error is related to branch not found (indicates it's likely a tag)
            if "Remote branch" in result.stderr or "not found" in result.stderr:
                logging.debug(
                    "Clone with --single-branch failed, retrying without it (git_ref '%s' is likely a tag)",
                    spec.git_ref,
                )
                clone_cmd_without_single_branch = [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    spec.git_ref,
                    clone_url,
                    str(repo_path),
                ]
                run_resolved(
                    clone_cmd_without_single_branch,
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding="utf-8",
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                )
                logging.debug("Git clone successful (without --single-branch).")
            else:
                # Different error, raise it
                raise subprocess.CalledProcessError(
                    result.returncode, clone_cmd, result.stdout, result.stderr
                )
        else:
            logging.debug("Git clone successful.")
    except subprocess.CalledProcessError as e:
        shutil.rmtree(temp_path, ignore_errors=True)
        raise RuntimeError(f"Git clone failed: {e.stderr.strip()}") from e

    # Process the successfully fetched template
    try:
        if spec.template_path:
            template_dir = repo_path / spec.template_path
        else:
            template_dir = repo_path

        if not template_dir.exists():
            raise FileNotFoundError(
                f"Template path not found in the repository: {spec.template_path}"
            )

        # Check for version lock and execute nested command if found
        if check_and_execute_with_version_lock(
            template_dir, original_agent_spec, locked, project_name
        ):
            # If we executed with locked version, the nested process will handle everything
            # Clean up and exit successfully
            shutil.rmtree(temp_path, ignore_errors=True)
            # Exit with success since the nested command will handle the rest
            sys.exit(0)

        return FetchedTemplate(
            template_dir=template_dir, temp_dir=temp_path, repo_root=repo_path
        )
    except Exception as e:
        # Clean up on error
        shutil.rmtree(temp_path, ignore_errors=True)
        raise RuntimeError(
            f"An unexpected error occurred after fetching remote template: {e}"
        ) from e


def _detect_flat_structure(template_dir: pathlib.Path) -> bool:
    """Detect if template has a flat structure (agent code in root).

    A flat structure means:
    - agent.py exists directly in the template root
    - No obvious agent subdirectory exists (like 'app/' or folder_name as package)

    Args:
        template_dir: Path to template directory

    Returns:
        True if template has flat structure, False otherwise
    """
    # Check if agent.py exists in root
    agent_py_in_root = (template_dir / "agent.py").exists()
    if not agent_py_in_root:
        return False

    # Check for common agent subdirectory patterns
    folder_name = template_dir.name.replace("-", "_")
    potential_agent_dirs = ["app", folder_name]

    for subdir in potential_agent_dirs:
        subdir_path = template_dir / subdir
        if subdir_path.is_dir() and (subdir_path / "agent.py").exists():
            # Found a proper agent subdirectory
            return False

    logging.debug(
        "Detected flat structure in '%s': agent.py in root, no agent subdirectory",
        template_dir,
    )
    return True


def _get_source_agent_directory(template_dir: pathlib.Path) -> str:
    """Return the subdirectory that holds a nested sample's ``agent.py``.

    Samples following the Agent Starter Pack convention keep their code in
    ``app/`` regardless of the folder name; others use a package named after the
    folder. Preferring the folder-named package keeps behavior unchanged for
    samples that already template into one directory, and falls back to ``app``
    so ``app``-convention samples (e.g. deep-search) template into the directory
    they actually reference — instead of splitting into two.

    Args:
        template_dir: Path to template directory

    Returns:
        The detected package directory name, defaulting to the folder-derived
        name when neither candidate contains ``agent.py``.
    """
    folder_pkg = template_dir.name.replace("-", "_")
    for candidate in (folder_pkg, "app"):
        if (template_dir / candidate / "agent.py").exists():
            return candidate
    return folder_pkg


def _infer_agent_directory_for_adk(
    template_dir: pathlib.Path, is_adk_sample: bool
) -> dict[str, Any]:
    """Infer agent configuration for ADK samples only using Python conventions.

    Args:
        template_dir: Path to template directory
        is_adk_sample: Whether this is an ADK sample

    Returns:
        Dictionary with inferred configuration, or empty dict if not ADK sample
    """
    if not is_adk_sample:
        return {}

    # Check for flat structure (agent code in root)
    is_flat = _detect_flat_structure(template_dir)

    # Convert folder name to Python package convention (hyphens to underscores)
    folder_name = template_dir.name
    folder_pkg = folder_name.replace("-", "_")

    if is_flat:
        logging.debug(
            "Flat structure detected: source is '.', target agent_directory is '%s'",
            folder_pkg,
        )
        return {
            "settings": {
                "agent_directory": folder_pkg,
                "source_agent_directory": ".",  # Special value for flat structure
            },
            "has_explicit_config": False,
            "is_flat_structure": True,
        }

    # Nested structure: target the sample's actual package directory so the
    # base-template render and the remote overlay land in the same directory.
    # Deriving the target from the folder name while the sample ships its code
    # in `app/` produced two agent directories.
    agent_directory = _get_source_agent_directory(template_dir)
    logging.debug(
        "Inferred agent_directory '%s' from the sample's package layout for "
        "ADK sample '%s'",
        agent_directory,
        folder_name,
    )

    return {
        "settings": {
            "agent_directory": agent_directory,
        },
        "has_explicit_config": False,
    }


def load_remote_template_config(
    template_dir: pathlib.Path,
    cli_overrides: dict[str, Any] | None = None,
    is_adk_sample: bool = False,
) -> dict[str, Any]:
    """Load template configuration from remote template's .template/templateconfig.yaml,
    agents-cli-manifest.yaml, or legacy [tool.agents-cli] section in pyproject.toml
    with CLI overrides.

    CLI overrides take precedence over all other sources. For ADK samples without
    explicit config, uses smart inference for agent directory naming.

    Args:
        template_dir: Path to template directory
        cli_overrides: Configuration overrides from CLI (takes highest precedence)
        is_adk_sample: Whether this is an ADK sample (enables smart inference)

    Returns:
        Template configuration dictionary with merged sources
    """
    config: dict[str, Any] = {}
    has_explicit_config = False

    # Start with defaults
    defaults = {
        "base_template": "adk",
        "name": template_dir.name,
        "description": "",
        "agent_directory": "app",  # Default for non-ADK samples
    }
    config.update(defaults)

    # Load from .template/templateconfig.yaml, agents-cli-manifest.yaml, or pyproject.toml
    template_config_path = template_dir / ".template" / "templateconfig.yaml"
    manifest_path = template_dir / "agents-cli-manifest.yaml"
    pyproject_path = template_dir / "pyproject.toml"

    if template_config_path.exists():
        try:
            import yaml

            with open(template_config_path, encoding="utf-8") as f:
                template_config = yaml.safe_load(f) or {}
            has_explicit_config = bool(template_config)
            if template_config:
                config.update(template_config)
                logging.debug(
                    "Found explicit .template/templateconfig.yaml configuration"
                )
        except Exception as e:
            # Falling through would treat the template as an ADK sample and
            # render a different project than the one it declares. ClickException
            # so the commands that surface it print the template author's typo
            # as an error rather than a traceback.
            raise click.ClickException(
                f"{template_config_path.name} is not valid YAML: {e}"
            ) from e
    elif manifest_path.exists():
        try:
            import yaml

            with open(manifest_path, encoding="utf-8") as f:
                manifest_config = yaml.safe_load(f) or {}
            has_explicit_config = bool(manifest_config)
            if manifest_config:
                config.update(manifest_config)
                logging.debug("Found explicit agents-cli-manifest.yaml configuration")
        except Exception as e:
            logging.error(f"Error loading agents-cli-manifest.yaml config: {e}")
    elif pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomllib.load(f)

            # Extract the agents-cli configuration
            toml_config = pyproject_data.get("tool", {}).get("agents-cli", {})

            # Fallback to [project] fields if not specified in agents-cli section
            project_info = pyproject_data.get("project", {})

            # Track if we have explicit configuration
            has_explicit_config = bool(toml_config)

            # Apply pyproject.toml configuration (overrides defaults)
            if toml_config:
                config.update(toml_config)
                logging.debug("Found explicit [tool.agents-cli] configuration")

            # Apply [project] fallbacks if not already set
            if "name" not in toml_config and "name" in project_info:
                config["name"] = project_info["name"]

            if "description" not in toml_config and "description" in project_info:
                config["description"] = project_info["description"]

            logging.debug("Loaded template config from %s", pyproject_path)
        except Exception as e:
            logging.error(f"Error loading pyproject.toml config: {e}")
    else:
        # No config file found
        if is_adk_sample:
            logging.debug(
                "No config file found for ADK sample %s, will use inference",
                template_dir.name,
            )
        else:
            logging.warning(
                "%s declares no agents-cli configuration, so it is treated as an ADK "
                "template. Add .template/templateconfig.yaml to say otherwise.",
                template_dir.name,
            )

    # Apply ADK inference if no explicit config and this is an ADK sample
    if not has_explicit_config and is_adk_sample:
        try:
            inferred_config = _infer_agent_directory_for_adk(template_dir, is_adk_sample)
            config.update(inferred_config)
            logging.debug("Applied ADK inference for template without explicit config")
        except Exception as e:
            logging.warning(f"Failed to apply ADK inference for {template_dir}: {e}")
            # Continue with default configuration

    # Detect flat structure for all remote templates (not just ADK samples)
    # This handles cases where agent.py is in root with no subdirectory
    if not has_explicit_config and not is_adk_sample:
        if _detect_flat_structure(template_dir):
            folder_name = template_dir.name.replace("-", "_")
            config.setdefault("settings", {})
            config["settings"]["agent_directory"] = folder_name
            config["settings"]["source_agent_directory"] = "."
            config["is_flat_structure"] = True
            logging.debug(
                "Detected flat structure for non-ADK template: source='.', target='%s'",
                folder_name,
            )

    # Add metadata about configuration source
    config["has_explicit_config"] = bool(has_explicit_config)

    # Apply CLI overrides (highest precedence) using deep merge
    if cli_overrides:
        config = merge_template_configs(config, cli_overrides)
        logging.debug("Applied CLI overrides: %s", cli_overrides)

    return config


def get_base_template_name(config: dict[str, Any]) -> str:
    """Get base template name from remote template config.

    Args:
        config: Template configuration dictionary

    Returns:
        Base template name (defaults to "adk"), with legacy aliases resolved
    """
    # Lazy import to avoid circular dependency
    from .template import resolve_agent_alias

    base_template = config.get("base_template", "adk")
    return resolve_agent_alias(base_template) or "adk"


def merge_template_configs(
    base_config: dict[str, Any], remote_config: dict[str, Any]
) -> dict[str, Any]:
    """Merge base template config with remote template config using a deep merge.

    Args:
        base_config: Base template configuration
        remote_config: Remote template configuration

    Returns:
        Merged configuration with remote overriding base
    """
    import copy

    def deep_merge(d1: dict[str, Any], d2: dict[str, Any]) -> dict[str, Any]:
        """Recursively merges d2 into d1."""
        for k, v in d2.items():
            if k in d1 and isinstance(d1[k], dict) and isinstance(v, dict):
                d1[k] = deep_merge(d1[k], v)
            else:
                d1[k] = v
        return d1

    # Start with a deep copy of the base to avoid modifying it
    merged_config = copy.deepcopy(base_config)

    # Perform the deep merge
    return deep_merge(merged_config, remote_config)


def discover_adk_agents(repo_path: pathlib.Path) -> dict[int, dict[str, Any]]:
    """Discover and load all ADK agents from a repository with inference support.

    Args:
        repo_path: Path to the cloned ADK samples repository

    Returns:
        Dictionary mapping agent numbers to agent info with keys:
        - name: Agent display name
        - description: Agent description
        - path: Relative path from repo root
        - spec: adk@ specification string
        - has_explicit_config: Whether agent has explicit configuration
    """
    import logging

    adk_agents = {}

    # Search specifically for agents in python/agents/* directories
    agents_dir = repo_path / "python" / "agents"
    logging.debug("Looking for agents in: %s", agents_dir)
    if agents_dir.exists():
        all_items = list(agents_dir.iterdir())
        logging.debug(
            "Found items in agents directory: %s", [item.name for item in all_items]
        )

        # Collect all agents first, then sort by configuration type
        all_agents = []

        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir():
                logging.debug("Skipping non-directory: %s", agent_dir.name)
                continue
            logging.debug("Processing agent directory: %s", agent_dir.name)

            try:
                # Load configuration with ADK inference support
                config = load_remote_template_config(
                    template_dir=agent_dir, is_adk_sample=True
                )

                agent_name = config.get("name", agent_dir.name)
                description = config.get("description", "")
                has_explicit_config = config.get("has_explicit_config", False)

                # Get the relative path from repo root
                relative_path = agent_dir.relative_to(repo_path)
                agent_spec_name = agent_dir.name

                agent_info = {
                    "name": agent_name,
                    "description": description,
                    "path": str(relative_path),
                    "spec": f"adk@{agent_spec_name}",
                    "has_explicit_config": has_explicit_config,
                }
                all_agents.append(agent_info)

            except Exception as e:
                logging.warning(f"Could not load agent from {agent_dir}: {e}")

        # Sort agents: explicit config first, then inferred (both alphabetically within their groups)
        all_agents.sort(key=lambda x: (not x["has_explicit_config"], x["name"].lower()))

        # Convert to numbered dictionary
        for i, agent_info in enumerate(all_agents, 1):
            adk_agents[i] = agent_info

    return adk_agents


def display_adk_caveat_if_needed(agents: dict[int, dict[str, Any]]) -> None:
    """Display helpful note for agents that use inference.

    Args:
        agents: Dictionary of agent info from discover_adk_agents
    """
    console = Console()
    inferred_agents = [
        a for a in agents.values() if not a.get("has_explicit_config", True)
    ]
    if inferred_agents:
        console.print(
            "\n[blue]ℹ️  Note: Agents marked with * are templated using Agents CLI heuristics for ADK samples.[/]"
        )
        console.print(
            "[dim]   Agents CLI attempts to create a working codebase, but you'll need to follow the generated README for complete setup.[/]"
        )


def parse_acli_version_from_lock(
    uv_lock_path: pathlib.Path,
) -> str | None:
    """Parse agents-cli version from uv.lock file.

    Args:
        uv_lock_path: Path to uv.lock file

    Returns:
        Version string if found, None otherwise
    """
    if not uv_lock_path.exists():
        return None

    try:
        with open(uv_lock_path, "rb") as f:
            lock_data = tomllib.load(f)

        # Look for agents-cli in the packages section
        packages = lock_data.get("package", [])
        for package in packages:
            if package.get("name") == "google-agents-cli":
                version = package.get("version")
                if version:
                    logging.debug("Found agents-cli version %s in uv.lock", version)
                    return version

    except Exception as e:
        logging.warning(f"Error parsing uv.lock file {uv_lock_path}: {e}")

    return None
