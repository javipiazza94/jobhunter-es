// Tipos compartidos del dashboard (respuestas de la API).

export interface JobOffer {
  id: string;
  title: string;
  company_name: string | null;
  location: string | null;
  relevance_score: number;
  url: string | null;
  description: string | null;
  cv_profile: string | null;
  modality: string | null;
  salary_text: string | null;
  experience_level: string | null;
  contract_type: string | null;
  source: string;
  is_applied: number;
  followed_tier: number | null;
  track_tag: string | null;
  open_to_junior: number | null;
  job_kind: string | null;
  generic_score: number | null;
  review_flags: string | null; // JSON: avisos de posting_guard y del filtro de idiomas
  evaluation?: EvaluationSummary | null; // evaluación con IA (null/ausente: sin evaluar)
}

/** Resumen de la evaluación con IA de una oferta (GET /api/offers). Nunca cambia relevance_score. */
export interface EvaluationSummary {
  verdict: string;
  score: number;
}

export interface Application {
  id: string;
  company_name: string;
  job_title: string | null;
  status: string;
  method: string;
  sent_at: string;
  offer_url: string | null;
  offer_source: string | null;
  offer_location: string | null;
  relevance_score: number | null;
  job_offer_id: string | null;
  followup_count?: number | null;
  last_followup_at?: string | null;
}

/** Candidatura 'sent' sin respuesta (GET /api/followups y /api/followups/stale). */
export interface QuietApplication {
  id: string;
  status: string;
  method: string | null;
  channel: "email" | "linkedin" | "portal";
  sent_at: string | null;
  cv_profile: string | null;
  followup_count: number;
  last_followup_at: string | null;
  days_quiet: number;
  company_name: string | null;
  job_title: string | null;
  offer_url: string | null;
  contact_value: string | null;
  contact_type: string | null;
  draft: string | null;
}

export interface Stats {
  companies: number;
  job_offers: number;
  relevant_offers: number;
  applications_sent: number;
  contacts_found: number;
}

export interface Company {
  id: string;
  name: string;
  website: string;
  careers_url: string;
  sector: string;
  country: string;
  remote_policy: string | null;
  salary_transparent: number;
  offer_count: number;
  application_count: number;
}

export interface ContactOffer {
  id: string;
  title: string;
  url: string | null;
  relevance_score: number;
  location: string | null;
}

export interface Contact {
  id: string;
  value: string;
  type: string | null;
  method: string | null;
  company_name: string | null;
  company_website: string | null;
  offers: ContactOffer[];
}

export interface InboxFile {
  name: string;
  rows: number;
}

export interface InboxReport {
  at: string;
  files: string[];
  new: number;
  updated: number;
  doubtful: number;
  invalid: number;
  to_review: number;
  error: boolean;
  output: string;
}

export interface InboxStatus {
  pending: InboxFile[];
  last: InboxReport | null;
  changes: number;
  automatic: boolean;
}

/** Un tipo de trabajo que busca el usuario (una pestaña del dashboard). Viene de GET /api/tracks. */
export interface Track {
  id: string;
  label: Record<string, string>;
  kind: "standard" | "isolated";
}

// ── Asistente de primer arranque, perfil y ajustes (IA / email) ──────────────────────────────
// Los secretos nunca vuelven de la API: solo si existen (`has_*`) y de dónde salen (`*_source`).

export type SecretSource = "env" | "keychain" | null;
export type AIProviderId = "none" | "ollama" | "anthropic" | "openai" | "claude_cli" | "codex_cli";
export type CefrLevel = "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "native";
export type WorkModality = "remote" | "hybrid" | "onsite";

/** GET /api/setup/status */
export interface SetupStatus {
  needs_setup: boolean;
  has_profile: boolean;
  has_config: boolean;
}

/** Una fuente sugerida para un mercado (GET /api/setup/markets → Record<mercado, MarketSource[]>). */
export interface MarketSource {
  id: string;
  label: string;
  requires_ack: boolean;
  default_on: boolean;
}

export interface TargetDraft {
  title: string;
  keywords: string[];
}

export interface ExperienceDraft {
  company: string;
  role: string;
  start: string;
  end: string;
  description: string;
  stack: string[];
}

export interface LanguageDraft {
  language: string;
  level: CefrLevel;
}

export interface EligibilityDraft {
  work_permit_countries: string[];
  needs_sponsorship: boolean | null;
  driving_license: boolean | null;
}

export interface ProfileDraft {
  full_name: string;
  email: string;
  phone: string;
  city: string;
  country: string;
  targets: TargetDraft[];
  years_experience: number | null;
  experience: ExperienceDraft[];
  tools: string[];
  languages: LanguageDraft[];
  modality: WorkModality[];
  eligibility: EligibilityDraft;
}

/** POST /api/setup/cv (multipart `file`) y POST /api/setup/propose ({text}). */
export interface SetupProposal {
  draft: ProfileDraft;
  source: "ai" | "empty";
  text_chars: number;
  cv_path: string | null;
}

export interface AISettings {
  provider: AIProviderId;
  model: string | null;
  base_url: string | null;
  timeout_seconds: number;
}

/** Cuerpo de POST /api/setup/apply. */
export interface SetupAnswers {
  draft: ProfileDraft;
  markets: string[];
  sources: string[];
  acknowledged_sources: string[];
  followed_companies: string[];
  ai?: AISettings;
  ui_language?: "es" | "en";
  cv_path?: string | null;
}

/** Respuesta de POST /api/setup/apply. */
export interface SetupApplyResult {
  tracks: string[];
  sources: string[];
}

/** GET/PUT /api/settings/ai */
export interface AISettingsView {
  provider: AIProviderId;
  model: string | null;
  base_url: string | null;
  timeout_seconds: number;
  has_key: Record<"anthropic" | "openai", boolean>;
  key_source: Record<"anthropic" | "openai", SecretSource>;
}

/** Cuerpo de PUT /api/settings/ai (parcial: solo cambian los campos enviados); `api_key` va al llavero y
 *  nunca se devuelve. `base_url` solo para ollama/openai (con openai la clave se envía a esa URL). */
export interface AISettingsUpdate {
  provider?: AIProviderId;
  model?: string | null;
  base_url?: string | null;
  timeout_seconds?: number;
  api_key?: string;
}

/** GET/PUT /api/settings/email */
export interface EmailSettingsView {
  preset: "gmail" | "custom";
  smtp_host: string;
  smtp_port: number;
  use_starttls: boolean;
  username: string | null;
  from_name: string | null;
  has_password: boolean;
  password_source: SecretSource;
}

/** Cuerpo de PUT /api/settings/email (parcial); `password` va al llavero y nunca se devuelve. */
export interface EmailSettingsUpdate {
  preset?: "gmail" | "custom";
  smtp_host?: string;
  smtp_port?: number;
  use_starttls?: boolean;
  username?: string | null;
  from_name?: string | null;
  password?: string;
}

/** POST /api/settings/ai/test y /api/settings/email/test */
export interface CheckResult {
  ok: boolean;
  message: string;
}

/** POST /api/applications/{id}/interview-pack */
export interface InterviewPack {
  path: string;
  markdown: string;
}

/** POST /api/applications/{id}/prepare: cuerpo opcional (use_ai ausente = IA si hay proveedor). */
export interface PrepareRequest {
  use_ai?: boolean | null;
}

/** POST /api/applications/{id}/prepare: CV y carta en PDF archivados en JH_HOME/applications/<id>/. */
export interface PreparedDocs {
  application_id: string;
  cv_pdf: string;
  cover_pdf: string;
  source: "ai" | "deterministic";
  verification: Record<string, unknown>;
  warnings: string[];
}

/** GET /api/applications/{id}/documents: un documento descargable del archivo de la candidatura. */
export interface DocumentFile {
  name: "cv.pdf" | "cover.pdf" | "job_posting.md" | "interview.md";
  size: number;
  modified_at: string;
}

/** GET/PUT /api/settings/sources: una fuente de ofertas y su estado en jobhunter.yaml. */
export interface SourceSetting {
  id: string;
  label: string;
  markets: string[];
  requires_ack: boolean;
  enabled: boolean;
  acknowledged: boolean;
}

/** Cuerpo de PUT /api/settings/sources. Una fuente `requires_ack` solo se activa si viene en `acknowledged`. */
export interface SourcesUpdate {
  enabled: string[];
  acknowledged: string[];
}

/** Cuerpo de POST /api/settings/ai/key (la clave va al llavero y nunca se devuelve). */
export interface AIKeyUpdate {
  provider: "anthropic" | "openai";
  api_key: string;
}

/** Respuesta de POST /api/settings/ai/key. */
export interface AIKeyResult {
  provider: "anthropic" | "openai";
  has_key: boolean;
  key_source: SecretSource;
}

/** Respuesta de POST /api/scraper/run (fuente o track). */
export interface JobStarted {
  status: string;
  source: string;
  job_id: string;
}

/** Evaluación detallada con IA (POST /api/offers/{id}/evaluate, GET /api/offers/{id}/evaluation). */
export interface OfferEvaluation {
  offer_id: string;
  verdict: string;
  score: number;
  strengths: string[];
  gaps: string[];
  urgency: "expired" | "urgent" | "normal" | "unknown";
  expired: boolean;
  evaluated_at: string;
  provider: string;
}

/** POST /api/offers/evaluate-batch: cuerpo. */
export interface EvaluateBatchRequest {
  ids: string[];
}

/** Resultado de una oferta del lote (`skipped`: presupuesto de IA agotado, se puede volver a pedir). */
export interface EvaluationBatchItem {
  offer_id: string;
  status: "evaluated" | "skipped" | "not_found" | "error";
  evaluation: OfferEvaluation | null;
  error: string | null;
}

/** POST /api/offers/evaluate-batch: respuesta. */
export interface EvaluationBatchResult {
  results: EvaluationBatchItem[];
  evaluated: number;
  skipped: number;
  failed: number;
}
