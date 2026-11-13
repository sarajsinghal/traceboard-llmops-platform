# Traceboard — LLM Observability and Operations

Traceboard is a local-first dashboard for reviewing trace events sent by an instrumented LLM application. It stores events in SQLite and provides filtering, analytics, span drill-down, prompt-version comparison, deterministic evaluation, alerts, and export. It does not connect to a model provider or discover production traffic on its own.

This repository intentionally ships **without sample/demo trace data, evaluation datasets, or mock application scripts**. The hosted app starts empty and accepts your own JSON/CSV trace exports and JSON evaluation cases. The interface has no AI/ChatGPT watermark or generated-by claim.

## Repository and deployment

This repository is public, so its source code is visible. Streamlit app access is configured separately from GitHub repository visibility. Keep API keys, personal data, and confidential trace content out of commits and public demonstrations.

Live application: https://traceboard-llmops-platform.streamlit.app/

Deploy from this repository with `streamlit_app.py` as the entry point. Review the app's viewer-access settings before sharing it. Hosted SQLite storage may be temporary, so use a managed database when durable records are required.

## Run locally on Windows 11

Python 3.11–3.13 and PowerShell are supported. The app runs on CPU; no GPU or API key is needed.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD\src"
streamlit run app.py
```

Open the local address Streamlit prints (usually `http://localhost:8501`). If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that window and activate again. Package installation requires internet access; subsequent app use is local.

## Import your own trace data

Open **Traces** and upload JSON or CSV. JSON may be one trace event, a list of events, or an object with an `events` list. Each event needs `model`, `provider`, `latency_ms`, `input_tokens`, and `output_tokens`. Optional fields include trace/session IDs, UTC timestamp, prompt version, task type, spans, status/error, feedback, evaluation score, and a cost rate that you explicitly provide.

The same local SQLite store is used for every page. Prompt/output bodies are not retained unless `LLMOPS_STORE_CONTENT=true` is set. If enabled, basic redaction is applied before storage but is not guaranteed to remove every sensitive value.

### Run the local ingestion API

In a second PowerShell window in this folder:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD\src"
python -m llmops api
```

The API is bound to `127.0.0.1:8000`; its docs are at `http://127.0.0.1:8000/docs`. Example request:

```powershell
$event = @{
  model = "your-model"; provider = "your-provider"; prompt_version = "support:v2"
  task_type = "support"; latency_ms = 420; input_tokens = 240; output_tokens = 96
  session_id = "session-001"; status = "ok"; feedback = 1
  spans = @(@{ span_id = "workflow-1"; name = "agent.workflow"; duration_ms = 400 })
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/traces -ContentType "application/json" -Body $event
```

Cost remains blank unless `rate_per_million_tokens` is explicitly included. The current estimate applies one supplied rate to combined input/output tokens.

## Dashboard sections

- **Overview:** trace count, latency, error rate, tokens, evaluation scores, optional estimated cost, trends, feedback, model comparisons, and configurable threshold alerts.
- **Traces:** import JSON/CSV, filter and search traces, inspect spans, and download filtered CSV/JSON.
- **Prompts:** register prompt versions and compare templates.
- **Evaluations:** upload a JSON case list and run `contains`, `exact_match`, `min_length`, or `rubric` checks. LLM-as-judge is disabled.
- **Settings:** review privacy/storage behavior and delete all local trace records.

## Tests

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest -q
```

## Repository contents

```text
app.py                     Streamlit dashboard
streamlit_app.py           Streamlit Community Cloud entry point
.streamlit/config.toml     Professional light teal theme
src/llmops/core.py         SQLite store, redaction, evaluation, alerts, exports
src/llmops/api.py          FastAPI ingestion and read/export endpoints
tests/                     Automated tests
ARCHITECTURE.md            Data flow, schema, design decisions, boundaries
RESUME_BULLETS.md          Resume bullets based on implemented features
CONTRIBUTING.md            Contribution guidance
```
