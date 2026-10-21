"""
inbox_job.py — Carga en la BD de lo que n8n deja en JH_HOME/inbox/candidaturas_n8n_auto.txt.

Reutiliza scripts/load_inbox_applications.py (deduplicación, «dudosas», nunca bajar un estado):
- `inbox`: simulacro sobre una copia temporal de la BD; no guarda nada. El informe sale por stdout
  (en la API se lee con GET /api/jobs/{id}).
- `inbox-apply`: copia de seguridad de la BD y carga con --save. Conserva solo la última copia automática.
"""
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from config import DB_PATH, INBOX_DIR

BACKEND_DIR = Path(__file__).parent
INBOX_FILE = "candidaturas_n8n_auto.txt"
BACKUP_DIR_NAME = "backups"
BACKUP_PREFIX = "job_hunter.db.bak-auto-"


def backup_dir(db_path: Path) -> Path:
    """Las copias viven en backups/ junto a la BD copiada (con la BD por defecto = JH_HOME/backups).
    Así una BD de prueba (JH_DB_PATH) nunca escribe ni poda las copias reales."""
    return db_path.parent / BACKUP_DIR_NAME


def _prune_backups(db_path: Path, keep: int) -> None:
    for old in sorted(backup_dir(db_path).glob(BACKUP_PREFIX + "*"))[:-keep]:
        old.unlink()


def run_inbox(apply: bool, inbox_dir: Path = INBOX_DIR, db_path: Path = DB_PATH,
              runner=subprocess.run, keep: int = 1, now=datetime.now) -> int:
    """Devuelve el código de salida (0 = bien)."""
    f = inbox_dir / INBOX_FILE
    eventos = 0
    if f.exists():
        eventos = sum(1 for linea in f.read_text(encoding="utf-8").splitlines() if linea.strip() and not linea.startswith("#"))
    if not eventos:
        print(f"No hay eventos pendientes en inbox/{INBOX_FILE}.")
        return 0
    print(f"{eventos} evento(s) en inbox/{INBOX_FILE}. " + ("Aplicando." if apply else "Simulacro: no se guarda nada."))

    cmd = [sys.executable, str(BACKEND_DIR / "scripts" / "load_inbox_applications.py"), str(f)]
    if apply:
        if not db_path.exists():
            print(f"No encuentro la BD ({db_path}); no se aplica nada.")
            return 1
        backup_dir(db_path).mkdir(parents=True, exist_ok=True)
        backup = backup_dir(db_path) / f"{BACKUP_PREFIX}{now():%Y%m%d-%H%M%S}"
        shutil.copy2(db_path, backup)
        print(f"Copia de seguridad de la BD: {backup.name}")
        _prune_backups(db_path, keep)
        cmd.append("--save")
    return runner(cmd, cwd=BACKEND_DIR).returncode
