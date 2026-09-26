"""Örnek dosyalarla uçtan uca beklenen sonuçlar."""
import os
import time

import pytest

from excel_diff import Settings, auto_map, compare_tables, guess_roles, read_table
from excel_diff.filtering import Filters
from excel_diff.model import CAT_ADDED, CAT_DELETED, CAT_FORMAT, CAT_MOVED, CAT_TEXT, Table
from excel_diff.render_html import report_html, side_by_side_html
from excel_diff.render_pdf import report_pdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = os.path.join(ROOT, "eskiprogram.xlsx")
NEW = os.path.join(ROOT, "Guncelprogram.xlsx")
pytestmark = pytest.mark.skipif(not (os.path.exists(OLD) and os.path.exists(NEW)), reason="örnek dosyalar yok")


def run(show_format=False):
    o = read_table(open(OLD, "rb").read(), "eski")
    n = read_table(open(NEW, "rb").read(), "yeni")
    pairs = auto_map(o, n)
    roles = guess_roles(pairs, o, n)
    cmp_idx = [i for i in range(len(pairs)) if i != roles["order"]]
    return compare_tables(o, n, Settings(pairs, cmp_idx, show_format=show_format, **roles)), pairs, roles


def key_text(r):
    c = next(c for c in r.cells if "BÖLÜM" in c.col)
    return c.new or c.old


def section(res, group, status="matched"):
    return next(s for s in res.sections if s.group == group and s.status == status)


def test_columns_mapped_despite_header_rename():
    _, pairs, roles = run()
    assert any(p.old == "KAZANIM/ÖĞRENME ÇIKTISI/BÖLÜM" and p.new == "BÖLÜM" for p in pairs)
    assert pairs[roles["group"]].new == "DERS ADI"
    assert pairs[roles["order"]].new == "SIRA NO"
    assert pairs[roles["unit"]].new == "ÜNİTE/TEMA/ÖĞRENME ALANI"


def test_old_non_tymm_program_is_fully_deleted():
    res, _, _ = run()
    dead = section(res, "Fen Bilimleri 3", "deleted_block")
    assert len(dead.rows) == 17
    assert all(r.kind == "deleted" for r in dead.rows)
    assert key_text(dead.rows[0]).startswith("F.3.1.1.1.")
    tymm = section(res, "Fen Bilimleri 3")
    assert len(tymm.rows) == 20 and all(r.kind == "matched" for r in tymm.rows)
    changed = {key_text(r).split()[0] for r in tymm.rows if CAT_TEXT in r.categories}
    assert {"FB.3.1.2.", "FB.3.3.2.", "FB.3.6.1.", "FB.3.6.2.", "FB.3.7.1."} <= changed


def test_biology_moves_and_deletions():
    res, _, _ = run()
    bio = section(res, "Biyoloji 9")
    deleted = [key_text(r) for r in bio.rows if r.kind == "deleted"]
    assert "Ön Değerlendirme" in deleted
    moved = {key_text(r).split(".", 4)[-1].strip()[:20]: r for r in bio.rows if r.moved == "unit"}
    assert any("İnorganik" in k for k in moved)
    assert any("Canlıları sınıflandı" in k for k in moved)
    assert len(moved) == 7
    # Taşınan satırlar raporda iki kez görünür (eski yer + yeni yer)
    assert sum(1 for r in bio.report_rows if r.kind == "moved_from") == 7


def test_hayat_bilgisi_added_row_and_case_change():
    res, _, _ = run()
    hb = section(res, "Hayat Bilgisi 1")
    added = [key_text(r) for r in hb.rows if r.kind == "added"]
    assert added == ["Belirli gün ve haftalar bölümü"]
    flag = next(r for r in hb.rows if "HB.1.4.2." in key_text(r))
    assert CAT_TEXT in flag.categories
    assert not any(CAT_MOVED in r.categories for r in hb.rows)  # ders sırası taşıma sayılmaz


def test_format_mode_toggle():
    res_ignore, _, _ = run(False)
    res_show, _, _ = run(True)
    assert res_ignore.stats[CAT_FORMAT] == 0
    assert res_show.stats[CAT_FORMAT] > 10
    assert res_ignore.stats[CAT_DELETED] == 20 and res_ignore.stats[CAT_ADDED] == 1


def test_renderers_produce_output():
    res, _, _ = run(True)
    html, total = side_by_side_html(res, Filters({CAT_MOVED}))
    assert total == 7 and "mvto" in html
    rep = report_html(res, Filters())
    assert "@page{size:A4 landscape" in rep and "tamamı silindi" in rep
    pdf = report_pdf(res, Filters())
    assert pdf.startswith(b"%PDF")


def _synthetic(n_groups=50, per_group=100, seed=1):
    import random
    rnd = random.Random(seed)
    words = "öğrenci video etkileşimli içerik animasyon hazırlanır kavram deney model basınç enerji hücre".split()
    cols = ["SIRA NO", "DERS ADI", "ÜNİTE", "KAZANIM", "TÜR", "AÇIKLAMA"]
    old_rows, new_rows = [], []
    for g in range(n_groups):
        for i in range(per_group):
            row = [str(i + 1), f"Ders {g}", f"{i // 10 + 1}. ÜNİTE", f"K.{g}.{i}. " + " ".join(rnd.choices(words, k=8)),
                   "Video", " ".join(rnd.choices(words, k=40))]
            old_rows.append(row)
            new = list(row)
            if rnd.random() < 0.2:
                new[5] = new[5].replace("video", "Video", 1) + " ek"
            if rnd.random() > 0.03:
                new_rows.append(new)
    return (Table("o", "", cols, old_rows, list(range(2, len(old_rows) + 2))),
            Table("n", "", cols, new_rows, list(range(2, len(new_rows) + 2))))


def test_performance_5000_rows():
    o, n = _synthetic()
    pairs = auto_map(o, n)
    roles = guess_roles(pairs, o, n)
    t = time.time()
    res = compare_tables(o, n, Settings(pairs, [1, 2, 3, 4, 5], **roles))
    assert time.time() - t < 15
    assert res.stats[CAT_DELETED] == len(o.rows) - len(n.rows)
