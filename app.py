from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from llmops.core import Store  # noqa: E402


def parse_trace_upload(upload) -> list[dict]:
    """Read one event, an event list, or {events: [...]} from JSON/CSV."""
    if upload.name.lower().endswith(".csv"):
        frame = pd.read_csv(upload, keep_default_na=False)
        records = frame.to_dict(orient="records")
    else:
        payload = json.loads(upload.getvalue().decode("utf-8-sig"))
        if isinstance(payload, dict):
            records = payload.get("events", [payload])
        else:
            records = payload
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError("Expected a JSON event, an array of events, or an object with an 'events' array.")
    normalized = []
    for source in records:
        event = {}
        for key, value in source.items():
            is_missing = pd.api.types.is_scalar(value) and pd.isna(value)
            is_blank = isinstance(value, str) and not value.strip()
            event[key] = None if is_missing or is_blank else value
        if isinstance(event.get("spans"), str):
            event["spans"] = json.loads(event["spans"]) if event["spans"].strip() else []
        if isinstance(event.get("simulated"), str):
            event["simulated"] = event["simulated"].strip().lower() in {"true", "1", "yes"}
        if event.get("simulated") is None:
            event["simulated"] = False
        normalized.append(event)
    return normalized


st.set_page_config(
    page_title="Traceboard · LLM Observability",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

db_path = os.getenv("LLMOPS_DB_PATH", str(ROOT / "data" / "llmops.db"))
store = Store(db_path, store_content=os.getenv("LLMOPS_STORE_CONTENT", "false").lower() == "true")

with st.sidebar:
    st.markdown("### 🔎 Traceboard")
    st.caption("Local-first LLM observability")
    page = st.segmented_control(
        "Workspace", ["Overview", "Traces", "Prompts", "Evaluations", "Settings"],
        label_visibility="collapsed", default="Overview",
    )
    st.divider()
    st.caption(f"Storage · `{Path(db_path).name}`")
    st.caption("🔒 Content off by default")

all_rows = store.traces()
all_df = pd.DataFrame(all_rows)
if not all_df.empty:
    all_df["timestamp"] = pd.to_datetime(all_df["timestamp"], utc=True, errors="coerce")

st.caption("PROJECT 17 · OBSERVABILITY WORKSPACE")
st.title("See what your LLM app is doing.")
st.write("Explore traces, understand agent steps, compare prompts, and check quality signals — all in one local dashboard.")
st.badge("SQLite", color="blue")
st.badge("Bring your own events", color="green")
st.badge("LLM judge off", color="gray")

if all_df.empty:
    df = all_df.copy()
    chosen_models, chosen_tasks, chosen_status = [], [], []
    st.info("Your workspace is empty. Open **Traces** to import a JSON or CSV export from an instrumented application.")
else:
    with st.container(border=True):
        st.markdown("**Explore a time window**")
        f1, f2, f3, f4 = st.columns([1.25, 1.25, 1.25, 1.7])
        min_day = all_df.timestamp.min().date()
        max_day = all_df.timestamp.max().date()
        date_range = f1.date_input("Dates", value=(min_day, max_day), min_value=min_day, max_value=max_day)
        model_opts = sorted(all_df.model.dropna().unique())
        chosen_models = f2.multiselect("Models", model_opts, default=model_opts)
        task_opts = sorted(all_df.task_type.dropna().unique())
        chosen_tasks = f3.multiselect("Task types", task_opts, default=task_opts)
        status_opts = sorted(all_df.status.dropna().unique())
        chosen_status = f4.multiselect("Statuses", status_opts, default=status_opts)
    if len(date_range) == 2:
        start = pd.Timestamp(date_range[0], tz="UTC")
        end = pd.Timestamp(date_range[1], tz="UTC") + pd.Timedelta(days=1)
        df = all_df[(all_df.timestamp >= start) & (all_df.timestamp < end)]
    else:
        df = all_df.copy()
    df = df[df.model.isin(chosen_models) & df.task_type.isin(chosen_tasks) & df.status.isin(chosen_status)]

if page == "Overview":
    st.subheader("Performance at a glance")
    if df.empty:
        st.caption("Metrics and trends will appear after you import traces.")
    else:
        st.caption("Metrics reflect the records selected above.")
        error_pct = (df.status != "ok").mean() * 100
        eval_avg = df.eval_score.dropna().mean()
        known_cost = df.estimated_cost.dropna()
        with st.container(horizontal=True):
            st.metric("Traces", f"{len(df):,}", help="Number of matching trace records", border=True)
            st.metric("Median latency", f"{df.latency_ms.median():,.0f} ms", border=True)
            st.metric("Error rate", f"{error_pct:.1f}%", border=True)
            st.metric("Total tokens", f"{int((df.input_tokens + df.output_tokens).sum()):,}", border=True)
            st.metric("Avg. eval score", f"{eval_avg:.0%}" if pd.notna(eval_avg) else "No scores", border=True)
            st.metric("Estimated cost", f"${known_cost.sum():.4f}" if not known_cost.empty else "Not configured", border=True)

        t1, t2, t3 = st.tabs(["Traffic & latency", "Quality & feedback", "By model"])
        with t1:
            left, right = st.columns(2)
            hourly = df.set_index("timestamp").sort_index().resample("1h").agg(trace_count=("trace_id", "count"), median_latency=("latency_ms", "median"))
            with left:
                st.markdown("**Trace volume**")
                st.area_chart(hourly[["trace_count"]], height=280, alt="Hourly trace volume in the selected time window")
            with right:
                st.markdown("**Median latency over time**")
                st.line_chart(hourly[["median_latency"]], height=280, alt="Median trace latency over time")
        with t2:
            left, right = st.columns(2)
            with left:
                st.markdown("**Evaluation score distribution**")
                scores = df.eval_score.dropna()
                if scores.empty: st.caption("Run an evaluation to populate this chart.")
                else: st.bar_chart(scores.value_counts(bins=5, sort=False).sort_index(), height=280, alt="Distribution of evaluation scores")
            with right:
                st.markdown("**User feedback**")
                feedback = df.feedback.dropna().map({-1: "Negative", 0: "Neutral", 1: "Positive"}).value_counts()
                if feedback.empty: st.caption("No feedback values in this selection.")
                else: st.bar_chart(feedback, height=280, alt="Count of positive, neutral, and negative user feedback")
        with t3:
            by_model = df.groupby("model").agg(traces=("trace_id", "count"), median_latency_ms=("latency_ms", "median"), error_rate=("status", lambda s: (s != "ok").mean()), avg_eval_score=("eval_score", "mean")).reset_index()
            st.dataframe(by_model, width="stretch", hide_index=True, alt="Comparison of trace counts, latency, errors, and evaluation score by model", column_config={"error_rate": st.column_config.ProgressColumn("Error rate", min_value=0, max_value=1, format="percent"), "avg_eval_score": st.column_config.ProgressColumn("Avg eval score", min_value=0, max_value=1, format="percent")})

        with st.expander("Threshold alerts", expanded=True):
            a,b,c = st.columns(3)
            latency_limit = a.number_input("Latency limit (ms)", min_value=1, value=2000, step=100)
            error_limit = b.slider("Error-rate limit", 0, 100, 10, format="%d%%") / 100
            quality_limit = c.slider("Minimum evaluation score", 0, 100, 50, format="%d%%") / 100
            alerts = []
            if (df.latency_ms > latency_limit).any(): alerts.append(f"{int((df.latency_ms > latency_limit).sum())} traces exceed {latency_limit} ms.")
            if error_pct / 100 > error_limit: alerts.append(f"Error rate ({error_pct:.1f}%) is above the {error_limit:.0%} limit.")
            low = df.eval_score.notna() & (df.eval_score < quality_limit)
            if low.any(): alerts.append(f"{int(low.sum())} scored traces fall below {quality_limit:.0%}.")
            if alerts:
                for alert in alerts: st.warning(alert, icon="⚠️")
            else: st.success("No selected traces breach these thresholds.", icon="✓")
        with st.expander("About estimated cost"):
            if known_cost.empty: st.caption("Cost is not configured for these events. It appears only when the sending application supplies an explicit rate.")
            else: st.metric("Sum of supplied estimates", f"${known_cost.sum():.4f}")

elif page == "Traces":
    st.subheader("Trace explorer")
    st.caption("Import event exports, search traces, inspect spans, and download filtered records.")
    uploaded = st.file_uploader("Import trace events (JSON or CSV)", type=["json", "csv"], help="JSON may contain one event, a list of events, or an object with an 'events' list.")
    if uploaded is not None:
        try:
            imported = parse_trace_upload(uploaded)
            st.caption(f"Found {len(imported)} event(s) in {uploaded.name}.")
            if st.button("Import events", type="primary"):
                added, errors = 0, []
                for index, event in enumerate(imported, start=1):
                    try:
                        store.ingest(event)
                        added += 1
                    except (ValueError, KeyError, sqlite3.IntegrityError, TypeError) as exc:
                        errors.append(f"Row {index}: {exc}")
                if added: st.success(f"Imported {added} trace event(s).")
                if errors:
                    for message in errors[:8]: st.error(message)
                if added: st.rerun()
        except (ValueError, json.JSONDecodeError, pd.errors.ParserError) as exc:
            st.error(f"Could not read this file: {exc}")

    search = st.text_input("Search traces", placeholder="Trace ID, session, prompt, or task type")
    view_df = df
    if search and not df.empty:
        searchable = ["trace_id", "session_id", "prompt_version", "task_type"]
        mask = df[searchable].fillna("").astype(str).apply(lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)
        view_df = df[mask]
    columns = ["trace_id", "timestamp", "session_id", "model", "provider", "prompt_version", "task_type", "latency_ms", "input_tokens", "output_tokens", "estimated_cost", "status", "feedback", "eval_score", "simulated"]
    if view_df.empty:
        st.info("No matching traces yet. Import your app's trace events above.")
    else:
        st.dataframe(view_df[columns], width="stretch", hide_index=True, height=390, alt="Filtered LLM trace records",
            column_config={"trace_id": st.column_config.TextColumn("Trace ID", width="medium"), "timestamp": st.column_config.DatetimeColumn("Timestamp", format="MMM D, HH:mm"), "latency_ms": st.column_config.NumberColumn("Latency", format="%.0f ms"), "estimated_cost": st.column_config.NumberColumn("Est. cost", format="$%.5f"), "eval_score": st.column_config.ProgressColumn("Eval score", min_value=0, max_value=1, format="percent"), "simulated": st.column_config.CheckboxColumn("Simulated")})
        ex1, ex2, _ = st.columns([1,1,4])
        export_frame = view_df[columns].copy()
        ex1.download_button("Download CSV", export_frame.to_csv(index=False), file_name="traceboard-traces.csv", mime="text/csv", width="stretch")
        ex2.download_button("Download JSON", export_frame.to_json(orient="records", date_format="iso", indent=2), file_name="traceboard-traces.json", mime="application/json", width="stretch")
        selected = st.selectbox("Select a trace to inspect", view_df.trace_id.tolist(), format_func=lambda tid: f"{tid[:8]}… · {view_df.loc[view_df.trace_id == tid, 'task_type'].iloc[0]}")
        detail = store.trace_detail(selected)
        main, info = st.columns([1.5,1])
        with main:
            st.markdown("**Agent steps**")
            spans = detail.get("spans", [])
            if spans:
                for span in spans:
                    parent = "↳ " if span.get("parent_span_id") else ""
                    col1, col2, col3 = st.columns([2,1,1])
                    col1.write(f"{parent}**{span['name']}**")
                    col2.write(f"{span['duration_ms']:.0f} ms")
                    col3.write(span["status"])
                    st.progress(min(1.0, float(span["duration_ms"]) / max(1, float(detail["latency_ms"]))))
            else: st.caption("This trace has no spans.")
        with info:
            st.markdown("**Trace details**")
            for label, key in (("Trace ID","trace_id"),("Session","session_id"),("Model","model"),("Prompt","prompt_version"),("Result","status"),("Error","error"),("Feedback","feedback"),("Evaluation","eval_score")):
                value = detail.get(key)
                if value is not None: st.markdown(f"**{label}:** {value}")
            if detail.get("input_text") or detail.get("output_text"):
                with st.expander("Stored content (redacted)"):
                    st.write("Input", detail.get("input_text")); st.write("Output", detail.get("output_text"))

elif page == "Prompts":
    st.subheader("Prompt library")
    st.caption("Register prompt versions and compare their wording side by side.")
    with st.form("new_prompt"):
        prompt_name = st.text_input("Prompt name")
        prompt_version = st.text_input("Version", placeholder="v1")
        prompt_template = st.text_area("Prompt template", height=140)
        save_prompt = st.form_submit_button("Save prompt version", type="primary")
    if save_prompt:
        if not prompt_name.strip() or not prompt_version.strip() or not prompt_template.strip():
            st.error("Enter a name, version, and template.")
        else:
            try:
                store.add_prompt(prompt_name.strip(), prompt_version.strip(), prompt_template)
                st.success("Prompt version saved.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("That prompt name and version already exist.")
    prompts = store.prompts()
    if prompts:
        prompt_df = pd.DataFrame(prompts)
        names = sorted(prompt_df.name.unique())
        selected_name = st.selectbox("Compare prompt", names)
        variants = prompt_df[prompt_df.name == selected_name].sort_values("created_at")
        if len(variants) >= 2:
            v1, v2 = st.columns(2)
            left_ix = v1.selectbox("Version A", variants.index, format_func=lambda ix: variants.loc[ix, "version"])
            right_ix = v2.selectbox("Version B", variants.index, index=min(1, len(variants)-1), format_func=lambda ix: variants.loc[ix, "version"])
            v1.text_area("Template A", variants.loc[left_ix, "template"], height=230, disabled=True)
            v2.text_area("Template B", variants.loc[right_ix, "template"], height=230, disabled=True)
        else:
            st.text_area("Saved template", variants.iloc[0].template, height=180, disabled=True)
            st.caption("Save another version with the same prompt name to compare it here.")
        st.dataframe(variants[["version", "created_at", "template"]], width="stretch", hide_index=True, alt="Prompt version history")
    else:
        st.caption("No prompt versions saved yet.")

elif page == "Evaluations":
    st.subheader("Evaluation lab")
    st.caption("Upload a JSON evaluation dataset and run deterministic checks. The optional LLM judge is disabled.")
    st.code('{"case_id":"refund-window","metric":"contains","expected":"within 30 days","output":"Refunds are available within 30 days."}', language="json")
    dataset_name = st.text_input("Dataset name", "my-quality-checks")
    evaluation_file = st.file_uploader("Upload evaluation cases (JSON)", type=["json"], key="evaluation_upload")
    if evaluation_file:
        try:
            payload = json.loads(evaluation_file.getvalue().decode("utf-8-sig"))
            cases = payload.get("cases", []) if isinstance(payload, dict) else payload
            if not isinstance(cases, list) or not all(isinstance(case, dict) and "case_id" in case and "metric" in case and "output" in case for case in cases):
                raise ValueError("Cases must be a JSON list with case_id, metric, and output fields.")
            st.caption(f"{len(cases)} evaluation case(s) loaded.")
            with st.expander("Review cases"):
                st.dataframe(pd.DataFrame(cases), width="stretch", hide_index=True, alt="Uploaded evaluation cases")
            if st.button("Run evaluation", type="primary"):
                results = store.evaluate(dataset_name, cases)
                st.session_state.last_eval = results
        except (ValueError, json.JSONDecodeError) as exc:
            st.error(f"Could not read evaluation dataset: {exc}")
    results = st.session_state.get("last_eval")
    if results:
        eval_df = pd.DataFrame(results)
        st.metric("Mean rule-check score", f"{eval_df.score.mean():.0%}")
        st.dataframe(eval_df[["case_id", "metric", "score"]], width="stretch", hide_index=True, alt="Deterministic evaluation results", column_config={"score": st.column_config.ProgressColumn("Score", min_value=0, max_value=1, format="percent")})
    with st.expander("Supported deterministic checks"):
        st.write("Use `contains`, `exact_match`, `min_length`, or `rubric` with required terms. These checks are reproducible, but they are not a semantic quality judgment.")

elif page == "Settings":
    st.subheader("Workspace settings & privacy")
    st.caption("Know where data lives and what happens when you connect an application.")
    s1,s2,s3 = st.columns(3)
    s1.metric("Trace records", len(all_rows), border=True)
    s2.metric("Storage", "SQLite · local" if not os.getenv("STREAMLIT_SHARING_MODE") else "SQLite · app instance", border=True)
    s3.metric("Content retention", "On" if store.store_content else "Off by default", border=True)
    st.info("Streamlit Community Cloud's local filesystem is temporary. Trace records can reset when the app restarts; durable hosted storage needs a separately configured database.")
    st.markdown("**Privacy defaults**")
    st.write("Prompt and response text is not stored unless `LLMOPS_STORE_CONTENT=true` is explicitly set. If enabled, basic redaction runs before storage, but should not be treated as complete sensitive-data removal.")
    st.markdown("**Connect an application**")
    st.write("The FastAPI endpoint can receive events from an instrumented application when you run it separately. This dashboard does not automatically observe provider accounts or production traffic.")
    if st.button("Delete all trace records", type="secondary"):
        with store.connect() as db: db.execute("DELETE FROM traces")
        st.success("Trace records deleted.")
        st.rerun()

st.divider()
st.caption("Traceboard · Local-first observability · External traffic appears only when an instrumented app sends events.")
