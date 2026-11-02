import sqlite3

import pytest

from database.db_manager import DatabaseError, readonly_connection, validate_database
from tools.schema_inspector import inspect_schema


def test_readonly_connection_and_integrity(sample_db):
    assert validate_database(sample_db)["integrity"] == "ok"
    conn = readonly_connection(sample_db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("CREATE TABLE forbidden (id INTEGER)")
    conn.close()


def test_schema_includes_columns_keys_and_relationships(sample_db):
    conn = readonly_connection(sample_db)
    try:
        schema = inspect_schema(conn)
    finally:
        conn.close()
    assert schema.tables["Artist"].columns[0].primary_key
    assert schema.tables["Album"].foreign_keys[0].to_table == "Artist"
    assert "ArtistId" in [column.name for column in schema.tables["Artist"].columns]


def test_missing_database_is_helpful(tmp_path):
    with pytest.raises(DatabaseError, match="missing"):
        readonly_connection(tmp_path / "absent.sqlite")


def test_database_integrity_and_expected_tables(sample_db):
    with pytest.raises(DatabaseError, match="Chinook verification"):
        validate_database(sample_db, require_chinook=True)


def test_invalid_table_and_column_errors_are_read_only(sample_db):
    from tools.query_executor import QueryExecutionError, execute_query
    with pytest.raises(QueryExecutionError, match="no such table"):
        execute_query(sample_db, "SELECT * FROM MissingTable")
    with pytest.raises(QueryExecutionError, match="no such column"):
        execute_query(sample_db, "SELECT MissingColumn FROM Artist")


def test_query_timeout_interrupts_long_running_cte(sample_db):
    from tools.query_executor import QueryExecutionError, execute_query
    sql = "WITH RECURSIVE counter(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM counter WHERE n < 1000000000) SELECT sum(n) FROM counter"
    with pytest.raises(QueryExecutionError, match="time limit"):
        execute_query(sample_db, sql, timeout_seconds=0.000001)


def test_parameterized_query(sample_db):
    from tools.query_executor import execute_query
    result = execute_query(sample_db, "SELECT Name FROM Artist WHERE Name = ?", params=("Example",))
    assert result.dataframe.iloc[0, 0] == "Example"
