"""
automation/location.py — Única definición de modalidad (remoto / híbrido / presencial)
y de «está en la ciudad objetivo» para el dashboard, el scoring y la pretensión salarial.

Regla: un «híbrido» o «presencial» explícito junto a «remoto» no cuenta como remoto puro:
«Madrid (Híbrido) y remoto ocasional» sigue exigiendo desplazarse.
"""
from search_config import JobHunterConfig, get_config

REMOTE_MARKERS = ("remoto", "remote", "teletrabajo", "telework", "work from home", "home office")
HYBRID_MARKERS = ("híbrido", "hibrido", "hybrid")
ONSITE_MARKERS = ("presencial", "on-site", "onsite", "on site")

def in_target_area(location: str | None, cfg: JobHunterConfig | None = None) -> bool:
    """¿La ubicación está en la ciudad objetivo o su área (`scoring.location` de jobhunter.yaml)?
    Sin ciudad ni área configuradas devuelve False."""
    rule = (cfg or get_config()).scoring.location
    loc = (location or "").lower()
    return bool(rule.city and rule.city.lower() in loc) or any(town.lower() in loc for town in rule.area)


def parse_modality(location: str | None, title: str | None = None) -> str | None:
    """'remoto', 'hibrido' o 'presencial'; None si no hay ni ubicación ni título que mirar.

    La ubicación decide híbrido/presencial; «remoto» también se busca en el título
    («Developer 100% remoto» con ubicación «Madrid» es remoto).
    """
    loc = (location or "").lower()
    text = f"{loc} {(title or '').lower()}".strip()
    if not text:
        return None
    if any(m in loc for m in HYBRID_MARKERS):
        return "hibrido"
    if any(m in loc for m in ONSITE_MARKERS):
        return "presencial"
    if any(m in text for m in REMOTE_MARKERS):
        return "remoto"
    # Hay una ubicación concreta (ciudad) sin modalidad ni «remoto»: presencial.
    return "presencial" if loc.strip() else None
