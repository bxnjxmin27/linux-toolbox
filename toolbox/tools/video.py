"""Video-Werkzeuge (FFmpeg / yt-dlp)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..context import ToolError, which
from ..registry import F, tool

CAT = "video"
VID = dict(filter="video")


def tsec(s) -> float:
    """„90“, „1:30“, „01:02:03.5“ → Sekunden."""
    s = str(s).strip()
    if not s:
        return 0.0
    try:
        parts = [float(p) for p in s.replace(",", ".").split(":")]
    except ValueError:
        raise ToolError(f"Zeit nicht lesbar: „{s}“. Beispiel: 1:30 oder 90")
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def vstream(ctx, path):
    info = ctx.probe(path)
    for st in info.get("streams", []):
        if st.get("codec_type") == "video":
            return st, info
    raise ToolError("Die Datei enthält keine Videospur.")


def has_audio(ctx, path) -> bool:
    return any(s.get("codec_type") == "audio" for s in ctx.probe(path).get("streams", []))


def each(ctx, files, fn):
    n = len(files)
    for i, f in enumerate(files):
        ctx.log(Path(f).name)
        fn(f, i, n)
        ctx.progress((i + 1) / n)


def sub_progress(ctx, i, n):
    """Fortschritt für Stapelverarbeitung: Teil i von n."""
    base = i / n
    orig = ctx._on_progress
    return lambda v: orig(base + v / n)


class _Scaled:
    """Kontext-Proxy, der Fortschritt einer Datei auf den Gesamtfortschritt abbildet."""
    def __init__(self, ctx, i, n):
        self._ctx, self._i, self._n = ctx, i, n

    def __getattr__(self, k):
        return getattr(self._ctx, k)

    def ffmpeg(self, args, duration=0.0):
        c = self._ctx
        orig = c._on_progress
        c._on_progress = lambda v: orig((self._i + v) / self._n)
        try:
            c.ffmpeg(args, duration)
        finally:
            c._on_progress = orig


def batch(ctx, files, fn):
    n = len(files)
    for i, f in enumerate(files):
        ctx.log(Path(f).name)
        fn(_Scaled(ctx, i, n), f)
    ctx.progress(1.0)


# ---------------------------------------------------------------------------
@tool("video-dl", "Video laden", CAT, "Sichere Videos von YouTube, X, TikTok und mehr.", "download",
      [F("url", "textarea", "Links (einer pro Zeile)", "", placeholder="https://…", hint="mono"),
       F("quality", "choice", "Qualität", "best", options=[["best", "Beste"], ["1080", "1080p"], ["720", "720p"],
                                                          ["480", "480p"], ["audio", "Nur Audio (MP3)"]])],
      needs=["yt-dlp"], keywords="youtube tiktok download herunterladen instagram twitter vimeo")
def video_dl(ctx, url, quality):
    urls = [u.strip() for u in url.splitlines() if u.strip()]
    if not urls:
        raise ToolError("Füge mindestens einen Link ein.")
    rx = re.compile(r"\[download\]\s+([\d.]+)%")
    for i, u in enumerate(urls):
        ctx.log(u)
        cmd = [which("yt-dlp"), "--no-playlist", "--newline", "-o", str(ctx.out_dir / "%(title).150B.%(ext)s"),
               "--no-mtime", "--restrict-filenames" if False else "--no-restrict-filenames"]
        if quality == "audio":
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        else:
            h = "" if quality == "best" else f"[height<={quality}]"
            cmd += ["-f", f"bv*{h}+ba/b{h}", "--merge-output-format", "mp4"]

        def parse(line, i=i):
            m = rx.search(line)
            if m:
                ctx.progress((i + float(m.group(1)) / 100) / len(urls))
        ctx.run(cmd + [u], parse)
    for f in sorted(ctx.out_dir.iterdir()):
        ctx.add_output(f)


@tool("burn-subs", "Untertitel einbrennen", CAT, "Füge einem Video Untertitel aus einer SRT-Datei oder per Transkription hinzu.",
      "captions",
      [F("video", "file", "Video", **VID),
       F("src", "choice", "Quelle", "srt", options=[["srt", "SRT-Datei"], ["auto", "Automatisch transkribieren"]]),
       F("srt", "file", "Untertitel-Datei", filter="srt", showIf="src=srt", optional=True),
       F("lang", "text", "Sprache (leer = automatisch)", "", showIf="src=auto"),
       F("size", "slider", "Schriftgröße", 24, min=12, max=64, step=1),
       F("pos", "choice", "Position", "bottom", options=[["bottom", "Unten"], ["middle", "Mitte"], ["top", "Oben"]])],
      needs=["ffmpeg"])
def burn_subs(ctx, video, src, srt, lang, size, pos):
    v = video[0]
    if src == "auto":
        from .textlang import transcribe_to_srt
        srt_path = transcribe_to_srt(ctx, v, lang or None, ctx.out_dir / "untertitel.srt", 0.0, 0.5)
    else:
        if not srt:
            raise ToolError("Wähle eine SRT-Datei oder schalte auf automatische Transkription.")
        srt_path = Path(srt[0])
    tmp = ctx.out_dir / ".sub.srt"
    shutil.copy(srt_path, tmp)
    align = {"bottom": 2, "middle": 10, "top": 6}[pos]
    style = f"FontSize={int(size)},Alignment={align},Outline=2,Shadow=0,MarginV=28,Bold=1"
    out = ctx.out(Path(v).stem + " mit Untertiteln.mp4")
    st, _ = vstream(ctx, v)
    dur = ctx.duration(v)
    esc = str(tmp).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    ctx.ffmpeg(["-i", v, "-vf", f"subtitles='{esc}':force_style='{style}'", "-c:v", "libx264", "-crf", "18",
                "-preset", "medium", "-c:a", "copy", out], dur)
    tmp.unlink(missing_ok=True)


def atempo_chain(f: float) -> str:
    parts = []
    while f > 2.0:
        parts.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5")
        f /= 0.5
    parts.append(f"atempo={f:.5f}")
    return ",".join(parts)


@tool("speed", "Tempo ändern", CAT, "Beschleunige oder verlangsame Videos ohne Mickymausstimmen.", "gauge",
      [F("files", "files", "Videos", **VID),
       F("factor", "slider", "Geschwindigkeit", 1.5, min=0.25, max=4, step=0.05, placeholder="×")],
      needs=["ffmpeg"], keywords="schneller langsamer zeitlupe zeitraffer")
def speed(ctx, files, factor):
    def one(c, f):
        d = c.duration(f) / factor
        args = ["-i", f, "-filter:v", f"setpts=PTS/{factor}"]
        if has_audio(c, f):
            args += ["-filter:a", atempo_chain(factor)]
        c.ffmpeg(args + ["-c:v", "libx264", "-crf", "18", c.out(f"{Path(f).stem} {factor}x.mp4")], d)
    batch(ctx, files, one)


@tool("frames", "Einzelbilder extrahieren", CAT, "Speichere Bilder aus einem Video – in festen Abständen oder alle Schlüsselbilder.",
      "images",
      [F("video", "file", "Video", **VID),
       F("mode", "choice", "Modus", "every", options=[["every", "Alle X Sekunden"], ["keys", "Schlüsselbilder"],
                                                    ["all", "Jedes Bild"], ["one", "Ein Bild bei …"]]),
       F("sec", "number", "Sekunden", 1, min=0.1, max=3600, showIf="mode=every"),
       F("at", "text", "Zeitpunkt", "0:05", showIf="mode=one"),
       F("fmt", "choice", "Format", "png", options=[["png", "PNG"], ["jpg", "JPG"], ["webp", "WebP"]])],
      needs=["ffmpeg"])
def frames(ctx, video, mode, sec, at, fmt):
    v = video[0]
    d = ctx.out_dir / "Bilder"
    d.mkdir(parents=True, exist_ok=True)
    pat = str(d / f"bild_%05d.{fmt}")
    q = ["-q:v", "2"] if fmt == "jpg" else []
    dur = ctx.duration(v)
    if mode == "every":
        ctx.ffmpeg(["-i", v, "-vf", f"fps=1/{sec}", *q, pat], dur)
    elif mode == "keys":
        ctx.ffmpeg(["-skip_frame", "nokey", "-i", v, "-vsync", "vfr", *q, pat], dur)
    elif mode == "all":
        ctx.ffmpeg(["-i", v, *q, pat], dur)
    else:
        ctx.ffmpeg(["-ss", str(tsec(at)), "-i", v, "-frames:v", "1", *q, pat], 1)
    ctx.add_output(d)
    n = len(list(d.iterdir()))
    return {"message": f"Fertig · {n} Bilder"}


@tool("screenrec", "Bildschirm aufnehmen", CAT, "Nimm einen Bildschirm oder ein Fenster mit Ton auf.", "monitor-play",
      [F("area", "choice", "Aufnehmen", "3", options=[["3", "Bildschirm oder Fenster"], ["1", "Nur Bildschirm"],
                                                    ["2", "Nur Fenster"]],
         hint="Beim Start fragt der Desktop, was aufgenommen werden soll."),
       F("audio", "choice", "Ton", "system", options=[["none", "Kein Ton"], ["system", "System"], ["mic", "Mikrofon"],
                                                    ["both", "System + Mikrofon"]]),
       F("fps", "choice", "Bildrate", "30", options=[["30", "30 fps"], ["60", "60 fps"]]),
       F("max", "number", "Maximale Dauer", 600, min=5, max=14400, placeholder="Sekunden")],
      needs=["gst-launch-1.0"], stoppable=True, keywords="aufzeichnen screen recorder capture")
def screenrec(ctx, area, audio, fps, max):
    import os
    import subprocess
    from ..portal import Portal
    p = Portal()
    try:
        ctx.log("Warte auf Auswahl …")
        fd, node = p.screencast(int(area))
    finally:
        p.close()
    out = ctx.out("Bildschirmaufnahme.mp4")
    pipe = [f"pipewiresrc fd={fd} path={node} do-timestamp=true ! queue max-size-buffers=8 leaky=downstream ! "
            f"videoconvert ! videorate ! video/x-raw,framerate={fps}/1 ! "
            f"x264enc tune=zerolatency speed-preset=veryfast bitrate=9000 key-int-max={int(fps) * 2} ! h264parse ! queue ! mux."]
    if audio != "none":
        devs = []
        if audio in ("system", "both"):
            devs.append("@DEFAULT_MONITOR@")
        if audio in ("mic", "both"):
            devs.append("@DEFAULT_SOURCE@")
        if len(devs) == 2:
            pipe.append("audiomixer name=mix ! audioconvert ! avenc_aac bitrate=160000 ! aacparse ! queue ! mux.")
            for d in devs:
                pipe.append(f"pulsesrc device={d} ! audioconvert ! audioresample ! mix.")
        else:
            pipe.append(f"pulsesrc device={devs[0]} ! audioconvert ! audioresample ! avenc_aac bitrate=160000 ! aacparse ! queue ! mux.")
    pipe.append(f"mp4mux name=mux faststart=true ! filesink location={out}")
    cmd = [which("gst-launch-1.0"), "-e", "-q", *" ".join(pipe).split(" ")]
    # Pipeline als Zeichenkette ausführen (gst-launch parst Leerzeichen-getrennt)
    proc_env = os.environ.copy()
    import threading
    import time
    ctx.log("Aufnahme läuft …")
    done = threading.Event()

    def limiter():
        t0 = time.time()
        while not done.wait(0.5):
            if time.time() - t0 >= max:
                ctx.stop()
                return
    threading.Thread(target=limiter, daemon=True).start()
    ctx._proc = subprocess.Popen(cmd, pass_fds=(fd,), env=proc_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        ctx._proc.wait()
    finally:
        done.set()
        os.close(fd)
    if ctx._cancel.is_set():
        from ..context import Cancelled
        raise Cancelled()
    if not Path(out).exists() or Path(out).stat().st_size == 0:
        raise ToolError("Die Aufnahme ist leer geblieben.")


@tool("vcompress", "Video komprimieren", CAT, "Verkleinere Videodateien, ohne dass sie schlechter aussehen.", "shrink",
      [F("files", "files", "Videos", **VID),
       F("level", "choice", "Stärke", "balanced", options=[["light", "Leicht (beste Qualität)"], ["balanced", "Ausgewogen"],
                                                          ["small", "Klein"], ["tiny", "Winzig"]]),
       F("codec", "choice", "Codec", "h264", options=[["h264", "H.264 (kompatibel)"], ["h265", "H.265 (kleiner)"],
                                                    ["av1", "AV1 (am kleinsten, langsam)"]]),
       F("maxh", "choice", "Höhe begrenzen", "0", options=[["0", "Original"], ["1080", "1080p"], ["720", "720p"],
                                                          ["480", "480p"]])],
      needs=["ffmpeg"], keywords="verkleinern größe reduzieren")
def vcompress(ctx, files, level, codec, maxh):
    crf = {"h264": {"light": 21, "balanced": 25, "small": 29, "tiny": 33},
           "h265": {"light": 24, "balanced": 28, "small": 31, "tiny": 35},
           "av1": {"light": 28, "balanced": 33, "small": 38, "tiny": 43}}[codec][level]
    enc = {"h264": ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf)],
           "h265": ["-c:v", "libx265", "-preset", "medium", "-crf", str(crf), "-tag:v", "hvc1"],
           "av1": ["-c:v", "libsvtav1", "-crf", str(crf), "-preset", "8"]}[codec]
    if shutil.which("ffmpeg") and codec == "av1":
        import subprocess
        enc_list = subprocess.run([which("ffmpeg"), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        if "libsvtav1" not in enc_list:
            raise ToolError("Dein FFmpeg hat keinen AV1-Encoder (libsvtav1). Nimm H.265.")
    before = after = 0

    def one(c, f):
        nonlocal before, after
        o = c.out(f"{Path(f).stem} klein.mp4")
        vf = [] if maxh == "0" else ["-vf", f"scale=-2:'min({maxh},ih)'"]
        aud = ["-c:a", "aac", "-b:a", "128k"] if has_audio(c, f) else []
        c.ffmpeg(["-i", f, *vf, *enc, "-pix_fmt", "yuv420p", *aud, "-movflags", "+faststart", o], c.duration(f))
        before += Path(f).stat().st_size
        after += Path(o).stat().st_size
    batch(ctx, files, one)
    pct = round((1 - after / before) * 100) if before else 0
    mb = lambda b: f"{b / 1e6:.1f} MB" if b < 1e9 else f"{b / 1e9:.2f} GB"  # noqa: E731
    return {"message": f"{mb(before)} → {mb(after)}  (−{pct} %)"}


@tool("vconvert", "Video umwandeln", CAT, "Wandle Videos in MP4, MOV, WebM, M4V oder MKV um.", "repeat",
      [F("files", "files", "Videos", **VID),
       F("fmt", "choice", "Zielformat", "mp4", options=[["mp4", "MP4"], ["mov", "MOV"], ["webm", "WebM"],
                                                      ["m4v", "M4V"], ["mkv", "MKV"]])],
      needs=["ffmpeg"])
def vconvert(ctx, files, fmt):
    def one(c, f):
        o = c.out(f"{Path(f).stem}.{fmt}")
        if fmt == "webm":
            args = ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-c:a", "libopus"]
        elif fmt == "mkv":
            args = ["-c", "copy"]
        else:
            args = ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
            if fmt in ("mp4", "m4v", "mov"):
                args += ["-movflags", "+faststart"]
        c.ffmpeg(["-i", f, *args, o], c.duration(f))
    batch(ctx, files, one)


@tool("vresize", "Videogröße ändern", CAT, "Skaliere Videos auf eine neue Auflösung.", "scaling",
      [F("files", "files", "Videos", **VID),
       F("preset", "choice", "Höhe", "720", options=[["2160", "4K"], ["1440", "1440p"], ["1080", "1080p"],
                                                    ["720", "720p"], ["480", "480p"], ["custom", "Eigene"]]),
       F("w", "number", "Breite", 1280, min=16, max=7680, showIf="preset=custom"),
       F("h", "number", "Höhe (px)", 720, min=16, max=4320, showIf="preset=custom")],
      needs=["ffmpeg"], keywords="auflösung skalieren")
def vresize(ctx, files, preset, w, h):
    sc = f"scale=-2:{preset}" if preset != "custom" else f"scale={int(w) // 2 * 2}:{int(h) // 2 * 2}"

    def one(c, f):
        c.ffmpeg(["-i", f, "-vf", sc, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy",
                  c.out(f"{Path(f).stem} {preset if preset != 'custom' else f'{int(w)}x{int(h)}'}.mp4")], c.duration(f))
    batch(ctx, files, one)


@tool("vcrop", "Video zuschneiden & drehen", CAT, "Schneide ein Video zu, drehe oder spiegle es.", "crop",
      [F("video", "file", "Video", **VID),
       F("crop", "choice", "Zuschnitt (Mitte)", "none", options=[["none", "Keiner"], ["1:1", "1:1"], ["9:16", "9:16"],
                                                               ["16:9", "16:9"], ["4:5", "4:5"], ["4:3", "4:3"]]),
       F("rot", "choice", "Drehen", "0", options=[["0", "Nein"], ["90", "90° rechts"], ["180", "180°"], ["270", "90° links"]]),
       F("flip", "choice", "Spiegeln", "none", options=[["none", "Nein"], ["h", "Horizontal"], ["v", "Vertikal"]])],
      needs=["ffmpeg"])
def vcrop(ctx, video, crop, rot, flip):
    v = video[0]
    vf = []
    if crop != "none":
        a, b = crop.split(":")
        vf.append(f"crop='if(gte(iw/ih,{a}/{b}),ih*{a}/{b},iw)':'if(gte(iw/ih,{a}/{b}),ih,iw*{b}/{a})'")
    vf += {"0": [], "90": ["transpose=1"], "180": ["hflip,vflip"], "270": ["transpose=2"]}[rot]
    vf += {"none": [], "h": ["hflip"], "v": ["vflip"]}[flip]
    if not vf:
        raise ToolError("Wähle einen Zuschnitt, eine Drehung oder eine Spiegelung.")
    ctx.ffmpeg(["-i", v, "-vf", ",".join(vf), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy",
                ctx.out(Path(v).stem + " bearbeitet.mp4")], ctx.duration(v))


@tool("mediainfo", "Medieninfo", CAT, "Zeige Codec, Auflösung, Bitrate und Metadaten einer Datei.", "info",
      [F("file", "file", "Datei", filter="media")], needs=["ffprobe"], output="text")
def mediainfo(ctx, file):
    info = ctx.probe(file[0])
    fm = info.get("format", {})
    out = [f"Datei:     {Path(file[0]).name}", f"Container: {fm.get('format_long_name', '?')}",
           f"Dauer:     {float(fm.get('duration', 0)):.2f} s",
           f"Größe:     {int(fm.get('size', 0)) / 1e6:.2f} MB",
           f"Bitrate:   {int(fm.get('bit_rate', 0)) // 1000} kb/s", ""]
    for i, s in enumerate(info.get("streams", [])):
        t = s.get("codec_type")
        if t == "video":
            fr = s.get("avg_frame_rate", "0/1").split("/")
            fps = float(fr[0]) / float(fr[1]) if len(fr) == 2 and float(fr[1]) else 0
            out.append(f"#{i} Video: {s.get('codec_name')} {s.get('width')}×{s.get('height')} {fps:.2f} fps "
                       f"{s.get('pix_fmt', '')} {int(s.get('bit_rate', 0)) // 1000} kb/s")
        elif t == "audio":
            out.append(f"#{i} Audio: {s.get('codec_name')} {s.get('sample_rate')} Hz {s.get('channels')} Kanäle "
                       f"{int(s.get('bit_rate', 0)) // 1000} kb/s")
        else:
            out.append(f"#{i} {t}: {s.get('codec_name')}")
    tags = fm.get("tags") or {}
    if tags:
        out += ["", "Metadaten:"] + [f"  {k}: {v}" for k, v in tags.items()]
    return "\n".join(out)


@tool("vtrim", "Video kürzen", CAT, "Schneide Anfang und Ende eines Clips ohne Neukodierung.", "scissors",
      [F("video", "file", "Video", **VID),
       F("start", "text", "Start", "0:00", placeholder="0:00"),
       F("end", "text", "Ende (leer = bis zum Schluss)", "", placeholder="1:30"),
       F("precise", "bool", "Bildgenau (neu kodieren)", False)],
      needs=["ffmpeg"], keywords="trim schneiden cut")
def vtrim(ctx, video, start, end, precise):
    v = video[0]
    s, e = tsec(start), tsec(end) if end.strip() else None
    dur = ctx.duration(v)
    if e is not None and e <= s:
        raise ToolError("Das Ende muss nach dem Start liegen.")
    args = ["-ss", str(s)]
    if e is not None:
        args += ["-to", str(e)]
    codec = ["-c:v", "libx264", "-crf", "17", "-c:a", "aac"] if precise else ["-c", "copy"]
    ctx.ffmpeg([*args, "-i", v, *codec, "-avoid_negative_ts", "make_zero", ctx.out(Path(v).stem + " gekürzt" + Path(v).suffix)],
               (e or dur) - s)


@tool("vconcat", "Videos zusammenfügen", CAT, "Hänge mehrere Videos zu einem zusammen.", "combine",
      [F("files", "files", "Videos (in Reihenfolge)", **VID),
       F("size", "choice", "Auflösung", "first", options=[["first", "Wie das erste"], ["1080", "1080p"], ["720", "720p"]])],
      needs=["ffmpeg"], keywords="merge join")
def vconcat(ctx, files, size):
    if len(files) < 2:
        raise ToolError("Wähle mindestens zwei Videos.")
    st, _ = vstream(ctx, files[0])
    w, h = st["width"], st["height"]
    if size != "first":
        h = int(size)
        w = int(round(st["width"] * h / st["height"] / 2)) * 2
    ins, filt = [], []
    total = 0.0
    for i, f in enumerate(files):
        ins += ["-i", f]
        total += ctx.duration(f)
        filt.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]")
        if has_audio(ctx, f):
            filt.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        else:
            filt.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={ctx.duration(f)}[a{i}]")
    cat = "".join(f"[v{i}][a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=1:a=1[v][a]"
    ctx.ffmpeg([*ins, "-filter_complex", ";".join(filt + [cat]), "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", ctx.out("Zusammengefügt.mp4")], total)


@tool("vmute", "Video stummschalten", CAT, "Entferne die Tonspur aus Videos.", "volume-x",
      [F("files", "files", "Videos", **VID)], needs=["ffmpeg"])
def vmute(ctx, files):
    batch(ctx, files, lambda c, f: c.ffmpeg(["-i", f, "-c:v", "copy", "-an", c.out(f"{Path(f).stem} stumm{Path(f).suffix}")],
                                          c.duration(f)))


@tool("replace-audio", "Audio ersetzen", CAT, "Tausche die Tonspur eines Videos gegen eine andere Datei.", "audio-waveform",
      [F("video", "file", "Video", **VID),
       F("audio", "file", "Neue Tonspur", filter="audio"),
       F("shortest", "bool", "Auf kürzeste Länge beschneiden", True),
       F("mix", "bool", "Original-Ton behalten (mischen)", False)],
      needs=["ffmpeg"])
def replace_audio(ctx, video, audio, shortest, mix):
    v, a = video[0], audio[0]
    args = ["-i", v, "-i", a]
    if mix and has_audio(ctx, v):
        args += ["-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]", "-map", "0:v", "-map", "[a]"]
    else:
        args += ["-map", "0:v", "-map", "1:a"]
    args += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    if shortest:
        args.append("-shortest")
    ctx.ffmpeg([*args, ctx.out(Path(v).stem + " neuer Ton.mp4")], ctx.duration(v))


@tool("vgif", "Video in GIF", CAT, "Mach aus Clips hochwertige animierte GIFs.", "film",
      [F("video", "file", "Video", **VID),
       F("start", "text", "Start", "0:00"),
       F("dur", "number", "Länge", 5, min=0.5, max=60, placeholder="Sekunden"),
       F("fps", "slider", "Bilder pro Sekunde", 15, min=5, max=30, step=1),
       F("width", "choice", "Breite", "480", options=[["320", "320"], ["480", "480"], ["640", "640"], ["800", "800"],
                                                    ["0", "Original"]])],
      needs=["ffmpeg"])
def vgif(ctx, video, start, dur, fps, width):
    v = video[0]
    sc = f"scale={width}:-1:flags=lanczos," if width != "0" else ""
    vf = f"fps={int(fps)},{sc}split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
    ctx.ffmpeg(["-ss", str(tsec(start)), "-t", str(dur), "-i", v, "-filter_complex", vf, "-loop", "0",
                ctx.out(Path(v).stem + ".gif")], dur)
