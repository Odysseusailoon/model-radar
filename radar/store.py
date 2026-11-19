"""Private, atomic run snapshots; shared by CLI and the optional web app."""
from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path


class ScanBusy(Exception):
    pass


class Store:
    def __init__(self, directory):
        self.root = Path(directory)

    def _path(self, run_id):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("invalid run ID")
        return self.root / "runs" / f"{run_id}.json"

    def save(self, run):
        self._atomic(self._path(run["id"]), run)

    def seen(self):
        path = self.root / "seen.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def save_seen(self, seen):
        self._atomic(self.root / "seen.json", seen)

    @staticmethod
    def _atomic(target, data):
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".run-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def get(self, run_id):
        return json.loads(self._path(run_id).read_text())

    def recent(self, limit=20):
        if not (self.root / "runs").exists():
            return []
        paths = sorted((self.root / "runs").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [json.loads(p.read_text()) for p in paths[:limit]]

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.root / ".scan.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ScanBusy("another scan is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
