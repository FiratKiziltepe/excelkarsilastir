"""Değişiklikleri izle raporunu yatay A4 PDF olarak üretir (reportlab)."""
from __future__ import annotations

import io
import os
from datetime import datetime
from xml.sax.saxutils import escape as xesc

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.doctemplate import LayoutError
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from .diff import DEL, EQ, FMT, INS
from .filtering import Filters, column_weights, filter_sections
from .model import (CAT_ADDED, CAT_DELETED, CAT_FORMAT, CAT_MOVED, CAT_SAME, CAT_TEXT, CompareResult,
                    RowResult)

ADD, ADD_BG = "#1a7f37", "#dafbe1"
DELC, DEL_BG = "#cf222e", "#ffebe9"
MOV, MOV_BG = "#8250df", "#fbefff"
FMTC, FMT_BG = "#bc4c00", "#fff1e5"
TEXTC = "#0969da"

_HERE = os.path.dirname(__file__)
_FONT_CANDIDATES = [
    (os.path.join(_HERE, "fonts", "DejaVuSans.ttf"), os.path.join(_HERE, "fonts", "DejaVuSans-Bold.ttf")),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]
_FONT: tuple[str, str] | None = None
_GLYPHS: set[int] = set()


def _font() -> tuple[str, str]:
    """Türkçe karakterleri destekleyen ilk TTF fontu kaydeder."""
    global _FONT, _GLYPHS
    if _FONT:
        return _FONT
    for reg, bold in _FONT_CANDIDATES:
        if os.path.exists(reg):
            f = TTFont("RptFont", reg)
            pdfmetrics.registerFont(f)
            _GLYPHS = set(f.face.charToGlyph)
            if os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("RptFont-Bold", bold))
                _FONT = ("RptFont", "RptFont-Bold")
            else:
                _FONT = ("RptFont", "RptFont")
            return _FONT
    raise RuntimeError("PDF için Türkçe destekli bir TTF font bulunamadı. "
                       "excel_diff/fonts/DejaVuSans.ttf dosyasını ekleyin.")


def _safe(text: str) -> str:
    """Fontta olmayan sembolleri değiştir, XML kaçışı yap, satır sonlarını koru."""
    if _GLYPHS:
        text = "".join(ch if (ord(ch) in _GLYPHS or ch in "\n\t") else _SUBST.get(ch, "?") for ch in text)
    return xesc(text).replace("\n", "<br/>")


_SUBST = {"↵": "¶", "⇄": "↔", "⏎": "¶", "\u200b": "", "\u00a0": " "}


def _del(t: str, color: str = DELC, bg: str | None = DEL_BG) -> str:
    bgattr = f' backColor="{bg}"' if bg else ""
    return f'<font color="{color}"{bgattr}><strike color="{color}" width="0.7">{t}</strike></font>'


def _ins(t: str) -> str:
    return f'<font color="{ADD}" backColor="{ADD_BG}"><u color="{ADD}" width="0.7">{t}</u></font>'


def _dstrike(t: str) -> str:
    return (f'<font color="{MOV}"><strike color="{MOV}" width="0.6" offset="0.2*F">'
            f'<strike color="{MOV}" width="0.6" offset="0.42*F">{t}</strike></strike></font>')


def _dunder(t: str) -> str:
    return (f'<u color="{MOV}" width="0.6"><u color="{MOV}" width="0.6" offset="-0.32*F">{t}</u></u>')


def segs_markup(segs: list[tuple[str, str]], mode: str = "") -> str:
    out = []
    for op, text in segs:
        t = _safe(text)
        if not t:
            continue
        if mode == "mvfrom":
            out.append(_dstrike(t) if op != FMT else t)
            continue
        if op == EQ:
            out.append(_dunder(t) if mode == "mvto" and text.strip() else t)
        elif op == DEL:
            out.append(_del(t))
        elif op == INS:
            out.append(_ins(t))
        elif op == FMT:
            out.append(f'<font color="{FMTC}" backColor="{FMT_BG}" size="6.5">{t}</font>')
    return "".join(out)


def _left_color(r: RowResult) -> str | None:
    for cat, col in ((CAT_ADDED, ADD), (CAT_DELETED, DELC), (CAT_MOVED, MOV), (CAT_TEXT, TEXTC), (CAT_FORMAT, FMTC)):
        if cat in r.categories:
            return col
    return None


def report_pdf(res: CompareResult, f: Filters, title: str = "Değişiklik Raporu", font_size: float = 7.5) -> bytes:
    reg, bold = _font()
    base = ParagraphStyle("b", fontName=reg, fontSize=font_size, leading=font_size * 1.28)
    head = ParagraphStyle("h", parent=base, fontName=bold)
    sumst = ParagraphStyle("s", parent=base, fontSize=font_size - 0.8, leading=(font_size - 0.8) * 1.28,
                           textColor=colors.HexColor("#59636e"))
    secst = ParagraphStyle("sec", parent=base, fontName=bold, fontSize=font_size + 1, leading=(font_size + 1) * 1.3)
    titlest = ParagraphStyle("t", parent=base, fontName=bold, fontSize=15, leading=19)
    meta = ParagraphStyle("m", parent=base, fontSize=8.5, leading=11, textColor=colors.HexColor("#59636e"))

    page = landscape(A4)
    margin = 10 * mm
    avail = page[0] - 2 * margin
    w = column_weights(res)
    parts = [2.8] + w + [10.0]
    widths = [avail * p / sum(parts) for p in parts]

    order_label = (res.order_pair.new or res.order_pair.old) if res.order_pair else "No"
    header = [Paragraph(_safe(order_label or "No"), head)]
    for p in res.pairs:
        if p.renamed:
            header.append(Paragraph(f"{_safe(p.new)}<br/>{_del(_safe(p.old), bg=None)}", head))
        elif p.new is None:
            header.append(Paragraph(_del(_safe(p.old or ""), bg=None), head))
        elif p.old is None:
            header.append(Paragraph(_ins(_safe(p.new)), head))
        else:
            header.append(Paragraph(_safe(p.label), head))
    header.append(Paragraph("Değişiklikler", head))

    rows = [header]
    style = [
        ("FONT", (0, 0), (-1, -1), reg, font_size),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d9e0")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fa")),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    ncol = len(widths)
    for sec, srows in filter_sections(res, f, report=True):
        i = len(rows)
        t = _safe(sec.title)
        if sec.status == "deleted_block":
            t = _del(t, bg=None)
            bg = DEL_BG
        elif sec.status == "added_block":
            t = f'<font color="{ADD}">{t}</font>'
            bg = ADD_BG
        else:
            bg = "#eef1f4"
        rows.append([Paragraph(t, secst)] + [""] * (ncol - 1))
        style += [("SPAN", (0, i), (-1, i)), ("BACKGROUND", (0, i), (-1, i), colors.HexColor(bg)),
                  ("LINEABOVE", (0, i), (-1, i), 1, colors.HexColor("#afb8c1"))]
        for r in srows:
            i = len(rows)
            mode = "mvfrom" if r.kind == "moved_from" else ("mvto" if r.kind == "matched" and r.moved else "")
            if r.kind == "deleted":
                no = _del(_safe(r.old_order), bg=None)
            elif r.kind == "moved_from":
                no = _safe(r.old_order)
            else:
                no = _safe(r.new_order)
            cells = [Paragraph(no, base)]
            cells += [Paragraph(segs_markup(c.merged, mode) or "", base) for c in r.cells]
            summ = []
            for k, s in enumerate(r.summary):
                s = _safe(s)
                summ.append(f'<font color="{MOV}"><b>{s}</b></font>' if r.moved and k == 0 else s)
            cells.append(Paragraph("<br/>".join(summ), sumst))
            rows.append(cells)
            lc = _left_color(r)
            if lc:
                style.append(("LINEBEFORE", (0, i), (0, i), 2.5, colors.HexColor(lc)))
            if r.kind == "moved_from":
                style.append(("BACKGROUND", (1, i), (-2, i), colors.HexColor(MOV_BG)))
    if len(rows) == 1:
        rows.append([Paragraph("Seçili filtrelere uyan satır yok.", base)] + [""] * (ncol - 1))
        style.append(("SPAN", (0, 1), (-1, 1)))

    def make_table(split: int):
        t = LongTable(rows, colWidths=widths, repeatRows=1, splitInRow=split)
        t.setStyle(TableStyle(style))
        return t

    st = res.stats
    stats = " · ".join(f"{c}: {st.get(c, 0)}" for c in (CAT_TEXT, CAT_FORMAT, CAT_MOVED, CAT_DELETED, CAT_ADDED, CAT_SAME))
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    legend = (f"Açıklama: {_ins('eklenen')}   {_del('silinen')}   {_dstrike('buradan taşındı')}   "
              f"{_dunder('buraya taşındı')}   "
              f'<font color="{FMTC}" backColor="{FMT_BG}">{_safe("↵+ / ↵− / ·")}</font> satır sonu / boşluk farkı')
    story = [
        Paragraph(_safe(title), titlest),
        Paragraph(f"Eski sürüm: <b>{_safe(res.old_name)}</b>  →  Güncel sürüm: <b>{_safe(res.new_name)}</b> · {now} · "
                  f"Eski {st.get('Eski satır', 0)} satır, güncel {st.get('Yeni satır', 0)} satır", meta),
        Paragraph(_safe(stats), meta),
    ]
    if f.categories or f.groups or f.query:
        bits = []
        if f.categories:
            bits.append("Kategori: " + ", ".join(sorted(f.categories)))
        if f.groups:
            bits.append("Ders: " + ", ".join(sorted(f.groups)))
        if f.query:
            bits.append(f"Arama: “{f.query}”")
        story.append(Paragraph(_safe("Filtre — " + " · ".join(bits)), meta))
    story += [Paragraph(legend, meta), Spacer(1, 4 * mm)]

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(reg, 7)
        canvas.setFillColor(colors.HexColor("#59636e"))
        canvas.drawString(margin, 6 * mm, f"{title} · {res.old_name} → {res.new_name}")
        canvas.drawRightString(page[0] - margin, 6 * mm, f"Sayfa {doc.page}")
        canvas.restoreState()

    def build(split: int) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=margin,
                                bottomMargin=12 * mm, title=title, author="Excel Karşılaştırma")
        doc.build(story + [make_table(split)], onFirstPage=on_page, onLaterPages=on_page)
        return buf.getvalue()

    try:
        return build(0)
    except LayoutError:
        # Sayfaya sığmayan çok uzun bir satır varsa satır içinden bölmeye izin ver
        return build(1)
