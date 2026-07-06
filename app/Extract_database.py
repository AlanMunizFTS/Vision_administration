import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(r"C:\FTS_SYNC")
BACKUP_DIR = BASE_DIR / "backups"
LOG_DIR = BASE_DIR / "logs"


def safe_filename(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def main():
    parser = argparse.ArgumentParser(
        description="Recibe un SQL por stdin y lo guarda como archivo .sql."
    )

    parser.add_argument(
        "--name",
        required=True,
        help="Nombre para identificar el backup. Ejemplo: ART_ENDFORM_1859_LEFT",
    )

    args = parser.parse_args()

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = safe_filename(args.name)

    sql_file = BACKUP_DIR / f"{safe_name}_{timestamp}.sql"
    partial_file = BACKUP_DIR / f"{safe_name}_{timestamp}.sql.partial"
    log_file = LOG_DIR / f"{safe_name}_{timestamp}.log"

    total_bytes = 0

    with open(partial_file, "wb") as output:
        while True:
            chunk = sys.stdin.buffer.read(64 * 1024)

            if not chunk:
                break

            output.write(chunk)
            total_bytes += len(chunk)

    if total_bytes == 0:
        with open(log_file, "w", encoding="utf-8") as log:
            log.write("ERROR: No llegó información por stdin. El SQL llegó vacío.\n")

        print(f"ERROR: El SQL llegó vacío. Revisa: {log_file}", file=sys.stderr)
        raise SystemExit(1)

    partial_file.rename(sql_file)

    with open(log_file, "w", encoding="utf-8") as log:
        log.write("SQL guardado correctamente.\n")
        log.write(f"Archivo: {sql_file}\n")
        log.write(f"Bytes: {total_bytes}\n")

    print(f"SQL guardado correctamente: {sql_file}", file=sys.stderr)


if __name__ == "__main__":
    main()