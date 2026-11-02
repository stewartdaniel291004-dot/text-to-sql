from utils.query_history import QueryHistory


def test_history_stores_status_favorites_and_reuse_data(tmp_path):
    history = QueryHistory(tmp_path / "history.json")
    history.add("List artists", "SELECT Name FROM Artist", "success", 0, database_label="sample")
    first = history.load()[0]
    assert first["question"] == "List artists"
    assert first["status"] == "success"
    history.update_favorite(first["id"], True)
    assert history.load()[0]["favorite"] is True
    history.clear()
    assert history.load() == []
