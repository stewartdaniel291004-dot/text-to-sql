from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

_LOCK = Lock()


def _redact(text: str, limit: int) -> str:
    text = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED]", text)
    text = re.sub(r"(?i)(OPENAI_API_KEY\s*[=:]\s*)\S+", r"\1[REDACTED]", text)
    return text[:limit]


class QueryHistory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict]:
        with _LOCK:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except (OSError, json.JSONDecodeError):
                return []

    def add(self, question: str, sql: str, status: str, attempts: int, *, database_label: str) -> None:
        rows = self.load()
        rows.insert(0, {"id": uuid4().hex, "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "question": _redact(question, 1000), "sql": _redact(sql, 10000), "status": status, "attempts": int(attempts), "database": _redact(database_label, 60), "favorite": False})
        with _LOCK:
            self.path.write_text(json.dumps(rows[:100], indent=2, ensure_ascii=False), encoding="utf-8")

    def update_favorite(self, item_id: str, value: bool) -> None:
        rows = self.load()
        for item in rows:
            if item.get("id") == item_id:
                item["favorite"] = bool(value)
        with _LOCK:
            self.path.write_text(json.dumps(rows[:100], indent=2, ensure_ascii=False), encoding="utf-8")

    def clear(self) -> None:
        with _LOCK:
            self.path.write_text("[]", encoding="utf-8")
