# PostgreSQL challenge experiments

The current candidate optimizes SQL inside the execution engine. All six
official SQL recipe files, the generator, and its seed remain byte-for-byte
identical to upstream commit 5dfde9d967425982229b92d6ffe98efcd74612e9.

## Method

`services/expansion_optimizer.py` recognizes a narrow lateral VALUES pattern.
It derives the positions, aliases, and JSON field names from the input SQL,
filters absent positions first, and extracts the remaining fields with CASE
expressions. Unsupported SQL remains unchanged. No source records, expected
answers, or benchmark identifiers are recognized.

The original SQL goes through the existing source, destination, function,
and dependency validation. Compilation runs within the measured SQL-batch
preparation scope. Version metadata preserves the original recipe. Managed
counters, locks, manifests, and registration remain unchanged.

## Reproduction

Use a disposable database. The scripts truncate the destination tables.
The container account and trust authentication are for loopback-only local use.

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt -r benchmarks/requirements.txt
docker build -f benchmarks/Dockerfile -t kaggle-postgres-local .
docker run -d --name kaggle-postgres-bench -p 127.0.0.1:15439:5432 \
  -e POSTGRES_HOST_AUTH_METHOD=trust kaggle-postgres-local
docker exec kaggle-postgres-bench pg_isready -d postgres -U postgres
docker exec kaggle-postgres-bench psql -U postgres \
  -c 'CREATE ROLE challenge LOGIN CREATEDB'
PATH=/opt/homebrew/opt/libpq/bin:$PATH .venv/bin/python generate_database.py \
  --rows 100000 --host 127.0.0.1 --postgres_port 15439 \
  --user challenge --admin_database postgres
RECIPE_TEST_DSN='host=127.0.0.1 port=15439 user=challenge dbname=kaggle_challenge' \
  .venv/bin/python -m pytest -q
.venv/bin/python benchmarks/compare_recipes.py --pairs 1
.venv/bin/python benchmarks/compare_hotspot.py --pairs 4
.venv/bin/python benchmarks/run_application.py --variant candidate
.venv/bin/python benchmarks/verify_rollback.py
```

After generating a different workload, pass its row count to the focused SQL
benchmark. For example, `--rows 500000` writes a separate 500k result file.

Wait for `pg_isready` to succeed before connecting. On other platforms put the
PostgreSQL client on PATH using its local installation. Run the benchmarks
sequentially. After use, run `docker stop --time 120 kaggle-postgres-bench`
so PostgreSQL has time to checkpoint cleanly.

The service runner uses a real SSH session over a Docker stdio transport. It
checks normal preflight validation, managed inserts, counters, manifests, and
all six version registrations. It does not exercise Windows GUI refresh.

## Current evidence

Ten tests passed, including exact equivalence on sparse and boundary fixtures
and a check that official recipes and generator are unchanged.

At 100,000 source rows, four alternating hot-path pairs gave a median of
6,068.716 ms for the original statement and 4,659.794 ms for the compiled
statement. This is 23.2 percent less time for table2 only. All four pairs favored
the compiler. An exact multiset comparison verified 232,386 identical child
records, excluding generated child identities. See
`results/engine-hotspot-100k.json` for all pairs and hashes.

At 500,000 source rows, the focused table2 benchmark produced 1,160,806 child
rows per pass. Four alternating pairs gave a 25,637.044 ms baseline median and
a 25,185.330 ms candidate median, a 1.8 percent reduction. Exact multiset
comparison passed. This result is limited to table2 and does not establish a
large full application improvement. See `results/engine-hotspot-500k.json`.

The real service path over SSH was measured at 100,000 source rows using the
challenge's `MEASURED PROCESSING TOTAL` calculation. The baseline took 9.275003
seconds and the candidate took 8.087493 seconds, a 12.8 percent reduction.
Both runs inserted 532,416 rows and registered all six destination versions
with matching row counts. See `results/engine-application-comparison-100k.json`
and its baseline and candidate reports.

## Limitations and history

Timing variation was substantial. The 500,000 row full-service trial was not
completed because local Docker checkpoint synchronization was very slow. The
500,000 row table2 result is a focused SQL measurement only. Peak-resource
profiling and a Windows client run remain required. Persistent checkpoint and
resume are not yet implemented.

The earlier recipe-editing candidates and their reports are historical
experiments. They are superseded because the standard benchmark requires the
official SQL files to remain unchanged. Only files beginning `engine-` describe
the current compiler candidate. The original recipes have been restored.

No public competition submission has been published from this checkout.
