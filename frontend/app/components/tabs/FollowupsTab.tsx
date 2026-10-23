"use client";

import { useMemo, useState } from "react";
import { Check, Copy, ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import { markFollowupSent, resolveStaleApplications } from "@/lib/api";
import type { QuietApplication } from "@/lib/types";
import { t, useLocale } from "@/lib/i18n";

/**
 * Pestaña «Seguimiento»: candidaturas enviadas sin respuesta.
 * - Recordatorios: borrador listo para copiar; nada se envía desde aquí. Al marcarlo como enviado
 *   se cuenta (máx. 2) y la candidatura sale de la lista hasta que vuelvan a pasar los días.
 * - Sin respuesta: las que llevan demasiado tiempo calladas; se cierran como 'no_response' solo
 *   las que se marquen, con confirmación en dos pasos.
 */
export function FollowupsTab({ followups, stale, onAction }: { followups: QuietApplication[]; stale: QuietApplication[]; onAction: () => void }) {
  useLocale();
  const [channel, setChannel] = useState<"all" | QuietApplication["channel"]>("all");
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);

  const channelLabel: Record<QuietApplication["channel"], string> = {
    email: t("followups.channel_email"),
    linkedin: t("followups.channel_linkedin"),
    portal: t("followups.channel_portal"),
  };

  const visible = useMemo(
    () => (channel === "all" ? followups : followups.filter(f => f.channel === channel)),
    [followups, channel],
  );

  const flash = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(null), 4000);
  };

  const handleCopy = async (f: QuietApplication) => {
    try {
      await navigator.clipboard.writeText(f.draft ?? "");
      flash(`Borrador para ${f.company_name ?? "la empresa"} copiado`);
    } catch {
      setOpen(f.id);
      flash("No se pudo copiar automáticamente: cópialo a mano del recuadro");
    }
  };

  const handleMarkSent = async (f: QuietApplication) => {
    setBusy(f.id);
    try {
      const res = await markFollowupSent(f.id);
      if (res.detail) flash(String(res.detail));
      else onAction();
    } finally {
      setBusy(null);
    }
  };

  const toggle = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const handleResolve = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setBusy("stale");
    try {
      const res = await resolveStaleApplications([...selected]);
      flash(`${res.resolved} candidatura${res.resolved === 1 ? "" : "s"} cerrada${res.resolved === 1 ? "" : "s"} sin respuesta`);
      setSelected(new Set());
      setConfirming(false);
      onAction();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      {feedback && (
        <div className="text-sm text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 px-4 py-2 rounded-xl w-fit">{feedback}</div>
      )}

      {stale.length > 0 && (
        <section className="glass-card p-6 border border-slate-500/20">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div>
              <h2 className="text-lg font-medium text-gray-200">{t("followups.stale_title")}</h2>
              <p className="text-sm text-gray-500">{t("followups.stale_hint")}</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { setSelected(selected.size === stale.length ? new Set() : new Set(stale.map(s => s.id))); setConfirming(false); }}
                className="text-xs text-gray-400 hover:text-white px-3 py-1.5 rounded-lg bg-white/5"
              >
                {selected.size === stale.length ? t("followups.select_none") : t("followups.select_all")}
              </button>
              <button
                disabled={selected.size === 0 || busy === "stale"}
                onClick={handleResolve}
                className={`text-sm px-4 py-1.5 rounded-lg border transition-colors disabled:opacity-40 ${confirming ? "bg-red-500/20 text-red-300 border-red-500/30" : "bg-white/5 text-gray-200 border-white/10 hover:bg-white/10"}`}
              >
                {confirming ? t("followups.confirm_close", { count: selected.size }) : t("followups.close_selected", { count: selected.size })}
              </button>
            </div>
          </div>
          <ul className="divide-y divide-white/5">
            {stale.map(s => (
              <li key={s.id} className="py-2 flex items-center gap-3 text-sm">
                <input type="checkbox" checked={selected.has(s.id)} onChange={() => { toggle(s.id); setConfirming(false); }} className="accent-slate-400" />
                <span className="text-gray-200 font-medium">{s.company_name ?? "—"}</span>
                <span className="text-gray-500 truncate">{s.job_title ?? ""}</span>
                <span className="ml-auto font-mono text-slate-400">{s.days_quiet} d</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-medium text-gray-200">{t("followups.reminders_title")}</h2>
            <p className="text-sm text-gray-500">{t("followups.reminders_hint")}</p>
          </div>
          <div className="flex items-center gap-1 p-1 bg-white/5 rounded-xl">
            {(["all", "email", "linkedin", "portal"] as const).map(c => (
              <button
                key={c}
                onClick={() => setChannel(c)}
                className={`text-xs px-3 py-1.5 rounded-lg ${channel === c ? "bg-white/10 text-white" : "text-gray-400 hover:text-gray-200"}`}
              >
                {c === "all" ? t("followups.all_channels") : channelLabel[c]}
                <span className="ml-1.5 text-gray-500">{c === "all" ? followups.length : followups.filter(f => f.channel === c).length}</span>
              </button>
            ))}
          </div>
        </div>

        {visible.length === 0 ? (
          <div className="glass-card p-12 text-center border-dashed border-white/10">
            <Check className="w-8 h-8 text-gray-500 mx-auto mb-3" />
            <p className="text-sm text-gray-400">{t("followups.empty_reminders")}</p>
          </div>
        ) : (
          <div className="glass-card divide-y divide-white/5">
            {visible.map(f => (
              <div key={f.id} className="p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <button onClick={() => setOpen(open === f.id ? null : f.id)} className="text-gray-400 hover:text-white" aria-label={t("followups.view_draft")}>
                    {open === f.id ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-gray-200 font-medium truncate">
                      {f.company_name ?? "—"} <span className="text-gray-500 font-normal">· {f.job_title ?? t("followups.no_title")}</span>
                    </div>
                    <div className="text-xs text-gray-500 flex flex-wrap gap-x-3">
                      <span>{channelLabel[f.channel]}{f.method ? ` (${f.method})` : ""}</span>
                      {f.contact_value && <span className="font-mono">{f.contact_value}</span>}
                      {f.followup_count > 0 && <span className="text-amber-400">{t("followups.sent_reminder_count", { count: f.followup_count })}</span>}
                    </div>
                  </div>
                  <span className="font-mono text-sm text-amber-300">{f.days_quiet} d</span>
                  {f.offer_url && (
                    <a href={f.offer_url} target="_blank" rel="noreferrer" className="p-1.5 text-gray-400 hover:text-white" aria-label={t("followups.open_offer")}>
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  )}
                  <button onClick={() => handleCopy(f)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-white/5 text-gray-200 hover:bg-white/10">
                    <Copy className="w-3.5 h-3.5" /> {t("common.copy")}
                  </button>
                  <button
                    disabled={busy === f.id}
                    onClick={() => handleMarkSent(f)}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 hover:bg-emerald-500/20 disabled:opacity-40"
                  >
                    <Check className="w-3.5 h-3.5" /> {t("followups.mark_sent_button")}
                  </button>
                </div>
                {open === f.id && (
                  <pre className="mt-3 ml-7 p-4 text-sm text-gray-300 whitespace-pre-wrap font-sans bg-black/20 rounded-xl border border-white/5">{f.draft}</pre>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
