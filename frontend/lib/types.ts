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
