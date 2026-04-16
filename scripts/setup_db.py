from __future__ import annotations

import argparse
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Apply sql/schema.sql to DATABASE_URL")
    p.add_argument(
        "--database-url",
        default=None,
        help="Overrides DATABASE_URL env var (optional)",
    )
    args = p.parse_args()

    database_url = args.database_url
    if not database_url:
        import os

        database_url = os.getenv("DATABASE_URL", "")

    if not database_url:
        raise SystemExit("DATABASE_URL is required (env var or --database-url).")

    schema_path = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(sql)

    print(f"Applied schema: {schema_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

