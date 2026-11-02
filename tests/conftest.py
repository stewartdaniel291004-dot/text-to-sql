import sqlite3

import pytest


@pytest.fixture
def sample_db(tmp_path):
    path = tmp_path / "sample.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE Artist (ArtistId INTEGER PRIMARY KEY, Name TEXT NOT NULL);
        CREATE TABLE Album (AlbumId INTEGER PRIMARY KEY, Title TEXT, ArtistId INTEGER REFERENCES Artist(ArtistId));
        INSERT INTO Artist VALUES (1, 'Example');
        INSERT INTO Album VALUES (1, 'Record', 1);
    """)
    conn.commit()
    conn.close()
    return path
