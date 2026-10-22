"use client";

import { useEffect, useState } from "react";
import { Building2, Loader2 } from "lucide-react";
import { fetchCompanyResearch, researchCompany } from "@/lib/api";
import type { CompanyResearch } from "@/lib/types";

// Textos de la interfaz en un solo sitio (la traducción llega en SP4).
export const T = {
  title: "Investigación de la empresa",
  button: "Investigar empresa",
  refresh: "Volver a investigar",
  busy: "Investigando la empresa…",
  products: "Productos y servicios",
  culture: "Cultura",
  tech: "Tecnologías",
  size: "Tamaño",
  sources: "Fuentes",
  noSources: "Sin web leída: resumen hecho solo con el texto de la oferta.",
  fetched: (date: string, age: number) =>
    `Investigada el ${date}${age > 0 ? ` (hace ${age} día${age === 1 ? "" : "s"})` : ""}`,
  shared: "Se comparte con la carta, la evaluación y el pack de entrevista; caduca a los 30 días.",
};

/** Investigación de una empresa con IA (web + oferta) guardada 30 días. Si no hay IA configurada o faltan
 *  fuentes, la API responde 409/422 y se muestra su mensaje. `initialResearch` undefined = la carga al montarse. */
export function CompanyResearchPanel({ company, initialResearch, initialError = "" }: {
  company: string;
  initialResearch?: CompanyResearch | null;
  initialError?: string;
}) {
  const [research, setResearch] = useState<CompanyResearch | null>(initialResearch ?? null);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (initialResearch !== undefined) return;
    let alive = true;
    fetchCompanyResearch(company)
      .then(r => { if (alive && r) setResearch(r); })
      .catch(() => { /* sin investigación guardada: se ofrece investigar */ });
    return () => { alive = false; };
  }, [company, initialResearch]);

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      setResearch(await researchCompany(company));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-6 p-4 rounded-xl bg-sky-500/5 border border-sky-500/20 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xs font-semibold text-sky-300 uppercase tracking-wider">{T.title}</h3>
        <button
          onClick={run}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-sm font-medium text-sky-200 hover:bg-sky-500/20 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Building2 className="w-4 h-4" />}
          {busy ? T.busy : research ? T.refresh : T.button}
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      {research && (
        <div className="space-y-3">
          <p className="text-sm text-gray-200 whitespace-pre-line">{research.summary}</p>
          {research.warnings.map(w => <p key={w} role="status" className="text-xs text-amber-300">{w}</p>)}
          <div className="grid gap-3 sm:grid-cols-2">
            <Points title={T.products} items={research.products} />
            <Points title={T.culture} items={research.culture_signals} />
            <Points title={T.tech} items={research.tech_stack} />
            {research.size_hint && (
              <div>
                <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">{T.size}</h4>
                <p className="text-sm text-gray-300">{research.size_hint}</p>
              </div>
            )}
          </div>
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">{T.sources}</h4>
            {research.sources.length === 0 ? (
              <p className="text-xs text-gray-500">{T.noSources}</p>
            ) : (
              <ul className="text-xs space-y-0.5 list-disc list-inside text-sky-300/90 break-all">
                {research.sources.map(s => <li key={s}>{s}</li>)}
              </ul>
            )}
          </div>
          <p className="text-xs text-gray-500">
            {T.fetched(research.fetched_date, research.age_days)}. {T.shared}
          </p>
        </div>
      )}
    </div>
  );
}

function Points({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">{title}</h4>
      <ul className="text-sm space-y-1 list-disc list-inside text-gray-300">
        {items.map(item => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}
