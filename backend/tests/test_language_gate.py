"""Filtro de idiomas: exige un idioma que no tienes → reject; más nivel del tuyo → flag."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from automation import language_gate as lg  # noqa: E402
from automation.filter_engine import score_offer  # noqa: E402


@pytest.fixture(autouse=True)
def profile(tmp_path, monkeypatch):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps({"languages": [
        {"language": "Español", "level": "Nativo"},
        {"language": "Inglés", "level": "B2"},
        {"language": "Italiano", "level": "A2 (Básico)"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(lg, "PROFILE_PATH", p)
    lg.candidate_languages.cache_clear()
    yield
    lg.candidate_languages.cache_clear()


def _gate(description, title="SAP FI Consultant"):
    return lg.language_gate({"title": title, "description": description})


def test_perfil_se_lee_con_niveles():
    assert lg.candidate_languages() == {"español": 7, "inglés": 4, "italiano": 2}


@pytest.mark.parametrize("desc", [
    "Requisitos: alemán fluido y 2 años de SAP FI.",
    "Fluent German is required.",
    "Imprescindible francés C1.",
    "Nivel alto de neerlandés.",
])
def test_idioma_exigido_que_no_tienes_rechaza(desc):
    verdict, reasons = _gate(desc)
    assert verdict == "reject"
    assert reasons and reasons[0].startswith("idioma: exige")


@pytest.mark.parametrize("desc", [
    "Se valorará alemán.",
    "German is a plus.",
    "Inglés B2 obligatorio.",
    "Clientes en Alemania y Francia.",
    "Trabajarás con equipos alemanes.",
    "Spanish native speaker.",
    "",
])
def test_no_rechaza(desc):
    assert _gate(desc)[0] == "ok"


def test_mas_nivel_del_tuyo_solo_avisa():
    verdict, reasons = _gate("Requisitos: inglés C1 para reuniones con cliente.")
    assert verdict == "flag"
    assert reasons == ["idioma: pide inglés a más nivel del tuyo"]


def test_score_offer_pone_cero_si_rechaza():
    base = {"title": "Consultor SAP S/4HANA Public Cloud FI", "location": "Villanova",
            "description": "SAP FI, S/4HANA, Fiori."}
    assert score_offer(base) > 0
    assert score_offer({**base, "description": base["description"] + "\nAlemán nativo imprescindible."}) == 0.0


def test_score_offer_no_cambia_con_un_aviso():
    base = {"title": "Consultor SAP S/4HANA Public Cloud FI", "location": "Villanova",
            "description": "SAP FI, S/4HANA, Fiori."}
    flagged = {**base, "description": base["description"] + "\nInglés C1."}
    assert score_offer(flagged) == score_offer(base)


def test_bajo_cabecera_valorable_no_cuenta():
    assert _gate("Requisitos:\n- SAP ABAP\n\nMuy valorable:\n-Catalán fluido.\n-Viajes puntuales")[0] == "ok"
    assert _gate("Esto te hará destacar:\nAlemán C1")[0] == "ok"


def test_cabecera_de_requisitos_tras_valorable_vuelve_a_contar():
    assert _gate("Valorable:\n- Docker\nRequisitos:\n- Alemán C1")[0] == "reject"


def test_alternativa_con_idioma_propio_no_rechaza():
    assert _gate("Idiomas: español o catalán nativo, inglés B2")[0] == "ok"


def test_codigo_mcer_manda_sobre_palabras():
    assert _gate("Nivel alto de inglés (B2).")[0] == "ok"


def _unaccented(s):
    import unicodedata
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()


def test_variantes_sin_tilde_se_generan_solas():
    """Cada variante con tilde se reconoce también escrita sin tilde (texto en inglés o sin acentos)."""
    for canon, variants in lg.LANGUAGES.items():
        for v in variants:
            if v in lg._NO_UNACCENTED:
                continue
            assert _unaccented(v) in variants, (canon, v)


def test_finés_sin_tilde_no_se_confunde_con_fines():
    assert "fines" not in lg.LANGUAGES["finés"]
    assert not list(lg._mentions("a efectos y fines del contrato", lg.LANGUAGES["finés"]))


def test_idioma_sin_tilde_en_el_texto_se_detecta():
    for canon in ("catalán", "alemán", "francés"):
        text = f"{_unaccented(canon).capitalize()} required"
        assert list(lg._mentions(text, lg.LANGUAGES[canon])), canon
