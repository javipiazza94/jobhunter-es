"""
automation/language_gate.py — Filtro de idiomas de una oferta frente a los del perfil.

Idea tomada del "Language Gate" de MadsLorentzen/ai-job-search (04-job-evaluation.md):
  * la oferta EXIGE un idioma que el candidato no declara → 'reject' (score_offer devuelve 0);
  * exige un idioma que sí declara pero a más nivel del que tiene → 'flag' (solo aviso: es un
    caso dudoso, decide el usuario; no toca la puntuación);
  * si el idioma solo es valorable / nice to have → no cuenta.

Idiomas del candidato: `languages` de profile.json (idioma + nivel MCER). Español nativo
siempre se da por hecho.
"""
import json
import re
import unicodedata
from functools import lru_cache

from config import PROFILE_PATH

# nombre canónico → variantes (es/en) que aparecen en las ofertas; la forma sin tilde de cada
# variante se añade sola (ver _with_unaccented).
_BASE_LANGUAGES = {
    "español": ["español", "castellano", "spanish"],
    "inglés": ["inglés", "english"],
    "italiano": ["italiano", "italian"],
    "alemán": ["alemán", "german", "deutsch"],
    "francés": ["francés", "french"],
    "portugués": ["portugués", "portuguese"],
    "neerlandés": ["neerlandés", "holandés", "dutch"],
    "catalán": ["catalán", "català"],
    "euskera": ["euskera", "basque"],
    "polaco": ["polaco", "polish"],
    "checo": ["checo", "czech"],
    "sueco": ["sueco", "swedish"],
    "danés": ["danés", "danish"],
    "noruego": ["noruego", "norwegian"],
    "finés": ["finés", "finlandés", "finnish"],
    "japonés": ["japonés", "japanese"],
    "chino": ["chino", "mandarín", "mandarin", "chinese"],
    "árabe": ["árabe", "arabic"],
    "ruso": ["ruso", "russian"],
}
# Sin tilde serían palabras corrientes ("fines") y darían falsos positivos.
_NO_UNACCENTED = {"finés"}


def _strip_accents(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode()


def _with_unaccented(variants: list[str]) -> list[str]:
    out = list(variants)
    for v in variants:
        bare = _strip_accents(v)
        if v not in _NO_UNACCENTED and bare not in out:
            out.append(bare)
    return out


LANGUAGES = {canon: _with_unaccented(variants) for canon, variants in _BASE_LANGUAGES.items()}

_LEVELS = {"a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5, "c2": 6}
# palabras que equivalen a un nivel MCER
_LEVEL_WORDS = {
    "nativo": 7, "native": 7, "bilingüe": 7, "bilingue": 7, "bilingual": 7, "mother tongue": 7,
    "fluido": 5, "fluent": 5, "fluency": 5, "fluidez": 5, "avanzado": 5, "advanced": 5,
    "proficient": 5, "proficiency": 5, "nivel alto": 5, "alto nivel": 5, "high level": 5,
    "business level": 5, "dominio": 5, "excelente": 5, "excellent": 5,
}
_REQUIRED = re.compile(
    r"\b(imprescindible|obligatori[oa]|requisito|requerid[oa]|necesari[oa]|indispensable|"
    r"required|mandatory|essential|exigid[oa]|se requiere)\b", re.I)
_NICE_TO_HAVE = re.compile(
    r"(valorable|se valorar[aá]|valoraremos|valorar[aá]|deseable|preferible|\bplus\b|nice to have|"
    r"\bbonus\b|advantage|ventaja|\bideally\b|idealmente|would be (a )?(plus|great)|is a plus|desirable|"
    r"te har[aá] destacar|destacar[aá]s|puntos extra|nice-to-have)",
    re.I)
_LEVEL_RX = re.compile(
    r"\b(a1|a2|b1|b2|c1|c2)\b|" + "|".join(rf"\b{re.escape(w)}\b" for w in _LEVEL_WORDS), re.I)
# frase = trozo entre puntos, punto y coma o viñetas (las líneas se recorren aparte)
_SENTENCE_SPLIT = re.compile(r"[.;•·]+")
_WINDOW = 35  # máximo de caracteres a cada lado de la mención, dentro de su cláusula
# "Muy valorable:" / "Requisitos:" — cabecera de sección (corta y acaba en dos puntos)
_HEADER = re.compile(r"^\s*[^:\n]{0,40}:\s*$")


def _level_value(text: str) -> int:
    """Nivel pedido en el texto (0 si no se pide ninguno). Un código MCER explícito manda sobre
    las palabras: "nivel alto de inglés (B2)" es B2."""
    tokens = [m.group(0).lower() for m in _LEVEL_RX.finditer(text)]
    codes = [_LEVELS[t] for t in tokens if t in _LEVELS]
    if codes:
        return max(codes)
    return max((_LEVEL_WORDS.get(t, 0) for t in tokens), default=0)


def _parse_profile_level(level: str) -> int:
    level = (level or "").lower()
    m = re.search(r"\b(a1|a2|b1|b2|c1|c2)\b", level)
    if m:
        return _LEVELS[m.group(1)]
    return max((v for w, v in _LEVEL_WORDS.items() if w in level), default=0)


def _canonical(name: str) -> str | None:
    name = (name or "").strip().lower()
    for canon, variants in LANGUAGES.items():
        if name == canon or name in variants:
            return canon
    return None


@lru_cache(maxsize=1)
def candidate_languages() -> dict[str, int]:
    """{idioma canónico: nivel} según profile.json; español nativo por defecto."""
    langs = {"español": 7}
    try:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return langs
    for entry in profile.get("languages") or []:
        canon = _canonical(entry.get("language", ""))
        if canon:
            langs[canon] = max(langs.get(canon, 0), _parse_profile_level(entry.get("level", "")))
    return langs


def _mentions(text: str, variants: list[str]):
    rx = re.compile(r"(?<![\w])(" + "|".join(re.escape(v) for v in variants) + r")(?![\w])", re.I)
    return rx.finditer(text)


def _clause(sentence: str, start: int, end: int) -> str:
    """Texto alrededor de la mención sin cruzar comas: en "catalán nativo, inglés B2" el
    "nativo" es del catalán, no del inglés."""
    left = sentence.rfind(",", 0, start) + 1
    right = sentence.find(",", end)
    right = len(sentence) if right == -1 else right
    return sentence[max(left, start - _WINDOW): min(right, end + _WINDOW)]


def _sentences(text: str):
    """Frases del texto, saltando las que caen bajo una cabecera de 'valorable' ("Muy valorable:",
    "Nice to have:") hasta la siguiente cabecera o línea en blanco."""
    in_nice_section = False
    for line in text.splitlines():
        if not line.strip():
            in_nice_section = False
            continue
        if _HEADER.match(line):
            in_nice_section = bool(_NICE_TO_HAVE.search(line))
            continue
        if in_nice_section:
            continue
        yield from _SENTENCE_SPLIT.split(line)


def language_gate(offer: dict) -> tuple[str, list[str]]:
    """Devuelve ('ok'|'flag'|'reject', motivos)."""
    text = f"{offer.get('title') or ''}\n{offer.get('description') or ''}"
    if not text.strip():
        return "ok", []
    have = candidate_languages()
    known = [v for canon in have for v in LANGUAGES.get(canon, [])]
    alternative = re.compile(
        r"(?:(?<![\w])(?:" + "|".join(map(re.escape, known)) + r")\s+(?:o|or|y/o|and/or)\s+$)", re.I)
    rejects, flags = [], []
    for sentence in _sentences(text):
        if _NICE_TO_HAVE.search(sentence):
            continue  # "inglés C1 valorable", "German is a plus"
        for canon, variants in LANGUAGES.items():
            for m in _mentions(sentence, variants):
                if alternative.search(sentence[max(0, m.start() - 25): m.start()]):
                    continue  # "español o catalán nativo": vale cualquiera de los dos
                around = _clause(sentence, m.start(), m.end())
                wanted = _level_value(around)
                required = wanted > 0 or bool(_REQUIRED.search(around))
                if not required:
                    continue
                if canon not in have:
                    reason = f"idioma: exige {canon}, que no tienes"
                    if reason not in rejects:
                        rejects.append(reason)
                elif wanted > have[canon]:
                    reason = f"idioma: pide {canon} a más nivel del tuyo"
                    if reason not in flags:
                        flags.append(reason)
                break  # una mención por idioma y frase basta
    if rejects:
        return "reject", rejects + flags
    if flags:
        return "flag", flags
    return "ok", []
