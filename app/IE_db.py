import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "machines.json"
DEFAULT_LOG = SCRIPT_DIR / "sync.log"


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


def setup_logger(log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ie_db")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="[%(asctime)s][%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def load_config(config_path):
    if not config_path.exists():
        raise FileNotFoundError(f"No se encontro el archivo de configuracion: {config_path}")

    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def require_config(config):
    required_paths = [
        ("ssh", "user"),
        ("ssh", "remote_command"),
        ("postgres", "docker_container"),
        ("postgres", "database"),
        ("postgres", "user"),
        ("retention", "folder_prefix"),
        ("retention", "date_format"),
    ]

    for section, key in required_paths:
        if not config.get(section, {}).get(key):
            raise ValueError(f"Falta {section}.{key} en machines.json.")

    stations = config.get("stations") or []
    if not stations:
        raise ValueError("No hay estaciones definidas en stations.")

    for station in stations:
        if not station.get("name"):
            raise ValueError("Hay una estacion sin name.")
        if not station.get("ip"):
            raise ValueError(f"La estacion '{station['name']}' no tiene ip.")
        if not station.get("output_file"):
            raise ValueError(f"La estacion '{station['name']}' no tiene output_file.")


def resolve_command(*command_names):
    for command_name in command_names:
        if shutil.which(command_name) is not None:
            return command_name

    raise RuntimeError(f"No se encontro ninguno de estos comandos en PATH: {', '.join(command_names)}")


def python_date_format(config_format):
    replacements = {
        "dd": "%d",
        "MM": "%m",
        "yyyy": "%Y",
        "yy": "%y",
    }

    result = config_format
    for source, target in replacements.items():
        result = result.replace(source, target)

    return result


def run_process(args, logger, step_name, stdin_path=None, stdout_path=None):
    logger.info("Ejecutando: %s", step_name)

    stdin_handle = None
    stdout_handle = None

    try:
        if stdin_path:
            stdin_handle = open(stdin_path, "rb")
        if stdout_path:
            stdout_handle = open(stdout_path, "wb")

        process = subprocess.run(
            args,
            stdin=stdin_handle,
            stdout=stdout_handle or subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            check=False,
        )
    finally:
        if stdin_handle:
            stdin_handle.close()
        if stdout_handle:
            stdout_handle.close()

    if process.stdout and not stdout_path:
        logger.info(process.stdout.decode("utf-8", errors="replace").rstrip())

    if process.stderr:
        stderr_text = process.stderr.decode("utf-8", errors="replace").rstrip()
        if stderr_text:
            logger.info(stderr_text)

    if process.returncode != 0:
        raise RuntimeError(f"{step_name} fallo con ExitCode={process.returncode}")


def export_remote_database(station, config, today_dir, logger, ssh_command):
    output_file = today_dir / station["output_file"]
    if output_file.exists():
        output_file.unlink()

    ssh_args = []

    if config["ssh"].get("batch_mode") is True:
        ssh_args.extend(["-o", "BatchMode=yes"])

    connect_timeout = config["ssh"].get("connect_timeout_seconds")
    if connect_timeout:
        ssh_args.extend(["-o", f"ConnectTimeout={int(connect_timeout)}"])

    ssh_args.extend(
        [
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=6",
        ]
    )

    ssh_target = f"{config['ssh']['user']}@{station['ip']}"
    remote_command = str(config["ssh"]["remote_command"])

    logger.info("Exportando %s desde %s hacia %s", station["name"], ssh_target, output_file)
    run_process(
        [ssh_command, *ssh_args, ssh_target, remote_command],
        logger,
        f"Exportacion SSH de {station['name']}",
        stdout_path=output_file,
    )

    if not output_file.exists():
        raise RuntimeError(f"No se genero archivo SQL para {station['name']}: {output_file}")

    file_size = output_file.stat().st_size
    if file_size <= 0:
        raise RuntimeError(f"El archivo SQL de {station['name']} esta vacio: {output_file}")

    logger.info(
        "Exportacion OK de %s. Tamano: %.2f MB",
        station["name"],
        file_size / 1024 / 1024,
    )
    return output_file


def write_centralized_sql(input_path, source_station, output_path, logger):
    source_station = normalize_source_station(source_station)
    encoding = detect_encoding(input_path)
    logger.info("Leyendo %s con codificacion detectada: %s", input_path, encoding)

    found_copy = False
    finished_copy = False

    with open(input_path, "r", encoding=encoding, errors="replace") as src:
        with open(output_path, "w", encoding="utf-8", newline="") as dst:
            dst.write("BEGIN;\n")
            dst.write(
                """
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
"""
            )

            for line in src:
                clean_line = line.lstrip("\ufeff")

                if clean_line.startswith("COPY public.model_results"):
                    dst.write(
                        clean_line.replace(
                            "COPY public.model_results",
                            "COPY tmp_model_results",
                            1,
                        )
                    )
                    found_copy = True
                    break

            if not found_copy:
                dst.write("ROLLBACK;\n")
                raise RuntimeError("No se encontro COPY public.model_results en el SQL.")

            for line in src:
                dst.write(line)

                if line.strip() == r"\.":
                    finished_copy = True
                    break

            if not finished_copy:
                dst.write("ROLLBACK;\n")
                raise RuntimeError("No se encontro el cierre del COPY: \\.")

            dst.write(
                f"""
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
"""
            )


def import_to_central_database(station, input_file, config, temp_dir, logger):
    transform_sql = temp_dir / f"{station['name']}_centralized.sql"
    if transform_sql.exists():
        transform_sql.unlink()

    logger.info("Transformando %s dentro de IE_db.py", station["name"])
    write_centralized_sql(input_file, station["name"], transform_sql, logger)

    if transform_sql.stat().st_size <= 0:
        raise RuntimeError(f"El SQL centralizado de {station['name']} esta vacio.")

    logger.info("Importando %s hacia PostgreSQL central", station["name"])
    run_process(
        [
            "docker",
            "exec",
            "-i",
            str(config["postgres"]["docker_container"]),
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            str(config["postgres"]["user"]),
            "-d",
            str(config["postgres"]["database"]),
        ],
        logger,
        f"Importacion PostgreSQL de {station['name']}",
        stdin_path=transform_sql,
    )

    logger.info("Importacion OK de %s", station["name"])
    transform_sql.unlink(missing_ok=True)


def show_central_counts(config, logger):
    target_table = config.get("postgres", {}).get("target_table")
    source_column = config.get("postgres", {}).get("source_station_column")

    if not target_table:
        logger.warning("No se configuro postgres.target_table. Saltando conteo final.")
        return

    logger.info("Conteo total en %s", target_table)
    run_process(
        [
            "docker",
            "exec",
            "-i",
            str(config["postgres"]["docker_container"]),
            "psql",
            "-U",
            str(config["postgres"]["user"]),
            "-d",
            str(config["postgres"]["database"]),
            "-c",
            f"SELECT COUNT(*) AS total_central FROM {target_table};",
        ],
        logger,
        "Conteo total",
    )

    if source_column:
        logger.info("Conteo por %s en %s", source_column, target_table)
        run_process(
            [
                "docker",
                "exec",
                "-i",
                str(config["postgres"]["docker_container"]),
                "psql",
                "-U",
                str(config["postgres"]["user"]),
                "-d",
                str(config["postgres"]["database"]),
                "-c",
                (
                    f"SELECT {source_column}, COUNT(*) AS total "
                    f"FROM {target_table} GROUP BY {source_column} ORDER BY {source_column};"
                ),
            ],
            logger,
            "Conteo por estacion",
        )


def remove_old_database_folders(base_dir, folder_prefix, date_format, retention_days, logger):
    logger.info("Revisando retencion. Se conservaran carpetas de los ultimos %s dias.", retention_days)

    limit_date = datetime.now().date() - timedelta(days=retention_days)
    for folder in base_dir.glob(f"{folder_prefix}*"):
        if not folder.is_dir():
            continue

        date_text = folder.name[len(folder_prefix) :]
        if not re.fullmatch(r"\d{6}", date_text):
            logger.warning("Saltando carpeta con formato no reconocido: %s", folder)
            continue

        try:
            folder_date = datetime.strptime(date_text, date_format).date()
        except ValueError as exc:
            logger.warning("No se pudo interpretar fecha de carpeta '%s': %s", folder, exc)
            continue

        if folder_date < limit_date:
            logger.info("Eliminando carpeta antigua de respaldo: %s", folder)
            shutil.rmtree(folder)
        else:
            logger.info("Conservando carpeta: %s", folder)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Exporta bases remotas por SSH e importa model_results en PostgreSQL central."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        type=Path,
        help="Ruta a machines.json. Por defecto usa app/machines.json.",
    )
    parser.add_argument(
        "--work-dir",
        default=SCRIPT_DIR,
        type=Path,
        help="Carpeta donde se guardan Database_ddMMyy y sync.log. Por defecto usa app.",
    )
    parser.add_argument(
        "--log",
        default=DEFAULT_LOG,
        type=Path,
        help="Ruta del log unico. Por defecto usa app/sync.log.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    work_dir = args.work_dir.resolve()
    log_path = args.log.resolve()
    logger = setup_logger(log_path)

    ok_count = 0
    error_count = 0
    skipped_count = 0
    temp_dir = None

    try:
        config = load_config(args.config.resolve())
        require_config(config)

        ssh_command = resolve_command("ssh.exe", "ssh")
        resolve_command("docker")

        folder_prefix = str(config["retention"]["folder_prefix"])
        date_format = python_date_format(str(config["retention"]["date_format"]))
        today_folder_name = f"{folder_prefix}{datetime.now().strftime(date_format)}"
        today_dir = work_dir / today_folder_name
        temp_dir = today_dir / "_temp"

        today_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info("============================================================")
        logger.info("Iniciando FTS DWH Sync desde IE_db.py")
        logger.info("ConfigPath: %s", args.config.resolve())
        logger.info("Carpeta de trabajo: %s", work_dir)
        logger.info("Carpeta diaria: %s", today_dir)
        logger.info("Log unico: %s", log_path)
        logger.info("============================================================")

        for station in config["stations"]:
            if station.get("enabled") is False:
                skipped_count += 1
                logger.warning("Saltando estacion deshabilitada: %s", station["name"])
                continue

            try:
                logger.info("------------------------------------------------------------")
                logger.info("Procesando estacion: %s", station["name"])

                sql_file = export_remote_database(station, config, today_dir, logger, ssh_command)
                import_to_central_database(station, sql_file, config, temp_dir, logger)

                ok_count += 1
                logger.info("Finalizado OK: %s", station["name"])
            except Exception as exc:
                error_count += 1
                logger.exception("ERROR en %s: %s", station["name"], exc)

        logger.info("------------------------------------------------------------")
        logger.info(
            "Resumen estaciones OK: %s | Error: %s | Saltadas: %s",
            ok_count,
            error_count,
            skipped_count,
        )

        show_central_counts(config, logger)

        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir)

        if config.get("retention", {}).get("enabled") is True:
            remove_old_database_folders(
                work_dir,
                folder_prefix,
                date_format,
                int(config["retention"].get("days", 7)),
                logger,
            )
        else:
            logger.info("Retencion deshabilitada desde JSON.")

        logger.info("============================================================")
        logger.info("FTS DWH Sync terminado")
        logger.info("============================================================")

        if error_count > 0:
            raise SystemExit(2)
    except SystemExit:
        raise
    except Exception as exc:
        logger.exception("ERROR GENERAL: %s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
