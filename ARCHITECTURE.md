# Architecture

## Runtime and flow

```text
Simulated seeder ─┐
Imported JSON/CSV ──────┐
Instrumented app ───────┼─ Store.ingest ─ SQLite ─ Store queries ─ Streamlit dashboard
FastAPI /traces (local) ┘                         ├─ traces
                                                  ├─ spans
                                                  ├─ prompts
                                                  └─ evaluations
```

The dashboard and API share `LLMOPS_DB_PATH` (default `data/llmops.db`) and the same SQLite schema. SQLite uses foreign keys so deleting a trace cascades to its spans. A trace is a top-level observed operation; spans describe nested work and point to their parent span. The store exposes direct SDK-style ingestion for local integrations as well as HTTP endpoints.

## Data model

- `traces`: identifiers, UTC timestamp, provider/model labels, prompt/task metadata, latency, token counts, nullable estimated cost, status/error, feedback, latest evaluation score, optional redacted input/output, and optional simulated flag.
- `spans`: trace foreign key, nullable parent span, span name/time/duration/status and JSON metadata.
- `prompts`: unique `(name, version)` templates and creation time.
- `evaluations`: dataset/case, metric, score, optional trace link, details JSON, creation time.

An estimated cost is computed only if an event supplies `rate_per_million_tokens`; the rate is applied to combined input and output token counts. This simple estimate assumes equal input/output rates, so actual applications should pass a deliberately chosen blended rate or extend the schema for separate rates.

## Evaluation and regression workflow

Evaluation cases are JSON objects containing `case_id`, `output`, `metric`, and metric-specific inputs. Deterministic metrics produce scores in `[0,1]`. Re-run the same dataset after changing a prompt version, compare result rows/scores in SQLite/dashboard, and decide regression thresholds for your use case. This project stores results but does not automatically claim that prompt v2 is superior. The optional judge is disabled and not implemented.

## Privacy and operational boundaries

Content retention defaults off. If enabled, regex redaction runs before persistence. Operational metadata is still stored. SQLite and API are local; no authentication, encryption-at-rest layer, external monitoring agent, or production alert delivery is included. Keep the API loopback-bound. A real integration must instrument the application and send its events; this system cannot see provider traffic without that connection.
