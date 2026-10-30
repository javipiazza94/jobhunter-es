import type {
  AIKeyResult,
  AIKeyUpdate,
  AISettings,
  AISettingsUpdate,
  AISettingsView,
  CheckResult,
  EmailSettingsUpdate,
  EmailSettingsView,
  CompanyResearch,
  EvaluationBatchResult,
  ExpandAcceptResult,
  ExpandProposal,
  ExpandResult,
  FollowedCompanySetting,
  InboxReport,
  InboxStatus,
  InterviewPack,
  JobStarted,
  MarketSource,
  OllamaStatus,
  OfferEvaluation,
  DocumentFile,
  PreparedDocs,
  QuietApplication,
  SetupAnswers,
  SetupApplyResult,
  SetupProposal,
  SetupStatus,
  SourceSetting,
  SourcesUpdate,
  PrepareRequest,
  TemplateCompiler,
  TemplateEngine,
  TemplateInfo,
  TemplateKind,
  Track,
  ScreeningQuestion,
  ScreeningResult,
  UpskillReport,
  UpskillScope,
} from "@/lib/types";
import { errorDetail, type StoredProfile } from "@/lib/setup";
import { resolveApiBase } from "@/lib/apiBase";

// En escritorio la URL (con puerto dinámico) la inyecta Tauri; ver lib/apiBase.ts.
const BASE = resolveApiBase();

// La API (sin login, solo local) exige esta cabecera en POST/PUT/PATCH/DELETE. Al no ser una
// cabecera «simple», el navegador hace preflight y CORS lo rechaza para webs ajenas.
// Ver docs/adr/0001-proteccion-de-la-api-local.md
const CLIENT_HEADER = { "X-JH-Client": "dashboard" };

function request(url: string, init: RequestInit = {}): Promise<Response> {
  if ((init.method ?? "GET").toUpperCase() === "GET") return fetch(url, init);
  return fetch(url, { ...init, headers: { ...CLIENT_HEADER, ...(init.headers as Record<string, string> | undefined) } });
}

/** Error de la API con su código HTTP (el mensaje es el `detail` legible; `detail` lo trae tal cual). */
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly detail: unknown = undefined, readonly code: string | undefined = undefined) {
    super(message);
    this.name = "ApiError";
  }
}

/** Código estable de error: `{detail, code}` o `{detail: {code}}`. */
function errorCode(body: unknown, detail: unknown): string | undefined {
  const top = body && typeof body === "object" ? (body as { code?: unknown }).code : undefined;
  const nested = detail && typeof detail === "object" ? (detail as { code?: unknown }).code : undefined;
  const code = typeof top === "string" ? top : nested;
  return typeof code === "string" && code ? code : undefined;
}

/** Respuesta JSON o `ApiError(detail)` si la API respondió con error (las funciones nuevas siempre lo comprueban). */
async function checked<T>(res: Response): Promise<T> {
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;
    throw new ApiError(errorDetail(body, res.status), res.status, detail, errorCode(body, detail));
  }
  return body as T;
}

function sendJson(url: string, method: "POST" | "PUT" | "PATCH", body?: unknown): Promise<Response> {
  return request(url, {
    method,
    ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
}

// ── Asistente de primer arranque, perfil y ajustes ──────────────────────────────────────────────
// Los secretos (clave de API, contraseña SMTP) solo viajan del navegador a la API, nunca de vuelta.

export async function fetchSetupStatus(): Promise<SetupStatus> {
  return checked(await request(`${BASE}/api/setup/status`));
}

export async function fetchMarkets(lang?: string): Promise<Record<string, MarketSource[]>> {
  const query = lang ? `?lang=${encodeURIComponent(lang)}` : "";
  return checked(await request(`${BASE}/api/setup/markets${query}`));
}

/** Sube el CV (PDF/DOCX) en el campo `file`; fetch pone el Content-Type multipart y el Content-Length.
 *  `ai`: proveedor elegido en el asistente, solo para esta llamada (no se guarda). */
export async function uploadCv(file: Blob, filename?: string, ai?: AISettings): Promise<SetupProposal> {
  const form = new FormData();
  if (ai) form.append("ai", JSON.stringify(ai));
  if (filename) form.append("file", file, filename);
  else form.append("file", file);
  return checked(await request(`${BASE}/api/setup/cv`, { method: "POST", body: form }));
}

export async function proposeProfile(text: string, ai?: AISettings): Promise<SetupProposal> {
  return checked(await sendJson(`${BASE}/api/setup/propose`, "POST", ai ? { text, ai } : { text }));
}

/** Respuestas equivalentes a la configuración actual (para volver a ejecutar el asistente). */
export async function fetchSetupCurrent(): Promise<SetupAnswers> {
  return checked(await request(`${BASE}/api/setup/current`));
}

export async function fetchSourceSettings(): Promise<SourceSetting[]> {
  return checked(await request(`${BASE}/api/settings/sources`));
}

export async function saveSourceSettings(update: SourcesUpdate): Promise<SourceSetting[]> {
  return checked(await sendJson(`${BASE}/api/settings/sources`, "PUT", update));
}

export async function fetchFollowedCompaniesSettings(): Promise<FollowedCompanySetting[]> {
  return checked(await request(`${BASE}/api/settings/followed-companies`));
}

export async function saveFollowedCompaniesSettings(companies: FollowedCompanySetting[]): Promise<FollowedCompanySetting[]> {
  return checked(await sendJson(`${BASE}/api/settings/followed-companies`, "PUT", companies));
}

/** Guarda la clave de API en el llavero (vale antes de completar el asistente); nunca se devuelve. */
export async function saveAIKey(update: AIKeyUpdate): Promise<AIKeyResult> {
  return checked(await sendJson(`${BASE}/api/settings/ai/key`, "POST", update));
}

/** Lanza una búsqueda: una fuente o el pipeline de un track. Lanza ApiError si no arranca (ya en marcha...). */
/** `tracks`: varios tracks en un solo trabajo que los recorre uno detrás de otro (sin navegadores en paralelo). */
export async function startScraperRun(run: { source: string } | { track: string } | { tracks: string[] }): Promise<JobStarted> {
  const qs =
    "tracks" in run ? `tracks=${encodeURIComponent(run.tracks.join(","))}`
    : "track" in run ? `track=${encodeURIComponent(run.track)}`
    : `source=${encodeURIComponent(run.source)}`;
  return checked(await request(`${BASE}/api/scraper/run?${qs}`, { method: "POST" }));
}

export async function applySetup(answers: SetupAnswers): Promise<SetupApplyResult> {
  return checked(await sendJson(`${BASE}/api/setup/apply`, "POST", answers));
}

export async function fetchProfile(): Promise<StoredProfile> {
  return checked(await request(`${BASE}/api/profile`));
}

export async function saveProfile(profile: StoredProfile): Promise<StoredProfile> {
  return checked(await sendJson(`${BASE}/api/profile`, "PUT", profile));
}

/** Fusiona las claves de primer nivel dadas con el perfil guardado (el resto no se toca). */
export async function patchProfile(changes: StoredProfile): Promise<StoredProfile> {
  return checked(await sendJson(`${BASE}/api/profile`, "PATCH", changes));
}

export async function fetchAISettings(): Promise<AISettingsView> {
  return checked(await request(`${BASE}/api/settings/ai`));
}

export async function saveAISettings(update: AISettingsUpdate): Promise<AISettingsView> {
  return checked(await sendJson(`${BASE}/api/settings/ai`, "PUT", update));
}

export async function testAI(): Promise<CheckResult> {
  return checked(await sendJson(`${BASE}/api/settings/ai/test`, "POST"));
}

export async function fetchEmailSettings(): Promise<EmailSettingsView> {
  return checked(await request(`${BASE}/api/settings/email`));
}

export async function saveEmailSettings(update: EmailSettingsUpdate): Promise<EmailSettingsView> {
  return checked(await sendJson(`${BASE}/api/settings/email`, "PUT", update));
}

export async function testEmail(): Promise<CheckResult> {
  return checked(await sendJson(`${BASE}/api/settings/email/test`, "POST"));
}

export async function generateInterviewPack(applicationId: string): Promise<InterviewPack> {
  return checked(await sendJson(`${BASE}/api/applications/${encodeURIComponent(applicationId)}/interview-pack`, "POST"));
}

export async function answerScreeningQuestions(applicationId: string, questions: ScreeningQuestion[]): Promise<ScreeningResult> {
  return checked(await sendJson(`${BASE}/api/applications/${encodeURIComponent(applicationId)}/answers`, "POST", { questions }));
}

// ── Candidatura: CV y carta en PDF archivados (JH_HOME/applications/<id>/) ──

/** Genera CV y carta (puede tardar: compila LaTeX). `useAi` ausente = IA si hay proveedor configurado. */
export async function prepareApplication(
  applicationId: string, useAi?: boolean, opts: { builtinTemplates?: boolean } = {},
): Promise<PreparedDocs> {
  const body: PrepareRequest = useAi === undefined ? {} : { use_ai: useAi };
  if (opts.builtinTemplates) body.builtin_templates = true;
  return checked(await sendJson(`${BASE}/api/applications/${encodeURIComponent(applicationId)}/prepare`, "POST", body));
}

export async function fetchApplicationDocuments(applicationId: string): Promise<DocumentFile[]> {
  return checked(await request(`${BASE}/api/applications/${encodeURIComponent(applicationId)}/documents`));
}

/** URL para abrir un documento archivado (los PDF se muestran en el navegador con `inline`). */
export function applicationDocumentUrl(applicationId: string, name: DocumentFile["name"], inline = true): string {
  const base = `${BASE}/api/applications/${encodeURIComponent(applicationId)}/documents/${encodeURIComponent(name)}`;
  return inline && name.endsWith(".pdf") ? `${base}?inline=1` : base;
}

// ── Plantillas propias de CV y carta ──

export async function fetchTemplates(): Promise<TemplateInfo[]> {
  return checked(await request(`${BASE}/api/templates`));
}

/** Registra una plantilla (zip o un único .tex.j2/.typ.j2); la API compila de prueba antes de aceptarla. */
export async function uploadTemplate(
  file: Blob,
  filename: string,
  meta: {
    name: string; kind: TemplateKind; engine?: TemplateEngine; compiler?: TemplateCompiler | null;
    page_limit?: number; style_rules?: string;
    /** Confirmación obligatoria: una plantilla puede leer ficheros del equipo y meterlos en el PDF. */
    trusted: boolean;
  },
): Promise<TemplateInfo> {
  const form = new FormData();
  form.append("name", meta.name);
  form.append("kind", meta.kind);
  if (meta.engine) form.append("engine", meta.engine);
  if (meta.compiler) form.append("compiler", meta.compiler);
  form.append("trusted", meta.trusted ? "true" : "false");
  if (meta.page_limit) form.append("page_limit", String(meta.page_limit));
  if (meta.style_rules) form.append("style_rules", meta.style_rules);
  form.append("file", file, filename);
  return checked(await request(`${BASE}/api/templates`, { method: "POST", body: form }));
}

export async function activateTemplate(kind: TemplateKind, name: string): Promise<TemplateInfo> {
  return checked(await sendJson(`${BASE}/api/templates/${encodeURIComponent(name)}/activate?kind=${kind}`, "POST"));
}

export async function deleteTemplate(kind: TemplateKind, name: string): Promise<{ deleted: string }> {
  return checked(await request(`${BASE}/api/templates/${encodeURIComponent(name)}?kind=${kind}`, { method: "DELETE" }));
}

// ── Evaluación con IA de ofertas (/rank en la app): nunca cambia relevance_score ──

export async function evaluateOffer(offerId: string): Promise<OfferEvaluation> {
  return checked(await sendJson(`${BASE}/api/offers/${encodeURIComponent(offerId)}/evaluate`, "POST"));
}

export async function fetchOfferEvaluation(offerId: string): Promise<OfferEvaluation | null> {
  return checked(await request(`${BASE}/api/offers/${encodeURIComponent(offerId)}/evaluation`));
}

export async function evaluateOffersBatch(ids: string[]): Promise<EvaluationBatchResult> {
  return checked(await sendJson(`${BASE}/api/offers/evaluate-batch`, "POST", { ids }));
}

// ── Investigación de empresas con IA (caché de 30 días compartida con redactor, evaluación y entrevista) ──

export async function fetchCompanyResearch(name: string): Promise<CompanyResearch | null> {
  return checked(await request(`${BASE}/api/companies/${encodeURIComponent(name)}/research`));
}

export async function researchCompany(name: string): Promise<CompanyResearch> {
  return checked(await sendJson(`${BASE}/api/companies/${encodeURIComponent(name)}/research`, "POST"));
}

// ── Upskill (mapa de huecos y plan de estudio) y «Ampliar perfil» (competencias desde fuentes enlazadas) ──

export async function runUpskill(scope: UpskillScope, offerIds: string[] = []): Promise<UpskillReport> {
  return checked(await sendJson(`${BASE}/api/upskill`, "POST", { scope, offer_ids: offerIds }));
}

/** Propone competencias desde las URLs dadas; no guarda nada en el perfil. */
export async function expandProfile(sources: string[]): Promise<ExpandResult> {
  return checked(await sendJson(`${BASE}/api/profile/expand`, "POST", { sources }));
}

/** Guarda en el perfil solo las propuestas aceptadas. */
export async function acceptExpansion(items: ExpandProposal[]): Promise<ExpandAcceptResult> {
  return checked(await sendJson(`${BASE}/api/profile/expand/accept`, "POST", { items }));
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

/** Cierra una candidatura atascada en «enviando»: `sent` = el email salió (true) o no (false). */
export async function resolveSendingApplication(id: string, sent: boolean): Promise<{ id: string; status: string }> {
  return checked(await request(`${BASE}/api/applications/${encodeURIComponent(id)}/resolve-sending?sent=${sent}`, { method: "POST" }));
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

// ── App de escritorio ───────────────────────────────────────────────────────────────────────────
export async function fetchOllamaStatus(): Promise<OllamaStatus> {
  return checked(await request(`${BASE}/api/ai/ollama`));
}
