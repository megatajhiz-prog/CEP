"""Jalali (Persian) and Gregorian calendars and period slicing.

Time-series data are stored as intervals with explicit Gregorian start and end dates (inclusive), so the calendar the
user prefers only changes how periods are generated and labelled: months and years of either calendar, or any custom
range cut into monthly or yearly slices (the first and last slice may be partial).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Tuple

JALALI_MONTHS_FA = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
JALALI_MONTHS_EN = ("Farvardin", "Ordibehesht", "Khordad", "Tir", "Mordad", "Shahrivar", "Mehr", "Aban", "Azar", "Dey",
                    "Bahman", "Esfand")
GREGORIAN_MONTHS_FA = ("ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر")
GREGORIAN_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

CALENDARS = ("jalali", "gregorian")
STEPS = ("month", "year")


def g2j(gy: int, gm: int, gd: int) -> Tuple[int, int, int]:
    g_d_m = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def j2g(jy: int, jm: int, jd: int) -> Tuple[int, int, int]:
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    days += (jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    months = (0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    gm = 0
    while gm < 13 and gd > months[gm]:
        gd -= months[gm]
        gm += 1
    return gy, gm, gd


def to_jalali(d: date) -> Tuple[int, int, int]:
    return g2j(d.year, d.month, d.day)


def from_jalali(jy: int, jm: int, jd: int) -> date:
    return date(*j2g(jy, jm, jd))


def is_jalali_leap(jy: int) -> bool:
    return to_jalali(from_jalali(jy, 12, 30)) == (jy, 12, 30)


def jalali_month_days(jy: int, jm: int) -> int:
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_jalali_leap(jy) else 29


def gregorian_month_days(y: int, m: int) -> int:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - date(y, m, 1)).days


def parts(d: date, cal: str) -> Tuple[int, int, int]:
    return to_jalali(d) if cal == "jalali" else (d.year, d.month, d.day)


def make_date(cal: str, y: int, m: int, d: int) -> date:
    """Date from calendar parts; the day is clipped to the month length."""
    if cal == "jalali":
        d = min(max(d, 1), jalali_month_days(y, m))
        return from_jalali(y, m, d)
    d = min(max(d, 1), gregorian_month_days(y, m))
    return date(y, m, d)


def month_days(cal: str, y: int, m: int) -> int:
    return jalali_month_days(y, m) if cal == "jalali" else gregorian_month_days(y, m)


def month_name(cal: str, m: int, lang: str) -> str:
    if cal == "jalali":
        return (JALALI_MONTHS_FA if lang == "fa" else JALALI_MONTHS_EN)[m - 1]
    return (GREGORIAN_MONTHS_FA if lang == "fa" else GREGORIAN_MONTHS_EN)[m - 1]


def format_date(d: date, cal: str) -> str:
    y, m, dd = parts(d, cal)
    return f"{y:04d}/{m:02d}/{dd:02d}" if cal == "jalali" else d.isoformat()


def parse_date(text: str, cal: str) -> date:
    """'1405/03/01' (Jalali) or '2026-05-22' (Gregorian); either separator is accepted."""
    t = text.strip().replace("/", "-").replace(".", "-")
    bits = [int(x) for x in t.split("-")]
    if len(bits) != 3:
        raise ValueError(text)
    return make_date(cal, *bits) if cal == "jalali" else date(*bits)


@dataclass(frozen=True)
class Slice:
    start: date
    end: date                      # inclusive
    label: str
    partial: bool                  # shorter than the calendar month / year it belongs to

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _month_bounds(cal: str, d: date) -> Tuple[date, date]:
    y, m, _ = parts(d, cal)
    return make_date(cal, y, m, 1), make_date(cal, y, m, month_days(cal, y, m))


def _year_bounds(cal: str, d: date) -> Tuple[date, date]:
    y, _m, _ = parts(d, cal)
    return make_date(cal, y, 1, 1), make_date(cal, y, 12, month_days(cal, y, 12))


def slices(start: date, end: date, step: str = "month", cal: str = "jalali", lang: str = "fa") -> List[Slice]:
    """Cut [start, end] into calendar months or years. The first and last slice are clipped to the range."""
    if end < start:
        raise ValueError("end before start")
    if step not in STEPS or cal not in CALENDARS:
        raise ValueError("bad step or calendar")
    out: List[Slice] = []
    cur = start
    while cur <= end:
        lo, hi = (_month_bounds if step == "month" else _year_bounds)(cal, cur)
        s, e = max(lo, cur), min(hi, end)
        y, m, _ = parts(cur, cal)
        label = (f"{month_name(cal, m, lang)} {y}" if step == "month" else f"{y}")
        out.append(Slice(s, e, label, (s, e) != (lo, hi)))
        cur = hi + timedelta(days=1)
    return out


def iso(d: date) -> str:
    return d.isoformat()


def from_iso(s: str) -> date:
    return date.fromisoformat(s)
