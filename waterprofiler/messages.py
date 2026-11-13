"""Persian versions of the engine's English error and warning messages.

The engine raises plain English text (stable for tests and for developers).
``localize`` turns the known messages into Persian for the user interface and
reports; anything it does not recognise is returned unchanged.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_NAMES = {
    "hours_per_year": "ساعت کار در سال", "load_fraction": "ضریب بار", "tonnage": "ظرفیت برج (kW تبرید)",
    "delta_t_c": "اختلاف دمای ورودی و خروجی", "recycled_fraction": "کسر بازچرخانی",
    "units_per_year": "تعداد واحد تولید", "water_use_per_unit_m3": "مصرف آب به ازای هر واحد",
    "consumed_in_product_per_unit_m3": "آب در هر واحد محصول", "employees": "تعداد کارکنان",
    "days_per_year": "روز کاری در سال", "litres_per_employee_day": "لیتر به ازای هر نفر در روز",
    "area_m2": "مساحت", "depth_mm_per_year": "عمق آبیاری", "bhp": "ظرفیت بخار بویلر (kg/h)",
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
     lambda m: "بویلر: بخار نامی بویلر (kg/h) را وارد کنید."),
    (re.compile(r"^give bhp or rated_steam_kg_per_h$"),
     lambda m: "بخار نامی بویلر (kg/h) را وارد کنید."),
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
    (re.compile(r"^Sources without a meter while others have one: (.+); their allocated volume is used in the plant balance$"),
     lambda m: f"منابع بدون کنتور در حالی که منابع دیگر کنتور دارند: {m[1]}؛ در بیلان کارخانه از حجم تخصیص‌یافته به آن‌ها استفاده شد."),
    (re.compile(r"^Outlets without a meter while others have one: (.+); their allocated volume is used in the plant balance$"),
     lambda m: f"مقصدهای بدون کنتور در حالی که مقصدهای دیگر کنتور دارند: {m[1]}؛ در بیلان کارخانه از حجم تخصیص‌یافته به آن‌ها استفاده شد."),
    (re.compile(r"^Plant boundary imbalance (.+) m3 is larger than 2 sigma \((.+) m3\): .*$"),
     lambda m: f"ناترازی مرز کارخانه ({m[1]} مترمکعب) از ۲σ ({m[2]} مترمکعب) بزرگ‌تر است؛ خطای کنتورها به‌تنهایی آن را توضیح نمی‌دهد "
               "(نشتی، جریان بی‌کنتور یا خطای کنتور)."),
    (re.compile(r"^Reconciliation: the balance cannot be closed within the limits.*$"),
     lambda m: "تطبیق داده: بیلان در محدودهٔ مجاز تغییر بسته نمی‌شود؛ داده‌ها با هم تناقض دارند (احتمالاً یک کنتور یا یک جریان اشتباه است)."),
    (re.compile(r"^Reconciliation: weighted sum of squares (.+) exceeds the 95 % limit (.+) for (\d+) constraints.*$"),
     lambda m: f"تطبیق داده: مجموع مربعات وزنی ({m[1]}) از حد ۹۵٪ ({m[2]}) برای {m[3]} قید بیشتر است؛ اصلاح‌ها از عدم‌قطعیت اعلام‌شده بزرگ‌ترند، "
               "نخست جریان‌های فهرست‌شده را بررسی کنید."),
    (re.compile(r"^Reconciliation: (\d+) flow\(s\) moved by more than 3 sigma or by more than half of their value$"),
     lambda m: f"تطبیق داده: {m[1]} جریان بیش از ۳σ یا بیش از نصف مقدارشان تغییر کرد (در جدول با رنگ مشخص شده‌اند)."),
    (re.compile(r"^Source '(.+)': abstraction (.+) m3/year exceeds its permit (.+) m3/year \((.+) %\)$"),
     lambda m: f"منبع «{m[1]}»: برداشت {m[2]} مترمکعب در سال از حداکثر مجاز آن ({m[3]}) بیشتر است ({m[4]}٪)."),
    (re.compile(r"^Source '(.+)': abstraction (.+) m3/year is (.+) % of its permit (.+) m3/year$"),
     lambda m: f"منبع «{m[1]}»: برداشت {m[2]} مترمکعب در سال به {m[3]}٪ حداکثر مجاز ({m[4]}) رسیده است."),
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
