"""profile_store: lectura tolerante y escritura atómica de profile.json."""
import config
import profile_store
from automation import application_engine, cover_letter, language_gate


def test_perfil_ausente_devuelve_dict_vacio(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "profile.json")
    assert profile_store.load_profile() == {}
    assert profile_store.profile_exists() is False


def test_perfil_corrupto_devuelve_dict_vacio(tmp_path, monkeypatch):
    p = tmp_path / "profile.json"
    p.write_text("{no es json", encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", p)
    assert profile_store.load_profile() == {}


def test_perfil_que_no_es_objeto_devuelve_dict_vacio(tmp_path, monkeypatch):
    p = tmp_path / "profile.json"
    p.write_text("[1, 2]", encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", p)
    assert profile_store.load_profile() == {}


def test_save_y_load_round_trip(tmp_path, monkeypatch):
    p = tmp_path / "sub" / "profile.json"
    monkeypatch.setattr(config, "PROFILE_PATH", p)
    data = {"personal": {"name": "Ada Ejemplo", "city": "Villanova"}, "languages": [{"language": "inglés", "level": "C1"}]}
    assert profile_store.save_profile(data) == p
    assert profile_store.profile_exists() is True
    assert profile_store.load_profile() == data
    assert "Villanova" in p.read_text(encoding="utf-8")  # unicode sin escapar
    assert not list(p.parent.glob("*.tmp"))


def test_save_profile_invalida_la_cache_de_idiomas(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "profile.json")
    monkeypatch.setattr(language_gate, "PROFILE_PATH", tmp_path / "profile.json")
    language_gate.candidate_languages.cache_clear()
    assert "inglés" not in language_gate.candidate_languages()
    profile_store.save_profile({"languages": [{"language": "inglés", "level": "C1"}]})
    assert "inglés" in language_gate.candidate_languages()
    language_gate.candidate_languages.cache_clear()


def test_loaders_de_automation_delegan_y_toleran_perfil_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "no-existe.json")
    assert cover_letter._load_profile() == {}
    assert application_engine._load_profile() == {}


def test_create_drafts_sin_profile_json_no_lanza(tmp_path, monkeypatch):
    import database

    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "no-existe.json")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    conn = database.get_conn()
    database.init_db(conn)
    conn.close()
    result = application_engine.create_drafts()
    assert result["drafts_created"] == 0
