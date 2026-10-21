"""Carga candidaturas dejadas en JH_HOME/inbox/ (a mano, por n8n o por un agente externo), una por línea:
    fecha|empresa|puesto|email_destino|estado|gmail_thread_id      (# = comentario)

- Estados válidos: sent, replied, interview, offer, rejected, rejected_manual (otro → se avisa y se omite).
- Dedupe: por gmail_thread_id (guardado en notes como "[gmail:ID]", la tabla no tiene columna) y por
  empresa normalizada + puesto aproximado. Si ya existe NO se duplica: solo se actualiza el estado
  (rejected pisa sent/replied; nunca se baja de interview/replied a sent; interview + rejected → dudosa).
- Filas sin gmail_thread_id: solo actualizan una candidatura existente con match claro; si no, se listan.
- Coincidencia solo parcial con una candidatura existente → dudosa (no se crea ni se toca).
- Empresa "(por confirmar)" → empresa «Sin confirmar»; ahí el dedupe es solo por thread id (el puesto
  no identifica nada). Sale en «Por revisar», igual que los puestos "por confirmar" y los comentarios
  de la sección «A REVISAR» del fichero.
- Filas de portal sin hilo de Gmail: usa como último campo una clave estable `portal-<slug>` (p. ej.
  `portal-ejemplo-teleoperador`); se guarda como [gmail:CLAVE] en notes y la oferta recibe la URL
  `portal://job-hunter/CLAVE`, así el dedupe por clave sigue funcionando.
- Trabajo puente → oferta con job_kind='generic' (nunca toca is_relevant/relevance_score): lo son las
  líneas bajo una cabecera "# ===== ... TRABAJO PUENTE" y las que nombran dependiente, camarero,
  recepcionista, conductor, teleoperador o closer.

Uso: python scripts/load_inbox_applications.py FICHERO [FICHERO...] [--save]
Orden recomendado: candidaturas_gmail → candidaturas_gmail_papelera → linkedin → n8n.
Sin --save el mismo código corre sobre una COPIA temporal de la BD (el informe es fiel) y no se guarda nada.
Con --save, tras guardar se BORRAN los ficheros cargados (regla: lo ya cargado no se acumula); se conserva
el que tenga filas dudosas, inválidas o comentarios «A REVISAR». Haz copia de job_hunter.db antes de --save."""
import argparse
import re
import sqlite3
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database  # noqa: E402
from automation.filter_engine import classify_track  # noqa: E402
from automation.generic_filter import primary_isolated_track  # noqa: E402
from inbox_files import delete_loaded  # noqa: E402
from database import (  # noqa: E402
    get_conn, init_db, record_application, upsert_company, upsert_contact, upsert_generic_offer, upsert_job_offer,
)

VALID = {"sent", "replied", "interview", "offer", "rejected", "rejected_manual"}
RANK = {"sent": 1, "replied": 2, "interview": 3, "offer": 4}
GMAIL = "https://mail.google.com/mail/u/0/"
SIN_CONFIRMAR = "Sin confirmar"
COMPANY_STOP = {"sa", "sl", "slu", "sau", "group", "grupo", "espana", "spain", "iberia", "iberica", "corp", "europe", "latam"}
GENERIC = {"consultor", "consultora", "consultant", "senior", "junior", "engineer", "developer", "ingeniero", "ingeniera",
           "candidatura", "application", "vacante", "perfil", "proceso", "seleccion",
           "sap", "con", "para", "del", "las", "los", "the", "and", "remoto", "remote", "ver", "gmail"}
UNSURE = re.compile(r"por confirmar|puesto no indicado|\(ver gmail|puesto seg[uú]n correo", re.I)
NO_COMPANY = re.compile(r"^\(?\s*por confirmar\s*\)?$", re.I)
BRIDGE = re.compile(r"dependiente|camarero|recepcionista|conductor|teleoperador|closer", re.I)


def strip(s: str) -> str:
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


def cnorm(name: str) -> str:
    name = re.sub(r"\(.*?\)", " ", strip(name))
    return "".join(w for w in re.findall(r"[a-z0-9]+", name) if w not in COMPANY_STOP)


def tokens(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", strip(re.sub(r"\(.*?\)", " ", title or ""))) if len(w) > 2}


def similarity(a: str, b: str) -> tuple[float, set[str]]:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0, set()
    shared = ta & tb
    return len(shared) / min(len(ta), len(tb)), {t for t in shared if t not in GENERIC and len(t) >= 5}


def same_company(a: str, b: str) -> bool:
    ca, cb = cnorm(a), cnorm(b)
    return bool(ca) and bool(cb) and (ca == cb or (min(len(ca), len(cb)) >= 4 and (ca.startswith(cb) or cb.startswith(ca))))


def parse(line: str):
    p = [x.strip() for x in line.split("|")]
    if len(p) < 6:
        return None
    return {"fecha": p[0], "empresa": p[1], "puesto": " | ".join(p[2:-3]).strip(), "email": p[-3], "estado": p[-2].lower(), "tid": p[-1]}


def read_lines(path: str):
    """Rinde (kind, text, bridge_section): kind 'row' para datos, 'review' para comentarios de «A REVISAR»."""
    section, bridge = "", False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            body = s.lstrip("#").strip()
            if body.startswith("====="):
                section = strip(body)
                bridge = "trabajo puente" in section
            elif "a revisar" in section and body:
                yield "review", body, False
            continue
        yield "row", s, bridge


def apps_of(conn, cids: list[str]) -> list[dict]:
    if not cids:
        return []
    q = ",".join("?" * len(cids))
    return [dict(x) for x in conn.execute(
        f"SELECT a.id, a.status, a.notes, jo.title FROM applications a LEFT JOIN job_offers jo ON jo.id=a.job_offer_id "
        f"WHERE a.company_id IN ({q})", cids)]


def find_match(conn, r: dict, apps: list[dict], pending: bool):
    """Devuelve (strong, weak). Con empresa «Sin confirmar» solo cuenta el thread id."""
    by_thread = [a for a in apps if r["tid"] and f"[gmail:{r['tid']}]" in (a["notes"] or "")]
    if r["tid"]:
        by_thread = by_thread or [dict(x) for x in conn.execute(
            "SELECT a.id, a.status, a.notes, jo.title FROM applications a LEFT JOIN job_offers jo ON jo.id=a.job_offer_id "
            "WHERE a.notes LIKE ?", (f"%[gmail:{r['tid']}]%",))]
        # un mismo hilo puede cubrir dos filas (p. ej. dos ofertas): exige también afinidad de puesto, salvo que
        # un puesto sea «(por confirmar)»: no tiene palabras que comparar y el hilo es lo único que lo identifica
        by_thread = [a for a in by_thread if UNSURE.search(r["puesto"]) or UNSURE.search(a["title"] or "")
                     or similarity(a["title"] or "", r["puesto"])[0] >= 0.5]
    if pending:
        return by_thread, []
    strong = by_thread or [a for a in apps if similarity(a["title"] or "", r["puesto"])[0] >= 0.6]
    weak = [] if strong else [a for a in apps if similarity(a["title"] or "", r["puesto"])[1]]
    return strong, weak


def track_for_title(title: str) -> str | None:
    """Track estándar de la config según el puesto; None si queda en manual_review."""
    track_id = classify_track({"title": title})[0]
    return None if track_id == "manual_review" else track_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    if not args.save:  # simulacro: mismo código, sobre una copia desechable de la BD
        tmp = Path(tempfile.mkdtemp()) / "job_hunter_dryrun.db"
        src, dst = sqlite3.connect(str(database.DB_PATH)), sqlite3.connect(str(tmp))
        src.backup(dst)
        src.close()
        dst.close()
        database.DB_PATH = tmp
    conn = get_conn()
    init_db(conn)
    isolated = primary_isolated_track()
    bridge_track_id = isolated.id if isolated else None
    companies = [dict(r) for r in conn.execute("SELECT id, name FROM companies")]
    rep = {"nuevas": [], "actualizadas": [], "sin_cambio": [], "dudosas": [], "invalidas": [], "por_revisar": []}

    pending_files: set[str] = set()  # ficheros con filas sin cargar: no se borran
    for f in args.files:
        unloaded = len(rep["dudosas"]) + len(rep["invalidas"])
        for kind, text, bridge in read_lines(f):
            if kind == "review":
                rep["por_revisar"].append(f"[comentario A REVISAR] {text}")
                pending_files.add(f)
                continue
            r = parse(text)
            tag = f"{r['empresa']} | {r['puesto'][:60]}" if r else text[:80]
            if r is None:
                rep["invalidas"].append(f"{tag}: formato incorrecto")
                continue
            if r["estado"] not in VALID:
                rep["invalidas"].append(f"{tag}: estado '{r['estado']}' no válido")
                continue
            pending = bool(NO_COMPANY.match(r["empresa"]))
            if pending:
                r["empresa"] = SIN_CONFIRMAR
                tag = f"{SIN_CONFIRMAR} | {r['puesto'][:60]}"
            if pending or UNSURE.search(r["empresa"] + " " + r["puesto"]):
                rep["por_revisar"].append(f"{tag} ({r['estado']})")
            generic = bool(bridge_track_id) and (bridge or bool(BRIDGE.search(r["puesto"])))  # sin track aislado, no hay «puente»
            cids = [c["id"] for c in companies if same_company(c["name"], r["empresa"])]
            apps = apps_of(conn, cids)
            strong, weak = find_match(conn, r, apps, pending)
            if strong:
                a = strong[0]
                old, new = a["status"], r["estado"]
                if old == "rejected" and new in ("replied", "interview"):
                    rep["dudosas"].append(f"{tag}: en BD está 'rejected' y el fichero dice '{new}' → no toco")
                elif old == new or old in ("rejected", "rejected_manual") or (RANK.get(new, 0) and RANK.get(old, 0) >= RANK[new]):
                    rep["sin_cambio"].append(f"{tag} (ya {old})")
                elif new == "rejected" and old == "interview":
                    rep["dudosas"].append(f"{tag}: en BD está 'interview' y el fichero dice 'rejected' → no toco")
                else:
                    rep["actualizadas"].append(f"{tag}: {old} → {new}")
                    conn.execute("UPDATE applications SET status=?, notes=COALESCE(notes,'')||? WHERE id=?",
                                 (new, f" | Estado actualizado a {new} (Gmail {r['fecha']}, {Path(f).name})", a["id"]))
                continue
            if weak:
                rep["dudosas"].append(f"{tag}: parecida a «{weak[0]['title']}» ({weak[0]['status']}) → no creo ni toco")
                continue
            meaningful = tokens(r["puesto"]) - tokens(r["empresa"]) - GENERIC
            if apps and not pending and not meaningful:
                rep["dudosas"].append(f"{tag}: puesto genérico y la empresa ya tiene {len(apps)} candidatura(s) (p. ej. «{apps[0]['title']}») → no creo")
                continue
            if not r["tid"]:
                rep["dudosas"].append(f"{tag}: sin gmail_thread_id y sin match claro en BD → no creo")
                continue
            cid = cids[0] if cids else upsert_company(conn, {"name": r["empresa"], "source": "portal" if r["tid"].startswith("portal-") else "gmail"})
            if not cids:
                companies.append({"id": cid, "name": r["empresa"]})
            contact_id = upsert_contact(conn, {"company_id": cid, "type": "email", "value": r["email"], "method": "gmail"}) if r["email"] else None
            slug = re.sub(r"[^a-z0-9]+", "-", strip(r["puesto"]))[:40]
            portal = r["tid"].startswith("portal-")
            offer = {"company_id": cid, "title": r["puesto"], "posted_at": r["fecha"], "source": "portal" if portal else "gmail",
                     "url": f"portal://job-hunter/{r['tid']}" if portal else f"{GMAIL}?p={slug}#all/{r['tid']}"}
            if generic:
                oid = upsert_generic_offer(conn, offer, bridge_track_id)
            else:
                oid = upsert_job_offer(conn, {**offer, "is_relevant": False, "relevance_score": 0.0})
            if oid is None:
                rep["dudosas"].append(f"{tag}: la URL de la oferta ya existe con otra categoría → no creo")
                continue
            cvp = bridge_track_id if generic else track_for_title(r["puesto"])
            record_application(conn, {"company_id": cid, "job_offer_id": oid, "contact_id": contact_id, "status": r["estado"],
                                      "method": "email" if r["email"] else "portal", "sent_at": r["fecha"], "cv_profile": cvp,
                                      "notes": f"Carga {Path(f).name} (Gmail {r['fecha']}){' [puente]' if generic else ''}. [gmail:{r['tid']}]"})
            rep["nuevas"].append(f"{tag} ({r['estado']}{', puente' if generic else ''})")
        if len(rep["dudosas"]) + len(rep["invalidas"]) > unloaded:
            pending_files.add(f)
    conn.commit()
    conn.close()
    titles = {"por_revisar": "Por revisar"}
    for k, v in rep.items():
        print(f"\n== {titles.get(k, k)}: {len(v)}")
        for x in (v if k != "sin_cambio" else []):
            print("  -", x)
    print("\n" + ("GUARDADO en job_hunter.db" if args.save else "(simulacro sobre copia temporal: la BD real no se ha tocado)"))
    if args.save:
        delete_loaded(args.files, pending_files)


if __name__ == "__main__":
    main()
