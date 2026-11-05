"""System-Werkzeuge für Fedora/GNOME."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from .. import settings
from ..context import ToolError, which
from ..registry import F, tool

CAT = "system"
HOME = Path.home()


def sh(cmd, check=False, timeout=30) -> str:
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise ToolError(f"„{cmd[0]}“ ist nicht installiert.")
    except subprocess.TimeoutExpired:
        raise ToolError(f"{cmd[0]} antwortet nicht.")
    if check and r.returncode != 0:
        raise ToolError((r.stderr or r.stdout).strip() or f"{cmd[0]} ist fehlgeschlagen.")
    return r.stdout


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1000 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1000
    return str(n)


def dir_size(p: Path) -> int:
    total = 0
    try:
        for root, _, files in os.walk(p, onerror=lambda e: None):
            for f in files:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


# ---------------------------------------------------------------------------
@tool("speedtest", "Netzwerk-Geschwindigkeitstest", CAT, "Miss Download, Upload und Reaktionsfähigkeit – ohne Browser-Tab.", "gauge",
      [F("size", "choice", "Testgröße", "mid", options=[["small", "Schnell (≈ 10 MB)"], ["mid", "Normal (≈ 50 MB)"], ["big", "Genau (≈ 200 MB)"]],
         hint="Der Test nutzt die Server von Cloudflare (speed.cloudflare.com).")],
      output="text", keywords="speedtest internet bandbreite ping latenz")
def speedtest(ctx, size):
    import http.client
    mb = {"small": 10, "mid": 50, "big": 200}[size] * 1_000_000
    host = "speed.cloudflare.com"

    def conn():
        return http.client.HTTPSConnection(host, timeout=20)

    def latency(n=8):
        c = conn()
        c.request("GET", "/__down?bytes=0")
        c.getresponse().read()
        ts = []
        for _ in range(n):
            t = time.perf_counter()
            c.request("GET", "/__down?bytes=0")
            c.getresponse().read()
            ts.append((time.perf_counter() - t) * 1000)
        c.close()
        return ts

    ctx.log("Messe Latenz …")
    base = latency()
    ctx.progress(0.1)

    # Download: 4 parallele Verbindungen
    got = [0]
    lock = threading.Lock()
    loaded_lat: list[float] = []
    stop = threading.Event()

    def dl(part):
        c = conn()
        c.request("GET", f"/__down?bytes={part}")
        r = c.getresponse()
        while chunk := r.read(262144):
            with lock:
                got[0] += len(chunk)
            if stop.is_set():
                break
        c.close()

    def probe():
        c = conn()
        while not stop.is_set():
            t = time.perf_counter()
            try:
                c.request("GET", "/__down?bytes=0")
                c.getresponse().read()
                loaded_lat.append((time.perf_counter() - t) * 1000)
            except Exception:
                break
            time.sleep(0.15)
    ctx.log("Messe Download …")
    th = [threading.Thread(target=dl, args=(mb // 4,)) for _ in range(4)] + [threading.Thread(target=probe)]
    t0 = time.perf_counter()
    for t in th:
        t.start()
    while any(t.is_alive() for t in th[:4]):
        time.sleep(0.2)
        ctx.progress(0.1 + 0.45 * min(1, got[0] / mb))
        ctx.log(f"{got[0] * 8 / 1e6 / max(0.1, time.perf_counter() - t0):.0f} Mbit/s")
    stop.set()
    dt = time.perf_counter() - t0
    down = got[0] * 8 / 1e6 / dt

    # Upload
    up_mb = max(5_000_000, mb // 4)
    sent = [0]

    def ul(part):
        c = conn()
        c.putrequest("POST", "/__up")
        c.putheader("Content-Length", str(part))
        c.putheader("Content-Type", "application/octet-stream")
        c.endheaders()
        blk = b"\0" * 65536
        left = part
        while left > 0:
            n = min(len(blk), left)
            c.send(blk[:n])
            left -= n
            with lock:
                sent[0] += n
        c.getresponse().read()
        c.close()
    ctx.log("Messe Upload …")
    th = [threading.Thread(target=ul, args=(up_mb // 3,)) for _ in range(3)]
    t0 = time.perf_counter()
    for t in th:
        t.start()
    while any(t.is_alive() for t in th):
        time.sleep(0.2)
        ctx.progress(0.55 + 0.45 * min(1, sent[0] / up_mb))
    up = sent[0] * 8 / 1e6 / (time.perf_counter() - t0)

    lat = sorted(base)[len(base) // 2]
    jitter = sum(abs(a - b) for a, b in zip(base, base[1:])) / max(1, len(base) - 1)
    load = sorted(loaded_lat)[len(loaded_lat) // 2] if loaded_lat else lat
    rpm = int(60000 / max(load, 1))
    resp = "Hoch" if rpm > 1000 else "Mittel" if rpm > 200 else "Niedrig"

    hist_f = settings._DIR / "speedtest.json"
    hist = json.loads(hist_f.read_text()) if hist_f.exists() else []
    hist.append({"t": time.strftime("%d.%m.%Y %H:%M"), "down": round(down), "up": round(up), "lat": round(lat)})
    settings._DIR.mkdir(parents=True, exist_ok=True)
    hist_f.write_text(json.dumps(hist[-30:]))
    rows = [f"Download:        {down:7.0f} Mbit/s", f"Upload:          {up:7.0f} Mbit/s",
            f"Latenz:          {lat:7.0f} ms   (Jitter {jitter:.1f} ms)",
            f"Unter Last:      {load:7.0f} ms   → Reaktionsfähigkeit {resp} ({rpm} RPM)", "", "Verlauf:"]
    rows += [f"  {h['t']}   ↓ {h['down']:>5} Mbit/s   ↑ {h['up']:>5} Mbit/s   {h['lat']} ms" for h in reversed(hist[-8:])]
    return "\n".join(rows)


# ---------------------------------------------------------------------------
def _hogs():
    h = HOME
    items = [
        ("Programm-Caches", [h / ".cache"], "Wird bei Bedarf neu angelegt."),
        ("Papierkorb", [h / ".local/share/Trash"], "Dauerhaft gelöscht!"),
        ("Flatpak-App-Caches", list((h / ".var/app").glob("*/cache")) if (h / ".var/app").exists() else [], ""),
        ("Browser-Caches", [h / ".cache/google-chrome", h / ".cache/mozilla", h / ".cache/chromium", h / ".cache/BraveSoftware"], ""),
        ("Python-Pakete (pip)", [h / ".cache/pip", h / ".cache/uv"], ""),
        ("npm / Yarn / pnpm", [h / ".npm/_cacache", h / ".cache/yarn", h / ".local/share/pnpm/store"], ""),
        ("Rust / Cargo", [h / ".cargo/registry", h / ".cargo/git"], ""),
        ("Gradle / Maven", [h / ".gradle/caches", h / ".m2/repository"], "Minecraft-Mods bauen lädt es neu."),
        ("Vorschaubilder", [h / ".cache/thumbnails"], ""),
        ("Alte Downloads (> 180 Tage)", None, "Einzelne Dateien in Downloads."),
        ("Podman / Docker", [h / ".local/share/containers"], "Images und Container!"),
    ]
    return items


@tool("storage", "Speicher-Explorer", CAT, "Sieh, was dein Laufwerk füllt, finde die üblichen Platzfresser und entferne sie sicher.", "hard-drive",
      [F("mode", "choice", "Aktion", "scan", options=[["scan", "Platzfresser finden"], ["clean", "Aufräumen"], ["folder", "Ordner analysieren"]]),
       F("folder", "folder", "Ordner", "", showIf="mode=folder", optional=True),
       F("caches", "bool", "Programm-Caches", True, showIf="mode=clean"),
       F("browser", "bool", "Browser-Caches", False, showIf="mode=clean"),
       F("dev", "bool", "Entwickler-Caches (pip, npm, Cargo, Gradle)", False, showIf="mode=clean"),
       F("thumbs", "bool", "Vorschaubilder", True, showIf="mode=clean"),
       F("trash", "bool", "Papierkorb leeren", False, showIf="mode=clean"),
       F("dl", "bool", "Alte Downloads (> 180 Tage)", False, showIf="mode=clean")],
      output="text", keywords="festplatte platz cache aufräumen ncdu disk")
def storage(ctx, mode, folder, caches, browser, dev, thumbs, trash, dl):
    out = []
    du = shutil.disk_usage(HOME)
    out.append(f"Laufwerk /home:  {human(du.used)} von {human(du.total)} belegt  ({human(du.free)} frei)\n")
    if mode == "folder":
        base = Path(folder or HOME)
        ents = []
        kids = [p for p in base.iterdir() if not p.is_symlink()]
        for i, p in enumerate(kids):
            ents.append((dir_size(p) if p.is_dir() else p.stat().st_size, p))
            ctx.progress((i + 1) / max(1, len(kids)))
            ctx.log(p.name)
        ents.sort(reverse=True)
        tot = sum(s for s, _ in ents) or 1
        out.append(f"{base}\n")
        for s, p in ents[:40]:
            bar = "█" * int(s / tot * 24)
            out.append(f"{human(s):>10}  {bar:<24}  {p.name}{'/' if p.is_dir() else ''}")
        return "\n".join(out)
    if mode == "scan":
        rows = []
        for i, (name, paths, note) in enumerate(_hogs()):
            ctx.log(name)
            if paths is None:
                dd = HOME / "Downloads"
                cutoff = time.time() - 180 * 86400
                size = sum(p.stat().st_size for p in dd.glob("*") if p.is_file() and p.stat().st_mtime < cutoff) if dd.exists() else 0
            else:
                size = sum(dir_size(p) for p in paths if p.exists())
            rows.append((size, name, note))
            ctx.progress((i + 1) / len(_hogs()))
        rows.sort(reverse=True)
        out.append("Platzfresser:\n")
        out += [f"{human(s):>10}  {n}" + (f"   ({note})" if note else "") for s, n, note in rows if s > 1_000_000]
        j = sh(["journalctl", "--disk-usage"])
        if j:
            out.append(f"\nSystem-Journal: {j.strip()}")
        out.append("\nZum Entfernen wähle oben „Aufräumen“. Alles geht erst in den Papierkorb.")
        return "\n".join(out)

    from send2trash import send2trash
    jobs = []
    if caches:
        jobs += [p for p in (HOME / ".cache").glob("*") if p.name not in ("google-chrome", "mozilla", "chromium", "BraveSoftware", "pip", "uv", "yarn", "thumbnails")]
        jobs += list((HOME / ".var/app").glob("*/cache")) if (HOME / ".var/app").exists() else []
    if browser:
        jobs += [HOME / ".cache" / n for n in ("google-chrome", "mozilla", "chromium", "BraveSoftware")]
    if dev:
        jobs += [HOME / ".cache/pip", HOME / ".cache/uv", HOME / ".npm/_cacache", HOME / ".cache/yarn",
                 HOME / ".cargo/registry", HOME / ".gradle/caches"]
    if thumbs:
        jobs += [HOME / ".cache/thumbnails"]
    if dl and (HOME / "Downloads").exists():
        cutoff = time.time() - 180 * 86400
        jobs += [p for p in (HOME / "Downloads").glob("*") if p.is_file() and p.stat().st_mtime < cutoff]
    jobs = [p for p in jobs if p.exists()]
    freed = 0
    for i, p in enumerate(jobs):
        ctx.log(p.name)
        sz = dir_size(p) if p.is_dir() else p.stat().st_size
        try:
            send2trash(str(p))
            freed += sz
        except Exception as e:  # noqa: BLE001
            out.append(f"Übersprungen: {p.name} ({e})")
        ctx.progress((i + 1) / max(1, len(jobs)))
    if trash:
        shutil.rmtree(HOME / ".local/share/Trash/files", ignore_errors=True)
        shutil.rmtree(HOME / ".local/share/Trash/info", ignore_errors=True)
        (HOME / ".local/share/Trash/files").mkdir(parents=True, exist_ok=True)
        (HOME / ".local/share/Trash/info").mkdir(parents=True, exist_ok=True)
        out.append("Papierkorb geleert.")
    out.append(f"{human(freed)} in den Papierkorb gelegt.")
    return {"text": "\n".join(out), "message": f"Fertig · {human(freed)} aufgeräumt"}


# ---------------------------------------------------------------------------
@tool("wifi", "WLAN-Passwort & QR", CAT, "Zeige das Passwort eines gespeicherten WLAN-Netzwerks und erstelle einen QR-Code für Gäste.", "wifi",
      [F("ssid", "text", "Netzwerkname (leer = alle anzeigen)", "", optional=True)],
      needs=["nmcli"], output="both", keywords="wlan wifi passwort gast")
def wifi(ctx, ssid):
    names = [l.split(":")[0] for l in sh(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"]).splitlines() if l.endswith("802-11-wireless")]
    if not names:
        raise ToolError("Keine gespeicherten WLAN-Netzwerke gefunden.")

    def pw(n):
        return sh(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", n]).strip()
    if not ssid.strip():
        return "\n".join(f"{n:<32} {pw(n) or '(offen / nicht lesbar)'}" for n in names)
    n = next((x for x in names if x.lower() == ssid.strip().lower()), None)
    if not n:
        raise ToolError("Netzwerk nicht gefunden. Gespeichert sind:\n" + "\n".join(names))
    p = pw(n)
    import qrcode
    esc = lambda s: re.sub(r'([\\;,:"])', r"\\\1", s)  # noqa: E731
    data = f"WIFI:T:WPA;S:{esc(n)};P:{esc(p)};;" if p else f"WIFI:T:nopass;S:{esc(n)};;"
    qrcode.make(data, box_size=14, border=3).save(ctx.out(f"WLAN {n}.png"))
    return {"text": f"Netzwerk:  {n}\nPasswort:  {p or '(kein Passwort)'}", "message": "Fertig · QR-Code gespeichert"}


@tool("battery", "Batteriezustand", CAT, "Sieh Batteriekapazität, Ladezyklen und Netzteil sowie Ladestände von Zubehör.", "battery-charging",
      [], needs=["upower"], output="text", live=True, keywords="akku laptop zyklen gesundheit")
def battery(ctx):
    devs = sh(["upower", "-e"]).split()
    out = []
    for d in devs:
        if "DisplayDevice" in d:
            continue
        info = sh(["upower", "-i", d])
        g = lambda k: (re.search(rf"^\s*{k}:\s*(.+)$", info, re.M) or [None, ""])[1].strip()  # noqa: E731
        kind = g("native-path") or d.split("/")[-1]
        if "line_power" in d:
            out.append(f"Netzteil:   {'angeschlossen' if g('online') == 'yes' else 'getrennt'}")
            continue
        if not g("percentage"):
            continue
        model = " ".join(x for x in (g("vendor"), g("model")) if x) or kind
        out.append(f"{model}\n  Ladung:      {g('percentage')}   ({g('state')})")
        full, design = g("energy-full"), g("energy-full-design")
        if full and design:
            try:
                f, ds = float(full.split()[0]), float(design.split()[0])
                out.append(f"  Gesundheit:  {f / ds * 100:.0f} %   ({f:.1f} von {ds:.1f} Wh)")
            except ValueError:
                pass
        if g("capacity"):
            out.append(f"  Kapazität:   {g('capacity')}")
        if g("charge-cycles") and g("charge-cycles") != "N/A":
            out.append(f"  Ladezyklen:  {g('charge-cycles')}")
        if g("energy-rate"):
            out.append(f"  Leistung:    {g('energy-rate')}")
        if g("temperature"):
            out.append(f"  Temperatur:  {g('temperature')}")
        if g("time to empty"):
            out.append(f"  Restzeit:    {g('time to empty')}")
        out.append("")
    return "\n".join(out).strip() or "Keine Batterie gefunden."


@tool("awake", "Wach halten", CAT, "Verhindere, dass dein Rechner bei Downloads, Renderings oder Vorträgen einschläft.", "coffee",
      [F("dur", "choice", "Wie lange?", "3600", options=[["1800", "30 Minuten"], ["3600", "1 Stunde"], ["7200", "2 Stunden"],
                                                        ["14400", "4 Stunden"], ["28800", "8 Stunden"], ["inf", "Bis ich beende"]]),
       F("screen", "bool", "Bildschirm anlassen", True)],
      stoppable=True, keywords="koffein caffeine ruhezustand schlafen standby")
def awake(ctx, dur, screen):
    what = "idle:sleep" if screen else "sleep"
    t = "infinity" if dur == "inf" else dur
    if shutil.which("gnome-session-inhibit"):
        cmd = [which("gnome-session-inhibit"), "--inhibit", "idle:suspend" if screen else "suspend", "--reason", "Toolbox: Wach halten",
               "sleep", t]
    else:
        cmd = [which("systemd-inhibit"), f"--what={what}", "--who=Toolbox", "--why=Wach halten", "sleep", t]
    ctx.log("Rechner bleibt wach – „Beenden“ zum Stoppen")
    ctx.run(cmd)
    return {"message": "Beendet · Rechner darf wieder schlafen"}


@tool("uninstall", "App deinstallieren", CAT, "Entferne eine App samt Caches, Einstellungen und Daten, die sie hinterlässt.", "trash-2",
      [F("name", "text", "App-Name", "", placeholder="z. B. Spotify"),
       F("remove", "bool", "Wirklich entfernen (sonst nur Vorschau)", False)],
      output="text", keywords="programm löschen flatpak rpm reste")
def uninstall(ctx, name, remove):
    q = name.strip().lower()
    if len(q) < 2:
        raise ToolError("Gib den Namen der App ein.")
    out, flat, rpms = [], [], []
    if shutil.which("flatpak"):
        for l in sh(["flatpak", "list", "--app", "--columns=application,name"]).splitlines():
            if q in l.lower():
                flat.append(l.split("\t")[0].strip())
    for l in sh(["rpm", "-qa", "--qf", "%{NAME}\n"]).splitlines():
        if l.lower() == q or l.lower().startswith(q):
            rpms.append(l)
    left = []
    for base in (HOME / ".config", HOME / ".cache", HOME / ".local/share", HOME / ".local/state"):
        if base.exists():
            left += [p for p in base.iterdir() if q in p.name.lower().replace(" ", "")
                     or q in p.name.lower()]
    for fid in flat:
        left += [p for p in [HOME / ".var/app" / fid] if p.exists()]
    left = sorted(set(left))
    if not (flat or rpms or left):
        return "Nichts gefunden."
    for f in flat:
        out.append(f"Flatpak:  {f}")
    for r in rpms:
        out.append(f"RPM:      {r}")
    out.append("\nÜbrig gebliebene Daten:")
    total = 0
    for p in left:
        sz = dir_size(p) if p.is_dir() else p.stat().st_size
        total += sz
        out.append(f"  {human(sz):>9}  {p}")
    out.append(f"\nGesamt: {human(total)}")
    if not remove:
        out.append("\nNichts wurde geändert. Setze den Haken, um zu entfernen.")
        return "\n".join(out)
    from send2trash import send2trash
    for f in flat:
        ctx.run(["flatpak", "uninstall", "-y", "--delete-data", f])
    if rpms:
        ctx.log("Authentifizierung für RPM-Entfernung …")
        ctx.run(["pkexec", "dnf", "remove", "-y", *rpms])
    for p in left:
        if p.exists():
            send2trash(str(p))
    return {"text": "\n".join(out) + "\n\nEntfernt.", "message": "Fertig · App entfernt"}


@tool("present", "Präsentationsmodus", CAT, "Ein Schalter, bevor du deinen Bildschirm teilst: Benachrichtigungen aus und wach bleiben.", "presentation",
      [F("dnd", "bool", "Benachrichtigungen ausblenden", True),
       F("awake", "bool", "Wach bleiben", True),
       F("dark", "bool", "Nicht automatisch sperren", True)],
      stoppable=True, keywords="nicht stören vortrag screen share")
def present(ctx, dnd, awake, dark):
    changed = []

    def gset(schema, key, val):
        old = sh(["gsettings", "get", schema, key]).strip()
        sh(["gsettings", "set", schema, key, val])
        changed.append((schema, key, old))
    try:
        if dnd:
            gset("org.gnome.desktop.notifications", "show-banners", "false")
        if dark:
            gset("org.gnome.desktop.screensaver", "lock-enabled", "false")
        cmd = [which("gnome-session-inhibit"), "--inhibit", "idle:suspend", "--reason", "Toolbox: Präsentation", "sleep", "infinity"] \
            if awake and shutil.which("gnome-session-inhibit") else ["sleep", "infinity"]
        ctx.log("Präsentationsmodus ist an – „Beenden“ stellt alles zurück")
        ctx.run(cmd)
    finally:
        for schema, key, old in changed:
            sh(["gsettings", "set", schema, key, old])
    return {"message": "Beendet · Einstellungen zurückgesetzt"}


@tool("cleankeys", "Tastatur reinigen", CAT, "Sperre die Tastatur für eine Minute, damit du die Tasten abwischen kannst – optional mit schwarzem Bildschirm.",
      "keyboard-off",
      [F("secs", "slider", "Dauer", 60, min=15, max=180, step=15, placeholder=" s"),
       F("black", "bool", "Bildschirm schwarz (zum Display-Wischen)", False)],
      keywords="reinigen sperren abwischen")
def cleankeys(ctx, secs, black):
    ctx.overlay("cleankeys", seconds=int(secs), black=bool(black))
    return {"message": "Fertig · Tastatur wieder frei"}


@tool("pixeltest", "Pixelfehler-Test", CAT, "Prüfe dein Display mit Vollfarben auf tote oder hängende Pixel.", "monitor-dot",
      [], new=True, keywords="display bildschirm tote pixel monitor test")
def pixeltest(ctx):
    ctx.overlay("pixeltest")
    return {"message": "Test beendet"}


@tool("eject", "Alle Volumes auswerfen", CAT, "Hänge alle externen Laufwerke mit einem Klick sicher aus.", "usb",
      [], needs=["lsblk"], output="text", keywords="usb stick festplatte auswerfen unmount")
def eject(ctx):
    data = json.loads(sh(["lsblk", "-J", "-o", "NAME,PATH,RM,HOTPLUG,MOUNTPOINTS,TYPE,PKNAME"]) or "{}")
    todo, drives = [], set()

    def walk(n, parent=None):
        mps = [m for m in (n.get("mountpoints") or []) if m]
        if (n.get("rm") or n.get("hotplug")) and any(m.startswith(("/run/media", "/media")) for m in mps):
            todo.append((n["path"], mps[0]))
            drives.add(parent or n["path"])
        for c in n.get("children") or []:
            walk(c, n["path"] if n.get("type") == "disk" else parent)
    for d in data.get("blockdevices", []):
        walk(d, d["path"] if d.get("type") == "disk" else None)
    if not todo:
        return "Keine externen Laufwerke eingehängt."
    out = []
    for dev, mp in todo:
        r = subprocess.run(["udisksctl", "unmount", "-b", dev], capture_output=True, text=True)
        out.append(("✓ " if r.returncode == 0 else "✗ ") + f"{mp}" + ("" if r.returncode == 0 else f"  ({r.stderr.strip()})"))
    for d in drives:
        subprocess.run(["udisksctl", "power-off", "-b", d], capture_output=True, text=True)
    return "\n".join(out) + "\n\nLaufwerke dürfen entfernt werden."


@tool("loginitems", "Anmelde- & Hintergrundobjekte", CAT, "Sieh, was bei der Anmeldung startet und im Hintergrund läuft – und schalte es ab.", "list-checks",
      [F("action", "choice", "Aktion", "list", options=[["list", "Anzeigen"], ["off", "Autostart abschalten"], ["on", "Autostart wieder an"]]),
       F("which", "text", "Name (bei Abschalten)", "", showIf="action=off", optional=True),
       F("which2", "text", "Name", "", showIf="action=on", optional=True)],
      output="text", keywords="autostart startprogramme dienste")
def loginitems(ctx, action, which, which2):
    user = HOME / ".config/autostart"
    entries = {}
    for base in (Path("/etc/xdg/autostart"), user):
        if base.exists():
            for f in base.glob("*.desktop"):
                t = f.read_text(errors="replace")
                nm = (re.search(r"^Name=(.+)$", t, re.M) or [None, f.stem])[1]
                hidden = bool(re.search(r"^(Hidden|X-GNOME-Autostart-enabled)=(true|false)$", t, re.M)) and \
                    (re.search(r"^Hidden=true", t, re.M) or re.search(r"^X-GNOME-Autostart-enabled=false", t, re.M))
                entries[f.name] = (nm, bool(hidden), f)
    if action == "list":
        out = ["Autostart-Programme:"]
        for k, (nm, hid, _) in sorted(entries.items(), key=lambda x: x[1][0].lower()):
            out.append(f"  [{'aus' if hid else 'an '}]  {nm}   ({k})")
        svcs = sh(["systemctl", "--user", "list-unit-files", "--state=enabled", "--type=service", "--no-legend"]).splitlines()
        out += ["", "Benutzer-Dienste (aktiviert):"] + [f"  {s.split()[0]}" for s in svcs if s.strip()]
        return "\n".join(out)
    q = (which if action == "off" else which2).strip().lower()
    hit = [k for k, (nm, _, _) in entries.items() if q and (q in nm.lower() or q in k.lower())]
    if not hit:
        raise ToolError("Kein passender Autostart-Eintrag gefunden.")
    user.mkdir(parents=True, exist_ok=True)
    msg = []
    for k in hit:
        nm, _, f = entries[k]
        target = user / k
        src = f.read_text(errors="replace")
        src = re.sub(r"^(Hidden|X-GNOME-Autostart-enabled)=.*\n?", "", src, flags=re.M)
        if action == "off":
            src = src.rstrip("\n") + "\nHidden=true\nX-GNOME-Autostart-enabled=false\n"
        target.write_text(src)
        msg.append(f"{nm}: {'abgeschaltet' if action == 'off' else 'wieder aktiv'}")
    return "\n".join(msg)


@tool("fixapp", "Blockierte App reparieren", CAT, "Prüfe, warum sich eine heruntergeladene App nicht öffnen lässt, und behebe es.", "wrench",
      [F("file", "file", "Programm / AppImage", filter="any"),
       F("fix", "bool", "Probleme direkt beheben", True)],
      output="text", keywords="appimage startet nicht ausführbar berechtigung beschädigt")
def fixapp(ctx, file, fix):
    p = Path(file[0])
    out = [f"Datei: {p.name}", sh(["file", "-b", p]).strip(), ""]
    st = p.stat()
    problems = []
    if not os.access(p, os.X_OK):
        problems.append("Nicht ausführbar")
        if fix:
            p.chmod(st.st_mode | 0o111)
            out.append("✓ Ausführbar gemacht")
    attrs = sh(["getfattr", "-d", "-m", "-", str(p)]) if shutil.which("getfattr") else ""
    if "xdg" in attrs or "quarantine" in attrs:
        problems.append("Download-Markierung (xattr) gefunden")
        if fix:
            for a in re.findall(r"^(user\.xdg\.[\w.]+)", attrs, re.M):
                sh(["setfattr", "-x", a, str(p)])
            out.append("✓ Download-Markierungen entfernt")
    ft = sh(["file", "-b", p])
    if "ELF" in ft:
        ld = sh(["ldd", str(p)])
        miss = re.findall(r"^\s*(\S+) => not found", ld, re.M)
        if miss:
            problems.append("Fehlende Bibliotheken: " + ", ".join(miss))
            out.append("Fehlend: " + ", ".join(miss) + "\n  → sudo dnf install " + " ".join(f"'*/{m}'" for m in miss))
        if "x86-64" not in ft and "aarch64" not in ft.lower():
            problems.append("Falsche Architektur")
        if "AppImage" in p.name or "appimage" in ft.lower():
            if not shutil.which("fusermount3") and not shutil.which("fusermount"):
                problems.append("FUSE fehlt (für AppImages)")
                out.append("  → sudo dnf install fuse fuse-libs")
    ctx_s = sh(["ls", "-Z", str(p)]).strip()
    out.append("\nSELinux: " + ctx_s.split()[0] if ctx_s else "")
    out.append("\n" + ("Gefundene Probleme:\n  • " + "\n  • ".join(problems) if problems else "Keine offensichtlichen Probleme gefunden."))
    return "\n".join(out)


@tool("resetperms", "Berechtigungen zurücksetzen", CAT, "Setze die Berechtigungen einer Flatpak-App (Kamera, Mikrofon, Dateien …) zurück.", "shield-check",
      [F("action", "choice", "Aktion", "list", options=[["list", "Apps & Berechtigungen anzeigen"], ["reset", "App zurücksetzen"],
                                                      ["all", "Alle Apps zurücksetzen"]]),
       F("app", "text", "App-ID", "", placeholder="z. B. com.discordapp.Discord", showIf="action=reset", optional=True)],
      needs=["flatpak"], output="text", keywords="flatpak rechte kamera mikrofon")
def resetperms(ctx, action, app):
    if action == "list":
        apps = sh(["flatpak", "list", "--app", "--columns=application,name"]).strip()
        perms = sh(["flatpak", "permission-list"]).strip()
        return f"Installierte Apps:\n{apps}\n\nPortal-Berechtigungen:\n{perms or '(keine gespeichert)'}"
    ids = [l.split("\t")[0] for l in sh(["flatpak", "list", "--app", "--columns=application"]).splitlines()] if action == "all" else [app.strip()]
    if not ids or not ids[0]:
        raise ToolError("Gib eine App-ID an.")
    for a in ids:
        sh(["flatpak", "permission-reset", a])
        sh(["flatpak", "override", "--user", "--reset", a])
    return f"Zurückgesetzt: {len(ids)} App{'s' if len(ids) != 1 else ''}"


def _tri(key, label, schema, k, on="true", off="false", opts=None):
    return key, label, schema, k, on, off


_HIDDEN = [
    ("seconds", "Sekunden in der Uhr", "org.gnome.desktop.interface", "clock-show-seconds", "true", "false"),
    ("weekday", "Wochentag in der Uhr", "org.gnome.desktop.interface", "clock-show-weekday", "true", "false"),
    ("batpct", "Akku-Prozent in der Leiste", "org.gnome.desktop.interface", "show-battery-percentage", "true", "false"),
    ("animations", "Animationen", "org.gnome.desktop.interface", "enable-animations", "true", "false"),
    ("hotcorner", "Aktive Ecke (Übersicht)", "org.gnome.desktop.interface", "enable-hot-corners", "true", "false"),
    ("hidden", "Versteckte Dateien in Dateien", "org.gtk.gtk4.Settings.FileChooser", "show-hidden", "true", "false"),
    ("center", "Neue Fenster zentrieren", "org.gnome.mutter", "center-new-windows", "true", "false"),
    ("dynws", "Dynamische Arbeitsflächen", "org.gnome.mutter", "dynamic-workspaces", "true", "false"),
    ("edgetile", "Fenster am Rand andocken", "org.gnome.mutter", "edge-tiling", "true", "false"),
    ("buttons", "Minimieren/Maximieren im Fensterkopf", "org.gnome.desktop.wm.preferences", "button-layout",
     "'appmenu:minimize,maximize,close'", "'appmenu:close'"),
    ("capslock", "Feststelltaste → zweite Esc-Taste", "org.gnome.desktop.input-sources", "xkb-options", "['caps:escape']", "@as []"),
]


@tool("hidden", "Versteckte Einstellungen", CAT, "Schalte Optionen von GNOME um, die du in den Einstellungen nicht findest.", "settings-2",
      [F(k, "choice", label, "", options=[["", "Unverändert"], ["on", "An"], ["off", "Aus"]]) for k, label, *_ in _HIDDEN],
      keywords="gnome gsettings tweaks")
def hidden(ctx, **kw):
    done = []
    for k, label, schema, key, on, off in _HIDDEN:
        v = kw.get(k)
        if v:
            sh(["gsettings", "set", schema, key, on if v == "on" else off], check=True)
            done.append(f"{label}: {'an' if v == 'on' else 'aus'}")
    if not done:
        raise ToolError("Wähle mindestens eine Einstellung.")
    return {"message": "Gesetzt · " + ", ".join(done)}


@tool("monitor", "Monitorsteuerung", CAT, "Ändere Helligkeit, Kontrast und Lautstärke externer Monitore direkt vom Rechner aus.", "sun-medium",
      [F("act", "choice", "Aktion", "show", options=[["show", "Monitore anzeigen"], ["set", "Werte setzen"]]),
       F("disp", "number", "Monitor-Nummer", 1, min=1, max=8, showIf="act=set"),
       F("bright", "slider", "Helligkeit", 50, min=0, max=100, step=1, showIf="act=set", placeholder=" %"),
       F("contrast", "slider", "Kontrast", 50, min=0, max=100, step=1, showIf="act=set", placeholder=" %"),
       F("volume", "choice", "Lautstärke", "", options=[["", "Unverändert"], ["0", "Aus"], ["25", "25 %"], ["50", "50 %"], ["75", "75 %"]],
         showIf="act=set")],
      needs=["ddcutil"], output="text", keywords="ddc helligkeit externer bildschirm")
def monitor(ctx, act, disp, bright, contrast, volume):
    if act == "show":
        det = sh(["ddcutil", "detect", "--brief"], timeout=60)
        if "Display" not in det:
            raise ToolError("Kein steuerbarer Monitor gefunden (DDC/CI aktivieren, Gruppe i2c prüfen).")
        out = [det.strip(), ""]
        for m in re.finditer(r"^Display (\d+)", det, re.M):
            n = m.group(1)
            b = sh(["ddcutil", "--display", n, "getvcp", "10", "--brief"], timeout=30).split()
            c = sh(["ddcutil", "--display", n, "getvcp", "12", "--brief"], timeout=30).split()
            out.append(f"Monitor {n}:  Helligkeit {b[3] if len(b) > 3 else '?'}   Kontrast {c[3] if len(c) > 3 else '?'}")
        return "\n".join(out)
    n = str(int(disp))
    sh(["ddcutil", "--display", n, "setvcp", "10", str(int(bright))], check=True, timeout=30)
    sh(["ddcutil", "--display", n, "setvcp", "12", str(int(contrast))], check=True, timeout=30)
    if volume:
        sh(["ddcutil", "--display", n, "setvcp", "62", volume], check=True, timeout=30)
    return f"Monitor {n}: Helligkeit {int(bright)} %, Kontrast {int(contrast)} %"


_MOUSE = [
    ("accel", "Mausbeschleunigung", "org.gnome.desktop.peripherals.mouse", "accel-profile", "'adaptive'", "'flat'"),
    ("mnat", "Natürliches Scrollen (Maus)", "org.gnome.desktop.peripherals.mouse", "natural-scroll", "true", "false"),
    ("tnat", "Natürliches Scrollen (Touchpad)", "org.gnome.desktop.peripherals.touchpad", "natural-scroll", "true", "false"),
    ("tap", "Tippen zum Klicken (Touchpad)", "org.gnome.desktop.peripherals.touchpad", "tap-to-click", "true", "false"),
    ("dwt", "Touchpad beim Tippen sperren", "org.gnome.desktop.peripherals.touchpad", "disable-while-typing", "true", "false"),
    ("left", "Linkshänder-Tasten", "org.gnome.desktop.peripherals.mouse", "left-handed", "true", "false"),
]


@tool("mousefix", "Maus-Korrekturen", CAT, "Korrigiere Mausverhalten: Beschleunigung aus, Scrollrichtung, Geschwindigkeit und Touchpad.", "mouse-pointer-2",
      [F(k, "choice", label, "", options=[["", "Unverändert"], ["on", "An" if k != "accel" else "Mit Beschleunigung"],
                                          ["off", "Aus" if k != "accel" else "Ohne (flach)"]]) for k, label, *_ in _MOUSE]
      + [F("speed", "choice", "Geschwindigkeit", "", options=[["", "Unverändert"], ["-0.6", "Langsam"], ["-0.2", "Etwas langsamer"],
                                                           ["0", "Standard"], ["0.4", "Schneller"], ["0.8", "Sehr schnell"]])],
      keywords="maus zeiger flat accel scroll touchpad")
def mousefix(ctx, speed, **kw):
    done = []
    for k, label, schema, key, on, off in _MOUSE:
        v = kw.get(k)
        if v:
            sh(["gsettings", "set", schema, key, on if v == "on" else off], check=True)
            done.append(label)
    if speed:
        for s in ("org.gnome.desktop.peripherals.mouse", "org.gnome.desktop.peripherals.touchpad"):
            sh(["gsettings", "set", s, "speed", speed])
        done.append("Geschwindigkeit")
    if not done:
        raise ToolError("Wähle mindestens eine Einstellung.")
    return {"message": "Gesetzt · " + ", ".join(done)}
