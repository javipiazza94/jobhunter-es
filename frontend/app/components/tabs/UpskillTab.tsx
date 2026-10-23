"use client";

import { useState } from "react";
import { GraduationCap, Loader2 } from "lucide-react";
import { runUpskill } from "@/lib/api";
import { t, useLocale } from "@/lib/i18n";
import { parseReport } from "@/lib/report";
import type { UpskillReport, UpskillScope } from "@/lib/types";

// Textos de la interfaz traducidos vía i18n (con getters para retrocompatibilidad).
export const T = {
  get title() { return t("upskill.title"); },
  get hint() { return t("upskill.hint"); },
  get scope() { return t("upskill.scope"); },
  get scopes() {
    return {
      saved: t("upskill.scope_saved"),
      evaluated: t("upskill.scope_evaluated"),
      applied: t("upskill.scope_applied"),
    } as Record<string, string>;
  },
  get button() { return t("upskill.button"); },
  get forOffer() { return t("upskill.for_offer"); },
  get forOfferHint() { return t("upskill.for_offer_hint"); },
  get busy() { return t("upskill.busy"); },
  saved: (path: string) => t("upskill.saved", { path }),
  analyzed: (n: number) => t("upskill.analyzed", { count: n }),
};

const SCOPES: UpskillScope[] = ["saved", "evaluated", "applied"];

/** Pantalla «Upskill»: lanza el mapa de huecos y muestra el informe Markdown como texto (sin HTML crudo).
 *  Con `offerId` es la versión del detalle de una oferta: ámbito «one» con esa oferta, sin selector. */
export function UpskillTab({ initialReport = null, initialError = "", offerId }: {
  initialReport?: UpskillReport | null;
  initialError?: string;
  offerId?: string;
}) {
  useLocale();
  const [scope, setScope] = useState<UpskillScope>("saved");
  const [report, setReport] = useState<UpskillReport | null>(initialReport);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      setReport(offerId ? await runUpskill("one", [offerId]) : await runUpskill(scope));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={offerId ? "mb-6 space-y-3" : "glass-card p-6 space-y-4 animate-fade-in max-w-3xl"}>
      {!offerId && <h3 className="text-base font-semibold text-white flex items-center gap-2"><GraduationCap className="w-5 h-5" /> {T.title}</h3>}
      <p className="text-xs text-gray-500">{offerId ? T.forOfferHint : T.hint}</p>
      <div className="flex flex-wrap items-end gap-3">
        {!offerId && <label className="text-xs text-gray-400 space-y-1">
          <span className="block">{T.scope}</span>
          <select
            value={scope}
            onChange={e => setScope(e.target.value as UpskillScope)}
            className="rounded-lg border border-white/10 bg-[#16161f] px-3 py-2 text-sm text-gray-200"
          >
            {SCOPES.map(s => <option key={s} value={s}>{T.scopes[s]}</option>)}
          </select>
        </label>}
        <button
          onClick={run}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <GraduationCap className="w-4 h-4" />}
          {busy ? T.busy : offerId ? T.forOffer : T.button}
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
