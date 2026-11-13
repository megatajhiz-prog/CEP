"""Static guards for GUI code that cannot run where PySide6 is missing."""

import pathlib
import re

from waterprofiler.i18n import all_keys, missing_translations

ROOT = pathlib.Path(__file__).resolve().parent.parent / "waterprofiler"


def _sources():
    return list((ROOT / "gui").glob("*.py")) + [ROOT / "app.py", ROOT / "export_xlsx.py", ROOT / "report_html.py"]


def test_literal_translation_keys_exist():
    keys = set(all_keys())
    missing = []
    for f in _sources():
        for m in re.finditer(r"""\bt\(\s*["']([A-Za-z0-9_ ]+)["']\s*[,)]""", f.read_text(encoding="utf-8")):
            if m.group(1) not in keys:
                missing.append((f.name, m.group(1)))
    assert not missing, missing


def test_dynamic_translation_families_complete():
    keys = set(all_keys())
    families = {
        "kind_": ["process", "cooling_tower", "boiler", "sanitary", "irrigation", "other"],
        "comp_": ["intake", "water_treatment", "pumping", "wastewater_treatment", "discharge", "heat"],
        "pr_": ["both", "volume", "cost", "low"],
        "st_": ["balanced", "unaccounted loss", "excess outflow"],
    }
    for pre, vals in families.items():
        assert [v for v in vals if pre + v not in keys] == []


def test_all_strings_have_both_languages():
    assert missing_translations() == []


def test_brand_assets_and_name():
    import os
    from waterprofiler import branding
    assert branding.APP_NAME == "Watra"
    for k in ("full", "mark"):
        assert os.path.getsize(branding.logo_path(k)) > 5000
    for f in ("app.ico", "chevron.png"):
        assert os.path.exists(branding.asset("brand", f))
