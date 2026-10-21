"""Una sola definición de modalidad: dashboard, scoring y salario deben coincidir."""
import pytest

from automation.filter_engine import _location_score
from automation.location import in_target_area, parse_modality
from automation.salary import classify_offer_location


@pytest.mark.parametrize("location, title, expected", [
    ("Remoto", None, "remoto"),
    ("Madrid", "Arquitecto técnico (Java/IA) - Remoto", "remoto"),  # el título cuenta para «remoto»
    ("Teletrabajo", None, "remoto"),
    ("Madrid (Híbrido) y remoto ocasional", None, "hibrido"),       # híbrido gana a remoto
    ("Galicia (remoto/hibrido)", None, "hibrido"),
    ("Barcelona - presencial o remoto", None, "presencial"),        # presencial explícito gana a remoto
    ("Villanova", None, "presencial"),
    ("Valencia", None, "presencial"),
    ("", None, None),
    (None, None, None),
])
def test_parse_modality(location, title, expected):
    assert parse_modality(location, title) == expected


def test_hibrido_en_el_titulo_no_cambia_la_modalidad():
    # Solo la ubicación decide híbrido/presencial; el título solo aporta «remoto».
    assert parse_modality("Madrid", "Consultor (híbrido)") == "presencial"


@pytest.mark.parametrize("location", ["Madrid (Híbrido) y remoto ocasional", "Barcelona - presencial o remoto"])
def test_remoto_ambiguo_no_es_remoto_para_salario_ni_scoring(location):
    assert classify_offer_location(location) == "onsite_elsewhere"
    assert _location_score(location) < 1.0


def test_scoring_ubicacion():
    assert _location_score("") == 0.5
    assert _location_score("Remoto") == 1.0
    assert _location_score("Teletrabajo") == 1.0
    assert _location_score("Villanova") == 1.0
    assert _location_score("Villanova (Híbrido)") == 1.0
    assert _location_score("Madrid (Híbrido)") == 0.7
    assert _location_score("Madrid") == 0.6


def test_target_area():
    assert in_target_area("Valdemar")
    assert in_target_area("Villanova (Híbrido)")
    assert not in_target_area("Madrid")
    assert not in_target_area(None)
