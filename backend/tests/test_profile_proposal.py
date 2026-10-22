"""Tests de la propuesta de perfil a partir del texto de un CV (proveedor de IA simulado)."""
from ai import AIError, AIUnavailable
from ai.base import NoneProvider
from automation.profile_proposal import ProfileDraft, propose_profile

CV = "Ada Villanova\nIngeniera de robótica en Acme Robotics (2019-2024). Python, ROS."


class FakeProvider:
    name = "fake"

    def __init__(self, data=None, error=None):
        self.data, self.error, self.calls = data, error, []

    def generate_json(self, prompt, schema, system=None):
        self.calls.append((prompt, schema, system))
        if self.error:
            raise self.error
        return self.data

    def generate_text(self, prompt, system=None):
        raise AssertionError("no debe usarse")

    def check(self):
        return True, "ok"


GOOD = {
    "full_name": "Ada Villanova",
    "email": "ada@example.com",
    "city": "Villanova",
    "targets": [{"title": "Ingeniera de robótica", "keywords": ["ROS"]}],
    "years_experience": 5,
    "experience": [{"company": "Acme Robotics", "role": "Ingeniera", "start": "2019",
                    "end": "2024", "description": "x", "stack": ["Python"]}],
    "tools": ["Python", "ROS"],
    "languages": [{"language": "Español", "level": "native"}, {"language": "Inglés", "level": "B2"}],
    "modality": ["remote", "hybrid"],
    "eligibility": {"work_permit_countries": ["ES"], "needs_sponsorship": False},
}


def test_proposal_with_ai():
    prov = FakeProvider(GOOD)
    draft, source = propose_profile(CV, prov)
    assert source == "ai"
    assert draft.full_name == "Ada Villanova"
    assert draft.targets[0].title == "Ingeniera de robótica"
    assert draft.experience[0].company == "Acme Robotics"
    assert draft.modality == ["remote", "hybrid"]
    assert draft.eligibility.needs_sponsorship is False
    prompt, schema, system = prov.calls[0]
    assert "Acme Robotics" in prompt
    assert "never invent" in system.lower() or "no inventes" in system.lower()
    assert "targets" in schema["required"]


def test_invalid_level_and_modality_dropped():
    data = dict(GOOD, languages=[{"language": "Inglés", "level": "fluent"},
                                 {"language": "Francés", "level": "b1"}],
                modality=["remote", "teletrabajo"])
    draft, source = propose_profile(CV, FakeProvider(data))
    assert source == "ai"
    assert [(x.language, x.level) for x in draft.languages] == [("Francés", "B1")]
    assert draft.modality == ["remote"]


def test_garbage_types_do_not_raise():
    data = {"full_name": 5, "targets": "x", "years_experience": "mucho", "tools": None}
    draft, source = propose_profile(CV, FakeProvider(data))
    assert isinstance(draft, ProfileDraft)
    assert source in ("ai", "empty")


def test_ai_error_gives_empty_draft():
    draft, source = propose_profile(CV, FakeProvider(error=AIError("boom")))
    assert source == "empty"
    assert draft == ProfileDraft()


def test_unavailable_gives_empty_draft():
    _, source = propose_profile(CV, FakeProvider(error=AIUnavailable("no")))
    assert source == "empty"


def test_none_provider_gives_empty_draft():
    draft, source = propose_profile(CV, NoneProvider())
    assert (draft, source) == (ProfileDraft(), "empty")


def test_default_provider_from_config(monkeypatch):
    monkeypatch.setattr("automation.profile_proposal.get_provider", lambda: NoneProvider())
    assert propose_profile(CV)[1] == "empty"


def test_blank_cv_skips_ai():
    prov = FakeProvider(GOOD)
    assert propose_profile("   ", prov)[1] == "empty"
    assert prov.calls == []


def test_cv_truncated():
    prov = FakeProvider(GOOD)
    propose_profile("x" * 50_000, prov)
    assert len(prov.calls[0][0]) < 21_000


def test_native_level_variants_kept():
    data = dict(GOOD, languages=[{"language": "Español", "level": "Native"},
                                 {"language": "Euskera", "level": "Nativo"}])
    draft, _ = propose_profile(CV, FakeProvider(data))
    assert [x.level for x in draft.languages] == ["native", "native"]


def test_years_variants():
    for raw in ("5 años", "5 years", 5.0, "5"):
        draft, _ = propose_profile(CV, FakeProvider(dict(GOOD, years_experience=raw)))
        assert draft.years_experience == 5, raw
    draft, _ = propose_profile(CV, FakeProvider(dict(GOOD, years_experience="mucho")))
    assert draft.years_experience is None


def test_error_message_not_logged(caplog):
    import logging

    with caplog.at_level(logging.DEBUG):
        propose_profile(CV, FakeProvider(error=AIError("Ada Villanova secreto")))
    assert "secreto" not in caplog.text and "AIError" in caplog.text


def test_partial_json_from_real_provider_keeps_ai_source():
    """Un modelo que solo devuelve algunas claves no debe descartar la propuesta: el resto, por defecto."""
    import json

    from ai.base import BaseProvider

    class PartialProvider(BaseProvider):
        name = "partial"

        def _complete(self, prompt, system, json_mode):
            return json.dumps({"full_name": "Ada Villanova", "targets": [{"title": "Ingeniera de robótica"}]})

    draft, source = propose_profile(CV, PartialProvider())
    assert source == "ai"
    assert draft.full_name == "Ada Villanova"
    assert draft.targets[0].title == "Ingeniera de robótica"
    assert draft.email == "" and draft.languages == [] and draft.years_experience is None
