import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import country_flag, country_name, fmt_flags


def test_country_flag():
    assert country_flag("DE") == "\U0001F1E9\U0001F1EA"
    assert country_flag("de") == country_flag("DE")
    assert country_flag("??") == "\U0001F3F3"


def test_country_name():
    assert country_name("CZ") == "Czechia"
    assert country_name("??") == "Desconocido"
    assert country_name("") == "Desconocido"


def test_fmt_flags():
    assert fmt_flags(["Exit", "Fast"]) == "Exit,Fast"
    assert fmt_flags([]) == "-"
