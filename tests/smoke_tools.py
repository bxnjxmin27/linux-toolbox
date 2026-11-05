"""Rauchtest: führt die meisten Werkzeuge mit erzeugten Beispieldateien aus (ohne Netzwerk, ohne GUI)."""
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
tmp = Path(tempfile.mkdtemp(prefix="toolbox-test-"))
os.environ["XDG_CONFIG_HOME"] = str(tmp / "cfg")
os.environ["XDG_DATA_HOME"] = str(ROOT / ".testdata") if False else os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))

from toolbox import settings  # noqa: E402
settings._cache = dict(settings.DEFAULTS, output_dir=str(tmp / "out"))
from toolbox.backend import _load_tools  # noqa: E402
from toolbox.context import Ctx  # noqa: E402
from toolbox.registry import TOOLS  # noqa: E402

_load_tools()
S = tmp / "samples"
S.mkdir()
sh = lambda *a: subprocess.run(a, check=True, capture_output=True)  # noqa: E731
sh("ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=4", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
   "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(S / "a.mp4"))
sh("ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(S / "b.mp4"))
sh("ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=3", str(S / "a.wav"))
from PIL import Image, ImageDraw  # noqa: E402
im = Image.new("RGB", (800, 600), "#e8e0d0")
d = ImageDraw.Draw(im)
d.rectangle([60, 60, 740, 540], fill="#ffffff", outline="#222222", width=4)
d.text((100, 120), "Hello World Max Mustermann", fill="black")
im.save(S / "a.png")
im.save(S / "b.jpg")
import pymupdf  # noqa: E402
doc = pymupdf.open()
for i in range(3):
    pg = doc.new_page()
    pg.insert_text((72, 100), f"Seite {i + 1} Max Mustermann max@example.com", fontsize=14)
doc.save(S / "a.pdf")
(S / "a.txt").write_text("Das ist ein Test. Hallo Welt!\nZweite Zeile mit Inhalt.")
(S / "a.md").write_text("# Titel\n\nText mit **fett** und `code`.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")

P = lambda n: [str(S / n)]  # noqa: E731
CASES = {
    "json": dict(text='{"b":1,"a":[1,2]}', mode="pretty2", sort=True),
    "base64": dict(text="hallo", mode="enc", url=False),
    "hash": dict(text="abc", file=[], upper=False),
    "uuid": dict(ver="7", n=3, upper=False, nodash=False),
    "timestamp": dict(text="1767225600", now=False),
    "diff": dict(a="a\nb", b="a\nc", ignore_ws=False),
    "regex": dict(pattern=r"(\w+)@", text="max@x.de", flags=""),
    "links": dict(text="https://example.com/a?utm_source=x&id=5&fbclid=zz"),
    "coords": dict(text="52.52, 13.405"),
    "unicode": dict(text="Hä👋"),
    "lorem": dict(unit="p", n=2, start=True),
    "wordcount": dict(text="Ein Test mit Wörtern. Noch ein Satz."),
    "case": dict(text="hello world", mode="snake"),
    "mediainfo": dict(file=P("a.mp4")),
    "vtrim": dict(video=P("a.mp4"), start="0:01", end="0:03", precise=True),
    "vcompress": dict(files=P("a.mp4"), level="small", codec="h264", maxh="0"),
    "vconvert": dict(files=P("a.mp4"), fmt="webm"),
    "vresize": dict(files=P("a.mp4"), preset="480", w=0, h=0),
    "vcrop": dict(video=P("a.mp4"), crop="1:1", rot="90", flip="none"),
    "vmute": dict(files=P("a.mp4")),
    "vgif": dict(video=P("a.mp4"), start="0:00", dur=2, fps=10, width="320"),
    "speed": dict(files=P("a.mp4"), factor=2.0),
    "frames": dict(video=P("a.mp4"), mode="every", sec=1, at="0:01", fmt="jpg"),
    "vconcat": dict(files=[str(S / "a.mp4"), str(S / "b.mp4")], size="first"),
    "replace-audio": dict(video=P("b.mp4"), audio=P("a.wav"), shortest=True, mix=False),
    "denoise": dict(files=P("a.wav"), strength="mid", hum=True, norm=True),
    "atrim": dict(file=P("a.wav"), start="0:01", end="0:02", fade=True),
    "aextract": dict(files=P("a.mp4"), fmt="mp3"),
    "aconvert": dict(files=P("a.wav"), fmt="flac", q="high"),
    "beautify": dict(files=P("a.png"), bg="sunset", color="#000000", bgimg=[], pad=8, radius=2.5, shadow=60, ratio="16:9"),
    "iconvert": dict(files=P("a.png"), fmt="webp", q=90, q2=85),
    "icompress": dict(files=P("b.jpg"), q=70, maxside="0", fmt="same"),
    "iresize": dict(files=P("a.png"), mode="side", side=400, pct=50, w=1, h=1, fit="cover"),
    "irotate": dict(files=P("a.png"), rot="90", flip="h"),
    "strip-meta": dict(files=P("b.jpg"), show=True),
    "colorpick": dict(mode="image", img=P("a.png")),
    "annotate": dict(file=P("a.png"), shapes='[{"t":"arrow","x1":0.1,"y1":0.1,"x2":0.5,"y2":0.5,"color":"#ff3b30","width":0.005},'
                                              '{"t":"text","x":0.2,"y":0.6,"text":"Hallo","size":0.05,"color":"#0000ff"},'
                                              '{"t":"num","x":0.8,"y":0.2,"n":1,"color":"#ff3b30","size":0.03},'
                                              '{"t":"rect","x":0.1,"y":0.7,"w":0.3,"h":0.2,"color":"#00aa00","width":0.004}]'),
    "redact-img": dict(file=P("a.png"), terms="", style="redact", shapes='[{"t":"redact","x":0.1,"y":0.1,"w":0.3,"h":0.2}]'),
    "pdf-merge": dict(files=[str(S / "a.pdf"), str(S / "a.png")]),
    "pdf-split": dict(file=P("a.pdf"), mode="each", ranges="", every=1),
    "pdf-organize": dict(file=P("a.pdf"), order="3,1", rot="1:90"),
    "pdf-delete": dict(file=P("a.pdf"), pages="2"),
    "pdf-extract": dict(file=P("a.pdf"), pages="1-2"),
    "img2pdf": dict(files=P("a.png"), size="a4", margin=5, orient="auto"),
    "pdf-compress": dict(files=P("a.pdf"), level="ebook"),
    "pdf-lock": dict(file=P("a.pdf"), pw="geheim123", noprint=False, nocopy=True),
    "pdf2img": dict(file=P("a.pdf"), pages="1", fmt="png", dpi="100"),
    "redact-pdf": dict(file=P("a.pdf"), terms="Mustermann", auto="email", flatten=False, strip=True),
    "sign-pdf": dict(file=P("a.pdf"), kind="text", name="Max Mustermann", sig=[], page="last", n=1, pos="br", size=25, date=True),
    "fill-pdf": dict(file=P("a.pdf"), list=False, fields="", free="1; 10; 10; Hallo", size=11, flatten=True),
    "md2pdf": dict(files=P("a.md"), text=""),
    "scan": dict(files=P("a.png"), mode="color", ocr=False),
    "qr": dict(mode="make", kind="text", text="https://example.com", ssid="", pw="", sec="WPA", addr="", tel="", name="", vtel="", vmail="",
               fg="#000000", bg="#ffffff", fmt="png", img=[]),
    "rename": dict(files=[str(S / "a.png"), str(S / "b.jpg")], find="", repl="", regex=False, prefix="x_", suffix="", num="after", start=1,
                   start2=1, start3=1, digits=3, date="none", case="keep", spaces=False, dry=False, inplace=False),
    "dupes": dict(dirs=[str(S / "a.png"), str(S / "b.jpg")], folder="", min=0, trash=False),
    "zip": dict(mode="zip", files=P("a.txt"), fmt="zip", level="5", pw="", each=False),
    "battery": dict(),
    "storage": dict(mode="scan", folder="", caches=False, browser=False, dev=False, thumbs=False, trash=False, dl=False),
    "loginitems": dict(action="list", which="", which2=""),
    "fixapp": dict(file=P("a.txt"), fix=False),
    "wifi": dict(ssid="") if False else None,
}
ok = bad = 0
for tid, params in CASES.items():
    if params is None:
        continue
    t = TOOLS[tid]
    ctx = Ctx(t.name, lambda v: None, lambda s: None)
    try:
        r = t.fn(ctx, **params)
        n = len(ctx.outputs)
        files_ok = all(Path(p).exists() for p in ctx.outputs)
        print(f"OK   {tid:14} files={n}{'' if files_ok else ' MISSING!'} {(r if isinstance(r, str) else '')[:50]!r}")
        ok += 1
    except Exception as e:  # noqa: BLE001
        bad += 1
        print(f"FAIL {tid:14} {type(e).__name__}: {str(e)[:300]}")
        if "-v" in sys.argv:
            traceback.print_exc()
print(f"\n{ok} ok, {bad} fehlgeschlagen · Ausgabe: {tmp}")
sys.exit(1 if bad else 0)
