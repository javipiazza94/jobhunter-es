"""
schemas.py — Contrato de la API (modelos de respuesta y de petición).

`extra="allow"` mantiene cualquier columna adicional que la BD devuelva, así que añadir una columna
no rompe nada; lo que se tipa es lo que el dashboard lee. Los tipos TypeScript equivalentes viven en
frontend/lib/types.ts; tests/test_api_contract.py comprueba que no se desajusten.
"""
from pydantic import BaseModel, ConfigDict


class _Out(BaseModel):
    model_config = ConfigDict(extra="allow")


class StatsOut(_Out):
    companies: int
    job_offers: int
    generic_offers: int
    relevant_offers: int
    applications_sent: int
    contacts_found: int


class DashboardStatsOut(_Out):
    sent_this_week: int
    pending_approval: int
    total_sent: int
    response_rate: float
    sent_by_track: dict[str, int]


class CompanyOut(_Out):
    id: str
    name: str
    website: str | None = None
    careers_url: str | None = None
    sector: str | None = None
    city: str | None = None
    country: str | None = None
    remote_policy: str | None = None
    salary_transparent: int | None = None
    offer_count: int = 0
    application_count: int = 0


class TrackOut(_Out):
    id: str
    label: dict[str, str]
    kind: str


class OfferOut(_Out):
    id: str
    company_id: str | None = None
    title: str
    description: str | None = None
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    tech_stack: str | None = None
    url: str | None = None
    source: str | None = None
    posted_at: str | None = None
    is_relevant: int = 0
    relevance_score: float = 0.0
    scraped_at: str | None = None
    cv_profile: str | None = None
    experience_level: str | None = None
    contract_type: str | None = None
    posted_date: str | None = None
    salary_text: str | None = None
    followed_tier: int | None = None
    track_tag: str | None = None
    open_to_junior: int | None = None
    discard_status: str | None = None
    review_flags: str | None = None  # JSON: avisos de posting_guard y del filtro de idiomas
    job_kind: str | None = None
    generic_score: float | None = None
    company_name: str | None = None
    is_applied: int = 0
    modality: str | None = None


class ApplicationOut(_Out):
    id: str
    company_id: str | None = None
    job_offer_id: str | None = None
    contact_id: str | None = None
    status: str
    method: str | None = None
    sent_at: str | None = None
    cover_letter_used: str | None = None
    notes: str | None = None
    cover_letter_edited: str | None = None
    approved_at: str | None = None
    cv_profile: str | None = None
    company_name: str | None = None
    job_title: str | None = None
    offer_url: str | None = None
    offer_source: str | None = None
    offer_location: str | None = None
    relevance_score: float | None = None
    followup_count: int | None = None
    last_followup_at: str | None = None


class PendingApplicationOut(_Out):
    id: str
    company_name: str | None = None
    job_title: str | None = None
    job_url: str | None = None
    contact_value: str | None = None
    contact_type: str | None = None
    cover_letter_used: str | None = None
    cover_letter_edited: str | None = None
    cv_profile: str | None = None
    cv_file: str | None = None
    method: str | None = None


class ContactOfferOut(_Out):
    id: str
    title: str
    url: str | None = None
    relevance_score: float | None = None
    location: str | None = None


class ContactOut(_Out):
    id: str
    company_id: str | None = None
    type: str | None = None
    value: str
    method: str | None = None
    verified: int | None = None
    created_at: str | None = None
    company_name: str | None = None
    company_website: str | None = None
    offers: list[ContactOfferOut] = []


class HistoryEntryOut(_Out):
    id: str
    company_name: str
    company_domain: str | None = None
    email_used: str
    profile_used: str
    sent_at: str
    outcome: str | None = None
    notes: str | None = None
    application_id: str | None = None


class JobOut(_Out):
    id: str
    source: str
    status: str
    started_at: str
    finished_at: str | None = None
    returncode: int | None = None


class JobDetailOut(JobOut):
    log_tail: str = ""


class JobStartedOut(_Out):
    status: str
    source: str
    job_id: str


# ── Cuerpos de petición ────────────────────────────────────────────────────────────────────
# Con valor por defecto para que un cuerpo incompleto llegue al handler y se rechace con el
# mismo 400 de siempre.

class CoverLetterIn(BaseModel):
    cover_letter_edited: str = ""


class OutcomeIn(BaseModel):
    outcome: str = ""


class QuietApplicationOut(_Out):
    """Candidatura 'sent' sin respuesta (automation/followup.py). `draft` solo en /api/followups."""
    id: str
    status: str
    method: str | None = None
    channel: str
    sent_at: str | None = None
    cv_profile: str | None = None
    followup_count: int = 0
    last_followup_at: str | None = None
    days_quiet: int
    company_name: str | None = None
    job_title: str | None = None
    offer_url: str | None = None
    contact_value: str | None = None
    contact_type: str | None = None
    draft: str | None = None


class ResolveStaleIn(BaseModel):
    ids: list[str]


class InboxFileOut(BaseModel):
    name: str
    rows: int


class InboxReportOut(BaseModel):
    at: str
    files: list[str]
    new: int
    updated: int
    doubtful: int
    invalid: int
    to_review: int
    error: bool
    output: str


class InboxStatusOut(BaseModel):
    pending: list[InboxFileOut]
    last: InboxReportOut | None = None
    changes: int
    automatic: bool
