from agents.sql_generator import SQLProposal
from agents.workflow import run_workflow
from database.db_manager import readonly_connection
from tools.schema_inspector import inspect_schema


def test_missing_api_key_does_not_fake_a_response(sample_db):
    conn = readonly_connection(sample_db)
    schema = inspect_schema(conn)
    conn.close()
    result = run_workflow("List artists", sample_db, schema, api_key=None, model="test")
    assert result.status == "unavailable"
    assert not result.sql


def test_api_failure_is_reported_without_fake_sql(sample_db, monkeypatch):
    import agents.workflow as workflow
    from agents.sql_generator import AIUnavailable
    conn = readonly_connection(sample_db)
    schema = inspect_schema(conn)
    conn.close()
    monkeypatch.setattr(workflow, "generate_sql", lambda *a, **k: (_ for _ in ()).throw(AIUnavailable("service unavailable")))
    result = run_workflow("List artists", sample_db, schema, api_key="test", model="test")
    assert result.status == "unavailable"
    assert not result.sql


def test_recoverable_error_is_corrected_and_revalidated(sample_db, monkeypatch):
    import agents.workflow as workflow
    conn = readonly_connection(sample_db)
    schema = inspect_schema(conn)
    conn.close()
    proposals = iter([SQLProposal("SELECT Missing FROM Artist", "first"), SQLProposal("SELECT Name FROM Artist", "fixed")])
    monkeypatch.setattr(workflow, "generate_sql", lambda *a, **k: next(proposals))
    monkeypatch.setattr(workflow, "correct_sql", lambda *a, **k: next(proposals))
    monkeypatch.setattr(workflow, "explain_sql", lambda *a, **k: "Selects artist names.")
    monkeypatch.setattr(workflow, "summarize_results", lambda *a, **k: "One artist was returned.")
    result = run_workflow("List artists", sample_db, schema, api_key="test", model="test", max_corrections=3)
    assert result.status == "success"
    assert result.correction_attempts == 1
    assert result.sql == "SELECT Name FROM Artist"
    assert "SQL validation passed" in result.activity


def test_policy_error_is_not_corrected(sample_db, monkeypatch):
    import agents.workflow as workflow
    conn = readonly_connection(sample_db)
    schema = inspect_schema(conn)
    conn.close()
    monkeypatch.setattr(workflow, "generate_sql", lambda *a, **k: SQLProposal("DELETE FROM Artist", "unsafe"))
    monkeypatch.setattr(workflow, "correct_sql", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not retry")))
    result = run_workflow("delete all", sample_db, schema, api_key="test", model="test")
    assert result.status == "rejected"
    assert result.correction_attempts == 0


def test_correction_limit_is_enforced(sample_db, monkeypatch):
    import agents.workflow as workflow
    conn = readonly_connection(sample_db)
    schema = inspect_schema(conn)
    conn.close()
    monkeypatch.setattr(workflow, "generate_sql", lambda *a, **k: SQLProposal("SELECT Missing FROM Artist", "bad"))
    attempts = []
    def correction(*a, **k):
        attempts.append(1)
        return SQLProposal("SELECT AlsoMissing FROM Artist", "still bad")
    monkeypatch.setattr(workflow, "correct_sql", correction)
    result = run_workflow("List artists", sample_db, schema, api_key="test", model="test", max_corrections=3)
    assert result.status == "failed"
    assert result.correction_attempts == 3
    assert len(attempts) == 3
