from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(value, high))


def _float_env(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(value, high))


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    database_path: Path = ROOT / os.getenv("DATABASE_PATH", "data/Chinook.sqlite")
    model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    max_rows: int = _int_env("MAX_RESULT_ROWS", 1000, 1, 10000)
    timeout_seconds: float = _float_env("QUERY_TIMEOUT_SECONDS", 5.0, 0.1, 60.0)
    max_corrections: int = _int_env("MAX_CORRECTION_ATTEMPTS", 3, 0, 3)
    api_key: str | None = (os.getenv("OPENAI_API_KEY") or "").strip() or None


settings = Settings()
