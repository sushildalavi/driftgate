from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from psycopg2 import errors
from psycopg2.extensions import parse_dsn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply runtime SQL migrations.")
    parser.add_argument(
        "--dsn",
        default=os.getenv("DATABASE_URL_SYNC", "postgresql://driftgate:dev@localhost:55433/driftgate_runtime"),
        help="PostgreSQL DSN for sync psycopg2 connection.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))
    dsn_map = parse_dsn(args.dsn)
    target_db = dsn_map.get("dbname")
    bootstrap_dsn = " ".join(
        f"{k}={v}" for k, v in dsn_map.items() if k != "dbname"
    ) + " dbname=postgres"

    admin_conn = psycopg2.connect(bootstrap_dsn)
    admin_conn.set_session(autocommit=True)
    try:
        with admin_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{target_db}"')
                print(f"created database {target_db}")
    finally:
        admin_conn.close()

    with psycopg2.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conn.commit()

            for file in files:
                cur.execute(
                    "SELECT 1 FROM runtime_schema_migrations WHERE filename = %s",
                    (file.name,),
                )
                if cur.fetchone():
                    continue
                sql = file.read_text()
                try:
                    cur.execute(sql)
                except (errors.DuplicateObject, errors.DuplicateTable):
                    conn.rollback()
                    print(f"skipped {file.name} (already applied objects present)")
                    cur.execute(
                        "INSERT INTO runtime_schema_migrations(filename) VALUES (%s) ON CONFLICT DO NOTHING",
                        (file.name,),
                    )
                    conn.commit()
                    continue
                cur.execute(
                    "INSERT INTO runtime_schema_migrations(filename) VALUES (%s)",
                    (file.name,),
                )
                conn.commit()
                print(f"applied {file.name}")


if __name__ == "__main__":
    main()
