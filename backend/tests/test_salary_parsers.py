"""Los parsers de salario de Tecnoempleo e Indeed son distintos A PROPÓSITO (cada portal publica
el salario con un formato distinto). Estos tests fijan su comportamiento actual para que
cualquier unificación futura sea una decisión consciente y no un cambio silencioso."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.indeed import _parse_salary as parse_indeed  # noqa: E402
from scraper.tecnoempleo import _parse_salary as parse_tecnoempleo  # noqa: E402


@pytest.mark.parametrize("text, expected", [
    ("30.000 - 40.000 €", (30000, 40000)),
    ("30.000€ – 40.000€", (30000, 40000)),
    ("30000-40000", (30000, 40000)),
    ("35.000 €", (None, None)),        # Tecnoempleo exige un rango
    ("Hasta 45.000", (None, None)),
    ("Competitivo", (None, None)),
    ("", (None, None)),
])
def test_tecnoempleo(text, expected):
    assert parse_tecnoempleo(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("30.000 € - 40.000 € al año", (30000, 40000)),
    ("30.000 € a 40.000 € por año", (30000, 40000)),
    ("35.000 €", (35000, None)),       # Indeed admite una cifra suelta
    ("2.000 € al mes", (24000, None)),  # mensual → anual
    ("1.500 - 2.000 € al mes", (18000, 24000)),
    ("15 € la hora", (26400, None)),    # por hora → anual (1.760 h)
    ("Competitivo", (None, None)),
    ("", (None, None)),
])
def test_indeed(text, expected):
    assert parse_indeed(text) == expected
