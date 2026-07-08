import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from app.config import load_env_file


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


def tail_text_lines(path, encoding, max_lines=8):
    try:
        with open(path, "r", encoding=encoding, errors="replace") as file:
            lines = file.readlines()
    except OSError:
        return []

    return [line.rstrip("\n") for line in lines[-max_lines:]]


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


def env_value(name, default=None, required=False):
    value = os.getenv(name)
    if value is None or not value.strip():
        if required:
            raise ValueError(f"Falta {name} en .env.")
        return default
    return value.strip()


def env_bool(name, default=False):
    value = env_value(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def env_int(name, default):
    value = env_value(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un numero entero.") from exc


def first_env_value(*names, default=None):
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def resolve_path(value, default):
    raw_path = value or default
    return Path(raw_path).expanduser()


def parse_env_stations(raw_stations):
    stations = []
    for raw_station in raw_stations.split(";"):
        raw_station = raw_station.strip()
        if not raw_station:
            continue

        parts = [part.strip() for part in raw_station.split("|")]
        if len(parts) not in {3, 4}:
            raise ValueError(
                "SYNC_STATIONS debe usar el formato name|ip|output_file|enabled "
                "separado por punto y coma."
            )

        station = {
            "name": parts[0],
            "ip": parts[1],
            "output_file": parts[2],
        }
        if len(parts) == 4:
            station["enabled"] = parts[3].lower() not in {"0", "false", "no", "n", "off"}
        else:
            station["enabled"] = True
        stations.append(station)

    return stations


def load_config_from_env():
    load_env_file()
    return {
        "version": "1.0",
        "paths": {
            "base_sync_dir": env_value("SYNC_BASE_SYNC_DIR", r"C:\FTS_SYNC"),
            "add_to_central_script": env_value("SYNC_ADD_TO_CENTRAL_SCRIPT", "add_to_database_central.py"),
            "logs_folder_name": env_value("SYNC_LOGS_FOLDER_NAME", "logs"),
        },
        "retention": {
            "enabled": env_bool("SYNC_RETENTION_ENABLED", True),
            "days": env_int("SYNC_RETENTION_DAYS", 7),
            "folder_prefix": env_value("SYNC_RETENTION_FOLDER_PREFIX", "Database_"),
            "date_format": env_value("SYNC_RETENTION_DATE_FORMAT", "ddMMyy"),
        },
        "ssh": {
            "user": env_value("SYNC_SSH_USER", required=True),
            "batch_mode": env_bool("SYNC_SSH_BATCH_MODE", True),
            "connect_timeout_seconds": env_int("SYNC_SSH_CONNECT_TIMEOUT_SECONDS", 20),
            "strict_host_key_checking": env_value("SYNC_SSH_STRICT_HOST_KEY_CHECKING"),
            "user_known_hosts_file": env_value("SYNC_SSH_USER_KNOWN_HOSTS_FILE"),
            "bootstrap_keys": env_bool("SYNC_SSH_BOOTSTRAP_KEYS", True),
            "key_type": env_value("SYNC_SSH_KEY_TYPE", "ed25519"),
            "key_comment": env_value("SYNC_SSH_KEY_COMMENT", "vision-sync"),
            "key_path": resolve_path(env_value("SYNC_SSH_KEY_PATH"), "~/.ssh/id_ed25519"),
            "public_key_path": resolve_path(env_value("SYNC_SSH_PUBLIC_KEY_PATH"), "~/.ssh/id_ed25519.pub"),
            "copy_password": env_value("SYNC_SSH_COPY_PASSWORD"),
            "authorized_keys_mode": env_value("SYNC_SSH_AUTHORIZED_KEYS_MODE", "windows_admin"),
            "remote_command": env_value("SYNC_SSH_REMOTE_COMMAND", required=True),
        },
        "postgres": {
            "docker_container": env_value("SYNC_POSTGRES_DOCKER_CONTAINER", "postgres-fts"),
            "host": first_env_value("SYNC_POSTGRES_HOST", "API_DB_HOST"),
            "port": int(first_env_value("SYNC_POSTGRES_PORT", "API_DB_PORT", default="5432")),
            "database": env_value("SYNC_POSTGRES_DATABASE", os.getenv("DB_NAME", "postgres")),
            "user": env_value("SYNC_POSTGRES_USER", os.getenv("DB_USER", "postgres")),
            "password": first_env_value("SYNC_POSTGRES_PASSWORD", "DB_PASSWORD"),
            "target_table": env_value("SYNC_POSTGRES_TARGET_TABLE", "model_results_central"),
            "source_station_column": env_value("SYNC_POSTGRES_SOURCE_STATION_COLUMN", "source_station"),
        },
        "stations": parse_env_stations(env_value("SYNC_STATIONS", required=True)),
    }


def load_sync_config(config_path):
    if config_path and config_path.exists():
        return load_config(config_path), str(config_path)
    return load_config_from_env(), ".env"


def require_config(config):
    required_paths = [
        ("ssh", "user"),
        ("ssh", "remote_command"),
        ("postgres", "database"),
        ("postgres", "user"),
        ("retention", "folder_prefix"),
        ("retention", "date_format"),
    ]

    for section, key in required_paths:
        if not config.get(section, {}).get(key):
            raise ValueError(f"Falta {section}.{key} en la configuracion de sincronizacion.")

    postgres_config = config.get("postgres", {})
    if not postgres_config.get("host") and not postgres_config.get("docker_container"):
        raise ValueError("Falta postgres.host o postgres.docker_container en la configuracion.")

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


def run_process(args, logger, step_name, stdin_path=None, stdout_path=None, stdin_text=None, env=None):
    logger.info("Ejecutando: %s", step_name)

    stdin_handle = None
    stdout_handle = None
    input_data = None

    try:
        if stdin_path:
            stdin_handle = open(stdin_path, "rb")
        elif stdin_text is not None:
            input_data = stdin_text.encode("utf-8")
        if stdout_path:
            stdout_handle = open(stdout_path, "wb")

        process = subprocess.run(
            args,
            stdin=stdin_handle,
            input=input_data,
            stdout=stdout_handle or subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            check=False,
            env=env,
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


def postgres_command(config, extra_args=None):
    postgres_config = config["postgres"]
    extra_args = extra_args or []

    if postgres_config.get("use_direct_client"):
        return [
            "psql",
            "-h",
            str(postgres_config["host"]),
            "-p",
            str(postgres_config.get("port") or 5432),
            "-U",
            str(postgres_config["user"]),
            "-d",
            str(postgres_config["database"]),
            *extra_args,
        ]

    return [
        "docker",
        "exec",
        "-i",
        str(postgres_config["docker_container"]),
        "psql",
        "-U",
        str(postgres_config["user"]),
        "-d",
        str(postgres_config["database"]),
        *extra_args,
    ]


def select_postgres_mode(config):
    postgres_config = config["postgres"]

    if postgres_config.get("host") and shutil.which("psql") is not None:
        postgres_config["use_direct_client"] = True
        return "psql"

    if postgres_config.get("docker_container") and shutil.which("psql") is not None:
        postgres_config["host"] = postgres_config["docker_container"]
        postgres_config["port"] = postgres_config.get("port") or 5432
        postgres_config["use_direct_client"] = True
        return "psql"

    if postgres_config.get("docker_container") and shutil.which("docker") is not None:
        postgres_config["use_direct_client"] = False
        return "docker"

    if postgres_config.get("host"):
        raise RuntimeError("No se encontro psql en PATH para conectar a PostgreSQL por host.")

    raise RuntimeError("No se encontro docker en PATH para usar docker exec con PostgreSQL.")


def postgres_env(config):
    password = config.get("postgres", {}).get("password")
    if not password:
        return None

    env = os.environ.copy()
    env["PGPASSWORD"] = str(password)
    return env


def build_ssh_args(config, batch_mode=None, include_identity=True):
    ssh_config = config["ssh"]
    ssh_args = []

    if batch_mode is None:
        batch_mode = ssh_config.get("batch_mode") is True

    if batch_mode is True:
        ssh_args.extend(["-o", "BatchMode=yes"])

    connect_timeout = ssh_config.get("connect_timeout_seconds")
    if connect_timeout:
        ssh_args.extend(["-o", f"ConnectTimeout={int(connect_timeout)}"])

    strict_host_key_checking = ssh_config.get("strict_host_key_checking")
    if strict_host_key_checking:
        ssh_args.extend(["-o", f"StrictHostKeyChecking={strict_host_key_checking}"])

    user_known_hosts_file = ssh_config.get("user_known_hosts_file")
    if user_known_hosts_file:
        ssh_args.extend(["-o", f"UserKnownHostsFile={user_known_hosts_file}"])

    key_path = ssh_config.get("key_path")
    if include_identity and key_path and Path(key_path).exists():
        ssh_args.extend(["-i", str(key_path), "-o", "IdentitiesOnly=yes"])

    ssh_args.extend(
        [
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=6",
        ]
    )
    return ssh_args


def ssh_target_for_station(station, config):
    return f"{config['ssh']['user']}@{station['ip']}"


def ensure_local_ssh_key(config, logger):
    ssh_config = config["ssh"]
    key_path = Path(ssh_config["key_path"])
    public_key_path = Path(ssh_config["public_key_path"])

    if key_path.exists() and public_key_path.exists():
        logger.info("Llave SSH local existente: %s", key_path)
        return

    resolve_command("ssh-keygen")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Generando llave SSH local: %s", key_path)
    run_process(
        [
            "ssh-keygen",
            "-t",
            str(ssh_config.get("key_type") or "ed25519"),
            "-f",
            str(key_path),
            "-N",
            "",
            "-C",
            str(ssh_config.get("key_comment") or "vision-sync"),
        ],
        logger,
        "Generacion de llave SSH local",
    )


def station_ssh_available(station, config, ssh_command, logger):
    ssh_target = ssh_target_for_station(station, config)
    process = subprocess.run(
        [ssh_command, *build_ssh_args(config, batch_mode=True), ssh_target, "echo ok"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if process.returncode == 0:
        logger.info("Acceso SSH OK para %s", station["name"])
        return True

    stderr_text = (process.stderr or "").strip()
    if stderr_text:
        logger.warning("Acceso SSH pendiente para %s: %s", station["name"], stderr_text)
    return False


def sshpass_command(config, ssh_command):
    password = config["ssh"].get("copy_password")
    if not password:
        return None, None

    sshpass = shutil.which("sshpass")
    if sshpass:
        env = os.environ.copy()
        env["SSHPASS"] = str(password)
        return [sshpass, "-e", ssh_command], env

    return None, None


def remote_authorized_key_command(config):
    mode = str(config["ssh"].get("authorized_keys_mode") or "windows_admin").lower()
    if mode in {"linux", "linux_user", "jetson"}:
        return (
            "sh -lc 'umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
            "key=$(cat); grep -qxF \"$key\" ~/.ssh/authorized_keys || printf \"%s\\n\" \"$key\" >> ~/.ssh/authorized_keys; "
            "chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'"
        )

    if mode in {"windows_user", "user"}:
        return (
            "powershell -NoProfile -Command "
            "\"$key = ([Console]::In.ReadToEnd()).Trim(); "
            "$dir = Join-Path $env:USERPROFILE '.ssh'; "
            "$file = Join-Path $dir 'authorized_keys'; "
            "New-Item -ItemType Directory -Path $dir -Force | Out-Null; "
            "if (!(Test-Path $file) -or -not (Select-String -Path $file -SimpleMatch $key -Quiet)) { Add-Content -Path $file -Value $key }\""
        )

    return (
        "powershell -NoProfile -Command "
        "\"$key = ([Console]::In.ReadToEnd()).Trim(); "
        "$file = 'C:\\ProgramData\\ssh\\administrators_authorized_keys'; "
        "New-Item -ItemType Directory -Path (Split-Path $file) -Force | Out-Null; "
        "if (!(Test-Path $file) -or -not (Select-String -Path $file -SimpleMatch $key -Quiet)) { Add-Content -Path $file -Value $key }; "
        "icacls $file /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F'\""
    )


def install_station_ssh_key(station, config, ssh_command, logger):
    public_key_path = Path(config["ssh"]["public_key_path"])
    public_key = public_key_path.read_text(encoding="utf-8").strip()
    sshpass_args, sshpass_env = sshpass_command(config, ssh_command)
    if not sshpass_args:
        logger.warning(
            "No se puede instalar la llave automaticamente para %s: falta SYNC_SSH_COPY_PASSWORD o sshpass.",
            station["name"],
        )
        return False

    ssh_target = ssh_target_for_station(station, config)
    logger.info("Instalando llave SSH en %s", station["name"])
    run_process(
        [
            *sshpass_args,
            *build_ssh_args(config, batch_mode=False, include_identity=False),
            ssh_target,
            remote_authorized_key_command(config),
        ],
        logger,
        f"Instalacion de llave SSH en {station['name']}",
        stdin_text=f"{public_key}\n",
        env=sshpass_env,
    )
    return True


def ensure_station_ssh_access(station, config, ssh_command, logger):
    if not config["ssh"].get("bootstrap_keys"):
        return

    ensure_local_ssh_key(config, logger)
    if station_ssh_available(station, config, ssh_command, logger):
        return

    try:
        if install_station_ssh_key(station, config, ssh_command, logger):
            station_ssh_available(station, config, ssh_command, logger)
    except Exception as exc:
        logger.warning("No se pudo preparar llave SSH para %s: %s", station["name"], exc)


def export_remote_database(station, config, today_dir, logger, ssh_command):
    output_file = today_dir / station["output_file"]
    if output_file.exists():
        output_file.unlink()

    ssh_args = build_ssh_args(config)

    ssh_target = ssh_target_for_station(station, config)
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
                file_size = input_path.stat().st_size if input_path.exists() else 0
                tail_lines = tail_text_lines(input_path, encoding)
                tail_preview = " | ".join(tail_lines) if tail_lines else "<sin lineas>"
                raise RuntimeError(
                    "No se encontro el cierre del COPY: \\. "
                    f"El dump puede estar incompleto o truncado. Archivo={input_path}, "
                    f"tamano={file_size} bytes, ultimas_lineas={tail_preview}"
                )

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
        postgres_command(config, ["-v", "ON_ERROR_STOP=1"]),
        logger,
        f"Importacion PostgreSQL de {station['name']}",
        stdin_path=transform_sql,
        env=postgres_env(config),
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
        postgres_command(config, ["-c", f"SELECT COUNT(*) AS total_central FROM {target_table};"]),
        logger,
        "Conteo total",
        env=postgres_env(config),
    )

    if source_column:
        logger.info("Conteo por %s en %s", source_column, target_table)
        run_process(
            postgres_command(
                config,
                [
                    "-c",
                    (
                        f"SELECT {source_column}, COUNT(*) AS total "
                        f"FROM {target_table} GROUP BY {source_column} ORDER BY {source_column};"
                    ),
                ],
            ),
            logger,
            "Conteo por estacion",
            env=postgres_env(config),
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
    load_env_file()
    default_config = os.getenv("SYNC_CONFIG_PATH")
    if default_config:
        default_config = Path(default_config)
        if not default_config.is_absolute():
            default_config = SCRIPT_DIR.parent / default_config
    else:
        default_config = DEFAULT_CONFIG

    parser = argparse.ArgumentParser(
        description="Exporta bases remotas por SSH e importa model_results en PostgreSQL central."
    )
    parser.add_argument(
        "--config",
        default=default_config,
        type=Path,
        help="Ruta al JSON privado de maquinas. Por defecto usa SYNC_CONFIG_PATH o app/machines.json.",
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
        config_path = args.config.resolve() if args.config else None
        config, config_source = load_sync_config(config_path)
        require_config(config)

        ssh_command = resolve_command("ssh.exe", "ssh")
        postgres_mode = select_postgres_mode(config)
        logger.info("Modo PostgreSQL: %s", postgres_mode)

        folder_prefix = str(config["retention"]["folder_prefix"])
        date_format = python_date_format(str(config["retention"]["date_format"]))
        today_folder_name = f"{folder_prefix}{datetime.now().strftime(date_format)}"
        today_dir = work_dir / today_folder_name
        temp_dir = today_dir / "_temp"

        today_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info("============================================================")
        logger.info("Iniciando FTS DWH Sync desde IE_db.py")
        logger.info("ConfigSource: %s", config_source)
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

                ensure_station_ssh_access(station, config, ssh_command, logger)
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
