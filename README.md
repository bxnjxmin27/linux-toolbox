# Toolbox für Linux

**94 Werkzeuge in einer App – komplett lokal, ohne Konto, ohne Cloud, ohne Abo.**
Video, Audio, Bilder, Dokumente, Text & Sprache, Dateien, System und Entwickler-Werkzeuge in einem schnellen, nativen Fenster.

> Eine Linux-Neuentwicklung nach der Idee von [Toolbox für Mac](https://mactoolbox.app). Unabhängiges Projekt, nicht mit dem Original verbunden – es enthält weder dessen Code noch dessen Grafiken.
> Gebaut für **Fedora / GNOME (Wayland)**, läuft aber auch auf anderen Distributionen.

- **Nativ & schnell:** Qt 6 / QML mit GPU-Rendering, eigene Titelleiste, Start in unter einer Sekunde, ~120 MB RAM im Leerlauf. Schwere Bibliotheken werden erst geladen, wenn ein Werkzeug sie braucht.
- **Privat:** Dateien verlassen den Rechner nie. KI-Funktionen (Whisper, Texterkennung, Übersetzung, Sprachausgabe, Freistellen) laufen lokal.
- **Sicher:** Originale bleiben unberührt. Jeder Durchlauf bekommt einen eigenen, datierten Ordner in `~/Downloads/Toolbox`.
- **Schnell erreichbar:** `Strg+K` öffnet die Suche, Favoriten und „Zuletzt benutzt“, Drag & Drop für Dateien.

## Installation

```bash
git clone https://github.com/bxnjxmin27/linux-toolbox.git
cd linux-toolbox
./install.sh
```

Das Skript legt eine Python-Umgebung an, installiert alle Pakete und erzeugt Starter (`toolbox`) und Anwendungsmenü-Eintrag. Root-Rechte sind nicht nötig.

Für den vollen Umfang empfohlen (Fedora):

```bash
sudo dnf install qpdf tesseract ddcutil zbar wl-clipboard poppler-utils libheif-tools libreoffice
# FFmpeg mit allen Codecs (RPM Fusion):
sudo dnf swap ffmpeg-free ffmpeg --allowerasing
```

| Paket | wofür |
|---|---|
| `ffmpeg` | alle Video- und Audio-Werkzeuge |
| `libreoffice` | Word/PowerPoint/Excel → PDF, Dokumente umwandeln |
| `ddcutil` | Monitorsteuerung |
| `google-chrome` / Chromium | Webseite → PDF |
| `yt-dlp` (`pip install --user yt-dlp`) | Video laden |
| [Ollama](https://ollama.com) | Zusammenfassen, Dokument befragen (lokales Sprachmodell) |

Werkzeuge, denen ein Programm fehlt, zeigen oben einen Hinweis, statt kaputt zu gehen.

## Die Werkzeuge

**Video (15)** · Video laden · Untertitel einbrennen · Tempo ändern · Einzelbilder extrahieren · Bildschirm aufnehmen · Video komprimieren · Video umwandeln · Videogröße ändern · Video zuschneiden & drehen · Medieninfo · Video kürzen · Videos zusammenfügen · Video stummschalten · Audio ersetzen · Video in GIF

**Audio (5)** · Audio bereinigen · Audio aufnehmen · Audio kürzen · Audio extrahieren · Audio umwandeln

**Bilder (11)** · Gesichter verpixeln · Bildschirmfoto verschönern · Hintergrund entfernen · Bilder umwandeln · Bilder komprimieren · Bildgröße ändern · Bilder drehen · Metadaten entfernen · Farbauswahl · Bild schwärzen · Bildschirmfoto beschriften

**Dokumente (22)** · Dokument scannen · PDF schwärzen · Formulare ausfüllen & fixieren · PDF durchsuchbar machen · PDF in Word · PDF signieren · PDFs zusammenfügen · PDF teilen · PDF organisieren · Seiten löschen · Seiten extrahieren · Bilder in PDF · PDF komprimieren · Passwort hinzufügen · Passwort entfernen · PDF in Bilder · Dokumente umwandeln · Word in PDF · PowerPoint in PDF · Excel in PDF · Webseite in PDF · Markdown in PDF

**Text & Sprache (9)** · Transkribieren · Zusammenfassen · Text extrahieren · Text erfassen · Übersetzen · Text zu Sprache · Dokument befragen · Wortzähler · Groß-/Kleinschreibung

**Dateien (4)** · QR-Code · Stapelumbenennung · Duplikate finden · Zippen & Entpacken

**System (16)** · Netzwerk-Geschwindigkeitstest · Speicher-Explorer · WLAN-Passwort & QR · Batteriezustand · Wach halten · App deinstallieren · Präsentationsmodus · Tastatur reinigen · Pixelfehler-Test · Alle Volumes auswerfen · Anmelde- & Hintergrundobjekte · Blockierte App reparieren · Berechtigungen zurücksetzen · Versteckte Einstellungen · Monitorsteuerung · Maus-Korrekturen

**Entwickler (12)** · JSON-Formatierer · Base64 · Hash-Generator · UUID-Generator · JWT-Decoder · Zeitstempel-Konverter · Textvergleich · Regex-Tester · Links bereinigen · Koordinaten-Picker · Unicode-Inspektor · Lorem Ipsum

## Was lokal läuft – und womit

| Aufgabe | Technik |
|---|---|
| Transkription | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CPU, int8) |
| Texterkennung (OCR) | [RapidOCR](https://github.com/RapidAI/RapidOCR) (ONNX) |
| Übersetzung | Argos-/OpusMT-Modelle über CTranslate2 (kein PyTorch) |
| Sprachausgabe | [Piper](https://github.com/OHF-Voice/piper1-gpl) |
| Hintergrund entfernen | [rembg](https://github.com/danielgatis/rembg) (U²-Net / ISNet) |
| Gesichter erkennen | YuNet (OpenCV) |
| Zusammenfassen / Fragen | lokales Modell über Ollama |
| PDF | PyMuPDF, pikepdf, pdf2docx, Ghostscript |
| Video / Audio | FFmpeg, yt-dlp |

Modelle werden beim ersten Einsatz einmalig nach `~/.local/share/linux-toolbox/models` geladen.

## Datenschutz: wann geht die App ins Netz?

Nur bei diesen Aktionen – sonst nie:

- **Video laden** (der Link, den du angibst)
- **Netzwerk-Geschwindigkeitstest** (Cloudflare-Messserver)
- **Webseite in PDF** (die Adresse, die du angibst)
- **einmaliger Modell-Download** (Hugging Face / GitHub) für Transkription, Übersetzung, Sprachausgabe, Freistellen und Gesichtserkennung

Kein Konto, keine Telemetrie, kein Tracking.

## Wayland-Hinweise

Bildschirmaufnahme, Farbwähler und „Text erfassen“ laufen über das Desktop-Portal (`xdg-desktop-portal`) – der Desktop fragt dich bei jeder Aktion. Ein globaler Tastenkürzel zum Öffnen der Suche ist unter Wayland ohne Compositor-Unterstützung nicht möglich; lege dafür in den GNOME-Einstellungen unter *Tastatur → Tastenkürzel* einen eigenen Eintrag mit dem Befehl `toolbox` an.

## Entwickeln

```bash
.venv/bin/python main.py                  # starten
.venv/bin/python tests/smoke_tools.py     # 60 Werkzeuge ohne GUI testen
.venv/bin/python tests/smoke_models.py    # KI-Werkzeuge testen (lädt Modelle)
```

Ein neues Werkzeug ist eine Python-Funktion mit Formular-Schema – die Oberfläche entsteht automatisch:

```python
@tool("mein-tool", "Mein Werkzeug", "files", "Was es tut.", "sparkles",
      [F("files", "files", "Dateien", filter="any"),
       F("mode", "choice", "Modus", "a", options=[["a", "A"], ["b", "B"]])])
def mein_tool(ctx, files, mode):
    for f in files:
        ctx.log(f)
        out = ctx.out("ergebnis.txt")     # landet im datierten Ausgabeordner
        out.write_text("…")
        ctx.progress(1.0)
```

Struktur: `toolbox/registry.py` (Schema), `toolbox/context.py` (Ausgabe, FFmpeg-Fortschritt, Abbruch), `toolbox/tools/*.py` (die Werkzeuge), `qml/` (Oberfläche).

## Lizenz

MIT – siehe [LICENSE](LICENSE). Icons: [Lucide](https://lucide.dev) (ISC).
