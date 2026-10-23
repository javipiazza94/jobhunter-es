import { Send } from "lucide-react";
import { SOURCE_COLORS, STATUS_COLORS } from "@/lib/ui";
import type { Application } from "@/lib/types";
import { APPLICATION_SORT_LABELS, defaultDirection, sortApplications, type ApplicationSortKey } from "@/lib/sort";
import type { ApplicationFilters } from "@/app/hooks/useApplicationFilters";
import { formatDate, t, useLocale } from "@/lib/i18n";

interface Props {
  applications: Application[];
  filters: ApplicationFilters;
  onSelectApplication: (a: Application) => void;
}

/** Pestaña «Candidaturas»: filtro por estado, orden y tabla. */
export function ApplicationsTab({ applications, filters, onSelectApplication }: Props) {
  useLocale();
  const {
    applicationStatusFilter, setApplicationStatusFilter,
    applicationSortKey, setApplicationSortKey, applicationSortDir, setApplicationSortDir,
  } = filters;

  const applicationStatuses = Array.from(new Set(applications.map(a => a.status))).sort();
  const filteredApplications = sortApplications(
    applications.filter(a => applicationStatusFilter === "all" || a.status === applicationStatusFilter),
    applicationSortKey, applicationSortDir,
  );

  return (
    <div className="glass-card overflow-hidden animate-fade-in">
      <div className="p-4 border-b border-white/5 bg-black/20 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">{t("applications.status_header")}</span>
          <select
            value={applicationStatusFilter} onChange={e => setApplicationStatusFilter(e.target.value)}
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none capitalize"
          >
            <option value="all">{t("applications.all_statuses")}</option>
            {applicationStatuses.map(s => (
              <option key={s} value={s} className="capitalize">{s}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">{t("applications.sort_by")}</span>
          <select
            value={applicationSortKey} onChange={e => {
              const key = e.target.value as ApplicationSortKey;
              setApplicationSortKey(key);
              // «Empresa (A-Z)» y «Ubicación» arrancan ascendentes; fecha y score, de mayor a menor
              setApplicationSortDir(defaultDirection(key));
            }}
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none"
          >
            {(Object.keys(APPLICATION_SORT_LABELS) as ApplicationSortKey[]).map(k => (
              <option key={k} value={k}>{APPLICATION_SORT_LABELS[k]}</option>
            ))}
          </select>
          <button
            onClick={() => setApplicationSortDir(d => d === "asc" ? "desc" : "asc")}
            title={applicationSortDir === "asc" ? t("applications.sort_asc") : t("applications.sort_desc")}
            aria-label={t("applications.invert_order")}
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 hover:border-indigo-500/50"
          >
            {applicationSortDir === "asc" ? t("applications.sort_asc") : t("applications.sort_desc")}
          </button>
        </div>
        <div className="ml-auto">
          <span className="text-sm font-medium text-indigo-300/80 bg-indigo-500/10 px-3 py-1 rounded-lg border border-indigo-500/20">
            {t("applications.count", { filtered: filteredApplications.length, total: applications.length })}
          </span>
        </div>
      </div>
      {applications.length === 0 ? (
        <div className="p-16 text-center border-dashed border-white/10">
          <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-4">
            <Send className="w-8 h-8 text-gray-500" />
          </div>
          <h3 className="text-lg font-medium text-gray-300 mb-2">{t("applications.empty_title")}</h3>
          <p className="text-sm text-gray-500">{t("applications.empty_hint")}</p>
        </div>
      ) : filteredApplications.length === 0 ? (
        <div className="p-16 text-center border-dashed border-white/10">
          <p className="text-sm text-gray-500">{t("applications.filter_empty")}</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-400 uppercase bg-black/40 border-b border-white/5 tracking-wider">
              <tr>
                <th className="px-6 py-4 font-semibold">{t("applications.offer_header")}</th>
                <th className="px-6 py-4 font-semibold">{t("applications.company_header")}</th>
                <th className="px-6 py-4 font-semibold">{t("applications.location_header")}</th>
                <th className="px-6 py-4 font-semibold">{t("applications.status_header")}</th>
                <th className="px-6 py-4 font-semibold text-right">{t("applications.score_date_header")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredApplications.map((a, idx) => (
                <tr
                  key={a.id}
                  onClick={() => onSelectApplication(a)}
                  className="hover:bg-white/[0.03] cursor-pointer transition-colors stagger-row"
                  style={{ animationDelay: `${idx * 0.02}s` }}
                >
                  <td className="px-6 py-4">
                    <div className="flex flex-col gap-1">
                      <span className="font-semibold text-gray-200 hover:text-indigo-400 transition-colors">
                        {a.job_title || t("applications.spontaneous")}
                      </span>
                      {a.offer_source && (
                        <span className={`text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded w-fit ${SOURCE_COLORS[a.offer_source] || SOURCE_COLORS.seed}`}>
                          {a.offer_source}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-gray-400 font-medium">{a.company_name}</td>
                  <td className="px-6 py-4 text-gray-400">{a.offer_location || "—"}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 rounded-md text-[10px] uppercase tracking-wider font-bold ${STATUS_COLORS[a.status] || "bg-gray-500/10 text-gray-400 border border-gray-500/20"}`}>
                      {a.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex flex-col items-end gap-1">
                      {a.relevance_score != null && (
                        <span className={`px-2 py-0.5 rounded text-xs font-bold border ${a.relevance_score >= 0.8 ? "bg-green-500/10 text-green-400 border-green-500/20" : a.relevance_score >= 0.65 ? "bg-yellow-500/10 text-yellow-400 border-yellow-500/20" : "bg-gray-500/10 text-gray-400 border-gray-500/20"}`}>
                          {(a.relevance_score * 100).toFixed(0)}%
                        </span>
                      )}
                      <span className="text-xs text-gray-500 font-mono">
                        {a.sent_at ? formatDate(a.sent_at) : "—"}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
