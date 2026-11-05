"""Datei-Werkzeuge: QR, Stapelumbenennung, Duplikate, Zippen."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from collections import defaultdict
from pathlib import Path

from ..context import ToolError, which
from ..registry import F, tool
from .images import open_img

CAT = "files"


@tool("qr", "QR-Code", CAT, "Erstelle QR-Codes für Links, Text und WLAN oder lies Codes und Barcodes aus Bildern.", "qr-code",
      [F("mode", "choice", "Aktion", "make", options=[["make", "Erstellen"], ["read", "Lesen"]]),
       F("kind", "choice", "Inhalt", "text", options=[["text", "Text / Link"], ["wifi", "WLAN"], ["mail", "E-Mail"],
                                                    ["tel", "Telefon"], ["vcard", "Kontakt"]], showIf="mode=make"),
       F("text", "textarea", "Text oder Link", "", showIf="kind=text", hint=""),
       F("ssid", "text", "Netzwerkname", "", showIf="kind=wifi"),
       F("pw", "text", "Passwort", "", showIf="kind=wifi"),
       F("sec", "choice", "Sicherheit", "WPA", options=[["WPA", "WPA/WPA2/WPA3"], ["WEP", "WEP"], ["nopass", "Offen"]], showIf="kind=wifi"),
       F("addr", "text", "Adresse / Nummer", "", showIf="kind=mail"),
       F("tel", "text", "Telefonnummer", "", showIf="kind=tel"),
       F("name", "text", "Name", "", showIf="kind=vcard"),
       F("vtel", "text", "Telefon", "", showIf="kind=vcard"),
       F("vmail", "text", "E-Mail", "", showIf="kind=vcard"),
       F("fg", "color", "Vordergrund", "#000000", showIf="mode=make"),
       F("bg", "color", "Hintergrund", "#ffffff", showIf="mode=make"),
       F("fmt", "choice", "Format", "png", options=[["png", "PNG"], ["svg", "SVG"]], showIf="mode=make"),
       F("img", "files", "Bilder mit Codes", filter="image", showIf="mode=read", optional=True)],
      output="both", keywords="barcode wlan code scannen")
def qr(ctx, mode, kind, text, ssid, pw, sec, addr, tel, name, vtel, vmail, fg, bg, fmt, img):
    if mode == "read":
        import cv2
        import numpy as np
        if not img:
            raise ToolError("Wähle ein Bild.")
        found = []
        for f in img:
            im = cv2.cvtColor(np.array(open_img(f).convert("RGB")), cv2.COLOR_RGB2BGR)
            ok, vals, _, _ = cv2.QRCodeDetector().detectAndDecodeMulti(im)
            res = [v for v in (vals if ok else []) if v]
            if not res:
                try:
                    det = cv2.barcode.BarcodeDetector() if hasattr(cv2, "barcode") else cv2.barcode_BarcodeDetector()
                    r = det.detectAndDecode(im)
                    res = [v for v in (r[1] if len(r) > 1 and r[1] else []) if v]
                except Exception:
                    pass
            found.append(f"{Path(f).name}:\n" + ("\n".join("  " + v for v in res) if res else "  Kein Code gefunden"))
        return "\n\n".join(found)
    import qrcode
    esc = lambda s: re.sub(r'([\\;,:"])', r"\\\1", s)  # noqa: E731
    data = {"text": text, "wifi": f"WIFI:T:{sec};S:{esc(ssid)};P:{esc(pw)};;" if sec != "nopass" else f"WIFI:T:nopass;S:{esc(ssid)};;",
            "mail": f"mailto:{addr}", "tel": f"tel:{tel}",
            "vcard": f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL:{vtel}\nEMAIL:{vmail}\nEND:VCARD"}[kind]
    if not data.strip() or data in ("mailto:", "tel:"):
        raise ToolError("Gib den Inhalt für den Code ein.")
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=14, border=3)
    q.add_data(data)
    q.make(fit=True)
    out = ctx.out(f"QR-Code.{fmt}")
    if fmt == "svg":
        import qrcode.image.svg
        qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage).save(out)
    else:
        q.make_image(fill_color=fg, back_color=bg).save(out)
    return {"message": "Fertig · QR-Code gespeichert"}


@tool("rename", "Stapelumbenennung", CAT, "Benenne viele Dateien auf einmal um – mit Suchen und Ersetzen, Nummerierung, Datum oder Schreibweise.",
      "replace-all",
      [F("files", "files", "Dateien", filter="any"),
       F("find", "text", "Suchen", "", placeholder="IMG_"),
       F("repl", "text", "Ersetzen durch", ""),
       F("regex", "bool", "Reguläre Ausdrücke", False),
       F("prefix", "text", "Präfix", ""),
       F("suffix", "text", "Suffix (vor der Endung)", ""),
       F("num", "choice", "Nummerierung", "none", options=[["none", "Keine"], ["after", "Am Ende"], ["before", "Am Anfang"],
                                                         ["replace", "Statt Name"]]),
       F("start", "number", "Beginn bei", 1, min=0, max=999999, showIf="num=after"),
       F("start2", "number", "Beginn bei", 1, min=0, max=999999, showIf="num=before"),
       F("start3", "number", "Beginn bei", 1, min=0, max=999999, showIf="num=replace"),
       F("digits", "number", "Stellen", 3, min=1, max=8),
       F("date", "choice", "Datum einfügen", "none", options=[["none", "Nein"], ["mtime", "Änderungsdatum"], ["today", "Heute"]]),
       F("case", "choice", "Schreibweise", "keep", options=[["keep", "Unverändert"], ["lower", "klein"], ["upper", "GROSS"],
                                                          ["title", "Titel"], ["snake", "snake_case"], ["dash", "kebab-case"]]),
       F("spaces", "bool", "Leerzeichen durch _ ersetzen", False),
       F("dry", "bool", "Nur Vorschau", True),
       F("inplace", "bool", "Originale umbenennen (statt Kopien)", False)],
      output="both", keywords="umbenennen dateien nummerieren")
def rename(ctx, files, find, repl, regex, prefix, suffix, num, start, start2, start3, digits, date, case, spaces, dry, inplace):
    begin = {"after": start, "before": start2, "replace": start3}.get(num, 1)
    lines, plan = [], []
    taken = set()
    for i, f in enumerate(files):
        p = Path(f)
        stem = p.stem
        if find:
            try:
                stem = re.sub(find, repl, stem) if regex else stem.replace(find, repl)
            except re.error as e:
                raise ToolError(f"Ungültiger Ausdruck: {e}")
        if spaces:
            stem = stem.replace(" ", "_")
        stem = {"keep": stem, "lower": stem.lower(), "upper": stem.upper(),
                "title": stem.title(), "snake": re.sub(r"[\s-]+", "_", stem).lower(),
                "dash": re.sub(r"[\s_]+", "-", stem).lower()}[case]
        stem = f"{prefix}{stem}{suffix}"
        if date != "none":
            t = p.stat().st_mtime if date == "mtime" else time.time()
            stem = f"{time.strftime('%Y-%m-%d', time.localtime(t))} {stem}".strip()
        n = str(int(begin) + i).zfill(int(digits))
        if num == "after":
            stem = f"{stem} {n}"
        elif num == "before":
            stem = f"{n} {stem}"
        elif num == "replace":
            stem = n
        name = stem + p.suffix
        key = (str(p.parent), name)
        k = 2
        while key in taken:
            name = f"{stem} ({k}){p.suffix}"
            key = (str(p.parent), name)
            k += 1
        taken.add(key)
        plan.append((p, name))
        lines.append(f"{p.name}  →  {name}")
    if dry:
        return {"text": "\n".join(lines), "message": "Vorschau · es wurde nichts geändert"}
    for i, (p, name) in enumerate(plan):
        if inplace:
            tgt = p.with_name(name)
            if tgt.exists() and tgt != p:
                raise ToolError(f"{name} existiert schon.")
            p.rename(tgt)
            ctx.add_output(tgt)
        else:
            shutil.copy2(p, ctx.out(name))
        ctx.progress((i + 1) / len(plan))
    return {"text": "\n".join(lines)}


def _hash(path, limit=None):
    h = hashlib.blake2b()
    with open(path, "rb") as fh:
        if limit:
            h.update(fh.read(limit))
        else:
            while c := fh.read(1 << 20):
                h.update(c)
    return h.digest()


@tool("dupes", "Duplikate finden", CAT, "Finde doppelte Dateien in Ordnern – exakt, per Inhalt.", "copy-check",
      [F("dirs", "files", "Dateien", filter="any", optional=True),
       F("folder", "folder", "…oder ganzen Ordner durchsuchen", "", optional=True),
       F("min", "number", "Mindestgröße", 1, min=0, max=100000, placeholder="KB"),
       F("trash", "bool", "Duplikate in den Papierkorb legen (Älteste bleiben)", False)],
      output="text", keywords="doppelt gleiche dateien aufräumen")
def dupes(ctx, dirs, folder, min, trash):
    paths = [Path(f) for f in dirs]
    if not paths and not folder:
        raise ToolError("Wähle Dateien oder einen Ordner.")
    if folder:
        for r, _, fs in os.walk(folder):
            if "/." in r:
                continue
            paths += [Path(r) / f for f in fs if not f.startswith(".")]
    by_size = defaultdict(list)
    for p in paths:
        try:
            if p.is_file() and not p.is_symlink() and p.stat().st_size >= min * 1024:
                by_size[p.stat().st_size].append(p)
        except OSError:
            pass
    cand = [g for g in by_size.values() if len(g) > 1]
    groups = []
    total = max(1, sum(len(g) for g in cand))
    done = 0
    for g in cand:
        by_head = defaultdict(list)
        for p in g:
            by_head[_hash(p, 65536)].append(p)
        for hg in by_head.values():
            if len(hg) < 2:
                continue
            full = defaultdict(list)
            for p in hg:
                full[_hash(p)].append(p)
            groups += [sorted(x, key=lambda q: q.stat().st_mtime) for x in full.values() if len(x) > 1]
        done += len(g)
        ctx.progress(done / total)
    if not groups:
        return "Keine Duplikate gefunden."
    wasted = sum(g[0].stat().st_size * (len(g) - 1) for g in groups)
    lines = [f"{len(groups)} Gruppen · {wasted / 1e6:.1f} MB belegt durch Duplikate\n"]
    for g in groups:
        lines.append(f"{g[0].stat().st_size / 1e3:.0f} KB")
        lines += [("  behalten  " if i == 0 else "  doppelt   ") + str(p) for i, p in enumerate(g)]
        lines.append("")
    if trash:
        from send2trash import send2trash
        n = 0
        for g in groups:
            for p in g[1:]:
                send2trash(str(p))
                n += 1
        lines.append(f"{n} Duplikate in den Papierkorb gelegt.")
    return "\n".join(lines)


@tool("zip", "Zippen & Entpacken", CAT, "Packe Dateien zu Archiven oder entpacke ZIP, 7z, TAR, RAR und mehr.", "archive",
      [F("mode", "choice", "Aktion", "zip", options=[["zip", "Zippen"], ["unzip", "Entpacken"]]),
       F("files", "files", "Dateien", filter="any"),
       F("fmt", "choice", "Format", "zip", options=[["zip", "ZIP"], ["7z", "7z"], ["tar.gz", "tar.gz"]], showIf="mode=zip"),
       F("level", "choice", "Komprimierung", "5", options=[["1", "Schnell"], ["5", "Normal"], ["9", "Maximal"]], showIf="mode=zip"),
       F("pw", "text", "Passwort (optional)", "", optional=True),
       F("each", "bool", "Jede Datei einzeln packen", False, showIf="mode=zip")],
      keywords="archiv komprimieren rar tar 7z")
def zip_(ctx, mode, files, fmt, level, pw, each):
    sz = which("7z")
    pwarg = [f"-p{pw}"] if pw else []
    if mode == "unzip":
        for i, f in enumerate(files):
            d = ctx.out_dir / Path(f).stem.removesuffix(".tar")
            ctx.run([sz, "x", "-y", f"-o{d}", *pwarg, f])
            ctx.add_output(d)
            ctx.progress((i + 1) / len(files))
        return
    groups = [[f] for f in files] if each else [files]
    for i, g in enumerate(groups):
        name = (Path(g[0]).stem if each or len(g) == 1 else (Path(g[0]).parent.name or "Archiv")) + "." + fmt
        out = ctx.out(name)
        if fmt == "tar.gz":
            ctx.run(["tar", "-czf", out, *sum((["-C", str(Path(f).parent), Path(f).name] for f in g), [])])
        else:
            extra = ["-tzip", "-mem=AES256"] if (fmt == "zip" and pw) else (["-tzip"] if fmt == "zip" else ["-t7z", "-mhe=on"] if pw else ["-t7z"])
            ctx.run([sz, "a", *extra, f"-mx={level}", *pwarg, out, *g])
        ctx.progress((i + 1) / len(groups))
