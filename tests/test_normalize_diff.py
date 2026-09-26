from excel_diff.diff import DEL, FMT, INS, diff_cell
from excel_diff.normalize import match_key, norm_ws, strip_code


def test_norm_ws_collapses_whitespace_and_newlines():
    assert norm_ws("  a\n\nb  c  ") == "a b c"


def test_strip_code_removes_leading_learning_outcome_code():
    assert strip_code("BİY.9.2.1. İnorganik moleküller") == "İnorganik moleküller"
    assert strip_code(" F.3.1.1.1. Dünya") == "Dünya"
    assert strip_code("Ön Değerlendirme") == "Ön Değerlendirme"


def test_turkish_lowercase_for_matching():
    assert match_key("İSTİKLÂL MARŞI") == "istiklâl marşı"


def test_whitespace_only_difference_is_format_or_same():
    old, new = "Bir video hazırlanır.\nİkinci", "Bir video hazırlanır.\n\nİkinci"
    assert diff_cell("c", old, new, show_format=False).status == "same"
    d = diff_cell("c", old, new, show_format=True)
    assert d.status == "format"
    assert any(op == FMT for op, _ in d.merged)


def test_case_change_is_text_difference():
    d = diff_cell("c", "Türk Bayrağı ve", "Türk bayrağı ve", show_format=False)
    assert d.status == "text"
    assert (DEL, "Bayrağı") in d.merged and (INS, "bayrağı") in d.merged


def test_text_cell_with_whitespace_change_counts_format_too():
    d = diff_cell("c", " BİY.9.2.5. Hücre", "BİY.9.2.1. Hücre", show_format=True)
    assert d.status == "text" and d.fmt == 1
