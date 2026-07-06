import argparse
import re
import sys
from pathlib import Path


def normalize_source_station(source_station):
    source_station = source_station.strip().upper()
    return re.sub(r"[^A-Z0-9_-]+", "_", source_station)


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


def detect_encoding(input_path):
    with open(input_path, "rb") as file:
        start = file.read(4)

    if start.startswith(b"\xff\xfe"):
        return "utf-16"
    if start.startswith(b"\xfe\xff"):
        return "utf-16"
    if start.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"

    return "utf-8"


def open_sql_file(input_path):
    encoding = detect_encoding(input_path)
    print(f"-- Leyendo SQL con codificación detectada: {encoding}", file=sys.stderr)
    return open(input_path, "r", encoding=encoding, errors="replace")


def main():
    parser = argparse.ArgumentParser(
        description="Transforma un dump SQL de model_results para insertarlo en model_results_central."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Ruta del archivo .sql exportado. Ejemplo: C:\\FTS_SYNC\\remote_db_backup.sql",
    )

    parser.add_argument(
        "--source-station",
        required=True,
        help="Nombre único de la estación. Ejemplo: ART_ENDFORM_1859_LEFT",
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        print(f"ERROR: No existe el archivo: {input_path}", file=sys.stderr)
        raise SystemExit(1)

    source_station = normalize_source_station(args.source_station)

    print("BEGIN;")
    print("""
CREATE TEMP TABLE tmp_model_results (
    id integer,
    img_name text,
    class_name text,
    confidence numeric(5,4),
    created_at timestamp without time zone,
    model_name text,
    geometry_type text,
    coordinates jsonb,
    image_width integer,
    image_height integer,
    part_number text
) ON COMMIT DROP;
""")

    found_copy = False
    finished_copy = False

    with open_sql_file(input_path) as src:
        for line in src:
            clean_line = line.lstrip("\ufeff")

            if clean_line.startswith("COPY public.model_results"):
                print(
                    clean_line.replace(
                        "COPY public.model_results",
                        "COPY tmp_model_results",
                        1
                    ),
                    end=""
                )
                found_copy = True
                break

        if not found_copy:
            print("ROLLBACK;")
            print("ERROR: No se encontró COPY public.model_results en el SQL.", file=sys.stderr)
            raise SystemExit(1)

        for line in src:
            print(line, end="")

            if line.strip() == r"\.":
                finished_copy = True
                break

    if not finished_copy:
        print("ROLLBACK;")
        print("ERROR: No se encontró el cierre del COPY: \\.", file=sys.stderr)
        raise SystemExit(1)

    print(f"""
INSERT INTO public.model_results_central (
    source_station,
    source_id,
    img_name,
    class_name,
    confidence,
    created_at,
    part_number
)
SELECT
    {sql_literal(source_station)} AS source_station,
    id AS source_id,
    img_name,
    class_name,
    confidence,
    created_at,
    part_number
FROM tmp_model_results
ON CONFLICT (source_station, source_id)
DO UPDATE SET
    img_name = EXCLUDED.img_name,
    class_name = EXCLUDED.class_name,
    confidence = EXCLUDED.confidence,
    created_at = EXCLUDED.created_at,
    part_number = EXCLUDED.part_number;
COMMIT;
""")


if __name__ == "__main__":
    main()