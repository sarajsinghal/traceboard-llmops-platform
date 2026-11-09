# Traceboard — AI observability and LLMOps

Traceboard is a local-first dashboard for reviewing trace events sent by an instrumented LLM application. It stores events in SQLite and provides filtering, analytics, span drill-down, prompt-version comparison, deterministic evaluation, alerts, and export. It does not connect to a model provider or discover production traffic on its own.

This repository intentionally ships **without sample/demo trace data, evaluation datasets, or mock application scripts**. The hosted app starts empty and accepts your own JSON/CSV trace exports and JSON evaluation cases. The interface has no AI/ChatGPT watermark or generated-by claim.

## Keep source private while sharing the app

Use a private GitHub repository for the code. Streamlit Community Cloud lets a private repository power an app whose viewer access is configured separately. For your goal, deploy from the private repository and set the app to public in Streamlit's sharing settings if you want anyone to view the dashboard. Public GitHub repositories expose source code; this project is not configured for public source publishing.

### GitHub repository setup

Create a **private**, empty GitHub repository named `project17-llmops`. In PowerShell, run these commands from this folder after replacing `YOUR-USERNAME`:

```powershell
git init
git add .
git status --short
git commit -m "Build Traceboard observability dashboard"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/project17-llmops.git
git push -u origin main
```

Review `git status --short` before committing. `.gitignore` excludes the demo files, local databases, virtual environments, and secrets.

### Streamlit Community Cloud

1. Connect GitHub to [Streamlit Community Cloud](https://share.streamlit.io/) and grant it access to the private repository.
2. Select **Create app**, choose the private `project17-llmops` repository and `main` branch, and set the entry point to `streamlit_app.py`.
3. Deploy. In app settings, choose whether viewers need an invitation or whether the app should be public. A private GitHub repository keeps the code private; making the app public permits people to view and use the interface.

No provider keys or Streamlit secrets are needed. Do not make the GitHub repository public if you don't want the source visible. Private app sharing requires viewers to be invited; public app sharing does not expose the private repository source through GitHub, though no hosted web app can prevent users from reproducing visible behavior.

**Cloud storage:** the hosted app writes to its local SQLite file. Community Cloud local storage is temporary, so trace records may reset when the app restarts or rebuilds. Durable shared storage requires a separately configured database.

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
