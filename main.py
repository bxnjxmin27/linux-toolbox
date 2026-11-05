#!/usr/bin/env python3
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QSG_RHI_BACKEND", "opengl")


def main():
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from toolbox.backend import Backend

    app = QGuiApplication(sys.argv)
    app.setApplicationName("Toolbox")
    app.setDesktopFileName("linux-toolbox")
    app.setWindowIcon(QIcon(str(ROOT / "assets" / "toolbox.svg")))

    backend = Backend()
    engine = QQmlApplicationEngine()
    from toolbox.icons import IconProvider
    engine.addImageProvider("icons", IconProvider())
    ctx = engine.rootContext()
    ctx.setContextProperty("backend", backend)
    ctx.setContextProperty("iconDir", QUrl.fromLocalFile(str(ROOT / "assets" / "icons")).toString())
    engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "Main.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
