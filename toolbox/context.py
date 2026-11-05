"""Laufzeitkontext für ein Werkzeug: Ausgabeordner, Fortschritt, Prozesse, Abbruch."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import settings


class Cancelled(Exception):
    pass


class ToolError(Exception):
    """Fehler mit lesbarer Meldung für den Nutzer."""


def which(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise ToolError(f"„{name}“ ist nicht installiert. Siehe README → Abhängigkeiten.")
    return p


class Ctx:
    def __init__(self, tool_name: str, on_progress, on_log):
        self.tool_name = tool_name
        self._on_progress = on_progress
        self._on_log = on_log
        self._out_dir: Path | None = None
        self._proc: subprocess.Popen | None = None
        self._cancel = threading.Event()
        self._stop = threading.Event()
        self.outputs: list[str] = []
        self.overlay_cb = None  # setzt das Backend

    # --- Ausgabe -------------------------------------------------------
    @property
    def out_dir(self) -> Path:
        if self._out_dir is None:
            stamp = time.strftime("%Y-%m-%d %H.%M.%S")
            self._out_dir = Path(settings.get("output_dir")) / f"{stamp} {self.tool_name}"
            self._out_dir.mkdir(parents=True, exist_ok=True)
        return self._out_dir

    def out(self, name: str) -> Path:
        """Neuer Ausgabepfad (kollisionsfrei), wird als Ergebnis registriert."""
        p = self.out_dir / name
        i = 2
        while p.exists():
            p = self.out_dir / f"{Path(name).stem} {i}{Path(name).suffix}"
            i += 1
        self.outputs.append(str(p))
        return p

    def add_output(self, p):
        self.outputs.append(str(p))

    def overlay(self, kind: str, **kw):
        """Zeigt ein Vollbild-Overlay im Hauptfenster und wartet, bis es geschlossen wird."""
        if not self.overlay_cb:
            raise ToolError("Overlay nicht verfügbar.")
        self.overlay_cb(kind, kw, self._cancel)

    # --- Status --------------------------------------------------------
    def progress(self, v: float):
        self.check()
        self._on_progress(max(0.0, min(1.0, v)))

    def log(self, s: str):
        self._on_log(s)

    def check(self):
        if self._cancel.is_set():
            raise Cancelled()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def stop(self):
        """Sauber beenden (z. B. Aufnahme) – das Ergebnis bleibt erhalten."""
        self._stop.set()
        p = self._proc
        if p and p.poll() is None:
            try:
                p.send_signal(signal.SIGINT)
            except Exception:
                pass

    def cancel(self):
        self._cancel.set()
        p = self._proc
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass

    # --- Prozesse ------------------------------------------------------
    def run(self, cmd: list, parse=None, cwd=None, env=None) -> str:
        """Startet einen Prozess, liest stdout/stderr zeilenweise, wirft bei Fehler."""
        self.check()
        cmd = [str(c) for c in cmd]
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            bufsize=1, cwd=cwd, env=env, errors="replace")
        buf: list[str] = []
        assert self._proc.stdout
        for line in self._proc.stdout:
            line = line.rstrip("\n")
            buf.append(line)
            if len(buf) > 400:
                buf.pop(0)
            if parse:
                parse(line)
        rc = self._proc.wait()
        self._proc = None
        if self._cancel.is_set():
            raise Cancelled()
        if rc != 0 and not self._stop.is_set():
            tail = "\n".join(buf[-12:])
            raise ToolError(f"{Path(cmd[0]).name} ist mit Fehler {rc} beendet:\n{tail}")
        return "\n".join(buf)

    def probe(self, path) -> dict:
        out = subprocess.run(
            [which("ffprobe"), "-v", "error", "-show_format", "-show_streams",
             "-of", "json", str(path)], capture_output=True, text=True)
        if out.returncode != 0:
            raise ToolError(f"Datei nicht lesbar: {Path(path).name}")
        return json.loads(out.stdout or "{}")

    def duration(self, path) -> float:
        try:
            return float(self.probe(path)["format"]["duration"])
        except Exception:
            return 0.0

    def ffmpeg(self, args: list, duration: float = 0.0):
        """ffmpeg mit Fortschrittsanzeige."""
        cmd = [which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
               "-progress", "pipe:1", "-nostats", *map(str, args)]
        rx = re.compile(r"out_time_us=(\d+)")

        def parse(line):
            m = rx.match(line)
            if m and duration > 0:
                self._on_progress(min(0.99, int(m.group(1)) / 1e6 / duration))
        self.run(cmd, parse)
        self._on_progress(1.0)
