import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from app.config import load_env_file


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_CONFIG = SCRIPT_DIR / "machines.json"
DEFAULT_LOG = PROJECT_DIR / "reports" / "sync.log"


def normalize_source_station(source_station):
    source_station = source_station.strip().upper()
    return re.sub(r"[^A-Z0-9_-]+", "_", source_station)


def get_piece_station_and_side(source_station):
    source_station = normalize_source_station(source_station)

    match = re.match(r"^ART_ENDFORM_([0-9]+)_(LEFT|RIGHT)$", source_station)
    if match:
        station_id = match.group(1)
        side = match.group(2)
        return f"ART_{station_id}_ENDFORM", side

    match = re.match(r"^(ART_[0-9]+_ENDFORM)_(LEFT|RIGHT)$", source_station)
    if match:
        return match.group(1), match.group(2)

    match = re.match(r"^(.+)_(LEFT|RIGHT)$", source_station)
    if match:
        return match.group(1), match.group(2)

    raise ValueError(f"No se pudo obtener LEFT/RIGHT desde source_station: {source_station}")


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

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
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


def parse_env_list(raw_value):
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def load_config_from_env():
    load_env_file()
    return {
        "version": "1.0",
        "paths": {
            "base_sync_dir": env_value("SYNC_BASE_SYNC_DIR", r"C:\FTS_SYNC"),
            "add_to_central_script": env_value("SYNC_ADD_TO_CENTRAL_SCRIPT", "add_to_database_central.py"),
            "logs_folder_name": env_value("SYNC_LOGS_FOLDER_NAME", "logs"),
        },
        "export": {
            "retries": env_int("SYNC_EXPORT_RETRIES", 2),
            "retry_delay_seconds": env_int("SYNC_EXPORT_RETRY_DELAY_SECONDS", 5),
            "fetch_retries": env_int("SYNC_FETCH_RETRIES", 3),
            "fetch_retry_delay_seconds": env_int("SYNC_FETCH_RETRY_DELAY_SECONDS", 5),
        },
        "station_retry": {
            "retries": env_int("SYNC_STATION_RETRIES", 1),
            "retry_delay_seconds": env_int("SYNC_STATION_RETRY_DELAY_SECONDS", 10),
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
            "remote_output_dir": env_value("SYNC_SSH_REMOTE_OUTPUT_DIR"),
            "remote_output_stations": parse_env_list(env_value("SYNC_SSH_REMOTE_OUTPUT_STATIONS")),
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


def model_results_copy_is_complete(input_path):
    encoding = detect_encoding(input_path)
    found_copy = False

    with open(input_path, "r", encoding=encoding, errors="replace") as file:
        for line in file:
            clean_line = line.lstrip("\ufeff")
            if clean_line.startswith("COPY public.model_results"):
                found_copy = True
                break

        if not found_copy:
            return False, "No se encontro COPY public.model_results en el SQL."

        for line in file:
            if line.strip() == r"\.":
                return True, None

    file_size = input_path.stat().st_size if input_path.exists() else 0
    tail_lines = tail_text_lines(input_path, encoding)
    tail_preview = " | ".join(tail_lines) if tail_lines else "<sin lineas>"
    return (
        False,
        "No se encontro el cierre del COPY: \\. "
        f"El dump puede estar incompleto o truncado. Archivo={input_path}, "
        f"tamano={file_size} bytes, ultimas_lineas={tail_preview}",
    )


TEMP_COLUMN_TYPES = {
    "id": "bigint",
    "piece_id": "bigint",
    "source_piece_id": "bigint",
    "img_name": "text",
    "class_name": "text",
    "confidence": "numeric(5,4)",
    "created_at": "timestamp without time zone",
    "model_name": "text",
    "geometry_type": "text",
    "coordinates": "jsonb",
    "image_width": "integer",
    "image_height": "integer",
    "part_number": "text",
    "jsn": "text",
    "decoat_length": "double precision",
    "decoat_micrometer": "double precision",
    "decoat_position": "double precision",
    "decoat_speed": "real",
    "decoat_trq": "double precision",
    "endform_flag_length": "double precision",
    "endform_flag_pos": "double precision",
    "endform_hit1": "double precision",
    "endform_hit2": "double precision",
    "endform_hit3": "double precision",
    "endform_position_act": "double precision",
    "endform_speed_act": "double precision",
    "endform_trq_act": "double precision",
}


def is_copy_for_table(line, table_name):
    pattern = rf"^COPY\s+public\.{re.escape(table_name)}\s*\("
    return re.match(pattern, line) is not None


def replace_copy_table(line, table_name, target_table):
    pattern = rf"^COPY\s+public\.{re.escape(table_name)}(?=\s*\()"
    return re.sub(pattern, f"COPY {target_table}", line, count=1)


def parse_copy_columns(copy_line, table_name):
    pattern = rf"COPY\s+public\.{re.escape(table_name)}\s*\((.*?)\)\s+FROM\s+stdin"
    match = re.search(pattern, copy_line, re.IGNORECASE)
    if not match:
        raise RuntimeError(f"No se pudo leer la lista de columnas del COPY: {copy_line.strip()}")

    columns = []
    for raw_column in match.group(1).split(","):
        column = raw_column.strip().strip('"').lower()
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", column):
            raise RuntimeError(f"Columna no valida en COPY public.{table_name}: {raw_column.strip()}")
        if column not in columns:
            columns.append(column)

    if not columns:
        raise RuntimeError(f"El COPY public.{table_name} no contiene columnas.")
    return columns


def create_temp_table_sql(table_name, columns):
    definitions = []
    for column in columns:
        column_type = TEMP_COLUMN_TYPES.get(column, "text")
        definitions.append(f"    {column} {column_type}")
    return f"CREATE TEMP TABLE {table_name} (\n" + ",\n".join(definitions) + "\n) ON COMMIT DROP;\n"


def emit_copy_block(src, dst, first_line, table_name, target_table):
    copy_columns = parse_copy_columns(first_line, table_name)
    dst.write(create_temp_table_sql(target_table, copy_columns))
    dst.write(replace_copy_table(first_line, table_name, target_table))

    for line in src:
        dst.write(line)
        if line.strip() == r"\.":
            return copy_columns

    raise RuntimeError(f"No se encontro el cierre del COPY de public.{table_name}: \\.")


def source_id_expression(columns):
    if "id" in columns:
        return "m.id"
    if "piece_id" in columns:
        return "m.piece_id"
    raise RuntimeError("El dump no trae columna id ni piece_id para usar como source_id.")


def temp_column_expression(alias, columns, column, fallback="NULL"):
    if column in columns:
        return f"{alias}.{column}"
    return fallback


def temp_column_select(alias, columns, column):
    column_type = TEMP_COLUMN_TYPES.get(column, "text")
    return temp_column_expression(alias, columns, column, f"NULL::{column_type}")


def quote_remote_arg(value):
    return '"' + str(value).replace('"', r'\"') + '"'


def remote_path_join(base_dir, filename):
    base_dir = str(base_dir).rstrip("\\/")
    filename = Path(filename).name
    separator = "\\" if ("\\" in base_dir or ":" in base_dir) else "/"
    return f"{base_dir}{separator}{filename}"


def fetch_remote_file(station, config, remote_path, output_file, logger, ssh_command):
    export_config = config.get("export", {})
    retries = max(0, int(export_config.get("fetch_retries") or 0))
    delay_seconds = max(0, int(export_config.get("fetch_retry_delay_seconds") or 0))
    attempts = retries + 1
    ssh_target = ssh_target_for_station(station, config)
    ssh_args = build_ssh_args(config)
    fetch_command = f"type {quote_remote_arg(remote_path)}"
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            if output_file.exists():
                output_file.unlink()

            logger.info(
                "Leyendo dump remoto de %s desde %s. Intento %s/%s",
                station["name"],
                remote_path,
                attempt,
                attempts,
            )
            run_process(
                [ssh_command, *ssh_args, ssh_target, fetch_command],
                logger,
                f"Lectura SSH de dump remoto de {station['name']}",
                stdout_path=output_file,
            )

            complete, issue = model_results_copy_is_complete(output_file)
            if not complete:
                raise RuntimeError(issue)

            return
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            logger.warning(
                "Lectura del dump remoto de %s fallo en intento %s/%s: %s",
                station["name"],
                attempt,
                attempts,
                exc,
            )
            if delay_seconds:
                logger.info(
                    "Esperando %s segundos antes de releer dump remoto de %s",
                    delay_seconds,
                    station["name"],
                )
                time.sleep(delay_seconds)

    raise last_error


def export_remote_database_once(station, config, output_dir, logger, ssh_command):
    output_file = output_dir / station["output_file"]
    if output_file.exists():
        output_file.unlink()

    ssh_args = build_ssh_args(config)

    ssh_target = ssh_target_for_station(station, config)
    remote_command = str(config["ssh"]["remote_command"])
    remote_output_dir = config["ssh"].get("remote_output_dir")
    remote_output_stations = set(config["ssh"].get("remote_output_stations") or [])
    remote_output_path = None
    if remote_output_dir and (not remote_output_stations or station["name"] in remote_output_stations):
        remote_output_path = remote_path_join(remote_output_dir, station["output_file"])
        remote_command = f"{remote_command} --output {quote_remote_arg(remote_output_path)}"

    logger.info("Exportando %s desde %s hacia %s", station["name"], ssh_target, output_file)
    run_process(
        [ssh_command, *ssh_args, ssh_target, remote_command],
        logger,
        f"Exportacion SSH de {station['name']}",
        stdout_path=None if remote_output_path else output_file,
    )

    if remote_output_path:
        logger.info(
            "Exportacion remota OK de %s. Descargando archivo validado desde %s",
            station["name"],
            remote_output_path,
        )
        fetch_remote_file(station, config, remote_output_path, output_file, logger, ssh_command)

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
    complete, issue = model_results_copy_is_complete(output_file)
    if not complete:
        raise RuntimeError(issue)

    return output_file


def export_remote_database(station, config, output_dir, logger, ssh_command):
    retries = max(0, int(config.get("export", {}).get("retries", 0)))
    delay_seconds = max(0, int(config.get("export", {}).get("retry_delay_seconds", 0)))
    attempts = retries + 1
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                logger.info("Reintentando exportacion de %s (%s/%s)", station["name"], attempt, attempts)
            return export_remote_database_once(station, config, output_dir, logger, ssh_command)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            logger.warning("Exportacion de %s fallo en intento %s/%s: %s", station["name"], attempt, attempts, exc)
            if delay_seconds:
                logger.info("Esperando %s segundos antes de reintentar %s", delay_seconds, station["name"])
                time.sleep(delay_seconds)

    raise last_error


def write_centralized_sql(input_path, source_station, output_path, logger):
    source_station = normalize_source_station(source_station)
    piece_source_station, side = get_piece_station_and_side(source_station)
    encoding = detect_encoding(input_path)
    logger.info("Leyendo %s con codificacion detectada: %s", input_path, encoding)

    model_results_columns = None
    pieces_columns = None

    with open(input_path, "r", encoding=encoding, errors="replace") as src:
        with open(output_path, "w", encoding="utf-8", newline="") as dst:
            dst.write("BEGIN;\n")

            for line in src:
                clean_line = line.lstrip("\ufeff")

                if is_copy_for_table(clean_line, "pieces"):
                    pieces_columns = emit_copy_block(
                        src,
                        dst,
                        clean_line,
                        "pieces",
                        "tmp_pieces",
                    )
                    continue

                if is_copy_for_table(clean_line, "model_results"):
                    model_results_columns = emit_copy_block(
                        src,
                        dst,
                        clean_line,
                        "model_results",
                        "tmp_model_results",
                    )
                    continue

            if model_results_columns is None:
                dst.write("ROLLBACK;\n")
                raise RuntimeError("No se encontro COPY public.model_results en el SQL.")

            if pieces_columns is not None:
                dst.write(
                    f"""
INSERT INTO public.pieces (
    source_piece_id,
    source_station,
    side,
    jsn,
    created_at,
    decoat_length,
    decoat_micrometer,
    decoat_position,
    decoat_speed,
    decoat_trq,
    endform_flag_length,
    endform_flag_pos,
    endform_hit1,
    endform_hit2,
    endform_hit3,
    endform_position_act,
    endform_speed_act,
    endform_trq_act
)
SELECT
    {temp_column_select("tp", pieces_columns, "id")} AS source_piece_id,
    {sql_literal(piece_source_station)} AS source_station,
    {sql_literal(side)} AS side,
    {temp_column_select("tp", pieces_columns, "jsn")} AS jsn,
    COALESCE({temp_column_select("tp", pieces_columns, "created_at")}, CURRENT_TIMESTAMP) AS created_at,
    {temp_column_select("tp", pieces_columns, "decoat_length")} AS decoat_length,
    {temp_column_select("tp", pieces_columns, "decoat_micrometer")} AS decoat_micrometer,
    {temp_column_select("tp", pieces_columns, "decoat_position")} AS decoat_position,
    {temp_column_select("tp", pieces_columns, "decoat_speed")} AS decoat_speed,
    {temp_column_select("tp", pieces_columns, "decoat_trq")} AS decoat_trq,
    {temp_column_select("tp", pieces_columns, "endform_flag_length")} AS endform_flag_length,
    {temp_column_select("tp", pieces_columns, "endform_flag_pos")} AS endform_flag_pos,
    {temp_column_select("tp", pieces_columns, "endform_hit1")} AS endform_hit1,
    {temp_column_select("tp", pieces_columns, "endform_hit2")} AS endform_hit2,
    {temp_column_select("tp", pieces_columns, "endform_hit3")} AS endform_hit3,
    {temp_column_select("tp", pieces_columns, "endform_position_act")} AS endform_position_act,
    {temp_column_select("tp", pieces_columns, "endform_speed_act")} AS endform_speed_act,
    {temp_column_select("tp", pieces_columns, "endform_trq_act")} AS endform_trq_act
FROM tmp_pieces tp
WHERE {temp_column_select("tp", pieces_columns, "jsn")} IS NOT NULL
ON CONFLICT (source_station, side, jsn)
DO UPDATE SET
    source_piece_id = EXCLUDED.source_piece_id,
    created_at = EXCLUDED.created_at,
    decoat_length = EXCLUDED.decoat_length,
    decoat_micrometer = EXCLUDED.decoat_micrometer,
    decoat_position = EXCLUDED.decoat_position,
    decoat_speed = EXCLUDED.decoat_speed,
    decoat_trq = EXCLUDED.decoat_trq,
    endform_flag_length = EXCLUDED.endform_flag_length,
    endform_flag_pos = EXCLUDED.endform_flag_pos,
    endform_hit1 = EXCLUDED.endform_hit1,
    endform_hit2 = EXCLUDED.endform_hit2,
    endform_hit3 = EXCLUDED.endform_hit3,
    endform_position_act = EXCLUDED.endform_position_act,
    endform_speed_act = EXCLUDED.endform_speed_act,
    endform_trq_act = EXCLUDED.endform_trq_act;
"""
                )

            piece_join_sql = ""
            piece_select_sql = "NULL::bigint AS piece_id"
            if pieces_columns is not None and "piece_id" in model_results_columns and "id" in pieces_columns:
                piece_join_sql = f"""
LEFT JOIN tmp_pieces tp
    ON tp.id = m.piece_id
LEFT JOIN public.pieces p
    ON p.source_station = {sql_literal(piece_source_station)}
   AND p.side = {sql_literal(side)}
   AND p.jsn = tp.jsn"""
                piece_select_sql = "p.id AS piece_id"

            dst.write(
                f"""
INSERT INTO public.model_results_central (
    source_station,
    source_id,
    img_name,
    class_name,
    confidence,
    created_at,
    part_number,
    piece_id
)
SELECT
    {sql_literal(source_station)} AS source_station,
    {source_id_expression(model_results_columns)} AS source_id,
    {temp_column_select("m", model_results_columns, "img_name")} AS img_name,
    {temp_column_select("m", model_results_columns, "class_name")} AS class_name,
    {temp_column_select("m", model_results_columns, "confidence")} AS confidence,
    {temp_column_select("m", model_results_columns, "created_at")} AS created_at,
    {temp_column_select("m", model_results_columns, "part_number")} AS part_number,
    {piece_select_sql}
FROM tmp_model_results m
{piece_join_sql}
ON CONFLICT (source_station, source_id)
DO UPDATE SET
    img_name = EXCLUDED.img_name,
    class_name = EXCLUDED.class_name,
    confidence = EXCLUDED.confidence,
    created_at = EXCLUDED.created_at,
    part_number = COALESCE(EXCLUDED.part_number, model_results_central.part_number),
    piece_id = COALESCE(EXCLUDED.piece_id, model_results_central.piece_id);
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


def process_station_with_resume(station, config, temp_dir, logger, ssh_command):
    retries = max(0, int(config.get("station_retry", {}).get("retries", 0)))
    delay_seconds = max(0, int(config.get("station_retry", {}).get("retry_delay_seconds", 0)))
    attempts = retries + 1

    ssh_checked = False
    sql_file = None
    last_error = None
    failed_stage = "ssh"

    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                logger.info(
                    "Reintentando %s desde etapa %s (%s/%s)",
                    station["name"],
                    failed_stage,
                    attempt,
                    attempts,
                )

            if not ssh_checked:
                failed_stage = "ssh"
                ensure_station_ssh_access(station, config, ssh_command, logger)
                ssh_checked = True
                logger.info("Checkpoint %s: SSH listo", station["name"])

            if sql_file is None:
                failed_stage = "export"
                sql_file = export_remote_database(station, config, temp_dir, logger, ssh_command)
                logger.info("Checkpoint %s: exportacion lista", station["name"])

            failed_stage = "import"
            import_to_central_database(station, sql_file, config, temp_dir, logger)
            logger.info("Checkpoint %s: importacion lista", station["name"])
            return
        except Exception as exc:
            last_error = exc
            if failed_stage == "ssh":
                ssh_checked = False
            if failed_stage == "export":
                sql_file = None

            if attempt >= attempts:
                break

            logger.warning(
                "%s fallo en etapa %s durante intento %s/%s: %s",
                station["name"],
                failed_stage,
                attempt,
                attempts,
                exc,
            )
            if delay_seconds:
                logger.info(
                    "Esperando %s segundos antes de reintentar %s desde %s",
                    delay_seconds,
                    station["name"],
                    failed_stage,
                )
                time.sleep(delay_seconds)

    raise last_error


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
        help="Carpeta base para temporales del sync. Por defecto usa app.",
    )
    parser.add_argument(
        "--log",
        default=DEFAULT_LOG,
        type=Path,
        help="Ruta del log unico. Por defecto usa reports/sync.log.",
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

        temp_dir = work_dir / "_sync_temp"

        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info("============================================================")
        logger.info("Iniciando FTS DWH Sync desde IE_db.py")
        logger.info("ConfigSource: %s", config_source)
        logger.info("Carpeta de trabajo: %s", work_dir)
        logger.info("Carpeta temporal: %s", temp_dir)
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

                process_station_with_resume(station, config, temp_dir, logger, ssh_command)

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
