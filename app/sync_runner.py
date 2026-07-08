import subprocess
import sys
import threading
import os
from datetime import datetime
from pathlib import Path

from app.config import load_env_file


APP_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = APP_DIR / "IE_db.py"
DEFAULT_SYNC_LOG = APP_DIR / "sync.log"


def get_sync_log_path():
    load_env_file()
    configured_path = os.getenv("SYNC_LOG_PATH")
    if configured_path:
        log_path = Path(configured_path)
        if log_path.is_absolute():
            return log_path
        return (APP_DIR.parent / log_path).resolve()

    reports_dir = APP_DIR.parent / "reports"
    if reports_dir.exists():
        return reports_dir / "sync.log"

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

    def _log_tail(self, max_lines=40):
        sync_log = get_sync_log_path()
        if not sync_log.exists():
            return []

        with open(sync_log, "r", encoding="utf-8", errors="replace") as file:
            lines = file.readlines()

        return [line.rstrip("\n") for line in lines[-max_lines:]]

    @staticmethod
    def _format_datetime(value):
        if value is None:
            return None
        return value.isoformat(sep=" ", timespec="seconds")


sync_runner = SyncRunner()
