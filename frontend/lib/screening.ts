// Utilidades puras de las preguntas de cribado (pegar preguntas, editar las respuestas guardadas).
import type { ScreeningAnswerSaved, ScreeningQuestion } from "@/lib/types";
import type { StoredProfile } from "@/lib/setup";

/** Una pregunta por línea; sufijo opcional «(max N)» / «(máx N)» / «(max N caracteres)» = límite de caracteres. */
const LIMIT_SUFFIX = /\s*\(\s*m[aá]x\.?\s*(\d{1,5})\s*(?:car[aá]cteres|caracteres|chars?|characters)?\s*\)\s*$/i;

export function parseQuestions(text: string): ScreeningQuestion[] {
  const out: ScreeningQuestion[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const m = LIMIT_SUFFIX.exec(line);
    const body = (m ? line.slice(0, m.index) : line).trim();
    if (!body) continue;
    const max = m ? Number(m[1]) : 0;
    out.push(max > 0 ? { text: body, max_chars: max } : { text: body });
  }
  return out;
}

/** Respuestas guardadas del perfil, tolerando datos mal formados escritos a mano en profile.json. */
export function savedAnswers(profile: StoredProfile): ScreeningAnswerSaved[] {
  const raw = profile.screening_answers;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap(item => {
    const o = (item ?? {}) as Record<string, unknown>;
    return typeof o.question === "string" && typeof o.answer === "string" ? [{ question: o.question, answer: o.answer }] : [];
  });
}

/** Perfil con las respuestas sustituidas (las filas sin pregunta se descartan). Conserva el resto del perfil. */
export function withSavedAnswers(profile: StoredProfile, items: ScreeningAnswerSaved[]): StoredProfile {
  return {
    ...profile,
    screening_answers: items
      .map(i => ({ question: i.question.trim(), answer: i.answer.trim() }))
      .filter(i => i.question),
  };
}
