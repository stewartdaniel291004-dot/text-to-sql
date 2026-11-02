import pytest

from tools.sql_validator import SQLPolicyError, validate_sql


@pytest.mark.parametrize("sql", ["SELECT 1", "WITH x AS (SELECT 1 AS n) SELECT n FROM x", "SELECT Name FROM Artist WHERE ArtistId = ?", "SELECT 1 UNION ALL SELECT 2"])
def test_accepts_readonly_selects(sql):
    assert validate_sql(sql).upper().startswith(("SELECT", "WITH"))


@pytest.mark.parametrize("sql", [
    "INSERT INTO Artist VALUES (2, 'x')", "UPDATE Artist SET Name='x'", "DELETE FROM Artist", "DROP TABLE Artist",
    "ALTER TABLE Artist ADD COLUMN x INT", "CREATE TABLE evil (x INT)", "REPLACE INTO Artist VALUES (2,'x')",
    "ATTACH DATABASE 'x' AS y", "DETACH DATABASE y", "VACUUM", "PRAGMA table_info(Artist)",
    "BEGIN", "COMMIT", "SELECT 1; DROP TABLE Artist", "SELECT 1; SELECT 2",
    "SELECT load_extension('evil')", "SELECT readfile('/secret')", "SELECT * FROM sqlite_master",
])
def test_rejects_destructive_or_unsafe_statements(sql):
    with pytest.raises(SQLPolicyError):
        validate_sql(sql)


def test_rejects_injection_and_trailing_payload():
    with pytest.raises(SQLPolicyError):
        validate_sql("SELECT 1 WHERE 1=1; -- ; DROP TABLE Artist")


def test_rejects_non_select_root():
    with pytest.raises(SQLPolicyError):
        validate_sql("EXPLAIN SELECT 1")
