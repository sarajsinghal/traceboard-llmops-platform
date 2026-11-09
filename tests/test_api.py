import llmops.api as api

def test_api_handlers_ingest_and_detail(tmp_path, monkeypatch):
    from llmops.core import Store
    from llmops.api import Event
    monkeypatch.setattr(api, "store", Store(tmp_path / "api.db"))
    response = api.ingest(Event(model="mock",provider="test",latency_ms=10,input_tokens=2,output_tokens=3))
    assert response["estimated_cost"] is None
    trace_id = response["trace_id"]
    assert api.trace_detail(trace_id)["trace_id"] == trace_id
    assert api.health()["judge_enabled"] is False
