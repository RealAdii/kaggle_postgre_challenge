# Compile sparse JSONB position expansion inside the execution engine

## Method

The candidate recognizes a narrow lateral VALUES pattern and filters declared
positions before extracting the remaining fields. Positions, aliases, and field
names are derived from the submitted SQL. CASE expressions preserve the original
field mapping. Unsupported SQL is left unchanged.

All official benchmark recipe files and the generator are unchanged. The
compiler runs inside measured batch preparation after the original recipe passes
validation. Version metadata retains the original recipe for traceability and
replay. Existing counter updates, locks, manifests, transactions, and version
registration remain in place.

## Preliminary measurements

An unchanged official generator produced 100,000 source records on PostgreSQL
17.11, Linux aarch64 in Docker. Four alternating comparisons of the child table
SQL statement produced a baseline median of 6,068.716 ms and candidate median
of 4,659.794 ms. This is 23.2 percent less time for that statement. The candidate
was faster in all four pairs. Exact multiset comparison confirmed the same
232,386 child records apart from generated child identities.

The real service path over SSH was measured against all six recipes at 100,000
source records. Under the challenge `MEASURED PROCESSING TOTAL` calculation,
baseline time was 9.275003 seconds and candidate time was 8.087493 seconds, a
12.8 percent reduction. Both runs inserted 532,416 rows, produced the same
destination row counts, and registered all six versions.

At 500,000 source records, the focused table2 query produced 1,160,806 rows per
pass. Four alternating pairs measured a 25,637.044 ms baseline median and a
25,185.330 ms candidate median, a 1.8 percent reduction for that SQL statement.
Exact multiset comparison passed. A 500,000 row full service run was not
completed because local Docker checkpoint synchronization was unusually slow.

Ten tests passed, including unchanged official file checks and randomized
sparse, null, whitespace, and rounding boundary fixtures.

Current evidence is in `benchmarks/results/engine-hotspot-100k.json`,
`benchmarks/results/engine-hotspot-500k.json`, and
`benchmarks/results/engine-application-comparison-100k.json`. Earlier reports
without the engine prefix describe superseded recipe editing experiments.

## Limits

These are local development results, not organizer scores. The Windows
graphical client, final GUI refresh, peak memory, and temporary storage still
need verification. Persistent checkpoint and resume are not implemented.

## Reproduction and status

See `benchmarks/README.md` for setup and commands. The upstream base is
`5dfde9d967425982229b92d6ffe98efcd74612e9`.

This is a local draft. The public repository URL and exact submission commit
must be added before the Kaggle Writeup is published. No organizer score, prize,
or leaderboard placement is claimed.
