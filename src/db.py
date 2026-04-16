from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from config import get_settings


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """
    Tiny DB helper for the MVP.
    For higher throughput, swap to a pool (psycopg_pool) later.
    """
    settings = get_settings()
    conn = psycopg.connect(settings.database_url, autocommit=True, row_factory=dict_row)
    try:
        if settings.use_pgvector:
            try:
                from pgvector.psycopg import register_vector

                register_vector(conn)
            except Exception:
                # pgvector extension or adapter may be unavailable; callers can fall back.
                pass
        yield conn
    finally:
        conn.close()

