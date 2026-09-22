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

"""Read/write helpers for pending deploy operations in METADATA_FILE.

When a deployment starts (sync or ``--no-wait``), the long-running operation
name and metadata are persisted as a ``pending_operation`` field inside
``METADATA_FILE`` so that ``deploy --status`` can poll it later.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any

METADATA_FILE = "deployment_metadata.json"


def _read_metadata() -> dict[str, Any]:
    """Read METADATA_FILE, tolerating a missing or corrupt file.

    A malformed or zero-byte file (left by an interrupted run, a partial
    write, or a manual edit) is treated as empty so a single bad file can't
    permanently block every subsequent deploy. Returns ``{}`` when the file
    is missing or unreadable.
    """
    if not os.path.exists(METADATA_FILE):
        return {}
    try:
        with open(METADATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logging.warning("Ignoring corrupt %s (%s); treating as empty.", METADATA_FILE, e)
        return {}
    if not isinstance(data, dict):
        logging.warning(
            "Ignoring %s with unexpected top-level %s; treating as empty.",
            METADATA_FILE,
            type(data).__name__,
        )
        return {}
    return data


def write_operation(
    operation_name: str,
    project: str,
    location: str,
    deployment_target: str,
) -> None:
    """Persist a pending deploy operation to METADATA_FILE."""
    pending = {
        "operation_name": operation_name,
        "project": project,
        "location": location,
        "deployment_target": deployment_target,
        "started_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
    }

    # Merge into existing metadata if present
    data = _read_metadata()
    data["pending_operation"] = pending
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_operation() -> dict[str, Any] | None:
    """Read a pending operation from METADATA_FILE, or None."""
    return _read_metadata().get("pending_operation")


def clear_operation() -> None:
    """Remove the pending_operation field from METADATA_FILE."""
    data = _read_metadata()
    if "pending_operation" in data:
        del data["pending_operation"]
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def read_remote_agent_runtime_id() -> str | None:
    """Read the remote_agent_runtime_id from METADATA_FILE."""
    value = _read_metadata().get("remote_agent_runtime_id")
    # Older scaffolds shipped the literal string ``"None"`` as a placeholder, so
    # treat that (and blank values) as "no id recorded" — otherwise a first deploy
    # would try to update an engine literally named ``None`` and fail with a 404
    # instead of creating a new one.
    if isinstance(value, str) and value.strip().lower() in ("", "none", "null"):
        return None
    return value
