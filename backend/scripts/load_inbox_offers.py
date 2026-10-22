"""Carga ofertas dejadas en JH_HOME/inbox/ (a mano o por un agente externo), una por línea:
    tipo|título|empresa|ubicación|url|fecha(AAAA-MM-DD)|contrato|nota
con tipo = id de un track de jobhunter.yaml (o un alias antiguo de LEGACY_TIPOS).

- Track aislado (kind: isolated) → filtro/score de ese track (job_kind='generic').
- Track estándar → oferta normal: score_offer + upsert_job_offer. NUNCA envía nada; las candidaturas
  siguen requiriendo generar borradores y aprobarlos en el dashboard.
- Dedupe: por URL y, como los enlaces cortos de Indeed cambian en cada búsqueda, también por
  empresa+título. Avisa si la empresa ya tiene candidaturas (evita duplicados).

Uso: python scripts/load_inbox_offers.py FICHERO [FICHERO...] [--save] [--max-age-days 60]
Sin --save solo muestra qué se haría. Haz copia de job_hunter.db antes de usar --save.
Con --save, tras guardar se BORRAN los ficheros cargados (regla: lo ya cargado no se acumula); se conserva
el que tenga líneas con mal formato."""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automation.filter_engine import score_offer  # noqa: E402
from automation.generic_filter import isolated_min_score, primary_isolated_track, score_isolated  # noqa: E402
from automation.offer_review import apply_hard_requirements, review_offer  # noqa: E402
from search_config import Track, get_config  # noqa: E402
from database import get_conn, init_db, upsert_company, upsert_generic_offer, upsert_job_offer  # noqa: E402
from inbox_files import delete_loaded  # noqa: E402

# Compatibilidad con ficheros anteriores a los tracks configurables: alias -> clase de track.
# "puente" usa el primer track aislado de la config.
LEGACY_TIPOS = {"sap": "standard", "ia": "standard", "puente": "isolated"}

# Portal de la URL -> valor de `source`; el resto (webs de empresa, otros portales) queda como "inbox".
KNOWN_SOURCES = ("indeed", "linkedin", "infojobs", "tecnoempleo", "computrabajo", "glassdoor",
                 "remotive", "remoteok", "arbeitnow", "welcometothejungle", "stepstone")


def source_from_url(url: str) -> str:
    """Fuente de una oferta del inbox según el dominio de su URL ('inbox' si no es un portal conocido)."""
    host = (urlparse(url or "").hostname or "").lower()
    return next((s for s in KNOWN_SOURCES if s in host.split(".")), "inbox")


def resolve_tipo(tipo: str) -> tuple[str, Track | None] | None:
    """('standard', None) | ('isolated', track) | None si el tipo no es un track ni un alias.
    Un alias "puente" sin track aislado en la config devuelve ('isolated', None): se descarta en el filtro."""
    tipo = tipo.strip().lower()
    track = get_config().track(tipo)
    if track is not None:
        return (track.kind, track if track.kind == "isolated" else None)
    legacy = LEGACY_TIPOS.get(tipo)
    if legacy == "isolated":
        return ("isolated", primary_isolated_track())
    if legacy == "standard":
        return ("standard", None)
    return None


def parse_line(line: str) -> dict | None:
    parts = [p.strip() for p in line.split("|")]
    # el título puede contener '|': tipo va primero y los 6 últimos campos son fijos
    if len(parts) < 8 or resolve_tipo(parts[0]) is None:
        return None
    company, location, url, posted, contract, nota = parts[-6:]
    return {"tipo": parts[0].lower(), "title": " | ".join(parts[1:-6]).strip(), "company_name": company,
            "location": location, "url": url, "posted_at": posted or None,
            "contract": contract, "nota": nota}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--max-age-days", type=int, default=60)
    args = ap.parse_args()

    conn = get_conn()
    init_db(conn)
    cutoff = (date.today() - timedelta(days=args.max_age_days)).isoformat()
    seen: set[tuple] = set()
    plan, stats = [], {"lineas": 0, "mal_formato": 0, "duplicadas": 0, "ya_en_bd": 0, "antiguas": 0, "filtro": 0}

    bad_files: set[str] = set()  # con líneas sin interpretar: no se borran
    for f in args.files:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            stats["lineas"] += 1
            o = parse_line(line)
            if o is None:
                stats["mal_formato"] += 1
                bad_files.add(f)
                print(f"  ! mal formato: {line[:90]}")
                continue
            key = (o["title"].lower(), o["company_name"].lower())
            if key in seen:
                stats["duplicadas"] += 1
                continue
            seen.add(key)
            if o["posted_at"] and o["posted_at"] < cutoff:
                stats["antiguas"] += 1
                continue
            if conn.execute("SELECT 1 FROM job_offers jo JOIN companies c ON c.id=jo.company_id "
                            "WHERE jo.url=? OR (LOWER(jo.title)=LOWER(?) AND LOWER(c.name)=LOWER(?))",
                            (o["url"], o["title"], o["company_name"])).fetchone():
                stats["ya_en_bd"] += 1
                continue
            desc = ". ".join(x for x in (o["contract"], o["nota"]) if x) or None
            offer = {"title": o["title"], "company_name": o["company_name"], "location": o["location"],
                     "url": o["url"], "posted_at": o["posted_at"], "description": desc, "source": source_from_url(o["url"])}
            kind, track = resolve_tipo(o["tipo"])
            if kind == "isolated":
                s = score_isolated({**offer, "description": o["contract"] or None}, track) if track else None
                if s is None or s < isolated_min_score(track):
                    stats["filtro"] += 1
                    continue
                plan.append({**offer, "tipo": o["tipo"], "isolated": True, "score": s, "track_id": track.id})
            else:
                # el score se calcula sin la nota (son comentarios de quien dejó el fichero, no texto de la oferta)
                s = score_offer({**offer, "description": o["contract"] or None})
                plan.append({**offer, "tipo": o["tipo"], "score": s})

    for o in plan:
        apps = conn.execute(
            "SELECT a.status FROM applications a JOIN companies c ON c.id=a.company_id "
            "WHERE LOWER(c.name)=LOWER(?)", (o["company_name"],)).fetchall()
        o["prev"] = ",".join(sorted({r["status"] for r in apps}))
    plan.sort(key=lambda o: (o["tipo"], -o["score"]))
    print(stats, "-> a cargar:", len(plan))
    for o in plan:
        flag = f"  [ya hay candidatura: {o['prev']}]" if o["prev"] else ""
        rel = ""
        if not o.get("isolated"):
            rel = " REL" if o["score"] >= get_config().scoring.min_relevance else " (bajo umbral)"
        print(f"  {o['tipo']:6} {o['score']:.2f}{rel} | {o['title'][:60]} | {o['company_name']} | {o['location']}{flag}")
    if not args.save:
        print("(sin --save: no se ha guardado nada)")
        return

    saved = skipped = 0
    for o in plan:
        cid = upsert_company(conn, {"name": o["company_name"], "source": o["source"]})
        base = {k: o[k] for k in ("title", "location", "url", "posted_at", "description", "source")}
        if o.get("isolated"):
            r = upsert_generic_offer(conn, {**base, "company_id": cid, "generic_score": o["score"]}, o["track_id"])
        else:
            base = review_offer(base)  # posting_guard + idiomas → review_flags
            score, base = apply_hard_requirements(base, o["score"])  # 0 si incumple un requisito duro (opt-in)
            r = upsert_job_offer(conn, {**base, "company_id": cid, "relevance_score": score,
                                        "is_relevant": score >= get_config().scoring.min_relevance})
        saved, skipped = (saved + 1, skipped) if r else (saved, skipped + 1)
    conn.close()
    print(f"guardadas={saved} omitidas={skipped}")
    delete_loaded(args.files, bad_files)


if __name__ == "__main__":
    main()
