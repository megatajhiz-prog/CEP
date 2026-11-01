"""Persian versions of the engine's English error and warning messages.

The engine raises plain English text (stable for tests and for developers).
``localize`` turns the known messages into Persian for the user interface and
reports; anything it does not recognise is returned unchanged.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_NAMES = {
    "hours_per_year": "ساعت کار در سال", "load_fraction": "ضریب بار", "tonnage": "ظرفیت برج (تن تبرید)",
    "delta_t_c": "اختلاف دمای ورودی و خروجی", "recycled_fraction": "کسر بازچرخانی",
    "units_per_year": "تعداد واحد تولید", "water_use_per_unit_m3": "مصرف آب به ازای هر واحد",
    "consumed_in_product_per_unit_m3": "آب در هر واحد محصول", "employees": "تعداد کارکنان",
    "days_per_year": "روز کاری در سال", "litres_per_employee_day": "لیتر به ازای هر نفر در روز",
    "area_m2": "مساحت", "depth_mm_per_year": "عمق آبیاری", "bhp": "ظرفیت بویلر (BHP)",
}
_LABELS = {"Boiler": "بویلر", "Cooling tower": "برج خنک‌کن"}


def _n(name: str) -> str:
    return _NAMES.get(name, name)


def _l(label: str) -> str:
    return _LABELS.get(label, label)


_RULES: List[Tuple["re.Pattern[str]", object]] = [
    (re.compile(r"^(\w+) must be between 0 and 1, got (.+)$"),
     lambda m: f"«{_n(m[1])}» باید بین ۰ و ۱ باشد (مقدار واردشده: {m[2]})."),
    (re.compile(r"^(\w+) must be >= 0, got (.+)$"),
     lambda m: f"«{_n(m[1])}» نمی‌تواند منفی باشد (مقدار واردشده: {m[2]})."),
    (re.compile(r"^(.+): conductivities must be > 0$"),
     lambda m: f"{_l(m[1])}: هدایت الکتریکی‌ها باید بزرگ‌تر از صفر باشند."),
    (re.compile(r"^(.+): cycles of concentration must be > 1 \(got ([\d.]+)\).*$"),
     lambda m: (f"{_l(m[1])}: چرخهٔ تغلیظ باید بزرگ‌تر از ۱ باشد (محاسبه‌شده: {m[2]}). "
                "بررسی کنید هدایت بلودان از هدایت مرجع (آب جبرانی یا آب تغذیه) بیشتر باشد.")),
    (re.compile(r"^Boiler: give bhp or rated_steam_kg_per_h$"),
     lambda m: "بویلر: ظرفیت بویلر (BHP) یا بخار نامی (kg/h) را وارد کنید."),
    (re.compile(r"^give bhp or rated_steam_kg_per_h$"),
     lambda m: "ظرفیت بویلر (BHP) یا بخار نامی (kg/h) را وارد کنید."),
    (re.compile(r"^Boiler: feedwater conductivity cannot exceed makeup conductivity.*$"),
     lambda m: "بویلر: هدایت آب تغذیه نمی‌تواند از هدایت آب جبرانی بیشتر باشد (سهم آب جبرانی بیش از ۱۰۰٪ می‌شود)."),
    (re.compile(r"^new cycles of concentration must be > 1$"),
     lambda m: "چرخهٔ تغلیظ جدید باید بزرگ‌تر از ۱ باشد."),
    (re.compile(r"^condensate return must be between 0 and 100 ?%$"),
     lambda m: "بازگشت میعانات باید بین ۰ و ۱۰۰ درصد باشد."),
    (re.compile(r"^no estimator for subsystem type '(.+)'$"),
     lambda m: f"برای نوع زیرسیستم «{m[1]}» برآوردگری وجود ندارد."),
    (re.compile(r"^unknown (source|outlet|treatment): (.+)$"),
     lambda m: {"source": "منبع", "outlet": "مقصد", "treatment": "تصفیه"}[m[1]] + f"ِ «{m[2]}» تعریف نشده است."),
    (re.compile(r"^(.+): intake from unknown source '(.+)'$"),
     lambda m: f"{m[1]}: برداشت از منبعی که تعریف نشده است («{m[2]}»)."),
    (re.compile(r"^(.+): discharge to unknown outlet '(.+)'$"),
     lambda m: f"{m[1]}: تخلیه به مقصدی که تعریف نشده است («{m[2]}»)."),
    (re.compile(r"^Inter-subsystem transfers do not cancel \(sent minus received = (.+) m3\).*$"),
     lambda m: f"ارسال و دریافت آب بین زیرسیستم‌ها یک‌دیگر را خنثی نمی‌کنند (ارسالی منهای دریافتی = {m[1]} مترمکعب)؛ "
               "مقدارهای «ارسال به زیرسیستم دیگر» و «دریافت از زیرسیستم دیگر» را بررسی کنید."),
    (re.compile(r"^(.+): unknown treatment '(.+)'$"),
     lambda m: f"{m[1]}: تصفیه‌ای که تعریف نشده است («{m[2]}»)."),
    (re.compile(r"^(.+): treated fraction for '(.+)' is (.+), expected 0\.\.1$"),
     lambda m: f"{m[1]}: کسر تصفیه‌شده برای «{m[2]}» برابر {m[3]} است؛ باید بین ۰ و ۱ باشد."),
]


def localize(msg: str, lang: str) -> str:
    """Return ``msg`` in Persian when ``lang`` is 'fa' and the message is a known one."""
    if lang != "fa":
        return msg
    text = str(msg).strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "'\"":   # str(KeyError('x')) is quoted
        text = text[1:-1]
    for pat, fn in _RULES:
        m = pat.match(text)
        if m:
            return fn(m)
    return msg


def localize_all(msgs, lang: str) -> List[str]:
    return [localize(m, lang) for m in msgs]
