"""Ampliar perfil: propuestas con fuente (GitHub por API, otras páginas por IA), nada guardado hasta aceptar,
fusión sin duplicados. Sin red: la lectura de páginas está simulada."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import config  # noqa: E402
from ai import AIError  # noqa: E402
from automation import expand_profile as ex  # noqa: E402
from automation import fetch_page  # noqa: E402
from tests.asgi_client import call  # noqa: E402

H = [("x-jh-client", "dashboard"), ("content-type", "application/json")]
PROFILE = {"personal": {"name": "Ana Test", "email": "ana.test@example.com"}, "stack": {"programming": ["Python"]},
           "skills": ["SQL"], "certifications": ["AWS Cloud Practitioner"]}
GH = "https://github.com/ana-test"
API = "https://api.github.com/users/ana-test/repos?per_page=100&sort=pushed"
REPOS = json.dumps([
    {"name": "robot", "language": "Rust", "topics": ["robotics", "embedded"], "fork": False},
    {"name": "web", "language": "Rust", "topics": [], "fork": False},
    {"name": "libpy", "language": "Python", "topics": ["hacktoberfest", "dotfiles"], "fork": False},
    {"name": "copia", "language": "Go", "topics": ["golang"], "fork": True},  # fork: no cuenta
])


class Fake:
    def __init__(self, data=None, exc=None, name="fake"):
        self.name, self.data, self.exc, self.calls = name, data, exc, []

    def generate_json(self, prompt, schema, system=None):
        self.calls.append(prompt)
        if self.exc:
            raise self.exc
        return self.data


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "profile.json")
    (tmp_path / "profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    pages = {API: REPOS}
    fetched = []

    def fake_fetch(url, timeout=None):
        fetched.append(url)
        page = pages.get(url, RuntimeError("HTTP 404"))
        if isinstance(page, Exception):
            raise page
        return page

    monkeypatch.setattr(ex, "fetch_html", fake_fetch)
    return pages, fetched, tmp_path / "profile.json"


def test_github_por_api_con_fuente_y_sin_conocidos(env):
    res = ex.propose([GH], provider=Fake(name="none"))
    names = {p["name"]: p for p in res["proposals"]}
    assert set(names) == {"Rust", "robotics", "embedded"}  # Python ya está en el perfil; el fork no cuenta
    assert all(p["source_url"] == GH for p in res["proposals"])
    assert "2 repositorio(s)" in names["Rust"]["evidence"]
    assert res["errors"] == []


def test_proponer_no_guarda_nada(env):
    _, _, profile_path = env
    before = profile_path.read_text(encoding="utf-8")
    ex.propose([GH])
    assert profile_path.read_text(encoding="utf-8") == before


def test_github_sin_api_cae_a_la_pagina_con_ia(env):
    pages, fetched, _ = env
    pages[API] = fetch_page.RobotsRefused(API)
    pages[GH] = "<html><body>Ana Test. Desarrolladora con Terraform y Kubernetes.</body></html>"
    ai = Fake(data={"skills": [{"name": "Terraform", "evidence": "Cita el perfil"}, {"name": "Cobol", "evidence": "inventado"}]})
    res = ex.propose([GH], provider=ai)
    assert [p["name"] for p in res["proposals"]] == ["Terraform"]  # Cobol no aparece en la página: se descarta
    assert res["proposals"][0]["source_url"] == GH and fetched == [API, GH]
    assert "<pagina>" in ai.calls[0]


def test_pagina_ajena_sin_ia_da_error_claro(env):
    pages, _, _ = env
    pages["https://ana.example/cv"] = "<p>Docker</p>"
    res = ex.propose(["https://ana.example/cv"], provider=Fake(name="none"))
    assert res["proposals"] == [] and "IA" in res["errors"][0]["error"]


def test_errores_por_fuente_no_cortan_el_resto(env):
    pages, _, _ = env
    pages["https://ok.example/"] = "<p>Experiencia con Terraform</p>"
    ai = Fake(data={"skills": [{"name": "Terraform", "evidence": "x"}]})
    res = ex.propose(["ftp://malo.example", "https://roto.example/", "https://ok.example/"], provider=ai)
    assert [p["name"] for p in res["proposals"]] == ["Terraform"]
    assert [e["url"] for e in res["errors"]] == ["ftp://malo.example", "https://roto.example/"]


def test_fallo_de_ia_se_informa(env):
    pages, _, _ = env
    pages["https://ok.example/"] = "<p>Terraform</p>"
    res = ex.propose(["https://ok.example/"], provider=Fake(exc=AIError("x")))
    assert res["proposals"] == [] and "IA" in res["errors"][0]["error"]


def test_github_user():
    assert ex.github_user("https://github.com/ana-test") == "ana-test"
    assert ex.github_user("https://github.com/ana-test/") == "ana-test"
    assert ex.github_user("https://github.com/ana-test/robot") is None
    assert ex.github_user("https://gitlab.com/ana") is None


def test_aceptar_fusiona_sin_duplicados(env):
    _, _, profile_path = env
    items = [{"name": "Rust", "evidence": "2 repos", "source_url": GH}, {"name": "rust", "evidence": "dup"},
             {"name": "python", "evidence": "ya está"}, {"name": "AWS Cloud Practitioner", "evidence": "ya"}]
    res = ex.accept(items)
    assert res == {"added": ["Rust"], "skipped": ["rust", "python", "AWS Cloud Practitioner"]}
    saved = json.loads(profile_path.read_text(encoding="utf-8"))
    assert saved["skills"] == ["SQL", "Rust"]
    assert saved["skills_sources"] == [{"name": "Rust", "evidence": "2 repos", "source_url": GH}]
    assert saved["personal"]["email"] == "ana.test@example.com"  # el resto del perfil intacto
    again = ex.accept([{"name": "Rust"}])
    assert again["added"] == [] and json.loads(profile_path.read_text(encoding="utf-8"))["skills"] == ["SQL", "Rust"]


def test_api(env):
    status, _, body = call("POST", "/api/profile/expand", H, body=json.dumps({"sources": [GH]}).encode())
    assert status == 200
    data = json.loads(body)
    assert {p["name"] for p in data["proposals"]} >= {"Rust"} and data["errors"] == []
    assert call("POST", "/api/profile/expand", H, body=b'{"sources": []}')[0] == 422
    status, _, body = call("POST", "/api/profile/expand/accept", H, body=json.dumps({"items": [data["proposals"][0]]}).encode())
    assert status == 200 and json.loads(body)["added"] == [data["proposals"][0]["name"]]
    assert call("POST", "/api/profile/expand/accept", H, body=b'{"items": []}')[0] == 422
    # Revisión SP3 M3: cada competencia aceptada debe traer su fuente http(s)
    for bad in ("", "javascript:alert(1)", "ftp://x.example/a", "https://user:pw@x.example/"):
        item = {"items": [{"name": "Zig", "evidence": "x", "source_url": bad}]}
        assert call("POST", "/api/profile/expand/accept", H, body=json.dumps(item).encode())[0] == 422, bad
    assert call("POST", "/api/profile/expand/accept", H, body=b'{"items": [{"name": "Zig"}]}')[0] == 422
    assert call("POST", "/api/profile/expand/accept", [("content-type", "application/json")], body=b'{"items": [{"name": "x"}]}')[0] == 403


def test_competencia_aceptada_llega_al_cv_determinista_y_a_la_ia(env):
    """Revisión SP3 I1: lo aceptado en «Ampliar perfil» aparece en el CV (también sin IA) y en lo que la IA puede usar."""
    import profile_store
    from automation import ai_documents, document_generator

    ex.accept([{"name": "Rust", "evidence": "2 repos", "source_url": GH}])
    profile = profile_store.load_profile()
    ctx = document_generator.prepare_cv_context(profile)
    assert (document_generator.OTHER_SKILLS_LABEL, "SQL, Rust") in ctx["competencies"]
    assert "Rust" in document_generator.render_cv_from_context(ctx)
    assert "Rust" in ai_documents._allowed_skills(profile)
    # lo que ya está en el stack no se repite
    profile["skills"] = ["Rust", "python", ""]
    ctx = document_generator.prepare_cv_context(profile)
    assert (document_generator.OTHER_SKILLS_LABEL, "Rust") in ctx["competencies"]
    # sin competencias aceptadas no hay grupo extra
    assert all(label != document_generator.OTHER_SKILLS_LABEL
               for label, _ in document_generator.prepare_cv_context({"stack": {"programming": ["Go"]}})["competencies"])


def test_temas_de_github_que_no_son_competencias_no_se_proponen(env):
    """Revisión SP3 M2: temas como «hacktoberfest» o «dotfiles» no son habilidades."""
    names = {p["name"] for p in ex.propose([GH])["proposals"]}
    assert "robotics" in names and not names & {"hacktoberfest", "dotfiles"}
