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

"""Output helpers for agents CLI."""

import json
import logging
import sys
from typing import Any

import click
from rich.console import Console as _RichConsole  # noqa: TID251
from rich.markup import escape

_OWN_LOGGER_NAME = "google.agents.cli"
_PLAIN_FORMATTER = logging.Formatter()


class Console(_RichConsole):
    """Rich Console configured with project-wide defaults (soft_wrap=True)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("soft_wrap", True)
        super().__init__(*args, **kwargs)


def emit(data: dict) -> None:
    """Write structured data to stdout."""
    print(json.dumps(data), file=sys.stdout)


def print_error(message: str) -> None:
    """Print an error message to stderr with a red "❌ Error:" prefix."""
    # escape() so text like "[cyan]" or "[0]" in the message is shown as-is.
    Console(stderr=True, highlight=False).print(
        f"[bold red]❌ Error:[/bold red] {escape(message)}"
    )


def print_warning(message: str) -> None:
    """Print a warning message to stderr with a yellow "⚠️  Warning:" prefix."""
    Console(stderr=True, highlight=False).print(
        f"[bold yellow]⚠️  Warning:[/bold yellow] {escape(message)}"
    )


INTERACTIVE_FIX = ("-i, --interactive", "be prompted for each missing value")


def auto_approve_fix(default: str) -> tuple[str, str]:
    """The -y entry for programmatic_mode_error; ``default`` names what -y picks."""
    return ("-y, --yes", f"accept the defaults ({default})")


def programmatic_mode_error(
    requirement: str, *fixes: tuple[str, str]
) -> click.UsageError:
    """Build the error for a value a command can't fill in without prompting.

    ``requirement`` is the subject, e.g. "--agent is required"; each fix is a
    (flag, description) pair, and an empty flag continues the fix above. Every
    fix gets its own aligned line: a trailing "pass -i for interactive mode"
    sentence was easy to miss.
    """
    if not fixes:
        return click.UsageError(f"{requirement} in programmatic mode.")
    width = max(len(flag) for flag, _ in fixes)
    lines = "\n".join(f"  {flag:<{width}}  {text}" for flag, text in fixes)
    return click.UsageError(
        f"{requirement} in programmatic mode. Rerun with one of:\n{lines}"
    )


def print_debug(message: str) -> None:
    """Print a debug message to stderr as a dim "Debug: <message>" line."""
    Console(stderr=True, highlight=False).print(f"Debug: {escape(message)}", style="dim")


def print_click_exception(e: click.ClickException) -> None:
    """Show a ClickException like Click does, but with a red "❌ Error:" prefix."""
    if isinstance(e, click.UsageError) and e.ctx is not None:
        hint = ""
        if e.ctx.command.get_help_option(e.ctx) is not None:
            hint = f"Try '{e.ctx.command_path} {e.ctx.help_option_names[0]}' for help.\n"
        click.echo(f"{e.ctx.get_usage()}\n{hint}", err=True, color=e.ctx.color)
    print_error(e.format_message())


def configure_logging(level: int = logging.INFO) -> None:
    """Send log records to stderr, formatting agents-cli's own records.

    agents-cli's own records are shown from ``level`` up. Records from libraries
    are shown from WARNING up (or from ``level``, if it is higher), except at
    DEBUG, where they are shown too. agents-cli's own errors, warnings and debug
    records get the print_error() / print_warning() / print_debug() format;
    everything else is printed plain.
    """
    root = logging.getLogger()
    for handler in [h for h in root.handlers if isinstance(h, _CliLogHandler)]:
        root.removeHandler(handler)

    debug = level <= logging.DEBUG
    library_level = level if debug else max(level, logging.WARNING)
    handler = _CliLogHandler()
    handler.setFormatter(
        logging.Formatter(logging.BASIC_FORMAT if debug else "%(message)s")
    )
    handler.addFilter(lambda r: _is_own_record(r) or r.levelno >= library_level)
    root.addHandler(handler)
    root.setLevel(level)
    # On its first request, google-auth turns off propagation on the "google"
    # logger unless that logger is already configured
    # (google.auth._helpers.is_logging_enabled). That would cut every google.*
    # logger, ours included, off from the handler above. A level counts as
    # configured. At DEBUG, google-auth then logs its requests; their headers
    # (with tokens) go in the record's extra fields, which this format doesn't
    # print.
    logging.getLogger("google").setLevel(level)


class _CliLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            printer = _OWN_RECORD_PRINTERS.get(record.levelno)
            if printer and _is_own_record(record):
                printer(_PLAIN_FORMATTER.format(record))
            else:
                # click.echo looks up sys.stderr on every call, so output still
                # reaches a stream swapped in later (e.g. by CliRunner).
                click.echo(self.format(record), err=True)
        except Exception:
            self.handleError(record)


def _is_own_record(record: logging.LogRecord) -> bool:
    # agents-cli code mostly calls logging.warning() etc. directly, which logs
    # on the root logger.
    return (
        record.name == "root"
        or record.name == _OWN_LOGGER_NAME
        or record.name.startswith(_OWN_LOGGER_NAME + ".")
    )


def _print_plain(message: str) -> None:
    # Our INFO lines stay plain, without the debug-mode "INFO:root:" prefix.
    click.echo(message, err=True)


_OWN_RECORD_PRINTERS = {
    logging.CRITICAL: print_error,
    logging.ERROR: print_error,
    logging.WARNING: print_warning,
    logging.INFO: _print_plain,
    logging.DEBUG: print_debug,
}
