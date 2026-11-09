from __future__ import annotations

import csv
from contextlib import contextmanager
import io
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(os.getenv("LLMOPS_DB_PATH", "data/llmops.db"))
SENSITIVE = re.compile(r"(?i)(sk-[A-Za-z0-9_-]{12,}|(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")


def redact(value: str | None) -> str | None:
    if value is None:
        return None
    return SENSITIVE.sub("[REDACTED]", value)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str | Path = DEFAULT_DB, *, store_content: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.store_content = store_content
        with self.connect() as db:
            db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS traces(
              trace_id TEXT PRIMARY KEY, session_id TEXT, timestamp TEXT NOT NULL,
              model TEXT NOT NULL, provider TEXT NOT NULL, prompt_version TEXT,
              task_type TEXT, latency_ms REAL NOT NULL, input_tokens INTEGER NOT NULL,
              output_tokens INTEGER NOT NULL, estimated_cost REAL, status TEXT NOT NULL,
              error TEXT, feedback INTEGER, eval_score REAL, input_text TEXT, output_text TEXT,
              simulated INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS spans(
              span_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
              parent_span_id TEXT REFERENCES spans(span_id) ON DELETE CASCADE,
              name TEXT NOT NULL, started_at TEXT NOT NULL, duration_ms REAL NOT NULL,
              status TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS prompts(
              prompt_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
              version TEXT NOT NULL, template TEXT NOT NULL, created_at TEXT NOT NULL,
              UNIQUE(name,version));
            CREATE TABLE IF NOT EXISTS evaluations(
              evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT, dataset TEXT NOT NULL,
              case_id TEXT NOT NULL, trace_id TEXT REFERENCES traces(trace_id) ON DELETE SET NULL,
              metric TEXT NOT NULL, score REAL NOT NULL, details TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(timestamp);
            CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, event: dict[str, Any]) -> dict[str, Any]:
        required = ("model", "provider", "latency_ms", "input_tokens", "output_tokens")
        missing = [key for key in required if event.get(key) is None]
        if missing:
            raise ValueError("Missing required fields: " + ", ".join(missing))
        if float(event["latency_ms"]) < 0 or int(event["input_tokens"]) < 0 or int(event["output_tokens"]) < 0:
            raise ValueError("Latency and token counts must be non-negative")
        if event.get("feedback") is not None and not -1 <= int(event["feedback"]) <= 1:
            raise ValueError("feedback must be -1, 0, or 1")
        if event.get("eval_score") is not None and not 0 <= float(event["eval_score"]) <= 1:
            raise ValueError("eval_score must be between 0 and 1")
        trace_id = str(event.get("trace_id") or uuid.uuid4())
        timestamp = event.get("timestamp") or now_iso()
        inp = redact(str(event["input_text"])) if event.get("input_text") is not None else None
        out = redact(str(event["output_text"])) if event.get("output_text") is not None else None
        if not self.store_content:
            inp = out = None
        rate = event.get("rate_per_million_tokens")
        cost = None
        if rate is not None:
            rate = float(rate)
            if rate < 0:
                raise ValueError("rate_per_million_tokens must be non-negative")
            cost = (int(event["input_tokens"]) + int(event["output_tokens"])) * rate / 1_000_000
        spans = event.get("spans", [])
        span_ids = {str(s.get("span_id")) for s in spans if s.get("span_id")}
        for span in spans:
            if float(span.get("duration_ms", 0)) < 0:
                raise ValueError("Span duration must be non-negative")
            parent_id = span.get("parent_span_id")
            if parent_id and str(parent_id) not in span_ids:
                raise ValueError("Span parent_span_id must reference a span in the same trace")
        with self.connect() as db:
            db.execute("""INSERT INTO traces VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                trace_id, event.get("session_id"), timestamp, str(event["model"]), str(event["provider"]),
                event.get("prompt_version"), event.get("task_type"), float(event["latency_ms"]),
                int(event["input_tokens"]), int(event["output_tokens"]), cost,
                str(event.get("status", "ok")), redact(str(event["error"])) if event.get("error") else None,
                event.get("feedback"), event.get("eval_score"), inp, out, int(bool(event.get("simulated", False)))))
            for span in spans:
                db.execute("INSERT INTO spans VALUES(?,?,?,?,?,?,?,?)", (
                    str(span.get("span_id") or uuid.uuid4()), trace_id, span.get("parent_span_id"),
                    str(span["name"]), span.get("started_at", timestamp), float(span.get("duration_ms", 0)),
                    str(span.get("status", "ok")), json.dumps(span.get("metadata", {}))))
        return {"trace_id": trace_id, "estimated_cost": cost}

    def traces(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        clauses, args = [], []
        for key in ("model", "provider", "status", "task_type", "session_id"):
            if filters.get(key): clauses.append(f"{key}=?"); args.append(filters[key])
        if filters.get("since"): clauses.append("timestamp>=?"); args.append(filters["since"])
        sql = "SELECT * FROM traces" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY timestamp DESC"
        with self.connect() as db: return [dict(row) for row in db.execute(sql, args)]

    def trace_detail(self, trace_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
            if not row: return None
            result = dict(row)
            result["spans"] = [dict(s) for s in db.execute("SELECT * FROM spans WHERE trace_id=? ORDER BY started_at", (trace_id,))]
            result["evaluations"] = [dict(s) for s in db.execute("SELECT * FROM evaluations WHERE trace_id=? ORDER BY evaluation_id", (trace_id,))]
            return result

    def add_prompt(self, name: str, version: str, template: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO prompts(name,version,template,created_at) VALUES(?,?,?,?)", (name, version, template, now_iso()))

    def prompts(self, name: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            sql = "SELECT * FROM prompts" + (" WHERE name=?" if name else "") + " ORDER BY name, created_at"
            return [dict(r) for r in db.execute(sql, (name,) if name else ())]

    def evaluate(self, dataset: str, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        with self.connect() as db:
            for case in cases:
                output = str(case.get("output", "")); expected = str(case.get("expected", ""))
                metric = case.get("metric", "contains")
                if metric == "contains": score = float(expected.casefold() in output.casefold()) if expected else 0.0
                elif metric == "exact_match": score = float(expected.strip().casefold() == output.strip().casefold())
                elif metric == "min_length": score = float(len(output) >= int(case.get("minimum", 1)))
                elif metric == "rubric":
                    keywords = case.get("required_terms", [])
                    score = sum(str(k).casefold() in output.casefold() for k in keywords) / max(1, len(keywords))
                else: raise ValueError(f"Unsupported deterministic metric: {metric}")
                result = {"dataset": dataset, "case_id": str(case["case_id"]), "metric": metric,
                          "score": score, "trace_id": case.get("trace_id"),
                          "details": {"expected": expected, "output": output}}
                db.execute("INSERT INTO evaluations(dataset,case_id,trace_id,metric,score,details,created_at) VALUES(?,?,?,?,?,?,?)",
                           (dataset, result["case_id"], result["trace_id"], metric, score, json.dumps(result["details"]), now_iso()))
                if result["trace_id"]: db.execute("UPDATE traces SET eval_score=? WHERE trace_id=?", (score, result["trace_id"]))
                results.append(result)
        return results

    def alerts(self, *, latency_ms: float = 2000, error_rate: float = 0.1, min_eval_score: float = 0.5) -> list[str]:
        rows = self.traces()
        alerts = []
        slow = [r for r in rows if r["latency_ms"] > latency_ms]
        if slow: alerts.append(f"{len(slow)} trace(s) exceed {latency_ms:g} ms latency.")
        if rows and sum(r["status"] != "ok" for r in rows) / len(rows) > error_rate:
            alerts.append(f"Error rate exceeds {error_rate:.0%}.")
        low = [r for r in rows if r["eval_score"] is not None and r["eval_score"] < min_eval_score]
        if low: alerts.append(f"{len(low)} evaluated trace(s) fall below score {min_eval_score:g}.")
        return alerts

    def export(self, format: str = "json", filters: dict[str, Any] | None = None) -> tuple[str, str]:
        rows = self.traces(filters)
        if format == "json": return json.dumps(rows, indent=2), "application/json"
        if format != "csv": raise ValueError("format must be csv or json")
        out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["trace_id"])
        writer.writeheader(); writer.writerows(rows)
        return out.getvalue(), "text/csv"

    def delete_older_than(self, days: int) -> int:
        if days < 1: raise ValueError("days must be at least 1")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.connect() as db: return db.execute("DELETE FROM traces WHERE timestamp<?", (cutoff,)).rowcount

