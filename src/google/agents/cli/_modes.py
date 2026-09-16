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

"""Protocol values shared by every command that talks to an agent."""

# A2A protocol.
MODE_A2A = "a2a"
# ADK over HTTP: POST /run_sse, or :streamQuery on Agent Runtime.
MODE_ADK = "adk"
# ADK over a bidi WebSocket: /run_live, the transport Live (voice) agents use.
MODE_ADK_LIVE = "adk_live"

# What each command accepts. Build every click.Choice and every "choose from"
# message from these, so adding a mode is one edit per set rather than one per
# call site.
RUN_MODES = (MODE_A2A, MODE_ADK, MODE_ADK_LIVE)
# A local server serves ADK only, so a2a needs a --url.
LOCAL_RUN_MODES = (MODE_ADK, MODE_ADK_LIVE)
# eval speaks ADK only.
EVAL_MODES = (MODE_ADK, MODE_ADK_LIVE)
