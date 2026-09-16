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

"""Upgrade command for upgrading existing projects to newer Agents CLI versions."""

import logging
import pathlib

import click

from google.agents.cli import _tools
from google.agents.cli._output import Console
from google.agents.cli._project import find_project_config, find_project_root

from ..utils.backup import make_backup_pre_apply_hook
from ..utils.generation_metadata import metadata_to_cli_args
from ..utils.merge import run_three_way_merge
from ..utils.upgrade import (
    migrate_legacy_evalsets,
    migrate_legacy_python_config,
    update_acli_metadata,
    warn_legacy_eval_config,
)
from ..utils.version import get_current_version

console = Console()


def _display_version_header(old_version: str, new_version: str) -> None:
    """Display the upgrade version header."""
    console.print()
    console.print(f"[bold blue]📦 Upgrading {old_version} → {new_version}[/bold blue]")
    console.print()


@click.command()
@click.argument(
    "project_path",
    type=click.Path(exists=True, path_type=pathlib.Path),
    default=".",
    required=False,
)
@click.option(
    "--dry-run",
    "--dryrun",
    is_flag=True,
    help="Preview changes without applying them",
)
@click.option(
    "--auto-approve",
    "--yes",
    "-y",
    is_flag=True,
    help="Auto-apply non-conflicting changes without prompts",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    default=False,
    help="Enable interactive prompts for human use",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug logging",
)
def upgrade(
    project_path: pathlib.Path,
    dry_run: bool,
    auto_approve: bool,
    interactive: bool,
    debug: bool,
) -> None:
    """Upgrade project to a newer agents-cli version.

    Applies a 3-way merge between the old template, the new template, and your
    project: unmodified files are auto-updated, your customizations are preserved,
    and conflicts are surfaced for manual resolution (with --interactive) or kept as-is.
    """
    if debug:
        logging.basicConfig(level=logging.DEBUG, force=True)
        console.print("[dim]Debug mode enabled[/dim]")

    # Resolve project path
    project_dir = project_path.resolve()
    # Handle the case where we're in a subdirectory under the project root.
    project_root_dir = find_project_root(project_dir)
    if project_root_dir is not None:
        project_dir = project_root_dir
        console.print(f"[dim]Resolved project root to: {project_dir}[/dim]")

    migrate_legacy_python_config(project_dir, dry_run=dry_run)

    metadata = find_project_config(project_dir)
    if not metadata:
        console.print("[bold red]Error:[/bold red] No agents-cli metadata found.")
        console.print("Ensure agents-cli-manifest.yaml exists in your project root.")
        raise SystemExit(1)

    # Get language from metadata for language-aware operations
    language = metadata.language

    # Version is normalized to acli_version by find_project_config
    old_version = metadata.acli_version
    if not old_version:
        console.print(
            "[bold red]Error:[/bold red] No acli_version found in project metadata."
        )
        console.print(
            "The project metadata is missing the version. "
            "Please ensure agents-cli-manifest.yaml has acli_version set."
        )
        raise SystemExit(1)

    new_version = get_current_version()

    # Check if upgrade is needed
    if old_version == new_version:
        console.print(
            f"[bold green]✅[/bold green] Project is already at version {new_version}"
        )
        return

    # We check this up front here because the underlying code would catch this
    # and fall back to the current templates, which would make the baseline
    # identical to the new template — the merge would find nothing to do and
    # still stamp the new version into the manifest.
    _tools.require_tool("uvx")

    _display_version_header(old_version, new_version)

    # Get project name and CLI args from metadata
    project_name = metadata.project_name or project_dir.name
    agent_directory = metadata.agent_directory or "app"
    cli_args = metadata_to_cli_args(metadata)

    # -- Pre-apply hook: back up the project before writing changes ----------
    backup_hook = make_backup_pre_apply_hook(
        console=console,
        auto_approve=auto_approve,
        interactive=interactive,
    )

    # Post-apply: stamp the new version into the manifest
    def _update_version(proj_dir: pathlib.Path, lang: str) -> None:
        update_acli_metadata(proj_dir, {}, acli_version=new_version)

    # Migrate before the merge so a customized evalset isn't clobbered by the
    # stock template default the merge would otherwise copy in first.
    migrate_legacy_evalsets(project_dir, dry_run=dry_run)
    warn_legacy_eval_config(project_dir)

    success = run_three_way_merge(
        project_dir=project_dir,
        project_name=project_name,
        agent_directory=agent_directory,
        language=language,
        old_args=cli_args,
        new_args=cli_args,
        old_version=old_version,
        auto_approve=auto_approve,
        dry_run=dry_run,
        interactive=interactive,
        operation_label="upgrade",
        pre_apply_hook=backup_hook,
        post_apply_hook=_update_version,
    )

    if not success:
        console.print(
            f"[bold red]Error:[/bold red] Could not fetch google-agents-cli@{old_version} "
            "(the version that scaffolded this project) to compute the upgrade diff."
        )
        console.print(
            "[dim]Check your network/proxy and retry. Your project was not modified.[/dim]"
        )
        raise SystemExit(1)
