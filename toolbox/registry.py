"""Werkzeug-Registry: jedes Werkzeug ist eine Funktion plus ein Formular-Schema."""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field, asdict
from typing import Callable

CATEGORIES = [
    ("video", "Video", "video"),
    ("audio", "Audio", "audio-lines"),
    ("images", "Bilder", "image"),
    ("docs", "Dokumente", "file-text"),
    ("text", "Text & Sprache", "languages"),
    ("files", "Dateien", "folder"),
    ("system", "System", "laptop"),
    ("dev", "Entwickler", "code-xml"),
]

TOOLS: dict[str, "Tool"] = {}


@dataclass
class Field:
    key: str
    type: str  # file files folder text textarea choice number slider bool color
    label: str = ""
    default: object = None
    options: list = field(default_factory=list)  # choice: [[value,label],...]
    min: float = 0
    max: float = 100
    step: float = 1
    filter: str = ""  # Dateifilter, z.B. "video"
    placeholder: str = ""
    hint: str = ""
    showIf: str = ""  # "key=value"
    optional: bool = False  # Dateifeld darf leer bleiben


def F(key, type, label="", default=None, **kw) -> Field:
    return Field(key, type, label, default, **kw)


FILTERS = {
    "video": "Video (*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.flv *.wmv *.ts)",
    "audio": "Audio (*.mp3 *.wav *.flac *.ogg *.opus *.m4a *.aac *.wma)",
    "media": "Medien (*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.mp3 *.wav *.flac *.ogg *.opus *.m4a *.aac)",
    "image": "Bilder (*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.gif *.avif *.heic)",
    "pdf": "PDF (*.pdf)",
    "pdfimg": "PDF und Bilder (*.pdf *.png *.jpg *.jpeg *.webp)",
    "office": "Office (*.docx *.doc *.odt *.pptx *.ppt *.odp *.xlsx *.xls *.ods *.rtf)",
    "word": "Word (*.docx *.doc *.odt *.rtf)",
    "ppt": "PowerPoint (*.pptx *.ppt *.odp)",
    "excel": "Excel (*.xlsx *.xls *.ods *.csv)",
    "srt": "Untertitel (*.srt *.vtt)",
    "text": "Text (*.txt *.md *.pdf *.docx *.srt *.html)",
    "md": "Markdown (*.md *.markdown *.txt)",
    "any": "Alle Dateien (*)",
}


@dataclass
class Tool:
    id: str
    name: str
    cat: str
    desc: str
    icon: str
    fields: list[Field]
    fn: Callable
    live: bool = False  # bei Eingabe sofort ausführen (Entwickler-Werkzeuge)
    needs: list[str] = field(default_factory=list)  # externe Programme
    isnew: bool = False
    keywords: str = ""
    output: str = "files"  # files | text | both
    stoppable: bool = False  # „Beenden & speichern“-Knopf (Aufnahmen)

    def to_dict(self):
        d = asdict(self)
        d.pop("fn")
        d["missing"] = [n for n in self.needs if not shutil.which(n)]
        return d


def tool(id, name, cat, desc, icon, fields=(), live=False, needs=(), new=False,
         keywords="", output="files", stoppable=False):
    def deco(fn):
        TOOLS[id] = Tool(id, name, cat, desc, icon, list(fields), fn, live,
                         list(needs), new, keywords, output, stoppable)
        return fn
    return deco
