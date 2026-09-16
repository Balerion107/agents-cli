# Evaluation Guide

Run structured evaluations to confirm your agent calls the right tools, produces quality responses, and handles edge cases. Under the hood, evaluation uses the [Gemini Enterprise Agent Platform GenAI Eval SDK](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation) to grade evaluations.

!!! note "Upgrading from an older agents-cli?"
    If your project still has `tests/eval/evalsets/*.evalset.json` files from a previous version, see [Migrating Eval Datasets](../reference/eval-dataset-migration.md) for the new format.

---

## Run Your First Evaluation

Your project includes a default dataset at `tests/eval/datasets/basic-dataset.json` and metrics configuration `tests/eval/eval_config.yaml`. Run it:

```bash
agents-cli eval run
```

`eval run` executes the agent over the dataset and grades the traces in one step. The output shows scores for each eval case against the configured metrics.

```bash
# Run for a custom dataset and different metrics
agents-cli eval run --dataset tests/eval/datasets/custom-dataset.json --metrics general_quality

# Evaluate a deployed agent instead of running one locally
agents-cli eval run --url https://my-agent.run.app --app-name app
```

Split the run into `eval generate` and `eval grade` when you want traces in a custom location, or want to re-grade existing traces without re-running the agent:

```bash
agents-cli eval generate --dataset tests/eval/datasets/custom-dataset.json --output custom_traces/
agents-cli eval grade --metrics general_quality --traces custom_traces/
```

---

## Writing Eval Cases and Choosing Metrics

For full documentation on eval case schemas and available metrics, see the [Gemini Enterprise Agent Platform Evaluation documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation).

### Available Metrics Reference

You can choose from a wide range of built-in metrics depending on your agent's capabilities and the task at hand. To see the full list of available metrics, run:

```bash
agents-cli eval metric list
```

#### Common metrics at a glance

A short reference for the most-used built-in metric IDs. Use `agents-cli eval metric list` for the full set with descriptions.

| Metric ID | What it grades |
|---|---|
| `general_quality` | Overall response quality with auto-generated content-based criteria. Recommended starting point for non-agent eval. |
| `text_quality` | Linguistic aspects: fluency, coherence, grammar. |
| `instruction_following` | How well the response adheres to specific constraints and instructions. |
| `tool_use_quality` | Tool selection, parameter accuracy, and step sequence correctness (single-turn). |
| `multi_turn_tool_use_quality` | Technical and semantic correctness of tool calls across a multi-turn conversation. |
| `multi_turn_trajectory_quality` | Sequential logic, efficiency, and error-recovery robustness across turns. |
| `multi_turn_task_success` | Whether the user's goal was fulfilled across the full multi-turn conversation. |
| `final_response_quality` | Comprehensive evaluation of the final response and intermediate tool usage. |
| `final_response_reference_free` | Final-response quality without a reference answer. Requires `rubric_groups` on the case. |
| `final_response_match` | Compares the agent's final response to a provided golden reference answer. |
| `hallucination` | Segments the response into atomic claims and verifies each against tool-returned context. |
| `grounding` | Factuality and consistency against provided context. |
| `safety` | Compliance against safety policies (PII, hate speech, dangerous content, harassment, sexual). |

### Evaluation Configuration (`eval_config.yaml`)

The `eval_config.yaml` file specifies the metrics to run and defines custom metrics for grading evaluations.

```yaml
metrics_to_run:
  - response_under_500_chars

custom_metrics:
  - name: response_under_500_chars
    custom_function: |
      def evaluate(instance: dict) -> dict:
          response = instance.get("response") or {}
          text = "".join(
              p.get("text", "") for p in (response.get("parts") or []) if p.get("text")
          )
          passed = len(text) <= 500
          return {
              "score": 1.0 if passed else 0.0,
              "explanation": f"Final response is {len(text)} chars (limit 500).",
          }
  - name: response_quality_rubric
    prompt_template: |
      Rate the agent's response 1-5 for helpfulness and accuracy.
      Prompt: {prompt}
      Final response: {response}
      Full trace (for tool-call and reasoning context): {agent_data}
      Return JSON: {"score": <1|2|3|4|5>, "explanation": "<reason>"}
    judge_model: gemini-3.8-flash
    judge_model_sampling_count: 3
```

Each custom metric must conform to either the **Code Execution Metric** or **LLM-as-a-Judge Metric** (`LLMMetric`) schema:
- **Code Execution Metric**: Used to run custom Python code for evaluation. Must have a `name` and a `custom_function` (containing a `def evaluate(instance):` signature). By default, the function executes **locally in the CLI process** — no GCP project or region is required, but the user-supplied code runs with the CLI's privileges. Add `"execution": "remote"` to opt into Vertex AI's sandboxed `CodeExecutionMetric` (server-side), which requires a configured GCP project + region.
- **LLM-as-a-Judge Metric**: Used to evaluate responses using an LLM judge. Must have a `name` and a `prompt_template`. Optional fields include `judge_model` (e.g., `gemini-3.8-flash`) and `judge_model_sampling_count` (between `1` and `32`).

### Quick Reference for Common Scenarios

- **Agents with custom function tools** — Use `tool_use_quality` (for single-turn) or `multi_turn_tool_use_quality` + `multi_turn_trajectory_quality` (for multi-turn).
- **RAG agents**: use `hallucination` + `safety`, plus `grounding` when the case carries a `context` field.
- **Conversational assistants**: use `general_quality` (single-turn) or `multi_turn_task_success` (multi-turn).
- **Goal-oriented agents** — Use `multi_turn_task_success`.

Only `multi_turn_task_success`, `multi_turn_trajectory_quality`, and `multi_turn_tool_use_quality` accept multi-turn traces; the other built-ins reject them.

---

## The Eval-Fix Loop

Evaluation is iterative. Expect 5-10+ cycles before your agent consistently passes.

1. **Write 1-2 core eval cases** covering the most important behavior.
2. **Run**: `agents-cli eval run`
3. **Read the results** — which cases failed and why.
4. **Fix** — adjust the agent's instruction, tools, or logic.
5. **Re-run**: `agents-cli eval run`
6. **Expand** — once core cases pass, add edge cases and new scenarios.

---

## Beyond `eval run`

`eval run` forms the inner loop, but the eval surface has a few more commands worth knowing about. Each is a separate step you reach for as your eval setup matures.

### `agents-cli eval dataset synthesize`

Bootstraps a dataset by inspecting your local ADK agent and generating multi-turn conversation scenarios for it — no input file required. Useful for cold-starting evaluation on a new agent or expanding coverage without writing every case by hand. Each generated case includes a starting user message, a conversation plan, and the full agent trace produced by playing the scenario out against an LLM-backed user simulator.

```bash
agents-cli eval dataset synthesize --count 10
```

Steer what gets generated with `--instruction` (e.g. `"Scenarios where the user changes their mind"`) and `--environment-context` (e.g. `"Today is Monday. Flights to Paris are available."`). The output is a regular `*-dataset.json` file you can edit, commit, and feed back into `eval grade` directly (the trace is already populated, so you can skip `eval generate`).

### `agents-cli eval compare`

Compares two grade results side by side so you can see whether a change actually improved things.

```bash
agents-cli eval compare baseline_results.json candidate_results.json
```

A typical use is comparing a "before fix" run against an "after fix" run during the eval-fix loop.

### `agents-cli eval analyze`

Clusters failure modes from a grade-results file into themes, so you can see *what kinds of things* are going wrong instead of skimming individual cases.

```bash
agents-cli eval analyze --eval-result grade_results.json
```

### `agents-cli eval metric list`

Prints every built-in metric the SDK supports, with a short description for each. The starting point when you want to know what's available beyond the common metrics table above.

### `agents-cli eval optimize`

Once your evals are in place, `eval optimize` uses them to automatically tune your agent's prompts.

```bash
agents-cli eval optimize
```

A run takes anywhere from a few minutes to several hours depending on dataset size and metric complexity, so it's not something to run over and over. Reach for it after simpler approaches (rewriting the prompt yourself, adjusting metrics, fixing failing cases by hand) have run their course.

---

For full documentation on eval case schemas, metrics, and user simulation, see the [Gemini Enterprise Agent Platform Evaluation documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation).
