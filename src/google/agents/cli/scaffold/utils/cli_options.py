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

"""Shared Click options for template-based commands."""

from collections.abc import Callable

import click

from . import template


def shared_template_options(f: Callable) -> Callable:
    """Decorator to add shared options for template-based commands."""
    # Apply options in reverse order since decorators are applied bottom-up
    f = click.option(
        "-ag",
        "--agent-garden",
        is_flag=True,
        help="Deployed from Agent Garden - customizes welcome messages",
        default=False,
    )(f)
    f = click.option(
        "--skip-deps",
        is_flag=True,
        help="Skip base template dependency installation (used when reusing saved config)",
        default=False,
        hidden=True,
    )(f)
    f = click.option(
        "-s",
        "--skip-checks",
        is_flag=True,
        help="Skip verification checks for GCP and Vertex AI",
        default=False,
    )(f)
    f = click.option(
        "--region",
        help="GCP region for deployment (default: us-east1)",
        default="us-east1",
    )(f)
    f = click.option(
        "--auto-approve",
        "--yes",
        "-y",
        is_flag=True,
        default=False,
        help="Non-interactive: skip prompts and use defaults",
    )(f)
    f = click.option(
        "--interactive",
        "-i",
        is_flag=True,
        default=False,
        help="Enable interactive prompts for human use",
    )(f)
    f = click.option("--debug", is_flag=True, help="Enable debug logging")(f)
    f = click.option(
        "--session-type",
        type=click.Choice(list(template.SESSION_TYPES.keys())),
        help="Type of session storage to use",
    )(f)
    f = click.option(
        "--prototype",
        "-p",
        is_flag=True,
        help="Create minimal project without CI/CD or Terraform infrastructure",
        default=False,
    )(f)
    f = click.option(
        "--cicd-runner",
        type=click.Choice(["google_cloud_build", "github_actions", "skip"]),
        help="CI/CD runner to use",
    )(f)
    f = click.option(
        "--deployment-target",
        "-d",
        type=click.Choice(list(template.DEPLOYMENT_TARGETS.keys())),
        help="Deployment target name",
    )(f)
    f = click.option(
        "--agent-directory",
        "-dir",
        help="Name of the agent directory (overrides template default)",
    )(f)
    f = click.option(
        "--bq-analytics",
        is_flag=True,
        help="Include BigQuery Agent Analytics Plugin for observability",
        default=False,
    )(f)
    # None means "not specified" -- use the current value.
    f = click.option(
        "--agent-gateway/--no-agent-gateway",
        default=None,
        help=(
            "Make the Dockerfile Agent Gateway-ready by trusting the gateway's "
            "root CA (Agent Runtime only). Required before `agents-cli deploy "
            "--agent-gateway-egress`"
        ),
    )(f)
    f = click.option(
        "--base-template",
        "-bt",
        help="Base template to use (overrides template default, only for remote templates)",
    )(f)
    f = click.option(
        "--agent-guidance-filename",
        default="GEMINI.md",
        help="Filename for agent guidance (e.g., GEMINI.md, CLAUDE.md, AGENTS.md)",
    )(f)
    return f
