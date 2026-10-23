"""
schemas.py — Contrato de la API (modelos de respuesta y de petición).

`extra="allow"` mantiene cualquier columna adicional que la BD devuelva, así que añadir una columna
no rompe nada; lo que se tipa es lo que el dashboard lee. Los tipos TypeScript equivalentes viven en
frontend/lib/types.ts; tests/test_api_contract.py comprueba que no se desajusten.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from automation.profile_proposal import ProfileDraft
from search_config import AISettings, EmailSettings


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


class EvaluationSummaryOut(_Out):
    """Resumen de la evaluación con IA de una oferta (detalle en GET /api/offers/{id}/evaluation)."""
    verdict: str
    score: int


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
    evaluation: EvaluationSummaryOut | None = None  # opcional: None si no se ha evaluado con IA


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


# ── Asistente de primer arranque, perfil y ajustes (IA / email) ────────────────────────────
# Los secretos nunca viajan de vuelta: las respuestas solo dicen si existen y de dónde salen.

SecretSource = Literal["env", "keychain"] | None


class SetupStatusOut(_Out):
    needs_setup: bool
    has_profile: bool
    has_config: bool


class AttributionOut(_Out):
    name: str
    url: str
    required: bool = False


class MarketSourceOut(_Out):
    id: str
    label: str
    requires_ack: bool = False
    ack_warning: str = ""
    default_on: bool = False
    attribution: AttributionOut | None = None


class SetupProposalOut(_Out):
    """Borrador de perfil propuesto (por IA o vacío). `cv_path` solo si se subió un archivo."""
    draft: ProfileDraft
    source: Literal["ai", "empty"]
    text_chars: int
    cv_path: str | None = None


class SetupTextIn(BaseModel):
    text: str = Field("", max_length=500_000)
    ai: AISettings | None = None  # proveedor solo para esta llamada (el asistente aún no ha guardado nada)


class SourceSettingOut(_Out):
    """Una fuente de ofertas en Perfil: del catálogo de mercados y/o del jobhunter.yaml actual."""
    id: str
    label: str
    markets: list[str]
    requires_ack: bool
    enabled: bool
    acknowledged: bool
    country: str | None = None
    locations: list[str] = Field(default_factory=list)


class SourceParamIn(BaseModel):
    country: str | None = None
    locations: list[str] = Field(default_factory=list)


class SourcesIn(BaseModel):
    """PUT /api/settings/sources: fuentes activadas y fuentes `requires_ack` cuyo aviso aceptó el usuario."""
    enabled: list[str] = Field(default_factory=list, max_length=50)
    acknowledged: list[str] = Field(default_factory=list, max_length=50)
    params: dict[str, SourceParamIn] = Field(default_factory=dict)


class FollowedCompanyIn(BaseModel):
    """Una empresa seguida con su tier y alias opcionales."""
    name: str = Field(..., min_length=1, max_length=100)
    tier: int = Field(1, ge=1, le=5)
    aliases: list[str] = Field(default_factory=list)


class FollowedCompanyOut(_Out):
    name: str
    tier: int = 1
    aliases: list[str] = []


class AIKeyIn(BaseModel):
    """POST /api/settings/ai/key: guarda la clave en el llavero (vale antes de completar el asistente)."""
    provider: Literal["anthropic", "openai"]
    api_key: str = Field(..., min_length=1, max_length=500)


class AIKeyOut(_Out):
    provider: str
    has_key: bool
    key_source: Literal["env", "keychain"] | None = None


class ScreeningAnswerIn(BaseModel):
    """Respuesta guardada a una pregunta de cribado (`profile.screening_answers`)."""
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(max_length=5000)


class ProfileIn(BaseModel):
    """Validación laxa de profile.json (PUT /api/profile): solo se exige la forma de las secciones que lee la
    app; cualquier otra clave se guarda tal cual."""
    model_config = ConfigDict(extra="allow")

    personal: dict | None = None
    eligibility: dict | None = None
    availability: dict | None = None
    salary_expectation: dict | None = None
    stack: dict | None = None
    languages: list[dict] | None = None
    experience: list[dict] | None = None
    education: list[dict] | None = None
    certifications: list[str | dict] | None = None
    screening_answers: list[ScreeningAnswerIn] | None = None


class SetupApplyOut(_Out):
    tracks: list[str]
    sources: list[str]


class KeyFlagsOut(BaseModel):
    anthropic: bool
    openai: bool


class KeySourcesOut(BaseModel):
    anthropic: SecretSource = None
    openai: SecretSource = None


class AISettingsOut(_Out):
    provider: str
    model: str | None = None
    base_url: str | None = None
    timeout_seconds: int
    has_key: KeyFlagsOut
    key_source: KeySourcesOut


class AISettingsIn(AISettings):
    """Sección `ai:` completa más la clave de API opcional (va al llavero, nunca a jobhunter.yaml)."""
    api_key: str | None = None


class EmailSettingsOut(_Out):
    preset: str
    smtp_host: str
    smtp_port: int
    use_starttls: bool
    username: str | None = None
    from_name: str | None = None
    has_password: bool
    password_source: SecretSource = None


class EmailSettingsIn(EmailSettings):
    """Sección `email:` completa más la contraseña SMTP opcional (va al llavero)."""
    password: str | None = None


class CheckOut(_Out):
    ok: bool
    message: str


class PrepareIn(BaseModel):
    """POST /api/applications/{id}/prepare: `use_ai` None = IA si hay proveedor configurado;
    `builtin_templates` usa las plantillas integradas aunque haya propias activas (reserva si una falla)."""
    use_ai: bool | None = None
    builtin_templates: bool = False


class ScreeningQuestionIn(BaseModel):
    """Pregunta de cribado de un formulario; `max_chars` = límite de caracteres de la caja de respuesta."""
    text: str = Field(min_length=1, max_length=1000)
    max_chars: int | None = Field(default=None, ge=1, le=10000)


class ScreeningRequestIn(BaseModel):
    """POST /api/applications/{id}/answers."""
    questions: list[ScreeningQuestionIn] = Field(min_length=1, max_length=30)


class ScreeningAnswerOut(_Out):
    question: str
    answer: str
    source: Literal["profile", "ai", "needs_input"]
    suggestion: str | None = None
    truncated: bool = False


class ScreeningResultOut(_Out):
    answers: list[ScreeningAnswerOut]


class DocumentFileOut(_Out):
    """Documento archivado de una candidatura (JH_HOME/applications/<id>/)."""
    name: str
    size: int
    modified_at: str


class InterviewPackOut(_Out):
    """Pack de entrevista generado: ruta del archivo y su contenido Markdown."""
    path: str
    markdown: str


class EvaluateBatchIn(BaseModel):
    """POST /api/offers/evaluate-batch: ofertas a evaluar con IA, una tras otra."""
    ids: list[str] = Field(min_length=1, max_length=20)  # = offer_evaluation.MAX_BATCH


class CompanyResearchOut(_Out):
    """Investigación de una empresa en caché (GET/POST /api/companies/{name}/research)."""
    company: str
    summary: str
    products: list[str] = Field(default_factory=list)
    culture_signals: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    size_hint: str = ""
    sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fetched_date: str
    age_days: int = 0
    provider: str = ""


class UpskillIn(BaseModel):
    """POST /api/upskill: ámbito del mapa de huecos; `offer_ids` restringe el ámbito (y es obligatorio con «one»)."""
    scope: Literal["saved", "evaluated", "applied", "one"] = "saved"
    offer_ids: list[str] = Field(default_factory=list, max_length=200)


class UpskillGapOut(_Out):
    skill: str
    count: int


class UpskillOut(_Out):
    """Informe de huecos: ruta del Markdown guardado, su texto y el recuento determinista."""
    report_path: str
    markdown: str
    offers_analyzed: int = 0
    gaps: list[UpskillGapOut] = Field(default_factory=list)
    ai_used: bool = False


class ExpandIn(BaseModel):
    """POST /api/profile/expand: páginas que enlaza el usuario (GitHub, portfolio, certificaciones…)."""
    sources: list[str] = Field(min_length=1, max_length=5)  # = expand_profile.MAX_SOURCES


class ExpandProposalOut(_Out):
    """Competencia propuesta con su prueba y la fuente de la que sale."""
    name: str
    evidence: str = ""
    source_url: str = ""


class ExpandErrorOut(_Out):
    url: str
    error: str


class ExpandOut(_Out):
    proposals: list[ExpandProposalOut]
    errors: list[ExpandErrorOut]


class ExpandAcceptItemIn(BaseModel):
    """Competencia aceptada: nombre y fuente http(s) obligatorios (la procedencia queda en `skills_sources`)."""
    name: str = Field(min_length=1, max_length=200)
    evidence: str = Field("", max_length=1000)
    source_url: str

    @field_validator("source_url")
    @classmethod
    def _http_source(cls, value: str) -> str:
        from automation.expand_profile import clean_url

        url = clean_url(value)
        if url is None:
            raise ValueError("la fuente debe ser una URL http(s) sin credenciales")
        return url


class ExpandAcceptIn(BaseModel):
    """POST /api/profile/expand/accept: solo las propuestas que el usuario acepta."""
    items: list[ExpandAcceptItemIn] = Field(min_length=1, max_length=100)


class ExpandAcceptOut(_Out):
    added: list[str]
    skipped: list[str]
