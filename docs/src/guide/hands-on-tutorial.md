# Tutorial: Manual Workflow

*For developers who prefer to type every command themselves, without a coding agent.*

This tutorial walks you through building, testing, and evaluating an ADK agent by typing every command yourself — no coding agent required.

!!! tip
    Prefer to let your coding agent do the work? See [Tutorial: Build Your First Agent](quickstart-tutorial.md) instead.

---

## What You'll Build

You'll start with the default agent template — an assistant that can look up weather and tell the time — then customize it with a new persona and a custom tool.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed
- Authentication set up — either a [Gemini API key](authentication.md#option-a-gemini-api-key-google-ai-studio) or [Google Cloud credentials](authentication.md#option-b-google-cloud-vertex-ai)

---

## 1. Create the Project

```bash
agents-cli create my-first-agent --prototype --yes
cd my-first-agent
agents-cli install
```

- `--prototype` skips Terraform and CI/CD — just agent code, tests, and eval sets.
- `--yes` auto-accepts defaults (ADK template, in-memory session storage).
- `agents-cli install` installs all Python dependencies via `uv sync`.

---

## 2. Explore the Project

Your project contains:

```
my-first-agent/
├── app/
│   ├── __init__.py       # Registers the app
│   ├── agent.py          # Agent definition — this is where your logic lives
│   └── app_utils/        # Telemetry and utility code
├── tests/
│   ├── eval/
│   │   ├── datasets/
│   │   │   └── basic-dataset.json   # Test cases for evaluation
│   │   └── eval_config.yaml         # Metrics configuration
│   ├── integration/
│   │   └── test_agent.py
│   └── unit/
│       └── test_dummy.py
├── pyproject.toml        # Project config and dependencies
└── GEMINI.md             # Guidance file for coding agents
```

The important file is `app/agent.py`. Open it and you'll see two tool functions (`get_weather`, `get_current_time`) and an agent definition:

```python title="app/agent.py"
root_agent = Agent(
    name="root_agent",
    model=Gemini(model="gemini-3.8-flash"),
    instruction="You are a helpful AI assistant designed to provide accurate and useful information.",
    tools=[get_weather, get_current_time],
)
```

For a full breakdown of every file, see [Project Structure](project-structure.md).

---

## 3. Run the Agent Locally

Start the ADK web playground:

```bash
agents-cli playground
```

Open [http://localhost:8080](http://localhost:8080) in your browser. You'll see a chat interface. Try sending:

> What's the weather in San Francisco?

The agent calls the `get_weather` tool and responds with something like: *"It's 60 degrees and foggy in San Francisco."*

!!! tip
    The playground has hot reload — save changes to `app/agent.py` and they take effect immediately.

---

## 4. Test from the Terminal

You can also test without the browser:

```bash
agents-cli run "What's the weather in San Francisco?"
```

This sends a single prompt and prints the agent's response.

---

## 5. Customize the Agent

Let's give the agent a personality. Open `app/agent.py` and change the instruction:

```python title="app/agent.py"
root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-3.8-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a cheerful weather reporter who speaks in short, 
    punchy sentences. Always include a fun weather-related pun in your responses. 
    When asked about time, relate it back to weather somehow.""",
    tools=[get_weather, get_current_time],
)
```

Save the file. If the playground is still running, it reloads automatically. Try the same question again — the response should now have a different tone.

---

## 6. Add a Custom Tool

Let's add a tool that counts words. Add this function above the `root_agent` definition in `app/agent.py`:

```python title="app/agent.py"
def count_words(text: str) -> str:
    """Count the number of words in the given text.

    Args:
        text: The text to count words in.

    Returns:
        A string with the word count.
    """
    word_count = len(text.split())
    return f"The text contains {word_count} words."
```

Then register it in the agent's `tools` list:

```python
    tools=[get_weather, get_current_time, count_words],
```

Test it:

```bash
agents-cli run "How many words are in: The quick brown fox jumps over the lazy dog"
```

The agent calls `count_words` and responds with the word count.

!!! tip
    ADK tools are plain Python functions. The **docstring** becomes the description the LLM sees, so write it clearly — it tells the model when and how to use the tool.

For more on adding tools, see the [ADK Tools documentation](https://google.github.io/adk-docs/tools/).

---

## 7. Run an Evaluation

Evaluations validate that your agent behaves correctly. Your project comes with a default dataset at `tests/eval/datasets/basic-dataset.json`:

```json title="tests/eval/datasets/basic-dataset.json"
{
  "eval_cases": [
    {
      "eval_case_id": "greeting",
      "prompt": {
        "role": "user",
        "parts": [{"text": "Hello, what can you help me with?"}]
      }
    }
  ]
}
```

Each eval case defines a user message. The evaluation system sends the message to your agent and grades the response using metrics specified in `eval_config.yaml`.

Run it:

```bash
agents-cli eval run
```

The output shows scores for each eval case against the configured metrics.

For the full evaluation workflow — writing test cases, adding metrics, the eval-fix loop, and the rest of the eval surface (`eval dataset synthesize`, `eval compare`, `eval analyze`, `eval metric list`, and `eval optimize`) — see the [Evaluation Guide](evaluation.md).

---

## 8. Deploy to Google Cloud

Once your agent passes evals, deploy it. First, add a deployment target (prototype projects don't include one):

```bash
agents-cli scaffold enhance --deployment-target cloud_run
```

Set your Google Cloud project and deploy:

```bash
gcloud config set project YOUR_DEV_PROJECT_ID
agents-cli deploy
```

Verify it's running:

```bash
agents-cli deploy --status
```

!!! note
    Deployment requires [Google Cloud credentials](authentication.md#option-b-google-cloud-vertex-ai). See the [Deployment Guide](deployment.md) for Agent Runtime, GKE, and other options.

---

## 9. Observe Your Agent

Cloud Trace is enabled by default — no configuration needed. Send a few requests to your agent, then open the [Trace explorer](https://console.cloud.google.com/traces) in the Google Cloud Console. You'll see spans for each LLM call and tool execution, with latency breakdowns.

### View content logs

To inspect the actual prompts and responses your agent handles in production, provision the observability infrastructure:

```bash
agents-cli infra single-project --project YOUR_DEV_PROJECT_ID
```

This runs Terraform to create a dedicated service account, GCS bucket, and BigQuery dataset — and updates your deployed service to use them.

See the [Observability Guide](observability/index.md) for verification steps, full content capture, and BigQuery Agent Analytics.

---

## What You've Done

| Step | What happened |
|------|--------------|
| `agents-cli create --prototype --yes` | Created a project with agent code, tests, and eval sets |
| `agents-cli playground` | Started the ADK playground for interactive testing |
| `agents-cli run "..."` | Tested the agent from the terminal |
| Edited `agent.py` | Customized the persona and added a tool |
| `agents-cli eval run` | Validated agent behavior with structured evaluations |
| `agents-cli deploy` | Deployed the agent to Google Cloud |
| Trace explorer + content logs | Verified tracing and set up prompt-response logging |

---

## Next Steps

- [ADK Custom Tools](https://google.github.io/adk-docs/tools/) — more tool patterns and advanced usage
- [Evaluation Guide](evaluation.md) — write better evals, understand metrics
- [Deployment Guide](deployment.md) — Agent Runtime, GKE, secrets, and CI/CD
- [Observability Guide](observability/index.md) — BigQuery Agent Analytics, third-party integrations
