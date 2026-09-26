"""Excel sürüm karşılaştırma – Streamlit arayüzü.

Çalıştırma:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import replace
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _refresh_excel_diff() -> None:
    """Paket dosyaları değiştiyse bellekteki eski excel_diff modüllerini at.

    Streamlit Cloud yeni commit'i çekip app.py'yi yeniden çalıştırdığında daha önce
    içe aktarılmış alt modüller eski sürümde kalabiliyor (ör. yeni alanı olmayan
    Filters sınıfı -> TypeError). Dosya damgası değişince paket baştan yüklenir.
    """
    pkg = os.path.join(APP_DIR, "excel_diff")
    stamp = tuple(sorted((f, os.stat(os.path.join(pkg, f)).st_mtime_ns)
                         for f in os.listdir(pkg) if f.endswith(".py")))
    loaded = sys.modules.get("excel_diff")
    if loaded is not None and getattr(loaded, "_source_stamp", None) != stamp:
        for name in [m for m in sys.modules if m == "excel_diff" or m.startswith("excel_diff.")]:
            del sys.modules[name]
    import excel_diff
    excel_diff._source_stamp = stamp


_refresh_excel_diff()

from excel_diff import Settings, auto_map, compare_tables, guess_roles, read_table, sheet_names
from excel_diff.filtering import Filters, filter_sections
from excel_diff.model import (ALL_CATEGORIES, CAT_ADDED, CAT_DELETED, CAT_FORMAT, CAT_MOVED, CAT_SAME,
                              CAT_TEXT, ColumnPair)
from excel_diff.render_html import report_html, side_by_side_html
from excel_diff.render_pdf import report_pdf

SAMPLES = ("eskiprogram.xlsx", "Guncelprogram.xlsx")
NONE = "(yok)"

st.set_page_config(page_title="Excel Karşılaştırma", page_icon="📊", layout="wide")


# ---------------------------------------------------------------------------
# Önbellekli işlemler
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def cached_sheets(data: bytes) -> list[str]:
    return sheet_names(data)


@st.cache_data(show_spinner=False)
def cached_table(data: bytes, name: str, sheet: str, header_row: int | None):
    return read_table(data, name, sheet, header_row)


@st.cache_data(show_spinner="Karşılaştırılıyor…")
def cached_compare(old_data: bytes, new_data: bytes, old_meta: tuple, new_meta: tuple,
                   pairs: tuple, compare: tuple, roles: tuple, show_format: bool, threshold: float):
    old = cached_table(old_data, *old_meta)
    new = cached_table(new_data, *new_meta)
    cp = [ColumnPair(o, n) for o, n in pairs]
    group, order, unit, key = roles
    s = Settings(cp, list(compare), group=group, order=order, unit=unit, key=key,
                 show_format=show_format, threshold=threshold)
    return compare_tables(old, new, s)


@st.cache_data(show_spinner="PDF hazırlanıyor…")
def cached_pdf(_res, res_key: str, cats: tuple, groups: tuple, query: str, moved_only_at_new: bool,
               title: str) -> bytes:
    return report_pdf(_res, Filters(set(cats), set(groups), query, moved_only_at_new), title)


def digest(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Kenar çubuğu: dosyalar ve seçenekler
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Dosyalar")
    up_old = st.file_uploader("Eski sürüm", type=["xlsx", "xlsm"], key="up_old")
    up_new = st.file_uploader("Güncel sürüm", type=["xlsx", "xlsm"], key="up_new")
    if all(os.path.exists(os.path.join(APP_DIR, f)) for f in SAMPLES) and not (up_old and up_new):
        if st.button("Örnek dosyaları kullan", icon=":material/folder_open:", width="stretch"):
            st.session_state["sample"] = True
    st.divider()
    st.header("Seçenekler")
    ignore_ws = st.toggle("Boşluk / alt+enter farklarını yok say", value=True,
                          help="Açıkken yalnızca boşluk veya satır sonu (alt+enter) farkı olan hücreler aynı sayılır. "
                               "Kapalıyken bu farklar 'Biçim farkı' olarak işaretlenir. "
                               "Büyük/küçük harf ve noktalama her zaman metin farkıdır.")
    threshold = st.slider("Satır eşleştirme benzerlik eşiği (%)", 30, 95, 55, 5,
                          help="İki satırın aynı satırın farklı sürümleri sayılması için gereken en düşük benzerlik. "
                               "Düşük eşik daha çok 'metin farkı', yüksek eşik daha çok 'silinen + eklenen' üretir.")


def load_source(upload, sample_name: str):
    if upload is not None:
        return upload.getvalue(), upload.name
    if st.session_state.get("sample"):
        with open(os.path.join(APP_DIR, sample_name), "rb") as fh:
            return fh.read(), sample_name
    return None, None


old_bytes, old_name = load_source(up_old, SAMPLES[0])
new_bytes, new_name = load_source(up_new, SAMPLES[1])

st.title("Excel Sürüm Karşılaştırma")
if not (old_bytes and new_bytes):
    st.info("Soldaki panelden **eski** ve **güncel** Excel dosyalarını yükleyin.")
    st.markdown(
        "- Dersler dosyadaki sıralarına bakılmaksızın adlarına göre karşılıklı getirilir.\n"
        "- Aynı dersin birden fazla programı (ör. TYMM ve eski program) ayrı bloklar olarak eşleştirilir; "
        "karşılığı olmayan program tamamen silinmiş gösterilir.\n"
        "- Eklenen satırlar **yeşil**, silinenler **kırmızı ve üstü çizili**, taşınanlar **mor** gösterilir.\n"
        "- Rapor, Word'deki *değişiklikleri izle* görünümünde yatay A4 PDF ve HTML olarak indirilebilir."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sayfa ve başlık satırı seçimi
# ---------------------------------------------------------------------------
fid = digest(old_bytes) + digest(new_bytes)
c1, c2 = st.columns(2)
metas = []
for col, data, name, side in ((c1, old_bytes, old_name, "Eski"), (c2, new_bytes, new_name, "Güncel")):
    with col:
        sheets = cached_sheets(data)
        a, b = st.columns([3, 1])
        sheet = a.selectbox(f"{side} sürüm sayfası · {name}", sheets, key=f"sheet_{side}_{fid}")
        hdr = b.number_input("Başlık satırı", min_value=0, max_value=50, value=0, key=f"hdr_{side}_{fid}",
                             help="0 = otomatik bul")
        metas.append((data, name, sheet, int(hdr) or None))

old_t = cached_table(metas[0][0], *metas[0][1:])
new_t = cached_table(metas[1][0], *metas[1][1:])
if not old_t.columns or not new_t.columns:
    st.error("Seçilen sayfalardan biri boş görünüyor.")
    st.stop()

# ---------------------------------------------------------------------------
# Sütun eşleme ve roller
# ---------------------------------------------------------------------------
mkey = f"map_{fid}_{metas[0][2]}_{metas[1][2]}_{metas[0][3]}_{metas[1][3]}"
if mkey not in st.session_state:
    auto = auto_map(old_t, new_t)
    roles0 = guess_roles(auto, old_t, new_t)
    st.session_state[mkey] = pd.DataFrame({
        "Güncel sütun": [p.new or NONE for p in auto],
        "Eski sütun": [p.old or NONE for p in auto],
        "Karşılaştır": [i != roles0["order"] and bool(p.old and p.new) for i, p in enumerate(auto)],
    })

with st.expander("Sütun eşleme ve karşılaştırılacak sütunlar", expanded=False, icon=":material/view_column:"):
    st.caption("Başlıkları farklı olan sütunlar içeriklerine göre otomatik eşleştirildi. "
               "Gerekirse eski sütunu değiştirin ve karşılaştırılacak sütunları işaretleyin.")
    edited = st.data_editor(
        st.session_state[mkey], key=f"ed_{mkey}", hide_index=True, width="stretch",
        column_config={
            "Güncel sütun": st.column_config.TextColumn(disabled=True),
            "Eski sütun": st.column_config.SelectboxColumn(options=[NONE] + old_t.columns, required=True),
            "Karşılaştır": st.column_config.CheckboxColumn(),
        },
    )

pairs = [ColumnPair(None if o == NONE else o, None if n == NONE else n)
         for n, o in zip(edited["Güncel sütun"], edited["Eski sütun"])]
labels = [p.label for p in pairs]
auto_roles = guess_roles(pairs, old_t, new_t)

r1, r2, r3, r4 = st.columns(4)
role_opts = [NONE] + labels


def role_box(col, title, role, help_text):
    default = auto_roles.get(role)
    idx = default + 1 if default is not None else 0
    choice = col.selectbox(title, role_opts, index=idx, key=f"role_{role}_{mkey}", help=help_text)
    return None if choice == NONE else labels.index(choice)


g_role = role_box(r1, "Ders (grup) sütunu", "group", "Dersleri dosyadaki sıradan bağımsız eşleştirmek için.")
o_role = role_box(r2, "Sıra no sütunu", "order", "1'e döndüğü yerde aynı dersin yeni bir programı başlar.")
u_role = role_box(r3, "Ünite / tema sütunu", "unit", "Üniteler arası taşımaları bulmak için.")
k_role = role_box(r4, "Anahtar sütun (kazanım)", "key", "Satır eşleştirmede en yüksek ağırlığı alır; baştaki kazanım kodu yok sayılır.")

compare_idx = [i for i, flag in enumerate(edited["Karşılaştır"]) if flag]
if not compare_idx:
    st.warning("En az bir sütunu karşılaştırmak için işaretleyin.")
    st.stop()

res = cached_compare(
    old_bytes, new_bytes, metas[0][1:], metas[1][1:],
    tuple((p.old, p.new) for p in pairs), tuple(compare_idx),
    (g_role, o_role, u_role, k_role), not ignore_ws, float(threshold),
)
res_key = f"{mkey}_{compare_idx}_{g_role}_{o_role}_{u_role}_{k_role}_{ignore_ws}_{threshold}"

# ---------------------------------------------------------------------------
# Özet ve filtreler
# ---------------------------------------------------------------------------
stats = res.stats
m = st.columns(6)
for col, cat in zip(m, [CAT_TEXT, CAT_FORMAT, CAT_MOVED, CAT_DELETED, CAT_ADDED, CAT_SAME]):
    col.metric(cat, stats.get(cat, 0), border=True)
st.caption(f"Eski: **{old_name}** ({stats['Eski satır']} satır) → Güncel: **{new_name}** ({stats['Yeni satır']} satır)"
           + (" · Boşluk/alt+enter farkları yok sayılıyor" if ignore_ws else " · Boşluk/alt+enter farkları gösteriliyor"))

f1, f2, f3 = st.columns([3, 2, 2])
with f1:
    cats = st.pills("Gösterilecek değişiklikler (boş = tümü)", ALL_CATEGORIES, selection_mode="multi",
                    key="flt_cats")
groups_all = list(dict.fromkeys(sec.group for sec in res.sections))
groups = f2.multiselect("Ders", groups_all, placeholder="Tüm dersler", key="flt_groups")
query = f3.text_input("Metinde ara", key="flt_query", placeholder="ör. BİY.9.2 veya animasyon")
flt = Filters(set(cats or []), set(groups), query.strip())

tab_side, tab_report, tab_summary = st.tabs(
    [":material/compare: Yan yana", ":material/track_changes: Değişiklikleri izle raporu", ":material/table_chart: Ders özeti"])

with tab_side:
    a, b, c, d = st.columns([2, 1, 1, 1])
    layout = a.segmented_control("Düzen", ["Excel'ler yan yana", "Sütun sütun"], default="Excel'ler yan yana",
                                 key="layout")
    font_px = b.slider("Yazı boyutu", 9, 20, 13, key="side_font")
    height = c.slider("Tablo yüksekliği", 400, 1600, 750, 50, key="side_h")
    per_page = d.selectbox("Sayfa başına satır", [100, 250, 500, "Tümü"], index=1, key="side_pp")
    total = sum(len(rows) for _, rows in filter_sections(res, flt, report=False))
    page = None
    if per_page != "Tümü" and total > per_page:
        pages = (total + per_page - 1) // per_page
        pno = st.number_input(f"Sayfa (toplam {pages})", 1, pages, 1, key="side_page")
        page = ((pno - 1) * per_page, per_page)
    html, _ = side_by_side_html(res, flt, "excel" if layout != "Sütun sütun" else "column", font_px, page)
    st.caption(f"{total} satır gösteriliyor. Tabloyu **⛶ Tam ekran** düğmesiyle büyütebilir, A− / A+ ile yakınlaştırabilirsiniz.")
    components.html(html, height=height, scrolling=False)

with tab_report:
    a, b, c = st.columns([3, 2, 2])
    title = a.text_input("Rapor başlığı", "E-İçerik Programı Değişiklik Raporu", key="rep_title")
    apply_f = b.toggle("Filtreleri rapora uygula", value=True, key="rep_apply",
                       help="Kapalıyken rapor tüm satırları içerir.")
    moved_new_only = c.checkbox("Taşınanları yalnızca taşındığı yerde göster", value=True, key="rep_moved_new",
                                help="İşaretliyken taşınan satır raporda yalnızca yeni yerinde (mor çift altı çizili) "
                                     "görünür; eski yerindeki üstü çizili kopyası gösterilmez. "
                                     "Eski yeri, satırın 'Değişiklikler' sütununda yazar.")
    rf = replace(flt if apply_f else Filters(), moved_only_at_new=moved_new_only)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    html_doc = report_html(res, rf, title, standalone=True)
    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("HTML indir", html_doc.encode("utf-8"), f"degisiklik_raporu_{stamp}.html", "text/html",
                       icon=":material/download:", width="stretch")
    if d2.button("PDF oluştur (A4 yatay)", icon=":material/picture_as_pdf:", width="stretch"):
        st.session_state["pdf"] = (res_key, rf, title, cached_pdf(
            res, res_key, tuple(sorted(rf.categories)), tuple(sorted(rf.groups)), rf.query,
            rf.moved_only_at_new, title))
    pdf = st.session_state.get("pdf")
    if pdf and pdf[0] == res_key and pdf[1] == rf and pdf[2] == title:
        d2.download_button("PDF indir", pdf[3], f"degisiklik_raporu_{stamp}.pdf", "application/pdf",
                           icon=":material/download:", width="stretch", type="primary")
    rh = st.slider("Önizleme yüksekliği", 400, 1600, 800, 50, key="rep_h")
    components.html(report_html(res, rf, title, standalone=False), height=rh, scrolling=True)

with tab_summary:
    rows = []
    for sec in res.sections:
        cnt = {c: sum(1 for r in sec.rows if c in r.categories) for c in ALL_CATEGORIES}
        rows.append({
            "Ders": sec.group,
            "Bölüm": {"matched": "Eşleşti", "deleted_block": "Program silindi",
                      "added_block": "Program eklendi"}[sec.status],
            "Başlık": sec.title,
            "Eski satır": len(sec.old_block.rows) if sec.old_block else 0,
            "Güncel satır": len(sec.new_block.rows) if sec.new_block else 0,
            **cnt,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
