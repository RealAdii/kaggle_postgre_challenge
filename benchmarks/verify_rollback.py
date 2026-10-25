"""Inject a late SQL failure and verify that all managed inserts roll back."""

import json
import hashlib
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_recipes import FILES, ROOT, TABLES
from services.postgres_service import PostgresAdminService
from ssh_fixture import open_ephemeral_ssh, remove_ephemeral_ssh_key


def main():
    dsn = "host=127.0.0.1 port=15439 user=challenge dbname=kaggle_challenge"
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("TRUNCATE " + ", ".join("public." + t for t in TABLES) + " RESTART IDENTITY CASCADE")
        conn.execute("UPDATE public.pgdm_table_row_counts SET row_count=0 WHERE schema_name='public' AND table_name=ANY(%s)", (TABLES,))
    client = open_ephemeral_ssh("kaggle-postgres-bench")
    service = PostgresAdminService()
    service.ssh_client = client
    service.sql_username = "challenge"
    service.sql_password = ""
    service.postgres_port = 5432
    destinations = [{"table_name": f"public.{p.stem.split('_')[1]}",
                     "version_title": "Deliberate rollback test", "sql": p.read_text()}
                    for p in FILES]
    destinations[-1]["sql"] = destinations[-1]["sql"].replace(
        "::numeric * 1000", "::numeric / 0", 1,
    )
    try:
        try:
            service.execute_cross_table_expansion(
                "kaggle_challenge", "public.raw_data", ["group001"], destinations,
            )
        except RuntimeError as error:
            assert "division by zero" in str(error), str(error)
        else:
            raise AssertionError("Injected failure did not occur")
        with psycopg.connect(dsn) as conn:
            counts = {t: conn.execute(f"SELECT count(*) FROM public.{t}").fetchone()[0] for t in TABLES}
            counters = dict(conn.execute("SELECT table_name,row_count FROM public.pgdm_table_row_counts WHERE schema_name='public' AND table_name=ANY(%s)", (TABLES,)).fetchall())
            assert all(value == 0 for value in counts.values()), counts
            assert set(counters) == set(TABLES) and all(value == 0 for value in counters.values()), counters
            assert conn.execute("SELECT count(*) FROM public.raw_data").fetchone()[0] == 100000
        result = {"late_failure": "division by zero in final destination",
                  "engine_sha256": hashlib.sha256((ROOT / "services/expansion_optimizer.py").read_bytes()).hexdigest(),
                  "destination_counts": counts, "managed_counters": counters,
                  "raw_rows": 100000, "transaction_rollback": "passed"}
        path = ROOT / "benchmarks/results/engine-rollback-100k.json"
        path.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    finally:
        service.close()
        remove_ephemeral_ssh_key("kaggle-postgres-bench")


if __name__ == "__main__":
    main()
