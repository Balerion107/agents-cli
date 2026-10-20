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

"""Surface the real cause of an Agent Runtime "Build failed" error.

When the remote container build fails, the deploy operation only reports a
generic ``code: 3, "Build failed. The issue might be caused by incorrect code,
requirements.txt file or other dependencies..."``. The build runs in a
Google-managed project, so ``gcloud builds list`` shows nothing; the actual
error (e.g. ``Failed to download attrs==26.1.0 ... Connection refused``) is only
in the ``reasoning_engine_build`` log forwarded to the user's Cloud Logging.
This module fetches the tail of that log so the deploy error can show it.
"""

from __future__ import annotations

import datetime
import logging
import urllib.parse
from collections.abc import Sequence
from typing import Any

import requests

_BUILD_LOG_ID = "aiplatform.googleapis.com%2Freasoning_engine_build"
_ENTRIES_LIST_URL = "https://logging.googleapis.com/v2/entries:list"
_REQUEST_TIMEOUT = 15
_DEFAULT_TAIL_LINES = 40
# Entries to fetch; more than the lines shown because entries with no text are
# skipped, so fetching only _DEFAULT_TAIL_LINES entries can leave the tail short.
_FETCH_ENTRIES = 100
# Leeway for clock skew between this machine and Cloud Logging timestamps.
_CLOCK_SKEW = datetime.timedelta(minutes=5)


def is_build_failure(error: Any) -> bool:
    """Whether an operation error is the remote container build failing.

    Agent Runtime reports it as ``code: 3`` with a message starting "Build failed".
    """
    if not isinstance(error, dict):
        return False
    message = error.get("message")
    return (
        error.get("code") == 3
        and isinstance(message, str)
        and message.lower().startswith("build failed")
    )


def build_log_details(
    *,
    project: str,
    engine_id: str,
    started_at: datetime.datetime | None,
) -> str:
    """The build log's tail when available, followed by a link to the full log."""
    logs_url = engine_logs_url(
        project=project, engine_id=engine_id, extra_clauses=[_log_name_filter(project)]
    )
    lines = fetch_build_log_tail(
        project=project, engine_id=engine_id, started_at=started_at
    )
    if not lines:
        return f"  The build's own error is in the reasoning_engine_build log:\n    {logs_url}"
    tail = "\n".join(f"    {line}" for line in lines)
    return (
        f"  Last lines of the build log (reasoning_engine_build):\n{tail}\n\n"
        f"  Full build log: {logs_url}"
    )


def engine_logs_url(
    *, project: str, engine_id: str, extra_clauses: Sequence[str] = ()
) -> str:
    """Logs Explorer URL for an engine's logs, narrowed by any extra filter clauses."""
    query = "\n".join(
        [f'resource.labels.reasoning_engine_id="{engine_id}"', *extra_clauses]
    )
    encoded = urllib.parse.quote(query, safe="")
    return (
        f"https://console.cloud.google.com/logs/query;query={encoded}?project={project}"
    )


def fetch_build_log_tail(
    *,
    project: str,
    engine_id: str,
    started_at: datetime.datetime | None,
    limit: int = _DEFAULT_TAIL_LINES,
) -> list[str]:
    """Last ``limit`` lines of the engine's build log, oldest first.

    ``started_at`` must be timezone-aware (see ``_operation.parse_started_at``).
    Best effort: returns an empty list on any failure (no credentials, no
    ``logging.viewer`` permission, network error), so it never hides the
    original deploy error.
    """
    try:
        from google.agents.cli.auth import get_access_token

        token = get_access_token()
        clauses = [
            _log_name_filter(project),
            f'resource.labels.reasoning_engine_id="{engine_id}"',
        ]
        if started_at is not None:
            since = (started_at - _CLOCK_SKEW).astimezone(datetime.UTC)
            clauses.append(f'timestamp>="{since.isoformat().replace("+00:00", "Z")}"')
        entries = _list_entries(
            project=project, log_filter=" AND ".join(clauses), token=token
        )
        # Split multi-line entries so each line is indented and counted.
        lines = [
            line
            for e in reversed(entries)
            if (text := _entry_text(e))
            for line in text.splitlines()
        ]
        return lines[-limit:]
    except Exception as exc:  # Never mask the deploy error itself.
        logging.debug("Could not fetch the reasoning_engine_build log", exc_info=exc)
    return []


def _log_name_filter(project: str) -> str:
    return f'logName="projects/{project}/logs/{_BUILD_LOG_ID}"'


def _list_entries(*, project: str, log_filter: str, token: str) -> list[dict[str, Any]]:
    resp = requests.post(
        _ENTRIES_LIST_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "resourceNames": [f"projects/{project}"],
            "filter": log_filter,
            "orderBy": "timestamp desc",
            "pageSize": _FETCH_ENTRIES,
        },
        timeout=_REQUEST_TIMEOUT,
    )
    if not resp.ok:
        logging.debug("Cloud Logging entries:list returned HTTP %s", resp.status_code)
        return []
    entries = resp.json().get("entries")
    return entries if isinstance(entries, list) else []


def _entry_text(entry: Any) -> str:
    """The human-readable text of a log entry."""
    if not isinstance(entry, dict):
        return ""
    text = entry.get("textPayload")
    if not isinstance(text, str):
        payload = entry.get("jsonPayload")
        text = payload.get("message") if isinstance(payload, dict) else None
    return text.rstrip() if isinstance(text, str) else ""
