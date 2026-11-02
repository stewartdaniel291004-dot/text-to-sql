from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


class SQLPolicyError(ValueError):
    """Raised when model SQL violates the read-only query policy."""


_DANGEROUS_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit", "eval", "fts3_tokenizer"}


def validate_sql(sql: str) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise SQLPolicyError("No SQL query was provided.")
    if len(sql) > 100_000:
        raise SQLPolicyError("The SQL query exceeds the allowed size.")
    try:
        parsed = sqlglot.parse(sql, read="sqlite")
    except ParseError as exc:
        raise SQLPolicyError("SQL could not be parsed as SQLite syntax.") from exc
    if len(parsed) != 1 or parsed[0] is None:
        raise SQLPolicyError("Exactly one SQL statement is allowed.")
    tree = parsed[0]
    # A CTE is represented by a SELECT; set operations also combine SELECT queries.
    if type(tree).__name__ not in {"Select", "Union", "Intersect", "Except"}:
        raise SQLPolicyError("Only a read-only SELECT or WITH ... SELECT query is allowed.")
    blocked_types = {"Insert", "Update", "Delete", "Create", "Drop", "Alter", "Command", "Transaction", "Merge", "Pragma", "Attach", "Detach", "Copy"}
    if any(type(node).__name__ in blocked_types for node in tree.walk()):
        raise SQLPolicyError("The query contains a prohibited operation.")
    protected_tables = {"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema"}
    if any(isinstance(node, exp.Table) and node.name.casefold() in protected_tables for node in tree.walk()):
        raise SQLPolicyError("Direct access to SQLite system catalogs is not allowed.")
    for node in tree.walk():
        if isinstance(node, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name() or "").casefold()
            if name in _DANGEROUS_FUNCTIONS or name.startswith("pragma_"):
                raise SQLPolicyError("The query uses a prohibited SQLite function.")
    return tree.sql(dialect="sqlite")
