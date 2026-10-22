"use client";

import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { evaluateOffer, fetchOfferEvaluation } from "@/lib/api";
import type { EvaluationBatchResult, OfferEvaluation } from "@/lib/types";

// Textos de la interfaz en un solo sitio (la traducción llega en SP4).
export const T = {
  title: "Evaluación con IA",
  button: "Evaluar con IA",
  reevaluate: "Volver a evaluar",
  busy: "Evaluando con IA…",
  strengths: "Puntos fuertes",
  gaps: "Huecos",
  note: "Opinión aparte: no cambia el score de la oferta.",
  evaluatedAt: (date: string, provider: string) => `Evaluada el ${date} con ${provider}`,
  bulkBusy: (n: number) => `Evaluando con IA ${n} oferta${n === 1 ? "" : "s"}...`,
  bulkEvaluated: (n: number) => `${n} evaluada${n === 1 ? "" : "s"}`,
  bulkSkipped: (n: number) => `${n} sin evaluar (presupuesto de IA agotado; vuelve a intentarlo)`,
  bulkFailed: (n: number) => `${n} con error`,
  verdicts: {
    "Strong Fit": "Encaje fuerte",
    "Good Fit": "Buen encaje",
    "Moderate Fit": "Encaje moderado",
    "Weak Fit": "Encaje débil",
    "Poor Fit": "Encaje bajo",
  } as Record<string, string>,
  urgency: {
    expired: "Caducada",
    urgent: "Cierra en menos de una semana",
    normal: "Plazo abierto",
    unknown: "",
  } satisfies Record<OfferEvaluation["urgency"], string>,
};

/** Veredicto en español (las bandas vienen de rank_state en inglés). */
export function verdictLabel(verdict: string): string {
  return T.verdicts[verdict] ?? verdict;
}

/** Resumen de un lote para la barra de acciones (solo lo que no es cero, salvo las evaluadas). */
export function batchSummary(r: Pick<EvaluationBatchResult, "evaluated" | "skipped" | "failed">): string {
  const parts = [T.bulkEvaluated(r.evaluated)];
  if (r.skipped) parts.push(T.bulkSkipped(r.skipped));
  if (r.failed) parts.push(T.bulkFailed(r.failed));
  return parts.join(", ");
}

/** Color del veredicto según la nota global (mismas bandas que /rank: 75, 60, 45). */
export function verdictClass(score: number): string {
  if (score >= 75) return "bg-green-500/10 text-green-400 border-green-500/20";
  if (score >= 60) return "bg-emerald-500/10 text-emerald-300 border-emerald-500/20";
  if (score >= 45) return "bg-yellow-500/10 text-yellow-400 border-yellow-500/20";
  return "bg-gray-500/10 text-gray-400 border-gray-500/20";
}

/** Evaluación detallada con IA de una oferta (/rank en la app). Si no hay IA configurada, la API responde
 *  409 y se muestra su mensaje. `initialEvaluation` undefined = la carga al montarse. */
export function OfferEvaluationPanel({ offerId, initialEvaluation, initialError = "", onEvaluated }: {
  offerId: string;
  initialEvaluation?: OfferEvaluation | null;
  initialError?: string;
  onEvaluated?: (evaluation: OfferEvaluation) => void;
}) {
  const [evaluation, setEvaluation] = useState<OfferEvaluation | null>(initialEvaluation ?? null);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (initialEvaluation !== undefined) return;
    let alive = true;
    fetchOfferEvaluation(offerId)
      .then(e => { if (alive && e) setEvaluation(e); })
      .catch(() => { /* sin evaluación guardada: se ofrece evaluar */ });
    return () => { alive = false; };
  }, [offerId, initialEvaluation]);

  const evaluate = async () => {
    setBusy(true);
    setError("");
    try {
      const e = await evaluateOffer(offerId);
      setEvaluation(e);
      onEvaluated?.(e);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const urgency = evaluation ? T.urgency[evaluation.urgency] : "";

  return (
    <div className="mb-6 p-4 rounded-xl bg-indigo-500/5 border border-indigo-500/20 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xs font-semibold text-indigo-300 uppercase tracking-wider">{T.title}</h3>
        <button
          onClick={evaluate}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-3 py-1.5 text-sm font-medium text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {busy ? T.busy : evaluation ? T.reevaluate : T.button}
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      {evaluation && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`px-3 py-1 rounded-lg text-sm font-bold border ${verdictClass(evaluation.score)}`}>
              {verdictLabel(evaluation.verdict)} · {evaluation.score}/100
            </span>
            {urgency && (
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-md border ${evaluation.expired ? "bg-red-500/10 text-red-300 border-red-500/20" : "bg-amber-500/10 text-amber-300 border-amber-500/20"}`}>
                {urgency}
              </span>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <PointList title={T.strengths} items={evaluation.strengths} className="text-green-300/90" />
            <PointList title={T.gaps} items={evaluation.gaps} className="text-amber-200/90" />
          </div>
          <p className="text-xs text-gray-500">
            {T.note} {T.evaluatedAt(evaluation.evaluated_at.slice(0, 10), evaluation.provider)}
          </p>
        </div>
      )}
    </div>
  );
}

function PointList({ title, items, className }: { title: string; items: string[]; className: string }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">{title}</h4>
      <ul className={`text-sm space-y-1 list-disc list-inside ${className}`}>
        {items.map(item => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}
