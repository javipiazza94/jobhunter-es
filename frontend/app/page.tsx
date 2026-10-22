"use client";

import { useEffect, useState } from "react";
import { Building2, Briefcase, Send, Users, Play, Check, ChevronRight, Sparkles, Trash2 } from "lucide-react";
import { fetchStats, fetchCompanies, fetchOffers, fetchTracks, fetchContacts, fetchApplications, triggerScraper, fetchPendingApplications, createDrafts, markOfferSent, unmarkOfferSent, updateApplicationStatus, discardOffer, fetchFollowups, fetchStaleApplications, fetchSetupStatus, ApiError, type PendingApplication } from "@/lib/api";
import type { Application, Company, Contact, JobOffer, OfferEvaluation, QuietApplication, Stats, Track } from "@/lib/types";
import { failureMessage, isObject, settle, type Failures } from "@/lib/safeLoad";
import { MODALITY_BADGE, SOURCE_COLORS, STATUS_COLORS, parseReviewFlags, trackBadge, trackTabs } from "@/lib/ui";
import { useInboxSync } from "@/app/hooks/useInboxSync";
import { InboxBanner } from "@/app/components/InboxBanner";
import { SetupBanner } from "@/app/components/SetupBanner";
import { useOfferFilters } from "@/app/hooks/useOfferFilters";
import { useApplicationFilters } from "@/app/hooks/useApplicationFilters";
import { OffersTab } from "@/app/components/tabs/OffersTab";
import { TrackTab } from "@/app/components/tabs/TrackTab";
import { PendingTab } from "@/app/components/tabs/PendingTab";
import { CompaniesTab } from "@/app/components/tabs/CompaniesTab";
import { ContactsTab } from "@/app/components/tabs/ContactsTab";
import { ApplicationsTab } from "@/app/components/tabs/ApplicationsTab";
import { FollowupsTab } from "@/app/components/tabs/FollowupsTab";
import { ProfileTab } from "@/app/components/tabs/ProfileTab";
import { UpskillTab } from "@/app/components/tabs/UpskillTab";
import { SetupWizard } from "@/app/components/setup/SetupWizard";
import { InterviewPackPanel } from "@/app/components/InterviewPackPanel";
import { CompanyResearchPanel } from "@/app/components/CompanyResearchPanel";
import { OfferEvaluationPanel, T as EVAL_T, runBatchEvaluation } from "@/app/components/OfferEvaluationPanel";
import { LanguageSelector } from "@/app/components/LanguageSelector";
import { useT } from "@/lib/i18n";
import { setupPrompt, type RunSummary } from "@/lib/setup";

// Matches the `valid` set in backend/main.py::update_application_status
const APPLICATION_STATUSES = ["sent", "replied", "interview", "offer", "rejected", "withdrawn", "expired", "no_response"];

function StatCard({ icon: Icon, label, value, colorClass, active, onClick }: { icon: React.ElementType; label: string; value: number; colorClass: string; active?: boolean; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`glass-card p-5 flex items-center gap-4 animate-fade-in text-left w-full transition-all ${onClick ? "cursor-pointer hover:border-white/20 hover:-translate-y-0.5" : ""} ${active ? "ring-2 ring-indigo-500/60 border-indigo-500/40" : ""}`}
    >
      <div className={`p-3 rounded-xl bg-opacity-10 backdrop-blur-md border border-white/5 ${colorClass}`}>
        <Icon className="w-6 h-6" />
      </div>
      <div>
        <div className="text-3xl font-bold tracking-tight text-white mb-1">{value}</div>
        <div className="text-sm font-medium text-gray-400">{label}</div>
      </div>
    </button>
  );
}

export default function Dashboard() {
  const t = useT();
  const [stats, setStats] = useState<Stats | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [offers, setOffers] = useState<JobOffer[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [pendingApps, setPendingApps] = useState<PendingApplication[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [trackOffers, setTrackOffers] = useState<Record<string, JobOffer[]>>({});
  const [followups, setFollowups] = useState<QuietApplication[]>([]);
  const [staleApps, setStaleApps] = useState<QuietApplication[]>([]);
  const [tab, setTab] = useState<"offers" | "companies" | "contacts" | "applications" | "pending" | "followups" | "upskill" | "profile" | `track:${string}`>("offers");
  // Asistente: a pantalla completa en el primer arranque (no se puede cerrar) o reabierto desde Perfil.
  const [wizard, setWizard] = useState<"closed" | "first-run" | "rerun">("closed");
  // Instalación con perfil pero sin jobhunter.yaml propio: aviso descartable que abre el asistente cancelable.
  const [setupBanner, setSetupBanner] = useState(false);
  const [profileVersion, setProfileVersion] = useState(0);
  const [selectedOffer, setSelectedOffer] = useState<JobOffer | null>(null);
  const [selectedApplication, setSelectedApplication] = useState<Application | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);
  
  // Filtros (las pestañas Ofertas y Candidaturas los comparten con las tarjetas de resumen)
  const offerFilters = useOfferFilters();
  const { minScore, includeApplied, setMinScore, setIncludeApplied, resetOfferFilters } = offerFilters;
  const applicationFilters = useApplicationFilters();
  const { applicationStatusFilter, setApplicationStatusFilter } = applicationFilters;
  const [countryFilter, setCountryFilter] = useState("");
  
  const [loading, setLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const [togglingIds, setTogglingIds] = useState<Set<string>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const fetchAll = async () => {
    const failures: Failures = { names: [] };
    const trackList = await settle<Track[]>("tracks", fetchTracks(), [], failures);
    const [s, c, o, ct, a, p, fu, st, ...perTrack] = await Promise.all([
      settle<Stats | null>("estadísticas", fetchStats(), null, failures, isObject),
      settle<Company[]>("empresas", fetchCompanies(), [], failures),
      settle<JobOffer[]>("ofertas", fetchOffers({ limit: 2500 }), [], failures),
      settle<Contact[]>("contactos", fetchContacts(), [], failures),
      settle<Application[]>("candidaturas", fetchApplications(), [], failures),
      settle<PendingApplication[]>("candidaturas pendientes", fetchPendingApplications(), [], failures),
      settle<QuietApplication[]>("seguimientos", fetchFollowups(), [], failures),
      settle<QuietApplication[]>("candidaturas sin respuesta", fetchStaleApplications(), [], failures),
      ...trackList.map(t => settle<JobOffer[]>(`ofertas de ${t.id}`, fetchOffers({ track: t.id, limit: 500 }), [], failures)),
    ]);
    const byTrack: Record<string, JobOffer[]> = {};
    trackList.forEach((t, i) => { byTrack[t.id] = perTrack[i]; });
    return { s, c, o, ct, a, p, fu, st, trackList, byTrack, error: failureMessage(failures.names) };
  };

  const applyAll = ({ s, c, o, ct, a, p, fu, st, trackList, byTrack, error }: Awaited<ReturnType<typeof fetchAll>>) => {
    setStats(s);
    setCompanies(c);
    setOffers(o);
    setContacts(ct);
    setApplications(a);
    setPendingApps(p);
    setTracks(trackList);
    setTrackOffers(byTrack);
    setFollowups(fu);
    setStaleApps(st);
    if (error) {
      setActionMsg(error);
      setTimeout(() => setActionMsg(""), 8000);
    }
  };

  const load = async () => applyAll(await fetchAll());

  // Lo que Cowork o n8n dejan en el inbox lo carga la API sola; aquí solo se refresca el panel.
  const inbox = useInboxSync(async report => {
    await load();
    setActionMsg(report ? `Inbox: ${report.new} nuevas, ${report.updated} actualizadas` : "Inbox cargado");
    setTimeout(() => setActionMsg(""), 6000);
  });

  // Carga inicial: se obtiene y se aplica en el .then (no hay setState síncrono dentro del efecto).
  useEffect(() => {
    fetchAll().then(applyAll);
    // Un backend antiguo sin /api/setup/status simplemente no abre el asistente.
    fetchSetupStatus()
      .then(s => {
        const prompt = setupPrompt(s);
        if (prompt === "wizard") setWizard("first-run");
        setSetupBanner(prompt === "banner");
      })
      .catch(e => {
        // Un backend antiguo sin la ruta (404) simplemente no abre el asistente; cualquier otro fallo se avisa.
        if (!(e instanceof ApiError && e.status === 404)) console.warn("No se pudo comprobar el asistente:", e);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSetupDone = async ({ started, failed }: RunSummary) => {
    setWizard("closed");
    setSetupBanner(false);
    setProfileVersion(v => v + 1);
    const parts = [`Configuración guardada. Búsquedas lanzadas: ${started.join(", ") || "ninguna"}`];
    if (failed.length) parts.push(`No arrancaron: ${failed.map(f => `${f.name} (${f.message})`).join("; ")}`);
    setActionMsg(parts.join(". "));
    await load();
    // Los scrapers corren en segundo plano: se vuelve a cargar al rato para ver las primeras ofertas.
    setTimeout(() => { load(); setActionMsg(""); }, failed.length ? 30000 : 15000);
  };

  const handleScrape = async (source: string) => {
    setLoading(true);
    setActionMsg(`Scraping ${source}...`);
    const result = await triggerScraper(source);
    if (result?.detail) {
      // La API rechazó el lanzamiento (ya en marcha o ejecutada hace poco): se muestra el motivo.
      setActionMsg(String(result.detail));
      setTimeout(() => { setLoading(false); setActionMsg(""); }, 5000);
      return;
    }
    setTimeout(() => { load(); setLoading(false); setActionMsg(""); }, 2000);
  };

  const mapTrackOffers = (fn: (o: JobOffer) => JobOffer) =>
    setTrackOffers(prev => Object.fromEntries(Object.entries(prev).map(([id, list]) => [id, list.map(fn)])));

  const handleToggleSent = async (offer: JobOffer) => {
    if (togglingIds.has(offer.id)) return;
    setTogglingIds(prev => new Set(prev).add(offer.id));
    if (offer.is_applied) {
      await unmarkOfferSent(offer.id);
      setOffers(prev => prev.map(o => o.id === offer.id ? { ...o, is_applied: 0 } : o));
      mapTrackOffers(o => o.id === offer.id ? { ...o, is_applied: 0 } : o);
      setApplications(prev => prev.filter(a => a.job_offer_id !== offer.id));
    } else {
      await markOfferSent(offer.id);
      setOffers(prev => prev.map(o => o.id === offer.id ? { ...o, is_applied: 1 } : o));
      mapTrackOffers(o => o.id === offer.id ? { ...o, is_applied: 1 } : o);
      setApplications(prev => [{
        id: crypto.randomUUID(),
        company_name: offer.company_name || "Desconocida",
        job_title: offer.title,
        status: "sent",
        method: "manual",
        sent_at: new Date().toISOString(),
        offer_url: offer.url,
        offer_source: offer.source,
        offer_location: offer.location,
        relevance_score: offer.relevance_score,
        job_offer_id: offer.id,
      }, ...prev]);
    }
    setTogglingIds(prev => { const s = new Set(prev); s.delete(offer.id); return s; });
  };

  const handleDiscardOffer = async (offer: JobOffer) => {
    if (togglingIds.has(offer.id)) return;
    if (!confirm(`¿Descartar "${offer.title}"? Dejará de aparecer en las listas de ofertas (no se borra el historial).`)) return;
    setTogglingIds(prev => new Set(prev).add(offer.id));
    await discardOffer(offer.id, "expired");
    setOffers(prev => prev.filter(o => o.id !== offer.id));
    setTrackOffers(prev => Object.fromEntries(Object.entries(prev).map(([id, list]) => [id, list.filter(o => o.id !== offer.id)])));
    setTogglingIds(prev => { const s = new Set(prev); s.delete(offer.id); return s; });
    setSelectedOffer(prev => prev && prev.id === offer.id ? null : prev);
  };

  const toggleSelected = (id: string) =>
    setSelectedIds(prev => { const s = new Set(prev); if (s.has(id)) s.delete(id); else s.add(id); return s; });

  const selectMany = (ids: string[], selected: boolean) =>
    setSelectedIds(prev => { const s = new Set(prev); ids.forEach(id => selected ? s.add(id) : s.delete(id)); return s; });

  const allOffers = [...new Map([...offers, ...Object.values(trackOffers).flat()].map(o => [o.id, o])).values()];

  const runBulk = async (label: string, ids: string[], action: (id: string) => Promise<unknown>) => {
    setLoading(true);
    setActionMsg(`${label} ${ids.length}...`);
    const results = await Promise.allSettled(ids.map(action));
    const failed = results.filter(r => r.status === "rejected").length;
    setSelectedIds(new Set());
    await load();
    setLoading(false);
    setActionMsg(failed ? `${ids.length - failed} hechas, ${failed} con error` : "");
    if (failed) setTimeout(() => setActionMsg(""), 5000);
  };

  const handleBulkMarkSent = () =>
    runBulk("Marcando como candidatura", allOffers.filter(o => selectedIds.has(o.id) && !o.is_applied).map(o => o.id), markOfferSent);

  const handleBulkUnmarkSent = () =>
    runBulk("Quitando de candidaturas", allOffers.filter(o => selectedIds.has(o.id) && o.is_applied).map(o => o.id), unmarkOfferSent);

  const handleBulkDiscard = () => {
    const ids = [...selectedIds];
    if (!confirm(`¿Descartar ${ids.length} ofertas? Dejarán de aparecer en las listas (no se borra el historial).`)) return;
    return runBulk("Descartando", ids, id => discardOffer(id, "expired"));
  };

  // Evaluación con IA (/rank): lotes secuenciales en el backend (máx. 50 por petición); nunca cambia el score.
  const handleBulkEvaluate = async () => {
    const ids = [...selectedIds];
    setLoading(true);
    setActionMsg(EVAL_T.bulkBusy(ids.length));
    const { message, remaining } = await runBatchEvaluation(ids);
    setActionMsg(message);
    setSelectedIds(new Set(remaining)); // las no evaluadas siguen seleccionadas para reintentar
    await load();
    setLoading(false);
    setTimeout(() => setActionMsg(""), 8000);
  };

  const handleOfferEvaluated = (e: OfferEvaluation) => {
    const withSummary = (o: JobOffer) => o.id === e.offer_id ? { ...o, evaluation: { verdict: e.verdict, score: e.score } } : o;
    setOffers(prev => prev.map(withSummary));
    mapTrackOffers(withSummary);
  };

  const handleStatusChange = async (appId: string, newStatus: string) => {
    await updateApplicationStatus(appId, newStatus);
    setApplications(prev => prev.map(a => a.id === appId ? { ...a, status: newStatus } : a));
    setSelectedApplication(prev => prev && prev.id === appId ? { ...prev, status: newStatus } : prev);
  };

  const handleApply = async () => {
    setLoading(true);
    setActionMsg("Generando borradores...");
    try {
      const result = await createDrafts();
      setActionMsg(`${result.drafts_created} borradores creados`);
      await load();
      setTab("pending");
      setTimeout(() => setActionMsg(""), 3000);
    } finally {
      setLoading(false);
    }
  };

  const handleStatClick = (which: "companies" | "offers" | "relevant" | "sent" | "contacts") => {
    if (which === "companies") {
      setTab("companies");
    } else if (which === "offers") {
      resetOfferFilters();
      setMinScore(0);
      setIncludeApplied(true);
      setTab("offers");
    } else if (which === "relevant") {
      resetOfferFilters();
      setMinScore(0.55);
      setIncludeApplied(true);
      setTab("offers");
    } else if (which === "sent") {
      setApplicationStatusFilter("sent");
      setTab("applications");
    } else if (which === "contacts") {
      setTab("contacts");
    }
  };

  return (
    <div className="min-h-screen bg-[#0f0f14] text-gray-300 font-sans selection:bg-indigo-500/30">
      {wizard !== "closed" && (
        <SetupWizard
          prefill={wizard === "rerun"}
          onDone={handleSetupDone}
          onCancel={wizard === "rerun" ? () => setWizard("closed") : undefined}
        />
      )}
      {/* Header */}
      <header inert={wizard !== "closed"} className="sticky top-0 z-30 bg-[#0f0f14]/80 backdrop-blur-xl border-b border-white/5 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between animate-fade-in">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-[0_0_20px_rgba(99,102,241,0.3)]">
              <Briefcase className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">{t("app.title")}</h1>
              <p className="text-xs text-indigo-300/80 font-medium tracking-wide uppercase">{t("app.subtitle")}</p>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            {actionMsg && (
              <span className="text-sm text-indigo-400 font-medium px-4 py-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 animate-pulse">
                {actionMsg}
              </span>
            )}
            
            <div className="flex items-center p-1 bg-white/5 rounded-xl border border-white/5">
              {(["seed", "tecnoempleo", "infojobs", "manfred", "linkedin", "contacts"] as const).map(src => (
                <button
                  key={src}
                  onClick={() => handleScrape(src)}
                  disabled={loading}
                  className="px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-all capitalize disabled:opacity-40"
                >
                  {src}
                </button>
              ))}
            </div>
            
            <LanguageSelector />

            <button
              onClick={handleApply}
              disabled={loading}
              className="gradient-border group px-5 py-2.5 flex items-center gap-2 transition-all disabled:opacity-50"
            >
              <div className="absolute inset-0 bg-indigo-500/20 group-hover:bg-indigo-500/30 transition-colors"></div>
              <Play className="w-4 h-4 fill-white relative z-10 text-white group-hover:scale-110 transition-transform" /> 
              <span className="text-sm font-semibold text-white relative z-10 tracking-wide">{t("header.generateDrafts")}</span>
            </button>
          </div>
        </div>
      </header>

      <main inert={wizard !== "closed"} className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Analytics row */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-5">
            <StatCard
              icon={Building2} label="Empresas" value={stats.companies} colorClass="text-blue-400 bg-blue-500"
              active={tab === "companies"}
              onClick={() => handleStatClick("companies")}
            />
            <StatCard
              icon={Briefcase} label="Ofertas Totales" value={stats.job_offers} colorClass="text-purple-400 bg-purple-500"
              active={tab === "offers" && includeApplied && minScore === 0}
              onClick={() => handleStatClick("offers")}
            />
            <StatCard
              icon={Check} label="Relevantes (>55%)" value={stats.relevant_offers} colorClass="text-green-400 bg-green-500"
              active={tab === "offers" && minScore === 0.55}
              onClick={() => handleStatClick("relevant")}
            />
            <StatCard
              icon={Send} label="Enviadas" value={stats.applications_sent} colorClass="text-orange-400 bg-orange-500"
              active={tab === "applications" && applicationStatusFilter === "sent"}
              onClick={() => handleStatClick("sent")}
            />
            <StatCard
              icon={Users} label="Contactos Extraídos" value={stats.contacts_found} colorClass="text-teal-400 bg-teal-500"
              active={tab === "contacts"}
              onClick={() => handleStatClick("contacts")}
            />
          </div>
        )}

        {setupBanner && <SetupBanner onOpen={() => setWizard("rerun")} onDismiss={() => setSetupBanner(false)} />}
        <InboxBanner status={inbox.status} syncing={inbox.syncing} onSync={inbox.sync} />

        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 p-1.5 bg-white/5 backdrop-blur-sm border border-white/5 rounded-2xl w-fit animate-slide-in">
          {(
            [
              { id: "offers", label: t("tabs.offers"), count: offers.length },
              ...trackTabs(tracks, trackOffers),
              { id: "companies", label: t("tabs.companies"), count: companies.length },
              { id: "contacts", label: t("tabs.contacts"), count: contacts.length },
              { id: "applications", label: t("tabs.applications"), count: applications.length },
              { id: "pending", label: t("tabs.pending"), count: pendingApps.length },
              { id: "followups", label: t("tabs.followups"), count: followups.length },
              { id: "upskill", label: t("tabs.upskill") },
              { id: "profile", label: t("tabs.profile") },
            ] as { id: typeof tab; label: string; count?: number }[]
          ).map(item => (
            <button
              key={item.id}
              onClick={() => { setSelectedIds(new Set()); setTab(item.id); }}
              className={`relative px-5 py-2 text-sm font-medium rounded-xl transition-all duration-300 ${
                tab === item.id 
                  ? "text-white bg-white/10 shadow-[0_2px_10px_rgba(0,0,0,0.2)] border border-white/10" 
                  : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
              }`}
            >
              {item.label} 
              {item.count !== undefined && (
                <span className={`ml-2 px-2 py-0.5 rounded-md text-xs ${tab === item.id ? 'bg-white/20' : 'bg-black/20'}`}>
                  {item.count}
                </span>
              )}
              {item.id === "pending" && !!item.count && (
                <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-amber-500 animate-pulse shadow-[0_0_8px_rgba(245,158,11,0.6)]" />
              )}
            </button>
          ))}
        </div>

        {/* Tab Content: Offers */}
        {tab === "offers" && (
          <OffersTab
            offers={offers}
            tracks={tracks}
            filters={offerFilters}
            selectedIds={selectedIds}
            onToggleSelected={toggleSelected}
            onSelectMany={selectMany}
            onSelectOffer={setSelectedOffer}
          />
        )}

        {/* Other tabs will follow the same pattern, abbreviated here for space */}
        {tab === "pending" && <PendingTab pendingApps={pendingApps} tracks={tracks} onAction={load} />}

        {tab === "followups" && <FollowupsTab followups={followups} stale={staleApps} onAction={load} />}

        {tab === "upskill" && <UpskillTab />}

        {tab === "profile" && <ProfileTab key={profileVersion} onRerunWizard={() => setWizard("rerun")} />}
        
        {tracks.filter(t => tab === `track:${t.id}`).map(t => (
          <TrackTab
            key={t.id}
            track={t}
            offers={trackOffers[t.id] ?? []}
            applications={applications}
            selectedIds={selectedIds}
            onToggleSelected={toggleSelected}
            onSelectMany={selectMany}
            onSelectOffer={setSelectedOffer}
            onSelectApplication={setSelectedApplication}
          />
        ))}

        {selectedIds.size > 0 && (
          <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 rounded-xl border border-indigo-500/40 bg-[#16161f] px-4 py-2.5 shadow-xl">
            <span className="text-sm font-medium text-indigo-300">{selectedIds.size} seleccionadas</span>
            <button onClick={handleBulkMarkSent} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg bg-green-500/15 px-3 py-1.5 text-sm font-medium text-green-300 border border-green-500/30 hover:bg-green-500/25 disabled:opacity-40">
              <Check className="w-4 h-4" /> Poner como candidatura
            </button>
            <button onClick={handleBulkUnmarkSent} disabled={loading} className="rounded-lg px-3 py-1.5 text-sm text-gray-300 border border-white/10 hover:bg-white/5 disabled:opacity-40">
              Quitar candidatura
            </button>
            <button onClick={handleBulkEvaluate} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-500/15 px-3 py-1.5 text-sm font-medium text-indigo-200 border border-indigo-500/30 hover:bg-indigo-500/25 disabled:opacity-40">
              <Sparkles className="w-4 h-4" /> {EVAL_T.button}
            </button>
            <button onClick={handleBulkDiscard} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg bg-red-500/15 px-3 py-1.5 text-sm font-medium text-red-300 border border-red-500/30 hover:bg-red-500/25 disabled:opacity-40">
              <Trash2 className="w-4 h-4" /> Eliminar
            </button>
            <button onClick={() => setSelectedIds(new Set())} className="text-sm text-gray-500 hover:text-gray-300">Cancelar</button>
          </div>
        )}

        {tab === "companies" && (
          <CompaniesTab
            companies={companies}
            countryFilter={countryFilter}
            onCountryFilterChange={setCountryFilter}
            onSelectCompany={setSelectedCompany}
          />
        )}

        {tab === "contacts" && <ContactsTab contacts={contacts} onSelectContact={setSelectedContact} />}

        {tab === "applications" && (
          <ApplicationsTab applications={applications} filters={applicationFilters} onSelectApplication={setSelectedApplication} />
        )}

      </main>

      {/* Offer Detail Modal */}
      {selectedOffer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 animate-fade-in">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setSelectedOffer(null)}></div>
          <div className="relative w-full max-w-3xl max-h-[85vh] flex flex-col bg-[#16161f] border border-white/10 rounded-2xl shadow-[0_0_40px_rgba(0,0,0,0.5)] overflow-hidden">
            <div className="p-6 border-b border-white/5 flex items-start justify-between bg-white/5">
              <div>
                <h2 className="text-xl font-bold text-white mb-2">{selectedOffer.title}</h2>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-sm font-medium text-indigo-400">{selectedOffer.company_name || "Empresa Confidencial"}</span>
                  <span className="text-gray-500">•</span>
                  <span className="text-sm text-gray-400">{selectedOffer.location || "Remoto"}</span>
                  <span className="text-gray-500">•</span>
                  {selectedOffer.salary_text && <span className="text-xs text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2 py-0.5 rounded-md font-mono">{selectedOffer.salary_text}</span>}
                  {selectedOffer.modality && <span className={`text-xs px-2 py-0.5 rounded-md font-medium ${MODALITY_BADGE[selectedOffer.modality] ?? ""}`}>{selectedOffer.modality}</span>}
                </div>
              </div>
              <button onClick={() => setSelectedOffer(null)} className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto flex-1 custom-scrollbar">
              <div className="flex gap-2 mb-6">
                <span className={`px-3 py-1 rounded-lg text-sm font-bold tracking-wide border ${selectedOffer.relevance_score >= 0.8 ? "bg-green-500/10 text-green-400 border-green-500/20" : selectedOffer.relevance_score >= 0.65 ? "bg-yellow-500/10 text-yellow-400 border-yellow-500/20" : "bg-gray-500/10 text-gray-400 border-gray-500/20"}`}>
                  Score: {(selectedOffer.relevance_score * 100).toFixed(0)}%
                </span>
                {selectedOffer.cv_profile && <span className={`text-xs uppercase font-bold tracking-wider px-3 py-1 rounded-lg flex items-center ${trackBadge(selectedOffer.cv_profile, tracks).className}`}>Perfil: {trackBadge(selectedOffer.cv_profile, tracks).label}</span>}
                {selectedOffer.source && <span className={`text-xs uppercase font-bold tracking-wider px-3 py-1 rounded-lg flex items-center border border-current ${SOURCE_COLORS[selectedOffer.source] || SOURCE_COLORS.seed}`}>{selectedOffer.source}</span>}
              </div>

              <OfferEvaluationPanel key={selectedOffer.id} offerId={selectedOffer.id} onEvaluated={handleOfferEvaluated} />

              {selectedOffer.company_name && <CompanyResearchPanel key={selectedOffer.company_name} company={selectedOffer.company_name} />}

              <UpskillTab key={`upskill-${selectedOffer.id}`} offerId={selectedOffer.id} />

              {parseReviewFlags(selectedOffer.review_flags).length > 0 && (
                <div className="mb-6 p-4 rounded-xl bg-amber-500/5 border border-amber-500/20">
                  <h3 className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-2">Avisos de revisión</h3>
                  <ul className="text-sm text-amber-200/80 space-y-1 list-disc list-inside">
                    {parseReviewFlags(selectedOffer.review_flags).map(f => <li key={f}>{f}</li>)}
                  </ul>
                </div>
              )}

              <div>
                <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4 border-b border-white/5 pb-2">Descripción del Puesto</h3>
                {selectedOffer.description ? (
                  <div className="text-sm text-gray-400 leading-relaxed whitespace-pre-wrap font-sans">
                    {selectedOffer.description}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500 italic">No hay descripción disponible para esta oferta.</p>
                )}
              </div>
            </div>
            
            <div className="p-5 border-t border-white/5 bg-black/20 flex justify-between gap-3">
              <button
                onClick={() => handleDiscardOffer(selectedOffer)}
                disabled={togglingIds.has(selectedOffer.id)}
                className="px-4 py-2 text-sm font-medium text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded-xl transition-colors disabled:opacity-40 flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" /> Descartar oferta
              </button>
              <div className="flex gap-3">
                <button onClick={() => setSelectedOffer(null)} className="px-5 py-2 text-sm font-medium text-gray-300 hover:text-white bg-white/5 hover:bg-white/10 rounded-xl transition-colors">
                  Cerrar
                </button>
                {selectedOffer.url && (
                  <a href={selectedOffer.url} target="_blank" rel="noopener noreferrer" className="px-5 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl shadow-[0_0_15px_rgba(99,102,241,0.3)] transition-all flex items-center gap-2">
                    Abrir Oferta Original <ChevronRight className="w-4 h-4" />
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Company Detail Modal */}
      {selectedCompany && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setSelectedCompany(null)} />
          <div className="relative w-full max-w-md bg-[#16161f] border border-white/10 rounded-2xl shadow-[0_0_40px_rgba(0,0,0,0.5)] overflow-hidden">
            <div className="p-6 border-b border-white/5 bg-white/5 flex items-start justify-between">
              <div>
                <h2 className="text-lg font-bold text-white mb-1">{selectedCompany.name}</h2>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">{selectedCompany.sector}</span>
              </div>
              <button onClick={() => setSelectedCompany(null)} className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div className="p-6 grid grid-cols-2 gap-3 text-sm">
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">País</div>
                <div className="text-gray-300">{selectedCompany.country || "—"}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Modalidad</div>
                <div className="text-gray-300">{selectedCompany.remote_policy || "—"}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Ofertas</div>
                <div className="text-gray-300 font-mono font-bold">{selectedCompany.offer_count}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Enviadas</div>
                <div className={`font-mono font-bold ${selectedCompany.application_count > 0 ? "text-emerald-400" : "text-gray-500"}`}>{selectedCompany.application_count}</div>
              </div>
            </div>
            <div className="px-6 pb-6 flex gap-2">
              {selectedCompany.website && (
                <a href={selectedCompany.website} target="_blank" rel="noopener noreferrer" className="flex-1 text-center px-4 py-2 text-sm font-medium text-gray-300 bg-white/5 hover:bg-white/10 rounded-xl transition-colors">Web</a>
              )}
              {selectedCompany.careers_url && (
                <a href={selectedCompany.careers_url} target="_blank" rel="noopener noreferrer" className="flex-1 text-center px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition-colors flex items-center justify-center gap-1">Empleos <ChevronRight className="w-4 h-4"/></a>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Contact Detail Modal */}
      {selectedContact && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setSelectedContact(null)} />
          <div className="relative w-full max-w-lg bg-[#16161f] border border-white/10 rounded-2xl shadow-[0_0_40px_rgba(0,0,0,0.5)] overflow-hidden">
            <div className="p-6 border-b border-white/5 bg-white/5 flex items-start justify-between">
              <div>
                <div className="font-mono text-indigo-400 font-semibold mb-1">{selectedContact.value}</div>
                <p className="text-sm text-gray-400">{selectedContact.company_name || "Empresa desconocida"}</p>
              </div>
              <button onClick={() => setSelectedContact(null)} className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div className="p-6 flex flex-col gap-4">
              <div className="flex gap-2">
                <span className="bg-white/5 text-gray-400 border border-white/10 px-2 py-1 rounded text-[10px] uppercase font-bold tracking-wider">{selectedContact.type || "email"}</span>
                {selectedContact.method && <span className="bg-white/5 text-gray-400 border border-white/10 px-2 py-1 rounded text-[10px] uppercase font-bold tracking-wider">{selectedContact.method}</span>}
              </div>
              {selectedContact.offers.length > 0 && (
                <div>
                  <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">Ofertas asociadas</div>
                  <div className="flex flex-col gap-2">
                    {selectedContact.offers.map(o => (
                      <div key={o.id} className="flex items-center justify-between gap-3 bg-white/5 rounded-lg px-3 py-2">
                        {o.url ? (
                          <a href={o.url} target="_blank" rel="noopener noreferrer" className="text-sm text-gray-300 hover:text-indigo-400 truncate font-medium flex-1">{o.title}</a>
                        ) : (
                          <span className="text-sm text-gray-300 truncate font-medium flex-1">{o.title}</span>
                        )}
                        <span className="text-xs text-gray-500 shrink-0">{o.location || "—"}</span>
                        <span className={`text-[10px] font-bold tracking-wider px-2 py-0.5 rounded shrink-0 border ${o.relevance_score >= 0.8 ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-gray-500/10 text-gray-400 border-gray-500/20"}`}>
                          {(o.relevance_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {selectedContact.company_website && (
              <div className="px-6 pb-6">
                <a href={selectedContact.company_website} target="_blank" rel="noopener noreferrer" className="w-full text-center block px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition-colors">Ver empresa</a>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Application Detail Modal */}
      {selectedApplication && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 animate-fade-in">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setSelectedApplication(null)} />
          <div className="relative w-full max-w-lg bg-[#16161f] border border-white/10 rounded-2xl shadow-[0_0_40px_rgba(0,0,0,0.5)] max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-white/5 bg-white/5 flex items-start justify-between">
              <div>
                <h2 className="text-lg font-bold text-white mb-1">{selectedApplication.job_title || "Candidatura espontánea"}</h2>
                <p className="text-sm text-indigo-400 font-medium">{selectedApplication.company_name}</p>
              </div>
              <button onClick={() => setSelectedApplication(null)} className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
              </button>
            </div>
            <div className="p-6 flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={selectedApplication.status}
                  onChange={e => handleStatusChange(selectedApplication.id, e.target.value)}
                  className={`px-2 py-1 rounded-md text-[10px] uppercase tracking-wider font-bold outline-none cursor-pointer ${STATUS_COLORS[selectedApplication.status] || "bg-gray-500/10 text-gray-400 border border-gray-500/20"}`}
                >
                  {APPLICATION_STATUSES.map(s => (
                    <option key={s} value={s} className="bg-[#16161f] text-gray-200 normal-case">{s}</option>
                  ))}
                </select>
                {selectedApplication.offer_source && (
                  <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-1 rounded ${SOURCE_COLORS[selectedApplication.offer_source] || SOURCE_COLORS.seed}`}>
                    {selectedApplication.offer_source}
                  </span>
                )}
                {selectedApplication.relevance_score != null && (
                  <span className={`px-2 py-1 rounded text-xs font-bold border ${selectedApplication.relevance_score >= 0.8 ? "bg-green-500/10 text-green-400 border-green-500/20" : selectedApplication.relevance_score >= 0.65 ? "bg-yellow-500/10 text-yellow-400 border-yellow-500/20" : "bg-gray-500/10 text-gray-400 border-gray-500/20"}`}>
                    {(selectedApplication.relevance_score * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-white/5 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Ubicación</div>
                  <div className="text-gray-300">{selectedApplication.offer_location || "—"}</div>
                </div>
                <div className="bg-white/5 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Enviada</div>
                  <div className="text-gray-300 font-mono">{selectedApplication.sent_at ? new Date(selectedApplication.sent_at).toLocaleDateString("es-ES") : "—"}</div>
                </div>
                <div className="bg-white/5 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Método</div>
                  <div className="text-gray-300 capitalize">{selectedApplication.method}</div>
                </div>
              </div>
              <InterviewPackPanel key={selectedApplication.id} applicationId={selectedApplication.id} />
            </div>
            <div className="p-5 border-t border-white/5 bg-black/20 flex justify-between gap-3">
              {selectedApplication.job_offer_id && (
                <button
                  onClick={async () => {
                    const offer = offers.find(o => o.id === selectedApplication.job_offer_id);
                    if (offer) {
                      await handleToggleSent(offer);
                    } else {
                      await unmarkOfferSent(selectedApplication.job_offer_id!);
                      setApplications(prev => prev.filter(a => a.id !== selectedApplication.id));
                    }
                    setSelectedApplication(null);
                  }}
                  className="px-4 py-2 text-sm font-medium text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded-xl transition-colors"
                >
                  Desmarcar como enviada
                </button>
              )}
              <div className="flex gap-2 ml-auto">
                <button onClick={() => setSelectedApplication(null)} className="px-4 py-2 text-sm font-medium text-gray-300 hover:text-white bg-white/5 hover:bg-white/10 rounded-xl transition-colors">
                  Cerrar
                </button>
                {selectedApplication.offer_url && (
                  <a href={selectedApplication.offer_url} target="_blank" rel="noopener noreferrer" className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition-all flex items-center gap-2">
                    Ver oferta <ChevronRight className="w-4 h-4" />
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
