from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

import pandas as pd
from langgraph.graph import END, START, StateGraph

from agents.result_summarizer import summarize_results
from agents.sql_corrector import correct_sql
from agents.sql_generator import AIUnavailable, SQLProposal, explain_sql, generate_sql
from tools.query_executor import QueryExecutionError, QueryResult, execute_query
from tools.schema_inspector import SchemaInfo
from tools.sql_validator import SQLPolicyError, validate_sql

logger = logging.getLogger("text_to_sql.workflow")


@dataclass
class WorkflowResult:
    status: str
    question: str
    query_id: str = field(default_factory=lambda: uuid4().hex)
    sql: str = ""
    parameters: tuple = ()
    rationale: str = ""
    sql_explanation: str = ""
    chart_type: str = ""
    chart_x: str = ""
    chart_y: str = ""
    chart_reason: str = ""
    explanation: str = ""
    dataframe: pd.DataFrame = field(default_factory=pd.DataFrame)
    duration_seconds: float = 0.0
    correction_attempts: int = 0
    truncated: bool = False
    error: str = ""
    activity: list[str] = field(default_factory=list)


class AgentState(TypedDict, total=False):
    question: str
    db_path: str | Path
    schema: SchemaInfo
    schema_prompt: str
    api_key: str | None
    model: str
    max_rows: int
    timeout_seconds: float
    max_corrections: int
    started: float
    proposal: SQLProposal
    outcome: WorkflowResult


def _prepare(state: AgentState) -> dict[str, Any]:
    outcome = WorkflowResult(status="running", question=state["question"], activity=["Schema inspected"])
    if not state.get("api_key"):
        outcome.status = "unavailable"
        outcome.error = "Live AI features are unavailable. Add OPENAI_API_KEY to .env; schema exploration remains available."
    return {"outcome": outcome, "schema_prompt": state["schema"].as_prompt(state["question"]), "started": time.perf_counter()}


def _generate(state: AgentState) -> dict[str, Any]:
    outcome = state["outcome"]
    try:
        proposal = generate_sql(state["question"], state["schema_prompt"], api_key=state.get("api_key"), model=state["model"])
        outcome.activity.append("SQL generated")
        if proposal.clarification:
            outcome.status, outcome.error = "clarification", str(proposal.clarification)[:500]
        elif not proposal.sql:
            outcome.status, outcome.error = "clarification", "The request could not be translated into a query. Please clarify the question."
        else:
            outcome.status = "pending_execution"
            return {"proposal": proposal, "outcome": outcome}
    except AIUnavailable as exc:
        outcome.status, outcome.error = "unavailable", str(exc)
    except Exception:
        logger.exception("SQL generation failed")
        outcome.status, outcome.error = "failed", "SQL generation failed unexpectedly. Check the redacted application log."
    return {"outcome": outcome}


def _execute_and_correct(state: AgentState) -> dict[str, Any]:
    outcome = state["outcome"]
    proposal = state["proposal"]
    current = proposal
    max_corrections = max(0, min(3, int(state.get("max_corrections", 3))))
    while True:
        outcome.sql, outcome.parameters, outcome.rationale = current.sql, current.parameters, current.rationale
        try:
            safe_sql = validate_sql(current.sql)
            outcome.sql = safe_sql
            outcome.activity.append("SQL validation passed")
        except SQLPolicyError as exc:
            outcome.status, outcome.error = "rejected", str(exc)
            break
        try:
            execution: QueryResult = execute_query(state["db_path"], safe_sql, max_rows=state["max_rows"], timeout_seconds=state["timeout_seconds"], params=current.parameters)
            outcome.dataframe = execution.dataframe
            outcome.duration_seconds = execution.duration_seconds
            outcome.truncated = execution.truncated
            outcome.activity.append("Query executed")
            chart = current.visualization or proposal.visualization
            if chart and not outcome.dataframe.empty:
                x_col, y_col = chart.get("x"), chart.get("y")
                if chart.get("chart_type") in {"Bar", "Line", "Pie"} and x_col in outcome.dataframe.columns and y_col in outcome.dataframe.columns and pd.api.types.is_numeric_dtype(outcome.dataframe[y_col]):
                    outcome.chart_type = chart["chart_type"]
                    outcome.chart_x, outcome.chart_y = x_col, y_col
                    outcome.chart_reason = str(chart.get("reason", "Suggested by the chart tool."))[:300]
                    outcome.activity.append("Chart Tool selected a chart from returned data")
            outcome.status = "success"
            break
        except QueryExecutionError as exc:
            if not exc.recoverable or outcome.correction_attempts >= max_corrections:
                outcome.status, outcome.error = "failed", str(exc)
                break
            outcome.correction_attempts += 1
            outcome.activity.append(f"SQL correction {outcome.correction_attempts} of {max_corrections}")
            logger.warning("Recoverable SQL execution error; correction attempt %s", outcome.correction_attempts)
            try:
                current = correct_sql(state["question"], state["schema_prompt"], outcome.sql, str(exc), api_key=state.get("api_key"), model=state["model"])
            except AIUnavailable as api_exc:
                outcome.status, outcome.error = "unavailable", str(api_exc)
                break
            if not current.sql:
                outcome.status, outcome.error = "failed", "The correction model did not return a usable query."
                break
        except Exception:
            logger.exception("Query execution failed unexpectedly")
            outcome.status, outcome.error = "failed", "The query execution failed unexpectedly. Check the redacted application log."
            break
    return {"outcome": outcome}


def _summarize(state: AgentState) -> dict[str, Any]:
    outcome = state["outcome"]
    try:
        outcome.sql_explanation = explain_sql(state["question"], outcome.sql, api_key=state.get("api_key"), model=state["model"])
        outcome.activity.append("SQL explained")
    except AIUnavailable:
        outcome.sql_explanation = outcome.rationale
    try:
        outcome.explanation = summarize_results(state["question"], outcome.dataframe, api_key=state.get("api_key"), model=state["model"], truncated=outcome.truncated)
        outcome.activity.append("Results summarized")
    except AIUnavailable:
        if outcome.dataframe.empty:
            outcome.explanation = "The query ran successfully and returned no rows."
        else:
            outcome.explanation = f"The query returned {len(outcome.dataframe):,} rows across {len(outcome.dataframe.columns)} columns: {', '.join(map(str, outcome.dataframe.columns))}."
            if outcome.truncated:
                outcome.explanation += f" Results were capped at {len(outcome.dataframe):,} rows."
        outcome.activity.append("Summary service unavailable; factual row summary shown")
    return {"outcome": outcome}


def _build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("prepare", _prepare)
    graph.add_node("generate_sql", _generate)
    graph.add_node("execute_read_only", _execute_and_correct)
    graph.add_node("summarize_results", _summarize)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", lambda state: "generate" if state["outcome"].status == "running" else "stop", {"generate": "generate_sql", "stop": END})
    graph.add_conditional_edges("generate_sql", lambda state: "execute" if state["outcome"].status == "pending_execution" else "stop", {"execute": "execute_read_only", "stop": END})
    graph.add_conditional_edges("execute_read_only", lambda state: "summarize" if state["outcome"].status == "success" else "stop", {"summarize": "summarize_results", "stop": END})
    graph.add_edge("summarize_results", END)
    return graph.compile()


_GRAPH = None


def run_workflow(question: str, db_path: str | Path, schema: SchemaInfo, *, api_key: str | None, model: str, max_rows: int = 1000, timeout_seconds: float = 5.0, max_corrections: int = 3) -> WorkflowResult:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    state: AgentState = {"question": question, "db_path": db_path, "schema": schema, "api_key": api_key, "model": model, "max_rows": max_rows, "timeout_seconds": timeout_seconds, "max_corrections": max_corrections}
    final = _GRAPH.invoke(state)
    outcome: WorkflowResult = final["outcome"]
    if outcome.duration_seconds == 0:
        outcome.duration_seconds = time.perf_counter() - final.get("started", time.perf_counter())
    return outcome
