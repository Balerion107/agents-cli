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

import importlib.metadata
import random

from google.agents.cli._output import Console

console = Console()

MOTTOS = [
    "Your agents are cleared for takeoff.",
    "Launching agents into production, one deploy at a time.",
    "Houston, we have an agent.",
    "To production... and beyond!",
    "One small step for code, one giant leap for agents.",
    "Fueling your AI agents with Google Cloud.",
    "3... 2... 1... Agent deployed!",
    "The sky is not the limit when you have agents.",
]


def _get_version() -> str:
    """Get the package version, with fallback to 'dev'."""
    try:
        return importlib.metadata.version("google-agents-cli")
    except Exception:
        return "dev"


def display_welcome_banner(
    *,
    agent: str | None = None,
    enhance_mode: bool = False,
    agent_garden: bool = False,
    setup_cicd_mode: bool = False,
    register_mode: bool = False,
    quiet: bool = False,
) -> None:
    """Display the Agents CLI welcome banner.

    Args:
        agent: Optional agent specification to customize the welcome message
        enhance_mode: Whether this is for enhancement mode
        agent_garden: Whether this deployment is from Agent Garden
        setup_cicd_mode: Whether this is for CI/CD setup
        register_mode: Whether this is for Gemini registration
        quiet: If True, skip the banner (e.g. in auto-approve/programmatic mode)
    """
    version = _get_version()
    motto = random.choice(MOTTOS)

    if quiet:
        console.print(f"[bold blue]Agents CLI[/] [dim]v{version}[/]")
        return

    if enhance_mode:
        line1 = "Enhancing your project with production-ready capabilities!"
    elif setup_cicd_mode:
        line1 = "Setting up CI/CD infrastructure for your agent!"
    elif register_mode:
        line1 = "Registering your agent with Gemini!"
    else:
        line1 = "Create production-ready AI agents on Google Cloud!"

    console.print()
    console.print(f"[bold blue]Agents CLI[/] [dim]v{version}[/]")
    console.print(f'[italic dim]"{motto}"[/]')
    console.print(f"[dim]{line1}[/]")
    console.print()
