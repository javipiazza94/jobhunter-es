"use client";

import { useEffect, useState } from "react";
import { FileCheck2, Loader2 } from "lucide-react";
import { applicationDocumentUrl, fetchAISettings, fetchApplicationDocuments, prepareApplication } from "@/lib/api";
import { summarizeVerification } from "@/lib/documents";
import type { DocumentFile, PreparedDocs } from "@/lib/types";

// Textos de la interfaz en un solo sitio (la traducción llega en SP4).
export const T = {
  title: "Documentos de la candidatura",
  hint: "Genera un CV (2 páginas) y una carta (1 página) en PDF adaptados a esta oferta. Al aprobar se adjuntan estos PDFs.",
  button: "Preparar candidatura",
  rebuild: "Volver a preparar",
  busy: "Preparando…",
  withAi: "con IA",
  aiHint: "Redacta con IA solo con datos de tu perfil",
  source: { ai: "con IA", deterministic: "determinista" } as Record<PreparedDocs["source"], string>,
  pages: (cv: number | null, cover: number | null) => `CV ${cv ?? "?"} pág. · Carta ${cover ?? "?"} pág.`,
  missing: (k: string[]) => `Sin cobertura en el CV (huecos, no se inventan): ${k.join(", ")}`,
  layoutSkipped: "Maquetación sin comprobar (Poppler no instalado)",
  trimmed: (n: number) => `Se recortó contenido menos relevante (${n})`,
  cv: "Abrir CV",
  cover: "Abrir carta",
};

/** «Preparar candidatura»: llama a /prepare y enseña origen, páginas, huecos de palabras clave y avisos.
 *  Con IA solo si hay proveedor configurado; si falla, la API vuelve a la versión determinista con aviso. */
export function PrepareDocsPanel({
  applicationId, onChange, initialFiles = [], initialResult = null, initialError = "",
}: {
  applicationId: string;
  /** Avisa a quien la contiene de qué documentos hay archivados (para decir qué se adjunta). */
  onChange?: (files: DocumentFile[]) => void;
  initialFiles?: DocumentFile[];
  initialResult?: PreparedDocs | null;
  initialError?: string;
}) {
  const [files, setFiles] = useState<DocumentFile[]>(initialFiles);
  const [result, setResult] = useState<PreparedDocs | null>(initialResult);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [useAi, setUseAi] = useState(true);

  useEffect(() => {
    let alive = true;
    fetchApplicationDocuments(applicationId)
      .then(list => { if (alive) { setFiles(list); onChange?.(list); } })
      .catch(() => { /* sin archivo todavía: no es un error */ });
    fetchAISettings()
      .then(s => { if (alive) setAiAvailable(s.provider !== "none"); })
      .catch(() => { /* sin ajustes de IA: se prepara sin ella */ });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const prepared = await prepareApplication(applicationId, aiAvailable ? useAi : false);
      setResult(prepared);
      const list = await fetchApplicationDocuments(applicationId);
      setFiles(list);
      onChange?.(list);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ready = files.some(f => f.name === "cv.pdf") && files.some(f => f.name === "cover.pdf");
  const summary = result ? summarizeVerification(result.verification) : null;

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-gray-200">{T.title}</h4>
      <p className="text-xs text-gray-500">{T.hint}</p>
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={run}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileCheck2 className="w-4 h-4" />}
          {busy ? T.busy : ready ? T.rebuild : T.button}
        </button>
        {aiAvailable && (
          <label className="inline-flex items-center gap-2 text-xs text-gray-400" title={T.aiHint}>
            <input type="checkbox" checked={useAi} disabled={busy} onChange={e => setUseAi(e.target.checked)} />
            {T.withAi}
          </label>
        )}
        {ready && (
          <span className="flex items-center gap-3 text-xs">
            <a className="text-indigo-300 hover:text-indigo-200" href={applicationDocumentUrl(applicationId, "cv.pdf")} target="_blank" rel="noreferrer">{T.cv}</a>
            <a className="text-indigo-300 hover:text-indigo-200" href={applicationDocumentUrl(applicationId, "cover.pdf")} target="_blank" rel="noreferrer">{T.cover}</a>
          </span>
        )}
      </div>
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      {result && summary && (
        <div className="rounded-lg border border-white/10 bg-black/20 p-3 space-y-1.5 text-xs text-gray-400">
          <p className="text-gray-300">
            {T.pages(summary.cvPages, summary.coverPages)} · <span className="text-emerald-300">{T.source[result.source]}</span>
          </p>
          {summary.missingKeywords.length > 0 && <p className="text-amber-300">{T.missing(summary.missingKeywords)}</p>}
          {summary.trimmed.length > 0 && <p>{T.trimmed(summary.trimmed.length)}</p>}
          {summary.layoutSkipped && <p>{T.layoutSkipped}</p>}
          {summary.layoutWarnings.map((w, i) => <p key={i} className="text-amber-300">{w}</p>)}
          {result.warnings.map((w, i) => <p key={`w${i}`} className="text-amber-300">{w}</p>)}
        </div>
      )}
    </div>
  );
}
