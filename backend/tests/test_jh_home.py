"""JH_HOME: una sola carpeta de datos (BD, inbox, logs, backups, sesiones, CVs)."""
import importlib
from pathlib import Path

import pytest

import config

ENV_VARS = ("JH_HOME", "JH_DB_PATH", "JH_INBOX_DIR", "JH_PROFILE_PATH")


@pytest.fixture
def reload_config(monkeypatch):
    """Recarga config con el entorno del test y lo restaura al terminar."""
    def _reload(**env):
        for var in ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, str(v))
        return importlib.reload(config)
    yield _reload
    monkeypatch.undo()
    importlib.reload(config)


def test_jh_home_por_defecto_es_data_del_repo(reload_config):
    cfg = reload_config()
    assert cfg.JH_HOME == cfg.REPO_ROOT / "data"
    assert cfg.REPO_ROOT == Path(config.__file__).parent.parent
    assert cfg.DB_PATH == cfg.JH_HOME / "job_hunter.db"
    assert cfg.INBOX_DIR == cfg.JH_HOME / "inbox"
    assert cfg.PROFILE_PATH == cfg.JH_HOME / "profile.json"
    assert cfg.BACKUPS_DIR == cfg.JH_HOME / "backups"
    assert cfg.LOGS_DIR == cfg.JH_HOME / "logs"
    assert cfg.CV_DIR == cfg.JH_HOME / "cv"
    assert cfg.SESSIONS_DIR == cfg.JH_HOME / "sessions"
    assert cfg.TEMPLATES_OVERRIDE_DIR == cfg.JH_HOME / "templates"


def test_env_individual_manda_sobre_jh_home(reload_config, tmp_path):
    cfg = reload_config(JH_HOME=tmp_path / "h", JH_DB_PATH=tmp_path / "otra.db",
                        JH_INBOX_DIR=tmp_path / "bandeja", JH_PROFILE_PATH=tmp_path / "p.json")
    assert cfg.JH_HOME == tmp_path / "h"
    assert cfg.DB_PATH == tmp_path / "otra.db"
    assert cfg.INBOX_DIR == tmp_path / "bandeja"
    assert cfg.PROFILE_PATH == tmp_path / "p.json"
    assert cfg.LOGS_DIR == tmp_path / "h" / "logs"


def test_ensure_data_dirs_crea_la_estructura(reload_config, tmp_path):
    home = tmp_path / "no" / "existe"
    cfg = reload_config(JH_HOME=home)
    assert not home.exists()
    cfg.ensure_data_dirs()
    for name in ("inbox", "backups", "logs", "cv", "sessions"):
        assert (home / name).is_dir()
    cfg.ensure_data_dirs()  # idempotente


def test_resolve_data_path(reload_config, tmp_path):
    cfg = reload_config(JH_HOME=tmp_path)
    assert cfg.resolve_data_path("cv/a.pdf") == tmp_path / "cv/a.pdf"
    assert cfg.resolve_data_path(Path("cv/a.pdf")) == tmp_path / "cv/a.pdf"
    absolute = tmp_path / "fuera" / "b.pdf"
    assert cfg.resolve_data_path(absolute) == absolute


def test_backup_dir_por_defecto_coincide_con_backups_dir():
    import inbox_job
    assert inbox_job.backup_dir(config.DB_PATH) == config.BACKUPS_DIR


def test_bd_de_prueba_fuera_de_jh_home_no_toca_las_copias_reales(tmp_path):
    import subprocess
    from datetime import datetime

    import inbox_job
    real = config.BACKUPS_DIR / (inbox_job.BACKUP_PREFIX + "20200101-000000")
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_bytes(b"copia real")
    try:
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        (inbox / inbox_job.INBOX_FILE).write_text("2026-10-06|ACME|SAP||sent|abc\n")
        db = tmp_path / "copia.db"
        db.write_bytes(b"bd de prueba")
        runner = lambda cmd, cwd=None: subprocess.CompletedProcess(cmd, 0)  # noqa: E731
        for i in range(3):  # keep=1: poda de verdad
            inbox_job.run_inbox(True, inbox, db, runner, keep=1, now=lambda i=i: datetime(2026, 10, 7, 12, 0, i))
        beside = list((tmp_path / "backups").glob(inbox_job.BACKUP_PREFIX + "*"))
        assert len(beside) == 1
        assert real.read_bytes() == b"copia real"
    finally:
        real.unlink(missing_ok=True)
