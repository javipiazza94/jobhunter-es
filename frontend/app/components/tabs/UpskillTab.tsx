"use client";

import { useState } from "react";
import { GraduationCap, Loader2 } from "lucide-react";
import { runUpskill } from "@/lib/api";
import { parseReport } from "@/lib/report";
import type { UpskillReport, UpskillScope } from "@/lib/types";

// Textos de la interfaz en un solo sitio (la traducción llega en SP4).
export const T = {
  title: "Upskill",
  hint: "Mapa de huecos: qué piden tus ofertas que tu perfil aún no respalda, con un plan de estudio si hay IA. Los recursos que sugiere la IA no están verificados.",
  scope: "Ofertas a analizar",
  scopes: { saved: "Guardadas (relevantes)", evaluated: "Evaluadas con IA", applied: "Con candidatura" } as Record<string, string>,
  button: "Generar mapa de huecos",
  busy: "Analizando ofertas…",
  saved: (path: string) => `Informe guardado en ${path}`,
  analyzed: (n: number) => `${n} oferta(s) analizadas`,
};

const SCOPES: UpskillScope[] = ["saved", "evaluated", "applied"];

/** Pantalla «Upskill»: lanza el mapa de huecos y muestra el informe Markdown como texto (sin HTML crudo). */
export function UpskillTab({ initialReport = null, initialError = "" }: { initialReport?: UpskillReport | null; initialError?: string }) {
  const [scope, setScope] = useState<UpskillScope>("saved");
  const [report, setReport] = useState<UpskillReport | null>(initialReport);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      setReport(await runUpskill(scope));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="glass-card p-6 space-y-4 animate-fade-in max-w-3xl">
      <h3 className="text-base font-semibold text-white flex items-center gap-2"><GraduationCap className="w-5 h-5" /> {T.title}</h3>
      <p className="text-xs text-gray-500">{T.hint}</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-gray-400 space-y-1">
          <span className="block">{T.scope}</span>
          <select
            value={scope}
            onChange={e => setScope(e.target.value as UpskillScope)}
            className="rounded-lg border border-white/10 bg-[#16161f] px-3 py-2 text-sm text-gray-200"
          >
            {SCOPES.map(s => <option key={s} value={s}>{T.scopes[s]}</option>)}
          </select>
        </label>
        <button
          onClick={run}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <GraduationCap className="w-4 h-4" />}
          {busy ? T.busy : T.button}
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      {report && (
        <div className="space-y-2" data-testid="upskill-report">
          <p className="text-xs text-gray-500">{T.analyzed(report.offers_analyzed)} · {T.saved(report.report_path)}</p>
          {parseReport(report.markdown).map((b, i) =>
            b.kind === "heading" ? (
              <h4 key={i} className={b.level === 1 ? "text-lg font-semibold text-white" : "text-sm font-semibold text-gray-200 pt-2"}>{b.text}</h4>
            ) : b.kind === "item" ? (
              <p key={i} className="text-sm text-gray-300 pl-4 -indent-3">{"• "}{b.text}</p>
            ) : (
              <p key={i} className="text-sm text-gray-400">{b.text}</p>
            ),
          )}
        </div>
      )}
    </div>
  );
}
