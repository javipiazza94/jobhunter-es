"use client";

import { useState } from "react";
import { Loader2, MessageSquareText } from "lucide-react";
import { answerScreeningQuestions } from "@/lib/api";
import { parseQuestions } from "@/lib/screening";
import type { ScreeningAnswer, ScreeningSource } from "@/lib/types";

// Textos de la interfaz en un solo sitio (la traducción llega en SP4).
export const T = {
  title: "Responder preguntas",
  hint: "Pega las preguntas del formulario, una por línea. Añade «(max N)» al final para limitar los caracteres.",
  placeholder: "¿Por qué quieres trabajar con nosotros? (max 500)\n¿Cuál es tu pretensión salarial?",
  button: "Responder preguntas",
  busy: "Respondiendo…",
  empty: "Escribe al menos una pregunta.",
  copy: "Copiar",
  copied: "Copiada",
  noAnswer: "Sin respuesta: añade este dato en Perfil → Respuestas de cribado.",
  chars: (n: number) => `${n} caracteres`,
  sources: { profile: "perfil", ai: "IA", needs_input: "falta dato" } as Record<ScreeningSource, string>,
};

const BADGE: Record<ScreeningSource, string> = {
  profile: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  ai: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  needs_input: "bg-amber-500/15 text-amber-300 border-amber-500/30",
};

/** Respuestas a preguntas de cribado de una candidatura: solo perfil, respuestas guardadas y (si hay IA) hechos
 *  del perfil. Nunca envía nada: el usuario copia cada respuesta al formulario. */
export function ScreeningPanel({ applicationId, initialText = "", initialAnswers = [], initialError = "" }: {
  applicationId: string;
  initialText?: string;
  initialAnswers?: ScreeningAnswer[];
  initialError?: string;
}) {
  const [text, setText] = useState(initialText);
  const [answers, setAnswers] = useState<ScreeningAnswer[]>(initialAnswers);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);

  const run = async () => {
    const questions = parseQuestions(text);
    if (!questions.length) { setError(T.empty); return; }
    setBusy(true);
    setError("");
    try {
      setAnswers((await answerScreeningQuestions(applicationId, questions)).answers);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const copy = async (i: number) => {
    try {
      await navigator.clipboard.writeText(answers[i].answer);
      setCopied(i);
    } catch {
      setError("No se pudo copiar automáticamente: selecciona el texto a mano.");
    }
  };

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-gray-200">{T.title}</h4>
      <p className="text-xs text-gray-500">{T.hint}</p>
      <textarea
        aria-label={T.title}
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder={T.placeholder}
        rows={4}
        className="w-full text-xs font-mono text-gray-300 border border-white/10 rounded-xl p-3 resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/50 bg-[#16161f]"
      />
      <button
        onClick={run}
        disabled={busy}
        className="inline-flex items-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50"
      >
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <MessageSquareText className="w-4 h-4" />}
        {busy ? T.busy : T.button}
      </button>
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      {answers.length > 0 && (
        <ul className="space-y-2">
          {answers.map((a, i) => (
            <li key={i} className="rounded-lg border border-white/10 bg-black/20 p-3 space-y-1.5">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm text-gray-300">{a.question}</p>
                <span className={`shrink-0 text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-md font-bold border ${BADGE[a.source]}`}>
                  {T.sources[a.source]}
                </span>
              </div>
              {a.source === "needs_input" ? (
                <p className="text-xs text-amber-300">{T.noAnswer}</p>
              ) : (
                <>
                  <p className="whitespace-pre-wrap text-sm text-gray-100">{a.answer}</p>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <button className="text-indigo-300 hover:text-indigo-200" onClick={() => copy(i)}>
                      {copied === i ? T.copied : T.copy}
                    </button>
                    <span>{T.chars(a.answer.length)}</span>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
