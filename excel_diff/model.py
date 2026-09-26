"""Karşılaştırma sonucunu taşıyan veri yapıları."""
from __future__ import annotations

from dataclasses import dataclass, field

# Satır kategorileri (filtrelerde kullanılır)
CAT_ADDED = "Eklenen"
CAT_DELETED = "Silinen"
CAT_TEXT = "Metin farkı"
CAT_FORMAT = "Biçim farkı"
CAT_MOVED = "Taşınan"
CAT_SAME = "Değişmeyen"
ALL_CATEGORIES = [CAT_TEXT, CAT_FORMAT, CAT_MOVED, CAT_DELETED, CAT_ADDED, CAT_SAME]


@dataclass
class CellDiff:
    col: str
    old: str
    new: str
    status: str  # same | format | text | added | deleted
    merged: list[tuple[str, str]]
    old_view: list[tuple[str, str]]
    new_view: list[tuple[str, str]]
    detail: str = ""
    fmt: int = 0  # boşluk/satır sonu farkı sayısı (biçim gösterim modunda)


@dataclass
class ColumnPair:
    old: str | None
    new: str | None

    @property
    def label(self) -> str:
        if self.old and self.new and self.old != self.new:
            return f"{self.new}"
        return self.new or self.old or ""

    @property
    def renamed(self) -> bool:
        return bool(self.old and self.new and self.old != self.new)


@dataclass
class Table:
    """Okunmuş Excel sayfası."""
    name: str
    sheet: str
    columns: list[str]
    rows: list[list[str]]  # ham metin değerleri
    excel_rows: list[int]  # her satırın Excel'deki satır numarası


@dataclass
class Block:
    """Bir dersin tek bir program bloğu (ör. Fen Bilimleri 3 - TYMM)."""
    side: str  # "old" | "new"
    group: str  # görünen ders adı
    group_key: str
    index: int  # dosyadaki blok sırası
    rows: list[int]  # Table.rows içindeki indeksler

    def label(self) -> str:
        return f"{self.group}"


@dataclass
class RowResult:
    kind: str  # matched | added | deleted | moved_from
    group: str
    old_idx: int | None = None
    new_idx: int | None = None
    old_excel_row: int | None = None
    new_excel_row: int | None = None
    old_order: str = ""
    new_order: str = ""
    cells: list[CellDiff] = field(default_factory=list)
    moved: str | None = None  # None | "unit" | "order"
    old_unit: str = ""
    new_unit: str = ""
    score: float = 0.0
    categories: set[str] = field(default_factory=set)
    summary: list[str] = field(default_factory=list)
    block_status: str = ""  # "" | "deleted_block" | "added_block"


@dataclass
class Section:
    """Rapor/yan yana tablodaki bir ders-program bölümü."""
    group: str
    status: str  # matched | deleted_block | added_block
    title: str
    rows: list[RowResult] = field(default_factory=list)  # yan yana sırası
    report_rows: list[RowResult] = field(default_factory=list)  # değişiklikleri izle sırası
    old_block: Block | None = None
    new_block: Block | None = None


@dataclass
class CompareResult:
    old_name: str
    new_name: str
    pairs: list[ColumnPair]
    order_pair: ColumnPair | None
    sections: list[Section]
    show_format: bool
    stats: dict[str, int] = field(default_factory=dict)
