"""Brücke zwischen QML und den Werkzeugen."""
from __future__ import annotations

import json
import subprocess
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication

from . import settings
from .context import Cancelled, Ctx, ToolError
from .registry import CATEGORIES, FILTERS, TOOLS


def _load_tools():
    # Registrierung durch Import; Module sind klein und lazy in ihren schweren Importen.
    from .tools import video, audio, images, documents, textlang, files, system, dev  # noqa: F401


class Backend(QObject):
    progressChanged = Signal(float)
    logLine = Signal(str)
    finished = Signal(str)  # JSON: {ok, message, text, files}
    runningChanged = Signal()
    overlayRequested = Signal(str)
    pickerResult = Signal(str, str)
    favoritesChanged = Signal()
    recentChanged = Signal()

    def __init__(self):
        super().__init__()
        _load_tools()
        self._running = False
        self._ctx: Ctx | None = None
        self._overlay_done = threading.Event()
        self._tools_json = json.dumps([t.to_dict() for t in TOOLS.values()], ensure_ascii=False)

    # --- Daten ---------------------------------------------------------
    @Property(str, constant=True)
    def toolsJson(self):
        return self._tools_json

    @Property(str, constant=True)
    def categoriesJson(self):
        return json.dumps([{"id": i, "name": n, "icon": ic} for i, n, ic in CATEGORIES])

    @Property(str, constant=True)
    def filtersJson(self):
        return json.dumps(FILTERS)

    @Property(bool, notify=runningChanged)
    def running(self):
        return self._running

    @Property(str, notify=favoritesChanged)
    def favorites(self):
        return json.dumps(settings.get("favorites"))

    @Property(str, notify=recentChanged)
    def recent(self):
        return json.dumps(settings.get("recent"))

    @Slot(str)
    def toggleFavorite(self, tid):
        fav = list(settings.get("favorites"))
        fav.remove(tid) if tid in fav else fav.append(tid)
        settings.put("favorites", fav)
        self.favoritesChanged.emit()

    @Slot(str)
    def markRecent(self, tid):
        rec = [t for t in settings.get("recent") if t != tid]
        rec.insert(0, tid)
        settings.put("recent", rec[:8])
        self.recentChanged.emit()

    # --- Einstellungen -------------------------------------------------
    @Slot(str, result="QVariant")
    def setting(self, key):
        return settings.get(key)

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        settings.put(key, value)

    # --- Ausführen -----------------------------------------------------
    @Slot(str, str)
    def run(self, tool_id, params_json):
        if self._running:
            return
        t = TOOLS[tool_id]
        params = json.loads(params_json)
        ctx = Ctx(t.name, self.progressChanged.emit, self.logLine.emit)
        ctx.overlay_cb = self._request_overlay
        self._ctx = ctx
        self._running = True
        self.runningChanged.emit()
        self.progressChanged.emit(0.0)

        def work():
            res = {"ok": True, "message": "", "text": "", "files": []}
            try:
                ret = t.fn(ctx, **params)
                if isinstance(ret, str):
                    res["text"] = ret
                elif isinstance(ret, dict):
                    res.update({k: v for k, v in ret.items() if k in ("text", "message")})
                res["files"] = list(ctx.outputs)
                if not res["message"]:
                    n = len(res["files"])
                    res["message"] = (f"Fertig · {n} Datei{'en' if n != 1 else ''} gespeichert"
                                      if n else "Fertig")
                res["dir"] = str(ctx._out_dir) if ctx._out_dir else ""
            except Cancelled:
                res.update(ok=False, message="Abgebrochen")
            except ToolError as e:
                res.update(ok=False, message=str(e))
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                res.update(ok=False, message=f"{type(e).__name__}: {e}")
            finally:
                self._running = False
                self._ctx = None
                self.runningChanged.emit()
                self.finished.emit(json.dumps(res, ensure_ascii=False))

        threading.Thread(target=work, daemon=True).start()

    def _request_overlay(self, kind, kw, cancel):
        self._overlay_done.clear()
        self.overlayRequested.emit(json.dumps({"kind": kind, **kw}))
        while not self._overlay_done.wait(0.2):
            if cancel.is_set():
                break

    @Slot()
    def overlayClosed(self):
        self._overlay_done.set()

    @Slot()
    def stop(self):
        if self._ctx:
            self._ctx.stop()

    @Slot()
    def cancel(self):
        if self._ctx:
            self._ctx.cancel()

    # --- Hilfen --------------------------------------------------------
    @Slot(str, str, str, bool, bool)
    def pick(self, token, title, filt, multiple, folder):
        """Natürliche Dateiauswahl über das Desktop-Portal; bei Fehler meldet ok=false (QML nutzt dann seinen eigenen Dialog)."""
        def work():
            try:
                from .portal import Portal
                p = Portal()
                try:
                    paths = p.file_chooser(title, filt, multiple, folder)
                finally:
                    p.close()
                self.pickerResult.emit(token, json.dumps({"ok": True, "paths": paths}))
            except Cancelled:
                self.pickerResult.emit(token, json.dumps({"ok": True, "paths": []}))
            except Exception:  # noqa: BLE001
                self.pickerResult.emit(token, json.dumps({"ok": False, "paths": []}))
        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def openPath(self, p):
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    @Slot(str)
    def reveal(self, p):
        path = Path(p)
        try:
            subprocess.Popen(["dbus-send", "--session", "--dest=org.freedesktop.FileManager1",
                              "--type=method_call", "/org/freedesktop/FileManager1",
                              "org.freedesktop.FileManager1.ShowItems",
                              f"array:string:{QUrl.fromLocalFile(str(path)).toString()}", "string:"])
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent if path.is_file() else path)))

    @Slot(str)
    def copy(self, text):
        QGuiApplication.clipboard().setText(text)

    @Slot(result=str)
    def clipboard(self):
        return QGuiApplication.clipboard().text()

    @Slot(str, result=str)
    def readText(self, path):
        try:
            return Path(path).read_text(errors="replace")[:2_000_000]
        except Exception:
            return ""

    @Slot(str, result=str)
    def fileName(self, p):
        return Path(p).name
