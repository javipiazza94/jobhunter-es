"use client";

import { useCallback, useEffect, useState } from "react";
import { FileUp, Loader2, Trash2 } from "lucide-react";
import { activateTemplate, deleteTemplate, fetchTemplates, uploadTemplate } from "@/lib/api";
import { t, useLocale } from "@/lib/i18n";
import type { TemplateCompiler, TemplateEngine, TemplateInfo, TemplateKind } from "@/lib/types";

/** Compiladores admitidos por motor (lista cerrada, igual que en el backend). */
export const COMPILERS: Record<TemplateEngine, TemplateCompiler[]> = {
  latex: ["tectonic", "xelatex"],
  typst: ["typst"],
};

// Textos de la interfaz traducidos vía i18n (con getters para retrocompatibilidad).
export const T = {
  get title() { return t("templates.title"); },
  get hint() { return t("templates.hint"); },
  get trust() { return t("templates.trust"); },
  get trustCheck() { return t("templates.trust_check"); },
  get noTrust() { return t("templates.no_trust"); },
  get kinds() {
    return { cv: t("templates.kind_cv"), letter: t("templates.kind_letter") } as Record<TemplateKind, string>;
  },
  get engines() {
    return { latex: t("templates.engine_latex"), typst: t("templates.engine_typst") } as Record<TemplateEngine, string>;
  },
  get builtin() { return t("templates.builtin"); },
  get active() { return t("templates.active"); },
  get invalid() { return t("templates.invalid"); },
  get activate() { return t("templates.activate"); },
  get remove() { return t("templates.remove"); },
  get upload() { return t("templates.upload"); },
  get uploading() { return t("templates.uploading"); },
  get name() { return t("templates.name"); },
  get kind() { return t("templates.kind"); },
  get engine() { return t("templates.engine"); },
  get compiler() { return t("templates.compiler"); },
  get compilerAuto() { return t("templates.compiler_auto"); },
  get pageLimit() { return t("templates.page_limit"); },
  get styleRules() { return t("templates.style_rules"); },
  get file() { return t("templates.file"); },
  get noFile() { return t("templates.no_file"); },
  get noName() { return t("templates.no_name"); },
  get loading() { return t("templates.loading"); },
};

/** Motor que sugiere el nombre del archivo (`.typ.j2` → Typst); null si no lo dice (p. ej. un .zip). */
export function engineFromFilename(filename: string): TemplateEngine | null {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".typ.j2")) return "typst";
  if (lower.endsWith(".tex.j2")) return "latex";
  return null;
}

/** Plantillas de CV y carta: elegir la activa, añadir propias (con compilación de prueba) y borrarlas. */
export function TemplatesPanel({ initial = [], initialError = "", autoLoad = true }: {
  initial?: TemplateInfo[];
  initialError?: string;
  /** false (tests): no pide las plantillas al montarse. */
  autoLoad?: boolean;
}) {
  useLocale();
  const [templates, setTemplates] = useState<TemplateInfo[]>(initial);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(!autoLoad || initial.length > 0);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<TemplateKind>("cv");
  const [engine, setEngine] = useState<TemplateEngine>("latex");
  const [compiler, setCompiler] = useState<TemplateCompiler | "">("");
  const [pageLimit, setPageLimit] = useState("");
  const [styleRules, setStyleRules] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [trusted, setTrusted] = useState(false);

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

  const chooseEngine = (value: TemplateEngine) => {
    setEngine(value);
    if (compiler && !COMPILERS[value].includes(compiler)) setCompiler("");
  };

  const chooseFile = (picked: File | null) => {
    setFile(picked);
    const guessed = picked ? engineFromFilename(picked.name) : null;
    if (guessed) chooseEngine(guessed);
  };

  const submit = async () => {
    if (!name.trim()) { setError(T.noName); return; }
    if (!file) { setError(T.noFile); return; }
    if (!trusted) { setError(T.noTrust); return; }
    await act(async () => {
      await uploadTemplate(file, file.name, {
        name: name.trim(), kind, engine, trusted,
        ...(compiler ? { compiler } : {}),
        ...(pageLimit ? { page_limit: Number(pageLimit) } : {}),
        ...(styleRules.trim() ? { style_rules: styleRules.trim() } : {}),
      });
      setName(""); setFile(null); setPageLimit(""); setStyleRules(""); setCompiler(""); setTrusted(false);
    });
  };

  const field = "text-xs text-gray-300 border border-white/10 rounded-lg px-3 py-2 bg-[#16161f]";

  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold text-gray-200">{T.title}</h3>
      <p className="text-xs text-gray-500">{T.hint}</p>
      <p className="text-xs text-amber-300/80">{T.trust}</p>
      {!loaded && <p className="text-xs text-gray-500">{T.loading}</p>}
      {(["cv", "letter"] as TemplateKind[]).map(k => (
        <div key={k} className="space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">{T.kinds[k]}</h4>
          <ul className="space-y-1.5">
            {templates.filter(t => t.kind === k).map(t => (
              <li key={t.name} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                <div className="text-sm text-gray-300">
                  <span className="font-mono">{t.name}</span>
                  <span className="ml-2 text-xs text-gray-500">
                    {t.engine}{t.compiler ? ` · ${t.compiler}` : ""}{t.page_limit ? ` · ${t.page_limit} pág.` : ""}{t.builtin ? ` · ${T.builtin}` : ""}
                  </span>
                  {t.active && <span className="ml-2 text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-md font-bold border bg-emerald-500/15 text-emerald-300 border-emerald-500/30">{T.active}</span>}
                  {t.invalid_reason && (
                    <span title={t.invalid_reason} className="ml-2 text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-md font-bold border bg-red-500/15 text-red-300 border-red-500/30">{T.invalid}</span>
                  )}
                  {t.invalid_reason && <p className="mt-1 text-xs text-red-300">{t.invalid_reason}</p>}
                </div>
                <div className="flex items-center gap-3 text-xs">
                  {!t.active && !t.invalid_reason && (
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
        <input aria-label={T.name} placeholder={T.name} value={name} onChange={e => setName(e.target.value)} className={field} />
        <select aria-label={T.kind} value={kind} onChange={e => setKind(e.target.value as TemplateKind)} className={field}>
          <option value="cv">{T.kinds.cv}</option>
          <option value="letter">{T.kinds.letter}</option>
        </select>
        <select aria-label={T.engine} value={engine} onChange={e => chooseEngine(e.target.value as TemplateEngine)} className={field}>
          <option value="latex">{T.engines.latex}</option>
          <option value="typst">{T.engines.typst}</option>
        </select>
        <select aria-label={T.compiler} value={compiler} onChange={e => setCompiler(e.target.value as TemplateCompiler | "")} className={field}>
          <option value="">{T.compilerAuto}</option>
          {COMPILERS[engine].map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <input
          aria-label={T.pageLimit}
          placeholder={T.pageLimit}
          inputMode="numeric"
          value={pageLimit}
          onChange={e => setPageLimit(e.target.value.replace(/\D/g, ""))}
          className={`w-28 ${field}`}
        />
        <input
          type="file"
          aria-label={T.file}
          accept=".zip,.j2"
          onChange={e => chooseFile(e.target.files?.[0] ?? null)}
          className="text-xs text-gray-400"
        />
        <textarea
          aria-label={T.styleRules}
          placeholder={T.styleRules}
          value={styleRules}
          maxLength={2000}
          rows={2}
          onChange={e => setStyleRules(e.target.value)}
          className={`basis-full ${field}`}
        />
        <label className="basis-full inline-flex items-center gap-2 text-xs text-amber-200">
          <input type="checkbox" checked={trusted} onChange={e => setTrusted(e.target.checked)} />
          {T.trustCheck}
        </label>
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
