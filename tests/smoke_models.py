"""Tests mit Modell-Downloads (Netzwerk nötig): OCR, Übersetzung, Sprachausgabe, Freistellen, Gesichter, Transkription."""
import os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
tmp = Path(tempfile.mkdtemp(prefix="toolbox-models-"))
os.environ["XDG_CONFIG_HOME"] = str(tmp / "cfg")
from toolbox import settings
settings._cache = dict(settings.DEFAULTS, output_dir=str(tmp / "out"), whisper_model="tiny")
from toolbox.backend import _load_tools
from toolbox.context import Ctx
from toolbox.registry import TOOLS
_load_tools()
only = sys.argv[1:] 
def run(tid, **kw):
    if only and tid not in only: return
    t = TOOLS[tid]; ctx = Ctx(t.name, lambda v: None, lambda s: print("   ·", s[:90]))
    try:
        r = t.fn(ctx, **kw)
        print(f"OK   {tid:12} files={[Path(p).name for p in ctx.outputs]} {(r if isinstance(r, str) else (r or {}).get('text',''))[:160]!r}")
    except Exception as e:
        print(f"FAIL {tid:12} {type(e).__name__}: {str(e)[:400]}")
from PIL import Image, ImageDraw, ImageFont
img = Image.new("RGB", (900, 300), "white"); d = ImageDraw.Draw(img)
f = ImageFont.truetype(__import__("toolbox.tools.images", fromlist=["x"]).system_font_path(True), 44); d.text((30, 40), "Rechnung Nr. 4711", font=f, fill="black"); d.text((30, 130), "Max Mustermann, Berlin", font=f, fill="black")
p_img = tmp / "text.png"; img.save(p_img)
subprocess.run(["espeak-ng", "-v", "de", "-w", str(tmp / "speech.wav"), "Guten Tag, dies ist ein kurzer Test der Transkription."], check=True)
run("ocr", files=[str(p_img)])
run("translate", text="Guten Morgen. Wie geht es dir heute?", files=[], src="de", dst="en")
run("tts", text="Hallo, das ist ein Test.", files=[], lang="de", speed=1.0, fmt="wav")
run("transcribe", files=[str(tmp / "speech.wav")], lang="de", fmt="txt", model="")
run("remove-bg", files=[str(p_img)], bg="transparent", color="#00b140", quality="fast", crop=False)
run("redact-img", file=[str(p_img)], terms="Mustermann", style="redact", shapes="[]")
