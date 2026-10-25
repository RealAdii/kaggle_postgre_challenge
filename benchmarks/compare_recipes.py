"""Compare SQL recipes on an unchanged official generator database.

This measures the SQL phase, not the complete application processing total.
Run only against a disposable challenge database: destination rows are truncated.
"""

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.postgres_service import PostgresAdminService
from services.expansion_optimizer import optimize_sparse_positions

UPSTREAM = "5dfde9d967425982229b92d6ffe98efcd74612e9"
TABLES = [f"table{i}" for i in range(1, 7)]
FILES = sorted((ROOT / "SQL files").glob("*.sql"))


def recipes(variant):
    destinations = []
    for path in FILES:
        if variant == "baseline":
            sql = subprocess.check_output(
                ["git", "show", f"{UPSTREAM}:{path.relative_to(ROOT)}"],
                cwd=ROOT, text=True,
            )
        else:
            sql = path.read_text()
        destinations.append({
            "table_name": f"public.{path.stem.split('_')[1]}",
            "version_title": "Recipe benchmark",
            "sql": sql,
        })
    result = PostgresAdminService._prepare_cross_table_expansion(
        "public.raw_data", ["group001"], destinations,
    )["destinations"]
    if variant == "candidate":
        for destination in result:
            destination["statements"] = [optimize_sparse_positions(s) for s in destination["statements"]]
    return result


def canonical(table):
    # Generated surrogate identifiers may differ between valid query plans.
    # Compare every other column, resolving references to their natural values.
    if table == "table3":
        return "SELECT to_jsonb(t) - 'id_column_1' AS value FROM public.table3 t"
    if table == "table4":
        return "SELECT to_jsonb(t) AS value FROM public.table4 t"
    if table == "table1":
        return """SELECT (to_jsonb(t) - 'id_column_1' - 'id_column_4') ||
            jsonb_build_object('dimension', to_jsonb(d) - 'id_column_1') AS value
            FROM public.table1 t
            JOIN public.table3 d ON d.id_column_1 = t.id_column_4"""
    return f"""SELECT (to_jsonb(t) - 'id_column_1' - 'id_column_2') ||
        jsonb_build_object('source_raw_id', m.id_column_3) AS value
        FROM public.{table} t
        JOIN public.table1 m ON m.id_column_1 = t.id_column_2"""


def run(conn, variant, prepared):
    conn.execute("TRUNCATE " + ", ".join("public." + t for t in TABLES)
                 + " RESTART IDENTITY CASCADE")
    for table in TABLES:
        conn.execute(f"ANALYZE public.{table}")
    results = []
    with conn.transaction():
        for destination in prepared:
            statement = destination["statements"][0]
            plan = conn.execute(
                "EXPLAIN (ANALYZE, FORMAT JSON) " + statement
            ).fetchone()[0][0]
            results.append({
                "table": destination["table_name"],
                "execution_ms": plan["Execution Time"],
                "planning_ms": plan["Planning Time"],
                "plan": plan,
            })
    counts = {t: conn.execute(f"SELECT count(*) FROM public.{t}").fetchone()[0]
              for t in TABLES}
    return {"variant": variant, "tables": results, "counts": counts,
            "execution_ms": sum(t["execution_ms"] for t in results)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default="host=127.0.0.1 port=15439 user=challenge dbname=kaggle_challenge")
    parser.add_argument("--pairs", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/results/recipes-100k.json")
    args = parser.parse_args()
    prepared = {v: recipes(v) for v in ("baseline", "candidate")}
    generator = ROOT / "generate_database.py"
    upstream_generator = subprocess.check_output(
        ["git", "show", f"{UPSTREAM}:generate_database.py"], cwd=ROOT,
    )
    assert generator.read_bytes() == upstream_generator, "Generator changed"
    runs = []
    with psycopg.connect(args.dsn, autocommit=True,
                         application_name="kaggle-recipe-benchmark") as conn:
        raw_count = conn.execute("SELECT count(*) FROM public.raw_data").fetchone()[0]
        version = conn.execute("SELECT version()").fetchone()[0]
        for pair in range(args.pairs):
            order = ["baseline", "candidate"] if pair % 2 == 0 else ["candidate", "baseline"]
            for variant in order:
                result = run(conn, variant, prepared[variant])
                result["pair"] = pair
                runs.append(result)
                print(json.dumps(result), flush=True)
                # Verification needs fresh statistics on the newly filled tables.
                # This runs after timing and is not part of either recipe variant.
                if pair == 0:
                    for table in TABLES:
                        conn.execute(f"ANALYZE public.{table}")
                if pair == 0 and variant == "baseline":
                    for table in TABLES:
                        conn.execute(f"CREATE TEMP TABLE reference_{table} AS " + canonical(table))
                if pair == 0 and variant == "candidate":
                    for table in TABLES:
                        query = canonical(table)
                        mismatch = conn.execute(f"""SELECT EXISTS (
                            (SELECT value FROM reference_{table} EXCEPT ALL {query})
                            UNION ALL
                            ({query} EXCEPT ALL SELECT value FROM reference_{table})
                        )""").fetchone()[0]
                        assert not mismatch, f"Output mismatch in {table}"
                        print(f"Exact multiset comparison passed: {table}", flush=True)
                    for table in TABLES:
                        conn.execute(f"DROP TABLE reference_{table}")
        medians = {v: statistics.median(r["execution_ms"] for r in runs if r["variant"] == v)
                   for v in prepared}
        report = {
            "upstream_commit": UPSTREAM, "postgresql": version,
            "raw_rows": raw_count,
            "generator_sha256": hashlib.sha256(generator.read_bytes()).hexdigest(),
            "metric": "PostgreSQL EXPLAIN ANALYZE execution time, six recipe statements only",
            "complete_application_processing_total": False,
            "exact_canonical_multiset_comparison": "passed for all six tables",
            "median_ms": medians,
            "speedup": medians["baseline"] / medians["candidate"],
            "runs": runs,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "runs"}), flush=True)


if __name__ == "__main__":
    main()
