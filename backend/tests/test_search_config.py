"""Esquema y carga de jobhunter.yaml (search_config)."""
import re
from pathlib import Path

import pytest

import search_config
from search_config import ConfigError, JobHunterConfig, load_config

FIXTURES = Path(__file__).parent / "fixtures"
TEST_CONFIG = FIXTURES / "config_test.yaml"
DEFAULTS = Path(search_config.__file__).parent / "defaults" / "jobhunter.yaml"


def _write(tmp_path, text: str) -> Path:
    p = tmp_path / "jobhunter.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_default_config_es_valida_y_generica():
    cfg = load_config(DEFAULTS)
    assert isinstance(cfg, JobHunterConfig)
    assert cfg.scoring.location.city is None
    for group in cfg.scoring.keyword_groups:
        assert not any("sap" in kw.lower() for kw in group.keywords)
    for track in cfg.tracks:
        assert not any("sap" in kw.lower() for kw in track.classify_keywords)
    assert cfg.track("developer") is not None
    assert sum(g.weight for g in cfg.scoring.keyword_groups) == pytest.approx(0.6)


def test_config_test_reproduce_valores_esperados():
    cfg = load_config(TEST_CONFIG)
    groups = {g.id: g for g in cfg.scoring.keyword_groups}
    assert groups["core_skills"].weight == 0.35
    assert "s/4hana" in groups["core_skills"].keywords
    assert groups["stack"].weight == 0.20
    assert cfg.scoring.location.city == "villanova"
    assert cfg.scoring.salary.min_base == 22000
    assert [t.id for t in cfg.standard_tracks()] == ["ia_dev", "sap"]
    assert [t.id for t in cfg.isolated_tracks()] == ["generic"]
    assert cfg.track("generic").isolated.min_score == 0.40
    assert cfg.track("nope") is None


def test_track_aislado_es_autocontenido():
    # Las constantes de generic_filter ya no existen: el track aislado vive entero en la config.
    cfg = load_config(TEST_CONFIG)
    rules = cfg.track("generic").isolated
    for text in (rules.exclude_title_regex, rules.exclude_text_regex, rules.exclude_lang_regex,
                 rules.province_regex, rules.remote_regex, rules.nationwide_regex):
        re.compile(text, re.IGNORECASE)
    assert rules.province_regex == "villanova|vilanova"
    assert rules.capital_names == ["villanova", "villanova capital"]
    # province_towns = scoring.location.area seguido de los municipios extra de la provincia
    area = cfg.scoring.location.area
    assert rules.province_towns[:len(area)] == area
    assert rules.province_towns[len(area):][0] == "alto verde" and rules.province_towns[-1] == "bajo pinar"
    assert len(rules.province_towns) == len(area) + 7
    assert set(rules.role_families) == {
        "atencion_cliente", "aeropuerto", "administrativo", "hosteleria_retail", "baja_cualificacion"}
    assert rules.min_score == 0.40


def test_scoring_y_clasificacion_de_la_config_de_test():
    # Las constantes de scoring y clasificación viven solo en la config.
    cfg = load_config(TEST_CONFIG)
    assert cfg.scoring.profile_confidence_threshold == 0.2
    assert cfg.scoring.negative_title_keywords == ["director", "cto", "ceo"]
    assert "+10 años" in cfg.scoring.negative_keywords
    assert len(cfg.track("sap").classify_keywords) == 21
    assert len(cfg.track("ia_dev").classify_keywords) == 25


_BASE = """
scoring:
  keyword_groups:
    - {id: a, weight: 0.5, keywords: [x]}
  location: {weight: 0.2}
  experience: {weight: 0.2}
  salary: {weight: 0.1}
tracks:
  - {id: dev, label: {es: Dev, en: Dev}}
"""


def test_base_minima_es_valida(tmp_path):
    assert load_config(_write(tmp_path, _BASE)).track("dev") is not None


def test_pesos_que_no_suman_uno_falla(tmp_path):
    p = _write(tmp_path, _BASE.replace("weight: 0.5", "weight: 0.6"))
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert str(p) in str(e.value)
    assert "scoring" in str(e.value)


def test_id_de_track_repetido_falla(tmp_path):
    p = _write(tmp_path, _BASE + "  - {id: dev, label: {es: Otro, en: Other}}\n")
    with pytest.raises(ConfigError, match="dev"):
        load_config(p)


def test_manual_review_reservado(tmp_path):
    p = _write(tmp_path, _BASE.replace("id: dev", "id: manual_review"))
    with pytest.raises(ConfigError, match="manual_review"):
        load_config(p)


def test_track_aislado_sin_reglas_falla(tmp_path):
    p = _write(tmp_path, _BASE + "  - {id: puente, label: {es: P, en: P}, kind: isolated}\n")
    with pytest.raises(ConfigError, match="puente"):
        load_config(p)


def test_yaml_invalido_da_error_legible(tmp_path):
    p = _write(tmp_path, "scoring: [unclosed\n")
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert str(p) in str(e.value)

    p2 = _write(tmp_path, _BASE.replace("location: {weight: 0.2}", "location: {weight: 0.2, ciudad: x}"))
    with pytest.raises(ConfigError) as e2:
        load_config(p2)
    assert str(p2) in str(e2.value)
    assert "scoring.location.ciudad" in str(e2.value)


def test_regex_invalida_falla(tmp_path):
    txt = _BASE + "  - {id: g, label: {es: G, en: G}, kind: isolated, isolated: {role_families: {a: [x]}, remote_regex: '(' }}\n"
    with pytest.raises(ConfigError, match="remote_regex"):
        load_config(_write(tmp_path, txt))


def test_load_usa_jh_home_si_existe_y_defaults_si_no(tmp_path, monkeypatch):
    monkeypatch.setattr(search_config, "JH_HOME", tmp_path)
    assert load_config().track("developer") is not None
    _write(tmp_path, _BASE)
    assert load_config().track("dev") is not None


def test_set_get_reload_config(tmp_path, monkeypatch):
    monkeypatch.setattr(search_config, "JH_HOME", tmp_path)
    cfg = load_config(TEST_CONFIG)
    search_config.set_config(cfg)
    try:
        assert search_config.get_config() is cfg
        _write(tmp_path, _BASE)
        assert search_config.reload_config().track("dev") is not None
        assert search_config.get_config().track("dev") is not None
    finally:
        search_config.set_config(load_config(TEST_CONFIG))


@pytest.mark.parametrize("bad_id", ["Foo", "1a", "SAP", "a b"])
def test_formato_de_id_de_track_invalido_falla(tmp_path, bad_id):
    p = _write(tmp_path, _BASE.replace("id: dev", f"id: '{bad_id}'"))
    with pytest.raises(ConfigError) as e:
        load_config(p)
    msg = str(e.value)
    assert str(p) in msg
    assert "tracks" in msg
    assert bad_id in msg
    assert "^[a-z][a-z0-9_]*$" in msg


def test_experience_scores_parcial_se_completa_con_defaults(tmp_path):
    from automation.filter_engine import score_offer

    p = _write(tmp_path, _BASE.replace("experience: {weight: 0.2}", "experience: {weight: 0.2, scores: {junior: 0.9}}"))
    cfg = load_config(p)
    assert cfg.scoring.experience.scores == {"junior": 0.9, "mid": 0.5, "senior": 0.0, "lead": 0.0, "unknown": 0.5}
    score_offer({"title": "Dev", "description": "", "location": "Remoto"}, cfg=cfg)  # no KeyError


def test_experience_scores_con_nivel_desconocido_falla(tmp_path):
    p = _write(tmp_path, _BASE.replace("experience: {weight: 0.2}", "experience: {weight: 0.2, scores: {expert: 1.0}}"))
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert "experience.scores" in str(e.value)
    assert "expert" in str(e.value)
