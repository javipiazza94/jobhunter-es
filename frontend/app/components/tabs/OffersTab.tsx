import { ChevronRight } from "lucide-react";
import { MODALITY_BADGE, SOURCE_COLORS, parseReviewFlags, trackBadge, trackLabel } from "@/lib/ui";
import type { JobOffer, Track } from "@/lib/types";
import { OFFER_SORT_LABELS, defaultDirection, sortOffers, type OfferSortKey } from "@/lib/sort";
import type { OfferFilters } from "@/app/hooks/useOfferFilters";
import { verdictClass, verdictLabel } from "@/app/components/OfferEvaluationPanel";

const OFFERS_PER_PAGE = 100;

interface Props {
  offers: JobOffer[];
  tracks: Track[];
  filters: OfferFilters;
  selectedIds: Set<string>;
  onToggleSelected: (id: string) => void;
  onSelectMany: (ids: string[], selected: boolean) => void;
  onSelectOffer: (o: JobOffer) => void;
}

/** Pestaña «Ofertas»: filtros, tabla con casillas de selección y paginación. */
export function OffersTab({ offers, tracks, filters, selectedIds, onToggleSelected, onSelectMany, onSelectOffer }: Props) {
  const {
    profileFilter, setProfileFilter, modalityFilter, setModalityFilter, sourceFilter, setSourceFilter,
    experienceFilter, setExperienceFilter, locationSearch, setLocationSearch, textSearch, setTextSearch,
    minScore, setMinScore, includeApplied, setIncludeApplied, onlyFollowed, setOnlyFollowed,
    offersPage, setOffersPage,
    offerSortKey, setOfferSortKey, offerSortDir, setOfferSortDir,
  } = filters;

  const filteredOffers = sortOffers(offers, offerSortKey, offerSortDir).filter(o => {
    if (!includeApplied && o.is_applied) return false;
    if (onlyFollowed && (o.followed_tier === null || o.followed_tier === undefined)) return false;
    if (textSearch) {
      const q = textSearch.toLowerCase();
      const searchable = `${o.title} ${o.company_name ?? ""} ${o.description ?? ""}`.toLowerCase();
      if (!searchable.includes(q)) return false;
    }
    if (profileFilter !== "all" && o.cv_profile !== profileFilter) return false;
    if (modalityFilter !== "all" && o.modality !== modalityFilter) return false;
    if (sourceFilter !== "all" && o.source !== sourceFilter) return false;
    if (experienceFilter !== "all" && o.experience_level !== experienceFilter) return false;
    if (locationSearch && !o.location?.toLowerCase().includes(locationSearch.toLowerCase())) return false;
    if (o.relevance_score < minScore) return false;
    return true;
  });

  const totalPages = Math.ceil(filteredOffers.length / OFFERS_PER_PAGE);
  const pagedOffers = filteredOffers.slice(offersPage * OFFERS_PER_PAGE, (offersPage + 1) * OFFERS_PER_PAGE);

  return (
    <div className="glass-card overflow-hidden animate-fade-in">
      {/* Filters Bar */}
      <div className="p-4 border-b border-white/5 bg-black/20 flex flex-wrap items-center gap-4">
        <input
          value={textSearch} onChange={e => { setTextSearch(e.target.value); setOffersPage(0); }}
          placeholder="Buscar por título, empresa, descripción..."
          className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none w-72 placeholder-gray-600"
        />

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">Perfil</span>
          <select
            value={profileFilter} onChange={e => { setProfileFilter(e.target.value); setOffersPage(0); }}
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none"
          >
            <option value="all">Todos</option>
            {tracks.filter(t => t.kind === "standard").map(t => (
              <option key={t.id} value={t.id}>{trackLabel(t)}</option>
            ))}
            <option value="manual_review">Revisar</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">Fuente</span>
          <select
            value={sourceFilter} onChange={e => { setSourceFilter(e.target.value); setOffersPage(0); }}
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none"
          >
            <option value="all">Todas</option>
            <option value="tecnoempleo">Tecnoempleo</option>
            <option value="infojobs">InfoJobs</option>
            <option value="manfred">Manfred</option>
            <option value="linkedin">LinkedIn</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">Nivel</span>
          <select
            value={experienceFilter} onChange={e => { setExperienceFilter(e.target.value); setOffersPage(0); }}
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none"
          >
            <option value="all">Todos</option>
            <option value="junior">Junior</option>
            <option value="mid">Mid</option>
            <option value="senior">Senior</option>
            <option value="lead">Lead</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">Ubicación</span>
          <input
            value={locationSearch} onChange={e => { setLocationSearch(e.target.value); setOffersPage(0); }}
            placeholder="Buscar ciudad..."
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none w-48 placeholder-gray-600"
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">Modalidad</span>
          <select
            value={modalityFilter} onChange={e => { setModalityFilter(e.target.value); setOffersPage(0); }}
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none"
          >
            <option value="all">Todas</option>
            <option value="remoto">Remoto</option>
            <option value="hibrido">Híbrido</option>
            <option value="presencial">Presencial</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">Score</span>
          <select
            value={minScore} onChange={e => { setMinScore(Number(e.target.value)); setOffersPage(0); }}
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none"
          >
            <option value={0}>Todos</option>
            <option value={0.5}>≥ 50%</option>
            <option value={0.65}>≥ 65%</option>
            <option value={0.8}>≥ 80%</option>
          </select>
        </div>

        <label className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-gray-500 cursor-pointer">
          <input
            type="checkbox"
            checked={includeApplied}
            onChange={e => { setIncludeApplied(e.target.checked); setOffersPage(0); }}
            className="accent-indigo-500"
          />
          Incluir enviadas
        </label>

        <label className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-gray-500 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyFollowed}
            onChange={e => { setOnlyFollowed(e.target.checked); setOffersPage(0); }}
            className="accent-indigo-500"
          />
          Solo empresas seguidas
        </label>

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">Ordenar por</span>
          <select
            value={offerSortKey}
            onChange={e => {
              const key = e.target.value as OfferSortKey;
              setOfferSortKey(key);
              setOfferSortDir(defaultDirection(key));
              setOffersPage(0);
            }}
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500/50 outline-none"
          >
            {(Object.keys(OFFER_SORT_LABELS) as OfferSortKey[]).map(k => (
              <option key={k} value={k}>{OFFER_SORT_LABELS[k]}</option>
            ))}
          </select>
          <button
            onClick={() => { setOfferSortDir(d => d === "asc" ? "desc" : "asc"); setOffersPage(0); }}
            title={offerSortDir === "asc" ? "Ascendente" : "Descendente"}
            aria-label="Invertir el orden"
            className="bg-[#16161f] border border-white/10 text-gray-300 text-sm rounded-lg px-3 py-1.5 hover:border-indigo-500/50"
          >
            {offerSortDir === "asc" ? "↑ Asc" : "↓ Desc"}
          </button>
        </div>

        <div className="ml-auto flex items-center gap-4">
          <span className="text-sm font-medium text-indigo-300/80 bg-indigo-500/10 px-3 py-1 rounded-lg border border-indigo-500/20">
            {filteredOffers.length} / {offers.length} ofertas
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-gray-400 uppercase bg-black/40 border-b border-white/5 tracking-wider">
            <tr>
              <th className="px-4 py-4 w-10 text-center">
                <input
                  type="checkbox"
                  checked={pagedOffers.length > 0 && pagedOffers.every(o => selectedIds.has(o.id))}
                  onChange={e => onSelectMany(pagedOffers.map(o => o.id), e.target.checked)}
                  aria-label="Seleccionar todas las ofertas de la página"
                  className="w-4 h-4 accent-indigo-500 cursor-pointer"
                />
              </th>
              <th className="px-6 py-4 font-semibold">Oferta</th>
              <th className="px-6 py-4 font-semibold">Empresa</th>
              <th className="px-6 py-4 font-semibold">Ubicación & Stats</th>
              <th className="px-6 py-4 font-semibold text-right">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {pagedOffers.map((o, idx) => (
              <tr key={o.id} className="hover:bg-white/[0.02] transition-colors stagger-row" style={{ animationDelay: `${idx * 0.03}s` }}>
                <td className="px-4 py-4 text-center">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(o.id)}
                    onChange={() => onToggleSelected(o.id)}
                    aria-label={`Seleccionar ${o.title}`}
                    className="w-4 h-4 accent-indigo-500 cursor-pointer"
                  />
                </td>
                <td className="px-6 py-4">
                  <div className="flex flex-col gap-1.5">
                    <button onClick={() => onSelectOffer(o)} className="font-semibold text-left text-gray-200 hover:text-indigo-400 transition-colors inline-flex items-center gap-1">
                      {o.title} {o.url && <ChevronRight className="w-3 h-3 opacity-50" />}
                    </button>
                    <div className="flex items-center gap-2">
                      {o.is_applied ? <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/20">Candidatura</span> : null}
                      {o.source && <span className={`text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded ${SOURCE_COLORS[o.source] || SOURCE_COLORS.seed}`}>{o.source}</span>}
                      {o.experience_level && <span className="text-xs text-gray-500 font-mono capitalize">{o.experience_level}</span>}
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 text-gray-400 font-medium">
                  {o.company_name || "—"}
                </td>
                <td className="px-6 py-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-gray-300">{o.location || "—"}</span>
                    <div className="flex gap-2">
                      {o.modality && <span className={`text-xs px-2 py-0.5 rounded-md font-medium ${MODALITY_BADGE[o.modality] ?? ""}`}>{o.modality}</span>}
                      {o.salary_text && <span className="text-xs text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2 py-0.5 rounded-md font-mono">{o.salary_text}</span>}
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 text-right">
                  <div className="flex flex-col items-end gap-2">
                    <span className={`px-3 py-1 rounded-lg text-sm font-bold tracking-wide border ${o.relevance_score >= 0.8 ? "bg-green-500/10 text-green-400 border-green-500/20" : o.relevance_score >= 0.65 ? "bg-yellow-500/10 text-yellow-400 border-yellow-500/20" : "bg-gray-500/10 text-gray-400 border-gray-500/20"}`}>
                      {(o.relevance_score * 100).toFixed(0)}%
                    </span>
                    {o.cv_profile && (() => {
                      const b = trackBadge(o.cv_profile, tracks);
                      return <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full ${b.className}`}>{b.label}</span>;
                    })()}
                    {o.evaluation && (
                      <span title={verdictLabel(o.evaluation.verdict)} className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${verdictClass(o.evaluation.score)}`}>
                        IA {o.evaluation.score}
                      </span>
                    )}
                    <ReviewFlagsBadge raw={o.review_flags} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>


      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-6 py-4 border-t border-white/5 bg-black/20">
          <span className="text-sm text-gray-500">
            {offersPage * OFFERS_PER_PAGE + 1}–{Math.min((offersPage + 1) * OFFERS_PER_PAGE, filteredOffers.length)} de {filteredOffers.length}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setOffersPage(p => Math.max(0, p - 1))}
              disabled={offersPage === 0}
              className="px-3 py-1.5 text-sm rounded-lg border border-white/10 text-gray-400 hover:text-white hover:border-indigo-500/50 hover:bg-indigo-500/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              ‹
            </button>
            {Array.from({ length: totalPages }, (_, i) => i).filter(i =>
              i === 0 || i === totalPages - 1 || Math.abs(i - offersPage) <= 2
            ).reduce<(number | "…")[]>((acc, i, idx, arr) => {
              if (idx > 0 && i - (arr[idx - 1] as number) > 1) acc.push("…");
              acc.push(i);
              return acc;
            }, []).map((item, idx) =>
              item === "…" ? (
                <span key={`dots-${idx}`} className="px-2 text-gray-600">…</span>
              ) : (
                <button
                  key={item}
                  onClick={() => setOffersPage(item as number)}
                  className={`px-3 py-1.5 text-sm rounded-lg border transition-all ${offersPage === item ? "bg-indigo-500/20 border-indigo-500/50 text-indigo-300 font-bold" : "border-white/10 text-gray-400 hover:text-white hover:border-white/20"}`}
                >
                  {(item as number) + 1}
                </button>
              )
            )}
            <button
              onClick={() => setOffersPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={offersPage === totalPages - 1}
              className="px-3 py-1.5 text-sm rounded-lg border border-white/10 text-gray-400 hover:text-white hover:border-indigo-500/50 hover:bg-indigo-500/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              ›
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Avisos de revisión de la oferta (idiomas, posting_guard); el detalle va en el tooltip y en el modal. */
function ReviewFlagsBadge({ raw }: { raw: string | null }) {
  const flags = parseReviewFlags(raw);
  if (flags.length === 0) return null;
  return (
    <span title={flags.join("\n")} className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
      ⚠ {flags.length} aviso{flags.length > 1 ? "s" : ""}
    </span>
  );
}
