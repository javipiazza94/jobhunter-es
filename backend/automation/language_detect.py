"""automation/language_detect.py — Detección determinista y ligera del idioma de una oferta.

Detecta es, en, de, fr, it o pt a partir de la frecuencia de palabras funcionales (stopwords) sobre
texto normalizado. Si el texto tiene menos de 20 palabras o el resultado es dudoso (empate o
margen de confianza estrecho), devuelve `None`.
"""
from __future__ import annotations

import re
import unicodedata

MIN_WORDS = 20
CONFIDENCE_RATIO = 1.25  # El primero debe superar al segundo por al menos un 25%
MIN_STOPWORD_HITS = 3

# Palabras funcionales representativas y distintivas por idioma (en minúsculas y sin tildes)
STOPWORDS: dict[str, set[str]] = {
    "es": {
        "de", "la", "el", "en", "y", "a", "los", "del", "se", "las", "por", "un", "para", "con",
        "no", "una", "su", "al", "lo", "como", "mas", "pero", "sus", "le", "ya", "o", "fue",
        "este", "ha", "si", "sobre", "entre", "cuando", "todo", "esta", "ser", "son", "dos",
        "tambien", "era", "muy", "hasta", "desde", "nos", "durante", "todos", "uno", "les", "ni",
        "contra", "otros", "fueron", "ese", "eso", "habia", "ante", "ellos", "esto", "mi", "antes",
        "nuestro", "nuestra", "trabajo", "experiencia", "requisitos", "equipo", "funciones",
    },
    "en": {
        "the", "and", "to", "of", "a", "in", "that", "is", "was", "for", "it", "with", "as",
        "his", "on", "be", "at", "by", "this", "had", "not", "are", "but", "from", "or",
        "have", "an", "they", "which", "one", "you", "were", "her", "all", "she", "there",
        "would", "their", "we", "been", "has", "when", "who", "will", "more", "if", "out",
        "so", "up", "its", "about", "into", "than", "them", "can", "only", "other", "some",
        "could", "time", "these", "may", "then", "do", "any", "my", "now", "such", "like",
        "our", "over", "even", "most", "after", "also", "should", "work", "experience", "team",
    },
    "de": {
        "der", "die", "und", "in", "den", "von", "zu", "das", "mit", "sich", "des", "auf",
        "fur", "ist", "im", "dem", "nicht", "ein", "eine", "als", "auch", "es", "an", "werden",
        "aus", "er", "hat", "dass", "sie", "nach", "wird", "bei", "einer", "um", "am", "sind",
        "noch", "wie", "einem", "uber", "einen", "so", "zum", "war", "haben", "nur", "oder",
        "aber", "vor", "zur", "bis", "mehr", "durch", "man", "sein", "wurde", "kann", "gegen",
        "wir", "ihre", "ihr", "uns", "unsere", "erfahrung", "aufgaben", "profil", "bewerbung",
    },
    "fr": {
        "de", "la", "le", "et", "les", "des", "en", "un", "du", "une", "que", "est", "pour",
        "qui", "dans", "par", "plus", "pas", "au", "sur", "ne", "ce", "avec", "il", "ont",
        "ses", "mais", "comme", "on", "ou", "nous", "sa", "cette", "son", "aux", "ete",
        "sont", "ils", "vous", "leur", "elle", "tout", "faire", "deux", "sans", "aussi",
        "ces", "bien", "peut", "apres", "votre", "vos", "notre", "nos", "travail", "equipe",
    },
    "it": {
        "di", "il", "la", "che", "in", "un", "per", "del", "non", "dei", "della", "le", "una",
        "si", "da", "delle", "con", "sono", "ed", "ha", "su", "alla", "nel", "dalla", "degli",
        "gli", "come", "dello", "ma", "ci", "dal", "anche", "ad", "uno", "alle", "nei", "ai",
        "dall", "nella", "loro", "lo", "tra", "questa", "questo", "nelle", "piu", "agli",
        "questi", "sul", "dalle", "fra", "nostro", "nostra", "vostro", "vostra", "lavoro",
    },
    "pt": {
        "de", "que", "do", "da", "em", "um", "para", "com", "nao", "uma", "os", "no", "se",
        "na", "por", "mais", "as", "dos", "como", "mas", "ao", "ele", "das", "tem", "seu",
        "sua", "ou", "quando", "muito", "nos", "ja", "eu", "tambem", "so", "pelo", "pela",
        "ate", "isso", "ela", "entre", "depois", "sem", "mesmo", "aos", "seus", "quem", "nas",
        "voce", "tinha", "foram", "essa", "num", "nem", "suas", "meu", "minha", "numa", "pelos",
        "qual", "lhe", "deles", "nosso", "nossa", "nossos", "nossas", "trabalho", "vaga",
        "experiencia", "equipa", "equipe", "estamos", "desenvolvimento", "desenvolvedor",
        "funcao", "procura", "trabalhar", "solucoes",
    },
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> list[str]:
    """Minúsculas, sin tildes, lista de palabras alfanuméricas."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _WORD_RE.findall(ascii_text)


def detect_language(text: str | None) -> str | None:
    """Detecta el idioma (es, en, de, fr, it, pt) o `None` si no es seguro o faltan palabras."""
    if not text:
        return None

    words = _normalize(text)
    if len(words) < MIN_WORDS:
        return None

    scores: dict[str, int] = {}
    for lang, stoplist in STOPWORDS.items():
        hits = sum(1 for w in words if w in stoplist)
        scores[lang] = hits

    sorted_langs = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_lang, best_hits = sorted_langs[0]
    second_lang, second_hits = sorted_langs[1]

    if best_hits < MIN_STOPWORD_HITS:
        return None

    # Margen de confianza sobre el segundo clasificado (diferencia de al menos 2 y ratio razonable)
    if second_hits > 0:
        if (best_hits - second_hits) < 2 or best_hits < (second_hits * 1.12):
            return None

    return best_lang
