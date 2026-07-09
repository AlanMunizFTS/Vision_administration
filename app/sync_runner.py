import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from app.config import load_env_file


APP_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = APP_DIR / "IE_db.py"
DEFAULT_SYNC_LOG = APP_DIR / "sync.log"


def get_sync_log_path():
    return DEFAULT_SYNC_LOG


def get_sync_config_path():
    load_env_file()
    configured_path = os.getenv("SYNC_CONFIG_PATH")
    if not configured_path:
        return APP_DIR / "machines.json"

    config_path = Path(configured_path)
    if config_path.is_absolute():
        return config_path

    return (APP_DIR.parent / config_path).resolve()


class SyncRunner:
    def __init__(self):
        self._lock = threading.RLock()
        self._process = None
        self._started_at = None
        self._finished_at = None
        self._return_code = None

    def start(self):
        with self._lock:
            self._refresh_locked()
            if self._process and self._process.poll() is None:
                return self.status()

            self._started_at = datetime.now()
            self._finished_at = None
            self._return_code = None
            sync_config = get_sync_config_path()
            sync_log = get_sync_log_path()
            sync_log.parent.mkdir(parents=True, exist_ok=True)
            sync_log.write_text("", encoding="utf-8")
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.IE_db",
                    "--config",
                    str(sync_config),
                    "--work-dir",
                    str(APP_DIR),
                    "--log",
                    str(sync_log),
                ],
                cwd=APP_DIR.parent,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return self.status()

    def status(self):
        with self._lock:
            self._refresh_locked()
            running = self._process is not None and self._process.poll() is None
            return {
                "running": running,
                "started_at": self._format_datetime(self._started_at),
                "finished_at": self._format_datetime(self._finished_at),
                "return_code": self._return_code,
                "log_path": str(get_sync_log_path()),
                "log_tail": self._log_tail(),
                "station_statuses": self._station_statuses(running),
            }

    def _refresh_locked(self):
        if not self._process:
            return

        return_code = self._process.poll()
        if return_code is None:
            return

        if self._return_code is None:
            self._return_code = return_code
            self._finished_at = datetime.now()

    def _latest_run_lines(self):
        sync_log = get_sync_log_path()
        if not sync_log.exists():
            return []

        with open(sync_log, "r", encoding="utf-8", errors="replace") as file:
            lines = file.readlines()

        start_index = 0
        for index, line in enumerate(lines):
            if "Iniciando FTS DWH Sync" in line:
                start_index = index

        latest_run_lines = lines[start_index:]
        return [line.rstrip("\n") for line in latest_run_lines]

    def _log_tail(self, max_lines=160):
        latest_run_lines = self._latest_run_lines()
        return [line.rstrip("\n") for line in latest_run_lines[-max_lines:]]

    def _station_statuses(self, running):
        statuses = {}
        current_station = None

        for line in self._latest_run_lines():
            message = self._log_message(line)
            process_match = re.search(r"Procesando estacion:\s*([A-Za-z0-9_-]+)", message)
            if process_match:
                current_station = process_match.group(1)
                statuses[current_station] = "running"
                continue

            success_match = re.search(r"Finalizado OK:\s*([A-Za-z0-9_-]+)", message)
            if success_match:
                station = success_match.group(1)
                statuses[station] = "success"
                current_station = None
                continue

            error_match = re.search(r"ERROR en\s+([A-Za-z0-9_-]+):", message)
            if error_match:
                station = error_match.group(1)
                statuses[station] = "error"
                current_station = None
                continue

        if not running:
            for station, state in list(statuses.items()):
                if state == "running":
                    statuses[station] = "error"
        return statuses

    @staticmethod
    def _log_message(line):
        return re.sub(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\[[A-Z]+\]\s*", "", line or "")

    @staticmethod
    def _format_datetime(value):
        if value is None:
            return None
        return value.isoformat(sep=" ", timespec="seconds")


sync_runner = SyncRunner()
