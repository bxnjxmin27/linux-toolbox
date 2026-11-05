"""Screenshots der Oberfläche (offscreen) – nutzt QQuickWindow.grabWindow."""
import json, os, sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QObject, QTimer, QUrl, QMetaObject, Q_ARG, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from toolbox.backend import Backend
from toolbox.icons import IconProvider

app = QGuiApplication(sys.argv)
b = Backend(); e = QQmlApplicationEngine(); e.addImageProvider("icons", IconProvider())
e.rootContext().setContextProperty("backend", b); e.rootContext().setContextProperty("iconDir", "")
e.load(QUrl.fromLocalFile(str(ROOT / "qml" / "Main.qml")))
w = e.rootObjects()[0]
tools = {t["id"]: t for t in json.loads(b.toolsJson)}
steps = []  # (delay, fn)

def shot(name):
    return lambda: w.grabWindow().save(f"/tmp/shot-{name}.png")
def home(sec="all"):
    return lambda: (w.setProperty("currentTool", None), w.setProperty("section", sec))
def opent(tid):
    return lambda: (w.setProperty("pageTool", tools[tid]), w.setProperty("currentTool", tools[tid]))
def setval(key, val):
    def f():
        page = w.findChild(QObject, "toolPage")
        QMetaObject.invokeMethod(page, "setVal", Qt.DirectConnection, Q_ARG("QVariant", key), Q_ARG("QVariant", val))
    return f
def palette():
    return lambda: QMetaObject.invokeMethod(w.findChild(QObject, "palette"), "open")

for spec in sys.argv[1:]:
    kind, _, arg = spec.partition(":")
    if kind == "home": steps += [(300, home(arg or "all")), (400, shot("home-" + (arg or "all")))]
    elif kind == "tool": steps += [(300, opent(arg)), (500, shot("tool-" + arg))]
    elif kind == "annotate":
        steps += [(300, opent(arg)), (300, setval("file", ["/tmp/sample.png"])), (700, shot("tool-" + arg))]
t = 500
for d, fn in steps:
    t += d
    QTimer.singleShot(t, fn)
QTimer.singleShot(t + 400, app.quit)
app.exec()
