"use client";

import { useCallback, useEffect, useState } from "react";
import { FileUp, Loader2, Trash2 } from "lucide-react";
import { activateTemplate, deleteTemplate, fetchTemplates, uploadTemplate } from "@/lib/api";
import type { TemplateInfo, TemplateKind } from "@/lib/types";

// Textos de la interfaz en un solo sitio (la traducción llega en SP4).
export const T = {
  title: "Plantillas de CV y carta",
  hint: "Las integradas siempre están. Una plantilla propia (LaTeX o Typst, .zip o un único .tex.j2/.typ.j2) se compila de prueba antes de aceptarla.",
  kinds: { cv: "CV", letter: "Carta" } as Record<TemplateKind, string>,
  builtin: "integrada",
  active: "activa",
  activate: "Activar",
  remove: "Borrar",
  upload: "Añadir plantilla",
  uploading: "Compilando prueba…",
  name: "Nombre (minúsculas, - o _)",
  pageLimit: "Páginas máx.",
  noFile: "Elige un archivo de plantilla.",
  noName: "Escribe un nombre.",
  loading: "Cargando plantillas…",
};

/** Plantillas de CV y carta: elegir la activa, añadir propias (con compilación de prueba) y borrarlas. */
export function TemplatesPanel({ initial = [], initialError = "", autoLoad = true }: {
  initial?: TemplateInfo[];
  initialError?: string;
  /** false (tests): no pide las plantillas al montarse. */
  autoLoad?: boolean;
}) {
  const [templates, setTemplates] = useState<TemplateInfo[]>(initial);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(!autoLoad || initial.length > 0);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<TemplateKind>("cv");
  const [pageLimit, setPageLimit] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const reload = useCallback(async () => {
    try {
      setTemplates(await fetchTemplates());
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (loaded) return;
    let alive = true;
    fetchTemplates()
      .then(list => { if (alive) { setTemplates(list); setLoaded(true); } })
      .catch((e: Error) => { if (alive) { setError(e.message); setLoaded(true); } });
    return () => { alive = false; };
  }, [loaded]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (!name.trim()) { setError(T.noName); return; }
    if (!file) { setError(T.noFile); return; }
    await act(async () => {
      await uploadTemplate(file, file.name, {
        name: name.trim(), kind, ...(pageLimit ? { page_limit: Number(pageLimit) } : {}),
      });
      setName(""); setFile(null); setPageLimit("");
    });
  };

  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold text-gray-200">{T.title}</h3>
      <p className="text-xs text-gray-500">{T.hint}</p>
      {!loaded && <p className="text-xs text-gray-500">{T.loading}</p>}
      {(["cv", "letter"] as TemplateKind[]).map(k => (
        <div key={k} className="space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">{T.kinds[k]}</h4>
          <ul className="space-y-1.5">
            {templates.filter(t => t.kind === k).map(t => (
              <li key={t.name} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                <div className="text-sm text-gray-300">
                  <span className="font-mono">{t.name}</span>
                  <span className="ml-2 text-xs text-gray-500">{t.engine}{t.builtin ? ` · ${T.builtin}` : ""}</span>
                  {t.active && <span className="ml-2 text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-md font-bold border bg-emerald-500/15 text-emerald-300 border-emerald-500/30">{T.active}</span>}
                </div>
                <div className="flex items-center gap-3 text-xs">
                  {!t.active && (
                    <button disabled={busy} className="text-indigo-300 hover:text-indigo-200 disabled:opacity-40" onClick={() => act(() => activateTemplate(t.kind, t.name))}>
                      {T.activate}
                    </button>
                  )}
                  {!t.builtin && (
                    <button disabled={busy} aria-label={`${T.remove} ${t.name}`} className="text-red-300 hover:text-red-200 disabled:opacity-40" onClick={() => act(() => deleteTemplate(t.kind, t.name))}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="flex flex-wrap items-end gap-2">
        <input
          aria-label={T.name}
          placeholder={T.name}
          value={name}
          onChange={e => setName(e.target.value)}
          className="text-xs text-gray-300 border border-white/10 rounded-lg px-3 py-2 bg-[#16161f]"
        />
        <select aria-label="Tipo" value={kind} onChange={e => setKind(e.target.value as TemplateKind)} className="text-xs text-gray-300 border border-white/10 rounded-lg px-3 py-2 bg-[#16161f]">
          <option value="cv">{T.kinds.cv}</option>
          <option value="letter">{T.kinds.letter}</option>
        </select>
        <input
          aria-label={T.pageLimit}
          placeholder={T.pageLimit}
          inputMode="numeric"
          value={pageLimit}
          onChange={e => setPageLimit(e.target.value.replace(/\D/g, ""))}
          className="w-28 text-xs text-gray-300 border border-white/10 rounded-lg px-3 py-2 bg-[#16161f]"
        />
        <input
          type="file"
          aria-label="Archivo de plantilla"
          accept=".zip,.j2"
          onChange={e => setFile(e.target.files?.[0] ?? null)}
          className="text-xs text-gray-400"
        />
        <button
          onClick={submit}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileUp className="w-4 h-4" />}
          {busy ? T.uploading : T.upload}
        </button>
      </div>
      {error && <p role="alert" className="whitespace-pre-wrap text-sm text-red-300">{error}</p>}
    </div>
  );
}
