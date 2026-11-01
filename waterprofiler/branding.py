"""Product and company identity used by the window, the About box and the reports."""

from __future__ import annotations

import os
import sys

APP_NAME = "CEPWater"
APP_SUBTITLE = {"fa": "مدیریت هوشمند مصرف آب کارخانه", "en": "Industrial plant water management"}
COMPANY = {"fa": "کنترل انرژی پاسارگاد", "en": "Control Energy Pasargad"}
TAGLINE = {"fa": "تجهیزات اندازه‌گیری، پایش و کالیبراسیون", "en": "Measuring, monitoring and calibration equipment"}

# Contact details shown in the About box and report footer when filled in.
CONTACT = {"phone": "", "email": "", "website": "", "address_fa": "", "address_en": ""}

# Colours sampled from the company logo.
NAVY = "#0B3D78"
BLUE = "#0A74C8"
BLUE_DARK = "#0858A6"
GREEN = "#2E9E4B"
LEAF = "#5DAA28"


def resource_dir() -> str:
    base = getattr(sys, "_MEIPASS", None)          # PyInstaller bundle
    return base or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset(*parts: str) -> str:
    return os.path.join(resource_dir(), "assets", *parts)


def logo_path(kind: str = "full") -> str:
    return asset("brand", "logo_mark.png" if kind == "mark" else "logo_full.png")


def contact_lines(lang: str):
    c = CONTACT
    out = []
    if c["address_" + ("fa" if lang == "fa" else "en")]:
        out.append(c["address_" + ("fa" if lang == "fa" else "en")])
    for k in ("phone", "email", "website"):
        if c[k]:
            out.append(c[k])
    return out
