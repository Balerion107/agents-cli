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

"""Utility functions for the optimize CLI command."""

import json
import logging
import os
import uuid
from typing import Any, cast

import click


def _to_adk_evalset_dict(dataset_data: dict, app_name: str, eval_set_id: str) -> dict:
    """Convert EvaluationDataset JSON to ADK EvalSet dictionary."""
    if not isinstance(dataset_data, dict):
        raise click.ClickException("EvaluationDataset must be a dictionary.")

    if "eval_cases" not in dataset_data:
        raise click.ClickException("EvaluationDataset must contain 'eval_cases'.")

    ignored_sources = [
        key
        for key in ["gcs_source", "bigquery_source", "eval_dataset_df"]
        if key in dataset_data
    ]
    if ignored_sources:
        logging.warning(
            "Sources %s are not supported for local optimization runs and will be ignored.",
            ", ".join(ignored_sources),
        )

    # Detect if already in ADK EvalSet format
    if "eval_set_id" in dataset_data:
        return {**dataset_data, "eval_set_id": eval_set_id}

    eval_cases_data = dataset_data["eval_cases"]

    adk_eval_cases = []
    for i, case in enumerate(eval_cases_data):
        # Map EvaluationDataset fields to ADK EvalCase
        history = case.get("conversation_history", [])
        current_prompt = case.get("prompt")

        adk_conversation = []
        for turn in history:
            author = turn.get("author")
            content = turn.get("content")
            if isinstance(content, str):
                content = {"parts": [{"text": content}]}

            # Handle both message style (role/content) and ADK style (user_content/final_response)
            role = turn.get("role")
            if role == "user" or author == "user":
                if adk_conversation and "final_response" not in adk_conversation[-1]:
                    last_user_content = adk_conversation[-1].get("user_content") or {}
                    adk_conversation[-1]["user_content"] = {
                        "parts": last_user_content.get("parts", [])
                        + content.get("parts", [])
                    }
                else:
                    adk_conversation.append({"user_content": content})
            elif (
                role == "model" or role == "agent" or author == "agent"
            ) and adk_conversation:
                if "final_response" in adk_conversation[-1]:
                    last_final_response = adk_conversation[-1]["final_response"] or {}
                    adk_conversation[-1]["final_response"] = {
                        "parts": last_final_response.get("parts", [])
                        + content.get("parts", [])
                    }
                else:
                    adk_conversation[-1]["final_response"] = content

        if current_prompt:
            # Both ADK and the Gemini platform SDK use google.genai.types.Content format here
            # although the Gemini platform SDK also accepts strings, which we handle below.
            prompt_content = current_prompt
            if isinstance(current_prompt, str):
                prompt_content = {"parts": [{"text": current_prompt}]}

            invocation = {"user_content": prompt_content}

            # Map intermediate_events to intermediate_data (InvocationEvents)
            if case.get("intermediate_events"):
                invocation["intermediate_data"] = {
                    "invocation_events": [
                        {
                            "author": event.get("author", "agent"),
                            "content": event.get("content"),
                        }
                        for event in case["intermediate_events"]
                    ]
                }

            adk_conversation.append(invocation)

        if case.get("reference") and adk_conversation:
            # For optimization, the reference response is the target "final_response"
            reference_data = case["reference"]
            if isinstance(reference_data, dict):
                ref_response = reference_data.get("response")
            else:
                ref_response = reference_data

            if isinstance(ref_response, str):
                ref_response = {"parts": [{"text": ref_response}]}
            adk_conversation[-1]["final_response"] = ref_response

        adk_eval_case = {
            "eval_id": case.get("eval_case_id") or case.get("eval_id") or f"case_{i}",
            "session_input": {"app_name": app_name, "user_id": "eval_user", "state": {}},
        }

        # Map rubrics from case.get("rubrics") or rubric_groups
        adk_rubrics = []

        # 1. Parse from direct rubrics list
        rubrics_list = case.get("rubrics", [])
        if isinstance(rubrics_list, list):
            for j, rubric in enumerate(rubrics_list):
                if isinstance(rubric, str):
                    adk_rubrics.append(
                        {
                            "rubric_id": f"rubric_{j}",
                            "rubric_content": {"text_property": rubric},
                        }
                    )
                elif isinstance(rubric, dict):
                    rubric_dict = cast(dict[str, Any], rubric)
                    adk_rubrics.append(
                        {
                            "rubric_id": rubric_dict.get("rubric_id") or f"rubric_{j}",
                            "rubric_content": rubric_dict.get("rubric_content")
                            or {"text_property": rubric_dict.get("description", "")},
                            "description": rubric_dict.get("description"),
                            "type": rubric_dict.get("type"),
                        }
                    )

        # 2. Parse from rubric_groups
        rubric_groups = case.get("rubric_groups", {})
        if isinstance(rubric_groups, dict):
            for group_name, group in rubric_groups.items():
                rubrics_in_group = (
                    group.get("rubrics", []) if isinstance(group, dict) else []
                )
                for rubric in rubrics_in_group:
                    if isinstance(rubric, dict):
                        text_prop = ""
                        content = rubric.get("content", {})
                        if isinstance(content, dict):
                            prop = content.get("property", {})
                            if isinstance(prop, dict):
                                text_prop = prop.get("description", "")
                                if not text_prop:
                                    logging.warning(
                                        "Empty rubric found in case '%s' (rubric_group: '%s'): rubric_id='%s' has no text property description.",
                                        case.get("eval_case_id"),
                                        group_name,
                                        rubric.get("rubric_id"),
                                    )

                        adk_rubrics.append(
                            {
                                "rubric_id": rubric.get("rubric_id", ""),
                                "rubric_content": {"text_property": text_prop},
                                "description": rubric.get("description"),
                                "type": rubric.get("type"),
                            }
                        )

        if adk_rubrics:
            adk_eval_case["rubrics"] = adk_rubrics

        # Map system_instruction to session state if provided
        if case.get("system_instruction"):
            adk_eval_case["session_input"]["state"]["system_instruction"] = case[
                "system_instruction"
            ]

        if case.get("user_scenario"):
            adk_eval_case["conversation_scenario"] = case["user_scenario"]
            # ADK validation might require one of conversation or conversation_scenario.
            # But if scenario is provided, conversation should be None.
            adk_eval_case["conversation"] = None
        else:
            adk_eval_case["conversation"] = adk_conversation

        adk_eval_cases.append(adk_eval_case)

    return {"eval_set_id": eval_set_id, "eval_cases": adk_eval_cases}


def _save_adk_evalset(adk_evalset_dict: dict, agent_dir: str) -> str:
    """Save ADK EvalSet dictionary to a hidden subdirectory in the agent directory."""
    eval_set_id = adk_evalset_dict["eval_set_id"]
    tmp_dir = os.path.join(agent_dir, ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    target_path = os.path.join(tmp_dir, f"{eval_set_id}.evalset.json")
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(adk_evalset_dict, f, indent=2)

    # Return path relative to agent's root directory, as required by ADK
    return os.path.join(".tmp", eval_set_id)


def _prepare_adk_evalsets(
    train_dataset: dict, validation_dataset: dict, full_agent_path: str, app_name: str
) -> tuple[str, str]:
    """Translates input dataset parameters into ADK evaluation configuration."""
    # We use unique IDs in a hidden subdir to avoid collisions and trashing
    train_id = f"tmp_train_{uuid.uuid4().hex[:8]}"
    val_id = f"tmp_val_{uuid.uuid4().hex[:8]}"

    rel_train_id = _save_adk_evalset(
        _to_adk_evalset_dict(train_dataset, app_name, train_id), full_agent_path
    )
    rel_val_id = _save_adk_evalset(
        _to_adk_evalset_dict(validation_dataset, app_name, val_id), full_agent_path
    )

    return rel_train_id, rel_val_id
