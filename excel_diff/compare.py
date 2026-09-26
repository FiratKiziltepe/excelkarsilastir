"""Karşılaştırmanın ana akışı: bloklar -> satır eşleme -> taşıma -> hücre farkları -> bölümler."""
from __future__ import annotations

from dataclasses import dataclass

from .blocks import match_blocks, split_blocks
from .diff import DEL, INS, diff_cell, whole_cell
from .matcher import detect_moves, match_rows, similarity_matrix
from .model import (CAT_ADDED, CAT_DELETED, CAT_FORMAT, CAT_MOVED, CAT_SAME, CAT_TEXT, Block,
                    ColumnPair, CompareResult, RowResult, Section, Table)
from .normalize import extract_code, match_key, norm_ws


@dataclass
class Settings:
    pairs: list[ColumnPair]
    compare: list[int]  # karşılaştırılacak çift indeksleri
    group: int | None = None
    order: int | None = None
    unit: int | None = None
    key: int | None = None
    show_format: bool = False
    threshold: float = 55.0


def _val(t: Table, row: int | None, col: str | None) -> str:
    if row is None or not col or col not in t.columns:
        return ""
    return t.rows[row][t.columns.index(col)]


def _unit_label(t: Table, row: int, col: str | None) -> str:
    return norm_ws(_val(t, row, col)) or "—"


class _Ctx:
    def __init__(self, old: Table, new: Table, s: Settings):
        self.old, self.new, self.s = old, new, s
        self.cmp_pairs = [s.pairs[i] for i in s.compare]
        self.order = s.pairs[s.order] if s.order is not None else None
        self.unit = s.pairs[s.unit] if s.unit is not None else None
        self.key = s.pairs[s.key] if s.key is not None else None
        self.group = s.pairs[s.group] if s.group is not None else None

    # --- satır üreticiler -------------------------------------------------
    def _base(self, kind: str, group: str, oi: int | None, ni: int | None) -> RowResult:
        o, n = self.old, self.new
        r = RowResult(kind=kind, group=group, old_idx=oi, new_idx=ni)
        if oi is not None:
            r.old_excel_row = o.excel_rows[oi]
            r.old_order = norm_ws(_val(o, oi, self.order.old if self.order else None))
            r.old_unit = _unit_label(o, oi, self.unit.old if self.unit else None)
        if ni is not None:
            r.new_excel_row = n.excel_rows[ni]
            r.new_order = norm_ws(_val(n, ni, self.order.new if self.order else None))
            r.new_unit = _unit_label(n, ni, self.unit.new if self.unit else None)
        return r

    def deleted(self, group: str, oi: int, block_status: str = "") -> RowResult:
        r = self._base("deleted", group, oi, None)
        r.cells = [whole_cell(p.label, _val(self.old, oi, p.old), DEL) for p in self.cmp_pairs]
        r.categories = {CAT_DELETED}
        r.summary = ["Program kaldırıldı: satır silindi" if block_status else "Satır silindi"]
        r.block_status = block_status
        return r

    def added(self, group: str, ni: int, block_status: str = "") -> RowResult:
        r = self._base("added", group, None, ni)
        r.cells = [whole_cell(p.label, _val(self.new, ni, p.new), INS) for p in self.cmp_pairs]
        r.categories = {CAT_ADDED}
        r.summary = ["Yeni program: satır eklendi" if block_status else "Satır eklendi"]
        r.block_status = block_status
        return r

    def matched(self, group: str, oi: int, ni: int, score: float, moved: str | None) -> RowResult:
        r = self._base("matched", group, oi, ni)
        r.score, r.moved = score, moved
        for p in self.cmp_pairs:
            c = diff_cell(p.label, _val(self.old, oi, p.old), _val(self.new, ni, p.new), self.s.show_format)
            r.cells.append(c)
            if c.status == "text":
                r.categories.add(CAT_TEXT)
                if c.fmt:
                    r.categories.add(CAT_FORMAT)
                r.summary.append(f"{p.label}: {c.detail}")
            elif c.status == "format":
                r.categories.add(CAT_FORMAT)
                r.summary.append(f"{p.label}: {c.detail}")
        if moved:
            r.categories.add(CAT_MOVED)
            r.summary.insert(0, self._move_text(r, to_here=True))
        if not r.categories:
            r.categories = {CAT_SAME}
        return r

    def moved_from(self, src: RowResult) -> RowResult:
        """Taşınan satırın eski yerinde gösterilen hayalet satır (Word 'buradan taşındı')."""
        r = self._base("moved_from", src.group, src.old_idx, src.new_idx)
        r.moved = src.moved
        r.cells = [whole_cell(p.label, _val(self.old, src.old_idx, p.old), DEL) for p in self.cmp_pairs]
        r.categories = {CAT_MOVED}
        r.summary = [self._move_text(r, to_here=False)]
        return r

    @staticmethod
    def _move_text(r: RowResult, to_here: bool) -> str:
        if r.moved == "unit":
            if to_here:
                return f"Buraya taşındı ← {r.old_unit} (eski sıra {r.old_order or '?'})"
            return f"Buradan taşındı → {r.new_unit} (yeni sıra {r.new_order or '?'})"
        if to_here:
            return f"Ünite içinde yeri değişti ← eski sıra {r.old_order or '?'}"
        return f"Buradan taşındı → aynı ünitede yeni sıra {r.new_order or '?'}"

    # --- bölümler ---------------------------------------------------------
    def block_code_hint(self, t: Table, b: Block, col: str | None) -> str:
        codes = [extract_code(_val(t, i, col)) for i in b.rows[:3]]
        code = next((c for c in codes if c), "")
        return f"{code} …" if code else ""

    def section_for_pair(self, ob: Block | None, nb: Block | None) -> Section:
        if ob and nb:
            return self.matched_section(ob, nb)
        if ob:
            hint = self.block_code_hint(self.old, ob, self.key.old if self.key else None)
            title = (f"{ob.group} · eski sürümdeki program" + (f" ({hint})" if hint else "")
                     + f" · {len(ob.rows)} satır · yeni sürümde yok — tamamı silindi")
            sec = Section(ob.group, "deleted_block", title, old_block=ob)
            sec.rows = [self.deleted(ob.group, i, "deleted_block") for i in ob.rows]
            sec.report_rows = list(sec.rows)
            return sec
        hint = self.block_code_hint(self.new, nb, self.key.new if self.key else None)
        title = (f"{nb.group} · yeni sürümde eklenen program" + (f" ({hint})" if hint else "")
                 + f" · {len(nb.rows)} satır")
        sec = Section(nb.group, "added_block", title, new_block=nb)
        sec.rows = [self.added(nb.group, i, "added_block") for i in nb.rows]
        sec.report_rows = list(sec.rows)
        return sec

    def matched_section(self, ob: Block, nb: Block) -> Section:
        o, n, s = self.old, self.new, self.s
        others = [(p.old, p.new) for p in self.cmp_pairs
                  if p is not self.key and p is not self.order and p is not self.group]
        key_pair = (self.key.old, self.key.new) if self.key else None
        sim = similarity_matrix(o, n, ob.rows, nb.rows, key_pair, others)
        matches = match_rows(sim, s.threshold)

        if self.unit and self.unit.old and self.unit.new:
            ou = [match_key(_val(o, i, self.unit.old)) for i in ob.rows]
            nu = [match_key(_val(n, j, self.unit.new)) for j in nb.rows]
            moves = detect_moves(matches, ou, nu)
        else:
            moves = detect_moves(matches, None, None)

        group = nb.group
        by_new: dict[int, RowResult] = {}
        old_to_new: dict[int, int] = {}
        for i, j, sc in matches:
            by_new[j] = self.matched(group, ob.rows[i], nb.rows[j], sc, moves.get((i, j)))
            old_to_new[i] = j

        # Eski satırları, eski sırada kendilerinden önceki son "sabit" (taşınmamış)
        # eşleşmiş satırın yeni konumuna iliştir.
        side_after: dict[int, list[RowResult]] = {}
        report_after: dict[int, list[RowResult]] = {}
        anchor = -1
        for i in range(len(ob.rows)):
            if i in old_to_new:
                j = old_to_new[i]
                row = by_new[j]
                if row.moved:
                    report_after.setdefault(anchor, []).append(self.moved_from(row))
                else:
                    anchor = j
                continue
            d = self.deleted(group, ob.rows[i])
            side_after.setdefault(anchor, []).append(d)
            report_after.setdefault(anchor, []).append(d)

        sec = Section(group, "matched", group, old_block=ob, new_block=nb)
        sec.rows.extend(side_after.get(-1, []))
        sec.report_rows.extend(report_after.get(-1, []))
        for j in range(len(nb.rows)):
            row = by_new.get(j) or self.added(group, nb.rows[j])
            sec.rows.append(row)
            sec.report_rows.append(row)
            sec.rows.extend(side_after.get(j, []))
            sec.report_rows.extend(report_after.get(j, []))
        return sec


def _order_sections(pairs: list[tuple[Block | None, Block | None]], secs: list[Section]) -> list[Section]:
    """Yeni dosyadaki blok sırası esas; yalnız eskide olan bloklar aynı dersin yanına
    (yoksa eski dosyada kendisinden önce gelen bloğun arkasına) yerleştirilir."""
    placed = [(p, s) for p, s in zip(pairs, secs) if p[1] is not None]
    placed.sort(key=lambda x: x[0][1].index)
    ordered = [s for _, s in placed]
    old_pos = {id(p[0]): s for p, s in placed if p[0] is not None}  # eski blok -> bölüm
    orphans = sorted([(p, s) for p, s in zip(pairs, secs) if p[1] is None], key=lambda x: x[0][0].index)
    all_old = sorted([p[0] for p in pairs if p[0] is not None], key=lambda b: b.index)
    for (ob, _), sec in orphans:
        same = [x for x in ordered if x.group and match_key(x.group) == ob.group_key and x.status == "matched"]
        if same:
            target = same[0]
            later = target.old_block is not None and target.old_block.index > ob.index
            pos = ordered.index(target) + (0 if later else 1)
            ordered.insert(pos, sec)
        else:
            prev = [b for b in all_old if b.index < ob.index and id(b) in old_pos]
            if prev:
                pos = ordered.index(old_pos[id(prev[-1])]) + 1
            else:
                pos = 0
            ordered.insert(pos, sec)
        old_pos[id(ob)] = sec
    return ordered


def compare_tables(old: Table, new: Table, s: Settings) -> CompareResult:
    ctx = _Ctx(old, new, s)
    g = ctx.group
    o_ord = ctx.order
    old_blocks = split_blocks(old, "old", g.old if g else None, o_ord.old if o_ord else None)
    new_blocks = split_blocks(new, "new", g.new if g else None, o_ord.new if o_ord else None)
    key = ctx.key
    pairs = match_blocks(old, new, old_blocks, new_blocks, key.old if key else None,
                         key.new if key else None, s.threshold)
    secs = [ctx.section_for_pair(ob, nb) for ob, nb in pairs]
    sections = _order_sections(pairs, secs)

    # Aynı dersin birden fazla programı varsa eşleşen bölüm başlığına kod ipucu ekle
    counts: dict[str, int] = {}
    for b in old_blocks + new_blocks:
        counts[b.group_key] = counts.get(b.group_key, 0) + 1
    for sec in sections:
        if sec.status == "matched" and counts.get(sec.new_block.group_key, 0) > 2:
            hint = ctx.block_code_hint(new, sec.new_block, key.new if key else None)
            if hint:
                sec.title = f"{sec.group} · güncel program ({hint})"

    stats = {c: 0 for c in (CAT_TEXT, CAT_FORMAT, CAT_MOVED, CAT_DELETED, CAT_ADDED, CAT_SAME)}
    for sec in sections:
        for r in sec.rows:
            for c in r.categories:
                stats[c] += 1
    stats["Eski satır"] = len(old.rows)
    stats["Yeni satır"] = len(new.rows)
    return CompareResult(old.name, new.name, ctx.cmp_pairs, ctx.order, sections, s.show_format, stats)
