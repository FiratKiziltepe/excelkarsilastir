"""Blok içi satır eşleme ve taşıma tespiti."""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter

import numpy as np
from rapidfuzz import fuzz, process
from scipy.optimize import linear_sum_assignment

from .model import Table
from .normalize import match_key, strip_code

KEY_WEIGHT = 0.6
UNIT_NAME_WEIGHT = 0.5


def _col_texts(t: Table, rows: list[int], col: str | None, strip: bool = False) -> list[str]:
    if col not in t.columns:
        return ["" for _ in rows]
    c = t.columns.index(col)
    if strip:
        return [match_key(strip_code(t.rows[r][c])) for r in rows]
    return [match_key(t.rows[r][c]) for r in rows]


def _sim(a: list[str], b: list[str], scorer) -> np.ndarray:
    m = process.cdist(a, b, scorer=scorer, workers=-1, dtype=np.float32)
    # İki tarafı da boş hücreler özdeştir
    ea = np.array([not x for x in a])[:, None]
    eb = np.array([not x for x in b])[None, :]
    m[ea & eb] = 100
    return m


def similarity_matrix(old: Table, new: Table, orows: list[int], nrows: list[int],
                      key_pair: tuple[str | None, str | None] | None,
                      other_pairs: list[tuple[str | None, str | None]]) -> np.ndarray:
    parts, weights = [], []
    if key_pair and key_pair[0] and key_pair[1]:
        parts.append(_sim(_col_texts(old, orows, key_pair[0], True),
                          _col_texts(new, nrows, key_pair[1], True), fuzz.ratio))
        weights.append(KEY_WEIGHT)
    others = [p for p in other_pairs if p[0] and p[1]]
    if others:
        acc = sum(_sim(_col_texts(old, orows, o), _col_texts(new, nrows, n), fuzz.token_sort_ratio)
                  for o, n in others) / len(others)
        parts.append(acc)
        weights.append(1 - KEY_WEIGHT if parts[:-1] else 1.0)
    if not parts:
        return np.zeros((len(orows), len(nrows)))
    total = sum(weights)
    return sum(w * p for w, p in zip(weights, parts)) / total


def match_rows(sim: np.ndarray, threshold: float) -> list[tuple[int, int, float]]:
    """Optimal atama; eşik altındakiler eşleşmemiş sayılır. Dönen indeksler blok içidir."""
    if sim.size == 0:
        return []
    ri, cj = linear_sum_assignment(-sim)
    return sorted(((int(i), int(j), float(sim[i, j])) for i, j in zip(ri, cj) if sim[i, j] >= threshold),
                  key=lambda x: x[1])


def map_units(old_units: list[str], new_units: list[str], matches: list[tuple[int, int, float]]) -> dict[str, str]:
    """Eski ünite anahtarı -> yeni ünite anahtarı.

    Skor = ad benzerliği (%50) + eski ünitenin eşleşen satırlarının o yeni üniteye
    giden oranı (%50). Böylece "1. YAŞAM" -> "1. TEMA: YAŞAM" yeniden adlandırması
    taşıma sayılmaz ve ünite içeriğinin bir kısmı başka üniteye geçse de ad baskın olur.
    """
    ou = list(dict.fromkeys(u for u in old_units))
    nu = list(dict.fromkeys(u for u in new_units))
    if not ou or not nu:
        return {}
    flow = Counter((old_units[i], new_units[j]) for i, j, _ in matches)
    out_total = Counter(old_units[i] for i, _, _ in matches)
    name = process.cdist(ou, nu, scorer=fuzz.token_set_ratio)
    score = np.zeros((len(ou), len(nu)))
    for a, o in enumerate(ou):
        for b, n in enumerate(nu):
            overlap = flow[(o, n)] / out_total[o] * 100 if out_total[o] else 0
            score[a, b] = UNIT_NAME_WEIGHT * name[a, b] + (1 - UNIT_NAME_WEIGHT) * overlap
    ri, cj = linear_sum_assignment(-score)
    return {ou[a]: nu[b] for a, b in zip(ri, cj) if score[a, b] >= 40}


def _lis_members(seq: list[int]) -> set[int]:
    """En uzun artan alt dizinin elemanlarının konumları."""
    tails, tails_idx, prev = [], [], [-1] * len(seq)
    for i, v in enumerate(seq):
        k = bisect_left(tails, v)
        if k == len(tails):
            tails.append(v)
            tails_idx.append(i)
        else:
            tails[k] = v
            tails_idx[k] = i
        prev[i] = tails_idx[k - 1] if k else -1
    out, i = set(), tails_idx[-1] if tails_idx else -1
    while i != -1:
        out.add(i)
        i = prev[i]
    return out


def detect_moves(matches: list[tuple[int, int, float]], old_units: list[str] | None,
                 new_units: list[str] | None) -> dict[tuple[int, int], str]:
    """(eski, yeni) -> "unit" | "order". Taşınmayanlar sözlükte yer almaz."""
    moves: dict[tuple[int, int], str] = {}
    staying = list(matches)
    if old_units is not None and new_units is not None:
        umap = map_units(old_units, new_units, matches)
        staying = []
        for i, j, s in matches:
            if umap.get(old_units[i]) != new_units[j]:
                moves[(i, j)] = "unit"
            else:
                staying.append((i, j, s))
        groups: dict[str, list[tuple[int, int, float]]] = {}
        for m in staying:
            groups.setdefault(new_units[m[1]], []).append(m)
        buckets = list(groups.values())
    else:
        buckets = [staying]
    for bucket in buckets:
        bucket = sorted(bucket, key=lambda x: x[1])
        keep = _lis_members([i for i, _, _ in bucket])
        for pos, (i, j, _) in enumerate(bucket):
            if pos not in keep:
                moves[(i, j)] = "order"
    return moves
