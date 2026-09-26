"""Hücre düzeyinde kelime bazlı fark hesaplama."""
from __future__ import annotations

from difflib import SequenceMatcher

from .model import CellDiff
from .normalize import norm_ws, tokenize

# Segment işlemleri
EQ, DEL, INS, FMT = "eq", "del", "ins", "fmt"


def _clean(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _ws_marker(old_ws: str, new_ws: str) -> str:
    """İki boşluk parçası farklıysa gösterilecek küçük işaret."""
    o, n = old_ws.count("\n"), new_ws.count("\n")
    if n > o:
        return "↵+"
    if n < o:
        return "↵−"
    return "·"


def _join(tokens: list[tuple[str, str]]) -> str:
    return "".join(w + ws for w, ws in tokens)


def _short(text: str, limit: int = 60) -> str:
    text = norm_ws(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def diff_cell(col: str, old: str, new: str, show_format: bool) -> CellDiff:
    """İki hücre değerini karşılaştırır.

    status: 'same' | 'format' (yalnızca boşluk/satır sonu) | 'text'
    merged: Word "değişiklikleri izle" görünümü için tek segment listesi
    old_view / new_view: yan yana görünüm için
    """
    old, new = _clean(old), _clean(new)
    if old == new:
        seg = [(EQ, new)] if new else []
        return CellDiff(col, old, new, "same", seg, seg, seg, "")

    old_lead, old_tok = tokenize(old)
    new_lead, new_tok = tokenize(new)
    old_words = [w for w, _ in old_tok]
    new_words = [w for w, _ in new_tok]

    merged: list[tuple[str, str]] = []
    old_view: list[tuple[str, str]] = []
    new_view: list[tuple[str, str]] = []
    changes: list[str] = []
    fmt_count = 0

    if show_format and old_lead != new_lead:
        mark = _ws_marker(old_lead, new_lead)
        merged.append((FMT, mark))
        old_view.append((FMT, mark))
        new_view.append((FMT, mark))
        fmt_count += 1

    sm = SequenceMatcher(None, old_words, new_words, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for (ow, ows), (nw, nws) in zip(old_tok[i1:i2], new_tok[j1:j2]):
                merged.append((EQ, nw))
                old_view.append((EQ, ow))
                new_view.append((EQ, nw))
                if show_format and ows != nws:
                    mark = _ws_marker(ows, nws)
                    merged.append((FMT, mark))
                    old_view.append((FMT, mark))
                    new_view.append((FMT, mark))
                    fmt_count += 1
                merged.append((EQ, nws))
                old_view.append((EQ, ows))
                new_view.append((EQ, nws))
            continue
        old_part = _join(old_tok[i1:i2])
        new_part = _join(new_tok[j1:j2])
        if old_part:
            merged.append((DEL, old_part.rstrip()))
            merged.append((EQ, " "))
            old_view.append((DEL, old_part.rstrip()))
            old_view.append((EQ, old_part[len(old_part.rstrip()):] or " "))
        if new_part:
            merged.append((INS, new_part.rstrip()))
            merged.append((EQ, new_part[len(new_part.rstrip()):] or " "))
            new_view.append((INS, new_part.rstrip()))
            new_view.append((EQ, new_part[len(new_part.rstrip()):] or " "))
        if tag == "replace":
            changes.append(f"«{_short(old_part, 40)}» → «{_short(new_part, 40)}»")
        elif tag == "delete":
            changes.append(f"−«{_short(old_part, 40)}»")
        else:
            changes.append(f"+«{_short(new_part, 40)}»")

    if changes:
        status = "text"
        shown = changes[:3]
        detail = "; ".join(shown) + (f" (+{len(changes) - 3} değişiklik)" if len(changes) > 3 else "")
        if not old.strip():
            detail = "boş hücre dolduruldu"
        elif not new.strip():
            detail = "hücre içeriği silindi"
    else:
        # Kelimeler aynı; fark yalnızca boşluk/satır sonu
        status = "format" if show_format else "same"
        detail = f"biçim (boşluk/satır sonu, {fmt_count} yer)" if show_format else ""
        if not show_format:
            merged = [(EQ, new)]
            old_view = [(EQ, old)]
            new_view = [(EQ, new)]

    if status == "text" and fmt_count:
        detail += f" + biçim ({fmt_count} yer)"
    return CellDiff(col, old, new, status, merged, old_view, new_view, detail, fmt_count)


def whole_cell(col: str, text: str, op: str) -> CellDiff:
    """Eklenen/silinen satırlar için hücrenin tamamı tek segment."""
    text = _clean(text)
    seg = [(op, text)] if text else []
    status = "added" if op == INS else "deleted"
    if op == INS:
        return CellDiff(col, "", text, status, seg, [], seg, "")
    return CellDiff(col, text, "", status, seg, seg, [], "")
