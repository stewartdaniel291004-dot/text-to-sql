from __future__ import annotations

import argparse
import sqlite3
import urllib.request
from pathlib import Path
from urllib.parse import quote

SOURCE_URL = "https://github.com/lerocha/chinook-database/releases/download/v1.4.5/Chinook_Sqlite.sqlite"
EXPECTED_TABLES = {"Artist", "Album", "Track", "Genre", "MediaType", "Playlist", "Customer", "Invoice", "InvoiceLine", "Employee"}


def setup_database(destination: str | Path) -> Path:
    path = Path(destination).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".download")
    try:
        request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "text-to-sql-agent-setup/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response, temp.open("wb") as out:
            if response.status != 200:
                raise RuntimeError(f"Chinook download returned HTTP {response.status}.")
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        conn = sqlite3.connect(f"file:{quote(temp.resolve().as_posix(), safe='/')}?mode=ro", uri=True)
        try:
            integrity = conn.execute("PRAGMA quick_check").fetchone()
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if not integrity or integrity[0] != "ok" or not EXPECTED_TABLES.issubset(tables):
                raise RuntimeError("Downloaded file failed Chinook integrity or expected-table validation.")
        finally:
            conn.close()
        temp.replace(path)
        return path
    except Exception as exc:
        temp.unlink(missing_ok=True)
        raise RuntimeError("Could not set up Chinook. Check network access, then rerun: py -3.11 database/setup_database.py") from exc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and verify the official Chinook SQLite sample database.")
    parser.add_argument("--output", default="data/Chinook.sqlite")
    args = parser.parse_args()
    print(f"Verified Chinook database: {setup_database(args.output)}")
