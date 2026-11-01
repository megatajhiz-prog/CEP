# CEPWater — مدیریت مصرف آب کارخانه

محصول **کنترل انرژی پاسارگاد** (Control Energy Pasargad)

Desktop software for industrial plant water management: subsystem water balance,
true cost of water, savings analysis, data reconciliation, Excel and PDF reports.
Bilingual (Persian default, English), right-to-left, offline, Windows installer.

نرم‌افزار دسکتاپ مدیریت مصرف آب کارخانه: بیلان آب زیرسیستم‌ها، هزینهٔ واقعی آب،
تحلیل صرفه‌جویی، تطبیق داده، و خروجی Excel و PDF. دوزبانه، آفلاین، با نصب‌کنندهٔ ویندوز.
روش‌شناسی بر پایهٔ گزارش ORNL/TM-2021/1918.

## نصب (کاربر نهایی) / Install

1. در صفحهٔ **Actions** همین مخزن، آخرین اجرای موفق «Build Windows installer» را باز کنید.
2. از بخش Artifacts فایل **CEPWater-Setup** را دانلود و اجرا کنید.
   (اگر نسخهٔ Release منتشر شده باشد، `CEPWater-Setup-x.y.z.exe` در بخش Releases هم هست.)

## کار با برنامه / Workflow

1. **کارخانه**: منابع آب (با قیمت و کنتور)، مقاصد پساب، تصفیه‌ها، قیمت برق و سوخت.
2. **زیرسیستم‌ها**: برای هر زیرسیستم (فرایند، برج خنک‌کن، بویلر، بهداشتی، فضای سبز، سایر) یا
   «برآورد از روی مشخصات» را بزنید، یا جریان‌های اندازه‌گیری‌شده را مستقیم وارد کنید.
3. **بیلان آب**: تلفات/نشتی احتمالی هر زیرسیستم و مقایسه با کنتور کارخانه.
4. **هزینهٔ واقعی آب**: خرید، تصفیه، پمپاژ، پساب و گرمای هدررفته؛ اولویت‌بندی.
5. **صرفه‌جویی**: افزایش چرخهٔ تغلیظ، بازگشت میعانات، رفع نشتی و دورهٔ بازگشت سرمایه.
6. **تطبیق داده**: اصلاح وزنی جریان‌ها تا بیلان ببندد.

ورود داده از Excel: *پرونده ← ذخیرهٔ الگوی Excel* را بزنید، الگو را پر کنید و با *ورود داده از Excel* بخوانید.

Use *File → Load demo plant* for a worked example. Project files are `.wpj` (JSON).

## Develop

```
pip install -r requirements-dev.txt
python -m pytest            # engine tests + headless GUI tests
python -m waterprofiler     # run the app
build\build_windows.bat     # Windows: tests + PyInstaller + Inno Setup installer
```

CI (`.github/workflows/build.yml`) runs the tests, builds the executable, self-tests
it, builds the installer, silently installs it and self-tests the installed copy.

* Formulas and corrections to the printed report: [docs/FORMULAS.md](docs/FORMULAS.md)
* Engine: `waterprofiler/` (`estimators`, `balance`, `cost`, `savings`, `reconcile`, `kpi`)
* GUI: `waterprofiler/gui/`  ·  Strings: `waterprofiler/i18n.py`

## Limits

Results are only as good as the inputs: the estimators are rules of thumb from the
ORNL report and should be replaced by metered values where available. Treat the
output as an engineering screening, not a certified audit.

## Water-saving measures (v0.3)

The *Measures database* page lists 80 water-saving measures in 9 groups with screening ranges, investment level and
a plant-specific estimate; *Saving plan* combines the chosen measures without double counting and reports
saving, annual value, I1, I2, LCC and payback. The plan is stored in the project file and exported to Excel and PDF.
