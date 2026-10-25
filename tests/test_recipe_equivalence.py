"""Optional database checks using isolated temporary fixture tables."""

import os
import random
import subprocess
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb
from services.expansion_optimizer import optimize_sparse_positions

ROOT = Path(__file__).resolve().parents[1]
DSN = os.getenv("RECIPE_TEST_DSN")
UPSTREAM = "5dfde9d967425982229b92d6ffe98efcd74612e9"


@pytest.mark.skipif(not DSN, reason="Set RECIPE_TEST_DSN to a disposable PostgreSQL database")
def test_child_recipe_matches_on_sparse_and_boundary_values():
    path = "SQL files/06_table2.sql"
    baseline = subprocess.check_output(["git", "show", f"{UPSTREAM}:{path}"], cwd=ROOT, text=True)
    candidate = optimize_sparse_positions((ROOT / path).read_text())
    assert candidate != baseline

    def select(sql):
        return sql[sql.index("\nSELECT\n"):].rstrip().rstrip(";").replace(
            "{{source}}", "pg_temp.fixture_raw"
        ).replace("public.table1", "pg_temp.fixture_main")

    rng = random.Random(42017)
    fixtures = [{}, {"values": None}, {"values": {}}, {"values": "scalar"}]
    for index in range(120):
        values = {}
        for position in range(1, 15):
            if rng.random() < 0.4:
                values[f"integer_column_{position + 1}"] = rng.choice(
                    [str(position), f" {position} ", "", None, "0"]
                )
                values[f"text_column_{position + 3}"] = rng.choice(
                    ["X", " y ", "z", "invalid", "", None]
                )
                values[f"numeric_column_{2 * position + 1}"] = rng.choice(
                    ["0", "0.0005", " 3.125 ", "-1", "1e2", "", None]
                )
                values[f"numeric_column_{2 * position + 2}"] = rng.choice(
                    ["-1", "0", "0.0005", "3.125", "", None]
                )
        fixtures.append({"values": values})
    # Explicitly exercise the final position and decimal rounding boundaries.
    fixtures.append({"values": {"integer_column_15": "14", "text_column_17": " X ",
                                 "numeric_column_29": "0.0005", "numeric_column_30": "0.0015"}})
    with psycopg.connect(DSN) as conn:
        conn.execute("CREATE TEMP TABLE fixture_raw(raw_id bigint, raw jsonb)")
        conn.execute("CREATE TEMP TABLE fixture_main(id_column_1 bigint, id_column_3 bigint)")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO fixture_raw VALUES (%s,%s)",
                            [(i, Jsonb(payload)) for i, payload in enumerate(fixtures)])
            cur.executemany("INSERT INTO fixture_main VALUES (%s,%s)",
                            [(1000 + i, i) for i in range(len(fixtures))])
        original = conn.execute(select(baseline)).fetchall()
        optimized = conn.execute(select(candidate)).fetchall()
        from collections import Counter
        assert Counter(original) == Counter(optimized)
        assert any(row[1] == 14 and row[2] == 1 and row[-1] == 2 for row in optimized)


def test_compiler_leaves_unsupported_sql_unchanged():
    sql = "INSERT INTO public.target SELECT x FROM public.source"
    assert optimize_sparse_positions(sql) == sql


def test_official_recipes_and_generator_are_unchanged():
    for path in ["generate_database.py", *[str(p.relative_to(ROOT)) for p in (ROOT / "SQL files").glob("*.sql")]]:
        original = subprocess.check_output(["git", "show", f"{UPSTREAM}:{path}"], cwd=ROOT)
        assert (ROOT / path).read_bytes() == original, path


def test_compiler_only_rewrites_supported_conjunctive_guard():
    sql = (ROOT / "SQL files/06_table2.sql").read_text()
    assert optimize_sparse_positions(sql) != sql
    disjunctive = sql.rstrip().rstrip(";") + " OR true;"
    assert optimize_sparse_positions(disjunctive) == disjunctive
    for path in (ROOT / "SQL files").glob("*.sql"):
        if path.name != "06_table2.sql":
            original = path.read_text()
            assert optimize_sparse_positions(original) == original
