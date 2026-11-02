import pandas as pd

from tools.exports import csv_bytes, csv_filename, sql_filename
from tools.query_executor import execute_query
from tools.visualization import make_chart
from agents.result_summarizer import summarize_results


def test_execution_returns_rows_and_limits(sample_db):
    result = execute_query(sample_db, "SELECT Name FROM Artist", max_rows=1)
    assert list(result.dataframe.columns) == ["Name"]
    assert result.dataframe.iloc[0, 0] == "Example"
    assert not result.truncated


def test_empty_results_are_successful(sample_db):
    result = execute_query(sample_db, "SELECT Name FROM Artist WHERE ArtistId = 999")
    assert result.dataframe.empty
    assert list(result.dataframe.columns) == ["Name"]


def test_result_row_limit(sample_db):
    result = execute_query(sample_db, "SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3", max_rows=2)
    assert len(result.dataframe) == 2
    assert result.truncated


def test_chart_requires_numeric_value_column():
    frame = pd.DataFrame({"label": ["a", "b"], "value": [1, 2]})
    figure = make_chart(frame, "Bar", "label", "value")
    assert len(figure.data) == 1


def test_csv_export_and_filenames():
    data = csv_bytes(pd.DataFrame({"name": ["A"]}))
    assert data.startswith(b"\xef\xbb\xbf")
    assert b"name" in data and b"A" in data
    assert csv_filename("Monthly revenue!").endswith("-results.csv")
    assert sql_filename("List artists").endswith(".sql")


def test_summary_uses_only_supplied_rows(monkeypatch):
    import agents.result_summarizer as summarizer
    captured = {}
    def fake_response(_client, _model, _system, payload):
        captured.update(payload)
        return {"summary": "The returned row is Example."}
    monkeypatch.setattr(summarizer, "_json_response", fake_response)
    answer = summarize_results("List artist", pd.DataFrame({"Name": ["Example"]}), api_key="test", model="test")
    assert answer == "The returned row is Example."
    assert captured["sample_rows"] == [{"Name": "Example"}]
