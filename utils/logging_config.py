from __future__ import annotations

import logging
import re
from pathlib import Path


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        message = re.sub(r"(?i)(sk-[A-Za-z0-9_-]{12,}|OPENAI_API_KEY\s*[=:]\s*\S+)", "[REDACTED]", message)
        record.msg, record.args = message, ()
        return True


def configure_logging(path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("text_to_sql")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(target, encoding="utf-8")
        handler.addFilter(SecretRedactionFilter())
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
