INSERT INTO public.table2 (
    id_column_2,
    integer_column_1,
    integer_column_2,
    text_column_1,
    integer_column_3,
    integer_column_4,
    integer_column_5,
    integer_column_6
)
SELECT
    main_row.id_column_1,
    position_data.position_number,
    ROUND(
        NULLIF(BTRIM(position_data.weight_text), '')::numeric * 1000
    )::integer,
    UPPER(BTRIM(position_data.type_text)),
    NULL::integer,
    NULL::integer,
    NULL::integer,
    CASE
        WHEN NULLIF(BTRIM(position_data.gap_text), '')::numeric > 0
        THEN ROUND(
            NULLIF(BTRIM(position_data.gap_text), '')::numeric * 1000
        )::integer
        ELSE NULL::integer
    END
FROM {{source}} AS source_row
CROSS JOIN LATERAL (
    SELECT source_row.raw -> 'values' AS payload
    OFFSET 0
) AS decoded
CROSS JOIN LATERAL (
    VALUES
        (1::smallint, decoded.payload ->> 'integer_column_2'),
        (2::smallint, decoded.payload ->> 'integer_column_3'),
        (3::smallint, decoded.payload ->> 'integer_column_4'),
        (4::smallint, decoded.payload ->> 'integer_column_5'),
        (5::smallint, decoded.payload ->> 'integer_column_6'),
        (6::smallint, decoded.payload ->> 'integer_column_7'),
        (7::smallint, decoded.payload ->> 'integer_column_8'),
        (8::smallint, decoded.payload ->> 'integer_column_9'),
        (9::smallint, decoded.payload ->> 'integer_column_10'),
        (10::smallint, decoded.payload ->> 'integer_column_11'),
        (11::smallint, decoded.payload ->> 'integer_column_12'),
        (12::smallint, decoded.payload ->> 'integer_column_13'),
        (13::smallint, decoded.payload ->> 'integer_column_14'),
        (14::smallint, decoded.payload ->> 'integer_column_15')
) AS declared(position_number, declared_number_text)
CROSS JOIN LATERAL (
    SELECT
        declared.position_number,
        decoded.payload ->> ('text_column_' || (declared.position_number + 3)::text) AS type_text,
        decoded.payload ->> ('numeric_column_' || (2 * declared.position_number + 1)::text) AS weight_text,
        decoded.payload ->> ('numeric_column_' || (2 * declared.position_number + 2)::text) AS gap_text
    OFFSET 0
) AS position_data
JOIN public.table1 AS main_row
  ON main_row.id_column_3 = source_row.raw_id
WHERE NULLIF(BTRIM(declared.declared_number_text), '')::smallint
        = position_data.position_number
  AND NULLIF(BTRIM(position_data.weight_text), '')::numeric >= 0
  AND UPPER(BTRIM(position_data.type_text)) IN ('X', 'Y', 'Z');
