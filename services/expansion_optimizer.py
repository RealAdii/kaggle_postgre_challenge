"""Equivalent SQL rewrites for sparse lateral JSON position expansions.

The original recipe remains the validation and version-history input. This
compiler recognizes a narrow SQL shape and leaves unsupported statements alone.
"""

import re

IDENT = r"[A-Za-z_][A-Za-z_0-9]*"
EXPRESSION = rf"{IDENT}\.raw\s*->\s*'[A-Za-z_0-9]+'\s*->>\s*'[A-Za-z_0-9]+'"
ROW = re.compile(
    rf"\(\s*(\d+)::smallint\s*,\s*({EXPRESSION})\s*,\s*"
    rf"({EXPRESSION})\s*,\s*({EXPRESSION})\s*,\s*({EXPRESSION})\s*\)",
    re.IGNORECASE,
)
LATERAL = re.compile(
    rf"CROSS\s+JOIN\s+LATERAL\s*\(\s*VALUES\s*(.*?)\)\s+AS\s+"
    rf"({IDENT})\s*\(([^)]+)\)", re.IGNORECASE | re.DOTALL,
)
FIELD = re.compile(
    rf"({IDENT})\.raw\s*->\s*'([A-Za-z_0-9]+)'\s*->>\s*'([A-Za-z_0-9]+)'",
    re.IGNORECASE,
)


def optimize_sparse_positions(statement: str) -> str:
    """Filter declared positions before extracting other JSON fields.

    All positions, fields, and aliases come from the submitted SQL. No benchmark
    identifiers, generated data values, or expected outputs are recognized.
    """
    if "_pgdm_payload" in statement or "_pgdm_declared" in statement:
        return statement
    match = LATERAL.search(statement)
    if not match:
        return statement
    values_sql, alias, columns_sql = match.groups()
    columns = [s.strip() for s in columns_sql.split(",")]
    if len(columns) != 5 or any(not re.fullmatch(IDENT, c) for c in columns):
        return statement
    rows = list(ROW.finditer(values_sql))
    if not rows or ROW.sub("", values_sql).strip(" \r\n\t,"):
        return statement
    positions = [r.group(1) for r in rows]
    if len(set(positions)) != len(positions):
        return statement
    fields = [FIELD.fullmatch(expression).groups()
              for row in rows for expression in row.groups()[1:]]
    scopes = {(source, member) for source, member, _key in fields}
    if len(scopes) != 1:
        return statement
    source, member = scopes.pop()
    position, declared, *remaining = columns
    predicate = re.compile(
        rf"NULLIF\s*\(\s*BTRIM\s*\(\s*{re.escape(alias)}\.{re.escape(declared)}"
        rf"\s*\)\s*,\s*''\s*\)\s*::smallint\s*=\s*"
        rf"{re.escape(alias)}\.{re.escape(position)}\b", re.IGNORECASE,
    )
    # Require the original guard in a WHERE conjunction. General rewrites of
    # OR predicates or arbitrary aliases need separate proof and are skipped.
    suffix = statement[match.end():]
    where = re.search(r"\bWHERE\b", suffix, re.IGNORECASE)
    if not where or re.search(r"\bOR\b", suffix[where.start():], re.IGNORECASE):
        return statement
    if len(predicate.findall(suffix[where.start():])) != 1:
        return statement

    def field(expression):
        key = FIELD.fullmatch(expression).group(3)
        return f"_pgdm_payload.payload ->> '{key}'"

    declarations = ",\n".join(
        f"        ({r.group(1)}::smallint, {field(r.group(2))})" for r in rows
    )
    projections = [f"_pgdm_declared.{position} AS {position}",
                   f"_pgdm_declared.{declared} AS {declared}"]
    for expression_index, name in enumerate(remaining, start=3):
        cases = "\n".join(
            f"            WHEN {r.group(1)} THEN {field(r.group(expression_index))}"
            for r in rows
        )
        projections.append(f"CASE _pgdm_declared.{position}\n{cases}\n        END AS {name}")
    projection_sql = ",\n        ".join(projections)
    replacement = f"""CROSS JOIN LATERAL (
    SELECT {source}.raw -> '{member}' AS payload
    OFFSET 0
) AS _pgdm_payload
CROSS JOIN LATERAL (
    VALUES
{declarations}
) AS _pgdm_declared({position}, {declared})
CROSS JOIN LATERAL (
    SELECT
        {projection_sql}
    OFFSET 0
) AS {alias}"""
    suffix = predicate.sub(
        f"NULLIF(BTRIM(_pgdm_declared.{declared}), '')::smallint "
        f"= _pgdm_declared.{position}", suffix, count=1,
    )
    return statement[:match.start()] + replacement + suffix
