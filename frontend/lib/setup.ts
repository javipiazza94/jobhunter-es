// Lógica pura del asistente de primer arranque y de la pestaña Perfil (sin React ni red, se prueba con bun test).
import type {
  AISettings,
  MarketSource,
  ProfileDraft,
  SecretSource,
  SetupAnswers,
  SetupApplyResult,
  SetupStatus,
} from "@/lib/types";

export type WizardStep = 1 | 2 | 3;

/** Estado del asistente: el borrador revisado (paso 2) y dónde buscar (paso 3). */
export interface WizardState {
  draft: ProfileDraft;
  cvPath: string | null;
  markets: string[];
  /** Elección explícita del usuario por fuente; si no está, manda el default del catálogo. */
  sources: Record<string, boolean>;
  /** Fuentes `requires_ack` cuyo aviso aceptó el usuario. */
  acknowledged: Record<string, boolean>;
  followedCompanies: string[];
  /** IA que se guarda al aplicar (y la que usa el paso 1 para leer el CV). */
  ai: AISettings;
}

/** Una fuente tal como se muestra en el paso 3. */
export interface SuggestedSource {
  id: string;
  label: string;
  requires_ack: boolean;
  checked: boolean;
}

/** Mismo default que `AISettings.timeout_seconds` del backend. */
const AI_TIMEOUT_SECONDS = 120;

export function suggestedAI(): AISettings {
  return { provider: "ollama", model: null, base_url: null, timeout_seconds: AI_TIMEOUT_SECONDS };
}

export function emptyDraft(): ProfileDraft {
  return {
    full_name: "",
    email: "",
    phone: "",
    city: "",
    country: "",
    targets: [],
    years_experience: null,
    experience: [],
    tools: [],
    languages: [],
    modality: [],
    eligibility: { work_permit_countries: [], needs_sponsorship: null, driving_license: null },
  };
}

/** Ollama es el proveedor que sugiere el asistente: local y gratuito; si no está, todo cae a plantillas. */
export function emptyWizardState(): WizardState {
  return {
    draft: emptyDraft(),
    cvPath: null,
    markets: [],
    sources: {},
    acknowledged: {},
    followedCompanies: [],
    ai: suggestedAI(),
  };
}

export function addTarget(draft: ProfileDraft): ProfileDraft {
  return { ...draft, targets: [...draft.targets, { title: "", keywords: [] }] };
}

export function removeTarget(draft: ProfileDraft, index: number): ProfileDraft {
  return { ...draft, targets: draft.targets.filter((_, i) => i !== index) };
}

/** «a, b ,, A» → ["a", "b"]: sin vacíos ni duplicados (sin distinguir mayúsculas), en orden. */
export function splitList(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of text.split(",")) {
    const value = raw.trim();
    if (value && !seen.has(value.toLowerCase())) {
      seen.add(value.toLowerCase());
      out.push(value);
    }
  }
  return out;
}

export function joinList(values: string[]): string {
  return values.join(", ");
}

/** Fuentes de los mercados elegidos, sin repetir. Las `requires_ack` salen siempre desmarcadas salvo que el
 *  usuario las marque; el resto, según `default_on` o lo que ya eligiera el usuario. */
export function suggestedSources(
  markets: Record<string, MarketSource[]>,
  selectedMarkets: string[],
  choices: Record<string, boolean> = {},
): SuggestedSource[] {
  const byId = new Map<string, SuggestedSource>();
  for (const market of selectedMarkets) {
    for (const s of markets[market] ?? []) {
      const prev = byId.get(s.id);
      if (prev) {
        prev.requires_ack = prev.requires_ack || s.requires_ack;
        continue;
      }
      byId.set(s.id, { id: s.id, label: s.label, requires_ack: s.requires_ack, checked: s.default_on });
    }
  }
  return [...byId.values()].map(s => ({
    ...s,
    checked: s.id in choices ? choices[s.id] : s.checked && !s.requires_ack,
  }));
}

/** Errores que impiden pasar del paso `step` (vacío = se puede seguir). */
export function validateStep(
  step: WizardStep,
  state: WizardState,
  markets: Record<string, MarketSource[]> = {},
): string[] {
  const errors: string[] = [];
  if (step === 2 && !state.draft.targets.some(t => t.title.trim())) {
    errors.push("Añade al menos un objetivo profesional con título.");
  }
  if (step === 3) {
    const selected = suggestedSources(markets, state.markets, state.sources).filter(s => s.checked);
    if (!selected.length) errors.push("Elige al menos una fuente de ofertas.");
    for (const s of selected) {
      if (s.requires_ack && !state.acknowledged[s.id]) errors.push(`Acepta el aviso de ${s.label} o desmárcala.`);
    }
  }
  return errors;
}

/** Cuerpo de POST /api/setup/apply. Solo van las fuentes marcadas, y en `acknowledged_sources` solo las
 *  `requires_ack` marcadas cuyo aviso aceptó el usuario. */
export function toAnswers(state: WizardState, markets: Record<string, MarketSource[]>): SetupAnswers {
  const selected = suggestedSources(markets, state.markets, state.sources).filter(s => s.checked);
  return {
    draft: state.draft,
    markets: state.markets,
    sources: selected.map(s => s.id),
    acknowledged_sources: selected.filter(s => s.requires_ack && state.acknowledged[s.id]).map(s => s.id),
    followed_companies: state.followedCompanies.map(c => c.trim()).filter(Boolean),
    ai: state.ai,
    ui_language: "es",
    cv_path: state.cvPath,
  };
}

/** Estado del asistente a partir de la configuración actual (GET /api/setup/current): las fuentes del catálogo
 *  de esos mercados que no están activadas salen desmarcadas (no se vuelve a los defaults) y la IA se conserva. */
export function answersToState(answers: SetupAnswers, markets: Record<string, MarketSource[]>): WizardState {
  const enabled = new Set(answers.sources);
  const sources: Record<string, boolean> = {};
  for (const s of suggestedSources(markets, answers.markets)) sources[s.id] = enabled.has(s.id);
  for (const id of enabled) sources[id] = true;
  return {
    draft: answers.draft,
    cvPath: answers.cv_path ?? null,
    markets: answers.markets,
    sources,
    acknowledged: Object.fromEntries(answers.acknowledged_sources.map(id => [id, true])),
    followedCompanies: answers.followed_companies,
    ai: answers.ai ?? suggestedAI(),
  };
}

/** Qué hace el dashboard al arrancar (GET /api/setup/status): sin perfil, el asistente obligatorio; con perfil
 *  pero sin jobhunter.yaml propio (instalación antigua), solo un aviso que lo abre en modo cancelable. */
export type SetupPrompt = "wizard" | "banner" | "none";

export function setupPrompt(status: SetupStatus): SetupPrompt {
  if (status.needs_setup) return "wizard";
  return status.has_config ? "none" : "banner";
}

/** Una búsqueda que lanzar: el pipeline de los tracks (uno detrás de otro, en un solo trabajo) o una fuente suelta. */
export type SearchRun = { tracks: string[] } | { source: string };

/** Fuentes que el pipeline de track ya recorre (respetando las activadas); el resto va como fuente suelta. */
const TRACK_PIPELINE_SOURCES = new Set(["tecnoempleo", "infojobs", "computrabajo", "linkedin"]);
const STANDALONE_SOURCES = new Set(["manfred", "indeed"]);

/** Búsquedas tras aplicar el asistente: UN trabajo con todos los tracks nuevos (el backend los recorre en serie y
 *  reserva sus portales, así nunca hay dos Chromium/sesiones de LinkedIn a la vez) más Manfred/Indeed si se
 *  activaron (fuentes sueltas, sin navegador compartido con los tracks). */
export function searchRuns(result: SetupApplyResult): SearchRun[] {
  return [
    ...(result.tracks.length ? [{ tracks: result.tracks }] : []),
    ...result.sources.filter(s => STANDALONE_SOURCES.has(s) && !TRACK_PIPELINE_SOURCES.has(s)).map(source => ({ source })),
  ];
}

export const runName = (run: SearchRun): string => ("tracks" in run ? run.tracks.join(", ") : run.source);

export interface RunSummary {
  started: string[];
  failed: { name: string; message: string }[];
}

/** Qué arrancó y qué no (con el motivo que dio la API), a partir de `Promise.allSettled`. */
export function summarizeRuns(runs: SearchRun[], outcomes: PromiseSettledResult<unknown>[]): RunSummary {
  const summary: RunSummary = { started: [], failed: [] };
  runs.forEach((run, i) => {
    const o = outcomes[i];
    if (o?.status === "fulfilled") summary.started.push(runName(run));
    else summary.failed.push({ name: runName(run), message: o ? String((o.reason as Error)?.message ?? o.reason) : "sin respuesta" });
  });
  return summary;
}

/** Estado de un secreto sin mostrarlo nunca. */
export function secretStatus(has: boolean, source: SecretSource): string {
  if (!has) return "no configurada";
  return source === "env" ? "configurada (variable de entorno)" : "guardada en el llavero";
}

/** Mensaje legible del cuerpo de error de FastAPI (`detail` texto o lista de errores de validación). */
export function errorDetail(body: unknown, status: number): string {
  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map(d => (d && typeof d === "object" ? String((d as { msg?: unknown }).msg ?? "") : String(d))).filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  return `Error ${status} de la API`;
}

// ── Perfil guardado (profile.json) ↔ formulario de la pestaña Perfil ─────────────────────────────

export type StoredProfile = Record<string, unknown>;

export interface ProfileForm {
  full_name: string;
  email: string;
  phone: string;
  city: string;
  country: string;
  /** `level`: A1…C2 o «Nativo», como en profile.json. */
  languages: { language: string; level: string }[];
}

const str = (v: unknown): string => (typeof v === "string" ? v : "");
const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};

export function profileToForm(profile: StoredProfile): ProfileForm {
  const p = obj(profile.personal);
  const langs = Array.isArray(profile.languages) ? profile.languages : [];
  return {
    full_name: str(p.name),
    email: str(p.email),
    phone: str(p.phone),
    city: str(p.city),
    country: str(p.country),
    languages: langs.map(l => ({ language: str(obj(l).language), level: str(obj(l).level) })),
  };
}

/** Perfil completo con los cambios del formulario; el resto de claves se conserva tal cual. */
export function formToProfile(profile: StoredProfile, form: ProfileForm): StoredProfile {
  return {
    ...profile,
    personal: {
      ...obj(profile.personal),
      name: form.full_name.trim(),
      email: form.email.trim(),
      phone: form.phone.trim(),
      city: form.city.trim(),
      country: form.country.trim(),
    },
    languages: form.languages
      .filter(l => l.language.trim())
      .map(l => ({ language: l.language.trim(), level: l.level })),
  };
}
