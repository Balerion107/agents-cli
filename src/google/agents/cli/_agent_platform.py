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

"""Shared construction of the Gemini platform SDK client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import agentplatform

# Retry options applied to every Gemini platform client the CLI builds. Leaving
# http_status_codes unset keeps the SDK's default retryable set (408/429/500/502/503/504);
# waits are roughly 1s, 2s, 4s, 8s (full-jittered).
RETRY_OPTIONS: dict[str, Any] = {
    "attempts": 5,
    "initial_delay": 1.0,
}


class AgentPlatformClient:
    """Gemini platform client configured with CLI-wide defaults (e.g. retries on transient errors).

    Retries are opt-in in the underlying SDK, so constructing ``agentplatform.Client``
    directly runs without them. A ruff rule enforces using this wrapper instead.

    Args:
        project: GCP project ID, or None to let the SDK resolve it.
        location: API location (e.g. ``us-east1``), or None.
        api_version: Optional API version override (e.g. ``v1beta1``).
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str | None = None,
        api_version: str | None = None,
    ) -> None:
        # Lazy: agentplatform is expensive to import, this module is not.
        import agentplatform

        http_options: dict[str, Any] = {"retry_options": RETRY_OPTIONS}
        if api_version:
            http_options["api_version"] = api_version

        self._client: agentplatform.Client = agentplatform.Client(  # noqa: TID251
            project=project,
            location=location,
            http_options=http_options,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)
