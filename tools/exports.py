from __future__ import annotations

import re

import pandas as pd


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def sql_filename(question: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", question.casefold()).strip("-")[:48]
    return f"{slug or 'query'}.sql"


def csv_filename(question: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", question.casefold()).strip("-")[:48]
    return f"{slug or 'query'}-results.csv"
