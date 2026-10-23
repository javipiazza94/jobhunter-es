"""API del asistente de primer arranque, del perfil y de los ajustes de IA/email.

Todo vive en una carpeta temporal (JH_HOME, cv/, profile.json, jobhunter.yaml) y los secretos en un llavero en
memoria: nunca se toca el llavero real ni la carpeta de datos. Los datos de prueba son inventados.
"""
import io
import json
import sys
from pathlib import Path

import keyring
import pytest
from docx import Document
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError

sys.path.insert(0, str(Path(__file__).parent.parent))

import ai  # noqa: E402
import config  # noqa: E402
import search_config  # noqa: E402
import secrets_store  # noqa: E402
import setup_builder  # noqa: E402
from automation import cv_reader, email_sender, language_gate, profile_proposal  # noqa: E402
from tests.asgi_client import call  # noqa: E402

CLIENT = ("x-jh-client", "dashboard")
JSON = ("content-type", "application/json")
SECRET = "sk-prueba-NO-DEVOLVER-123"  # gitleaks:allow (clave falsa de test)
SMTP_SECRET = "clave-smtp-NO-DEVOLVER-456"
BOUNDARY = "jhtestboundary7MA4YWxkTrZu0gW"


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        self.data = {}

    def get_password(self, service, username):
        return self.data.get((service, username))

    def set_password(self, service, username, password):
        self.data[(service, username)] = password

    def delete_password(self, service, username):
        self.data.pop((service, username), None)


class FailingKeyring(KeyringBackend):
    priority = 1

    def get_password(self, service, username):
        raise KeyringError("sin backend")

    def set_password(self, service, username, password):
        raise KeyringError("sin backend")

    def delete_password(self, service, username):
        raise KeyringError("sin backend")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """JH_HOME vacío en tmp, llavero en memoria y sin variables de entorno de secretos; restaura la config."""
    profile = tmp_path / "profile.json"
    monkeypatch.setattr(config, "JH_HOME", tmp_path)
    monkeypatch.setattr(config, "CV_DIR", tmp_path / "cv")
    monkeypatch.setattr(config, "PROFILE_PATH", profile)
    monkeypatch.setattr(language_gate, "PROFILE_PATH", profile)
    for var in (*secrets_store.ENV_FALLBACK.values(), "GMAIL_USER"):
        monkeypatch.delenv(var, raising=False)
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    saved = (search_config._cache, search_config._pinned, search_config._loaded_from)
    search_config.set_config(None)
    language_gate.candidate_languages.cache_clear()
    yield tmp_path
    keyring.set_keyring(previous)
    search_config._cache, search_config._pinned, search_config._loaded_from = saved
    language_gate.candidate_languages.cache_clear()


def _get(path):
    status, _, body = call("GET", path)
    return status, json.loads(body) if body else None


def _send(method, path, payload, headers=(CLIENT, JSON)):
    status, _, body = call(method, path, headers=headers, body=json.dumps(payload).encode())
    return status, json.loads(body) if body else None


def _multipart(filename: str, content: bytes, ctype: str = "application/octet-stream") -> bytes:
    head = (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode()
    return head + content + f"\r\n--{BOUNDARY}--\r\n".encode()


def _upload(filename, content, length=None):
    """Sube `content`; `length` fuerza la cabecera Content-Length (None = la real, "" = sin cabecera)."""
    payload = _multipart(filename, content)
    length = str(len(payload)) if length is None else length
    headers = (CLIENT, ("content-type", f"multipart/form-data; boundary={BOUNDARY}"))
    if length != "":
        headers += (("content-length", length),)
    status, _, body = call("POST", "/api/setup/cv", headers=headers, body=payload)
    return status, json.loads(body) if body else None


def _docx_bytes(text="Ana Prueba — Data Engineer en Villanova. Python, SQL, Spark.") -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _answers(**kw) -> dict:
    base = {
        "draft": {
            "full_name": "Ana Prueba Ejemplo",
            "email": "ana@example.com",
            "city": "Villanova",
            "country": "España",
            "targets": [{"title": "Data Engineer", "keywords": ["data engineer", "spark"]}],
            "tools": ["Python", "SQL"],
            "languages": [{"language": "English", "level": "B2"}],
            "modality": ["remote"],
        },
        "markets": ["spain"],
        "sources": ["tecnoempleo"],
        "followed_companies": ["Acme Robotics"],
    }
    base.update(kw)
    return base


def _apply(**kw):
    return _send("POST", "/api/setup/apply", _answers(**kw))


class FakeProvider:
    def __init__(self, ok=True):
        self.ok = ok

    def generate_json(self, prompt, schema, system=None):
        return {"full_name": "Ana Prueba", "city": "Villanova",
                "targets": [{"title": "Data Engineer", "keywords": ["spark"]}], "tools": ["Python"]}

    def generate_text(self, prompt, system=None):
        return "texto"

    def check(self):
        return (True, "IA lista") if self.ok else (False, "No responde")


# ── Estado y mercados ────────────────────────────────────────────────────────────


def test_status_con_jh_home_vacio_pide_asistente():
    assert _get("/api/setup/status") == (200, {"needs_setup": True, "has_profile": False, "has_config": False})


def test_status_tras_apply_ya_no_pide_asistente():
    assert _apply()[0] == 200
    assert _get("/api/setup/status")[1] == {"needs_setup": False, "has_profile": True, "has_config": True}


def test_status_con_config_pero_sin_perfil_pide_asistente(home):
    (home / "jobhunter.yaml").write_text((Path(search_config.DEFAULT_CONFIG_PATH)).read_text(encoding="utf-8"))
    assert _get("/api/setup/status")[1] == {"needs_setup": True, "has_profile": False, "has_config": True}


def test_status_instalacion_antigua_con_perfil_sin_config_no_fuerza_asistente(home):
    """Instalación previa con profile.json y sin jobhunter.yaml propio: el dashboard solo sugiere el asistente."""
    (home / "profile.json").write_text(json.dumps({"personal": {"name": "Ana Prueba"}}), encoding="utf-8")
    assert _get("/api/setup/status")[1] == {"needs_setup": False, "has_profile": True, "has_config": False}


def test_markets_devuelve_markets_yaml():
    status, data = _get("/api/setup/markets")
    assert status == 200
    assert data == setup_builder.load_markets()
    assert {"id", "label", "requires_ack", "default_on"} <= set(data["spain"][0])


# ── Subida de CV y propuesta ────────────────────────────────────────────────────


def test_subir_docx_guarda_nombre_saneado_y_propone_vacio_sin_ia(home):
    status, data = _upload("../../Mi CV (2026) ñ.docx", _docx_bytes())
    assert status == 200, data
    assert data["source"] == "empty"
    assert data["text_chars"] > 20
    assert data["cv_path"].startswith("cv/") and data["cv_path"].endswith(".docx")
    name = data["cv_path"].removeprefix("cv/")
    assert "/" not in name and " " not in name and ".." not in name
    assert (home / "cv" / name).is_file()
    assert [p.name for p in (home / "cv").iterdir()] == [name]  # sin temporales
    assert data["draft"]["targets"] == []


def test_subir_cv_con_ia_devuelve_borrador(monkeypatch):
    monkeypatch.setattr(profile_proposal, "get_provider", lambda: FakeProvider())
    status, data = _upload("cv.docx", _docx_bytes())
    assert status == 200
    assert data["source"] == "ai"
    assert data["draft"]["full_name"] == "Ana Prueba"
    assert data["draft"]["targets"][0]["title"] == "Data Engineer"


@pytest.mark.parametrize("name", ["cv.txt", "cv.exe", "cv", "cv.pdf.sh"])
def test_subir_otro_tipo_da_400_y_no_escribe(home, name):
    status, data = _upload(name, b"hola")
    assert status == 400
    assert "PDF" in data["detail"]
    assert not (home / "cv").exists() or not any((home / "cv").iterdir())


def test_subir_mas_de_10_mb_da_413_antes_de_leer(home):
    status, data = _upload("grande.pdf", b"0" * (cv_reader.MAX_FILE_BYTES + 64 * 1024 + 1))
    assert status == 413
    assert "10 MB" in data["detail"]
    assert not (home / "cv").exists()


def test_content_length_falso_se_corta_al_leer_por_trozos(home):
    # Content-Length pequeño pero cuerpo de más de 10 MB: el corte por trozos lo para igual.
    status, data = _upload("grande.pdf", b"0" * (cv_reader.MAX_FILE_BYTES + 1), length="1000")
    assert status == 413
    assert not any((home / "cv").iterdir())


def test_poco_mas_de_10_mb_se_corta_al_leer(home):
    status, data = _upload("grande.pdf", b"0" * (cv_reader.MAX_FILE_BYTES + 1))
    assert status == 413 and "10 MB" in data["detail"]
    assert not any((home / "cv").iterdir())


@pytest.mark.parametrize("length", ["", "mucho"])
def test_sin_content_length_valido_da_411(home, length):
    status, _ = _upload("cv.docx", _docx_bytes(), length=length)
    assert status == 411
    assert not (home / "cv").exists()


def test_mismo_nombre_no_sobrescribe(home):
    first = _upload("cv.docx", _docx_bytes("Primera versión del CV de Ana Prueba en Villanova"))[1]["cv_path"]
    second = _upload("cv.docx", _docx_bytes("Segunda versión del CV de Ana Prueba en Villanova"))[1]["cv_path"]
    third = _upload("cv.docx", _docx_bytes("Tercera versión del CV de Ana Prueba en Villanova"))[1]["cv_path"]
    assert (first, second, third) == ("cv/cv.docx", "cv/cv-2.docx", "cv/cv-3.docx")
    assert sorted(p.name for p in (home / "cv").iterdir()) == ["cv-2.docx", "cv-3.docx", "cv.docx"]


def test_pdf_ilegible_da_400_con_mensaje_y_no_se_guarda(home):
    status, data = _upload("roto.pdf", b"%PDF-1.4 esto no es un pdf")
    assert status == 400
    assert data["detail"]
    assert not any((home / "cv").iterdir())


def test_subir_sin_campo_file_da_400():
    body = f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"otro\"\r\n\r\nx\r\n--{BOUNDARY}--\r\n".encode()
    headers = (CLIENT, ("content-type", f"multipart/form-data; boundary={BOUNDARY}"), ("content-length", str(len(body))))
    status, _, _ = call("POST", "/api/setup/cv", headers=headers, body=body)
    assert status == 400


def test_subir_sin_cabecera_cliente_da_403(home):
    headers = (("content-type", f"multipart/form-data; boundary={BOUNDARY}"),)
    status, _, _ = call("POST", "/api/setup/cv", headers=headers, body=_multipart("cv.docx", _docx_bytes()))
    assert status == 403
    assert not (home / "cv").exists()


def test_propose_con_texto_pegado(monkeypatch):
    monkeypatch.setattr(profile_proposal, "get_provider", lambda: FakeProvider())
    status, data = _send("POST", "/api/setup/propose", {"text": "Ana Prueba, Data Engineer"})
    assert status == 200
    assert data["source"] == "ai" and data["text_chars"] == len("Ana Prueba, Data Engineer")
    assert data["cv_path"] is None


def test_propose_texto_enorme_da_422():
    assert _send("POST", "/api/setup/propose", {"text": "x" * 500_001})[0] == 422


def test_propose_sin_ia_da_borrador_vacio():
    status, data = _send("POST", "/api/setup/propose", {"text": "Ana Prueba"})
    assert status == 200 and data["source"] == "empty"


# ── Aplicar el asistente ────────────────────────────────────────────────────────


def test_apply_y_luego_tracks_devuelve_los_nuevos(home):
    status, data = _apply()
    assert status == 200
    assert data == {"tracks": ["data_engineer"], "sources": ["tecnoempleo"]}
    status, tracks = _get("/api/tracks")
    assert [t["id"] for t in tracks] == ["data_engineer"]
    assert (home / "jobhunter.yaml").is_file() and (home / "profile.json").is_file()


def test_apply_guarda_cv_path_en_el_perfil():
    _, up = _upload("cv.docx", _docx_bytes())
    assert _apply(cv_path=up["cv_path"])[0] == 200
    assert _get("/api/profile")[1]["cv_path"] == up["cv_path"]


def test_apply_rechaza_cv_path_fuera_de_cv():
    assert _apply(cv_path="../profile.json")[0] == 422


def test_apply_sin_objetivos_da_422_y_no_escribe(home):
    answers = _answers()
    answers["draft"]["targets"] = []
    status, data = _send("POST", "/api/setup/apply", answers)
    assert status == 422
    assert "objetivo" in data["detail"]
    assert not (home / "jobhunter.yaml").exists()


# ── Perfil ──────────────────────────────────────────────────────────────────────


def test_perfil_get_vacio_y_put_round_trip():
    assert _get("/api/profile") == (200, {})
    perfil = {"personal": {"name": "Ana Prueba", "city": "Villanova"}, "languages": []}
    assert _send("PUT", "/api/profile", perfil) == (200, perfil)
    assert _get("/api/profile") == (200, perfil)


def test_perfil_put_recalcula_codigo_de_pais_permiso_e_idiomas_como_el_asistente():
    """Editar país o idiomas en Perfil deja los campos derivados coherentes (los que leen los filtros)."""
    perfil = {
        "personal": {"name": "Ana Prueba", "country": "México", "country_code": "ES", "work_permit": True,
                     "work_permit_countries": ["México"]},
        "languages": [{"language": "English", "level": "B2"}, {"language": "Klingon", "level": "A1"}],
    }
    status, data = _send("PUT", "/api/profile", perfil)
    assert status == 200
    assert data["personal"]["country_code"] == "MX"
    assert data["personal"]["work_permit"] is False
    assert [lang["language"] for lang in data["languages"]] == ["Inglés", "Klingon"]
    language_gate.candidate_languages.cache_clear()
    assert language_gate.candidate_languages()["inglés"] == 4


def test_perfil_put_pais_desconocido_conserva_un_codigo_puesto_a_mano():
    perfil = {"personal": {"country": "Nederland", "country_code": "NL"}}
    assert _send("PUT", "/api/profile", perfil)[1]["personal"]["country_code"] == "NL"
    perfil = {"personal": {"country": "Atlantis", "country_code": "ES"}}  # código de otro país: ya no vale
    assert _send("PUT", "/api/profile", perfil)[1]["personal"]["country_code"] == ""


def test_perfil_patch_guarda_preferencias_de_idioma_sin_tocar_el_resto():
    """La interfaz persiste `preferences.ui_language` con PATCH; el resto del perfil queda igual."""
    perfil = {"personal": {"name": "Ana Prueba"}, "languages": []}
    assert _send("PUT", "/api/profile", perfil)[0] == 200
    status, data = _send("PATCH", "/api/profile", {"preferences": {"ui_language": "en"}})
    assert status == 200
    assert data["preferences"] == {"ui_language": "en"}
    assert data["personal"]["name"] == "Ana Prueba"
    assert _get("/api/profile")[1]["preferences"]["ui_language"] == "en"


def test_perfil_put_que_no_es_objeto_da_422():
    assert _send("PUT", "/api/profile", ["no", "objeto"])[0] == 422


@pytest.mark.parametrize("bad", [
    {"languages": "ab", "personal": "x"},
    {"personal": "x"},
    {"experience": ["no es un dict"]},
    {"stack": []},
])
def test_perfil_put_con_forma_incorrecta_da_422(bad):
    assert _send("PUT", "/api/profile", bad)[0] == 422


def test_perfil_put_acepta_campos_extra_y_certificaciones_texto():
    perfil = {"personal": {}, "certifications": ["AWS", {"name": "SAP"}], "cover_letter_intro": "Hola {company_name}"}
    assert _send("PUT", "/api/profile", perfil) == (200, perfil)


def test_perfil_put_de_mas_de_1_mb_da_413():
    body = json.dumps({"notes": "x" * (1024 * 1024)}).encode()
    headers = (CLIENT, JSON, ("content-length", str(len(body))))
    status, _, _ = call("PUT", "/api/profile", headers=headers, body=body)
    assert status == 413


def test_perfil_put_sin_cabecera_da_403():
    assert _send("PUT", "/api/profile", {"a": 1}, headers=(JSON,))[0] == 403


# ── Ajustes de IA ───────────────────────────────────────────────────────────────


def test_ai_get_por_defecto():
    status, data = _get("/api/settings/ai")
    assert status == 200
    assert data["provider"] == "none"
    assert data["has_key"] == {"anthropic": False, "openai": False}
    assert data["key_source"] == {"anthropic": None, "openai": None}


def test_ai_put_sin_asistente_da_409(home):
    status, data = _send("PUT", "/api/settings/ai", {"provider": "ollama"})
    assert status == 409
    assert data["detail"] == "Completa primero el asistente"
    assert not (home / "jobhunter.yaml").exists()


def test_ai_put_sin_cabecera_da_403():
    _apply()
    assert _send("PUT", "/api/settings/ai", {"provider": "ollama"}, headers=(JSON,))[0] == 403


def test_ai_put_guarda_proveedor_y_clave_en_llavero_sin_devolverla(home):
    _apply()
    status, data = _send("PUT", "/api/settings/ai",
                         {"provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": SECRET})
    assert status == 200
    assert SECRET not in json.dumps(data)
    assert data["provider"] == "anthropic" and data["model"] == "claude-sonnet-5-5"
    assert data["has_key"] == {"anthropic": True, "openai": False}
    assert data["key_source"]["anthropic"] == "keychain"
    assert keyring.get_keyring().get_password("jobhunter", "anthropic_api_key") == SECRET
    yaml_text = (home / "jobhunter.yaml").read_text(encoding="utf-8")
    assert "provider: anthropic" in yaml_text and SECRET not in yaml_text
    status, again = _get("/api/settings/ai")
    assert again == data and SECRET not in json.dumps(again)


def test_ai_key_source_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    status, data = _get("/api/settings/ai")
    assert data["has_key"]["openai"] is True and data["key_source"]["openai"] == "env"
    assert SECRET not in json.dumps(data)


def test_ai_put_clave_para_proveedor_sin_clave_da_400():
    _apply()
    assert _send("PUT", "/api/settings/ai", {"provider": "ollama", "api_key": SECRET})[0] == 400


def test_ai_put_proveedor_desconocido_da_422():
    _apply()
    assert _send("PUT", "/api/settings/ai", {"provider": "skynet"})[0] == 422


def test_ai_put_llavero_no_disponible_da_503_y_no_cambia_config(home):
    _apply()
    keyring.set_keyring(FailingKeyring())
    status, data = _send("PUT", "/api/settings/ai", {"provider": "openai", "api_key": SECRET})
    assert status == 503
    assert data["detail"].startswith("El llavero del sistema no está disponible: usa la variable de entorno")
    assert "OPENAI_API_KEY" in data["detail"] and SECRET not in data["detail"]
    assert _get("/api/settings/ai")[1]["provider"] == "none"


def test_ai_put_parcial_solo_cambia_lo_enviado():
    _apply()
    _send("PUT", "/api/settings/ai", {"provider": "ollama", "model": "llama3.1", "base_url": "http://localhost:11434"})
    status, data = _send("PUT", "/api/settings/ai", {"timeout_seconds": 30})
    assert status == 200
    assert (data["provider"], data["model"], data["base_url"], data["timeout_seconds"]) == (
        "ollama", "llama3.1", "http://localhost:11434", 30)


@pytest.mark.parametrize("timeout", [0, 601])
def test_ai_put_timeout_fuera_de_rango_da_422(timeout):
    _apply()
    assert _send("PUT", "/api/settings/ai", {"timeout_seconds": timeout})[0] == 422


@pytest.mark.parametrize("provider, status", [("anthropic", 422), ("claude_cli", 422), ("openai", 200), ("ollama", 200)])
def test_ai_base_url_solo_para_ollama_y_openai(provider, status):
    _apply()
    assert _send("PUT", "/api/settings/ai", {"provider": provider, "base_url": "http://localhost:9999"})[0] == status


def test_ai_put_config_invalida_da_422(monkeypatch):
    import main
    from search_config import ConfigError

    def boom(*a, **kw):
        raise ConfigError("jobhunter.yaml inválido")

    _apply()
    monkeypatch.setattr(main, "save_config", boom)
    assert _send("PUT", "/api/settings/ai", {"provider": "ollama"}) == (422, {"detail": "jobhunter.yaml inválido"})
    assert _send("PUT", "/api/settings/email", {"preset": "gmail"})[0] == 422


def test_ai_test_usa_check_del_proveedor(monkeypatch):
    monkeypatch.setattr(ai, "get_provider", lambda settings=None: FakeProvider(ok=False))
    status, _, body = call("POST", "/api/settings/ai/test", headers=(CLIENT,))
    assert status == 200 and json.loads(body) == {"ok": False, "message": "No responde"}


def test_ai_test_sin_ia_responde_ok_false():
    status, _, body = call("POST", "/api/settings/ai/test", headers=(CLIENT,))
    data = json.loads(body)
    assert status == 200 and data["ok"] is False and data["message"]


# ── Ajustes de email ────────────────────────────────────────────────────────────


def test_email_get_por_defecto_es_gmail():
    status, data = _get("/api/settings/email")
    assert status == 200
    assert data["preset"] == "gmail" and data["smtp_host"] == "smtp.gmail.com" and data["smtp_port"] == 587
    assert data["has_password"] is False and data["password_source"] is None


def test_email_put_sin_asistente_da_409():
    assert _send("PUT", "/api/settings/email", {"preset": "gmail"})[0] == 409


def test_email_put_guarda_ajustes_y_contrasena_sin_devolverla(home):
    _apply()
    payload = {"preset": "custom", "smtp_host": "smtp.villanova.example", "smtp_port": 465, "use_starttls": False,
               "username": "ana@villanova.example", "from_name": "Ana Prueba", "password": SMTP_SECRET}
    status, data = _send("PUT", "/api/settings/email", payload)
    assert status == 200
    assert SMTP_SECRET not in json.dumps(data)
    assert data["smtp_host"] == "smtp.villanova.example" and data["smtp_port"] == 465
    assert data["has_password"] is True and data["password_source"] == "keychain"
    assert keyring.get_keyring().get_password("jobhunter", "smtp_password") == SMTP_SECRET
    assert SMTP_SECRET not in (home / "jobhunter.yaml").read_text(encoding="utf-8")
    assert _get("/api/settings/email")[1] == data


def test_email_put_parcial_solo_cambia_lo_enviado():
    _apply()
    _send("PUT", "/api/settings/email", {"preset": "custom", "smtp_host": "smtp.villanova.example", "smtp_port": 465})
    status, data = _send("PUT", "/api/settings/email", {"from_name": "Ana Prueba"})
    assert status == 200
    assert (data["preset"], data["smtp_host"], data["smtp_port"], data["from_name"]) == (
        "custom", "smtp.villanova.example", 465, "Ana Prueba")


@pytest.mark.parametrize("port", [0, 70000])
def test_email_put_puerto_fuera_de_rango_da_422(port):
    _apply()
    assert _send("PUT", "/api/settings/email", {"smtp_port": port})[0] == 422


def test_email_password_source_env(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", SMTP_SECRET)
    data = _get("/api/settings/email")[1]
    assert data["has_password"] is True and data["password_source"] == "env"
    assert SMTP_SECRET not in json.dumps(data)


def test_email_put_llavero_no_disponible_da_503():
    _apply()
    keyring.set_keyring(FailingKeyring())
    status, data = _send("PUT", "/api/settings/email", {"preset": "gmail", "password": SMTP_SECRET})
    assert status == 503 and "GMAIL_APP_PASSWORD" in data["detail"]


def test_email_put_sin_cabecera_da_403():
    _apply()
    assert _send("PUT", "/api/settings/email", {"preset": "gmail"}, headers=(JSON,))[0] == 403


def test_email_test_usa_check_smtp_connection(monkeypatch):
    monkeypatch.setattr(email_sender, "check_smtp_connection", lambda: (True, "Conexión correcta con x:587."))
    status, _, body = call("POST", "/api/settings/email/test", headers=(CLIENT,))
    assert status == 200 and json.loads(body) == {"ok": True, "message": "Conexión correcta con x:587."}


def test_email_test_sin_credenciales():
    status, _, body = call("POST", "/api/settings/email/test", headers=(CLIENT,))
    assert status == 200 and json.loads(body)["ok"] is False


# ── Ronda de correcciones 1: precarga, fuentes en Perfil, IA del asistente ───────────


def test_current_sin_nada_devuelve_borrador_vacio_y_sin_fuentes_de_usuario():
    status, data = _get("/api/setup/current")
    assert status == 200
    assert data["draft"]["full_name"] == ""
    assert data["ai"]["provider"] == "none"


def test_current_tras_apply_precarga_perfil_objetivos_fuentes_e_ia():
    assert _apply(
        sources=["tecnoempleo", "infojobs"],
        acknowledged_sources=["infojobs"],
        ai={"provider": "ollama", "model": "llama3.1", "base_url": None, "timeout_seconds": 90},
        draft={**_answers()["draft"], "modality": ["remote", "hybrid"],
               "experience": [{"company": "Acme Robotics", "role": "Dev"}]},
    )[0] == 200
    status, data = _get("/api/setup/current")
    assert status == 200
    d = data["draft"]
    assert d["full_name"] == "Ana Prueba Ejemplo" and d["city"] == "Villanova"
    assert d["targets"] == [{"title": "Data Engineer", "keywords": ["data engineer", "spark"]}]
    assert d["tools"] == ["Python", "SQL"]
    assert d["modality"] == ["remote", "hybrid"]
    assert d["experience"][0]["company"] == "Acme Robotics"
    assert {"language": "Inglés", "level": "B2"} in d["languages"]
    assert data["sources"] == ["tecnoempleo", "infojobs"]
    assert data["acknowledged_sources"] == ["infojobs"]
    assert "spain" in data["markets"]
    assert data["followed_companies"] == ["Acme Robotics"]
    assert data["ai"]["provider"] == "ollama" and data["ai"]["timeout_seconds"] == 90
    # Volver a aplicar lo precargado no falla y deja lo mismo
    assert _send("POST", "/api/setup/apply", data)[0] == 200


def test_sources_get_y_put_respetan_avisos_y_conservan_ajustes(home):
    assert _apply(sources=["tecnoempleo"])[0] == 200
    status, data = _get("/api/settings/sources")
    assert status == 200
    by_id = {s["id"]: s for s in data}
    assert by_id["tecnoempleo"]["enabled"] and not by_id["infojobs"]["enabled"]
    assert by_id["infojobs"]["requires_ack"] and "spain" in by_id["infojobs"]["markets"]
    before = search_config.get_config().sources["tecnoempleo"]

    # requires_ack sin aceptar → 422 y no cambia nada
    assert _send("PUT", "/api/settings/sources", {"enabled": ["tecnoempleo", "infojobs"], "acknowledged": []})[0] == 422
    assert list(search_config.load_config(home / "jobhunter.yaml").sources) == ["tecnoempleo"]

    status, data = _send("PUT", "/api/settings/sources",
                         {"enabled": ["tecnoempleo", "infojobs", "manfred"], "acknowledged": ["infojobs"]})
    assert status == 200, data
    saved = search_config.load_config(home / "jobhunter.yaml").sources
    assert list(saved) == ["tecnoempleo", "infojobs", "manfred"]
    assert saved["tecnoempleo"] == before
    assert saved["infojobs"]["keywords"] == ["data engineer", "spark"]
    assert {s["id"]: s["acknowledged"] for s in data}["infojobs"] is True

    assert _send("PUT", "/api/settings/sources", {"enabled": ["no_existe"], "acknowledged": []})[0] == 422


def test_sources_put_sin_asistente_da_409():
    assert _send("PUT", "/api/settings/sources", {"enabled": [], "acknowledged": []})[0] == 409


def test_propose_con_ia_del_asistente_usa_ese_proveedor_solo_para_la_llamada(monkeypatch):
    usados = []

    def fake(settings=None):
        usados.append(settings.provider if settings else None)
        return FakeProvider()

    monkeypatch.setattr(ai, "get_provider", fake)
    body = {"text": "Ana Prueba, Data Engineer en Villanova", "ai": {"provider": "ollama", "timeout_seconds": 30}}
    status, data = _send("POST", "/api/setup/propose", body)
    assert status == 200 and data["source"] == "ai"
    assert usados == ["ollama"]
    assert not (config.JH_HOME / "jobhunter.yaml").exists()  # no guarda nada


def test_subir_cv_con_campo_ai_usa_ese_proveedor(monkeypatch):
    usados = []
    monkeypatch.setattr(ai, "get_provider", lambda settings=None: usados.append(settings.provider) or FakeProvider())
    ai_part = (
        f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"ai\"\r\n\r\n"
        '{"provider": "ollama"}\r\n'
    ).encode()
    payload = ai_part + _multipart("cv.docx", _docx_bytes())
    headers = (CLIENT, ("content-type", f"multipart/form-data; boundary={BOUNDARY}"), ("content-length", str(len(payload))))
    status, _, body = call("POST", "/api/setup/cv", headers=headers, body=payload)
    assert status == 200, body
    assert json.loads(body)["source"] == "ai" and usados == ["ollama"]


def test_subir_cv_con_campo_ai_invalido_da_422():
    ai_part = f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"ai\"\r\n\r\n{{\"provider\": \"skynet\"}}\r\n".encode()
    payload = ai_part + _multipart("cv.docx", _docx_bytes())
    headers = (CLIENT, ("content-type", f"multipart/form-data; boundary={BOUNDARY}"), ("content-length", str(len(payload))))
    assert call("POST", "/api/setup/cv", headers=headers, body=payload)[0] == 422


def test_clave_de_ia_se_guarda_antes_del_asistente_y_nunca_vuelve():
    status, _, body = call("POST", "/api/settings/ai/key", headers=(CLIENT, JSON),
                           body=json.dumps({"provider": "anthropic", "api_key": SECRET}).encode())
    assert status == 200
    assert SECRET not in (body.decode() if isinstance(body, bytes) else body)
    assert json.loads(body) == {"provider": "anthropic", "has_key": True, "key_source": "keychain"}
    assert secrets_store.get_secret("anthropic_api_key") == SECRET


def test_clave_de_ia_con_llavero_caido_da_503_sin_eco():
    keyring.set_keyring(FailingKeyring())
    status, _, body = call("POST", "/api/settings/ai/key", headers=(CLIENT, JSON),
                           body=json.dumps({"provider": "openai", "api_key": SECRET}).encode())
    assert status == 503
    assert SECRET not in (body.decode() if isinstance(body, bytes) else body)


def test_clave_de_ia_proveedor_sin_clave_da_422():
    assert _send("POST", "/api/settings/ai/key", {"provider": "ollama", "api_key": "x"})[0] == 422


@pytest.mark.parametrize("provider,status", [("ollama", 200), ("openai", 200), ("anthropic", 422), ("claude_cli", 422)])
def test_propose_con_base_url_solo_para_ollama_y_openai(monkeypatch, provider, status):
    """La misma regla que PUT /api/settings/ai: con anthropic, la clave iría a una URL arbitraria."""
    monkeypatch.setattr(ai, "get_provider", lambda settings=None: FakeProvider())
    body = {"text": "Ana Prueba", "ai": {"provider": provider, "base_url": "http://localhost:9999"}}
    assert _send("POST", "/api/setup/propose", body)[0] == status


def test_subir_cv_con_base_url_no_permitida_da_422_sin_guardar(home):
    ai_part = (
        f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"ai\"\r\n\r\n"
        '{"provider": "anthropic", "base_url": "http://localhost:9999"}\r\n'
    ).encode()
    payload = ai_part + _multipart("cv.docx", _docx_bytes())
    headers = (CLIENT, ("content-type", f"multipart/form-data; boundary={BOUNDARY}"), ("content-length", str(len(payload))))
    assert call("POST", "/api/setup/cv", headers=headers, body=payload)[0] == 422
    assert not any((home / "cv").glob("*"))


def test_apply_con_base_url_no_permitida_da_422(home):
    status, _ = _apply(ai={"provider": "anthropic", "base_url": "http://localhost:9999"})
    assert status == 422
    assert not (home / "jobhunter.yaml").exists()
