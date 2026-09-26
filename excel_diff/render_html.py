"""HTML çıktıları: yan yana karşılaştırma tablosu ve Word tarzı değişiklik raporu."""
from __future__ import annotations

from datetime import datetime
from html import escape

from .diff import DEL, EQ, FMT, INS
from .filtering import Filters, column_weights, filter_sections
from .model import (CAT_ADDED, CAT_DELETED, CAT_FORMAT, CAT_MOVED, CAT_SAME, CAT_TEXT, CompareResult,
                    RowResult)

CAT_CLASS = {CAT_TEXT: "text", CAT_FORMAT: "format", CAT_MOVED: "moved", CAT_DELETED: "deleted",
             CAT_ADDED: "added", CAT_SAME: "same"}

BASE_CSS = """
:root{
  --ink:#1f2328; --muted:#59636e; --line:#d1d9e0; --head:#f6f8fa; --band:#eef1f4;
  --add:#1a7f37; --add-bg:#dafbe1; --del:#cf222e; --del-bg:#ffebe9;
  --mov:#8250df; --mov-bg:#fbefff; --fmt:#bc4c00; --fmt-bg:#fff1e5; --empty:#f6f8fa;
  --fs:13px;
}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--ink);font-family:"Segoe UI",Calibri,Arial,"DejaVu Sans",sans-serif;font-size:var(--fs)}
table{border-collapse:separate;border-spacing:0;width:100%}
th,td{border-right:1px solid var(--line);border-bottom:1px solid var(--line);padding:5px 7px;vertical-align:top;text-align:left;
  overflow-wrap:anywhere;line-height:1.4}
th{background:var(--head);font-weight:600;font-size:.9em}
del.d{color:var(--del);text-decoration:line-through;text-decoration-thickness:1.5px;background:var(--del-bg)}
ins.i{color:var(--add);text-decoration:underline;background:var(--add-bg)}
span.f{color:var(--fmt);background:var(--fmt-bg);border-bottom:1px dotted var(--fmt);font-size:.85em;padding:0 1px}
tr.sec td{background:var(--band);font-weight:700;font-size:1.02em;border-top:2px solid #afb8c1}
tr.sec.deleted_block td{background:var(--del-bg);color:var(--del);text-decoration:line-through}
tr.sec.added_block td{background:var(--add-bg);color:var(--add)}
tr.mvfrom td.c{color:var(--mov);text-decoration:line-through double;background:var(--mov-bg)}
tr.mvfrom td.c del.d{color:var(--mov);background:transparent;text-decoration:line-through double}
tr.mvto td.c{text-decoration:underline double var(--mov);text-decoration-skip-ink:none}
tr.mvto td.c ins.i, tr.mvto td.c del.d{text-decoration-color:inherit}
td.sum{font-size:.88em;color:var(--muted)}
td.sum div{margin:0 0 2px}
td.sum .mv{color:var(--mov);font-weight:600}
td.no{white-space:nowrap;color:var(--muted);font-size:.9em;text-align:right}
.chip{display:inline-block;border-radius:10px;padding:0 6px;margin:0 3px 3px 0;font-size:.78em;font-weight:600;white-space:nowrap}
.chip.text{background:#ddf4ff;color:#0969da}.chip.format{background:var(--fmt-bg);color:var(--fmt)}
.chip.moved{background:var(--mov-bg);color:var(--mov)}.chip.deleted{background:var(--del-bg);color:var(--del)}
.chip.added{background:var(--add-bg);color:var(--add)}.chip.same{background:#eaeef2;color:var(--muted)}
tr td:first-child{border-left:4px solid transparent}
tr.r-added td:first-child{border-left-color:var(--add)}
tr.r-deleted td:first-child{border-left-color:var(--del)}
tr.r-moved td:first-child{border-left-color:var(--mov)}
tr.r-text td:first-child{border-left-color:#0969da}
tr.r-format td:first-child{border-left-color:var(--fmt)}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.88em;color:var(--muted);align-items:center}
.legend b{font-weight:600;color:var(--ink)}
"""

LEGEND = (
    '<div class="legend"><b>Açıklama:</b>'
    '<span><ins class="i">eklenen</ins></span>'
    '<span><del class="d">silinen</del></span>'
    '<span style="color:#8250df;text-decoration:line-through double">buradan taşındı</span>'
    '<span style="color:#8250df;text-decoration:underline double">buraya taşındı</span>'
    '<span><span class="f">↵+</span> satır sonu eklendi</span>'
    '<span><span class="f">↵−</span> satır sonu kaldırıldı</span>'
    '<span><span class="f">·</span> boşluk farkı</span></div>'
)


def segs_html(segs: list[tuple[str, str]]) -> str:
    out = []
    for op, text in segs:
        t = escape(text).replace("\n", "<br>")
        if op == EQ:
            out.append(t)
        elif op == DEL:
            out.append(f'<del class="d">{t}</del>')
        elif op == INS:
            out.append(f'<ins class="i">{t}</ins>')
        elif op == FMT:
            out.append(f'<span class="f" title="Boşluk / satır sonu farkı">{t}</span>')
    return "".join(out)


def _row_class(r: RowResult) -> str:
    cls = []
    for cat in (CAT_ADDED, CAT_DELETED, CAT_MOVED, CAT_TEXT, CAT_FORMAT):
        if cat in r.categories:
            cls.append("r-" + CAT_CLASS[cat])
            break
    if r.kind == "moved_from":
        cls.append("mvfrom")
    elif r.kind == "matched" and r.moved:
        cls.append("mvto")
    return " ".join(cls)


def _summary_html(r: RowResult, chips: bool = True) -> str:
    parts = []
    if chips:
        order = [CAT_ADDED, CAT_DELETED, CAT_MOVED, CAT_TEXT, CAT_FORMAT, CAT_SAME]
        parts.append("".join(f'<span class="chip {CAT_CLASS[c]}">{c}</span>' for c in order if c in r.categories))
    for i, s in enumerate(r.summary):
        cls = ' class="mv"' if r.moved and i == 0 else ""
        parts.append(f"<div{cls}>{escape(s)}</div>")
    return "".join(parts)


def _no_html(r: RowResult) -> str:
    if r.kind == "deleted":
        return f'<del class="d">{escape(r.old_order)}</del>'
    if r.kind == "moved_from":
        return escape(r.old_order)
    return escape(r.new_order)


def _pct(weights: list[float], extra: list[float]) -> list[float]:
    total = sum(weights) + sum(extra)
    return [w / total * 100 for w in weights + extra]


# ---------------------------------------------------------------------------
# Yan yana görünüm
# ---------------------------------------------------------------------------
SIDE_CSS = """
html,body{height:100%}
body{display:flex;flex-direction:column}
.bar{flex:0 0 auto;z-index:5;display:flex;gap:8px;align-items:center;padding:6px 8px;background:#fff;border-bottom:1px solid var(--line);flex-wrap:wrap}
.bar button{border:1px solid var(--line);background:var(--head);border-radius:6px;padding:3px 10px;cursor:pointer;font:inherit;font-size:13px}
.bar button:hover{background:#eaeef2}
.bar .sp{flex:1}
.wrap{overflow:auto;flex:1 1 auto;min-height:0}
table.side{min-width:var(--minw)}
table.side thead th{position:sticky;z-index:3}
table.side thead tr.h1 th{top:0;height:30px;font-size:.95em}
table.side thead tr.h2 th{top:30px}
th.oldh{background:#fff5f5}th.newh{background:#f3fff5}
td.empty{background:repeating-linear-gradient(45deg,#fff,#fff 6px,var(--empty) 6px,var(--empty) 12px)}
td.oldc{background:#fffdfd}
tr.mvto td.oldc{text-decoration:line-through double var(--mov)}
"""

SIDE_JS = """
<script>
const root=document.documentElement;let fs=%FS%;
function zoom(d){fs=Math.max(8,Math.min(24,fs+d));root.style.setProperty('--fs',fs+'px');}
function full(){
  const el=document.documentElement;
  if(document.fullscreenElement){document.exitFullscreen();return;}
  if(el.requestFullscreen){el.requestFullscreen().catch(()=>openTab());}else{openTab();}
}
function openTab(){
  const blob=new Blob(['<!doctype html>'+document.documentElement.outerHTML],{type:'text/html'});
  window.open(URL.createObjectURL(blob),'_blank');
}
</script>
"""


def side_by_side_html(res: CompareResult, f: Filters, layout: str = "excel", font_px: int = 13,
                      page: tuple[int, int] | None = None) -> tuple[str, int]:
    """Yan yana tablo HTML'i ve (sayfalama öncesi) toplam satır sayısı."""
    data = filter_sections(res, f, report=False)
    total = sum(len(rows) for _, rows in data)
    if page:
        start, size = page
        data = _slice(data, start, size)

    pairs = res.pairs
    w = column_weights(res)
    n = len(pairs)
    order_name_old = res.order_pair.old if res.order_pair else "No"
    order_name_new = res.order_pair.new if res.order_pair else "No"

    # Sütun sırası
    if layout == "excel":
        cols = [("no", "old", None)] + [("c", "old", k) for k in range(n)] + \
               [("no", "new", None)] + [("c", "new", k) for k in range(n)]
    else:
        cols = [("no", "old", None), ("no", "new", None)] + \
               [x for k in range(n) for x in (("c", "old", k), ("c", "new", k))]
    colw = [2.2 if kind == "no" else w[k] for kind, _, k in cols]
    pct = _pct(colw, [9.0])
    minw = int(sum(colw) * 28 + 250)

    h1, h2 = [], []
    if layout == "excel":
        h1.append(f'<th class="oldh" colspan="{n + 1}">Eski sürüm · {escape(res.old_name)}</th>')
        h1.append(f'<th class="newh" colspan="{n + 1}">Güncel sürüm · {escape(res.new_name)}</th>')
    else:
        h1.append('<th colspan="2">No</th>')
        h1 += [f'<th colspan="2">{escape(p.label)}</th>' for p in pairs]
    h1.append('<th rowspan="2" style="top:0">Değişiklikler</th>')
    for kind, side, k in cols:
        hcls = "oldh" if side == "old" else "newh"
        if kind == "no":
            name = order_name_old if side == "old" else order_name_new
            label = f"{'Eski' if side == 'old' else 'Yeni'} {name or 'No'}" if layout != "excel" else (name or "No")
        else:
            p = pairs[k]
            label = (p.old or "—") if side == "old" else (p.new or "—")
            if layout != "excel":
                label = "Eski" if side == "old" else "Güncel"
        h2.append(f'<th class="{hcls}">{escape(label)}</th>')

    body = []
    span = len(cols) + 1
    for sec, rows in data:
        body.append(f'<tr class="sec {sec.status}"><td colspan="{span}">{escape(sec.title)}</td></tr>')
        for r in rows:
            tds = []
            for kind, side, k in cols:
                has = (r.old_idx is not None) if side == "old" else (r.new_idx is not None)
                if r.kind == "added" and side == "old" or r.kind == "deleted" and side == "new":
                    has = False
                if not has:
                    tds.append('<td class="empty"></td>')
                    continue
                if kind == "no":
                    val = r.old_order if side == "old" else r.new_order
                    tds.append(f'<td class="no">{escape(val)}</td>')
                    continue
                c = r.cells[k]
                segs = c.old_view if side == "old" else c.new_view
                cls = "c oldc" if side == "old" else "c"
                tds.append(f'<td class="{cls}">{segs_html(segs)}</td>')
            tds.append(f'<td class="sum">{_summary_html(r)}</td>')
            body.append(f'<tr class="{_row_class(r)}">{"".join(tds)}</tr>')
    if not data:
        body.append(f'<tr><td colspan="{span}" style="padding:24px;text-align:center;color:#59636e">'
                    'Seçili filtrelere uyan satır yok.</td></tr>')

    colgroup = "".join(f'<col style="width:{p:.2f}%">' for p in pct)
    html = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<style>{BASE_CSS}{SIDE_CSS}</style></head>
<body style="--fs:{font_px}px;--minw:{minw}px">
<div class="bar"><button onclick="zoom(-1)" title="Küçült">A−</button><button onclick="zoom(1)" title="Büyüt">A+</button>
<button onclick="full()" title="Tam ekran">⛶ Tam ekran</button><span class="sp"></span>{LEGEND}</div>
<div class="wrap"><table class="side"><colgroup>{colgroup}</colgroup>
<thead><tr class="h1">{''.join(h1)}</tr><tr class="h2">{''.join(h2)}</tr></thead>
<tbody>{''.join(body)}</tbody></table></div>
{SIDE_JS.replace('%FS%', str(font_px))}</body></html>"""
    return html, total


def _slice(data, start: int, size: int):
    out, pos = [], 0
    for sec, rows in data:
        s0, s1 = max(start - pos, 0), min(start + size - pos, len(rows))
        if s0 < s1:
            out.append((sec, rows[s0:s1]))
        pos += len(rows)
    return out


# ---------------------------------------------------------------------------
# Değişiklikleri izle raporu
# ---------------------------------------------------------------------------
REPORT_CSS = """
@page{size:A4 landscape;margin:10mm}
body{padding:18px 22px}
header h1{font-size:1.45em;margin:0 0 4px}
header .meta{color:var(--muted);font-size:.9em;margin-bottom:8px}
.stats{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 10px}
table.rep{table-layout:fixed;margin-top:8px}
@media screen{table.rep{min-width:1100px}}
table.rep thead th{position:sticky;top:0;z-index:2}
th .oldname{display:block;font-weight:400;font-size:.85em}
.printbtn{position:fixed;right:16px;top:12px;border:1px solid var(--line);background:var(--head);border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit}
@media print{
  body{padding:0;--fs:8.3pt}
  .printbtn{display:none}
  table.rep thead{display:table-header-group}
  table.rep thead th{position:static}
  tr{page-break-inside:avoid;break-inside:avoid}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""


def report_html(res: CompareResult, f: Filters, title: str = "Değişiklik Raporu", standalone: bool = True,
                font_px: int = 12) -> str:
    data = filter_sections(res, f, report=True)
    pairs = res.pairs
    w = column_weights(res)
    pct = _pct([2.8] + w, [10.0])
    order_label = (res.order_pair.new or res.order_pair.old) if res.order_pair else "No"

    heads = [f"<th>{escape(order_label or 'No')}</th>"]
    for p in pairs:
        if p.renamed:
            heads.append(f'<th>{escape(p.new)}<span class="oldname"><del class="d">{escape(p.old)}</del></span></th>')
        elif p.new is None:
            heads.append(f'<th><del class="d">{escape(p.old or "")}</del></th>')
        elif p.old is None:
            heads.append(f'<th><ins class="i">{escape(p.new)}</ins></th>')
        else:
            heads.append(f"<th>{escape(p.label)}</th>")
    heads.append("<th>Değişiklikler</th>")

    span = len(pairs) + 2
    body = []
    for sec, rows in data:
        body.append(f'<tr class="sec {sec.status}"><td colspan="{span}">{escape(sec.title)}</td></tr>')
        for r in rows:
            tds = [f'<td class="no">{_no_html(r)}</td>']
            tds += [f'<td class="c">{segs_html(c.merged)}</td>' for c in r.cells]
            tds.append(f'<td class="sum">{_summary_html(r, chips=False)}</td>')
            body.append(f'<tr class="{_row_class(r)}">{"".join(tds)}</tr>')
    if not data:
        body.append(f'<tr><td colspan="{span}" style="padding:24px;text-align:center">Seçili filtrelere uyan satır yok.</td></tr>')

    st = res.stats
    chips = "".join(f'<span class="chip {CAT_CLASS[c]}">{c}: {st.get(c, 0)}</span>'
                    for c in (CAT_TEXT, CAT_FORMAT, CAT_MOVED, CAT_DELETED, CAT_ADDED, CAT_SAME))
    flt = ""
    if f.categories or f.groups or f.query or f.moved_only_at_new:
        bits = []
        if f.categories:
            bits.append("Kategori: " + ", ".join(sorted(f.categories)))
        if f.groups:
            bits.append("Ders: " + ", ".join(sorted(f.groups)))
        if f.query:
            bits.append(f"Arama: “{f.query}”")
        if f.moved_only_at_new:
            bits.append("Taşınan satırlar yalnızca yeni yerinde gösterilir; eski yeri 'Değişiklikler' sütununda yazar.")
        flt = f'<div class="meta">Filtre — {escape(" · ".join(bits))}</div>'
    colgroup = "".join(f'<col style="width:{p:.2f}%">' for p in pct)
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    printbtn = '<button class="printbtn" onclick="window.print()">Yazdır / PDF</button>' if standalone else ""
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>{BASE_CSS}{REPORT_CSS}</style></head><body style="--fs:{font_px}px">{printbtn}
<header><h1>{escape(title)}</h1>
<div class="meta">Eski sürüm: <b>{escape(res.old_name)}</b> &nbsp;→&nbsp; Güncel sürüm: <b>{escape(res.new_name)}</b> · {now}
 · Eski {st.get('Eski satır', 0)} satır, güncel {st.get('Yeni satır', 0)} satır</div>
{flt}<div class="stats">{chips}</div>{LEGEND}</header>
<table class="rep"><colgroup>{colgroup}</colgroup><thead><tr>{''.join(heads)}</tr></thead>
<tbody>{''.join(body)}</tbody></table></body></html>"""
