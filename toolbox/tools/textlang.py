"""Text & Sprache: Transkription, OCR, Übersetzung, Sprachausgabe, lokale KI (Ollama)."""
from __future__ import annotations

import collections
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .. import settings
from ..context import ToolError
from ..registry import F, tool
from .images import download, fetch_model, open_img

CAT = "text"

LANGS = [["de", "Deutsch"], ["en", "Englisch"], ["fr", "Französisch"], ["es", "Spanisch"], ["it", "Italienisch"],
         ["pt", "Portugiesisch"], ["nl", "Niederländisch"], ["pl", "Polnisch"], ["ru", "Russisch"], ["tr", "Türkisch"],
         ["ja", "Japanisch"], ["zh", "Chinesisch"], ["ko", "Koreanisch"], ["ar", "Arabisch"]]


# ---------------------------------------------------------------------------
# Transkription
_models: dict = {}


def whisper(ctx, name):
    if name in _models:
        return _models[name]
    from faster_whisper import WhisperModel
    import os
    ctx.log(f"Lade Sprachmodell „{name}“ (beim ersten Mal ein Download) …")
    m = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=max(2, (os.cpu_count() or 4) - 2),
                     download_root=str(settings.models_dir() / "whisper"))
    _models[name] = m
    return m


def ts(t: float, vtt=False) -> str:
    h, rem = divmod(int(t * 1000), 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{'.' if vtt else ','}{ms:03d}"


def segments(ctx, path, lang, p0=0.0, p1=1.0, model=None):
    m = whisper(ctx, model or settings.get("whisper_model"))
    dur = ctx.duration(path) or 1.0
    ctx.log("Transkribiere …")
    it, info = m.transcribe(str(path), language=lang or None, vad_filter=True, beam_size=5,
                            vad_parameters=dict(min_silence_duration_ms=500))
    out = []
    for seg in it:
        out.append(seg)
        ctx.progress(p0 + (p1 - p0) * min(1.0, seg.end / dur))
        ctx.log(seg.text.strip()[:80])
    return out, info


def transcribe_to_srt(ctx, path, lang, out_path, p0=0.0, p1=1.0):
    segs, _ = segments(ctx, path, lang, p0, p1)
    out_path.write_text(srt_text(segs), encoding="utf-8")
    return out_path


def srt_text(segs, vtt=False):
    lines = ["WEBVTT\n"] if vtt else []
    for i, s in enumerate(segs, 1):
        if not vtt:
            lines.append(str(i))
        lines.append(f"{ts(s.start, vtt)} --> {ts(s.end, vtt)}")
        lines.append(s.text.strip() + "\n")
    return "\n".join(lines)


@tool("transcribe", "Transkribieren", CAT, "Mach aus Sprache in Audio und Video ein Transkript mit Zeitstempeln – lokal mit Whisper.",
      "mic-vocal",
      [F("files", "files", "Audio oder Video", filter="media"),
       F("lang", "choice", "Sprache", "", options=[["", "Automatisch"]] + LANGS),
       F("fmt", "choice", "Ausgabe", "txt", options=[["txt", "Text"], ["ts", "Text mit Zeitstempeln"], ["srt", "SRT-Untertitel"],
                                                   ["vtt", "VTT-Untertitel"]]),
       F("model", "choice", "Genauigkeit", "", options=[["", "Aus Einstellungen"], ["base", "Schnell"], ["small", "Ausgewogen"],
                                                      ["large-v3-turbo", "Beste (langsamer)"]])],
      output="both", keywords="whisper sprache zu text untertitel diktat speech")
def transcribe(ctx, files, lang, fmt, model):
    shown = []
    for i, f in enumerate(files):
        n = len(files)
        segs, info = segments(ctx, f, lang, i / n, (i + 1) / n, model or None)
        stem = Path(f).stem
        if fmt == "txt":
            body = "\n".join(s.text.strip() for s in segs)
            ext = "txt"
        elif fmt == "ts":
            body = "\n".join(f"[{ts(s.start).split(',')[0]}] {s.text.strip()}" for s in segs)
            ext = "txt"
        else:
            body = srt_text(segs, fmt == "vtt")
            ext = fmt
        ctx.out(f"{stem}.{ext}").write_text(body, encoding="utf-8")
        shown.append((f"— {Path(f).name} —\n" if len(files) > 1 else "") + body)
    return {"text": "\n\n".join(shown)}


# ---------------------------------------------------------------------------
# Textquellen
def read_text(ctx, path) -> str:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".txt", ".md", ".markdown", ".srt", ".vtt", ".csv", ".html", ".htm", ".json"):
        t = p.read_text(errors="replace")
        if ext in (".html", ".htm"):
            t = re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S | re.I)
            t = re.sub(r"<[^>]+>", " ", t)
        return t
    if ext == ".docx":
        import docx
        d = docx.Document(str(p))
        return "\n".join(par.text for par in d.paragraphs)
    if ext == ".pdf":
        import pymupdf
        d = pymupdf.open(str(p))
        txt = "\n".join(pg.get_text() for pg in d)
        if len(txt.strip()) < 20:
            from .ocr import ocr_text
            from PIL import Image
            parts = []
            for i, pg in enumerate(d):
                pix = pg.get_pixmap(dpi=200)
                parts.append(ocr_text(ctx, Image.frombytes("RGB", (pix.w, pix.h), pix.samples)))
                ctx.progress(0.5 * (i + 1) / len(d))
            txt = "\n\n".join(parts)
        return txt
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".heic", ".avif"):
        from .ocr import ocr_text
        return ocr_text(ctx, open_img(p))
    raise ToolError(f"Dateityp {ext or '?'} wird nicht unterstützt.")


@tool("ocr", "Text extrahieren", CAT, "Erkenne Text in Bildern, Bildschirmfotos und gescannten PDFs.", "text-select",
      [F("files", "files", "Bilder oder PDFs", filter="pdfimg")],
      output="both", keywords="ocr texterkennung scan bild zu text")
def ocr(ctx, files):
    shown = []
    for i, f in enumerate(files):
        ctx.log(Path(f).name)
        t = read_text(ctx, f)
        ctx.out(Path(f).stem + ".txt").write_text(t, encoding="utf-8")
        shown.append((f"— {Path(f).name} —\n" if len(files) > 1 else "") + t)
        ctx.progress((i + 1) / len(files))
    return {"text": "\n\n".join(shown)}


@tool("capture-text", "Text erfassen", CAT, "Wähle einen Bereich auf dem Bildschirm – der Text darin wird erkannt und kopiert.",
      "scan-text",
      [F("copy", "bool", "Automatisch in die Zwischenablage kopieren", True)],
      output="text", keywords="bildschirm ocr screenshot kopieren")
def capture_text(ctx, copy):
    from ..portal import screenshot
    from .ocr import ocr_text
    ctx.log("Wähle einen Bereich …")
    path = screenshot(True)
    t = ocr_text(ctx, open_img(path))
    if copy and t and shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=t, text=True)
    return t or "Kein Text erkannt."


# ---------------------------------------------------------------------------
# Übersetzung (Argos-Modelle direkt über CTranslate2, ohne PyTorch)
ARGOS_INDEX = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
_tr: dict = {}


def _argos_dir() -> Path:
    d = settings.models_dir() / "translate"
    d.mkdir(exist_ok=True)
    return d


def _ensure_pair(ctx, a, b) -> Path:
    d = _argos_dir() / f"{a}-{b}"
    if (d / "model").exists():
        return d
    ctx.log(f"Lade Übersetzungsmodell {a} → {b} (einmalig) …")
    idx = _argos_dir() / "index.json"
    if not idx.exists():
        download(ctx, ARGOS_INDEX, idx, 0.05)
    entries = [e for e in json.loads(idx.read_text()) if e.get("from_code") == a and e.get("to_code") == b]
    if not entries:
        raise ToolError(f"Für {a} → {b} gibt es kein Modell.")
    link = entries[-1]["links"][0]
    z = _argos_dir() / f"{a}-{b}.argosmodel"
    download(ctx, link, z, 0.5)
    with zipfile.ZipFile(z) as zf:
        tmp = _argos_dir() / f".x-{a}-{b}"
        shutil.rmtree(tmp, ignore_errors=True)
        zf.extractall(tmp)
    inner = next(p for p in tmp.iterdir() if p.is_dir())
    shutil.rmtree(d, ignore_errors=True)
    shutil.move(str(inner), d)
    shutil.rmtree(tmp, ignore_errors=True)
    z.unlink(missing_ok=True)
    return d


def _pair_translator(ctx, a, b):
    key = (a, b)
    if key not in _tr:
        import ctranslate2
        import sentencepiece as spm
        d = _ensure_pair(ctx, a, b)
        sp = spm.SentencePieceProcessor(model_file=str(d / "sentencepiece.model"))
        t = ctranslate2.Translator(str(d / "model"), device="cpu", compute_type="int8", inter_threads=1, intra_threads=0)
        _tr[key] = (t, sp)
    return _tr[key]


def split_sentences(text: str) -> list[str]:
    out = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        out += [s for s in re.split(r"(?<=[.!?…。！？])\s+", para.strip()) if s]
        out.append("\n")
    return out


def translate_lines(ctx, lines: list[str], src: str, dst: str) -> list[str]:
    if src == dst:
        return lines
    pairs = [(src, dst)] if src == "en" or dst == "en" else [(src, "en"), ("en", dst)]
    cur = lines
    for a, b in pairs:
        t, sp = _pair_translator(ctx, a, b)
        todo = [(i, s) for i, s in enumerate(cur) if s.strip()]
        res = list(cur)
        B = 16
        for k in range(0, len(todo), B):
            chunk = todo[k:k + B]
            toks = [sp.encode(s, out_type=str) for _, s in chunk]
            outs = t.translate_batch(toks, beam_size=4, max_decoding_length=512, repetition_penalty=1.1)
            for (i, _), o in zip(chunk, outs):
                res[i] = sp.decode(o.hypotheses[0])
            ctx.progress(min(0.95, (k + B) / max(1, len(todo))))
        cur = res
    return cur


def translate_text(ctx, text: str, src: str, dst: str) -> str:
    parts = split_sentences(text)
    res = translate_lines(ctx, parts, src, dst)
    out, buf = [], []
    for p in res:
        if p == "\n":
            out.append(" ".join(buf))
            buf = []
        elif p == "":
            out.append("")
        else:
            buf.append(p)
    if buf:
        out.append(" ".join(buf))
    return "\n".join(out)


def detect_lang(text: str) -> str:
    sample = text.lower()
    scores = {
        "de": sum(sample.count(w) for w in (" der ", " die ", " und ", " das ", " nicht ", " ist ", " ein ", " mit ")),
        "en": sum(sample.count(w) for w in (" the ", " and ", " is ", " of ", " to ", " that ", " with ", " for ")),
        "fr": sum(sample.count(w) for w in (" le ", " la ", " et ", " les ", " des ", " est ", " une ", " que ")),
        "es": sum(sample.count(w) for w in (" el ", " la ", " y ", " los ", " de ", " que ", " una ", " es ")),
        "it": sum(sample.count(w) for w in (" il ", " di ", " che ", " la ", " e ", " per ", " una ", " non ")),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "en"


@tool("translate", "Übersetzen", CAT, "Übersetze Texte, Dokumente und Untertitel auf dem Gerät – ohne Cloud.", "languages",
      [F("text", "textarea", "Text", "", placeholder="Text einfügen …"),
       F("files", "files", "…oder Dateien (TXT, MD, SRT, DOCX)", filter="text", optional=True),
       F("src", "choice", "Von", "auto", options=[["auto", "Erkennen"]] + LANGS[:10]),
       F("dst", "choice", "Nach", "en", options=LANGS[:10])],
      output="both", keywords="übersetzer deepl google translate sprache")
def translate(ctx, text, files, src, dst):
    shown = []
    if text.strip():
        s = detect_lang(" " + text + " ") if src == "auto" else src
        shown.append(translate_text(ctx, text, s, dst))
    for f in files or []:
        p = Path(f)
        ext = p.suffix.lower()
        if ext == ".srt":
            blocks = re.split(r"\n\s*\n", p.read_text(errors="replace").strip())
            heads, bodies = [], []
            for b in blocks:
                ls = b.splitlines()
                heads.append("\n".join(ls[:2]))
                bodies.append(" ".join(ls[2:]))
            s = detect_lang(" " + " ".join(bodies[:80]) + " ") if src == "auto" else src
            tr = translate_lines(ctx, bodies, s, dst)
            body = "\n\n".join(f"{h}\n{t}" for h, t in zip(heads, tr)) + "\n"
            ctx.out(f"{p.stem} {dst}.srt").write_text(body, encoding="utf-8")
        elif ext == ".docx":
            import docx
            d = docx.Document(str(p))
            paras = [x for x in d.paragraphs if x.text.strip()]
            s = detect_lang(" " + " ".join(x.text for x in paras[:40]) + " ") if src == "auto" else src
            tr = translate_lines(ctx, [x.text for x in paras], s, dst)
            for para, t in zip(paras, tr):
                runs = para.runs
                if runs:
                    runs[0].text = t
                    for r in runs[1:]:
                        r.text = ""
                else:
                    para.text = t
            d.save(ctx.out(f"{p.stem} {dst}.docx"))
        else:
            t = read_text(ctx, f)
            s = detect_lang(" " + t[:4000] + " ") if src == "auto" else src
            res = translate_text(ctx, t, s, dst)
            ctx.out(f"{p.stem} {dst}.txt").write_text(res, encoding="utf-8")
            shown.append(res)
    if not shown and not ctx.outputs:
        raise ToolError("Gib einen Text ein oder wähle Dateien.")
    return {"text": "\n\n".join(shown)}


# ---------------------------------------------------------------------------
# Sprachausgabe (Piper)
VOICES = {
    "de": ("de/de_DE/thorsten/medium", "de_DE-thorsten-medium"), "en": ("en/en_US/lessac/medium", "en_US-lessac-medium"),
    "fr": ("fr/fr_FR/siwis/medium", "fr_FR-siwis-medium"), "es": ("es/es_ES/davefx/medium", "es_ES-davefx-medium"),
    "it": ("it/it_IT/paola/medium", "it_IT-paola-medium"), "pt": ("pt/pt_BR/faber/medium", "pt_BR-faber-medium"),
    "nl": ("nl/nl_BE/nathalie/medium", "nl_BE-nathalie-medium"),
    "pl": ("pl/pl_PL/darkman/medium", "pl_PL-darkman-medium"), "ru": ("ru/ru_RU/denis/medium", "ru_RU-denis-medium"),
    "tr": ("tr/tr_TR/dfki/medium", "tr_TR-dfki-medium"), "zh": ("zh/zh_CN/huayan/medium", "zh_CN-huayan-medium"),
}


@tool("tts", "Text zu Sprache", CAT, "Lass dir Text von einer natürlichen Stimme vorlesen und speichere ihn als Audio.", "audio-lines",
      [F("text", "textarea", "Text", "", placeholder="Was soll vorgelesen werden?"),
       F("files", "files", "…oder Textdatei", filter="text", optional=True),
       F("lang", "choice", "Stimme", "de", options=[[k, dict(LANGS).get(k, k)] for k in VOICES]),
       F("speed", "slider", "Tempo", 1.0, min=0.6, max=1.6, step=0.05, placeholder="×"),
       F("fmt", "choice", "Format", "mp3", options=[["mp3", "MP3"], ["wav", "WAV"], ["m4a", "M4A"]])],
      keywords="vorlesen sprachausgabe stimme tts speech")
def tts(ctx, text, files, lang, speed, fmt):
    import wave
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    t = text.strip() or (read_text(ctx, files[0]) if files else "")
    if not t.strip():
        raise ToolError("Gib einen Text ein oder wähle eine Datei.")
    sub, name = VOICES[lang]
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/" + sub + "/" + name
    onnx = fetch_model(ctx, base + ".onnx", name + ".onnx")
    fetch_model(ctx, base + ".onnx.json", name + ".onnx.json")
    ctx.log("Erzeuge Sprache …")
    voice = PiperVoice.load(str(onnx))
    wav_path = ctx.out_dir / ".tts.wav"
    with wave.open(str(wav_path), "wb") as wf:
        voice.synthesize_wav(t, wf, syn_config=SynthesisConfig(length_scale=1 / speed))
    out = ctx.out(f"Sprache.{fmt}")
    if fmt == "wav":
        shutil.move(wav_path, out)
    else:
        codec = ["-c:a", "libmp3lame", "-q:a", "2"] if fmt == "mp3" else ["-c:a", "aac", "-b:a", "192k"]
        ctx.ffmpeg(["-i", wav_path, *codec, out], 1)
        wav_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Lokales Sprachmodell (Ollama)
def llm(ctx, prompt: str, system: str = "") -> str:
    url = settings.get("llm_url").rstrip("/") + "/api/chat"
    body = {"model": settings.get("llm_model"), "stream": False, "options": {"temperature": 0.3},
            "messages": ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ToolError(f"Das Modell „{settings.get('llm_model')}“ ist nicht installiert.\n"
                            f"Installiere es mit:  ollama pull {settings.get('llm_model')}")
        raise ToolError(f"Ollama-Fehler {e.code}")
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        raise ToolError("Ollama läuft nicht. Starte es mit:  systemctl --user start ollama  (oder  ollama serve)\n"
                        "Installieren: sudo dnf install ollama – dann in den Einstellungen das Modell wählen.")


def chunks(text: str, size=6000) -> list[str]:
    paras, out, cur = text.split("\n"), [], ""
    for p in paras:
        if len(cur) + len(p) > size and cur:
            out.append(cur)
            cur = ""
        cur += p + "\n"
    if cur.strip():
        out.append(cur)
    return out


@tool("summarize", "Zusammenfassen", CAT, "Fasse Texte und Dokumente mit einem lokalen Sprachmodell zusammen.", "text-quote",
      [F("text", "textarea", "Text", "", placeholder="Text einfügen …"),
       F("files", "files", "…oder Dokumente", filter="text", optional=True),
       F("style", "choice", "Stil", "bullets", options=[["bullets", "Stichpunkte"], ["short", "Kurz (3 Sätze)"],
                                                      ["long", "Ausführlich"], ["actions", "Aufgaben & Entscheidungen"]]),
       F("lang", "choice", "Antwortsprache", "same", options=[["same", "Wie der Text"], ["de", "Deutsch"], ["en", "Englisch"]])],
      output="text", keywords="zusammenfassung tl;dr ki llm")
def summarize(ctx, text, files, style, lang):
    src = text.strip() or "\n\n".join(read_text(ctx, f) for f in files or [])
    if not src.strip():
        raise ToolError("Gib einen Text ein oder wähle Dokumente.")
    ask = {"bullets": "Fasse den Text in prägnanten Stichpunkten zusammen.", "short": "Fasse den Text in genau drei Sätzen zusammen.",
           "long": "Schreibe eine ausführliche, gut gegliederte Zusammenfassung.",
           "actions": "Liste die Aufgaben, Entscheidungen und offenen Fragen aus dem Text auf."}[style]
    lg = {"same": "Antworte in der Sprache des Textes.", "de": "Antworte auf Deutsch.", "en": "Answer in English."}[lang]
    sysmsg = f"Du bist ein präziser Assistent. {lg} Erfinde nichts, das nicht im Text steht."
    parts = chunks(src)
    if len(parts) == 1:
        return llm(ctx, f"{ask}\n\n---\n{parts[0]}", sysmsg)
    partial = []
    for i, p in enumerate(parts):
        ctx.progress(i / (len(parts) + 1))
        partial.append(llm(ctx, f"Fasse diesen Abschnitt knapp zusammen:\n\n{p}", sysmsg))
    return llm(ctx, f"{ask}\n\nDies sind Teilzusammenfassungen eines langen Textes:\n\n" + "\n\n".join(partial), sysmsg)


_WORD = re.compile(r"\w+", re.U)


def top_chunks(text: str, question: str, k=4, size=1500) -> str:
    qs = {w.lower() for w in _WORD.findall(question) if len(w) > 3}
    cs = chunks(text, size)
    scored = sorted(cs, key=lambda c: -sum(c.lower().count(w) for w in qs))
    return "\n\n---\n\n".join(scored[:k])


@tool("ask-doc", "Dokument befragen", CAT, "Stelle Fragen zu einem Dokument und bekomme Antworten aus dessen Inhalt.", "message-circle-question",
      [F("files", "files", "Dokumente", filter="text"),
       F("q", "textarea", "Deine Frage", "", placeholder="Was ist die Kündigungsfrist?")],
      output="text", keywords="frage antwort chat pdf ki rag")
def ask_doc(ctx, files, q):
    if not q.strip():
        raise ToolError("Stelle eine Frage.")
    text = "\n\n".join(read_text(ctx, f) for f in files)
    ctx_text = text if len(text) < 9000 else top_chunks(text, q)
    return llm(ctx, f"Dokument:\n{ctx_text}\n\nFrage: {q}", "Beantworte die Frage ausschließlich anhand des Dokuments. "
               "Wenn die Antwort nicht darin steht, sage das ehrlich. Antworte in der Sprache der Frage und nenne wichtige Stellen.")


# ---------------------------------------------------------------------------
@tool("wordcount", "Wortzähler", CAT, "Zähle Wörter, Zeichen, Sätze und schätze die Lesezeit.", "whole-word",
      [F("text", "textarea", "Text", "", placeholder="Text einfügen …")], live=True, output="text", new=True)
def wordcount(ctx, text):
    if not text.strip():
        return ""
    words = _WORD.findall(text)
    sents = [s for s in re.split(r"[.!?…]+\s", text) if s.strip()]
    stop = {"der", "die", "das", "und", "ist", "ein", "eine", "zu", "den", "von", "mit", "the", "and", "to", "of", "a", "in", "es", "im"}
    top = collections.Counter(w.lower() for w in words if len(w) > 3 and w.lower() not in stop).most_common(8)
    rm = len(words) / 220
    nospace = len(re.sub(r"\s", "", text))
    paras = len([p for p in text.split("\n\n") if p.strip()])
    return "\n".join([f"Wörter:            {len(words)}", f"Zeichen:           {len(text)}",
                      f"Ohne Leerzeichen:  {nospace}", f"Sätze:             {len(sents)}",
                      f"Absätze:           {paras}",
                      f"Lesezeit:          {int(rm)} min {int((rm % 1) * 60)} s", "",
                      "Häufigste Wörter:", *[f"  {w}  ×{c}" for w, c in top]])


@tool("case", "Groß-/Kleinschreibung", CAT, "Wandle Text in GROSS, klein, Titel, camelCase, snake_case und mehr um.", "case-sensitive",
      [F("text", "textarea", "Text", "", placeholder="Text einfügen …"),
       F("mode", "choice", "Umwandeln in", "title", options=[["upper", "GROSS"], ["lower", "klein"], ["title", "Titel"],
                                                           ["sentence", "Satz"], ["camel", "camelCase"], ["pascal", "PascalCase"],
                                                           ["snake", "snake_case"], ["kebab", "kebab-case"], ["const", "CONSTANT_CASE"]])],
      live=True, output="text", new=True, keywords="gross klein camel snake")
def case(ctx, text, mode):
    if not text:
        return ""

    def words(s):
        return re.findall(r"[A-Za-zÀ-ÿ0-9]+", re.sub(r"([a-zà-ÿ])([A-ZÀ-Ý])", r"\1 \2", s))
    if mode == "upper":
        return text.upper()
    if mode == "lower":
        return text.lower()
    if mode == "title":
        return re.sub(r"\b(\w)(\w*)", lambda m: m.group(1).upper() + m.group(2).lower(), text)
    if mode == "sentence":
        return re.sub(r"(^|[.!?]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), text.lower())
    w = [x.lower() for x in words(text)]
    if not w:
        return ""
    return {"camel": w[0] + "".join(x.title() for x in w[1:]), "pascal": "".join(x.title() for x in w),
            "snake": "_".join(w), "kebab": "-".join(w), "const": "_".join(w).upper()}[mode]
