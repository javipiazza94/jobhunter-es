"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, ArrowRight, FileUp, KeyRound, Loader2, PenLine, Plus, RotateCcw, Search, X } from "lucide-react";
import { applySetup, fetchMarkets, fetchSetupCurrent, proposeProfile, saveAIKey, startScraperRun, uploadCv } from "@/lib/api";
import {
  addTarget,
  answersToState,
  emptyWizardState,
  joinList,
  removeTarget,
  searchRuns,
  secretStatus,
  splitList,
  suggestedSources,
  summarizeRuns,
  toAnswers,
  validateStep,
  type RunSummary,
  type WizardState,
  type WizardStep,
} from "@/lib/setup";
import { KEY_PROVIDERS } from "@/lib/settings";
import type {
  AIProviderId,
  AISettings,
  CefrLevel,
  MarketSource,
  ProfileDraft,
  SetupProposal,
  WorkModality,
} from "@/lib/types";

// Textos de la interfaz en un solo sitio (la traducción llega en SP4).
export const T = {
  title: "Configura tu búsqueda",
  subtitle: "Tres pasos y empezamos a buscar ofertas para ti.",
  stepNames: { 1: "Tu CV", 2: "Revisa lo que hemos entendido", 3: "Dónde buscar" } as Record<WizardStep, string>,
  stepOf: (n: number) => `Paso ${n} de 3`,
  close: "Cerrar el asistente",
  back: "Atrás",
  next: "Siguiente",
  // Paso 1
  cvIntro: "Sube tu CV (PDF o DOCX). El texto se extrae en tu equipo; si tienes una IA configurada, propone tu perfil.",
  cvUpload: "Subir CV",
  cvUploading: "Leyendo el CV…",
  pasteLabel: "¿Prefieres pegar el texto del CV?",
  pasteButton: "Analizar texto",
  manual: "Rellenar a mano",
  manualHint: "Sin CV ni IA también funciona: completas el perfil en el siguiente paso.",
  emptyProposal: "No hemos podido interpretar el CV automáticamente (sin IA o sin respuesta). Rellena los campos a mano.",
  aiProposal: "Esto es lo que ha entendido la IA. Revísalo y corrige lo que haga falta.",
  // Paso 2
  personal: "Datos personales",
  fullName: "Nombre completo",
  email: "Email",
  phone: "Teléfono",
  city: "Ciudad",
  country: "País",
  targets: "Objetivos profesionales",
  targetsHint: "Cada objetivo es una pestaña del panel. Las palabras clave afinan la búsqueda.",
  targetTitle: "Puesto buscado",
  targetKeywords: "Palabras clave (separadas por comas)",
  addTarget: "Añadir objetivo",
  remove: "Quitar",
  yearsExperience: "Años de experiencia",
  experience: "Experiencia",
  company: "Empresa",
  role: "Puesto",
  start: "Inicio",
  end: "Fin",
  addExperience: "Añadir experiencia",
  tools: "Herramientas y tecnologías (separadas por comas)",
  languages: "Idiomas",
  language: "Idioma",
  level: "Nivel",
  addLanguage: "Añadir idioma",
  modality: "Modalidad",
  modalities: { remote: "Remoto", hybrid: "Híbrido", onsite: "Presencial" } as Record<WorkModality, string>,
  eligibility: "Elegibilidad",
  workPermit: "Países donde puedes trabajar (separados por comas)",
  sponsorship: "¿Necesitas patrocinio de visado?",
  drivingLicense: "¿Tienes carné de conducir?",
  unknown: "Sin indicar",
  yes: "Sí",
  no: "No",
  // Paso 3
  markets: "Mercados",
  marketNames: { spain: "España", latam: "Latinoamérica", remote: "Remoto", global: "Internacional" } as Record<string, string>,
  sources: "Fuentes de ofertas",
  noSources: "Elige al menos un mercado para ver sus fuentes.",
  ackWarning: (label: string) =>
    `${label} tiene condiciones de uso delicadas (sesión propia o términos del portal que limitan la automatización). Úsala bajo tu responsabilidad.`,
  ackCheckbox: (label: string) => `Entiendo el aviso y quiero usar ${label}`,
  followed: "Empresas que sigues (separadas por comas)",
  followedHint: "Sus ofertas salen destacadas.",
  ai: "IA para leer tu CV y adaptar las cartas",
  aiHint: "Opcional. Ollama funciona en local y gratis. Sin IA, rellenas el perfil a mano y las cartas usan la plantilla. Se guarda al terminar el asistente.",
  aiModel: "Modelo (vacío = el predeterminado)",
  aiKey: "Clave de API",
  aiKeySave: "Usar este proveedor",
  aiKeyStatus: (status: string) => `Clave: ${status}`,
  aiKeyHint: "La clave va al llavero del sistema; nunca se guarda en archivos ni se vuelve a mostrar.",
  aiProviders: {
    none: "Sin IA",
    ollama: "Ollama (local)",
    anthropic: "Anthropic (clave de API)",
    openai: "OpenAI (clave de API)",
    claude_cli: "Claude Code (CLI)",
    codex_cli: "Codex (CLI)",
  } as Record<AIProviderId, string>,
  loadingCurrent: "Cargando tu configuración actual…",
  marketsError: (msg: string) => `No se pudieron cargar los mercados: ${msg}`,
  retry: "Reintentar",
  progress: "Progreso del asistente",
  finish: "Buscar ofertas",
  finishing: "Guardando y lanzando la búsqueda…",
};

export const CEFR_LEVELS: CefrLevel[] = ["A1", "A2", "B1", "B2", "C1", "C2", "native"];
const LEVEL_LABEL = (l: CefrLevel) => (l === "native" ? "Nativo" : l);
const MODALITIES: WorkModality[] = ["remote", "hybrid", "onsite"];

const input =
  "w-full rounded-lg border border-white/10 bg-[var(--bg-input)] px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-indigo-500/60 focus:outline-none";
const label = "block text-xs font-medium text-gray-400 mb-1";
const card = "glass-card p-5 space-y-4";
const ghostBtn =
  "inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-gray-300 hover:bg-white/5 disabled:opacity-40";
const primaryBtn =
  "inline-flex items-center gap-2 rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-50";

/** Campo de lista separada por comas: el texto se edita libre y la lista se recalcula al escribir. */
export function ListInput({ id, value, onChange, placeholder }: { id: string; value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [text, setText] = useState(joinList(value));
  return (
    <input
      id={id}
      className={input}
      value={text}
      placeholder={placeholder}
      onChange={e => { setText(e.target.value); onChange(splitList(e.target.value)); }}
    />
  );
}

function TriState({ id, value, onChange }: { id: string; value: boolean | null; onChange: (v: boolean | null) => void }) {
  return (
    <select
      id={id}
      className={input}
      value={value === null ? "" : value ? "yes" : "no"}
      onChange={e => onChange(e.target.value === "" ? null : e.target.value === "yes")}
    >
      <option value="">{T.unknown}</option>
      <option value="yes">{T.yes}</option>
      <option value="no">{T.no}</option>
    </select>
  );
}

function Errors({ errors }: { errors: string[] }) {
  if (!errors.length) return null;
  return (
    <ul role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300 space-y-1">
      {errors.map(e => <li key={e}>{e}</li>)}
    </ul>
  );
}


// ── Paso 1: CV ──────────────────────────────────────────────────────────────────────────────────

/** Selector de IA del paso 1: se usa para leer el CV y se guarda al aplicar. La clave (anthropic/openai) va
 *  al llavero en cuanto se pulsa «Usar este proveedor»; nunca se guarda en el estado del asistente. */
export function AIPicker({ ai, keyStatus, keyBusy, onChange, onSaveKey }: {
  ai: AISettings;
  keyStatus: string | null;
  keyBusy: boolean;
  onChange: (ai: AISettings) => void;
  onSaveKey: (key: string) => void;
}) {
  const [key, setKey] = useState("");
  const usesKey = KEY_PROVIDERS.includes(ai.provider);
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label} htmlFor="w-ai">{T.ai}</label>
          <select
            id="w-ai"
            className={input}
            value={ai.provider}
            onChange={e => onChange({ ...ai, provider: e.target.value as AIProviderId, model: null, base_url: null })}
          >
            {(Object.keys(T.aiProviders) as AIProviderId[]).map(p => <option key={p} value={p}>{T.aiProviders[p]}</option>)}
          </select>
        </div>
        {ai.provider !== "none" && (
          <div>
            <label className={label} htmlFor="w-ai-model">{T.aiModel}</label>
            <input id="w-ai-model" className={input} value={ai.model ?? ""} onChange={e => onChange({ ...ai, model: e.target.value || null })} />
          </div>
        )}
      </div>
      {usesKey && (
        <div className="space-y-2">
          <label className={label} htmlFor="w-ai-key">{T.aiKey}</label>
          <div className="flex gap-2">
            <input
              id="w-ai-key"
              type="password"
              autoComplete="new-password"
              className={input}
              value={key}
              onChange={e => setKey(e.target.value)}
            />
            <button
              className={ghostBtn}
              disabled={keyBusy || !key.trim()}
              onClick={() => { onSaveKey(key.trim()); setKey(""); }}
            >
              {keyBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />} {T.aiKeySave}
            </button>
          </div>
          {keyStatus && <p className="text-xs text-gray-400">{T.aiKeyStatus(keyStatus)}</p>}
          <p className="text-xs text-gray-500">{T.aiKeyHint}</p>
        </div>
      )}
      <p className="text-xs text-gray-500">{T.aiHint}</p>
    </div>
  );
}

export function StepCv({ busy, onUpload, onPaste, onManual, aiPicker }: {
  busy: boolean;
  onUpload: (file: File) => void;
  onPaste: (text: string) => void;
  onManual: () => void;
  aiPicker?: React.ReactNode;
}) {
  const [text, setText] = useState("");
  return (
    <div className="space-y-5">
      {aiPicker && <div className={card}>{aiPicker}</div>}
      <div className={card}>
        <p className="text-sm text-gray-300">{T.cvIntro}</p>
        <label
          className={`${primaryBtn} cursor-pointer w-fit focus-within:ring-2 focus-within:ring-indigo-400 focus-within:ring-offset-2 focus-within:ring-offset-[var(--bg-primary)] ${busy ? "pointer-events-none opacity-50" : ""}`}
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileUp className="w-4 h-4" />}
          {busy ? T.cvUploading : T.cvUpload}
          <input
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="sr-only"
            disabled={busy}
            onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ""; }}
          />
        </label>
        <details className="text-sm">
          <summary className="cursor-pointer text-gray-400 hover:text-gray-200">{T.pasteLabel}</summary>
          <textarea className={`${input} mt-3 h-40`} value={text} onChange={e => setText(e.target.value)} />
          <button className={`${ghostBtn} mt-2`} disabled={busy || !text.trim()} onClick={() => onPaste(text)}>
            {T.pasteButton}
          </button>
        </details>
      </div>
      <div className={card}>
        <button className={ghostBtn} disabled={busy} onClick={onManual}>
          <PenLine className="w-4 h-4" /> {T.manual}
        </button>
        <p className="text-xs text-gray-500">{T.manualHint}</p>
      </div>
    </div>
  );
}

// ── Paso 2: revisión del borrador ──────────────────────────────────────────────────────────────

export function StepReview({ draft, onChange }: { draft: ProfileDraft; onChange: (d: ProfileDraft) => void }) {
  const set = <K extends keyof ProfileDraft>(key: K, value: ProfileDraft[K]) => onChange({ ...draft, [key]: value });
  const setAt = <K extends "targets" | "languages" | "experience">(key: K, i: number, patch: Partial<ProfileDraft[K][number]>) =>
    set(key, draft[key].map((item, j) => (j === i ? { ...item, ...patch } : item)) as ProfileDraft[K]);
  const dropAt = (key: "languages" | "experience", i: number) =>
    set(key, draft[key].filter((_, j) => j !== i) as never);

  return (
    <div className="space-y-5">
      <section className={card}>
        <h3 className="text-sm font-semibold text-white">{T.personal}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {(["full_name", "email", "phone", "city", "country"] as const).map(k => (
            <div key={k}>
              <label className={label} htmlFor={`d-${k}`}>{T[k === "full_name" ? "fullName" : k]}</label>
              <input id={`d-${k}`} className={input} value={draft[k]} onChange={e => set(k, e.target.value)} />
            </div>
          ))}
          <div>
            <label className={label} htmlFor="d-years">{T.yearsExperience}</label>
            <input
              id="d-years"
              type="number"
              min={0}
              max={60}
              className={input}
              value={draft.years_experience ?? ""}
              onChange={e => set("years_experience", e.target.value === "" ? null : Number(e.target.value))}
            />
          </div>
        </div>
      </section>

      <section className={card}>
        <h3 className="text-sm font-semibold text-white">{T.targets}</h3>
        <p className="text-xs text-gray-500">{T.targetsHint}</p>
        {/* La clave incluye el total: al quitar un objetivo se rehacen los campos de lista (texto local). */}
        {draft.targets.map((t, i) => (
          <div key={`${i}/${draft.targets.length}`} className="grid gap-3 sm:grid-cols-[1fr_1.5fr_auto] items-end">
            <div>
              <label className={label} htmlFor={`t-title-${i}`}>{T.targetTitle}</label>
              <input id={`t-title-${i}`} className={input} value={t.title} onChange={e => setAt("targets", i, { title: e.target.value })} />
            </div>
            <div>
              <label className={label} htmlFor={`t-kw-${i}`}>{T.targetKeywords}</label>
              <ListInput id={`t-kw-${i}`} value={t.keywords} onChange={v => setAt("targets", i, { keywords: v })} />
            </div>
            <button className={ghostBtn} aria-label={T.remove} onClick={() => onChange(removeTarget(draft, i))}>
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
        <button className={ghostBtn} onClick={() => onChange(addTarget(draft))}>
          <Plus className="w-4 h-4" /> {T.addTarget}
        </button>
      </section>

      <section className={card}>
        <h3 className="text-sm font-semibold text-white">{T.experience}</h3>
        {draft.experience.map((x, i) => (
          <div key={i} className="grid gap-3 sm:grid-cols-[1fr_1fr_0.6fr_0.6fr_auto] items-end">
            {(["company", "role", "start", "end"] as const).map(k => (
              <div key={k}>
                <label className={label} htmlFor={`x-${k}-${i}`}>{T[k]}</label>
                <input id={`x-${k}-${i}`} className={input} value={x[k]} onChange={e => setAt("experience", i, { [k]: e.target.value })} />
              </div>
            ))}
            <button className={ghostBtn} aria-label={T.remove} onClick={() => dropAt("experience", i)}>
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
        <button
          className={ghostBtn}
          onClick={() => set("experience", [...draft.experience, { company: "", role: "", start: "", end: "", description: "", stack: [] }])}
        >
          <Plus className="w-4 h-4" /> {T.addExperience}
        </button>
        <div>
          <label className={label} htmlFor="d-tools">{T.tools}</label>
          <ListInput id="d-tools" value={draft.tools} onChange={v => set("tools", v)} />
        </div>
      </section>

      <section className={card}>
        <h3 className="text-sm font-semibold text-white">{T.languages}</h3>
        {draft.languages.map((l, i) => (
          <div key={i} className="grid gap-3 grid-cols-[1fr_8rem_auto] items-end">
            <div>
              <label className={label} htmlFor={`l-name-${i}`}>{T.language}</label>
              <input id={`l-name-${i}`} className={input} value={l.language} onChange={e => setAt("languages", i, { language: e.target.value })} />
            </div>
            <div>
              <label className={label} htmlFor={`l-level-${i}`}>{T.level}</label>
              <select id={`l-level-${i}`} className={input} value={l.level} onChange={e => setAt("languages", i, { level: e.target.value as CefrLevel })}>
                {CEFR_LEVELS.map(c => <option key={c} value={c}>{LEVEL_LABEL(c)}</option>)}
              </select>
            </div>
            <button className={ghostBtn} aria-label={T.remove} onClick={() => dropAt("languages", i)}>
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
        <button className={ghostBtn} onClick={() => set("languages", [...draft.languages, { language: "", level: "B2" }])}>
          <Plus className="w-4 h-4" /> {T.addLanguage}
        </button>
      </section>

      <section className={card}>
        <h3 className="text-sm font-semibold text-white">{T.modality}</h3>
        <div className="flex flex-wrap gap-4">
          {MODALITIES.map(m => (
            <label key={m} className="inline-flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={draft.modality.includes(m)}
                onChange={e => set("modality", e.target.checked ? [...draft.modality, m] : draft.modality.filter(x => x !== m))}
              />
              {T.modalities[m]}
            </label>
          ))}
        </div>
        <h3 className="text-sm font-semibold text-white pt-2">{T.eligibility}</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className={label} htmlFor="e-permit">{T.workPermit}</label>
            <ListInput
              id="e-permit"
              value={draft.eligibility.work_permit_countries}
              onChange={v => set("eligibility", { ...draft.eligibility, work_permit_countries: v })}
            />
          </div>
          <div>
            <label className={label} htmlFor="e-visa">{T.sponsorship}</label>
            <TriState id="e-visa" value={draft.eligibility.needs_sponsorship} onChange={v => set("eligibility", { ...draft.eligibility, needs_sponsorship: v })} />
          </div>
          <div>
            <label className={label} htmlFor="e-license">{T.drivingLicense}</label>
            <TriState id="e-license" value={draft.eligibility.driving_license} onChange={v => set("eligibility", { ...draft.eligibility, driving_license: v })} />
          </div>
        </div>
      </section>
    </div>
  );
}


// ── Paso 3: dónde buscar ────────────────────────────────────────────────────────────────────────

type Updater = (fn: (s: WizardState) => WizardState) => void;

export function StepSources({ state, markets, onChange }: {
  state: WizardState;
  markets: Record<string, MarketSource[]>;
  onChange: Updater;
}) {
  const sources = suggestedSources(markets, state.markets, state.sources);
  const toggleMarket = (m: string, on: boolean) =>
    onChange(s => ({ ...s, markets: on ? [...s.markets, m] : s.markets.filter(x => x !== m) }));

  return (
    <div className="space-y-5">
      <section className={card}>
        <h3 className="text-sm font-semibold text-white">{T.markets}</h3>
        <div className="flex flex-wrap gap-4">
          {Object.keys(markets).map(m => (
            <label key={m} className="inline-flex items-center gap-2 text-sm text-gray-300">
              <input type="checkbox" checked={state.markets.includes(m)} onChange={e => toggleMarket(m, e.target.checked)} />
              {T.marketNames[m] ?? m}
            </label>
          ))}
        </div>
      </section>

      <section className={card}>
        <h3 className="text-sm font-semibold text-white">{T.sources}</h3>
        {!sources.length && <p className="text-sm text-gray-500">{T.noSources}</p>}
        <ul className="space-y-3">
          {sources.map(src => {
            const warningId = `warn-${src.id}`;
            return (
              <li key={src.id} className={src.requires_ack ? "rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-2" : ""}>
                <label className="inline-flex items-center gap-2 text-sm text-gray-200">
                  <input
                    type="checkbox"
                    name={`source-${src.id}`}
                    checked={src.checked}
                    aria-describedby={src.requires_ack ? warningId : undefined}
                    onChange={e => { const on = e.target.checked; onChange(s => ({ ...s, sources: { ...s.sources, [src.id]: on } })); }}
                  />
                  {src.label}
                </label>
                {src.requires_ack && (
                  <>
                    <p id={warningId} className="flex items-start gap-2 text-xs text-amber-300">
                      <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden /> {T.ackWarning(src.label)}
                    </p>
                    <label className="inline-flex items-center gap-2 text-xs text-gray-300">
                      <input
                        type="checkbox"
                        name={`ack-${src.id}`}
                        checked={!!state.acknowledged[src.id]}
                        aria-describedby={warningId}
                        onChange={e => { const on = e.target.checked; onChange(s => ({ ...s, acknowledged: { ...s.acknowledged, [src.id]: on } })); }}
                      />
                      {T.ackCheckbox(src.label)}
                    </label>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <section className={card}>
        <label className={label} htmlFor="w-followed">{T.followed}</label>
        <ListInput id="w-followed" value={state.followedCompanies} onChange={v => onChange(s => ({ ...s, followedCompanies: v }))} />
        <p className="text-xs text-gray-500">{T.followedHint}</p>
      </section>
    </div>
  );
}

// ── Contenedor ──────────────────────────────────────────────────────────────────────────────────

/**
 * Asistente a pantalla completa (diálogo modal). Guarda el perfil y el jobhunter.yaml con POST /api/setup/apply
 * y lanza una búsqueda por track nuevo (más Manfred/Indeed si se activaron); `onDone` recibe qué arrancó y qué
 * no. `prefill` (al reabrirlo desde Perfil) precarga la configuración actual. `onCancel` solo existe al
 * reabrirlo: en el primer arranque no se puede saltar.
 */
export function SetupWizard({ initialState, initialStep = 1, initialMarkets, prefill = false, onDone, onCancel }: {
  initialState?: WizardState;
  initialStep?: WizardStep;
  initialMarkets?: Record<string, MarketSource[]>;
  prefill?: boolean;
  onDone: (summary: RunSummary) => void;
  onCancel?: () => void;
}) {
  const [step, setStep] = useState<WizardStep>(initialStep);
  const [state, setState] = useState<WizardState>(initialState ?? emptyWizardState());
  const [markets, setMarkets] = useState<Record<string, MarketSource[]>>(initialMarkets ?? {});
  const [loading, setLoading] = useState(prefill || !initialMarkets);
  const [marketsError, setMarketsError] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [keyBusy, setKeyBusy] = useState(false);
  const [keyStatus, setKeyStatus] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const mounted = useRef(false);

  // Mercados (y, al reabrirlo, la configuración actual). El estado se fija en los callbacks, no en el efecto.
  const load = useCallback(
    () =>
      (async () => {
        const m = initialMarkets ?? (await fetchMarkets());
        return { m, current: prefill ? await fetchSetupCurrent() : null };
      })()
        .then(({ m, current }) => {
          setMarkets(m);
          if (current) setState(answersToState(current, m));
          setMarketsError("");
        })
        .catch((e: Error) => setMarketsError(e.message))
        .finally(() => setLoading(false)),
    [initialMarkets, prefill],
  );

  useEffect(() => {
    if (!prefill && initialMarkets) return;
    load();
  }, [load, prefill, initialMarkets]);

  // Al cambiar de paso, el foco va al título (lectores de pantalla y teclado); no en el primer render.
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return; }
    headingRef.current?.focus();
  }, [step]);

  useEffect(() => {
    if (!onCancel) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const applyProposal = (p: SetupProposal) => {
    setState(s => ({ ...s, draft: p.draft, cvPath: p.cv_path ?? s.cvPath }));
    setNotice(p.source === "ai" ? T.aiProposal : T.emptyProposal);
    setErrors([]);
    setStep(2);
  };

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setErrors([]);
    try {
      await fn();
    } catch (e) {
      setErrors([(e as Error).message]);
    } finally {
      setBusy(false);
    }
  };

  const saveKey = async (key: string) => {
    const provider = state.ai.provider;
    if (provider !== "anthropic" && provider !== "openai") return;
    setKeyBusy(true);
    setErrors([]);
    try {
      const res = await saveAIKey({ provider, api_key: key });
      setKeyStatus(secretStatus(res.has_key, res.key_source));
    } catch (e) {
      setErrors([(e as Error).message]);
    } finally {
      setKeyBusy(false);
    }
  };

  const goNext = () => {
    const errs = validateStep(step, state, markets);
    setErrors(errs);
    if (!errs.length && step < 3) setStep(s => (s + 1) as WizardStep);
  };

  const finish = () => {
    const errs = validateStep(3, state, markets);
    if (errs.length) return setErrors(errs);
    return run(async () => {
      const result = await applySetup(toAnswers(state, markets));
      const runs = searchRuns(result);
      const outcomes = await Promise.allSettled(runs.map(r => startScraperRun(r)));
      onDone(summarizeRuns(runs, outcomes));
    });
  };

  const retryMarkets = () => { setMarketsError(""); setLoading(true); load(); };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="setup-wizard-title"
      className="fixed inset-0 z-50 overflow-y-auto bg-[var(--bg-primary)] text-gray-300"
    >
      <div className="mx-auto max-w-3xl px-6 py-10 space-y-6">
        <header className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-indigo-300/80">{T.stepOf(step)}</p>
            <h2 id="setup-wizard-title" ref={headingRef} tabIndex={-1} className="text-2xl font-bold text-white outline-none">
              {T.stepNames[step]}
            </h2>
            <p className="text-sm text-gray-500">{T.subtitle}</p>
          </div>
          {onCancel && (
            <button className={ghostBtn} aria-label={T.close} onClick={onCancel}>
              <X className="w-4 h-4" />
            </button>
          )}
        </header>

        <ol className="flex gap-2" aria-label={T.progress}>
          {([1, 2, 3] as WizardStep[]).map(n => (
            <li
              key={n}
              aria-current={n === step ? "step" : undefined}
              className={`h-1.5 flex-1 rounded-full ${n <= step ? "bg-indigo-500" : "bg-white/10"}`}
            >
              <span className="sr-only">{T.stepOf(n)}: {T.stepNames[n]}</span>
            </li>
          ))}
        </ol>

        {loading && <p className="text-sm text-gray-400">{T.loadingCurrent}</p>}
        {marketsError && (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {T.marketsError(marketsError)}
            <button className={ghostBtn} onClick={retryMarkets}><RotateCcw className="w-4 h-4" /> {T.retry}</button>
          </div>
        )}
        {step === 2 && notice && <p className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200">{notice}</p>}
        <Errors errors={errors} />

        {step === 1 && (
          <StepCv
            busy={busy || loading}
            onUpload={file => run(async () => applyProposal(await uploadCv(file, file.name, state.ai)))}
            onPaste={text => run(async () => applyProposal(await proposeProfile(text, state.ai)))}
            onManual={() => { setNotice(""); setErrors([]); setStep(2); }}
            aiPicker={
              <AIPicker
                ai={state.ai}
                keyStatus={keyStatus}
                keyBusy={keyBusy}
                onChange={ai => { setKeyStatus(null); setState(s => ({ ...s, ai })); }}
                onSaveKey={saveKey}
              />
            }
          />
        )}
        {step === 2 && <StepReview draft={state.draft} onChange={draft => setState(s => ({ ...s, draft }))} />}
        {step === 3 && <StepSources state={state} markets={markets} onChange={setState} />}

        {step > 1 && (
          <footer className="flex items-center justify-between pt-2">
            <button className={ghostBtn} disabled={busy} onClick={() => { setErrors([]); setStep(s => (s - 1) as WizardStep); }}>
              <ArrowLeft className="w-4 h-4" /> {T.back}
            </button>
            {step < 3 ? (
              <button className={primaryBtn} onClick={goNext}>
                {T.next} <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <button className={primaryBtn} disabled={busy || loading || !!marketsError} onClick={finish}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                {busy ? T.finishing : T.finish}
              </button>
            )}
          </footer>
        )}
      </div>
    </div>
  );
}
