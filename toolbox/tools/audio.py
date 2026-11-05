"""Audio-Werkzeuge (FFmpeg)."""
from __future__ import annotations

import time
import threading
from pathlib import Path

from ..context import ToolError, which
from ..registry import F, tool
from .video import batch, tsec

CAT = "audio"
AUD = dict(filter="media")


@tool("denoise", "Audio bereinigen", CAT, "Reduziere Hintergrundrauschen und Brummen in Sprachaufnahmen und Videos.",
      "wand-sparkles",
      [F("files", "files", "Audio oder Video", **AUD),
       F("strength", "choice", "Stärke", "mid", options=[["low", "Leicht"], ["mid", "Mittel"], ["high", "Stark"]]),
       F("hum", "bool", "Brummen entfernen (50/60 Hz)", True),
       F("norm", "bool", "Lautstärke angleichen", True)],
      needs=["ffmpeg"], keywords="rauschen noise brummen")
def denoise(ctx, files, strength, hum, norm):
    nr = {"low": 10, "mid": 16, "high": 24}[strength]
    chain = ["highpass=f=70"]
    if hum:
        chain += ["bandreject=f=50:width_type=q:w=30", "bandreject=f=100:width_type=q:w=30"]
    chain += [f"afftdn=nr={nr}:nf=-35:tn=1", "afftdn=nr=6:nf=-45"]
    if norm:
        chain.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    def one(c, f):
        p = Path(f)
        is_video = p.suffix.lower() in (".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v")
        if is_video:
            c.ffmpeg(["-i", f, "-af", ",".join(chain), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                      c.out(f"{p.stem} bereinigt{p.suffix}")], c.duration(f))
        else:
            c.ffmpeg(["-i", f, "-af", ",".join(chain), c.out(f"{p.stem} bereinigt.wav" if p.suffix.lower() == ".wav"
                                                              else f"{p.stem} bereinigt.flac")], c.duration(f))
    batch(ctx, files, one)


@tool("arecord", "Audio aufnehmen", CAT, "Nimm Sprache über dein Mikrofon oder den Systemton auf.", "mic",
      [F("src", "choice", "Quelle", "mic", options=[["mic", "Mikrofon"], ["system", "Systemton"], ["both", "Beides"]]),
       F("fmt", "choice", "Format", "m4a", options=[["m4a", "M4A"], ["mp3", "MP3"], ["wav", "WAV"], ["flac", "FLAC"]]),
       F("max", "number", "Maximale Dauer", 3600, min=5, max=86400, placeholder="Sekunden")],
      needs=["ffmpeg"], stoppable=True, keywords="mikrofon aufnahme sprachmemo")
def arecord(ctx, src, fmt, max):
    out = ctx.out(f"Aufnahme.{fmt}")
    inputs = []
    if src in ("mic", "both"):
        inputs += ["-f", "pulse", "-i", "@DEFAULT_SOURCE@"]
    if src in ("system", "both"):
        inputs += ["-f", "pulse", "-i", "@DEFAULT_MONITOR@"]
    args = [which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-t", str(int(max)), *inputs]
    if src == "both":
        args += ["-filter_complex", "amix=inputs=2:normalize=0"]
    codec = {"m4a": ["-c:a", "aac", "-b:a", "192k"], "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
             "wav": ["-c:a", "pcm_s16le"], "flac": ["-c:a", "flac"]}[fmt]
    ctx.log("Aufnahme läuft …")
    t0 = time.time()
    done = threading.Event()

    def tick():
        while not done.wait(0.5):
            s = int(time.time() - t0)
            ctx.log(f"{s // 60:02d}:{s % 60:02d}")
    threading.Thread(target=tick, daemon=True).start()
    try:
        ctx.run(args + codec + [out])
    finally:
        done.set()


@tool("atrim", "Audio kürzen", CAT, "Schneide Anfang und Ende einer Audiodatei.", "scissors",
      [F("file", "file", "Audio", **AUD),
       F("start", "text", "Start", "0:00"),
       F("end", "text", "Ende (leer = bis zum Schluss)", ""),
       F("fade", "bool", "Weich ein-/ausblenden", False)],
      needs=["ffmpeg"])
def atrim(ctx, file, start, end, fade):
    f = file[0]
    s = tsec(start)
    e = tsec(end) if end.strip() else None
    if e is not None and e <= s:
        raise ToolError("Das Ende muss nach dem Start liegen.")
    d = (e or ctx.duration(f)) - s
    args = ["-ss", str(s)] + (["-to", str(e)] if e else []) + ["-i", f]
    if fade:
        args += ["-af", f"afade=t=in:d=0.5,afade=t=out:st={max(0, d - 0.5)}:d=0.5"]
    else:
        args += ["-c", "copy"]
    ctx.ffmpeg(args + [ctx.out(Path(f).stem + " gekürzt" + Path(f).suffix)], d)


@tool("aextract", "Audio extrahieren", CAT, "Ziehe die Tonspur aus einem Video.", "audio-lines",
      [F("files", "files", "Videos", filter="video"),
       F("fmt", "choice", "Format", "mp3", options=[["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"], ["flac", "FLAC"],
                                                    ["opus", "Opus"]])],
      needs=["ffmpeg"])
def aextract(ctx, files, fmt):
    codec = {"mp3": ["-c:a", "libmp3lame", "-q:a", "0"], "m4a": ["-c:a", "aac", "-b:a", "256k"],
             "wav": ["-c:a", "pcm_s16le"], "flac": ["-c:a", "flac"], "opus": ["-c:a", "libopus", "-b:a", "160k"]}[fmt]
    batch(ctx, files, lambda c, f: c.ffmpeg(["-i", f, "-vn", *codec, c.out(f"{Path(f).stem}.{fmt}")], c.duration(f)))


@tool("aconvert", "Audio umwandeln", CAT, "Wandle Audio in MP3, WAV, FLAC, M4A, OGG oder Opus um.", "repeat",
      [F("files", "files", "Audiodateien", filter="audio"),
       F("fmt", "choice", "Zielformat", "mp3", options=[["mp3", "MP3"], ["wav", "WAV"], ["flac", "FLAC"], ["m4a", "M4A"],
                                                       ["ogg", "OGG"], ["opus", "Opus"]]),
       F("q", "choice", "Qualität", "high", options=[["std", "Standard"], ["high", "Hoch"], ["max", "Maximal"]])],
      needs=["ffmpeg"])
def aconvert(ctx, files, fmt, q):
    br = {"std": "128k", "high": "192k", "max": "320k"}[q]
    codec = {"mp3": ["-c:a", "libmp3lame", "-b:a", br], "wav": ["-c:a", "pcm_s16le"], "flac": ["-c:a", "flac"],
             "m4a": ["-c:a", "aac", "-b:a", br], "ogg": ["-c:a", "libvorbis", "-b:a", br],
             "opus": ["-c:a", "libopus", "-b:a", br]}[fmt]
    batch(ctx, files, lambda c, f: c.ffmpeg(["-i", f, "-vn", *codec, c.out(f"{Path(f).stem}.{fmt}")], c.duration(f)))
