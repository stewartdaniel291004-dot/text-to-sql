from __future__ import annotations

import hashlib
import logging
import sqlite3
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from agents.workflow import WorkflowResult, run_workflow
from config.settings import settings
from database.db_manager import DatabaseError, validate_database
from tools.schema_inspector import SchemaInfo
from tools.exports import csv_bytes, csv_filename, sql_filename
from tools.visualization import make_chart
from utils.logging_config import configure_logging
from utils.query_history import QueryHistory

st.set_page_config(page_title="Text-to-SQL Agent", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
configure_logging(settings.root / "logs" / "app.log")
logger = logging.getLogger("text_to_sql.ui")

st.markdown("""
<style>
:root { --ink:#14223b; --muted:#71809b; --blue:#496df5; --violet:#8065e9; --line:#e6eaf2; }
html, body, [class*="css"] { font-family:'Segoe UI','DM Sans',sans-serif; color:var(--ink); }
.stApp { background:linear-gradient(135deg,#f8faff 0%,#f5f6fc 52%,#f9f8ff 100%); }
h1,h2,h3 { font-family:'Manrope',sans-serif !important; letter-spacing:-.035em; color:var(--ink); }
[data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); }
.hero { padding:1.7rem 1.9rem; border-radius:22px; background:linear-gradient(115deg,#fff 0%,#f3f6ff 62%,#f8f4ff 100%); border:1px solid #e8ebfa; box-shadow:0 12px 35px rgba(33,53,95,.06); margin-bottom:1.2rem; }
.hero-kicker { text-transform:uppercase; letter-spacing:.14em; color:#685ce1; font-weight:700; font-size:.72rem; }
.hero h1 { margin:.25rem 0 .25rem; font-size:2.15rem; }
.hero p { color:var(--muted); margin:0; }
.metric-card { background:#fff; padding:1rem 1.1rem; border:1px solid var(--line); border-radius:16px; box-shadow:0 7px 22px rgba(33,53,95,.04); }
.section-card { background:#fff; border:1px solid var(--line); border-radius:18px; padding:1.15rem 1.35rem; box-shadow:0 8px 26px rgba(33,53,95,.045); }
.small-muted { color:var(--muted); font-size:.88rem; }
div.stButton > button[kind="primary"] { background:linear-gradient(100deg,#496df5,#8065e9); border:0; border-radius:11px; font-weight:700; }
div[data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:14px; padding:.75rem 1rem; }
</style>
""", unsafe_allow_html=True)

SUGGESTIONS = [
    "Which artist has the most albums?", "What are the top 10 best-selling tracks?",
    "Which country generates the highest revenue?", "What is the total revenue by year?",
    "Which customers have spent more than $50?", "Which genre has the most tracks?",
    "Show monthly revenue", "Which employees support the most customers?",
]
history = QueryHistory(settings.root / "data" / "query_history.json")


def _reuse_question(value: str) -> None:
    st.session_state.question_input = value


def _schema_for(path: Path, *, require_chinook: bool = False) -> SchemaInfo:
    return validate_database(path, require_chinook=require_chinook)["schema"]


def _accept_upload(upload) -> Path:
    payload = upload.getvalue()
    if len(payload) > 100 * 1024 * 1024:
        raise ValueError("Database upload exceeds the 100 MB limit.")
    if not payload.startswith(b"SQLite format 3\x00"):
        raise ValueError("The upload is not a valid SQLite database file.")
    folder = settings.root / "data" / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"upload-{uuid4().hex}.sqlite"
    path.write_bytes(payload)
    try:
        validate_database(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise ValueError("The uploaded SQLite database failed validation or contains no tables.")
    return path


if "selected_db" not in st.session_state:
    st.session_state.selected_db = settings.database_path
    st.session_state.db_label = "Chinook sample"
if "latest_result" not in st.session_state:
    st.session_state.latest_result = None
if "question_input" not in st.session_state:
    st.session_state.question_input = ""

with st.sidebar:
    st.markdown("## ◈ QueryPilot")
    st.caption("Autonomous Text-to-SQL Agent")
    st.markdown("---")
    st.markdown("**Database**")
    default_exists = settings.database_path.is_file()
    st.markdown("🟢 Connected · Chinook" if default_exists else "🟠 Database not set up")
    database_choice = st.radio("Choose data source", ["Chinook sample", "Upload SQLite"], label_visibility="collapsed", key="database_choice")
    if database_choice == "Upload SQLite":
        upload = st.file_uploader("Upload a SQLite database", type=["sqlite", "sqlite3", "db"])
        if upload:
            digest = hashlib.sha256(upload.getvalue()).hexdigest()
            if st.session_state.get("uploaded_digest") != digest:
                try:
                    st.session_state.uploaded_db = _accept_upload(upload)
                    st.session_state.uploaded_digest = digest
                    st.session_state.db_label = upload.name[:60]
                except ValueError as exc:
                    st.error(str(exc))
        db_path = st.session_state.get("uploaded_db")
        db_label = st.session_state.get("db_label", "Uploaded database")
    else:
        db_path, db_label = settings.database_path, "Chinook sample"
    st.markdown("**Model**")
    st.markdown("🟢 API key configured" if settings.api_key else "⚪ Schema-only mode")
    if not settings.api_key:
        st.caption("Add your key to `.env` to enable live query generation and summaries.")
    st.caption(f"Model: `{settings.model}`")
    st.markdown("---")
    st.markdown("**Settings**")
    max_rows = st.slider("Maximum result rows", 100, 5000, settings.max_rows, step=100)
    timeout = st.slider("Query timeout (seconds)", 1.0, 30.0, float(settings.timeout_seconds), step=1.0)
    st.caption(f"Up to {settings.max_corrections} SQL correction retries after the initial run.")
    schema = None
    db_ready = bool(db_path and Path(db_path).is_file())
    if db_ready:
        try:
            schema = _schema_for(Path(db_path), require_chinook=(database_choice == "Chinook sample"))
            st.markdown("---")
            st.markdown(f"**Schema explorer** · {len(schema.tables)} tables")
            table_filter = st.text_input("Search tables and columns", placeholder="e.g. invoice", key="schema_search").casefold().strip()
            for table_name, table in schema.tables.items():
                matching = not table_filter or table_filter in table_name.casefold() or any(table_filter in c.name.casefold() for c in table.columns)
                if not matching:
                    continue
                with st.expander(table_name):
                    st.dataframe(pd.DataFrame([{"Column": c.name, "Type": c.data_type or "—", "PK": "✓" if c.primary_key else ""} for c in table.columns]), hide_index=True, use_container_width=True)
                    if table.foreign_keys:
                        st.caption("Relationships: " + ", ".join(f"{f.from_column} → {f.to_table}.{f.to_column}" for f in table.foreign_keys))
        except DatabaseError as exc:
            st.error(str(exc))
            schema = None
    else:
        st.info("Run `py -3.11 database/setup_database.py` to download and verify Chinook.")

st.markdown('<div class="hero"><div class="hero-kicker">AI data workspace</div><h1>Ask your database anything.</h1><p>Explore relational data with natural language, transparent SQL, and results you can verify.</p></div>', unsafe_allow_html=True)

with st.container(border=True):
    question = st.text_area("Your question", key="question_input", placeholder="Ask a question about the data…", height=100, label_visibility="collapsed")
    left, right = st.columns([1, 5])
    with left:
        run_clicked = st.button("Run Query  ↗", type="primary", use_container_width=True, disabled=not db_ready or schema is None)
    with right:
        st.caption("Read-only queries · Results capped at the configured row limit")
    st.markdown("**Try asking**")
    suggestion_cols = st.columns(4)
    for index, suggested in enumerate(SUGGESTIONS):
        suggestion_cols[index % 4].button(suggested, key=f"suggestion_{index}", use_container_width=True, on_click=_reuse_question, args=(suggested,))

if run_clicked:
    if not question.strip():
        st.warning("Enter a question first.")
    elif not settings.api_key:
        st.info("Schema exploration is available, but live AI is disabled until an OpenAI API key is configured.")
    elif not db_ready or schema is None:
        st.error("Database is unavailable. Set up Chinook or choose a valid SQLite file.")
    else:
        with st.spinner("Inspecting schema, generating SQL, and running a read-only query…"):
            outcome = run_workflow(question.strip(), db_path, schema, api_key=settings.api_key, model=settings.model, max_rows=max_rows, timeout_seconds=timeout, max_corrections=settings.max_corrections)
        st.session_state.latest_result = outcome
        history.add(question.strip(), outcome.sql, outcome.status, outcome.correction_attempts, database_label=db_label)
        logger.info("query completed status=%s correction_attempts=%d db=%s", outcome.status, outcome.correction_attempts, db_label)

outcome: WorkflowResult | None = st.session_state.latest_result
if outcome:
    st.markdown("## Results")
    if outcome.status == "success":
        st.success("Query completed")
        st.markdown("### AI Answer")
        st.markdown(outcome.explanation)
        if outcome.sql_explanation or outcome.rationale:
            st.caption("SQL explanation: " + (outcome.sql_explanation or outcome.rationale))
        st.markdown("### Generated SQL")
        st.caption("Use the copy icon in the SQL block, or download the query below.")
        st.code(outcome.sql, language="sql")
        sql_name = sql_filename(outcome.question)
        csv_data = csv_bytes(outcome.dataframe)
        col_csv, col_sql, _ = st.columns([1, 1, 4])
        col_csv.download_button("Download CSV", csv_data, file_name=csv_filename(outcome.question), mime="text/csv")
        col_sql.download_button("Download SQL", outcome.sql, file_name=sql_name, mime="text/sql")
        st.markdown("### Query Results")
        if outcome.dataframe.empty:
            st.info("The query ran successfully and returned zero rows.")
        else:
            st.dataframe(outcome.dataframe, use_container_width=True, hide_index=True)
        st.markdown("### Visualization")
        numeric_cols = [c for c in outcome.dataframe.columns if pd.api.types.is_numeric_dtype(outcome.dataframe[c])]
        chartable = not outcome.dataframe.empty and len(outcome.dataframe.columns) >= 2 and bool(numeric_cols)
        if chartable:
            suggested = outcome.chart_type and outcome.chart_x in outcome.dataframe.columns and outcome.chart_y in numeric_cols
            default_y = outcome.chart_y if suggested else numeric_cols[0]
            default_x = outcome.chart_x if suggested else next((c for c in outcome.dataframe.columns if c != default_y), outcome.dataframe.columns[0])
            if suggested:
                st.caption("Chart Tool suggestion: " + (outcome.chart_reason or f"{outcome.chart_type} chart") + " · You can change the type or columns below.")
            x_col, y_col, type_col = st.columns(3)
            chart_x = x_col.selectbox("Category / time", list(outcome.dataframe.columns), index=list(outcome.dataframe.columns).index(default_x), key=f"chart_x_{outcome.query_id}")
            chart_y = y_col.selectbox("Value", numeric_cols, index=numeric_cols.index(default_y), key=f"chart_y_{outcome.query_id}")
            type_options = ["Bar", "Line", "Pie"]
            type_index = type_options.index(outcome.chart_type) if suggested and outcome.chart_type in type_options else 0
            chart_type = type_col.selectbox("Chart type", type_options, index=type_index, key=f"chart_type_{outcome.query_id}")
            try:
                st.plotly_chart(make_chart(outcome.dataframe, chart_type, chart_x, chart_y), use_container_width=True)
            except ValueError as exc:
                st.caption(str(exc))
        else:
            st.caption("This result does not have enough numeric columns for a chart. The table remains available.")
        st.markdown("### Agent Activity")
        st.write(" → ".join(outcome.activity))
        st.markdown("### Execution Details")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Returned rows", f"{len(outcome.dataframe):,}" + ("+" if outcome.truncated else ""))
        m2.metric("Columns", len(outcome.dataframe.columns))
        m3.metric("Execution time", f"{outcome.duration_seconds:.3f}s")
        m4.metric("Correction attempts", outcome.correction_attempts)
        if outcome.truncated:
            st.warning(f"Results were capped at {len(outcome.dataframe):,} rows.")
    elif outcome.status == "clarification":
        st.warning(outcome.error)
    elif outcome.status == "rejected":
        st.error("The generated SQL was blocked by the read-only safety policy.")
        st.code(outcome.sql, language="sql")
        st.caption(outcome.error)
    else:
        st.error(outcome.error or "The query could not be completed.")
        if outcome.sql:
            st.markdown("**SQL retained for review**")
            st.code(outcome.sql, language="sql")
        st.caption(f"Correction attempts: {outcome.correction_attempts} · Status: {outcome.status}")

with st.expander("Query history", expanded=False):
    items = history.load()
    head_col, clear_col = st.columns([4, 1])
    head_col.caption(f"{len(items)} recent queries stored locally on this device. API keys are not stored.")
    if clear_col.button("Clear history", disabled=not items):
        history.clear()
        st.rerun()
    for item in items:
        title = f"{'★ ' if item.get('favorite') else ''}{item.get('question','(no question)')} · {item.get('status','unknown')} · {item.get('timestamp','')}"
        with st.expander(title):
            st.code(item.get("sql") or "No SQL generated", language="sql")
            st.caption(f"Database: {item.get('database', '—')} · Correction attempts: {item.get('attempts', 0)}")
            c1, c2 = st.columns([1, 5])
            c1.button("Reuse question", key=f"reuse_{item.get('id')}", on_click=_reuse_question, args=(item.get("question", ""),))
            if c2.button("☆ Favorite" if not item.get("favorite") else "★ Unfavorite", key=f"fav_{item.get('id')}"):
                history.update_favorite(item.get("id", ""), not item.get("favorite", False))
                st.rerun()

st.caption("Read-only SQL reduces risk but does not replace normal application security. Uploaded database content and query text are treated as untrusted input.")
