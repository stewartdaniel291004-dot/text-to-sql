from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    not_null: bool
    primary_key: bool


@dataclass(frozen=True)
class ForeignKeyInfo:
    from_column: str
    to_table: str
    to_column: str


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: tuple[ColumnInfo, ...]
    foreign_keys: tuple[ForeignKeyInfo, ...]


@dataclass(frozen=True)
class SchemaInfo:
    tables: dict[str, TableInfo]

    def to_dict(self) -> dict:
        return {name: {"columns": [asdict(c) for c in table.columns], "foreign_keys": [asdict(f) for f in table.foreign_keys]} for name, table in self.tables.items()}

    def as_prompt(self, query: str = "") -> str:
        # Include full schema; never choose or fabricate identifiers from model memory.
        return "\n".join(
            f"{name}({', '.join(c.name + ':' + (c.data_type or 'ANY') + (' [PK]' if c.primary_key else '') for c in t.columns)})"
            + (" REFERENCES " + ", ".join(f"{f.from_column}->{f.to_table}.{f.to_column}" for f in t.foreign_keys) if t.foreign_keys else "")
            for name, t in self.tables.items()
        )

    def search(self, text: str) -> list[tuple[str, str]]:
        needle = text.casefold().strip()
        return [(table.name, column.name) for table in self.tables.values() for column in table.columns if needle in table.name.casefold() or needle in column.name.casefold()]


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def inspect_schema(conn: sqlite3.Connection) -> SchemaInfo:
    names = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    tables: dict[str, TableInfo] = {}
    for row in names:
        name = row[0]
        columns = tuple(ColumnInfo(c[1], c[2] or "", bool(c[3]), bool(c[5])) for c in conn.execute(f"PRAGMA table_info({_quote_identifier(name)})"))
        foreign_keys = tuple(ForeignKeyInfo(f[3], f[2], f[4]) for f in conn.execute(f"PRAGMA foreign_key_list({_quote_identifier(name)})"))
        tables[name] = TableInfo(name, columns, foreign_keys)
    return SchemaInfo(tables)
