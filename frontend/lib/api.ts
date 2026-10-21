import type { InboxReport, InboxStatus, QuietApplication, Track } from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8020";

// La API (sin login, solo local) exige esta cabecera en POST/PUT/PATCH/DELETE. Al no ser una
// cabecera «simple», el navegador hace preflight y CORS lo rechaza para webs ajenas.
// Ver docs/adr/0001-proteccion-de-la-api-local.md
const CLIENT_HEADER = { "X-JH-Client": "dashboard" };

function request(url: string, init: RequestInit = {}): Promise<Response> {
  if ((init.method ?? "GET").toUpperCase() === "GET") return fetch(url, init);
  return fetch(url, { ...init, headers: { ...CLIENT_HEADER, ...(init.headers as Record<string, string> | undefined) } });
}

export async function fetchStats() {
  const res = await request(`${BASE}/api/stats`);
  return res.json();
}

export async function fetchCompanies(params?: { sector?: string; country?: string }) {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  const res = await request(`${BASE}/api/companies${qs ? `?${qs}` : ""}`);
  return res.json();
}

export interface OfferFilters {
  relevant_only?: boolean;
  source?: string;
  salary_min?: number;
  salary_max?: number;
  posted_after?: string;
  min_score?: number;
  experience_level?: string;
  contract_type?: string;
  stack?: string;
  track?: string;
  modality?: string;
  location?: string;
  sort_by?: string;
  sort_dir?: string;
  limit?: number;
}

export async function fetchTracks(): Promise<Track[]> {
  const res = await request(`${BASE}/api/tracks`);
  return res.json();
}

export async function fetchOffers(filters: OfferFilters = {}) {
  const params = new URLSearchParams();
  for (const [key, val] of Object.entries(filters)) {
    if (val !== undefined && val !== null && val !== "" && val !== "all") {
      params.set(key, String(val));
    }
  }
  const qs = params.toString();
  const res = await request(`${BASE}/api/offers${qs ? `?${qs}` : ""}`);
  return res.json();
}

export async function fetchApplications(status?: string) {
  const qs = status ? `?status=${status}` : "";
  const res = await request(`${BASE}/api/applications${qs}`);
  return res.json();
}

export async function updateApplicationStatus(id: string, status: string) {
  const res = await request(`${BASE}/api/applications/${id}/status?status=${status}`, {
    method: "PATCH",
  });
  return res.json();
}

// Seguimiento: la API solo propone borradores; nunca envía nada.
export async function fetchFollowups(): Promise<QuietApplication[]> {
  const res = await request(`${BASE}/api/followups`);
  return res.json();
}

export async function fetchStaleApplications(): Promise<QuietApplication[]> {
  const res = await request(`${BASE}/api/followups/stale`);
  return res.json();
}

export async function markFollowupSent(id: string): Promise<{ id: string; followup?: boolean; detail?: string }> {
  const res = await request(`${BASE}/api/applications/${id}/followup`, { method: "POST" });
  return res.json();
}

export async function resolveStaleApplications(ids: string[]): Promise<{ resolved: number }> {
  const res = await request(`${BASE}/api/followups/stale/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  return res.json();
}

export async function fetchContacts() {
  const res = await request(`${BASE}/api/contacts`);
  return res.json();
}

export async function markOfferSent(offerId: string): Promise<{ id: string; created?: boolean; already_sent?: boolean }> {
  const res = await request(`${BASE}/api/offers/${offerId}/mark-sent`, { method: "POST" });
  return res.json();
}

export async function unmarkOfferSent(offerId: string): Promise<{ removed: boolean }> {
  const res = await request(`${BASE}/api/offers/${offerId}/mark-sent`, { method: "DELETE" });
  return res.json();
}

export async function discardOffer(offerId: string, reason: string = "expired") {
  const res = await request(`${BASE}/api/offers/${offerId}/discard?reason=${encodeURIComponent(reason)}`, { method: "POST" });
  return res.json();
}

export async function restoreOffer(offerId: string) {
  const res = await request(`${BASE}/api/offers/${offerId}/discard`, { method: "DELETE" });
  return res.json();
}

export async function fetchInboxStatus(): Promise<InboxStatus> {
  const res = await request(`${BASE}/api/inbox/status`);
  return res.json();
}

/** Carga ya lo que haya en backend/inbox/. Devuelve el informe, o null si no había nada. */
export async function syncInbox(): Promise<InboxReport | null> {
  const res = await request(`${BASE}/api/inbox/sync`, { method: "POST" });
  return res.json();
}

export async function triggerScraper(source: string) {
  const res = await request(`${BASE}/api/scraper/run?source=${source}`, { method: "POST" });
  return res.json();
}

export async function triggerApplications() {
  const res = await request(`${BASE}/api/applications/run`, { method: "POST" });
  return res.json();
}

export async function createDrafts(limit?: number): Promise<{ drafts_created: number; skipped_manual_review: number; skipped_duplicate: number; skipped_no_contact: number }> {
  const qs = limit !== undefined ? `?limit=${limit}` : "";
  const res = await request(`${BASE}/api/applications/create-drafts${qs}`, { method: "POST" });
  return res.json();
}

export async function fetchPendingApplications(): Promise<PendingApplication[]> {
  const res = await request(`${BASE}/api/applications/pending`);
  return res.json();
}

export async function approveApplication(id: string): Promise<{ id: string; success: boolean; status: string }> {
  const res = await request(`${BASE}/api/applications/${id}/approve`, { method: "POST" });
  return res.json();
}

export async function updateCoverLetter(id: string, coverLetterEdited: string): Promise<{ id: string; updated: boolean }> {
  const res = await request(`${BASE}/api/applications/${id}/cover-letter`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cover_letter_edited: coverLetterEdited }),
  });
  return res.json();
}

export async function rejectApplication(id: string): Promise<{ id: string; status: string }> {
  const res = await request(`${BASE}/api/applications/${id}/reject`, { method: "POST" });
  return res.json();
}

export async function markApplicationSentManual(id: string): Promise<{ id: string; success: boolean; status: string }> {
  const res = await request(`${BASE}/api/applications/${id}/mark-sent-manual`, { method: "POST" });
  return res.json();
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const res = await request(`${BASE}/api/stats/dashboard`);
  return res.json();
}

export async function fetchHistory(params?: { company?: string; profile?: string; outcome?: string }): Promise<HistoryEntry[]> {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  const res = await request(`${BASE}/api/history${qs ? `?${qs}` : ""}`);
  return res.json();
}

export async function exportHistoryCSV(): Promise<void> {
  const res = await request(`${BASE}/api/history/export?format=csv`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `job_hunter_history_${new Date().toISOString().split("T")[0]}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Types used by the new functions
export interface PendingApplication {
  id: string;
  company_name: string | null;
  job_title: string | null;
  job_url: string | null;
  contact_value: string | null;
  contact_type: string | null;
  cover_letter_used: string | null;
  cover_letter_edited: string | null;
  cv_profile: string | null;
  cv_file: string | null;
  method: string;
}

export interface DashboardStats {
  sent_this_week: number;
  pending_approval: number;
  total_sent: number;
  response_rate: number;
  sent_by_track: Record<string, number>;
}

export interface HistoryEntry {
  id: string;
  company_name: string;
  company_domain: string;
  email_used: string;
  profile_used: string;
  sent_at: string;
  outcome: string;
  notes: string | null;
  application_id: string | null;
}
