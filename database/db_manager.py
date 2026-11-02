from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from tools.schema_inspector import inspect_schema


class DatabaseError(RuntimeError):
    pass


def readonly_connection(path: str | Path) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise DatabaseError("Database file is missing. Set up Chinook or select a valid SQLite database.")
    uri = f"file:{quote(resolved.as_posix(), safe='/')}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=2.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA trusted_schema = OFF")
        return conn
    except sqlite3.Error as exc:
        raise DatabaseError("Could not open the selected database as read-only.") from exc


def validate_database(path: str | Path, *, require_chinook: bool = False) -> dict:
    conn = readonly_connection(path)
    try:
        result = conn.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise DatabaseError("SQLite integrity check failed.")
        schema = inspect_schema(conn)
        if not schema.tables:
            raise DatabaseError("The database contains no user tables.")
        if require_chinook:
            required = {"Artist", "Album", "Track", "Genre", "MediaType", "Playlist", "Customer", "Invoice", "InvoiceLine", "Employee"}
            missing = required - set(schema.tables)
            if missing:
                raise DatabaseError("Chinook verification failed: expected tables are missing.")
        return {"table_count": len(schema.tables), "integrity": "ok", "schema": schema}
    finally:
        conn.close()
