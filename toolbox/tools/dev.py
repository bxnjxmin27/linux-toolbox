"""Entwickler-Werkzeuge (alle live, reine Text-Ein-/Ausgabe)."""
from __future__ import annotations

import base64
import binascii
import difflib
import hashlib
import json
import random
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from ..context import ToolError
from ..registry import F, tool

CAT = "dev"


@tool("json", "JSON-Formatierer", CAT, "Formatiere, minimiere und prüfe JSON.", "braces",
      [F("text", "textarea", "JSON", "", placeholder='{"hallo": "welt"}', hint="mono"),
       F("mode", "choice", "Aktion", "pretty2", options=[["pretty2", "Einrücken (2)"], ["pretty4", "Einrücken (4)"],
                                                        ["min", "Minimieren"]]),
       F("sort", "bool", "Schlüssel sortieren", False)],
      live=True, output="text")
def json_fmt(ctx, text, mode, sort):
    if not text.strip():
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ToolError(f"Ungültiges JSON: {e.msg} (Zeile {e.lineno}, Spalte {e.colno})")
    if mode == "min":
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=sort)
    return json.dumps(data, ensure_ascii=False, indent=2 if mode == "pretty2" else 4, sort_keys=sort)


@tool("base64", "Base64", CAT, "Kodiere und dekodiere Text als Base64.", "binary",
      [F("text", "textarea", "Eingabe", "", hint="mono"),
       F("mode", "choice", "Richtung", "enc", options=[["enc", "Kodieren"], ["dec", "Dekodieren"]]),
       F("url", "bool", "URL-sicher (- und _)", False)],
      live=True, output="text")
def b64(ctx, text, mode, url):
    if not text:
        return ""
    if mode == "enc":
        f = base64.urlsafe_b64encode if url else base64.b64encode
        return f(text.encode()).decode()
    s = text.strip()
    s += "=" * (-len(s) % 4)
    try:
        raw = (base64.urlsafe_b64decode if url or "-" in s or "_" in s else base64.b64decode)(s)
    except (binascii.Error, ValueError):
        raise ToolError("Das ist kein gültiges Base64.")
    try:
        return raw.decode()
    except UnicodeDecodeError:
        return "(Binärdaten, " + str(len(raw)) + " Bytes)\n" + raw.hex()


@tool("hash", "Hash-Generator", CAT, "MD5, SHA-1, SHA-256, SHA-512 und mehr für Text oder Dateien.", "fingerprint",
      [F("text", "textarea", "Text", "", hint="mono"),
       F("file", "file", "…oder eine Datei", filter="any", optional=True),
       F("upper", "bool", "Großbuchstaben", False)],
      live=True, output="text", keywords="md5 sha checksum prüfsumme")
def hasher(ctx, text, file, upper):
    algos = ["md5", "sha1", "sha256", "sha512", "sha3_256", "blake2b"]
    hs = {a: hashlib.new(a) for a in algos}
    if file:
        with open(file[0], "rb") as fh:
            while chunk := fh.read(1 << 20):
                for h in hs.values():
                    h.update(chunk)
    elif text:
        for h in hs.values():
            h.update(text.encode())
    else:
        return ""
    return "\n".join(f"{a.upper().replace('_', '-'):9} {(h.hexdigest().upper() if upper else h.hexdigest())}"
                     for a, h in hs.items())


def _uuid7() -> uuid.UUID:
    ms = int(time.time() * 1000)
    rnd = random.getrandbits(74)
    v = (ms << 80) | (0x7 << 76) | ((rnd >> 62) << 64) | (0b10 << 62) | (rnd & ((1 << 62) - 1))
    return uuid.UUID(int=v)


@tool("uuid", "UUID-Generator", CAT, "Erzeuge UUIDs in den Versionen 1, 4 und 7.", "hash",
      [F("ver", "choice", "Version", "4", options=[["4", "v4 (zufällig)"], ["7", "v7 (zeitsortiert)"], ["1", "v1"]]),
       F("n", "number", "Anzahl", 5, min=1, max=1000),
       F("upper", "bool", "Großbuchstaben", False),
       F("nodash", "bool", "Ohne Bindestriche", False)],
      live=True, output="text")
def uuids(ctx, ver, n, upper, nodash):
    gen = {"4": uuid.uuid4, "7": _uuid7, "1": uuid.uuid1}[ver]
    out = []
    for _ in range(int(max(1, min(1000, n)))):
        s = str(gen())
        s = s.replace("-", "") if nodash else s
        out.append(s.upper() if upper else s)
    return "\n".join(out)


@tool("jwt", "JWT-Decoder", CAT, "Zeige Header und Payload eines JSON Web Tokens.", "key-round",
      [F("text", "textarea", "Token", "", placeholder="eyJhbGciOi…", hint="mono")],
      live=True, output="text")
def jwt(ctx, text):
    t = text.strip()
    if not t:
        return ""
    parts = t.split(".")
    if len(parts) < 2:
        raise ToolError("Ein JWT besteht aus drei Teilen, getrennt durch Punkte.")

    def dec(p):
        return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    try:
        head, pay = dec(parts[0]), dec(parts[1])
    except Exception:
        raise ToolError("Header oder Payload sind kein gültiges Base64/JSON.")
    out = ["HEADER", json.dumps(head, indent=2, ensure_ascii=False), "", "PAYLOAD",
           json.dumps(pay, indent=2, ensure_ascii=False)]
    times = []
    for k, label in (("iat", "Ausgestellt"), ("nbf", "Gültig ab"), ("exp", "Läuft ab")):
        if isinstance(pay.get(k), (int, float)):
            d = datetime.fromtimestamp(pay[k])
            times.append(f"{label}: {d:%d.%m.%Y %H:%M:%S}")
            if k == "exp":
                times.append("Status: " + ("ABGELAUFEN" if d < datetime.now() else "noch gültig"))
    if times:
        out += ["", *times]
    out += ["", "Signatur wird nicht geprüft."]
    return "\n".join(out)


@tool("timestamp", "Zeitstempel-Konverter", CAT, "Unix-Zeit in Datum umrechnen und umgekehrt.", "clock",
      [F("text", "text", "Zeitstempel oder Datum", "", placeholder="1767225600 oder 2026-01-01 12:00"),
       F("now", "bool", "Aktuelle Zeit anzeigen", True)],
      live=True, output="text", keywords="unix epoch datum")
def timestamp(ctx, text, now):
    t = text.strip()
    if not t:
        return datetime.now().strftime("Jetzt: %d.%m.%Y %H:%M:%S\nUnix:  ") + str(int(time.time())) if now else ""
    dt = None
    if re.fullmatch(r"-?\d+(\.\d+)?", t):
        v = float(t)
        if abs(v) > 1e14:
            v /= 1e6
        elif abs(v) > 1e11:
            v /= 1e3
        dt = datetime.fromtimestamp(v, timezone.utc)
    else:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
                    "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(t, fmt)
                break
            except ValueError:
                pass
        if dt is None:
            raise ToolError("Format nicht erkannt. Probiere z. B. 2026-01-01 12:00 oder 1767225600.")
        if dt.tzinfo is None:
            dt = dt.astimezone()  # lokale Zeit
    ts = dt.timestamp()
    loc = dt.astimezone()
    return "\n".join([f"Unix (s):  {int(ts)}", f"Unix (ms): {int(ts * 1000)}",
                      f"UTC:       {dt.astimezone(timezone.utc):%Y-%m-%d %H:%M:%S}",
                      f"Lokal:     {loc:%d.%m.%Y %H:%M:%S} ({loc.tzname()})",
                      f"ISO 8601:  {dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')}"])


@tool("diff", "Textvergleich", CAT, "Vergleiche zwei Texte Zeile für Zeile.", "git-compare",
      [F("a", "textarea", "Original", "", hint="mono"),
       F("b", "textarea", "Geändert", "", hint="mono"),
       F("ignore_ws", "bool", "Leerzeichen am Rand ignorieren", False)],
      live=True, output="text", keywords="diff unterschied")
def diff(ctx, a, b, ignore_ws):
    if not a and not b:
        return ""
    la, lb = a.splitlines(), b.splitlines()
    if ignore_ws:
        la, lb = [x.strip() for x in la], [x.strip() for x in lb]
    d = list(difflib.unified_diff(la, lb, "Original", "Geändert", lineterm="", n=2))
    return "\n".join(d) if d else "Keine Unterschiede."


@tool("regex", "Regex-Tester", CAT, "Teste reguläre Ausdrücke mit Treffern und Gruppen.", "regex",
      [F("pattern", "text", "Muster", "", placeholder=r"(\w+)@(\w+)\.de"),
       F("text", "textarea", "Text", "", hint="mono"),
       F("flags", "choice", "Optionen", "", options=[["", "Normal"], ["i", "Groß/Klein egal"],
                                                    ["m", "Mehrzeilig"], ["s", "Punkt = Zeilenumbruch"]])],
      live=True, output="text")
def regex(ctx, pattern, text, flags):
    if not pattern:
        return ""
    fl = 0
    for ch in flags:
        fl |= {"i": re.I, "m": re.M, "s": re.S}[ch]
    try:
        rx = re.compile(pattern, fl)
    except re.error as e:
        raise ToolError(f"Ungültiges Muster: {e}")
    ms = list(rx.finditer(text))[:500]
    if not ms:
        return "Keine Treffer."
    out = [f"{len(ms)} Treffer\n"]
    for i, m in enumerate(ms, 1):
        out.append(f"#{i}  [{m.start()}–{m.end()}]  {m.group(0)!r}")
        for gi, g in enumerate(m.groups(), 1):
            out.append(f"     Gruppe {gi}: {g!r}")
        for k, v in m.groupdict().items():
            out.append(f"     {k}: {v!r}")
    return "\n".join(out)


_TRACK = re.compile(r"^(utm_.*|fbclid|gclid|gclsrc|dclid|msclkid|mc_cid|mc_eid|igshid|igsh|si|ref|ref_src|ref_url|"
                    r"_hsenc|_hsmi|yclid|twclid|ttclid|wbraid|gbraid|spm|share_id|feature|pp|s|t|"
                    r"vero_.*|oly_.*|mkt_tok|trk|trkCampaign|sc_.*|cmpid|cid)$", re.I)


def clean_url(u: str) -> str:
    u = u.strip()
    try:
        sp = urlsplit(u)
    except ValueError:
        return u
    if not sp.scheme or not sp.netloc:
        return u
    q = dict(parse_qsl(sp.query, keep_blank_values=True))
    host = sp.netloc.lower()
    # Weiterleitungen auspacken
    for key in ("url", "u", "q", "target", "redirect", "dest"):
        if key in q and q[key].startswith("http") and ("google." in host or "facebook." in host
                                                       or "l." in host.split(".")[0:1] or "redirect" in sp.path):
            return clean_url(unquote(q[key]))
    # t= / s= nur bei Video-/Social-Seiten entfernen, sonst behalten
    keep = [(k, v) for k, v in parse_qsl(sp.query, keep_blank_values=True)
            if not (_TRACK.match(k) and (k not in ("t", "s", "si", "feature", "pp", "ref", "cid")
                                         or any(x in host for x in ("youtu", "twitter", "x.com", "spotify", "instagram"))))]
    path = sp.path
    path = re.sub(r"/amp/?$", "/", path)
    return urlunsplit((sp.scheme, sp.netloc, path, urlencode(keep), ""))


@tool("links", "Links bereinigen", CAT, "Entferne Tracking-Parameter und Weiterleitungen aus Links.", "link",
      [F("text", "textarea", "Links (einer pro Zeile)", "", hint="mono",
         placeholder="https://example.com/?utm_source=x&fbclid=abc")],
      live=True, output="text", new=True, keywords="tracking utm bereinigen")
def links(ctx, text):
    return "\n".join(clean_url(l) if l.strip() else "" for l in text.splitlines())


def _parse_coord(s: str):
    s = s.strip().replace(",", " ").replace("°", " ").replace("′", "'").replace("″", '"')
    nums = re.findall(r"-?\d+(?:\.\d+)?", s)
    if len(nums) == 2 and "'" not in s:
        return float(nums[0]), float(nums[1])
    m = re.findall(r"(\d+)\s*[°\s]\s*(\d+)\s*'\s*(\d+(?:\.\d+)?)\s*\"?\s*([NSEWO])", s, re.I)
    if len(m) == 2:
        vals = []
        for d, mi, se, h in m:
            v = int(d) + int(mi) / 60 + float(se) / 3600
            vals.append(-v if h.upper() in "SW" else v)
        return vals[0], vals[1]
    raise ToolError("Koordinaten nicht erkannt. Beispiel: 52.5200, 13.4050")


def _dms(v, pos, neg):
    h = pos if v >= 0 else neg
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    s = (v - d - m / 60) * 3600
    return f"{d}° {m}′ {s:.2f}″ {h}"


@tool("coords", "Koordinaten-Picker", CAT, "Rechne Koordinaten um und erzeuge Kartenlinks.", "map-pin",
      [F("text", "text", "Koordinaten", "", placeholder="52.5200, 13.4050 oder 52°31'12\"N 13°24'18\"E")],
      live=True, output="text", new=True, keywords="gps karte breitengrad")
def coords(ctx, text):
    if not text.strip():
        return ""
    lat, lon = _parse_coord(text)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ToolError("Breite muss zwischen −90 und 90 liegen, Länge zwischen −180 und 180.")
    return "\n".join([f"Dezimal:  {lat:.6f}, {lon:.6f}", f"Grad:     {_dms(lat, 'N', 'S')}  {_dms(lon, 'E', 'W')}",
                      f"geo-URI:  geo:{lat:.6f},{lon:.6f}", "",
                      f"OpenStreetMap:\nhttps://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=15/{lat:.5f}/{lon:.5f}",
                      "", f"Google Maps:\nhttps://www.google.com/maps?q={lat:.6f},{lon:.6f}"])


@tool("unicode", "Unicode-Inspektor", CAT, "Zeige Codepoints, Namen und Bytes jedes Zeichens.", "scan-text",
      [F("text", "textarea", "Text", "", placeholder="Hällo 👋")],
      live=True, output="text", new=True)
def unicode_inspect(ctx, text):
    if not text:
        return ""
    rows = [f"{len(text)} Zeichen · {len(text.encode())} Bytes (UTF-8)\n"]
    for ch in text[:300]:
        cp = ord(ch)
        name = unicodedata.name(ch, "(kein Name)")
        shown = ch if ch.isprintable() and not ch.isspace() else "·"
        rows.append(f"{shown}  U+{cp:04X}  {name}  [{unicodedata.category(ch)}]  {ch.encode().hex(' ').upper()}")
    if len(text) > 300:
        rows.append("… (gekürzt)")
    return "\n".join(rows)


_LATIN = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore "
          "magna aliqua ut enim ad minim veniam quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo "
          "consequat duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
          "pariatur excepteur sint occaecat cupidatat non proident sunt in culpa qui officia deserunt mollit anim id "
          "est laborum").split()


@tool("lorem", "Lorem Ipsum", CAT, "Erzeuge Platzhaltertext.", "text-quote",
      [F("unit", "choice", "Einheit", "p", options=[["p", "Absätze"], ["s", "Sätze"], ["w", "Wörter"]]),
       F("n", "number", "Anzahl", 3, min=1, max=200),
       F("start", "bool", "Mit „Lorem ipsum“ beginnen", True)],
      live=True, output="text", new=True)
def lorem(ctx, unit, n, start):
    rnd = random.Random(42)
    n = int(max(1, min(200, n)))

    def sentence(first=False):
        w = [rnd.choice(_LATIN) for _ in range(rnd.randint(7, 15))]
        if first and start:
            w[:2] = ["lorem", "ipsum"]
        return " ".join(w).capitalize() + "."

    if unit == "w":
        w = [rnd.choice(_LATIN) for _ in range(n)]
        if start and n >= 2:
            w[:2] = ["lorem", "ipsum"]
        return " ".join(w)
    if unit == "s":
        return " ".join(sentence(i == 0) for i in range(n))
    return "\n\n".join(" ".join(sentence(i == 0 and j == 0) for j in range(rnd.randint(3, 6))) for i in range(n))
