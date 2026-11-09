from __future__ import annotations
import json
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from .core import Store

store = Store(os.getenv("LLMOPS_DB_PATH", "data/llmops.db"), store_content=os.getenv("LLMOPS_STORE_CONTENT", "false").lower() == "true")
app = FastAPI(title="Project 17 LLMOps Local API", version="1.0.0", description="Local trace ingestion and deterministic evaluation. No external provider calls.")

class Event(BaseModel):
    model: str
    provider: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    trace_id: str | None = None
    session_id: str | None = None
    timestamp: str | None = None
    prompt_version: str | None = None
    task_type: str | None = None
    status: str = "ok"
    error: str | None = None
    feedback: int | None = None
    eval_score: float | None = None
    rate_per_million_tokens: float | None = None
    input_text: str | None = None
    output_text: str | None = None
    simulated: bool = False
    spans: list[dict] = []

@app.get("/health")
def health(): return {"status": "ok", "storage": "local SQLite", "judge_enabled": False}

@app.post("/traces")
def ingest(event: Event):
    try: return store.ingest(event.model_dump())
    except (ValueError, KeyError) as exc: raise HTTPException(422, str(exc)) from exc

@app.get("/traces")
def list_traces(model: str | None = None, status: str | None = None, provider: str | None = None):
    return store.traces({"model": model, "status": status, "provider": provider})

@app.get("/traces/{trace_id}")
def trace_detail(trace_id: str):
    result = store.trace_detail(trace_id)
    if result is None: raise HTTPException(404, "Trace not found")
    return result

@app.get("/export/{format}")
def export(format: str = "json"):
    try: body, media = store.export(format)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    return Response(body, media_type=media, headers={"Content-Disposition": f"attachment; filename=traces.{format}"})

@app.post("/evaluate/{dataset}")
def evaluate(dataset: str, cases: list[dict]):
    try: return store.evaluate(dataset, cases)
    except (ValueError, KeyError) as exc: raise HTTPException(422, str(exc)) from exc

