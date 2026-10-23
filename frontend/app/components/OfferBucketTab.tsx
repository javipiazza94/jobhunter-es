import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import type { Application, JobOffer } from "@/lib/types";
import { SOURCE_COLORS, STATUS_COLORS, TIER_BADGE } from "@/lib/ui";
import { t, useLocale } from "@/lib/i18n";

function TierAndLabel({ tier, label }: { tier: number | null; label: string | null }) {
  return (
    <div className="flex gap-2">
      {tier != null && (
        <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md ${TIER_BADGE[tier]?.className ?? ""}`}>
          {TIER_BADGE[tier]?.label ?? t("track.tier_label", { tier })}
        </span>
      )}
      <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md bg-white/5 text-gray-400 border border-white/10">
        {label || t("track.tag_other")}
      </span>
    </div>
  );
}

/** Columna que clasifica la oferta; cambia según la pestaña. */
export interface ClassificationColumn {
  header: string;
  render: (o: JobOffer) => ReactNode;
  /** Si también se muestra en la tabla de ofertas con candidatura. */
  inTracked: boolean;
}

/** Track estándar: insignia de la empresa seguida (si la hay) y etiqueta del track. */
export const STANDARD_COLUMN: ClassificationColumn = {
  get header() { return t("track.header_tier_tag"); },
  render: (o) => <TierAndLabel tier={o.followed_tier} label={o.track_tag} />,
  inTracked: true,
};

export const ISOLATED_COLUMN: ClassificationColumn = {
  get header() { return t("track.header_affinity"); },
  render: (o) => (
    <span className="text-xs font-mono px-2 py-0.5 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
      {o.generic_score != null ? o.generic_score.toFixed(2) : "—"}
    </span>
  ),
  inTracked: false,
};

interface Props {
  newOffers: JobOffer[];
  trackedOffers: JobOffer[];
  applications: Application[];
  selectedIds: Set<string>;
  column: ClassificationColumn;
  /** Mensaje cuando no hay ofertas nuevas. */
  emptyNew: ReactNode;
  /** Texto introductorio opcional sobre las tablas. */
  intro?: ReactNode;
  showJuniorBadge?: boolean;
  showSalary?: boolean;
  /** Tope del retardo escalonado de las animaciones (listas muy largas). */
  maxAnimationIndex?: number;
  onToggleSelected: (id: string) => void;
  onSelectMany: (ids: string[], selected: boolean) => void;
  onSelectOffer: (o: JobOffer) => void;
  onSelectApplication: (a: Application) => void;
}

const TABLE_HEAD = "text-xs text-gray-400 uppercase bg-black/40 border-b border-white/5 tracking-wider";

/** Pestaña de ofertas de un track: «Nuevas» y «Con candidatura». */
export function OfferBucketTab({
  newOffers, trackedOffers, applications, selectedIds, column, emptyNew, intro,
  showJuniorBadge = false, showSalary = false, maxAnimationIndex = Infinity,
  onToggleSelected, onSelectMany, onSelectOffer, onSelectApplication,
}: Props) {
  useLocale();
  const delay = (idx: number) => ({ animationDelay: `${Math.min(idx, maxAnimationIndex) * 0.03}s` });

  return (
    <div className="space-y-8 animate-fade-in">
      {intro && (
        <div className="glass-card p-4 text-sm text-gray-400 border-white/5">{intro}</div>
      )}
      {/* Nuevas */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-medium text-gray-200">{t("track.new_section")}</h2>
          <span className="text-sm font-mono text-indigo-300 bg-indigo-500/10 px-3 py-1 rounded-lg border border-indigo-500/20">
            {t("track.untracked_count", { count: newOffers.length })}
          </span>
        </div>
        {newOffers.length === 0 ? (
          <div className="glass-card p-10 text-center border-dashed border-white/10 text-sm text-gray-500">
            {emptyNew}
          </div>
        ) : (
          <div className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className={TABLE_HEAD}>
                  <tr>
                    <th className="px-4 py-4 w-10 text-center">
                      <input
                        type="checkbox"
                        checked={newOffers.length > 0 && newOffers.every(o => selectedIds.has(o.id))}
                        onChange={e => onSelectMany(newOffers.map(o => o.id), e.target.checked)}
                        aria-label={t("track.select_all_new")}
                        className="w-4 h-4 accent-indigo-500 cursor-pointer"
                      />
                    </th>
                    <th className="px-6 py-4 font-semibold">{t("track.header_offer")}</th>
                    <th className="px-6 py-4 font-semibold">{t("track.header_company")}</th>
                    <th className="px-6 py-4 font-semibold">{column.header}</th>
                    <th className="px-6 py-4 font-semibold">{t("track.header_location")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {newOffers.map((o, idx) => (
                    <tr key={o.id} className="hover:bg-white/[0.02] transition-colors stagger-row" style={delay(idx)}>
                      <td className="px-4 py-4 text-center">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(o.id)}
                          onChange={() => onToggleSelected(o.id)}
                          aria-label={t("offers.select_offer", { title: o.title })}
                          className="w-4 h-4 accent-indigo-500 cursor-pointer"
                        />
                      </td>
                      <td className="px-6 py-4">
                        <button onClick={() => onSelectOffer(o)} className="font-semibold text-left text-gray-200 hover:text-indigo-400 transition-colors inline-flex items-center gap-1">
                          {o.title} {o.url && <ChevronRight className="w-3 h-3 opacity-50" />}
                        </button>
                        <div className="flex items-center gap-2 mt-1.5">
                          {o.source && <span className={`text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded ${SOURCE_COLORS[o.source] || SOURCE_COLORS.seed}`}>{o.source}</span>}
                          {showJuniorBadge && o.open_to_junior === 1 && <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{t("track.junior_friendly")}</span>}
                          {showSalary && o.salary_text && <span className="text-xs text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2 py-0.5 rounded-md font-mono">{o.salary_text}</span>}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-gray-400 font-medium">{o.company_name || "—"}</td>
                      <td className="px-6 py-4">{column.render(o)}</td>
                      <td className="px-6 py-4 text-gray-300">{o.location || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Pendientes / Enviadas */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-medium text-gray-200">{t("track.tracked_section")}</h2>
          <span className="text-sm font-mono text-amber-400 bg-amber-400/10 px-3 py-1 rounded-lg border border-amber-400/20">
            {t("track.tracked_count", { count: trackedOffers.length })}
          </span>
        </div>
        {trackedOffers.length === 0 ? (
          <div className="glass-card p-10 text-center border-dashed border-white/10 text-sm text-gray-500">
            {t("track.empty_tracked")}
          </div>
        ) : (
          <div className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className={TABLE_HEAD}>
                  <tr>
                    <th className="px-6 py-4 font-semibold">{t("track.header_offer")}</th>
                    <th className="px-6 py-4 font-semibold">{t("track.header_company")}</th>
                    {column.inTracked && <th className="px-6 py-4 font-semibold">{column.header}</th>}
                    <th className="px-6 py-4 font-semibold">{t("track.header_status")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {trackedOffers.map((o, idx) => {
                    const app = applications.find(a => a.job_offer_id === o.id);
                    return (
                      <tr key={o.id} onClick={() => app && onSelectApplication(app)} className="hover:bg-white/[0.02] transition-colors cursor-pointer stagger-row" style={delay(idx)}>
                        <td className="px-6 py-4 font-semibold text-gray-200">{o.title}</td>
                        <td className="px-6 py-4 text-gray-400 font-medium">{o.company_name || "—"}</td>
                        {column.inTracked && <td className="px-6 py-4">{column.render(o)}</td>}
                        <td className="px-6 py-4">
                          <span className={`px-2 py-1 rounded-md text-[10px] uppercase tracking-wider font-bold ${STATUS_COLORS[app?.status ?? ""] || "bg-gray-500/10 text-gray-400 border border-gray-500/20"}`}>
                            {app?.status ?? "sent"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
