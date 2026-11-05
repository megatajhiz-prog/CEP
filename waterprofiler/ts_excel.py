"""Excel template for entering time-series data, and its import.

Layout of the data sheet (one row per period, one column per variable):

    row 1   headers: period | start | end | variable name [unit] ...
    row 2   "key" | | | variable keys (what the import reads; do not change)
    row 3+  period label | start (ISO date) | end (ISO date) | values ...

Dates are written as ISO text (YYYY-MM-DD, Gregorian) so Excel cannot re-interpret them. Blank cells mean "no data"
and are skipped on import, so importing never erases anything that is already in the project.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional, Sequence, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import jcalendar as cal
from . import timeseries as TS
from .model import Plant

HEAD_FILL = PatternFill("solid", fgColor="0B3C6E")
HEAD_FONT = Font(bold=True, color="FFFFFF")
KEY_FONT = Font(italic=True, color="8A94A6", size=9)
FIRST_DATA_ROW = 3

_TEXT = {
    "fa": {"data": "داده", "guide": "راهنما", "period": "دوره", "start": "شروع (میلادی)", "end": "پایان (میلادی)",
           "key": "key",
           "lines": ["نحوهٔ پر کردن",
                     "۱) فقط سلول‌های عددی ستون‌های متغیر را پر کنید؛ سلول خالی یعنی «بدون داده» و هنگام ورود نادیده گرفته می‌شود.",
                     "۲) حجم‌ها (m³، kWh، تولید، درآمد) مقدار کل همان دوره هستند. دما، قیمت و تعداد پرسنل مقدار میانگین دوره‌اند.",
                     "۳) ستون‌های دوره، شروع و پایان و سطر دوم (key) را تغییر ندهید. تاریخ‌ها میلادی‌اند و دورهٔ شمسی/میلادی فقط در ستون اول نوشته شده است.",
                     "۴) برای دورهٔ دیگر، در برنامه بازه و برش (ماهانه/سالانه) را تغییر دهید و دوباره قالب بگیرید؛ یا ردیف را با همان قالب تاریخ اضافه کنید.",
                     "۵) در برنامه: صفحهٔ سری زمانی ← «ورود از Excel…»."]},
    "en": {"data": "Data", "guide": "Guide", "period": "Period", "start": "Start (Gregorian)", "end": "End (Gregorian)",
           "key": "key",
           "lines": ["How to fill in",
                     "1) Fill only the number cells of the variable columns; a blank cell means \"no data\" and is skipped on import.",
                     "2) Volumes (m3, kWh, production, revenue) are the total of that period. Temperature, prices and head count are the mean of the period.",
                     "3) Do not change the period, start and end columns or row 2 (key). Dates are Gregorian; the Jalali/Gregorian label is only in column A.",
                     "4) For other periods change the range and slicing (monthly/yearly) in the program and export again, or add rows with the same date format.",
                     "5) In the program: Time series page > \"Import Excel...\"."]},
}


def export_template(plant: Plant, path: str, slices: Sequence[cal.Slice], specs: Sequence[TS.VarSpec], lang: str = "fa") -> int:
    """Write the template for the given slices and variables, prefilled with the data the project already has
    (only where a slice is fully covered). Returns the number of period rows."""
    tx = _TEXT["en" if lang != "fa" else "fa"]
    wb = Workbook()
    ws = wb.active
    ws.title = tx["data"]
    ws.sheet_view.rightToLeft = lang == "fa"
    heads = [tx["period"], tx["start"], tx["end"]] + [f"{sp.label(lang)}\n[{TS.unit_text(sp.unit, lang, plant)}]" for sp in specs]
    for j, h in enumerate(heads, 1):
        c = ws.cell(row=1, column=j, value=h)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 48
    ws.cell(row=2, column=1, value=tx["key"]).font = KEY_FONT
    for j, sp in enumerate(specs, 4):
        ws.cell(row=2, column=j, value=sp.key).font = KEY_FONT
    for i, s in enumerate(slices):
        r = FIRST_DATA_ROW + i
        ws.cell(row=r, column=1, value=s.label + ("  *" if s.partial else ""))
        ws.cell(row=r, column=2, value=s.start.isoformat())
        ws.cell(row=r, column=3, value=s.end.isoformat())
        for j, sp in enumerate(specs, 4):
            pts = plant.series.get(sp.key)
            if not pts:
                continue
            v, cov = TS.value_in(pts, s.start, s.end, sp.agg)
            if v is not None and cov >= 0.999:
                c = ws.cell(row=r, column=j, value=round(v, 6))
                c.number_format = "#,##0.00"
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    for j in range(4, 4 + len(specs)):
        ws.column_dimensions[get_column_letter(j)].width = 22
    ws.freeze_panes = ws.cell(row=FIRST_DATA_ROW, column=4)
    g = wb.create_sheet(tx["guide"])
    g.sheet_view.rightToLeft = lang == "fa"
    for i, line in enumerate(tx["lines"], 1):
        c = g.cell(row=i, column=1, value=line)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 1:
            c.font = Font(bold=True, size=13)
    g.column_dimensions["A"].width = 110
    wb.save(path)
    return len(slices)


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v).strip()[:10])


def _as_float(v) -> Optional[float]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(",", "").replace("٫", ".").strip())


def import_template(plant: Plant, path: str) -> Tuple[int, List[str]]:
    """Read a filled template. Returns (values imported, problems). Blank cells are skipped."""
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    key_row = next((i for i, r in enumerate(rows[:6]) if r and str(r[0] or "").strip().lower() == "key"), None)
    if key_row is None:
        return 0, ["no key row"]
    keys = [str(k).strip() if k else "" for k in rows[key_row]]
    ok, bad = 0, []
    for ri in range(key_row + 1, len(rows)):
        r = rows[ri]
        if not r or (len(r) < 3) or r[1] in (None, "") or r[2] in (None, ""):
            continue
        try:
            a, b = _as_date(r[1]), _as_date(r[2])
            if b < a:
                raise ValueError
        except (ValueError, TypeError):
            bad.append(f"{ri + 1}: {r[1]} .. {r[2]}")
            continue
        for ci in range(3, min(len(r), len(keys))):
            if not keys[ci] or r[ci] in (None, ""):
                continue
            try:
                v = _as_float(r[ci])
                if v is None or TS.spec_of(plant, keys[ci]) is None:
                    raise ValueError
            except ValueError:
                bad.append(f"{ri + 1}:{ci + 1} {keys[ci]} = {r[ci]}")
                continue
            TS.put(plant, keys[ci], a, b, v)
            ok += 1
    return ok, bad
