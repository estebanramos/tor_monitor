"""Helpers: country flag and flag formatting."""
from __future__ import annotations

import pycountry


def country_flag(cc: str) -> str:
    """'DE' -> 🇩🇪 (regional-indicator letters); anything else -> 🏳."""
    if len(cc) != 2 or not cc.isalpha():
        return "🏳"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc.upper())


def fmt_flags(flags: list[str]) -> str:
    return ",".join(flags) if flags else "-"


def country_name(cc: str) -> str:
    c = pycountry.countries.get(alpha_2=cc.upper()) if len(cc) == 2 else None
    return c.name if c else "Desconocido"
