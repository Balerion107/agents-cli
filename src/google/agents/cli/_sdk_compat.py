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

"""Gemini platform SDK features that the public SDK doesn't expose.

Every private SDK module or member the CLI uses goes through here, so an SDK
bump that breaks one of them breaks only this module (and its contract tests in
``tests/unittests/cli/test_sdk_compat.py``). Other modules get the SDK types
through ``google.agents.cli._agent_platform_types``, which re-exports ``types``.
Private submodule imports are lazy, so commands that need only part of this
module don't load the rest of the SDK.
"""

from __future__ import annotations

import functools
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # The public `agentplatform.types` is served by an untyped module
    # `__getattr__`, which type checkers resolve to Unknown. Point them at the
    # module it returns so the SDK models stay type-checked.
    from agentplatform._genai import types
    from agentplatform._genai.runtimes import Runtimes

    from google.agents.cli._agent_platform import AgentPlatformClient
else:

    def __getattr__(name: str) -> Any:
        # Lazy: `agentplatform.types` takes ~2s to import, which callers that
        # need only the Agent Runtime or eval helpers shouldn't pay.
        if name == "types":
            from agentplatform import types

            return types
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# --- Agent Runtime ------------------------------------------------------------
#
# The SDK's public ``create()`` / ``update()`` block until the deploy finishes and
# never return the operation, which ``--no-wait`` and ``deploy --status`` need.
# They also can't take a custom update mask.

POLL_INTERVAL_SECONDS = 10.0


def build_config(
    client: AgentPlatformClient, *, mode: str, **kwargs: Any
) -> types.UpdateRuntimeConfigDict:
    """Build the create/update request config, including its update mask."""
    return _runtimes(client)._create_config(mode=mode, **kwargs)


def start_create(
    client: AgentPlatformClient, *, config: types.CreateRuntimeConfigDict
) -> str:
    """Start creating an Agent Runtime agent and return the operation name without waiting."""
    return _operation_name(_runtimes(client)._create(config=config))


def start_update(
    client: AgentPlatformClient, *, name: str, config: types.UpdateRuntimeConfigDict
) -> str:
    """Start updating an Agent Runtime agent and return the operation name without waiting."""
    return _operation_name(_runtimes(client)._update(name=name, config=config))


def get_operation(
    client: AgentPlatformClient, *, operation_name: str
) -> types.RuntimeOperation:
    """Fetch the current state of an Agent Runtime operation."""
    return _runtimes(client)._get_agent_operation(operation_name=operation_name)


def wait_for_operation(
    client: AgentPlatformClient,
    *,
    operation_name: str,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> types.RuntimeOperation:
    """Poll an Agent Runtime operation until it is done and return it."""
    operation = get_operation(client, operation_name=operation_name)
    while not operation.done:
        time.sleep(poll_interval_seconds)
        operation = get_operation(client, operation_name=operation_name)
    return operation


def _operation_name(operation: types.RuntimeOperation) -> str:
    name = getattr(operation, "name", None)
    if not name:
        raise RuntimeError("Gemini platform returned an operation without a name.")
    return name


def _runtimes(client: AgentPlatformClient) -> Runtimes:
    # AgentPlatformClient forwards attributes untyped; naming the SDK class lets
    # the type checker verify the private calls above against the SDK.
    return client.runtimes


# --- Eval ---------------------------------------------------------------------
#
# The SDK renders its evaluation and loss-analysis HTML reports, and lists its
# predefined metrics, only from private modules (b/512125999).


@functools.cache
def supported_predefined_metrics() -> frozenset[str]:
    """Versioned predefined metric names, e.g. ``general_quality_v1``.

    The public ``types.PrebuiltMetric`` loader drops the versions and adds legacy
    metrics, so it isn't a drop-in.
    """
    from agentplatform._genai._evals_constant import SUPPORTED_PREDEFINED_METRICS

    return frozenset(SUPPORTED_PREDEFINED_METRICS)


def evaluation_html(eval_result_json: str) -> str:
    """Render the SDK's HTML report for a serialized ``EvaluationResult``."""
    return _visualization().get_evaluation_html(eval_result_json)


def loss_analysis_html(loss_analysis_json: str) -> str:
    """Render the SDK's HTML report for a serialized loss-analysis response."""
    return _visualization().get_loss_analysis_html(loss_analysis_json)


def dataset_rows(dataset: types.EvaluationDataset) -> list[dict[str, Any]]:
    """Flatten a dataset into the per-case rows the HTML report displays."""
    return _visualization()._extract_dataset_rows(dataset)


def _visualization() -> Any:
    # Lazy: importing it loads the SDK's eval stack (litellm among others),
    # about 3s that `eval metric list` shouldn't pay.
    from agentplatform._genai import _evals_visualization

    return _evals_visualization
