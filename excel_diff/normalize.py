"""Metin normalleştirme yardımcıları.

"Biçim farkı" = yalnızca boşluk / alt+enter (satır sonu) / NBSP / baş-son boşluk farkı.
Büyük-küçük harf ve noktalama içerik sayılır, burada DOKUNULMAZ.
"""
from __future__ import annotations

import re

_WS_RE = re.compile(r"\s+")
# Kazanım kodu: "HB.1.1.1.", "BİY.9.2.1.", "F.3.1.1.1.", "FİZ.9.4.3." gibi
_CODE_RE = re.compile(r"^\s*[A-Za-zÇĞİÖŞÜçğıöşü]{1,6}\.(?:\d+\.)*\d+\.?\s*")
_TOKEN_RE = re.compile(r"\S+")


def to_text(value) -> str:
    """Hücre değerini metne çevirir (None -> '', 3.0 -> '3')."""
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if value.is_integer():
            return str(int(value))
    return str(value)


def norm_ws(text: str) -> str:
    """NBSP, satır sonu ve çoklu boşlukları tek boşluğa indirger, baş/son boşluğu atar."""
    if not text:
        return ""
    return _WS_RE.sub(" ", text.replace(" ", " ").replace("​", "")).strip()


def tr_lower(text: str) -> str:
    """Türkçe'ye uygun küçük harfe çevirme (yalnızca eşleştirme için)."""
    return text.replace("I", "ı").replace("İ", "i").lower()


def match_key(text: str) -> str:
    """Satır/grup eşleştirmede kullanılan anahtar: boşluk normalize + küçük harf."""
    return tr_lower(norm_ws(text))


def strip_code(text: str) -> str:
    """Baştaki kazanım kodunu atar ("BİY.9.2.1. İnorganik..." -> "İnorganik...")."""
    return _CODE_RE.sub("", text or "", count=1)


def extract_code(text: str) -> str:
    m = _CODE_RE.match(text or "")
    return m.group(0).strip() if m else ""


def tokenize(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Metni (baştaki boşluk, [(kelime, sonraki boşluk), ...]) biçiminde parçalar.

    Kelime = boşluk içermeyen karakter dizisi; böylece noktalama ve harf farkları
    kelime farkı olarak, boşluk/alt+enter farkları ise ayrı olarak ele alınabilir.
    """
    text = text or ""
    tokens: list[tuple[str, str]] = []
    matches = list(_TOKEN_RE.finditer(text))
    if not matches:
        return text, []
    lead = text[: matches[0].start()]
    for i, m in enumerate(matches):
        end_ws = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        tokens.append((m.group(0), text[m.end(): end_ws]))
    return lead, tokens


def ws_signature(ws: str) -> str:
    """Boşluk parçasının anlamlı özeti: satır sonu sayısı + boşluk var/yok."""
    if not ws:
        return ""
    nl = ws.count("\n")
    return "\n" * nl if nl else " "
