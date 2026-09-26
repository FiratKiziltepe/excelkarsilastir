"""Görünümler (yan yana, rapor, PDF) için ortak satır filtreleme ve sütun genişliği."""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import CompareResult, RowResult, Section
from .normalize import match_key


@dataclass
class Filters:
    categories: set[str] = field(default_factory=set)  # boşsa tümü
    groups: set[str] = field(default_factory=set)  # boşsa tümü
    query: str = ""
    moved_only_at_new: bool = False  # raporda taşınan satırın eski yerindeki kopyasını gizle


def _row_ok(r: RowResult, f: Filters, q: str) -> bool:
    if f.moved_only_at_new and r.kind == "moved_from":
        return False
    if f.categories and not (r.categories & f.categories):
        return False
    if q:
        hay = " ".join(c.old + " " + c.new for c in r.cells) + " " + " ".join(r.summary)
        if q not in match_key(hay):
            return False
    return True


def filter_sections(res: CompareResult, f: Filters, report: bool) -> list[tuple[Section, list[RowResult]]]:
    q = match_key(f.query) if f.query else ""
    out = []
    for sec in res.sections:
        if f.groups and sec.group not in f.groups:
            continue
        rows = sec.report_rows if report else sec.rows
        kept = [r for r in rows if _row_ok(r, f, q)]
        if kept:
            out.append((sec, kept))
    return out


def column_weights(res: CompareResult) -> list[float]:
    """Karşılaştırılan sütunların ortalama metin uzunluğuna göre göreli genişlik."""
    n = len(res.pairs)
    totals, counts = [0.0] * n, [0] * n
    for sec in res.sections:
        for r in sec.rows[:400]:
            for k, c in enumerate(r.cells):
                totals[k] += len(c.new or c.old)
                counts[k] += 1
    avg = [t / c if c else 10 for t, c in zip(totals, counts)]
    # Kısa sütunlar okunabilir kalsın, uzunlar orantılı ama sınırlı büyüsün
    return [min(max(a, 8) ** 0.6, 30) for a in avg]
