# Faster sparse position expansion for JSONB records

## Summary

The official expansion recipe enumerates 14 possible positions and extracts
several JSON fields for each position before filtering to the positions that
exist in a source record. This candidate compiles a narrow lateral `VALUES`
pattern inside the execution engine. It filters the declared position first,
then extracts the remaining fields for surviving positions.

The compiler derives aliases, positions, and field names from the submitted SQL.
Unsupported SQL passes through unchanged. The original SQL is still validated
and stored in version metadata. The six official SQL files, database generator,
fixed seed, source data, table mapping, counters, locks, transaction handling,
manifests, and version registration were preserved.

## Measurements

The table2 focused benchmark used the unchanged official generator and four
alternating baseline and candidate passes.

| Source rows | Baseline median | Candidate median | Reduction | Scope |
| --- | ---: | ---: | ---: | --- |
| 100,000 | 6,068.716 ms | 4,659.794 ms | 23.2% | table2 statement |
| 500,000 | 25,637.044 ms | 25,185.330 ms | 1.8% | table2 statement |

Exact multiset comparisons passed for the table2 outputs at both sizes, apart
from generated surrogate identifiers. The 500,000 row statement produced
1,160,806 child rows per pass.

At 100,000 source rows, I also measured the real service path over SSH across
all six destination recipes. The challenge `MEASURED PROCESSING TOTAL` was
9.275003 seconds for baseline and 8.087493 seconds for the candidate, a 12.8%
reduction. Both runs inserted 532,416 rows, produced identical destination row
counts, and registered all six versions. The service test ran on PostgreSQL
17.11 in a Linux aarch64 Docker container, controlled by the macOS headless
service over an SSH stdio proxy.

The 500,000 row full-service run was not completed because local Docker
checkpoint synchronization was unusually slow. The 500,000 row result above is
only a focused SQL measurement. The organizer has not reproduced these results.

## Correctness and failure handling

Ten tests passed. They include differential sparse and boundary fixtures,
unsupported SQL fallback, official recipe and generator hash checks, and the
existing rollback checks. Full recipe comparisons confirmed the same six
destination outputs on the 100,000 row benchmark, excluding generated surrogate
identifiers.

An injected late failure rolled back destination rows and managed counters while
retaining the source table. The candidate preserves the existing all-or-nothing
transaction behavior. Persistent checkpoint and resume are not implemented.

## Limitations

The 100,000 row full-service measurement is one local paired observation, not an
organizer score. The 500,000 row SQL improvement is modest. Peak memory and
temporary storage were not profiled. The Windows graphical client and its final
refresh were not tested. Persistent checkpoint and resume remain future work.

## Reproduction

The benchmark scripts, machine-readable reports, and source are in the public
repository below. The submission tag points to the exact code commit used for
the measurements.

Repository: https://github.com/RealAdii/kaggle_postgre_challenge

Submission commit: 56882882e089d545ef9973e4035bc21e53abb452
