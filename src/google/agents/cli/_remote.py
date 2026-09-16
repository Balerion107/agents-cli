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

"""URL classification + auth headers for talking to remote agents.

Transport-neutral so all callers (ADK, A2A, Agent Runtime) agree on
how a ``--url`` is classified and what auth token it gets.
"""

from __future__ import annotations

import re
from typing import NamedTuple
from urllib.parse import urlparse, urlsplit, urlunsplit

import click

from google.agents.cli.auth import get_access_token, get_id_token

_AGENT_ENGINE_URL_FRAGMENT = "aiplatform.googleapis.com"
_REASONING_ENGINE_PATH = "reasoningEngines"
# A valid Agent Runtime host carries a location prefix: <location>-aiplatform.googleapis.com
_AGENT_RUNTIME_HOST_RE = re.compile(rf".+-{re.escape(_AGENT_ENGINE_URL_FRAGMENT)}$")

# WebSocket traffic has its own ingress; HTTP goes through reasoningEngines/v1.
# https://github.com/GoogleCloudPlatform/generative-ai/blob/main/agents/agent_engine/tutorial_bidi_stream_v2.ipynb
_AGENT_RUNTIME_WS_INGRESS = "reasoningEngines/ws/internal"


def is_agent_runtime_url(url: str) -> bool:
    """Return ``True`` if *url* points to an Agent Runtime endpoint."""
    return _AGENT_ENGINE_URL_FRAGMENT in url and _REASONING_ENGINE_PATH in url


def is_legacy_agent_runtime_url(url: str) -> bool:
    """``True`` for a bare, non-passthrough Agent Runtime resource URL.

    This URL can only be used for legacy ``:streamQuery`` endpoints, not the
    ``/api/`` passthrough API.

    A URL already containing ``/api`` (the deployed APP_URL form served by the
    container) or any non-Agent-Runtime URL returns ``False``.
    """
    return is_agent_runtime_url(url) and "/api" not in url


def validate_agent_runtime_url(url: str) -> None:
    """Raise a helpful hint when *url* references an Agent Runtime resource but
    its host is missing the required ``<location>-`` location prefix.

    Agent Runtime endpoints are hosted at ``<location>-aiplatform.googleapis.com``.
    A bare resource path (no host) or a host without the location prefix can't be
    queried, so we point at the correct format instead of failing obscurely.
    """
    if _REASONING_ENGINE_PATH not in url:
        return
    if _AGENT_RUNTIME_HOST_RE.match(urlparse(url).hostname or ""):
        return  # Host already carries a <location>- prefix.
    raise click.UsageError(
        "Detected an Agent Runtime URL with a missing location.\n"
        "  The location must appear in the host. The correct format is:\n"
        "    https://<LOCATION>-aiplatform.googleapis.com/v1/projects/<PROJECT>"
        "/locations/<LOCATION>/reasoningEngines/<ID>"
    )


def build_agent_runtime_passthrough_url(location: str, runtime_resource: str) -> str:
    """Base all clients can target. ``runtime_resource`` is the full
    ``projects/<num>/locations/<loc>/reasoningEngines/<id>`` resource name."""
    return (
        f"https://{location}-aiplatform.googleapis.com/reasoningEngines/v1/"
        f"{runtime_resource}/api"
    )


class AgentEndpoints(NamedTuple):
    """HTTP and WebSocket base URLs for one remote agent."""

    http_base: str
    ws_base: str


def http_to_ws_url(base_url: str) -> str:
    """Normalize a URL's scheme to ws/wss"""
    parts = urlsplit(base_url)
    scheme = {"http": "ws", "https": "wss"}.get(parts.scheme, parts.scheme)
    return urlunsplit(parts._replace(scheme=scheme))


def build_agent_runtime_endpoints(location: str, runtime_resource: str) -> AgentEndpoints:
    """Build Agent Runtime ingress base URLs for a deployed engine."""
    host = f"{location}-{_AGENT_ENGINE_URL_FRAGMENT}"
    resource = runtime_resource.strip("/")
    return AgentEndpoints(
        http_base=build_agent_runtime_passthrough_url(location, resource),
        ws_base=f"wss://{host}/{_AGENT_RUNTIME_WS_INGRESS}/{resource}/api",
    )


def resolve_agent_endpoints(url: str) -> AgentEndpoints:
    """Resolve the HTTP and WebSocket base URLs for a remote agent."""
    http_url = url.rstrip("/")
    if not is_agent_runtime_url(http_url):
        return AgentEndpoints(http_base=http_url, ws_base=http_to_ws_url(http_url))

    validate_agent_runtime_url(http_url)
    location, resource = parse_agent_runtime_service_url(http_url)
    return build_agent_runtime_endpoints(location, resource.removesuffix("/api"))


def parse_agent_runtime_service_url(service_url: str) -> tuple[str, str]:
    """Split an Agent Runtime service URL into (location, runtime_resource).

    Handles both the ``/v1/`` and ``/v1beta1/`` API path variants.
    ``https://europe-west1-aiplatform.googleapis.com/v1/projects/123/locations/
    europe-west1/reasoningEngines/456`` →
    ``("europe-west1", "projects/123/locations/europe-west1/reasoningEngines/456")``.
    """
    host = urlparse(service_url).hostname or ""
    location = host.split(f"-{_AGENT_ENGINE_URL_FRAGMENT}", 1)[0]
    # Resource path follows the API version segment (v1, v1beta1, ...).
    match = re.search(r"/v1[^/]*/(.+)", service_url)
    runtime_resource = match.group(1) if match else service_url
    return location, runtime_resource


def _parse_header(value: str) -> tuple[str, str]:
    """Parse a ``Key: Value`` header string."""
    if ":" not in value:
        raise click.BadParameter(
            f"Invalid header format (expected 'Key: Value'): {value}"
        )
    key, _, val = value.partition(":")
    return key.strip(), val.strip()


def build_remote_headers(
    custom_headers: tuple[str, ...], url: str = ""
) -> dict[str, str]:
    """Build headers for remote requests.

    Auto-detects Google Cloud credentials unless the caller supplies
    an ``Authorization`` header via ``--header``.

    Uses an **access token** for Vertex AI / Agent Runtime URLs and an
    **identity token** (with the service URL as audience) for everything
    else (Cloud Run, GKE, etc.).
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    parsed = dict(_parse_header(h) for h in custom_headers)

    if "Authorization" not in parsed:
        try:
            if is_agent_runtime_url(url):
                token = get_access_token()
            else:
                parsed_url = urlparse(url)
                audience = f"{parsed_url.scheme}://{parsed_url.netloc}"
                token = get_id_token(audience)
            headers["Authorization"] = f"Bearer {token}"
        except Exception as exc:
            click.echo(
                f"Warning: Could not obtain credentials: {exc}",
                err=True,
            )

    headers.update(parsed)
    return headers
