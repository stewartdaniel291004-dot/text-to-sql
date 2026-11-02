from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from database.db_manager import readonly_connection
from tools.schema_inspector import inspect_schema
from tools.sql_validator import validate_sql


@dataclass
class QueryResult:
    dataframe: pd.DataFrame
    duration_seconds: float
    truncated: bool


class QueryExecutionError(RuntimeError):
    def __init__(self, safe_message: str, *, recoverable: bool = False):
        super().__init__(safe_message)
        self.recoverable = recoverable


def _authorizer(allowed: set[str]):
    safe_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    def authorize(action: int, arg1: str | None, arg2: str | None, _db: str | None, _source: str | None) -> int:
        if action not in safe_actions:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and arg1 not in allowed:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or arg1 or "").casefold() in {"load_extension", "readfile", "writefile", "edit", "eval"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return authorize


def execute_query(path: str | Path, sql: str, *, max_rows: int = 1000, timeout_seconds: float = 5.0, params: tuple[Any, ...] = ()) -> QueryResult:
    safe_sql = validate_sql(sql)
    conn = readonly_connection(path)
    started = time.perf_counter()
    deadline = started + timeout_seconds
    try:
        schema = inspect_schema(conn)
        conn.set_authorizer(_authorizer(set(schema.tables)))
        # Bound SQL and cell sizes as a second resource guard for hostile or accidental queries.
        for limit_name, limit_value in (("SQLITE_LIMIT_LENGTH", 10 * 1024 * 1024), ("SQLITE_LIMIT_SQL_LENGTH", 100_000), ("SQLITE_LIMIT_COLUMN", 2000), ("SQLITE_LIMIT_COMPOUND_SELECT", 50), ("SQLITE_LIMIT_VARIABLE_NUMBER", 1000)):
            limit = getattr(sqlite3, limit_name, None)
            if limit is not None:
                conn.setlimit(limit, limit_value)
        conn.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 1000)
        cursor = conn.execute(safe_sql, params)
        names = [d[0] for d in (cursor.description or [])]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        frame = pd.DataFrame.from_records([tuple(row) for row in rows], columns=names)
        return QueryResult(frame, time.perf_counter() - started, truncated)
    except sqlite3.OperationalError as exc:
        message = str(exc)
        if "interrupted" in message.casefold():
            raise QueryExecutionError("Query exceeded the execution time limit.") from exc
        recoverable = any(marker in message.casefold() for marker in ("syntax error", "no such table", "no such column", "ambiguous column", "misuse of aggregate", "wrong number of arguments"))
        clean = message[:240].replace("\n", " ")
        raise QueryExecutionError(f"SQLite could not run the query: {clean}", recoverable=recoverable) from exc
    except sqlite3.Error as exc:
        raise QueryExecutionError("The database denied the query or encountered a database error.") from exc
    finally:
        conn.close()
