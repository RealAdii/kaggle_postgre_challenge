"""Paired table2 comparison with the same populated parent tables and statistics."""

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_recipes import ROOT, UPSTREAM, recipes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--rows", type=int, default=100000)
    args = parser.parse_args()
    variants = {v: recipes(v)[-1]["statements"][0] for v in ("baseline", "candidate")}
    rows = []
    with psycopg.connect(
        "host=127.0.0.1 port=15439 user=challenge dbname=kaggle_challenge",
        autocommit=True, application_name="kaggle-hotspot-benchmark",
    ) as conn:
        # Other recipes are unchanged. Reuse populated parents; fresh statistics
        # are fixed for both variants throughout this focused experiment.
        if conn.execute("SELECT count(*) FROM public.table1").fetchone()[0] == 0:
            with conn.transaction():
                for destination in recipes("baseline")[:-1]:
                    conn.execute(destination["statements"][0])
        assert conn.execute("SELECT count(*) FROM public.table1").fetchone()[0] == args.rows
        for table in ["raw_data", "table1", "table3", "table4"]:
            conn.execute(f"ANALYZE public.{table}")
        for pair in range(args.pairs):
            for variant in (["baseline", "candidate"] if pair % 2 == 0 else ["candidate", "baseline"]):
                conn.execute("TRUNCATE public.table2 RESTART IDENTITY")
                plan = conn.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + variants[variant]).fetchone()[0][0]
                count = conn.execute("SELECT count(*) FROM public.table2").fetchone()[0]
                result = {"pair": pair, "variant": variant,
                          "execution_ms": plan["Execution Time"], "rows": count}
                rows.append(result)
                print(json.dumps(result), flush=True)
                if pair == 0 and variant == "baseline":
                    conn.execute("CREATE TEMP TABLE expected AS SELECT to_jsonb(t) - 'id_column_1' AS value FROM public.table2 t")
                if pair == 0 and variant == "candidate":
                    conn.execute("SET work_mem='128MB'")
                    mismatch = conn.execute("""SELECT EXISTS (
                        (SELECT value FROM expected EXCEPT ALL
                         SELECT to_jsonb(t) - 'id_column_1' FROM public.table2 t)
                        UNION ALL
                        (SELECT to_jsonb(t) - 'id_column_1' FROM public.table2 t
                         EXCEPT ALL SELECT value FROM expected)
                    )""").fetchone()[0]
                    conn.execute("RESET work_mem")
                    assert not mismatch, "Candidate outputs differ"
                    conn.execute("DROP TABLE expected")
                    print("Exact multiset comparison passed", flush=True)
        medians = {v: statistics.median(r["execution_ms"] for r in rows if r["variant"] == v)
                   for v in variants}
        report = {
            "upstream_commit": UPSTREAM, "raw_rows": args.rows,
            "generator_sha256": hashlib.sha256((ROOT / "generate_database.py").read_bytes()).hexdigest(),
            "candidate_sha256": hashlib.sha256((ROOT / "SQL files/06_table2.sql").read_bytes()).hexdigest(),
            "engine_sha256": hashlib.sha256((ROOT / "services/expansion_optimizer.py").read_bytes()).hexdigest(),
            "official_recipes_unchanged": True,
            "metric": "PostgreSQL EXPLAIN ANALYZE execution time for table2 only",
            "complete_application_processing_total": False,
            "exact_multiset_comparison": "passed, all columns except generated table2 identity",
            "median_ms": medians, "speedup": medians["baseline"] / medians["candidate"],
            "runs": rows,
        }
        path = ROOT / f"benchmarks/results/engine-hotspot-{args.rows // 1000}k.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
