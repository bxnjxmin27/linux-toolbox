"""Bild-Werkzeuge (Pillow, OpenCV, rembg, RapidOCR)."""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from .. import settings
from ..context import ToolError
from ..registry import F, tool

CAT = "images"
IMG = dict(filter="image")

_heif = False


def pil():
    """Pillow mit HEIC/AVIF-Unterstützung, falls vorhanden."""
    global _heif
    from PIL import Image
    if not _heif:
        _heif = True
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception:
            pass
        Image.MAX_IMAGE_PIXELS = None
    return Image


_font_cache: dict = {}


def system_font_path(bold=True) -> str | None:
    """Pfad der System-Sans (per fontconfig), damit Text auf jeder Distribution hübsch gesetzt wird."""
    key = bold
    if key not in _font_cache:
        import subprocess
        try:
            _font_cache[key] = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold" if bold else "sans"],
                                              capture_output=True, text=True, timeout=5).stdout.strip() or None
        except Exception:
            _font_cache[key] = None
    return _font_cache[key]


def open_img(path):
    Image = pil()
    from PIL import ImageOps
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        return im
    except Exception:
        raise ToolError(f"Bild nicht lesbar: {Path(path).name}")


def fetch_model(ctx, url: str, name: str) -> Path:
    """Lädt ein Modell einmalig nach ~/.local/share/linux-toolbox/models."""
    dest = settings.models_dir() / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    ctx.log(f"Lade Modell {name} (einmalig) …")
    tmp = dest.with_suffix(dest.suffix + ".part")

    def hook(b, bs, total):
        if total > 0:
            ctx.progress(min(0.5, b * bs / total * 0.5))
    urllib.request.urlretrieve(url, tmp, hook)
    tmp.rename(dest)
    return dest


def per_file(ctx, files, fn):
    n = len(files)
    for i, f in enumerate(files):
        ctx.log(Path(f).name)
        fn(f)
        ctx.progress((i + 1) / n)


def save_like(ctx, im, src, suffix_name="", fmt=None, quality=92):
    p = Path(src)
    ext = (fmt or p.suffix.lstrip(".") or "png").lower()
    ext = "jpg" if ext == "jpeg" else ext
    out = ctx.out(f"{p.stem}{suffix_name}.{ext}")
    kw = {}
    if ext == "jpg":
        im = im.convert("RGB")
        kw = dict(quality=quality, optimize=True, subsampling=0 if quality >= 90 else 2)
    elif ext == "webp":
        kw = dict(quality=quality, method=6)
    elif ext == "png":
        kw = dict(optimize=True)
    elif ext == "avif":
        kw = dict(quality=quality)
    im.save(out, **kw)
    return out


# ---------------------------------------------------------------------------
# Formen zeichnen (Beschriften / Schwärzen / Verpixeln) – gemeinsam mit dem QML-Editor
def render_shapes(im, shapes):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    import math
    im = im.convert("RGBA")
    W, H = im.size
    base = max(W, H)
    d = ImageDraw.Draw(im)

    def col(c, a=255):
        c = c.lstrip("#")
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)

    def font(sz):
        p = system_font_path(True)
        if p:
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                pass
        return ImageFont.load_default(sz)

    for s in shapes:
        t = s.get("t")
        c = col(s.get("color", "#ff3b30"))
        lw = max(2, int(s.get("width", 0.004) * base))
        if t == "rect":
            box = [s["x"] * W, s["y"] * H, (s["x"] + s["w"]) * W, (s["y"] + s["h"]) * H]
            d.rounded_rectangle(box, radius=lw * 1.5, outline=c, width=lw,
                                fill=col(s["color"], 60) if s.get("fill") else None)
        elif t == "ellipse":
            d.ellipse([s["x"] * W, s["y"] * H, (s["x"] + s["w"]) * W, (s["y"] + s["h"]) * H], outline=c, width=lw)
        elif t in ("arrow", "line"):
            x1, y1, x2, y2 = s["x1"] * W, s["y1"] * H, s["x2"] * W, s["y2"] * H
            d.line([x1, y1, x2, y2], fill=c, width=lw)
            if t == "arrow":
                ang = math.atan2(y2 - y1, x2 - x1)
                hl = lw * 5
                for da in (math.radians(150), -math.radians(150)):
                    d.line([x2, y2, x2 + hl * math.cos(ang + da), y2 + hl * math.sin(ang + da)], fill=c, width=lw)
        elif t == "pen":
            pts = [(p[0] * W, p[1] * H) for p in s.get("pts", [])]
            if len(pts) > 1:
                d.line(pts, fill=c, width=lw, joint="curve")
        elif t == "text":
            sz = max(10, int(s.get("size", 0.04) * H))
            f = font(sz)
            x, y = s["x"] * W, s["y"] * H
            txt = s.get("text", "")
            bb = d.textbbox((x, y), txt, font=f)
            if s.get("bg"):
                d.rounded_rectangle([bb[0] - sz * .3, bb[1] - sz * .15, bb[2] + sz * .3, bb[3] + sz * .15],
                                    radius=sz * .25, fill=col(s["bg"]))
            d.text((x, y), txt, font=f, fill=c)
        elif t == "num":
            r = max(12, int(s.get("size", 0.03) * H))
            x, y = s["x"] * W, s["y"] * H
            d.ellipse([x - r, y - r, x + r, y + r], fill=c)
            d.text((x, y), str(s.get("n", 1)), font=font(int(r * 1.2)), fill=(255, 255, 255, 255), anchor="mm")
        elif t in ("redact", "blur", "pixel"):
            x0, y0 = max(0, int(s["x"] * W)), max(0, int(s["y"] * H))
            x1, y1 = min(W, int((s["x"] + s["w"]) * W)), min(H, int((s["y"] + s["h"]) * H))
            if x1 <= x0 or y1 <= y0:
                continue
            region = im.crop((x0, y0, x1, y1))
            if t == "redact":
                im.paste((0, 0, 0, 255), (x0, y0, x1, y1))
            elif t == "blur":
                im.paste(region.filter(ImageFilter.GaussianBlur(max(6, (y1 - y0) // 6))), (x0, y0))
            else:
                k = max(6, (y1 - y0) // 8)
                sm = region.resize((max(1, (x1 - x0) // k), max(1, (y1 - y0) // k)), Image.BILINEAR)
                im.paste(sm.resize(region.size, Image.NEAREST), (x0, y0))
            d = ImageDraw.Draw(im)
    return im


def parse_shapes(js):
    try:
        v = json.loads(js) if isinstance(js, str) else js
        return v or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
@tool("blur-faces", "Gesichter verpixeln", CAT, "Finde Gesichter in Fotos und zeichne sie weich, verpixle oder schwärze sie.",
      "scan-face",
      [F("files", "files", "Bilder", **IMG),
       F("mode", "choice", "Art", "blur", options=[["blur", "Weichzeichnen"], ["pixel", "Verpixeln"], ["black", "Schwärzen"]]),
       F("pad", "slider", "Rand um das Gesicht", 20, min=0, max=60, step=5, placeholder=" %"),
       F("sens", "choice", "Empfindlichkeit", "mid", options=[["low", "Streng"], ["mid", "Normal"], ["high", "Großzügig"]])],
      keywords="anonymisieren datenschutz gesicht")
def blur_faces(ctx, files, mode, pad, sens):
    import cv2
    import numpy as np
    from PIL import Image, ImageFilter
    model = fetch_model(ctx, "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
                             "face_detection_yunet_2023mar.onnx", "yunet.onnx")
    thr = {"low": 0.85, "mid": 0.7, "high": 0.5}[sens]
    total = 0

    def one(f):
        nonlocal total
        im = open_img(f).convert("RGB")
        arr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
        h, w = arr.shape[:2]
        det = cv2.FaceDetectorYN.create(str(model), "", (w, h), thr, 0.3, 5000)
        _, faces = det.detect(arr)
        faces = [] if faces is None else faces
        for fc in faces:
            x, y, bw, bh = fc[:4]
            px, py = bw * pad / 100, bh * pad / 100
            x0, y0 = int(max(0, x - px)), int(max(0, y - py))
            x1, y1 = int(min(w, x + bw + px)), int(min(h, y + bh + py))
            reg = im.crop((x0, y0, x1, y1))
            if mode == "black":
                im.paste((0, 0, 0), (x0, y0, x1, y1))
            elif mode == "blur":
                im.paste(reg.filter(ImageFilter.GaussianBlur(max(8, (y1 - y0) // 4))), (x0, y0))
            else:
                k = max(8, (y1 - y0) // 8)
                sm = reg.resize((max(1, (x1 - x0) // k), max(1, (y1 - y0) // k)), Image.BILINEAR)
                im.paste(sm.resize(reg.size, Image.NEAREST), (x0, y0))
        total += len(faces)
        save_like(ctx, im, f, " verpixelt")
    per_file(ctx, files, one)
    return {"message": f"Fertig · {total} Gesicht{'er' if total != 1 else ''} bearbeitet"}


GRADIENTS = [["sunset", "Sonnenuntergang"], ["ocean", "Ozean"], ["aurora", "Aurora"], ["peach", "Pfirsich"],
             ["night", "Nacht"], ["mint", "Minze"], ["solid", "Einfarbig"], ["image", "Eigenes Bild"]]
_GR = {"sunset": ("#ff7e5f", "#feb47b", "#ff5e8a"), "ocean": ("#2193b0", "#6dd5ed", "#3a47d5"),
       "aurora": ("#00c9a7", "#845ec2", "#2c73d2"), "peach": ("#ffecd2", "#fcb69f", "#ff9a9e"),
       "night": ("#0f2027", "#203a43", "#2c5364"), "mint": ("#a8edea", "#fed6e3", "#8fd3f4")}


@tool("beautify", "Bildschirmfoto verschönern", CAT, "Setze Bildschirmfotos auf einen weichen Hintergrund mit Innenabstand, "
      "abgerundeten Ecken und Schatten.", "sparkles",
      [F("files", "files", "Bildschirmfotos", **IMG),
       F("bg", "choice", "Hintergrund", "sunset", options=GRADIENTS),
       F("color", "color", "Farbe", "#7c6cff", showIf="bg=solid"),
       F("bgimg", "file", "Hintergrundbild", filter="image", showIf="bg=image", optional=True),
       F("pad", "slider", "Abstand", 8, min=0, max=25, step=1, placeholder=" %"),
       F("radius", "slider", "Eckenradius", 2.5, min=0, max=8, step=0.5, placeholder=" %"),
       F("shadow", "slider", "Schatten", 60, min=0, max=100, step=5, placeholder=" %"),
       F("ratio", "choice", "Format", "auto", options=[["auto", "Auto"], ["16:9", "16:9 (X)"], ["4:5", "4:5 (Instagram)"],
                                                     ["1:1", "1:1"], ["9:16", "9:16"]])],
      keywords="screenshot hintergrund schatten mockup")
def beautify(ctx, files, bg, color, bgimg, pad, radius, shadow, ratio):
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    def gradient(w, h, cols):
        import numpy as np
        c = [tuple(int(x.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) for x in cols]
        yy, xx = np.mgrid[0:h, 0:w]
        t = (xx / w * 0.6 + yy / h * 0.4)
        t = np.clip(t, 0, 1)[..., None]
        a, b, cc = (np.array(v, dtype=float) for v in c)
        out = np.where(t < 0.5, a + (b - a) * (t * 2), b + (cc - b) * ((t - 0.5) * 2))
        return Image.fromarray(out.astype("uint8"), "RGB")

    def one(f):
        im = open_img(f).convert("RGBA")
        w0, h0 = im.size
        p = int(max(w0, h0) * pad / 100)
        W, H = w0 + 2 * p, h0 + 2 * p
        if ratio != "auto":
            a, b = (int(x) for x in ratio.split(":"))
            if W / H < a / b:
                W = int(H * a / b)
            else:
                H = int(W * b / a)
        if bg == "solid":
            canvas = Image.new("RGBA", (W, H), color)
        elif bg == "image" and bgimg:
            bi = open_img(bgimg[0]).convert("RGBA")
            s = max(W / bi.width, H / bi.height)
            bi = bi.resize((int(bi.width * s) + 1, int(bi.height * s) + 1), Image.LANCZOS)
            canvas = bi.crop(((bi.width - W) // 2, (bi.height - H) // 2, (bi.width - W) // 2 + W, (bi.height - H) // 2 + H))
        else:
            canvas = gradient(W, H, _GR.get(bg, _GR["sunset"])).convert("RGBA")
        r = int(max(w0, h0) * radius / 100)
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w0 - 1, h0 - 1], radius=r, fill=255)
        im.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
        x, y = (W - w0) // 2, (H - h0) // 2
        if shadow:
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            blur = max(10, int(max(w0, h0) * 0.025))
            sm = Image.new("L", (W, H), 0)
            sm.paste(mask.point(lambda v: int(v * shadow / 100 * 0.75)), (x, y + blur // 2))
            sh.putalpha(sm.filter(ImageFilter.GaussianBlur(blur)))
            canvas = Image.alpha_composite(canvas, sh)
        canvas.alpha_composite(im, (x, y))
        save_like(ctx, canvas, f, " schön", "png")
    per_file(ctx, files, one)


@tool("remove-bg", "Hintergrund entfernen", CAT, "Stelle das Motiv in Fotos frei – komplett auf deinem Rechner.", "eraser",
      [F("files", "files", "Fotos oder Ordner-Inhalt", **IMG),
       F("bg", "choice", "Hintergrund", "transparent", options=[["transparent", "Transparent"], ["white", "Weiß"],
                                                               ["color", "Eigene Farbe"]]),
       F("color", "color", "Farbe", "#00b140", showIf="bg=color"),
       F("quality", "choice", "Modell", "fast", options=[["fast", "Schnell"], ["best", "Beste Qualität"]],
         hint="Das Modell wird beim ersten Mal einmalig geladen."),
       F("crop", "bool", "Auf das Motiv zuschneiden", False)],
      keywords="freistellen background removal")
def remove_bg(ctx, files, bg, color, quality, crop):
    os.environ["U2NET_HOME"] = str(settings.models_dir() / "rembg")
    from rembg import new_session, remove
    from PIL import Image
    ctx.log("Lade Modell …")
    session = new_session("isnet-general-use" if quality == "best" else "u2netp")

    def one(f):
        im = open_img(f).convert("RGBA")
        cut = remove(im, session=session)
        if crop:
            bb = cut.getchannel("A").getbbox()
            if bb:
                cut = cut.crop(bb)
        if bg != "transparent":
            base = Image.new("RGBA", cut.size, "#ffffff" if bg == "white" else color)
            base.alpha_composite(cut)
            cut = base
        save_like(ctx, cut, f, " freigestellt", "png" if bg == "transparent" else "png")
    per_file(ctx, files, one)


@tool("iconvert", "Bilder umwandeln", CAT, "Wandle Bilder in PNG, JPG, WebP, AVIF oder andere Formate um.", "repeat",
      [F("files", "files", "Bilder", **IMG),
       F("fmt", "choice", "Zielformat", "webp", options=[["png", "PNG"], ["jpg", "JPG"], ["webp", "WebP"], ["avif", "AVIF"],
                                                       ["bmp", "BMP"], ["tiff", "TIFF"], ["gif", "GIF"], ["ico", "ICO"]]),
       F("q", "slider", "Qualität", 90, min=40, max=100, step=1, showIf="fmt=jpg"),
       F("q2", "slider", "Qualität", 90, min=40, max=100, step=1, showIf="fmt=webp")],
      keywords="heic png jpg webp konvertieren")
def iconvert(ctx, files, fmt, q, q2):
    def one(f):
        im = open_img(f)
        if fmt == "ico":
            out = ctx.out(Path(f).stem + ".ico")
            im.convert("RGBA").save(out, sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= max(im.size)] or [(16, 16)])
        else:
            save_like(ctx, im, f, "", fmt, int(q if fmt == "jpg" else q2))
    per_file(ctx, files, one)


@tool("icompress", "Bilder komprimieren", CAT, "Verkleinere Bilder und behalte die Qualität.", "file-down",
      [F("files", "files", "Bilder", **IMG),
       F("q", "slider", "Qualität", 80, min=30, max=95, step=1),
       F("maxside", "choice", "Längste Seite", "0", options=[["0", "Original"], ["3840", "4K"], ["2560", "2560"],
                                                            ["1920", "1920"], ["1280", "1280"]]),
       F("fmt", "choice", "Format", "same", options=[["same", "Wie Original"], ["webp", "WebP"], ["jpg", "JPG"]])],
      keywords="verkleinern größe")
def icompress(ctx, files, q, maxside, fmt):
    Image = pil()
    before = after = 0

    def one(f):
        nonlocal before, after
        im = open_img(f)
        if maxside != "0":
            im.thumbnail((int(maxside), int(maxside)), Image.LANCZOS)
        ext = Path(f).suffix.lstrip(".").lower()
        out = save_like(ctx, im, f, " klein", None if fmt == "same" else fmt, int(q))
        before += Path(f).stat().st_size
        after += Path(out).stat().st_size
    per_file(ctx, files, one)
    pct = round((1 - after / before) * 100) if before else 0
    return {"message": f"{before / 1e6:.1f} MB → {after / 1e6:.1f} MB  (−{pct} %)"}


@tool("iresize", "Bildgröße ändern", CAT, "Skaliere Bilder auf eine neue Größe.", "maximize-2",
      [F("files", "files", "Bilder", **IMG),
       F("mode", "choice", "Art", "side", options=[["side", "Längste Seite"], ["pct", "Prozent"], ["exact", "Genau (Breite × Höhe)"]]),
       F("side", "number", "Pixel", 1920, min=16, max=20000, showIf="mode=side"),
       F("pct", "slider", "Prozent", 50, min=5, max=300, step=5, showIf="mode=pct"),
       F("w", "number", "Breite", 1080, min=1, max=20000, showIf="mode=exact"),
       F("h", "number", "Höhe", 1080, min=1, max=20000, showIf="mode=exact"),
       F("fit", "choice", "Bei „Genau“", "cover", options=[["cover", "Zuschneiden"], ["contain", "Einpassen"], ["stretch", "Strecken"]],
         showIf="mode=exact")],
      keywords="skalieren größe pixel")
def iresize(ctx, files, mode, side, pct, w, h, fit):
    Image = pil()
    from PIL import ImageOps

    def one(f):
        im = open_img(f)
        if mode == "side":
            s = side / max(im.size)
            im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
        elif mode == "pct":
            im = im.resize((max(1, round(im.width * pct / 100)), max(1, round(im.height * pct / 100))), Image.LANCZOS)
        else:
            size = (int(w), int(h))
            if fit == "cover":
                im = ImageOps.fit(im, size, Image.LANCZOS)
            elif fit == "contain":
                im = ImageOps.pad(im, size, Image.LANCZOS, color=(0, 0, 0, 0) if im.mode == "RGBA" else "#000000")
            else:
                im = im.resize(size, Image.LANCZOS)
        save_like(ctx, im, f, f" {im.width}x{im.height}")
    per_file(ctx, files, one)


@tool("irotate", "Bilder drehen", CAT, "Drehe oder spiegle Bilder.", "rotate-cw",
      [F("files", "files", "Bilder", **IMG),
       F("rot", "choice", "Drehen", "90", options=[["0", "Nicht drehen"], ["90", "90° rechts"], ["180", "180°"], ["270", "90° links"]]),
       F("flip", "choice", "Spiegeln", "none", options=[["none", "Nein"], ["h", "Horizontal"], ["v", "Vertikal"]])])
def irotate(ctx, files, rot, flip):
    Image = pil()

    def one(f):
        im = open_img(f)
        if rot != "0":
            im = im.rotate(-int(rot), expand=True)
        if flip == "h":
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        elif flip == "v":
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        save_like(ctx, im, f, " gedreht")
    per_file(ctx, files, one)


@tool("strip-meta", "Metadaten entfernen", CAT, "Entferne Orts-, Kamera- und Datumsinfos aus Fotos.", "shield-off",
      [F("files", "files", "Fotos", **IMG),
       F("show", "bool", "Vorher gefundene Daten im Bericht nennen", True)],
      keywords="exif gps datenschutz privatsphäre")
def strip_meta(ctx, files, show):
    Image = pil()
    found = []

    def one(f):
        src = Image.open(f)
        exif = src.getexif()
        if show and exif:
            tags = []
            from PIL.ExifTags import TAGS
            for k, v in exif.items():
                n = TAGS.get(k, str(k))
                if n in ("Make", "Model", "DateTime", "Software", "GPSInfo", "LensModel"):
                    tags.append(n)
            if exif.get_ifd(0x8825):
                tags.append("GPS")
            found.append(f"{Path(f).name}: {', '.join(sorted(set(tags))) or 'EXIF'}")
        clean = Image.new(src.mode if src.mode != "P" else "RGBA", src.size)
        clean.paste(src.convert(clean.mode))
        ext = Path(f).suffix.lstrip(".").lower()
        out = ctx.out(f"{Path(f).stem} ohne Metadaten.{ext or 'png'}")
        clean.save(out, quality=95) if ext in ("jpg", "jpeg") else clean.save(out)
    per_file(ctx, files, one)
    return {"message": "Fertig · Metadaten entfernt", "text": "\n".join(found)} if found else None


@tool("colorpick", "Farbauswahl", CAT, "Wähle eine Farbe vom Bildschirm oder hole die Palette aus einem Bild.", "pipette",
      [F("mode", "choice", "Quelle", "screen", options=[["screen", "Vom Bildschirm"], ["image", "Aus Bild (Palette)"]]),
       F("img", "file", "Bild", filter="image", showIf="mode=image", optional=True)],
      output="text", keywords="farbe pipette hex rgb")
def colorpick(ctx, mode, img):
    def fmt(rgb):
        import colorsys
        r, g, b = rgb
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        return f"#{r:02X}{g:02X}{b:02X}   rgb({r}, {g}, {b})   hsl({round(h * 360)}, {round(s * 100)}%, {round(l * 100)}%)"
    if mode == "screen":
        from ..portal import pick_color
        ctx.log("Klicke auf eine Stelle des Bildschirms …")
        return fmt(pick_color())
    if not img:
        raise ToolError("Wähle ein Bild.")
    im = open_img(img[0]).convert("RGB")
    im.thumbnail((200, 200))
    q = im.quantize(colors=8, method=2).convert("RGB")
    cols = sorted(q.getcolors(), reverse=True)
    return "\n".join(fmt(c) for _, c in cols)


@tool("redact-img", "Bild schwärzen", CAT, "Schwärze oder verpixele Bereiche in einem Bild – von Hand oder per Texterkennung.",
      "square-dashed-mouse-pointer",
      [F("file", "file", "Bild", **IMG),
       F("terms", "textarea", "Text automatisch schwärzen (ein Begriff pro Zeile)", "",
         placeholder="Max Mustermann\nDE89 3704 …"),
       F("style", "choice", "Art", "redact", options=[["redact", "Schwärzen"], ["pixel", "Verpixeln"], ["blur", "Weichzeichnen"]]),
       F("shapes", "annotate", "Bereiche markieren", "[]", options=["redact", "pixel", "blur"], filter="file")],
      keywords="zensieren unkenntlich")
def redact_img(ctx, file, terms, style, shapes):
    im = open_img(file[0]).convert("RGBA")
    W, H = im.size
    sh = [dict(s, t=style) if s.get("t") in ("redact", "pixel", "blur") else s for s in parse_shapes(shapes)]
    words = [t.strip().lower() for t in terms.splitlines() if t.strip()]
    if words:
        from .ocr import ocr_boxes
        for text, (x0, y0, x1, y1) in ocr_boxes(ctx, im):
            tl = text.lower()
            if any(w in tl or tl in w and len(tl) > 3 for w in words):
                pad = (y1 - y0) * 0.15
                sh.append({"t": style, "x": (x0 - pad) / W, "y": (y0 - pad) / H,
                           "w": (x1 - x0 + 2 * pad) / W, "h": (y1 - y0 + 2 * pad) / H})
    if not sh:
        raise ToolError("Markiere Bereiche im Bild oder gib Begriffe an.")
    save_like(ctx, render_shapes(im, sh), file[0], " geschwärzt")
    return {"message": f"Fertig · {len(sh)} Bereich{'e' if len(sh) != 1 else ''} bearbeitet"}


@tool("annotate", "Bildschirmfoto beschriften", CAT, "Füge Pfeile, Rahmen, Text und Nummern zu Bildern hinzu.", "pen-line",
      [F("file", "file", "Bild", **IMG),
       F("shapes", "annotate", "Beschriften", "[]", options=["arrow", "rect", "ellipse", "text", "num", "pen", "blur"], filter="file")],
      keywords="markieren pfeil text")
def annotate(ctx, file, shapes):
    sh = parse_shapes(shapes)
    if not sh:
        raise ToolError("Zeichne mindestens eine Beschriftung ins Bild.")
    save_like(ctx, render_shapes(open_img(file[0]), sh), file[0], " beschriftet")
