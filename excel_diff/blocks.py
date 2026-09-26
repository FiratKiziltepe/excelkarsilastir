"""Dersleri gruplara, grupları program bloklarına ayırma ve blok eşleme.

Aynı ders adı dosyada birden fazla program olarak geçebilir (ör. eski dosyada
TYMM dışı ve TYMM "Fen Bilimleri 3"). Bir blok, sıra sütunu 1'e (veya önceki
değerden küçük bir sayıya) döndüğünde ya da ders adı değiştiğinde başlar.
"""
from __future__ import annotations

import numpy as np
from rapidfuzz import fuzz, process
from scipy.optimize import linear_sum_assignment

from .model import Block, Table
from .normalize import match_key, norm_ws, strip_code

BLOCK_MIN_SCORE = 0.25  # eşleşen satır oranı
GROUP_FUZZY_MIN = 90


def _as_int(v: str) -> int | None:
    v = norm_ws(v)
    return int(v) if v.isdigit() else None


def split_blocks(t: Table, side: str, group_col: str | None, order_col: str | None) -> list[Block]:
    gi = t.columns.index(group_col) if group_col in t.columns else None
    oi = t.columns.index(order_col) if order_col in t.columns else None
    blocks: list[Block] = []
    cur: Block | None = None
    prev_order: int | None = None
    for idx, row in enumerate(t.rows):
        g = norm_ws(row[gi]) if gi is not None else "Tümü"
        gk = match_key(g)
        order = _as_int(row[oi]) if oi is not None else None
        new_block = cur is None or gk != cur.group_key
        if not new_block and order is not None and prev_order is not None and order <= prev_order and order <= 1:
            new_block = True
        if new_block:
            cur = Block(side, g or "(ders adı yok)", gk, len(blocks), [])
            blocks.append(cur)
        cur.rows.append(idx)
        if order is not None:
            prev_order = order
    return blocks


def key_texts(t: Table, rows: list[int], key_col: str | None) -> list[str]:
    if key_col not in t.columns:
        return ["" for _ in rows]
    c = t.columns.index(key_col)
    return [match_key(strip_code(t.rows[r][c])) for r in rows]


def block_similarity(old: Table, new: Table, ob: Block, nb: Block, key_old: str | None,
                     key_new: str | None, threshold: float) -> float:
    a = key_texts(old, ob.rows, key_old)
    b = key_texts(new, nb.rows, key_new)
    if not a or not b:
        return 0.0
    m = process.cdist(a, b, scorer=fuzz.ratio, workers=-1)
    ri, cj = linear_sum_assignment(-m)
    good = sum(1 for i, j in zip(ri, cj) if m[i, j] >= threshold)
    return good / max(len(a), len(b))


def match_groups(old_blocks: list[Block], new_blocks: list[Block]) -> dict[str, str]:
    """Eski ders anahtarı -> yeni ders anahtarı (tam eşleşme, sonra bulanık)."""
    old_keys = list(dict.fromkeys(b.group_key for b in old_blocks))
    new_keys = list(dict.fromkeys(b.group_key for b in new_blocks))
    mapping = {k: k for k in old_keys if k in new_keys}
    rest_old = [k for k in old_keys if k not in mapping]
    rest_new = [k for k in new_keys if k not in mapping.values()]
    if rest_old and rest_new:
        m = process.cdist(rest_old, rest_new, scorer=fuzz.ratio)
        ri, cj = linear_sum_assignment(-m)
        for i, j in zip(ri, cj):
            if m[i, j] >= GROUP_FUZZY_MIN:
                mapping[rest_old[i]] = rest_new[j]
    return mapping


def match_blocks(old: Table, new: Table, old_blocks: list[Block], new_blocks: list[Block],
                 key_old: str | None, key_new: str | None, threshold: float) -> list[tuple[Block | None, Block | None]]:
    """Blok çiftleri: (eski, yeni). Eşi olmayanlar (eski, None) / (None, yeni)."""
    gmap = match_groups(old_blocks, new_blocks)
    pairs: list[tuple[Block | None, Block | None]] = []
    matched_old: set[int] = set()
    matched_new: set[int] = set()
    for ok, nk in gmap.items():
        obs = [b for b in old_blocks if b.group_key == ok]
        nbs = [b for b in new_blocks if b.group_key == nk]
        if len(obs) == 1 and len(nbs) == 1:
            pairs.append((obs[0], nbs[0]))
            matched_old.add(obs[0].index)
            matched_new.add(nbs[0].index)
            continue
        sim = np.array([[block_similarity(old, new, ob, nb, key_old, key_new, threshold) for nb in nbs] for ob in obs])
        ri, cj = linear_sum_assignment(-sim)
        for i, j in zip(ri, cj):
            if sim[i, j] >= BLOCK_MIN_SCORE:
                pairs.append((obs[i], nbs[j]))
                matched_old.add(obs[i].index)
                matched_new.add(nbs[j].index)
    pairs += [(b, None) for b in old_blocks if b.index not in matched_old]
    pairs += [(None, b) for b in new_blocks if b.index not in matched_new]
    return pairs
