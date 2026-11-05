"""Gemeinsame Texterkennung (RapidOCR, ONNX – komplett lokal)."""
from __future__ import annotations

_engine = None


def engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def ocr_boxes(ctx, pil_img):
    """[(text, (x0, y0, x1, y1)), …]"""
    import numpy as np
    ctx.log("Erkenne Text …")
    res, _ = engine()(np.array(pil_img.convert("RGB")))
    out = []
    for box, text, _score in res or []:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append((text, (min(xs), min(ys), max(xs), max(ys))))
    return out


def ocr_text(ctx, pil_img) -> str:
    """Text in Leserichtung, Zeilen gruppiert."""
    items = ocr_boxes(ctx, pil_img)
    items.sort(key=lambda it: (round((it[1][1] + it[1][3]) / 2 / 12), it[1][0]))
    lines, cur, cy = [], [], None
    for text, (x0, y0, x1, y1) in sorted(items, key=lambda it: ((it[1][1] + it[1][3]) / 2, it[1][0])):
        mid = (y0 + y1) / 2
        if cy is not None and abs(mid - cy) > (y1 - y0) * 0.6:
            lines.append(" ".join(t for t, _ in sorted(cur, key=lambda c: c[1])))
            cur = []
        cur.append((text, x0))
        cy = mid
    if cur:
        lines.append(" ".join(t for t, _ in sorted(cur, key=lambda c: c[1])))
    return "\n".join(lines)
