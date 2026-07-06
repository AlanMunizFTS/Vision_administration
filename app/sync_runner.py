import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = APP_DIR / "IE_db.py"
SYNC_CONFIG = APP_DIR / "machines.json"
SYNC_LOG = APP_DIR / "sync.log"


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
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    str(SYNC_SCRIPT),
                    "--config",
                    str(SYNC_CONFIG),
                    "--work-dir",
                    str(APP_DIR),
                    "--log",
                    str(SYNC_LOG),
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
                "log_path": str(SYNC_LOG),
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
        if not SYNC_LOG.exists():
            return []

        with open(SYNC_LOG, "r", encoding="utf-8", errors="replace") as file:
            lines = file.readlines()

        return [line.rstrip("\n") for line in lines[-max_lines:]]

    @staticmethod
    def _format_datetime(value):
        if value is None:
            return None
        return value.isoformat(sep=" ", timespec="seconds")


sync_runner = SyncRunner()
