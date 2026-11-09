import json
from datetime import datetime, timedelta, timezone
import pytest
from llmops.core import Store

@pytest.fixture
def store(tmp_path): return Store(tmp_path / "test.db", store_content=True)

def event(**extra):
    return {"trace_id":"t1", "model":"mock", "provider":"simulated", "latency_ms":250,
            "input_tokens":1000, "output_tokens":500, "input_text":"email me at a@b.com sk-abcdefghijklmnop",
            "output_text":"safe output", **extra}

def test_ingestion_spans_redaction_and_privacy(store):
    result = store.ingest(event(spans=[{"span_id":"root","name":"agent"},{"name":"child","parent_span_id":"root","duration_ms":40}]))
    detail = store.trace_detail(result["trace_id"])
    assert len(detail["spans"]) == 2 and detail["spans"][1]["parent_span_id"] == "root"
    assert "[REDACTED]" in detail["input_text"] and "a@b.com" not in detail["input_text"]
    private_store = Store(store.path.parent / "private.db")
    private_store.ingest(event(trace_id="private"))
    assert private_store.trace_detail("private")["input_text"] is None

def test_explicit_cost_only(store):
    assert store.ingest(event())["estimated_cost"] is None
    result = store.ingest(event(trace_id="t2", rate_per_million_tokens=2))
    assert result["estimated_cost"] == pytest.approx(.003)
    with pytest.raises(ValueError): store.ingest(event(trace_id="t3", rate_per_million_tokens=-1))
    with pytest.raises(ValueError): store.ingest(event(trace_id="t4", spans=[{"span_id":"child","parent_span_id":"missing","name":"bad"}]))

def test_prompt_versioning(store):
    store.add_prompt("support", "v1", "hello {{x}}")
    store.add_prompt("support", "v2", "hello kindly {{x}}")
    assert [p["version"] for p in store.prompts("support")] == ["v1", "v2"]
    with pytest.raises(Exception): store.add_prompt("support", "v1", "duplicate")

def test_deterministic_eval_and_alerts(store):
    store.ingest(event(eval_score=.2, latency_ms=3500, status="error"))
    results = store.evaluate("tiny", [{"case_id":"a","metric":"contains","expected":"ok","output":"not ok"},
                                       {"case_id":"b","metric":"rubric","required_terms":["one","two"],"output":"one"}])
    assert [r["score"] for r in results] == [1.0, .5]  # contains is a literal substring check
    assert len(store.alerts(latency_ms=1000,error_rate=.2,min_eval_score=.5)) == 3

def test_exports_and_retention(store):
    store.ingest(event())
    payload, mime = store.export("json")
    assert json.loads(payload)[0]["trace_id"] == "t1" and mime == "application/json"
    csv, mime = store.export("csv")
    assert "trace_id" in csv and mime == "text/csv"
    store.ingest(event(trace_id="old", timestamp=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()))
    assert store.delete_older_than(7) == 1

