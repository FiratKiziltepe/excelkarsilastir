"""Sütun eşleme ve sütun rolü tahmini."""
from __future__ import annotations

import numpy as np
from rapidfuzz import fuzz, process
from scipy.optimize import linear_sum_assignment

from .model import ColumnPair, Table
from .normalize import match_key, norm_ws

MIN_COLUMN_SCORE = 45


def _col_values(t: Table, c: int, limit: int = 80) -> list[str]:
    vals, seen = [], set()
    for r in t.rows:
        v = match_key(r[c])
        if v and v not in seen:
            seen.add(v)
            vals.append(v[:200])
            if len(vals) >= limit:
                break
    return vals


def _content_score(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    m = process.cdist(a, b, scorer=fuzz.ratio, workers=-1)
    return float(np.mean(m.max(axis=1)))


def auto_map(old: Table, new: Table) -> list[ColumnPair]:
    """Başlık benzerliği (%60) + içerik benzerliği (%40) ile eski↔yeni sütunları eşler."""
    no, nn = len(old.columns), len(new.columns)
    if not no or not nn:
        return [ColumnPair(None, c) for c in new.columns] + [ColumnPair(c, None) for c in old.columns]
    old_vals = [_col_values(old, i) for i in range(no)]
    new_vals = [_col_values(new, j) for j in range(nn)]
    score = np.zeros((no, nn))
    for i, oc in enumerate(old.columns):
        for j, nc in enumerate(new.columns):
            h = fuzz.token_set_ratio(match_key(oc), match_key(nc))
            c = _content_score(old_vals[i], new_vals[j])
            score[i, j] = 0.6 * h + 0.4 * c
    ri, cj = linear_sum_assignment(-score)
    old_for_new: dict[int, int] = {}
    for i, j in zip(ri, cj):
        if score[i, j] >= MIN_COLUMN_SCORE:
            old_for_new[j] = i
    used_old = set(old_for_new.values())
    pairs = [ColumnPair(old.columns[old_for_new[j]] if j in old_for_new else None, nc)
             for j, nc in enumerate(new.columns)]
    pairs += [ColumnPair(oc, None) for i, oc in enumerate(old.columns) if i not in used_old]
    return pairs


def _is_numeric_col(t: Table, name: str | None) -> bool:
    if not name or name not in t.columns:
        return False
    c = t.columns.index(name)
    vals = [norm_ws(r[c]) for r in t.rows if norm_ws(r[c])]
    return bool(vals) and sum(v.isdigit() for v in vals) / len(vals) > 0.9


def _cardinality(t: Table, name: str | None) -> float:
    if not name or name not in t.columns or not t.rows:
        return 1.0
    c = t.columns.index(name)
    return len({match_key(r[c]) for r in t.rows}) / len(t.rows)


def guess_roles(pairs: list[ColumnPair], old: Table, new: Table) -> dict[str, int | None]:
    """order / group / unit / key rolleri için çift indeksi tahmini."""
    both = [i for i, p in enumerate(pairs) if p.old and p.new]

    def find(words: list[str], exclude: set[int]) -> int | None:
        for w in words:
            for i in both:
                if i in exclude:
                    continue
                name = match_key(f"{pairs[i].old} {pairs[i].new}")
                if w in name:
                    return i
        return None

    roles: dict[str, int | None] = {}
    used: set[int] = set()
    order = find(["sıra", "sira no", "no"], used)
    if order is None or not _is_numeric_col(new, pairs[order].new):
        order = next((i for i in both if _is_numeric_col(new, pairs[i].new)), None)
    roles["order"] = order
    if order is not None:
        used.add(order)

    roles["group"] = find(["ders", "kurs", "program adı"], used)
    if roles["group"] is None:
        cands = [i for i in both if i not in used and not _is_numeric_col(new, pairs[i].new)]
        cands.sort(key=lambda i: _cardinality(new, pairs[i].new))
        roles["group"] = cands[0] if cands else None
    if roles["group"] is not None:
        used.add(roles["group"])

    roles["unit"] = find(["ünite", "tema", "öğrenme alanı", "alan"], used)
    if roles["unit"] is not None:
        used.add(roles["unit"])

    roles["key"] = find(["kazanım", "çıktı", "bölüm", "konu", "başlık"], used)
    if roles["key"] is None:
        cands = [i for i in both if i not in used and not _is_numeric_col(new, pairs[i].new)]
        cands.sort(key=lambda i: -_cardinality(new, pairs[i].new))
        roles["key"] = cands[0] if cands else None
    return roles
