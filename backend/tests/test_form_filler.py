import sys
from pathlib import Path
from config import PROFILE_PATH  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_detect_ats_workday():
    from automation.ats_handlers import detect_ats
    assert detect_ats("https://acme.wd3.myworkdayjobs.com/AcmeCareers/job/123") == "workday"

def test_detect_ats_greenhouse():
    from automation.ats_handlers import detect_ats
    assert detect_ats("https://boards.greenhouse.io/acme/jobs/789") == "greenhouse"

def test_detect_ats_lever():
    from automation.ats_handlers import detect_ats
    assert detect_ats("https://jobs.lever.co/globex/123abc") == "lever"

def test_detect_ats_successfactors():
    from automation.ats_handlers import detect_ats
    assert detect_ats("https://globex.jobs.eu2.successfactors.eu/job/123") == "successfactors"
    assert detect_ats("https://jobs.sap.com/careers/job/123") == "successfactors"

def test_detect_ats_successfactors_sapsf_domain():
    # career55.sapsf.eu is the real hostname SAP uses for many SuccessFactors
    # career portals (e.g. Initech's) — found via a live test link, was misrouted
    # to "generic" before this pattern was added.
    from automation.ats_handlers import detect_ats
    assert detect_ats(
        "https://career55.sapsf.eu/portalcareer?company=examplesite&navBarLevel=MY_PROFILE"
    ) == "successfactors"
    assert detect_ats("https://career5.sapsf.com/careers?company=example") == "successfactors"

def test_detect_ats_generic_fallback():
    from automation.ats_handlers import detect_ats
    assert detect_ats("https://www.acme.com/trabaja/apply") == "generic"

def test_map_field_email():
    from automation.ats_handlers.generic import _map_field
    profile = {"personal": {"name": "Juan García", "email": "juan@example.com", "phone": "+34 600 000 000", "linkedin": "https://linkedin.com/in/juan"}}
    assert _map_field("email", profile) == "juan@example.com"

def test_map_field_first_and_last_name():
    from automation.ats_handlers.generic import _map_field
    profile = {"personal": {"name": "Juan García", "email": "j@e.com", "phone": "", "linkedin": ""}}
    assert _map_field("first_name", profile) == "Juan"
    assert _map_field("last_name", profile) == "García"

def test_map_field_unknown_returns_none():
    from automation.ats_handlers.generic import _map_field
    profile = {"personal": {"name": "Juan García", "email": "j@e.com", "phone": "", "linkedin": ""}}
    assert _map_field("random_unknown_field_xyz", profile) is None

def test_workday_handler_importable():
    from automation.ats_handlers.workday import fill_workday
    assert callable(fill_workday)

def test_greenhouse_handler_importable():
    from automation.ats_handlers.greenhouse import fill_greenhouse
    assert callable(fill_greenhouse)

def test_lever_handler_importable():
    from automation.ats_handlers.lever import fill_lever
    assert callable(fill_lever)

def test_successfactors_handler_importable():
    from automation.ats_handlers.successfactors import fill_successfactors
    assert callable(fill_successfactors)

def test_successfactors_never_declares_submit_labels_as_next():
    from automation.ats_handlers.successfactors import _SUBMIT_LABELS, _NEXT_LABELS, _LOGIN_LABELS
    assert not set(_SUBMIT_LABELS) & set(_NEXT_LABELS)
    assert not set(_SUBMIT_LABELS) & set(_LOGIN_LABELS)
    assert "Submit" in _SUBMIT_LABELS
    assert "Enviar" in _SUBMIT_LABELS
    assert "Entrar" in _LOGIN_LABELS

def test_maybe_login_does_nothing_without_env_credentials(monkeypatch):
    import asyncio
    from automation.ats_handlers.successfactors import _maybe_login
    monkeypatch.delenv("JOBPORTAL_EMAIL", raising=False)
    monkeypatch.delenv("JOBPORTAL_PASSWORD", raising=False)
    # page is never touched when credentials are absent — None is safe here.
    assert asyncio.run(_maybe_login(None)) is False

def test_successfactors_resolve_reads_nested_profile_paths():
    from automation.ats_handlers.successfactors import _resolve
    profile = {
        "personal": {"first_name": "Ana", "dni_nie": "12345678Z"},
        "availability": {"start_date": "2026-09-22"},
    }
    assert _resolve(profile, ("personal", "first_name")) == "Ana"
    assert _resolve(profile, ("personal", "dni_nie")) == "12345678Z"
    assert _resolve(profile, ("availability", "start_date")) == "2026-09-22"
    assert _resolve(profile, ("salary_expectation", "amount")) is None

def test_successfactors_resolve_supports_list_index_paths():
    from automation.ats_handlers.successfactors import _resolve
    profile = {"experience": [{"role": "Consultor SAP", "company": "Initech"}]}
    assert _resolve(profile, ("experience", 0, "role")) == "Consultor SAP"
    assert _resolve(profile, ("experience", 0, "company")) == "Initech"
    assert _resolve(profile, ("experience", 5, "role")) is None  # out of range -> None, no crash

def test_map_field_covers_new_successfactors_style_fields():
    from automation.ats_handlers.generic import _map_field
    profile = {
        "personal": {
            "name": "Ana Ejemplo Prueba", "first_name": "Ana", "last_name": "Ejemplo Prueba",
            "email": "j@e.com", "phone": "", "linkedin": "", "dni_nie": "12345678Z",
            "address": "Calle Falsa 1", "city": "Villanova", "postal_code": "99001", "country": "España",
        },
        "availability": {"start_date": "2026-09-22"},
        "salary_expectation": {"amount": None},
    }
    assert _map_field("national_id_number", profile) == "12345678Z"
    assert _map_field("home address", profile) == "Calle Falsa 1"
    assert _map_field("city", profile) == "Villanova"
    assert _map_field("postal_code", profile) == "99001"
    assert _map_field("country", profile) == "España"
    assert _map_field("earliest_available_start_date", profile) == "2026-09-22"
    assert _map_field("salary_pretension", profile) == ""  # no amount set -> blank, never guessed

def test_map_field_current_position_and_company_from_first_experience():
    from automation.ats_handlers.generic import _map_field
    profile = {
        "personal": {"name": "Ana Ejemplo Prueba"},
        "experience": [{"role": "Consultor SAP", "company": "Initech España"}],
    }
    assert _map_field("professional_experiences[0][position]", profile) == "Consultor SAP"
    assert _map_field("professional_experiences[0][company_name]", profile) == "Initech España"

def test_map_field_birth_date():
    from automation.ats_handlers.generic import _map_field
    profile = {"personal": {"name": "Ana", "birth_date": "1990-01-01"}}
    assert _map_field("fecha_nacimiento", profile) == "1990-01-01"

def test_map_field_availability_end_date_never_gets_start_date_value():
    from automation.ats_handlers.generic import _map_field
    profile = {
        "personal": {"name": "Ana"},
        "availability": {"start_date": "2026-09-22"},
    }
    assert _map_field("availability_init_date", profile) == "2026-09-22"
    assert _map_field("availability_end_date", profile) is None
    assert _map_field("disponibilidad_hasta", profile) is None

def test_fill_form_accepts_headless_and_pause_for_review_kwargs():
    from automation.form_filler import fill_form
    import json
    profile = json.loads(PROFILE_PATH.read_text())
    # dry_run short-circuits before touching the browser, so this must not hang.
    result = fill_form(
        "https://boards.greenhouse.io/acme/jobs/123",
        profile, None, "Test cover letter",
        dry_run=True, headless=False, pause_for_review=True,
    )
    assert result is True

def test_fill_forms_importable():
    from automation.application_engine import fill_forms
    assert callable(fill_forms)

def test_workday_never_declares_submit_labels_as_next():
    from automation.ats_handlers.workday import _SUBMIT_LABELS, _NEXT_LABELS
    assert not set(_SUBMIT_LABELS) & set(_NEXT_LABELS)
    assert "Submit" in _SUBMIT_LABELS
    assert "Next" in _NEXT_LABELS

def test_workday_fields_use_shared_map_field_hints():
    # Every hint fed to _map_field must resolve to a real canonical field —
    # if not, it's a typo that would silently fill nothing forever.
    from automation.ats_handlers.workday import _FIELDS
    from automation.ats_handlers.generic import _map_field
    profile = {
        "personal": {
            "name": "Ana Ejemplo Prueba", "first_name": "Ana", "last_name": "Ejemplo Prueba",
            "email": "j@e.com", "phone": "+34 600000000", "linkedin": "https://linkedin.com/in/j",
            "address": "Calle Falsa 1", "city": "Villanova", "postal_code": "99001", "country": "España",
        },
    }
    for _automation_id, hint in _FIELDS:
        assert _map_field(hint, profile), f"hint {hint!r} resolved to nothing"

def test_greenhouse_never_auto_submits():
    import inspect
    from automation.ats_handlers import greenhouse
    src = inspect.getsource(greenhouse.fill_greenhouse)
    assert "submit.click()" not in src
    assert "return True" not in src

def test_lever_never_auto_submits():
    import inspect
    from automation.ats_handlers import lever
    src = inspect.getsource(lever.fill_lever)
    assert "submit.click()" not in src
    assert "return True" not in src

def test_workday_never_clicks_a_submit_label_button():
    # The Next-loop legitimately clicks buttons to advance the wizard; only
    # the tail segment (after entering the _SUBMIT_LABELS loop) must contain
    # no click() call — just detection + logging.
    import inspect
    from automation.ats_handlers import workday
    src = inspect.getsource(workday.fill_workday)
    tail = src.split("for btn_text in _SUBMIT_LABELS:")[1]
    assert "btn.click()" not in tail
    assert "NO se pulsa" in tail
