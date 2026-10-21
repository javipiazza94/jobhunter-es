"""Validación estricta de jobhunter.yaml: errores en la carga, no a mitad de un scraping."""
import pytest

from automation.cv_selector import cv_tag_key
from automation.filter_engine import classify_track
from automation.generic_filter import score_isolated
from search_config import ConfigError, JobHunterConfig, load_config

_SCORING = {
    "keyword_groups": [{"id": "g", "weight": 0.5, "keywords": ["x"]}],
    "location": {"weight": 0.2},
    "experience": {"weight": 0.2},
    "salary": {"weight": 0.1},
}


def _cfg(*tracks, scoring=None):
    return JobHunterConfig.model_validate({"scoring": scoring or _SCORING, "tracks": list(tracks)})


def _isolated(**overrides):
    rules = {"role_families": {"r": ["mozo"]}, "capital_names": ["zaragoza"], "remote_regex": "remoto|teletrabajo"}
    rules.update(overrides)
    return {"id": "bridge", "label": {"es": "P"}, "kind": "isolated", "isolated": rules}


def _write(tmp_path, text):
    p = tmp_path / "jobhunter.yaml"
    p.write_text(text, encoding="utf-8")
    return p


# --- 3. minúsculas -------------------------------------------------------------------------------

def test_classify_keywords_con_mayusculas_clasifican():
    cfg = _cfg({"id": "dev", "label": {"es": "D"}, "classify_keywords": ["Python", "Developer"]})
    assert cfg.track("dev").classify_keywords == ["python", "developer"]
    assert classify_track({"title": "Python Developer"}, cfg)[0] == "dev"


def test_search_keywords_se_conservan_tal_cual():
    cfg = _cfg({"id": "dev", "label": {"es": "D"}, "search_keywords": ["SAP S/4HANA"],
                "remote_search_keywords": ["Python"]})
    assert cfg.track("dev").search_keywords == ["SAP S/4HANA"]


def test_capital_names_con_mayusculas_acepta_la_ciudad():
    track = _cfg(_isolated(capital_names=["Zaragoza"])).track("bridge")
    assert score_isolated({"title": "Mozo de almacén", "location": "Zaragoza"}, track) is not None


def test_role_families_province_towns_y_reject_levels_en_minusculas():
    rules = _cfg(_isolated(role_families={"r": ["Mozo"]}, province_towns=["Utebo"],
                           reject_levels=["Senior"])).track("bridge").isolated
    assert rules.role_families == {"r": ["mozo"]}
    assert rules.province_towns == ["utebo"] and rules.reject_levels == ["senior"]


# --- 4. diccionarios parciales -------------------------------------------------------------------

def test_location_scores_parcial_se_fusiona_con_los_defaults():
    rules = _cfg(_isolated(location_scores={"capital": 0.9})).track("bridge").isolated
    assert rules.location_scores == {"capital": 0.9, "nationwide": 0.8, "province": 0.7, "unknown": 0.5}


def test_salary_scores_parcial_se_fusiona_con_los_defaults():
    rules = _cfg(_isolated(salary_scores={"above": 0.9})).track("bridge").isolated
    assert rules.salary_scores == {"above": 0.9, "below": 0.3, "unknown": 0.5}


@pytest.mark.parametrize("field", ["location_scores", "salary_scores", "weights"])
def test_claves_desconocidas_se_rechazan(field):
    with pytest.raises(ValueError, match="desconocid"):
        _cfg(_isolated(**{field: {"typo": 0.1}}))


def test_weights_parcial_se_fusiona_y_debe_sumar_uno():
    rules = _cfg(_isolated(weights={"role": 0.45, "recency": 0.10})).track("bridge").isolated
    assert rules.weights == {"role": 0.45, "location": 0.25, "experience": 0.15, "salary": 0.05, "recency": 0.10}
    with pytest.raises(ValueError, match="sumar"):
        _cfg(_isolated(weights={"role": 0.9}))


def test_recency_vacia_se_rechaza():
    with pytest.raises(ValueError, match="recency"):
        _cfg(_isolated(recency=[]))


def test_recency_se_ordena_por_dias_ascendentes():
    rules = _cfg(_isolated(recency=[[60, 0.3], [14, 1.0], [30, 0.7]])).track("bridge").isolated
    assert rules.recency == [(14, 1.0), (30, 0.7), (60, 0.3)]


# --- 5. regex de tag_patterns --------------------------------------------------------------------

def test_tag_pattern_con_regex_invalida_falla_al_cargar():
    track = {"id": "dev", "label": {"es": "D"},
             "cv": {"tag_patterns": [{"tag": "FI", "regex": "(sin cerrar"}]}}
    with pytest.raises(ValueError, match="expresión regular inválida"):
        _cfg(track)


def test_tag_pattern_valida_funciona_en_select_cv():
    track = _cfg({"id": "dev", "label": {"es": "D"},
                  "cv": {"tag_patterns": [{"tag": "FI", "regex": r"\bfi\b"}]}}).track("dev")
    assert cv_tag_key(track, None, "Consultor FI") == "FI"


# --- menores -------------------------------------------------------------------------------------

def test_id_de_track_con_salto_de_linea_se_rechaza():
    with pytest.raises(ValueError, match="id de track inválido"):
        _cfg({"id": "dev\n", "label": {"es": "D"}})


def test_pesos_negativos_se_rechazan():
    scoring = {**_SCORING, "keyword_groups": [{"id": "g", "weight": 0.9, "keywords": ["x"]}],
               "location": {"weight": -0.2}}
    with pytest.raises(ValueError):
        _cfg({"id": "dev", "label": {"es": "D"}}, scoring=scoring)
    with pytest.raises(ValueError):
        _cfg(_isolated(weights={"role": -0.1, "location": 0.45, "experience": 0.15, "salary": 0.05, "recency": 0.46}))


def test_ids_de_keyword_groups_duplicados_se_rechazan():
    scoring = {**_SCORING, "keyword_groups": [
        {"id": "g", "weight": 0.25, "keywords": ["x"]}, {"id": "g", "weight": 0.25, "keywords": ["y"]}]}
    with pytest.raises(ValueError, match="repetido"):
        _cfg({"id": "dev", "label": {"es": "D"}}, scoring=scoring)


def test_fichero_no_utf8_es_config_error(tmp_path):
    p = tmp_path / "jobhunter.yaml"
    p.write_bytes("scoring: {x: 'año'}\n".encode("latin-1"))
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert str(p) in str(e.value)


def test_priority_max_years_obsoleto_se_ignora_con_aviso(tmp_path, caplog):
    experience = {"weight": 0.2, "priority_max_years": 2}
    caplog.set_level("WARNING")
    cfg = _cfg({"id": "dev", "label": {"es": "D"}}, scoring={**_SCORING, "experience": experience})
    assert not hasattr(cfg.scoring.experience, "priority_max_years")
    assert "priority_max_years" in caplog.text
