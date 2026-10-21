"""Clasificación por tracks estándar y puntuación del track aislado (parametrizable)."""
import pytest

from automation.filter_engine import classify_track
from automation.generic_filter import isolated_min_score, score_isolated
from search_config import JobHunterConfig

_SCORING = {
    "profile_confidence_threshold": 0.2,
    "keyword_groups": [{"id": "g", "weight": 0.5, "keywords": ["x"]}],
    "location": {"weight": 0.2},
    "experience": {"weight": 0.2},
    "salary": {"weight": 0.1},
}


def _track(id, keywords):
    return {"id": id, "label": {"es": id}, "classify_keywords": keywords}


def _cfg(*tracks, threshold=0.2):
    return JobHunterConfig.model_validate(
        {"scoring": {**_SCORING, "profile_confidence_threshold": threshold}, "tracks": list(tracks)}
    )


def test_un_solo_track_con_aciertos_gana():
    cfg = _cfg(_track("a", ["alfa", "beta"]), _track("b", ["gamma", "delta"]))
    assert classify_track({"title": "puesto alfa"}, cfg) == ("a", 0.5)


def test_empate_bajo_umbral_es_manual_review():
    cfg = _cfg(_track("a", ["alfa", "beta"]), _track("b", ["gamma", "delta"]))
    track, diff = classify_track({"title": "alfa gamma"}, cfg)
    assert track == "manual_review" and diff == 0.0


def test_tres_tracks_gana_el_mejor_si_supera_umbral():
    cfg = _cfg(_track("a", ["a1", "a2", "a3", "a4"]), _track("b", ["b1", "b2"]), _track("c", ["c1", "c2"]))
    # a 1/4=0.25, b 2/2=1.0, c 1/2=0.5 -> compara b y c
    track, diff = classify_track({"title": "a1 b1 b2 c1"}, cfg)
    assert track == "b" and diff == pytest.approx(0.5)
    # b 1/2=0.5, c 1/2=0.5: los dos mejores empatan -> manual_review
    assert classify_track({"title": "b1 c1"}, cfg)[0] == "manual_review"


def test_sin_tracks_estandar_es_manual_review():
    cfg = _cfg()
    assert classify_track({"title": "lo que sea"}, cfg) == ("manual_review", 0.0)


def test_un_solo_track_configurado():
    cfg = _cfg(_track("a", ["alfa"]))
    assert classify_track({"title": "alfa"}, cfg) == ("a", 1.0)
    assert classify_track({"title": "nada"}, cfg) == ("manual_review", 0.0)


def test_track_con_keywords_vacias_nunca_gana():
    cfg = _cfg(_track("vacio", []), _track("a", ["alfa"]))
    assert classify_track({"title": "alfa"}, cfg)[0] == "a"
    assert classify_track({"title": "otra cosa"}, _cfg(_track("vacio", [])))[0] == "manual_review"


def test_empate_de_ratio_en_un_track_gana_el_primero_si_supera_umbral():
    cfg = _cfg(_track("a", ["a1"]), _track("b", ["b1", "b2"]), threshold=0.0)
    assert classify_track({"title": "a1 b1 b2"}, cfg)[0] == "a"


def test_classify_track_usa_la_config_global_por_defecto():
    assert classify_track({"title": "Consultor SAP PS"})[0] == "sap"


def _isolated_cfg():
    track = {
        "id": "bridge",
        "label": {"es": "Puente"},
        "kind": "isolated",
        "isolated": {
            "role_families": {"almacen": ["mozo"]},
            "capital_names": ["zaragoza"],
            "province_regex": "zaragoza",
            "remote_regex": "remot",
            "nationwide_regex": "toda españa",
        },
    }
    return _cfg(track)


def test_track_aislado_parametrizado():
    cfg = _isolated_cfg()
    track = cfg.track("bridge")
    assert isolated_min_score(track) == 0.40
    assert score_isolated({"title": "Mozo de almacén", "location": "Zaragoza"}, track) is not None
    assert score_isolated({"title": "Mozo", "location": "Bilbao"}, track) is None
    # no depende de scoring.location (Villanova) ni de la config global
    assert score_isolated({"title": "Mozo", "location": "Villanova"}, track) is None


def test_track_borrado_no_rompe():
    from automation.cv_selector import cover_template_for, select_cv
    from automation.followup import draft_followup
    assert select_cv("borrado", {}) is None
    assert select_cv(None, {}) is None
    assert select_cv("manual_review", {}) is None
    assert cover_template_for("borrado") == "tech"
    text = draft_followup({"cv_profile": "borrado", "company_name": "X", "job_title": None, "method": "email"},
                          {"summary": {"sap": "Hola. Dos."}})
    assert "Les recuerdo brevemente" not in text


def test_stats_por_track(tmp_path):
    import sqlite3
    from database import get_dashboard_stats, init_db
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    for i, prof in enumerate(["sap", "sap", "ia_dev", None]):
        conn.execute("INSERT INTO applications (id, status, cv_profile) VALUES (?, 'sent', ?)", (f"a{i}", prof))
    assert get_dashboard_stats(conn)["sent_by_track"] == {"sap": 2, "ia_dev": 1}


def test_default_track_id_es_el_primer_estandar_nunca_aislado():
    from automation.cv_selector import default_track_id
    iso = {"id": "puente", "label": {"es": "p"}, "kind": "isolated", "isolated": {"role_families": {"r": ["x"]}}}
    cfg = _cfg(iso, _track("a", ["x"]), _track("b", ["y"]))
    assert default_track_id(cfg) == "a"


def test_default_track_id_legacy_es_ia_dev():
    from automation.cv_selector import default_track_id
    assert default_track_id() == "ia_dev"
