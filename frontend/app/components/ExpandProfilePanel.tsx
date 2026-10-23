"use client";

import { useState } from "react";
import { Check, Loader2, Sparkles, Trash2, X } from "lucide-react";
import { acceptExpansion, expandProfile, fetchProfile, patchProfile } from "@/lib/api";
import { parseSources, safeHref } from "@/lib/report";
import { t, useLocale } from "@/lib/i18n";
import type { StoredProfile } from "@/lib/setup";
import type { ExpandError, ExpandProposal } from "@/lib/types";

// Textos de la interfaz traducidos vía i18n (con getters para retrocompatibilidad).
export const T = {
  get title() { return t("expand_profile.title"); },
  get hint() { return t("expand_profile.hint"); },
  get placeholder() { return t("expand_profile.placeholder"); },
  get button() { return t("expand_profile.button"); },
  get busy() { return t("expand_profile.busy"); },
  get empty() { return t("expand_profile.empty"); },
  get none() { return t("expand_profile.none"); },
  get accept() { return t("expand_profile.accept"); },
  get reject() { return t("expand_profile.reject"); },
  get source() { return t("expand_profile.source"); },
  accepted: (n: number) => t("expand_profile.accepted", { count: n }),
  get skillsTitle() { return t("expand_profile.skills_title"); },
  get skillsHint() { return t("expand_profile.skills_hint"); },
  get noSkills() { return t("expand_profile.no_skills"); },
  get noSource() { return t("expand_profile.no_source"); },
  removeSkill: (name: string) => t("expand_profile.remove_skill", { name }),
};

/** Competencia de `profile.skills` con su procedencia (`skills_sources`, si la tiene). */
export interface AcceptedSkill {
  name: string;
  source_url: string;
  evidence: string;
}

const fold = (v: string) => v.trim().toLocaleLowerCase("es");

/** Competencias sueltas del perfil (`skills`) con la fuente y la prueba de `skills_sources`. */
export function acceptedSkills(profile: StoredProfile | null | undefined): AcceptedSkill[] {
  const skills = Array.isArray(profile?.skills) ? (profile!.skills as unknown[]) : [];
  const sources = Array.isArray(profile?.skills_sources) ? (profile!.skills_sources as unknown[]) : [];
  const byName = new Map<string, { source_url?: unknown; evidence?: unknown }>();
  for (const src of sources) {
    if (src && typeof src === "object" && typeof (src as { name?: unknown }).name === "string") {
      byName.set(fold((src as { name: string }).name), src as { source_url?: unknown; evidence?: unknown });
    }
  }
  return skills
    .filter((s): s is string => typeof s === "string" && s.trim() !== "")
    .map(name => {
      const src = byName.get(fold(name));
      return { name, source_url: String(src?.source_url ?? ""), evidence: String(src?.evidence ?? "") };
    });
}

/** Cambios para PATCH /api/profile que quitan una competencia y su procedencia (el resto no se toca). */
export function withoutSkill(profile: StoredProfile, name: string): { skills: unknown[]; skills_sources: unknown[] } {
  const skills = Array.isArray(profile.skills) ? (profile.skills as unknown[]) : [];
  const sources = Array.isArray(profile.skills_sources) ? (profile.skills_sources as unknown[]) : [];
  const target = fold(name);
  return {
    skills: skills.filter(s => !(typeof s === "string" && fold(s) === target)),
    skills_sources: sources.filter(s => !(s && typeof s === "object" && typeof (s as { name?: unknown }).name === "string"
      && fold((s as { name: string }).name) === target)),
  };
}

const btn = "inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-sm font-medium disabled:opacity-50";

/** Propuestas de competencias a partir de las páginas que enlaza el usuario. Proponer no guarda nada; «Aceptar»
 *  fusiona esa competencia en el perfil y «Rechazar» la descarta de la lista. */
export function ExpandProfilePanel({ initialProposals = [], initialErrors = [], initialText = "", initialProfile }: {
  initialProposals?: ExpandProposal[];
  initialErrors?: ExpandError[];
  initialText?: string;
  /** Perfil guardado: si se da, se listan las competencias añadidas con su fuente y se pueden quitar. */
  initialProfile?: StoredProfile;
}) {
  useLocale();
  const [skills, setSkills] = useState<AcceptedSkill[]>(() => acceptedSkills(initialProfile));
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
      if (res.added.includes(item.name)) {
        setSkills(list => [...list, { name: item.name, source_url: item.source_url ?? "", evidence: item.evidence ?? "" }]);
      }
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const removeSkill = async (name: string) => {
    setBusy(true);
    setFailure("");
    setMessage("");
    try {
      // Se parte del perfil recién leído: así no se pisa lo que haya cambiado en otra pestaña.
      const saved = await patchProfile(withoutSkill(await fetchProfile(), name));
      setSkills(acceptedSkills(saved));
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
      {initialProfile !== undefined && (
        <div className="space-y-2 border-t border-white/10 pt-4">
          <h4 className="text-sm font-semibold text-gray-200">{T.skillsTitle}</h4>
          <p className="text-xs text-gray-500">{T.skillsHint}</p>
          {skills.length === 0 && <p className="text-xs text-gray-400">{T.noSkills}</p>}
          <ul aria-label={T.skillsTitle} className="space-y-1.5">
            {skills.map(skill => {
              const href = safeHref(skill.source_url);
              return (
                <li key={skill.name} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                  <div className="min-w-0 text-xs text-gray-400">
                    <span className="text-sm font-medium text-gray-100">{skill.name}</span>
                    <span className="ml-2 break-all">
                      {T.source}:{" "}
                      {href ? <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-indigo-300 hover:text-indigo-200">{skill.source_url}</a>
                        : skill.source_url || T.noSource}
                    </span>
                    {skill.evidence && <p className="text-gray-500">{skill.evidence}</p>}
                  </div>
                  <button disabled={busy} aria-label={T.removeSkill(skill.name)} onClick={() => removeSkill(skill.name)}
                    className="text-red-300 hover:text-red-200 disabled:opacity-40">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
