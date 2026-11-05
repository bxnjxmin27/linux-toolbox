"""Dokument-Werkzeuge (PyMuPDF, pikepdf, LibreOffice, OpenCV)."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..context import ToolError, which
from ..registry import F, tool
from .images import open_img, parse_shapes, pil, render_shapes

CAT = "docs"
PDF = dict(filter="pdf")


def fitz():
    import pymupdf
    return pymupdf


def open_pdf(path, password=""):
    m = fitz()
    try:
        d = m.open(path)
    except Exception:
        raise ToolError(f"PDF nicht lesbar: {Path(path).name}")
    if d.needs_pass and not d.authenticate(password or ""):
        raise ToolError(f"{Path(path).name} ist passwortgeschützt. Entferne zuerst das Passwort.")
    return d


def parse_pages(spec: str, n: int, allow_empty=False) -> list[int]:
    """„1-3,5,8-“ → [0,1,2,4,7,…] (0-basiert, Reihenfolge bleibt)."""
    spec = spec.strip().lower()
    if not spec:
        if allow_empty:
            return []
        raise ToolError("Gib Seiten an, z. B. 1-3,5,8-")
    out: list[int] = []
    for part in re.split(r"[,;\s]+", spec):
        if not part:
            continue
        if part in ("alle", "all"):
            out += list(range(n))
            continue
        m = re.fullmatch(r"(\d*)-(\d*)", part)
        if m:
            a = int(m.group(1) or 1)
            b = int(m.group(2) or n)
            step = 1 if a <= b else -1
            rng = range(a, b + step, step)
        elif part.isdigit():
            rng = [int(part)]
        else:
            raise ToolError(f"Seitenangabe nicht verständlich: „{part}“")
        for p in rng:
            if p < 1 or p > n:
                raise ToolError(f"Seite {p} gibt es nicht (das Dokument hat {n} Seiten).")
            out.append(p - 1)
    return out


def soffice(ctx, src, fmt, outname=None, filt=None):
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        raise ToolError("LibreOffice ist nicht installiert (sudo dnf install libreoffice).")
    with tempfile.TemporaryDirectory() as td:
        target = fmt if not filt else f"{fmt}:{filt}"
        ctx.run([exe, "--headless", "--norestore", f"-env:UserInstallation=file://{td}/profile", "--convert-to", target,
                 "--outdir", td, str(src)])
        res = [p for p in Path(td).iterdir() if p.is_file() and p.suffix.lstrip(".") == fmt.split(":")[0]]
        if not res:
            raise ToolError(f"Konvertierung fehlgeschlagen: {Path(src).name}")
        out = ctx.out(outname or (Path(src).stem + "." + fmt.split(":")[0]))
        shutil.move(str(res[0]), out)
        return out


def batch_files(ctx, files, fn):
    for i, f in enumerate(files):
        ctx.log(Path(f).name)
        fn(f)
        ctx.progress((i + 1) / len(files))


# ---------------------------------------------------------------------------
def _order_quad(pts):
    import numpy as np
    pts = pts.reshape(4, 2).astype("float32")
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], dtype="float32")


def scan_page(im, mode):
    import cv2
    import numpy as np
    arr = cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    scale = 900 / max(h, w)
    small = cv2.resize(arr, None, fx=scale, fy=scale)
    g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(g, 40, 140), np.ones((3, 3), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    quad = None
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:6]:
        ap = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(ap) == 4 and cv2.contourArea(ap) > 0.2 * small.shape[0] * small.shape[1]:
            quad = ap
            break
    if quad is not None:
        q = _order_quad(quad) / scale
        tw = int(max(np.linalg.norm(q[0] - q[1]), np.linalg.norm(q[2] - q[3])))
        th = int(max(np.linalg.norm(q[0] - q[3]), np.linalg.norm(q[1] - q[2])))
        M = cv2.getPerspectiveTransform(q, np.array([[0, 0], [tw, 0], [tw, th], [0, th]], dtype="float32"))
        arr = cv2.warpPerspective(arr, M, (tw, th), flags=cv2.INTER_CUBIC)
    if mode == "color":
        lab = cv2.cvtColor(arr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        bg = cv2.medianBlur(cv2.dilate(l, np.ones((15, 15), np.uint8)), 31)
        l = cv2.divide(l, bg, scale=235)
        out = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2RGB)
    else:
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        bg = cv2.medianBlur(cv2.dilate(gray, np.ones((15, 15), np.uint8)), 31)
        gray = cv2.divide(gray, bg, scale=240)
        if mode == "bw":
            gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 14)
        out = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    from PIL import Image
    return Image.fromarray(out)


@tool("scan", "Dokument scannen", CAT, "Scanne Papier aus Fotos: Seiten werden erkannt, gerade ausgerichtet und zu einem PDF bereinigt.",
      "scan-line",
      [F("files", "files", "Fotos der Seiten (in Reihenfolge)", filter="image"),
       F("mode", "choice", "Look", "color", options=[["color", "Farbe"], ["gray", "Graustufen"], ["bw", "Schwarz-Weiß"]]),
       F("ocr", "bool", "Durchsuchbar machen (Texterkennung)", False)],
      keywords="scanner foto pdf kamera")
def scan(ctx, files, mode, ocr):
    pages = []
    for i, f in enumerate(files):
        ctx.log(Path(f).name)
        pages.append(scan_page(open_img(f), mode))
        ctx.progress((i + 1) / len(files) * (0.6 if ocr else 1))
    out = ctx.out("Scan.pdf")
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=200.0, quality=85)
    if ocr:
        tmp = ctx.out_dir / ".ocr.pdf"
        _ocr_pdf(ctx, out, tmp, "")
        shutil.move(tmp, out)


@tool("redact-pdf", "PDF schwärzen", CAT, "Schwärze Namen, Nummern oder Muster, sodass sie dauerhaft entfernt und nicht nur verdeckt werden.",
      "ink-pen" if False else "square-minus",
      [F("file", "file", "PDF", **PDF),
       F("terms", "textarea", "Begriffe (einer pro Zeile)", "", placeholder="Max Mustermann\nMusterstraße 5"),
       F("auto", "choice", "Muster automatisch finden", "none",
         options=[["none", "Keine"], ["email", "E-Mail-Adressen"], ["iban", "IBAN"], ["phone", "Telefonnummern"],
                  ["all", "Alle drei"]]),
       F("flatten", "bool", "Seiten zu Bildern abflachen (maximale Sicherheit)", True),
       F("strip", "bool", "Metadaten entfernen", True)],
      keywords="zensieren unkenntlich redaction")
def redact_pdf(ctx, file, terms, auto, flatten, strip):
    m = fitz()
    d = open_pdf(file[0])
    words = [t.strip() for t in terms.splitlines() if t.strip()]
    pats = {"email": r"[\w.+-]+@[\w-]+\.[\w.-]+", "iban": r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b",
            "phone": r"(?<!\w)(?:\+|00)?\d[\d\s/().-]{7,}\d"}
    use = list(pats) if auto == "all" else ([auto] if auto != "none" else [])
    if not words and not use:
        raise ToolError("Gib Begriffe ein oder wähle ein Muster.")
    count = 0
    for pi, page in enumerate(d):
        found = []
        for w in words:
            found += page.search_for(w)
        if use:
            text = page.get_text("text")
            for k in use:
                for mt in re.finditer(pats[k], text):
                    found += page.search_for(mt.group(0).strip())
        for r in found:
            page.add_redact_annot(r + (-1, -1, 1, 1), fill=(0, 0, 0))
        if found:
            page.apply_redactions(images=m.PDF_REDACT_IMAGE_PIXELS, graphics=m.PDF_REDACT_LINE_ART_REMOVED_IF_TOUCHED
                                  if hasattr(m, "PDF_REDACT_LINE_ART_REMOVED_IF_TOUCHED") else 0)
            count += len(found)
        ctx.progress((pi + 1) / len(d) * 0.8)
    if count == 0:
        raise ToolError("Nichts gefunden – es wurde nichts geändert.")
    out = ctx.out(Path(file[0]).stem + " geschwärzt.pdf")
    if flatten:
        nd = m.open()
        for page in d:
            pix = page.get_pixmap(dpi=200)
            np_ = nd.new_page(width=page.rect.width, height=page.rect.height)
            np_.insert_image(np_.rect, pixmap=pix)
        d.close()
        d = nd
    if strip:
        d.set_metadata({})
        d.del_xml_metadata()
        try:
            d.scrub()
        except Exception:
            pass
    d.save(out, garbage=4, deflate=True, clean=True)
    return {"message": f"Fertig · {count} Stelle{'n' if count != 1 else ''} dauerhaft geschwärzt"}


@tool("fill-pdf", "Formulare ausfüllen & fixieren", CAT, "Fülle PDF-Formulare aus, setze Text ohne Felder und fixiere die Antworten.",
      "form-input",
      [F("file", "file", "PDF", **PDF),
       F("list", "bool", "Nur Formularfelder anzeigen", False),
       F("fields", "textarea", "Felder (Name = Wert, je Zeile)", "", placeholder="Vorname = Max\nOrt = Berlin",
         hint="Haken: Ja / Nein"),
       F("free", "textarea", "Freier Text (Seite; x%; y%; Text)", "", placeholder="1; 20; 30; Hallo Welt",
         hint="x und y in Prozent der Seite von oben links."),
       F("size", "number", "Schriftgröße", 11, min=6, max=48),
       F("flatten", "bool", "Fixieren (nicht mehr änderbar)", True)],
      keywords="formular ausfüllen flatten")
def fill_pdf(ctx, file, list, fields, free, size, flatten):
    m = fitz()
    d = open_pdf(file[0])
    if list:
        rows = []
        for p in d:
            for w in p.widgets() or []:
                rows.append(f"Seite {p.number + 1}: {w.field_name}  [{w.field_type_string}]  = {w.field_value!r}")
        return "\n".join(rows) or "Dieses PDF hat keine Formularfelder."
    vals = {}
    for line in fields.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    filled = 0
    for p in d:
        for w in p.widgets() or []:
            if w.field_name in vals:
                v = vals[w.field_name]
                if w.field_type_string in ("CheckBox", "RadioButton"):
                    w.field_value = v.lower() in ("ja", "yes", "true", "1", "x", "an")
                else:
                    w.field_value = v
                w.update()
                filled += 1
    for line in free.splitlines():
        parts = [x.strip() for x in line.split(";", 3)]
        if len(parts) < 4:
            continue
        pg = d[int(parts[0]) - 1]
        pt = m.Point(float(parts[1]) / 100 * pg.rect.width, float(parts[2]) / 100 * pg.rect.height + size)
        pg.insert_text(pt, parts[3], fontsize=size, fontname="helv", color=(0, 0, 0))
        filled += 1
    if not filled:
        raise ToolError("Nichts eingetragen. Prüfe die Feldnamen (Haken bei „Nur Formularfelder anzeigen“).")
    if flatten:
        try:
            d.bake()
        except Exception:
            pass
    d.save(ctx.out(Path(file[0]).stem + " ausgefüllt.pdf"), garbage=3, deflate=True)


def _ocr_pdf(ctx, src, dst, password):
    from .ocr import engine
    import numpy as np
    m = fitz()
    d = open_pdf(src, password)
    eng = engine()
    for pi, page in enumerate(d):
        pix = page.get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
        res, _ = eng(img)
        k = 72 / 200
        for box, text, _ in res or []:
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            x0, y0, x1, y1 = min(xs) * k, min(ys) * k, max(xs) * k, max(ys) * k
            fs = max(4, (y1 - y0) * 0.85)
            tl = m.get_text_length(text, fontname="helv", fontsize=fs)
            if tl <= 0:
                continue
            page.insert_text((x0, y1 - (y1 - y0) * 0.2), text, fontsize=fs * min(1.0, (x1 - x0) / tl) if tl > (x1 - x0) else fs,
                             fontname="helv", render_mode=3)
        ctx.progress((pi + 1) / len(d))
    d.save(dst, garbage=3, deflate=True)


@tool("ocr-pdf", "PDF durchsuchbar machen", CAT, "Mache Scans durchsuchbar und kopierbar – per Texterkennung auf deinem Rechner.",
      "scan-search",
      [F("files", "files", "PDFs", **PDF)], keywords="ocr texterkennung scan")
def ocr_pdf(ctx, files):
    def one(f):
        _ocr_pdf(ctx, f, ctx.out(Path(f).stem + " durchsuchbar.pdf"), "")
    for f in files:
        ctx.log(Path(f).name)
        one(f)


@tool("pdf2word", "PDF in Word", CAT, "Mach aus PDFs bearbeitbare Word-Dokumente mit Überschriften, Listen und Absätzen.",
      "file-type",
      [F("files", "files", "PDFs", **PDF)], keywords="docx umwandeln")
def pdf2word(ctx, files):
    from pdf2docx import Converter

    def one(f):
        cv = Converter(f)
        try:
            cv.convert(str(ctx.out(Path(f).stem + ".docx")))
        finally:
            cv.close()
    batch_files(ctx, files, one)


_SCRIPT_FONTS = ["Z003", "URW Chancery L", "Lucida Handwriting", "Comic Neue", "DejaVu Serif"]


@tool("sign-pdf", "PDF signieren", CAT, "Tippe oder lade deine Signatur hoch und platziere sie auf einem Dokument.", "signature",
      [F("file", "file", "PDF", **PDF),
       F("kind", "choice", "Signatur", "text", options=[["text", "Getippt"], ["image", "Bilddatei (PNG)"]]),
       F("name", "text", "Name", "", placeholder="Max Mustermann", showIf="kind=text"),
       F("sig", "file", "Signatur-Bild", filter="image", showIf="kind=image", optional=True),
       F("page", "choice", "Seite", "last", options=[["first", "Erste"], ["last", "Letzte"], ["all", "Alle"], ["n", "Nummer …"]]),
       F("n", "number", "Seitennummer", 1, min=1, max=9999, showIf="page=n"),
       F("pos", "choice", "Position", "br", options=[["br", "Unten rechts"], ["bl", "Unten links"], ["bc", "Unten Mitte"],
                                                   ["mr", "Mitte rechts"], ["tr", "Oben rechts"]]),
       F("size", "slider", "Größe", 22, min=8, max=50, step=1, placeholder=" %"),
       F("date", "bool", "Datum darunter setzen", False)],
      keywords="unterschrift unterschreiben")
def sign_pdf(ctx, file, kind, name, sig, page, n, pos, size, date):
    import time
    m = fitz()
    d = open_pdf(file[0])
    if kind == "text" and not name.strip():
        raise ToolError("Gib einen Namen ein.")
    if kind == "image" and not sig:
        raise ToolError("Wähle ein Signatur-Bild.")
    idx = {"first": [0], "last": [len(d) - 1], "all": list(range(len(d))), "n": [int(n) - 1]}[page]
    for i in idx:
        if i < 0 or i >= len(d):
            raise ToolError("Diese Seite gibt es nicht.")
        pg = d[i]
        r = pg.rect
        w = r.width * size / 100
        h = w * 0.35
        x = {"l": r.width * 0.08, "c": (r.width - w) / 2, "r": r.width * 0.92 - w}[{"br": "r", "bl": "l", "bc": "c", "mr": "r", "tr": "r"}[pos]]
        y = {"b": r.height * 0.93 - h - (14 if date else 0), "m": (r.height - h) / 2, "t": r.height * 0.07}[{"br": "b", "bl": "b", "bc": "b", "mr": "m", "tr": "t"}[pos]]
        box = m.Rect(x, y, x + w, y + h)
        if kind == "image":
            pg.insert_image(box, filename=sig[0], keep_proportion=True)
        else:
            font = None
            for fname in _SCRIPT_FONTS:
                out = subprocess.run(["fc-match", "-f", "%{file}", fname], capture_output=True, text=True).stdout
                if out and fname.split()[0].lower() in out.lower():
                    font = out
                    break
            fs = h * 0.7
            pg.insert_textbox(box, name, fontsize=fs, fontname="sig" if font else "tiit",
                              fontfile=font, color=(0.05, 0.1, 0.45), align=1)
        if date:
            pg.insert_text((x, y + h + 10), time.strftime("%d.%m.%Y"), fontsize=8, color=(0.3, 0.3, 0.3))
    d.save(ctx.out(Path(file[0]).stem + " signiert.pdf"), garbage=3, deflate=True)


@tool("pdf-merge", "PDFs zusammenfügen", CAT, "Füge mehrere PDFs und Bilder zu einem Dokument zusammen.", "files",
      [F("files", "files", "PDFs und Bilder (in Reihenfolge)", filter="pdfimg")], keywords="vereinen merge combine")
def pdf_merge(ctx, files):
    if len(files) < 2:
        raise ToolError("Wähle mindestens zwei Dateien.")
    m = fitz()
    out = m.open()
    for i, f in enumerate(files):
        if Path(f).suffix.lower() == ".pdf":
            out.insert_pdf(open_pdf(f))
        else:
            im = open_img(f).convert("RGB")
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as t:
                im.save(t.name, quality=95)
            pg = out.new_page(width=im.width * 72 / 150, height=im.height * 72 / 150)
            pg.insert_image(pg.rect, filename=t.name)
            Path(t.name).unlink(missing_ok=True)
        ctx.progress((i + 1) / len(files))
    out.save(ctx.out("Zusammengefügt.pdf"), garbage=3, deflate=True)


@tool("pdf-split", "PDF teilen", CAT, "Teile ein PDF in einzelne Seiten oder Seitenbereiche auf.", "split",
      [F("file", "file", "PDF", **PDF),
       F("mode", "choice", "Teilen", "each", options=[["each", "Jede Seite einzeln"], ["ranges", "Bereiche"], ["every", "Alle N Seiten"]]),
       F("ranges", "text", "Bereiche (je Teil mit Semikolon)", "1-3; 4-6", showIf="mode=ranges"),
       F("every", "number", "Seiten pro Teil", 5, min=1, max=1000, showIf="mode=every")],
      keywords="trennen aufteilen")
def pdf_split(ctx, file, mode, ranges, every):
    m = fitz()
    d = open_pdf(file[0])
    n = len(d)
    stem = Path(file[0]).stem
    groups: list[list[int]] = []
    if mode == "each":
        groups = [[i] for i in range(n)]
    elif mode == "every":
        k = int(every)
        groups = [list(range(i, min(n, i + k))) for i in range(0, n, k)]
    else:
        groups = [parse_pages(r, n) for r in ranges.split(";") if r.strip()]
    for gi, g in enumerate(groups):
        nd = m.open()
        for p in g:
            nd.insert_pdf(d, from_page=p, to_page=p)
        label = f"Seite {g[0] + 1}" if len(g) == 1 else f"Seiten {g[0] + 1}-{g[-1] + 1}"
        nd.save(ctx.out(f"{stem} {label}.pdf"), garbage=3, deflate=True)
        ctx.progress((gi + 1) / len(groups))


@tool("pdf-organize", "PDF organisieren", CAT, "Ordne Seiten neu an, drehe oder dupliziere sie.", "arrow-down-up",
      [F("file", "file", "PDF", **PDF),
       F("order", "text", "Neue Reihenfolge", "", placeholder="3,1,2,5-7  (leer = unverändert)",
         hint="Seiten, die nicht aufgeführt sind, fallen weg. „4-1“ kehrt um."),
       F("rot", "text", "Drehen (Seite:Grad)", "", placeholder="2:90, 5:180")],
      keywords="sortieren reihenfolge drehen")
def pdf_organize(ctx, file, order, rot):
    d = open_pdf(file[0])
    n = len(d)
    if order.strip():
        d.select(parse_pages(order, n))
    for part in rot.split(","):
        if ":" in part:
            a, b = part.split(":")
            for p in parse_pages(a, len(d)):
                d[p].set_rotation((d[p].rotation + int(b)) % 360)
    d.save(ctx.out(Path(file[0]).stem + " neu geordnet.pdf"), garbage=3, deflate=True)


@tool("pdf-delete", "Seiten löschen", CAT, "Entferne Seiten aus einem PDF.", "file-minus",
      [F("file", "file", "PDF", **PDF),
       F("pages", "text", "Zu löschende Seiten", "", placeholder="2, 4-6")])
def pdf_delete(ctx, file, pages):
    d = open_pdf(file[0])
    dele = set(parse_pages(pages, len(d)))
    if len(dele) >= len(d):
        raise ToolError("Du kannst nicht alle Seiten löschen.")
    d.select([i for i in range(len(d)) if i not in dele])
    d.save(ctx.out(Path(file[0]).stem + " gekürzt.pdf"), garbage=3, deflate=True)


@tool("pdf-extract", "Seiten extrahieren", CAT, "Ziehe einzelne Seiten oder Bereiche in ein neues PDF.", "file-output",
      [F("file", "file", "PDF", **PDF),
       F("pages", "text", "Seiten", "", placeholder="1-3, 7")])
def pdf_extract(ctx, file, pages):
    d = open_pdf(file[0])
    d.select(parse_pages(pages, len(d)))
    d.save(ctx.out(Path(file[0]).stem + " Auszug.pdf"), garbage=3, deflate=True)


@tool("img2pdf", "Bilder in PDF", CAT, "Mach aus Bildern ein PDF.", "images",
      [F("files", "files", "Bilder (in Reihenfolge)", filter="image"),
       F("size", "choice", "Seitengröße", "a4", options=[["a4", "A4"], ["letter", "Letter"], ["fit", "An Bild anpassen"]]),
       F("margin", "slider", "Rand", 5, min=0, max=20, step=1, placeholder=" mm", showIf="size=a4"),
       F("orient", "choice", "Ausrichtung", "auto", options=[["auto", "Automatisch"], ["p", "Hochformat"], ["l", "Querformat"]],
         showIf="size=a4")])
def img2pdf(ctx, files, size, margin, orient):
    m = fitz()
    out = m.open()
    dims = {"a4": (595.28, 841.89), "letter": (612, 792)}
    for i, f in enumerate(files):
        im = open_img(f).convert("RGB")
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as t:
            im.save(t.name, quality=95)
        if size == "fit":
            pg = out.new_page(width=im.width * 72 / 150, height=im.height * 72 / 150)
            pg.insert_image(pg.rect, filename=t.name)
        else:
            w, h = dims.get(size, dims["a4"])
            land = (im.width > im.height) if orient == "auto" else orient == "l"
            if land:
                w, h = h, w
            pg = out.new_page(width=w, height=h)
            mg = margin * 72 / 25.4
            pg.insert_image(m.Rect(mg, mg, w - mg, h - mg), filename=t.name, keep_proportion=True)
        Path(t.name).unlink(missing_ok=True)
        ctx.progress((i + 1) / len(files))
    out.save(ctx.out("Bilder.pdf"), garbage=3, deflate=True)


@tool("pdf-compress", "PDF komprimieren", CAT, "Verkleinere PDF-Dateien.", "file-archive",
      [F("files", "files", "PDFs", **PDF),
       F("level", "choice", "Stärke", "ebook", options=[["printer", "Leicht (Druck)"], ["ebook", "Mittel (E-Book)"],
                                                       ["screen", "Stark (Bildschirm)"]])],
      needs=["gs"], keywords="verkleinern größe")
def pdf_compress(ctx, files, level):
    before = after = 0

    def one(f):
        nonlocal before, after
        o = ctx.out(Path(f).stem + " klein.pdf")
        ctx.run([which("gs"), "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6", f"-dPDFSETTINGS=/{level}", "-dNOPAUSE", "-dQUIET",
                 "-dBATCH", "-dDetectDuplicateImages=true", f"-sOutputFile={o}", f])
        if Path(o).stat().st_size >= Path(f).stat().st_size:
            shutil.copy(f, o)  # nicht schlechter werden
        before += Path(f).stat().st_size
        after += Path(o).stat().st_size
    batch_files(ctx, files, one)
    pct = round((1 - after / before) * 100) if before else 0
    return {"message": f"{before / 1e6:.1f} MB → {after / 1e6:.1f} MB  (−{pct} %)"}


@tool("pdf-lock", "Passwort hinzufügen", CAT, "Schütze ein PDF mit einem Passwort (AES-256).", "lock",
      [F("file", "file", "PDF", **PDF),
       F("pw", "text", "Passwort zum Öffnen", "", placeholder="mindestens 4 Zeichen"),
       F("noprint", "bool", "Drucken verbieten", False),
       F("nocopy", "bool", "Kopieren von Text verbieten", False)],
      keywords="verschlüsseln schützen")
def pdf_lock(ctx, file, pw, noprint, nocopy):
    import pikepdf
    if len(pw) < 4:
        raise ToolError("Das Passwort braucht mindestens 4 Zeichen.")
    with pikepdf.open(file[0]) as pdf:
        perm = pikepdf.Permissions(print_lowres=not noprint, print_highres=not noprint, extract=not nocopy)
        pdf.save(ctx.out(Path(file[0]).stem + " geschützt.pdf"),
                 encryption=pikepdf.Encryption(user=pw, owner=pw + "-owner", R=6, allow=perm))


@tool("pdf-unlock", "Passwort entfernen", CAT, "Sichere eine entsperrte Kopie eines passwortgeschützten PDFs, das dir gehört.",
      "lock-open",
      [F("file", "file", "PDF", **PDF), F("pw", "text", "Aktuelles Passwort", "")])
def pdf_unlock(ctx, file, pw):
    import pikepdf
    try:
        with pikepdf.open(file[0], password=pw) as pdf:
            pdf.save(ctx.out(Path(file[0]).stem + " entsperrt.pdf"))
    except pikepdf.PasswordError:
        raise ToolError("Das Passwort stimmt nicht.")


@tool("pdf2img", "PDF in Bilder", CAT, "Wandle PDF-Seiten in PNG, JPG oder WebP um.", "image-down",
      [F("file", "file", "PDF", **PDF),
       F("pages", "text", "Seiten (leer = alle)", "", placeholder="1-3"),
       F("fmt", "choice", "Format", "png", options=[["png", "PNG"], ["jpg", "JPG"], ["webp", "WebP"]]),
       F("dpi", "choice", "Auflösung", "200", options=[["100", "100 dpi"], ["150", "150 dpi"], ["200", "200 dpi"],
                                                     ["300", "300 dpi"], ["600", "600 dpi"]])])
def pdf2img(ctx, file, pages, fmt, dpi):
    d = open_pdf(file[0])
    idx = parse_pages(pages, len(d), True) or list(range(len(d)))
    pil()
    for k, i in enumerate(idx):
        pix = d[i].get_pixmap(dpi=int(dpi), alpha=False)
        out = ctx.out(f"{Path(file[0]).stem} Seite {i + 1}.{fmt}")
        if fmt in ("png", "jpg"):
            pix.save(out, jpg_quality=92)
        else:
            from PIL import Image
            Image.frombytes("RGB", (pix.w, pix.h), pix.samples).save(out, quality=90)
        ctx.progress((k + 1) / len(idx))


@tool("doc-convert", "Dokumente umwandeln", CAT, "Wandle Office-Dokumente in PDF, DOCX, ODT, TXT, HTML und mehr um.", "file-cog",
      [F("files", "files", "Dokumente", filter="office"),
       F("fmt", "choice", "Zielformat", "pdf", options=[["pdf", "PDF"], ["docx", "DOCX"], ["odt", "ODT"], ["txt", "TXT"],
                                                       ["html", "HTML"], ["rtf", "RTF"], ["xlsx", "XLSX"], ["pptx", "PPTX"]])],
      needs=["soffice"], keywords="libreoffice office umwandeln")
def doc_convert(ctx, files, fmt):
    batch_files(ctx, files, lambda f: soffice(ctx, f, fmt))


def _lo(name, tid, label, icon, flt, desc):
    @tool(tid, name, CAT, desc, icon, [F("files", "files", label, filter=flt)], needs=["soffice"])
    def run(ctx, files):
        batch_files(ctx, files, lambda f: soffice(ctx, f, "pdf"))
    return run


_lo("Word in PDF", "word2pdf", "Word-Dokumente", "file-text", "word", "Wandle Word-Dokumente in PDF um.")
_lo("PowerPoint in PDF", "ppt2pdf", "Präsentationen", "presentation", "ppt", "Wandle Präsentationen in PDF um.")
_lo("Excel in PDF", "xls2pdf", "Tabellen", "table", "excel", "Wandle Tabellen in PDF um.")


@tool("web2pdf", "Webseite in PDF", CAT, "Speichere eine Webseite als PDF.", "globe",
      [F("url", "text", "Adresse", "", placeholder="https://…"),
       F("page", "choice", "Papier", "A4", options=[["A4", "A4"], ["Letter", "Letter"]]),
       F("bg", "bool", "Hintergründe drucken", True)],
      keywords="website html drucken")
def web2pdf(ctx, url, page, bg):
    chrome = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser", "brave-browser", "microsoft-edge")
                   if shutil.which(c)), None)
    if not chrome:
        raise ToolError("Dafür wird ein Chromium-basierter Browser gebraucht (z. B. Google Chrome).")
    if not url.strip():
        raise ToolError("Gib eine Adresse ein.")
    u = url.strip() if "://" in url else "https://" + url.strip()
    out = ctx.out("Webseite.pdf")
    with tempfile.TemporaryDirectory() as td:
        ctx.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={td}", "--no-pdf-header-footer",
                 "--virtual-time-budget=8000", f"--print-to-pdf={out}"] + (["--print-background"] if bg else []) + [u])


_MD_CSS = """
@page { size: A4; margin: 22mm 20mm; }
body { font-family: 'Noto Sans','DejaVu Sans',sans-serif; font-size: 10.5pt; line-height: 1.55; color:#1c1e26; }
h1,h2,h3,h4 { line-height:1.25; margin: 1.4em 0 .5em; } h1{font-size:22pt;border-bottom:1px solid #ddd;padding-bottom:.25em}
h2{font-size:16pt} h3{font-size:13pt}
code { font-family:'JetBrains Mono','DejaVu Sans Mono',monospace; background:#f1f2f6; padding:1px 4px; border-radius:3px; font-size:9pt }
pre { background:#f1f2f6; padding:10px 12px; border-radius:6px; overflow:hidden; white-space:pre-wrap } pre code{background:none;padding:0}
blockquote { border-left:3px solid #7c6cff; margin-left:0; padding-left:12px; color:#555 }
table { border-collapse:collapse; width:100% } th,td { border:1px solid #d5d8e0; padding:5px 8px; text-align:left } th{background:#f1f2f6}
img { max-width:100% } a { color:#4a3fd6 }
"""


@tool("md2pdf", "Markdown in PDF", CAT, "Mache aus Markdown ein sauber gesetztes PDF.", "file-code",
      [F("files", "files", "Markdown-Dateien", filter="md", optional=True),
       F("text", "textarea", "…oder Text einfügen", "", hint="mono")],
      keywords="md")
def md2pdf(ctx, files, text):
    import markdown
    from weasyprint import HTML, CSS
    srcs = [(Path(f).stem, Path(f).read_text(errors="replace"), Path(f).parent) for f in files]
    if text.strip():
        srcs.append(("Markdown", text, Path.home()))
    if not srcs:
        raise ToolError("Wähle eine Datei oder füge Text ein.")
    for name, md, base in srcs:
        html = markdown.markdown(md, extensions=["extra", "fenced_code", "tables", "sane_lists", "toc"])
        HTML(string=html, base_url=str(base)).write_pdf(str(ctx.out(name + ".pdf")), stylesheets=[CSS(string=_MD_CSS)])
