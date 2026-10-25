"""Exercise the real service over SSH against the disposable Docker database.

The graphical client is not launched. This includes the original validation,
managed counters, transaction handling, manifest, and version registration.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_recipes import ROOT, TABLES
from services.postgres_service import PostgresAdminService
from ssh_fixture import open_ephemeral_ssh, remove_ephemeral_ssh_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["baseline", "candidate"], default="candidate")
    args = parser.parse_args()
    with psycopg.connect("host=127.0.0.1 port=15439 user=challenge dbname=kaggle_challenge", autocommit=True) as conn:
        raw_rows = conn.execute("SELECT count(*) FROM public.raw_data").fetchone()[0]
        conn.execute("TRUNCATE " + ", ".join("public." + t for t in TABLES) + " RESTART IDENTITY CASCADE")
        for table in TABLES:
            conn.execute(f"ANALYZE public.{table}")
        if conn.execute("SELECT to_regclass('public.pgdm_table_row_counts')").fetchone()[0]:
            conn.execute("UPDATE public.pgdm_table_row_counts SET row_count=0 WHERE schema_name='public' AND table_name=ANY(%s)", (TABLES,))
    client = open_ephemeral_ssh("kaggle-postgres-bench")
    service = PostgresAdminService()
    service.ssh_client = client
    service.sql_username = "challenge"
    service.sql_password = ""
    service.postgres_port = 5432
    destinations = []
    # Keep the source placeholder so the service performs its normal guarding.
    import subprocess
    from compare_recipes import FILES, UPSTREAM
    for path in FILES:
        sql = (subprocess.check_output(["git", "show", f"{UPSTREAM}:{path.relative_to(ROOT)}"], cwd=ROOT, text=True)
               if args.variant == "baseline" else path.read_text())
        destinations.append({"table_name": f"public.{path.stem.split('_')[1]}",
                             "version_title": "Local reproducibility benchmark", "sql": sql})
    try:
        report = service.create_cross_table_expansion_timing_report(
            "kaggle_challenge", "public.raw_data", ["group001"],
            [d["table_name"] for d in destinations],
        )
        result = service.execute_cross_table_expansion(
            "kaggle_challenge", "public.raw_data", ["group001"], destinations,
            timing_report=report,
            progress_callback=lambda *event: print(event, flush=True),
        )
        versions = service.register_cross_table_expansion_versions(
            result, requested_by="local-benchmark", workstation_name="disposable-docker",
            timing_report=report,
        )
        path = ROOT / f"benchmarks/results/engine-application-{args.variant}-{raw_rows // 1000}k.json"
        path.write_text(json.dumps({"variant": args.variant,
                                   "raw_rows": raw_rows,
                                   "recipe_sha256": {d["table_name"]: hashlib.sha256(d["sql"].encode()).hexdigest() for d in destinations},
                                   "engine_sha256": hashlib.sha256((ROOT / "services/expansion_optimizer.py").read_bytes()).hexdigest(),
                                   "client": "macOS headless service via SSH stdio proxy",
                                   "windows_gui_verified": False,
                                   "timing_report": report, "versions": versions}, indent=2, default=str) + "\n")
        print(f"Saved {path}", flush=True)
    finally:
        service.close()
        remove_ephemeral_ssh_key("kaggle-postgres-bench")


if __name__ == "__main__":
    main()
