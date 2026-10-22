"use client";

import { useState } from "react";
import { Check, Loader2, Sparkles, X } from "lucide-react";
import { acceptExpansion, expandProfile } from "@/lib/api";
import { parseSources, safeHref } from "@/lib/report";
import type { ExpandError, ExpandProposal } from "@/lib/types";

// Textos de la interfaz en un solo sitio (la traducción llega en SP4).
export const T = {
  title: "Ampliar perfil",
  hint: "Enlaza tu GitHub, portfolio o certificaciones (una URL por línea). Se leen respetando robots.txt y cada competencia nueva se propone con su fuente: solo se guarda lo que aceptes.",
  placeholder: "https://github.com/tu-usuario\nhttps://tu-portfolio.example",
  button: "Buscar competencias",
  busy: "Leyendo las fuentes…",
  empty: "Escribe al menos una URL.",
  none: "No hay competencias nuevas en esas fuentes.",
  accept: "Aceptar",
  reject: "Rechazar",
  source: "Fuente",
  accepted: (n: number) => `${n} competencia(s) añadida(s) al perfil`,
};

const btn = "inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-sm font-medium disabled:opacity-50";

/** Propuestas de competencias a partir de las páginas que enlaza el usuario. Proponer no guarda nada; «Aceptar»
 *  fusiona esa competencia en el perfil y «Rechazar» la descarta de la lista. */
export function ExpandProfilePanel({ initialProposals = [], initialErrors = [], initialText = "" }: {
  initialProposals?: ExpandProposal[];
  initialErrors?: ExpandError[];
  initialText?: string;
}) {
  const [text, setText] = useState(initialText);
  const [proposals, setProposals] = useState<ExpandProposal[]>(initialProposals);
  const [errors, setErrors] = useState<ExpandError[]>(initialErrors);
  const [searched, setSearched] = useState(initialProposals.length > 0 || initialErrors.length > 0);
  const [message, setMessage] = useState("");
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);

  const search = async () => {
    const sources = parseSources(text);
    if (!sources.length) { setFailure(T.empty); return; }
    setBusy(true);
    setFailure("");
    setMessage("");
    try {
      const res = await expandProfile(sources);
      setProposals(res.proposals);
      setErrors(res.errors);
      setSearched(true);
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const accept = async (item: ExpandProposal) => {
    setBusy(true);
    setFailure("");
    try {
      const res = await acceptExpansion([item]);
      setProposals(list => list.filter(p => p !== item));
      setMessage(T.accepted(res.added.length));
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass-card p-5 space-y-4 lg:col-span-2">
      <h3 className="text-base font-semibold text-white">{T.title}</h3>
      <p className="text-xs text-gray-500">{T.hint}</p>
      <textarea
        aria-label={T.title}
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder={T.placeholder}
        rows={3}
        className="w-full text-xs font-mono text-gray-300 border border-white/10 rounded-xl p-3 resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/50 bg-[#16161f]"
      />
      <button onClick={search} disabled={busy} className={`${btn} border-indigo-500/30 bg-indigo-500/10 text-indigo-200 hover:bg-indigo-500/20`}>
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
        {busy ? T.busy : T.button}
      </button>
      {failure && <p role="alert" className="text-sm text-red-300">{failure}</p>}
      {message && <p role="status" className="text-sm text-emerald-300">{message}</p>}
      {errors.map(e => (
        <p key={e.url} className="text-xs text-amber-300">{e.url}: {e.error}</p>
      ))}
      {searched && proposals.length === 0 && !errors.length && <p className="text-sm text-gray-400">{T.none}</p>}
      {proposals.length > 0 && (
        <ul className="space-y-2">
          {proposals.map(p => {
            const href = safeHref(p.source_url);
            return (
              <li key={`${p.name}|${p.source_url ?? ""}`} className="rounded-lg border border-white/10 bg-black/20 p-3 flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1 min-w-0">
                  <p className="text-sm font-medium text-gray-100">{p.name}</p>
                  {p.evidence && <p className="text-xs text-gray-400">{p.evidence}</p>}
                  {p.source_url && (
                    <p className="text-xs text-gray-500 break-all">
                      {T.source}:{" "}
                      {href ? <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-indigo-300 hover:text-indigo-200">{p.source_url}</a> : p.source_url}
                    </p>
                  )}
                </div>
                <div className="flex gap-2 shrink-0">
                  <button disabled={busy} onClick={() => accept(p)} className={`${btn} border-emerald-500/30 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20`}>
                    <Check className="w-4 h-4" /> {T.accept}
                  </button>
                  <button disabled={busy} onClick={() => setProposals(list => list.filter(x => x !== p))} className={`${btn} border-white/10 text-gray-300 hover:bg-white/5`}>
                    <X className="w-4 h-4" /> {T.reject}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
