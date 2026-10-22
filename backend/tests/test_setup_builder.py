"""Asistente de primer arranque: respuestas → profile.json + jobhunter.yaml válidos."""
import json
import math

import pytest

import config
import search_config
import setup_builder
from automation import language_gate
from automation.profile_proposal import EligibilityDraft, LanguageDraft, ProfileDraft, TargetDraft
from search_config import AISettings, load_config
from setup_builder import SetupAnswers, apply_setup, build_config, build_profile, load_markets

_TRACK_ID = r"^[a-z][a-z0-9_]*$"


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    """Perfil y config en una carpeta temporal; restaura el estado exacto de la config activa."""
    profile = tmp_path / "profile.json"
    monkeypatch.setattr(config, "PROFILE_PATH", profile)
    monkeypatch.setattr(language_gate, "PROFILE_PATH", profile)
    monkeypatch.setattr(config, "JH_HOME", tmp_path)
    saved = (search_config._cache, search_config._pinned, search_config._loaded_from)
    language_gate.candidate_languages.cache_clear()
    yield
    search_config._cache, search_config._pinned, search_config._loaded_from = saved
    language_gate.candidate_languages.cache_clear()


def _draft(**kw) -> ProfileDraft:
    base = dict(
        full_name="Ana Prueba Ejemplo",
        email="ana@example.com",
        phone="+34 600 000 000",
        city="Villanova",
        country="España",
        targets=[
            TargetDraft(title="Data Engineer", keywords=["data engineer", "etl", "spark"]),
            TargetDraft(title="Backend Developer", keywords=["backend", "python", "etl"]),
        ],
        years_experience=3,
        tools=["Python", "SQL", "Docker"],
        languages=[LanguageDraft(language="English", level="B2"), LanguageDraft(language="Deutsch", level="A2")],
        modality=["remote", "hybrid"],
        eligibility=EligibilityDraft(work_permit_countries=["ES"], needs_sponsorship=False, driving_license=True),
    )
    base.update(kw)
    return ProfileDraft(**base)


def _answers(**kw) -> SetupAnswers:
    base = dict(
        draft=_draft(),
        markets=["spain"],
        sources=["tecnoempleo", "manfred"],
        acknowledged_sources=[],
        followed_companies=["Acme Robotics", "Globex Data"],
        ai=AISettings(provider="ollama"),
    )
    base.update(kw)
    return SetupAnswers(**base)


def _weights_total(cfg) -> float:
    s = cfg.scoring
    return sum(g.weight for g in s.keyword_groups) + s.location.weight + s.experience.weight + s.salary.weight


def test_two_targets_two_tracks_three_groups_weights_sum_one():
    cfg = build_config(_answers())
    assert [t.id for t in cfg.tracks] == ["data_engineer", "backend_developer"]
    assert all(t.kind == "standard" for t in cfg.tracks)
    assert [g.id for g in cfg.scoring.keyword_groups] == ["data_engineer", "backend_developer", "tools"]
    assert math.isclose(_weights_total(cfg), 1.0, abs_tol=1e-9)
    base = load_config(search_config.DEFAULT_CONFIG_PATH).scoring
    assert cfg.scoring.location.weight == base.location.weight
    assert cfg.scoring.experience.weight == base.experience.weight
    assert cfg.scoring.salary.weight == base.salary.weight
    weights = [g.weight for g in cfg.scoring.keyword_groups]
    assert max(weights) - min(weights) < 1e-6  # reparto a partes iguales


def test_track_fields_from_target():
    cfg = build_config(_answers())
    t = cfg.track("data_engineer")
    assert t.label == {"es": "Data Engineer", "en": "Data Engineer"}
    assert t.classify_keywords == ["data engineer", "etl", "spark"]
    assert t.search_keywords == ["data engineer", "etl", "spark"]
    assert [(c.name, c.tier) for c in t.followed_companies] == [("Acme Robotics", 1), ("Globex Data", 1)]
    assert cfg.track("backend_developer").followed_companies == t.followed_companies
    assert cfg.scoring.keyword_groups[-1].keywords == ["python", "sql", "docker"]
    assert cfg.scoring.location.city == "Villanova"
    assert cfg.ai.provider == "ollama"


@pytest.mark.parametrize("n", [1, 3, 6, 7])
def test_weights_exact_for_awkward_counts(n):
    targets = [TargetDraft(title=f"Rol {i}", keywords=[f"kw{i}"]) for i in range(n)]
    cfg = build_config(_answers(draft=_draft(targets=targets)))
    assert math.isclose(_weights_total(cfg), 1.0, abs_tol=1e-9)
    assert len(cfg.scoring.keyword_groups) == n + 1


def test_unicode_duplicate_blank_reserved_titles_give_valid_unique_ids():
    targets = [
        TargetDraft(title="Ingeniería de Datos", keywords=["datos"]),
        TargetDraft(title="Ingeniería  de   datos!", keywords=["datos2"]),
        TargetDraft(title="   ", keywords=["sin título"]),
        TargetDraft(title="数据工程师", keywords=["data"]),
        TargetDraft(title="3D Artist", keywords=["blender"]),
        TargetDraft(title="Manual Review", keywords=["qa"]),
        TargetDraft(title="Tools", keywords=["tools"]),
    ]
    cfg = build_config(_answers(draft=_draft(targets=targets)))
    ids = [t.id for t in cfg.tracks]
    assert len(ids) == len(set(ids)) == 7
    assert ids[0] == "ingenieria_de_datos" and ids[1] == "ingenieria_de_datos_2"
    import re
    assert all(re.fullmatch(_TRACK_ID, i) for i in ids)
    assert "manual_review" not in ids
    group_ids = [g.id for g in cfg.scoring.keyword_groups]
    assert len(group_ids) == len(set(group_ids))
    assert all(t.label["es"].strip() for t in cfg.tracks)  # el título vacío recibe una etiqueta legible
    assert math.isclose(_weights_total(cfg), 1.0, abs_tol=1e-9)


def test_target_without_keywords_uses_title():
    cfg = build_config(_answers(draft=_draft(targets=[TargetDraft(title="QA Engineer", keywords=[])])))
    assert cfg.track("qa_engineer").search_keywords == ["QA Engineer"]
    assert cfg.track("qa_engineer").classify_keywords == ["qa engineer"]


def test_no_tools_skips_tools_group():
    cfg = build_config(_answers(draft=_draft(tools=[])))
    assert [g.id for g in cfg.scoring.keyword_groups] == ["data_engineer", "backend_developer"]
    assert math.isclose(_weights_total(cfg), 1.0, abs_tol=1e-9)


def test_no_targets_raises():
    with pytest.raises(ValueError):
        build_config(_answers(draft=_draft(targets=[])))
    with pytest.raises(ValueError):
        build_config(_answers(draft=_draft(targets=[TargetDraft(title="  ", keywords=[])])))


def test_sources_keywords_union_and_requires_ack_dropped_without_ack():
    cfg = build_config(_answers(sources=["tecnoempleo", "infojobs", "linkedin", "nope"]))
    assert set(cfg.sources) == {"tecnoempleo"}
    assert cfg.sources["tecnoempleo"]["keywords"] == ["data engineer", "etl", "spark", "backend", "python"]
    cfg2 = build_config(_answers(sources=["tecnoempleo", "infojobs", "linkedin"],
                                 acknowledged_sources=["infojobs", "linkedin"]))
    assert set(cfg2.sources) == {"tecnoempleo", "infojobs", "linkedin"}
    searches = cfg2.sources["linkedin"]["searches"]
    assert {s["track"] for s in searches} == {"data_engineer", "backend_developer"}


def test_markets_only_list_existing_sources():
    runnable = {"tecnoempleo", "infojobs", "manfred", "computrabajo", "indeed", "linkedin"}
    markets = load_markets()
    assert set(markets) == {"spain", "latam", "remote", "global"}
    for sources in markets.values():
        for s in sources:
            assert s["id"] in runnable
            assert set(s) >= {"id", "label", "requires_ack", "default_on"}
            if s["requires_ack"]:
                assert s["default_on"] is False
    linkedin = next(s for s in markets["global"] if s["id"] == "linkedin")
    assert linkedin["requires_ack"] is True


def test_build_profile_shape():
    p = build_profile(_answers())
    assert p["personal"]["name"] == "Ana Prueba Ejemplo"
    assert p["personal"]["first_name"] == "Ana"
    assert p["personal"]["last_name"] == "Prueba Ejemplo"
    assert p["personal"]["email"] == "ana@example.com"
    assert p["personal"]["city"] == "Villanova"
    assert p["personal"]["driving_license"] is True
    assert p["stack"]["other_tools"] == ["Python", "SQL", "Docker"]
    assert p["availability"]["work_mode_preference"] == "remoto, híbrido"
    assert p["eligibility"] == {"work_permit_countries": ["ES"], "needs_sponsorship": False, "driving_license": True}
    assert p["languages"][0] == {"language": "Inglés", "level": "B2"}


def test_apply_setup_writes_valid_files_and_languages_reach_gate(tmp_path):
    answers = _answers(draft=_draft(languages=[
        LanguageDraft(language="English", level="C1"),
        LanguageDraft(language="Deutsch", level="A2"),
        LanguageDraft(language="Klingon", level="native"),
    ]))
    result = apply_setup(answers)
    assert result == {"tracks": ["data_engineer", "backend_developer"], "sources": ["tecnoempleo", "manfred"]}
    cfg = load_config(tmp_path / "jobhunter.yaml")
    assert [t.id for t in cfg.tracks] == ["data_engineer", "backend_developer"]
    assert math.isclose(_weights_total(cfg), 1.0, abs_tol=1e-9)
    assert json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))["personal"]["city"] == "Villanova"
    language_gate.candidate_languages.cache_clear()
    langs = language_gate.candidate_languages()
    assert langs["inglés"] == 5 and langs["alemán"] == 2 and langs["español"] == 7


def test_apply_setup_without_targets_raises_and_writes_nothing(tmp_path):
    with pytest.raises(ValueError):
        apply_setup(_answers(draft=_draft(targets=[])))
    assert not (tmp_path / "jobhunter.yaml").exists()
    assert not (tmp_path / "profile.json").exists()


def _good_offer(cfg, track_id: str, city: str) -> dict:
    kws = cfg.track(track_id).search_keywords
    return {"title": cfg.track(track_id).label["es"], "description": " ".join(kws[: min(3, len(kws))]),
            "location": city or "remoto"}


@pytest.mark.parametrize("with_tools", [True, False])
@pytest.mark.parametrize("n", range(1, 8))
@pytest.mark.parametrize("title_only", [False, True])
def test_min_relevance_calibrated_good_match_relevant_unrelated_not(n, with_tools, title_only):
    from automation.filter_engine import score_offer

    targets = [TargetDraft(title=f"Rol{i} Engineer", keywords=[f"kwa{i}", f"kwb{i}", f"kwc{i}", f"kwd{i}"])
               for i in range(n)]
    if title_only:
        targets[-1] = TargetDraft(title="Solo Titulo Analyst", keywords=[])
    cfg = build_config(_answers(draft=_draft(targets=targets, tools=["Python", "SQL"] if with_tools else [])))
    base = load_config(search_config.DEFAULT_CONFIG_PATH).scoring
    assert 0.2 <= cfg.scoring.min_relevance <= base.min_relevance
    for t in cfg.tracks:
        assert score_offer(_good_offer(cfg, t.id, "Villanova"), cfg) >= cfg.scoring.min_relevance, t.id
    unrelated = {"title": "Camarero", "description": "", "location": "Villanova"}
    assert score_offer(unrelated, cfg) < cfg.scoring.min_relevance


def test_calibration_restores_config_state():
    before = (search_config._cache, search_config._pinned, search_config._loaded_from)
    build_config(_answers())
    assert (search_config._cache, search_config._pinned, search_config._loaded_from) == before


def test_profile_eligibility_wiring_rejects_us_only_offer():
    from automation.eligibility_gate import eligibility_gate

    p = build_profile(_answers())
    assert p["personal"]["work_permit"] is True
    assert p["personal"]["country_code"] == "ES"
    assert p["personal"]["nationality"] == ""
    offer = {"title": "Backend Developer",
             "description": "You must be authorized to work in the US without sponsorship."}
    verdict, reasons = eligibility_gate(offer, profile_data=p)
    assert verdict == "reject", reasons


@pytest.mark.parametrize("country,code,permits,expected", [
    ("México", "MX", ["MX"], False),
    ("United Kingdom", "GB", [], None),
    ("Atlantis", "", ["España"], True),
])
def test_profile_country_code_and_work_permit(country, code, permits, expected):
    draft = _draft(country=country, eligibility=EligibilityDraft(work_permit_countries=permits))
    p = build_profile(_answers(draft=draft))
    assert p["personal"]["country_code"] == code
    assert p["personal"]["work_permit"] is expected
    assert p["personal"]["work_permit_countries"] == permits


def test_build_profile_guarda_cv_path_si_viene():
    assert build_profile(_answers(cv_path="cv/cv_ana.pdf"))["cv_path"] == "cv/cv_ana.pdf"
    assert "cv_path" not in build_profile(_answers())


@pytest.mark.parametrize("bad", ["/etc/passwd", "../cv/x.pdf", "cv/../profile.json", "cv/sub/x.pdf", "otro/x.pdf"])
def test_cv_path_solo_acepta_un_fichero_dentro_de_cv(bad):
    with pytest.raises(ValueError):
        _answers(cv_path=bad)


def test_cv_path_es_el_cv_por_defecto_de_cada_track():
    cfg = build_config(_answers(cv_path="cv/cv_ana.pdf"))
    assert [t.cv.default for t in cfg.standard_tracks()] == ["cv/cv_ana.pdf"] * 2
    assert all(t.cv.default is None for t in build_config(_answers()).tracks)


def test_reaplicar_asistente_conserva_email_de_la_config_del_usuario(tmp_path):
    from search_config import EmailSettings
    apply_setup(_answers())
    path = tmp_path / "jobhunter.yaml"
    cfg = load_config(path)
    custom = EmailSettings(preset="custom", smtp_host="smtp.villanova.example", smtp_port=465, use_starttls=False)
    search_config.save_config(cfg.model_copy(update={"email": custom}), path)
    apply_setup(_answers(ai=AISettings(provider="openai")))
    again = load_config(path)
    assert again.email == custom
    assert again.ai.provider == "openai"


def test_keyword_hit_es_publico_y_conserva_el_alias():
    from automation import filter_engine
    assert filter_engine.keyword_hit("sql", "experto en sql y python")
    assert not filter_engine.keyword_hit("sql", "nosqlite")
    assert filter_engine._kw_hit is filter_engine.keyword_hit


# ── Volver a pasar el asistente no pierde datos ─────────────────────────────────


def _rich_profile() -> dict:
    """Perfil «de toda la vida» con claves que el asistente no pregunta."""
    return {
        "personal": {"name": "Ana Prueba Ejemplo", "email": "ana@example.com", "city": "Ciudad Vieja",
                     "linkedin": "https://www.linkedin.com/in/ana-prueba/", "dni_nie": "00000000T",
                     "nationality": "Villanovense", "postal_code": "00000"},
        "availability": {"work_mode_preference": "presencial", "notice_period": "15 días"},
        "salary_expectation": {"amount": 30000, "currency": "EUR", "period": "annual_gross"},
        "summary": {"general": "Ingeniera de datos con foco en ETL."},
        "cover_letter_intro": "Me interesa {company_name}.",
        "cv_sap_path": "./cv/cv_sap.pdf",
        "cv_general_path": "./cv/cv_general.pdf",
        "education": [{"title": "Grado", "institution": "Universidad de Villanova", "start": "2015", "end": "2019"}],
        "stack": {"programming": ["Python", "Go"], "data": ["Spark"], "other_tools": ["Excel"]},
        "experience": [{"company": "Acme Robotics", "role": "Data Engineer", "start": "2020", "end": "",
                        "description": "ETL", "stack": ["Python"], "achievements": ["Migró el data lake"]}],
        "eligibility": {"work_permit_countries": ["ES"], "needs_sponsorship": False, "notes": "UE"},
    }


def test_reaplicar_asistente_conserva_lo_que_el_asistente_no_pregunta(tmp_path):
    from profile_store import load_profile, save_profile

    save_profile(_rich_profile())
    exp = [{"company": "Acme Robotics", "role": "Data Engineer", "start": "2020", "end": "",
            "description": "ETL y streaming", "stack": ["Python", "Kafka"]}]
    apply_setup(_answers(draft=_draft(experience=exp)))
    p = load_profile()
    assert p["summary"] == {"general": "Ingeniera de datos con foco en ETL."}
    assert p["cover_letter_intro"] == "Me interesa {company_name}."
    assert p["cv_sap_path"] == "./cv/cv_sap.pdf" and p["cv_general_path"] == "./cv/cv_general.pdf"
    assert p["education"][0]["institution"] == "Universidad de Villanova"
    assert p["stack"]["programming"] == ["Python", "Go"] and p["stack"]["data"] == ["Spark"]
    assert p["stack"]["other_tools"] == ["Python", "SQL", "Docker"]  # lista del asistente: se sustituye
    personal = p["personal"]
    assert personal["city"] == "Villanova"  # lo que pregunta el asistente se actualiza
    assert personal["linkedin"] == "https://www.linkedin.com/in/ana-prueba/" and personal["dni_nie"] == "00000000T"
    assert personal["nationality"] == "Villanovense" and personal["postal_code"] == "00000"
    assert p["availability"] == {"work_mode_preference": "remoto, híbrido", "notice_period": "15 días"}
    assert p["salary_expectation"]["amount"] == 30000
    assert p["eligibility"]["notes"] == "UE" and p["eligibility"]["driving_license"] is True
    assert p["experience"][0]["description"] == "ETL y streaming"
    assert p["experience"][0]["achievements"] == ["Migró el data lake"]


def test_primer_asistente_sin_perfil_previo_da_el_perfil_completo(tmp_path):
    from profile_store import load_profile

    apply_setup(_answers())
    assert load_profile() == build_profile(_answers())


def _isolated_track():
    from search_config import IsolatedRules, Track
    return Track(id="puente", label={"es": "Puente", "en": "Bridge"}, kind="isolated",
                 search_keywords=["dependiente"], isolated=IsolatedRules(role_families={"tienda": ["dependiente"]}))


def test_reaplicar_asistente_conserva_tracks_aislados_y_ajustes_propios(tmp_path):
    from search_config import KeywordGroup

    apply_setup(_answers(sources=["tecnoempleo", "linkedin"], acknowledged_sources=["linkedin"]))
    path = tmp_path / "jobhunter.yaml"
    cfg = load_config(path)
    s = cfg.scoring
    groups = [g.model_copy(update={"weight": round(g.weight * 0.8, 6)}) for g in s.keyword_groups]
    rest = round(1.0 - s.location.weight - s.experience.weight - s.salary.weight - sum(g.weight for g in groups), 6)
    groups.append(KeywordGroup(id="cloud", weight=rest, keywords=["aws", "gcp"]))
    scoring = s.model_copy(update={
        "keyword_groups": groups,
        "negative_keywords": ["prácticas"],
        "location": s.location.model_copy(update={"remote_score": 0.9, "area": ["Villanova Norte"]}),
    })
    sources = dict(cfg.sources)
    sources["tecnoempleo"] = {**sources["tecnoempleo"], "max_pages": 2,
                              "keywords": [*sources["tecnoempleo"]["keywords"], "dbt"]}
    sources["linkedin"] = {**sources["linkedin"], "searches": [
        *sources["linkedin"]["searches"], {"keywords": "dependiente", "location": "Villanova", "track": "puente"}]}
    search_config.save_config(cfg.model_copy(update={
        "scoring": scoring, "tracks": [*cfg.tracks, _isolated_track()], "sources": sources}), path)

    new_targets = [TargetDraft(title="ML Engineer", keywords=["machine learning", "pytorch"])]
    result = apply_setup(_answers(draft=_draft(targets=new_targets), sources=["tecnoempleo", "linkedin"], acknowledged_sources=["linkedin"]))
    again = load_config(path)

    assert result["tracks"] == ["ml_engineer"]  # solo estándar: el aislado no se busca con "Buscar ofertas"

    assert [t.id for t in again.tracks] == ["ml_engineer", "puente"]
    assert again.track("puente").isolated.role_families == {"tienda": ["dependiente"]}
    ids = [g.id for g in again.scoring.keyword_groups]
    assert ids == ["ml_engineer", "tools", "cloud"]  # los grupos de los tracks viejos desaparecen
    assert math.isclose(_weights_total(again), 1.0, abs_tol=1e-9)
    assert again.scoring.negative_keywords == ["prácticas"]
    assert again.scoring.location.remote_score == 0.9 and again.scoring.location.area == ["Villanova Norte"]
    assert again.scoring.location.city == "Villanova"
    tecno = again.sources["tecnoempleo"]
    assert tecno["max_pages"] == 2
    assert tecno["keywords"] == ["machine learning", "pytorch", "dbt"]  # las del asistente se regeneran
    searches = again.sources["linkedin"]["searches"]
    assert {s["track"] for s in searches} == {"ml_engineer", "puente"}


def test_reaplicar_asistente_con_config_corrupta_parte_de_los_valores_por_defecto(tmp_path):
    (tmp_path / "jobhunter.yaml").write_text("scoring: [roto\n", encoding="utf-8")
    result = apply_setup(_answers())
    assert result["tracks"] == ["data_engineer", "backend_developer"]


def test_normalize_profile_keeps_manual_code_when_country_blank():
    """Un código puesto a mano no se borra si el país está vacío."""
    from setup_builder import normalize_profile

    out = normalize_profile({"personal": {"country": "", "country_code": "FR"}})
    assert out["personal"]["country_code"] == "FR"


def test_wizard_config_enables_eligibility_hard_reject(tmp_path):
    cfg = build_config(_answers())
    assert cfg.scoring.eligibility_hard_reject is True
    path = search_config.save_config(cfg, tmp_path / "jobhunter.yaml")
    assert load_config(path).scoring.eligibility_hard_reject is True
