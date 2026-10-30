"""Number parsing that accepts Persian/Arabic-Indic digits and separators."""

from __future__ import annotations

from typing import Optional

_TRANS = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_TRANS.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})
_TRANS.update({ord("٫"): ".", ord("٬"): "", ord("،"): "", ord(","): "", ord(" "): "", ord(" "): "",
               ord("−"): "-", ord("–"): "-"})


def parse_float(text) -> Optional[float]:
    """Return a float, or None for empty/invalid text. Commas are thousands separators."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).translate(_TRANS).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt_float(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"{v:.10g}"
