from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.workflow import run_workflow
from config.settings import settings
from database.db_manager import readonly_connection
from tools.schema_inspector import inspect_schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the natural-language-to-SQL benchmark against the selected database.")
    parser.add_argument("--database", default=str(settings.database_path))
    parser.add_argument("--output", default=str(ROOT / "evaluation" / "benchmark_results.json"))
    args = parser.parse_args()
    if not settings.api_key:
        print("Benchmark needs OPENAI_API_KEY; no questions were sent to an LLM.", file=sys.stderr)
        return 2
    conn = readonly_connection(args.database)
    try:
        schema = inspect_schema(conn)
    finally:
        conn.close()
    questions = json.loads((ROOT / "evaluation" / "benchmark_questions.json").read_text(encoding="utf-8"))
    results = []
    for item in questions:
        outcome = run_workflow(item["question"], args.database, schema, api_key=settings.api_key, model=settings.model, max_rows=settings.max_rows, timeout_seconds=settings.timeout_seconds, max_corrections=settings.max_corrections)
        actual = list(outcome.dataframe.columns)
        expected = item.get("expected_columns", [])
        results.append({"id": item["id"], "question": item["question"], "category": item["category"], "sql_generation_success": bool(outcome.sql), "sql_validation_success": "SQL validation passed" in outcome.activity, "execution_success": outcome.status == "success", "result_correctness": ("expected columns present" if all(c.casefold() in {a.casefold() for a in actual} for c in expected) else "expected columns missing") if outcome.status == "success" else "not verifiable", "correction_attempts": outcome.correction_attempts, "execution_time_seconds": round(outcome.duration_seconds, 4), "status": outcome.status, "columns": actual, "sql": outcome.sql, "error": outcome.error})
        print(f"{item['id']} {outcome.status} · corrections={outcome.correction_attempts} · {outcome.duration_seconds:.3f}s")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "database": Path(args.database).name, "model": settings.model, "note": "Correctness is checked by expected output-column presence only; semantic answer correctness requires human review.", "summary": {"questions": len(results), "generation_success": sum(r["sql_generation_success"] for r in results), "validation_success": sum(r["sql_validation_success"] for r in results), "execution_success": sum(r["execution_success"] for r in results)}, "results": results}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved benchmark report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
