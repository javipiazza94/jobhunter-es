"""Registra una candidatura suelta (teléfono, email directo, portal sin aviso) añadiendo UNA línea a
inbox/candidaturas_manual.txt (dentro de JH_HOME). No toca la BD: el vigilante del inbox (inbox_watcher.py) y
scripts/load_inbox_applications.py hacen el resto (dedupe, estados, copia previa).

Uso: python scripts/add_application.py "Empresa" "Puesto" [--estado sent] [--fecha AAAA-MM-DD]
                                        [--email destino@x.com] [--clave portal-empresa-puesto]

Sin --clave se genera una estable (`portal-<empresa>-<puesto>`), así registrar dos veces lo mismo no duplica.
"""
import argparse
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import INBOX_DIR  # noqa: E402

MANUAL_FILE = "candidaturas_manual.txt"
STATES = ("sent", "replied", "interview", "rejected", "rejected_manual")  # los que acepta el cargador


def _clean(value: str) -> str:
    """Una celda del formato: sin `|` ni saltos de línea."""
    return re.sub(r"\s+", " ", re.sub(r"[|\r\n]+", " ", value)).strip()


def _slug(value: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


def build_line(company: str, position: str, state: str = "sent", when: str | None = None,
               email: str = "", key: str | None = None) -> str:
    company, position = _clean(company), _clean(position)
    if not company or not position:
        raise ValueError("empresa y puesto son obligatorios")
    if state not in STATES:
        raise ValueError(f"estado «{state}» no válido; usa uno de: {', '.join(STATES)}")
    when = when or date.today().isoformat()
    date.fromisoformat(when)  # falla con ValueError si el formato no es AAAA-MM-DD
    key = _clean(key) if key else f"portal-{_slug(company)}-{_slug(position)}"[:120]
    return "|".join([when, company, position, _clean(email), state, key])


def append_line(line: str, inbox_dir: Path = INBOX_DIR) -> Path:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    path = inbox_dir / MANUAL_FILE
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if line in existing:
        return path  # ya estaba pendiente: no se repite
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("empresa")
    ap.add_argument("puesto")
    ap.add_argument("--estado", default="sent", choices=STATES)
    ap.add_argument("--fecha")
    ap.add_argument("--email", default="")
    ap.add_argument("--clave")
    args = ap.parse_args(argv)
    try:
        line = build_line(args.empresa, args.puesto, args.estado, args.fecha, args.email, args.clave)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    path = append_line(line, INBOX_DIR)  # explícito: así los tests pueden redirigir INBOX_DIR
    print(f"Añadida a {path.name}: {line}\nEl vigilante del inbox la cargará sola (API encendida).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
