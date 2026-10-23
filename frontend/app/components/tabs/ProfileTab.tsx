"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, KeyRound, Loader2, Plus, RotateCcw, Save, Wand2, X, XCircle } from "lucide-react";
import {
  fetchAISettings,
  fetchEmailSettings,
  fetchProfile,
  fetchSourceSettings,
  saveAISettings,
  saveEmailSettings,
  patchProfile,
  saveSourceSettings,
  fetchFollowedCompaniesSettings,
  saveFollowedCompaniesSettings,
  testAI,
  testEmail,
} from "@/lib/api";
import { ExpandProfilePanel } from "@/app/components/ExpandProfilePanel";
import { TemplatesPanel } from "@/app/components/TemplatesPanel";
import { savedAnswers, withSavedAnswers } from "@/lib/screening";
import type { ScreeningAnswerSaved } from "@/lib/types";
import { formToProfile, profileToForm, secretStatus, type ProfileForm, type StoredProfile } from "@/lib/setup";
import {
  BASE_URL_PROVIDERS,
  CLI_PROVIDERS,
  GMAIL,
  KEY_PROVIDERS,
  aiFormDirty,
  aiFormFromView,
  buildAIUpdate,
  buildEmailUpdate,
  changeAIProvider,
  emailFormDirty,
  emailFormFromView,
  sourcesErrors,
  sourcesUpdate,
  type AIForm,
  type EmailForm,
} from "@/lib/settings";
import { t, useLocale } from "@/lib/i18n";
import { COMPUTRABAJO_COUNTRIES } from "@/lib/setup";
import type { AIProviderId, AISettingsView, CheckResult, EmailSettingsView, FollowedCompanySetting, SourceSetting } from "@/lib/types";

// Textos de la interfaz traducidos vía i18n (con getters para retrocompatibilidad).
export const T = {
  get loading() { return t("profile.loading"); },
  get save() { return t("common.save"); },
  get saved() { return t("common.saved"); },
  get test() { return t("common.test"); },
  get remove() { return t("common.remove"); },
  // Perfil
  get profile() { return t("profile.title"); },
  get fullName() { return t("profile.full_name"); },
  get email() { return t("profile.email"); },
  get phone() { return t("profile.phone"); },
  get city() { return t("profile.city"); },
  get country() { return t("profile.country"); },
  get languages() { return t("profile.languages"); },
  get language() { return t("profile.language"); },
  get level() { return t("profile.level"); },
  get addLanguage() { return t("profile.add_language"); },
  // Respuestas de cribado
  get screening() { return t("profile.screening"); },
  get screeningHint() { return t("profile.screening_hint"); },
  get screeningQuestion() { return t("profile.screening_question"); },
  get screeningAnswer() { return t("profile.screening_answer"); },
  get screeningAdd() { return t("profile.screening_add"); },
  get screeningEmpty() { return t("profile.screening_empty"); },
  // IA
  get ai() { return t("profile.ai"); },
  get aiHint() { return t("profile.ai_hint"); },
  get provider() { return t("profile.provider"); },
  get providers() {
    return {
      none: t("profile.provider_none"),
      ollama: t("profile.provider_ollama"),
      anthropic: t("profile.provider_anthropic"),
      openai: t("profile.provider_openai"),
      claude_cli: t("profile.provider_claude_cli"),
      codex_cli: t("profile.provider_codex_cli"),
    } as Record<AIProviderId, string>;
  },
  get model() { return t("profile.model"); },
  get baseUrl() { return t("profile.base_url"); },
  get baseUrlOpenAI() { return t("profile.base_url_openai"); },
  get apiKey() { return t("profile.api_key"); },
  get apiKeyPlaceholder() { return t("profile.api_key_placeholder"); },
  keyStatus: (status: string) => t("profile.key_status", { status }),
  get envOverrides() { return t("profile.env_overrides"); },
  get cliHint() { return t("profile.cli_hint"); },
  // Email
  get emailSection() { return t("profile.email_section"); },
  get emailHint() { return t("profile.email_hint"); },
  get preset() { return t("profile.preset"); },
  get presets() {
    return { gmail: t("profile.preset_gmail"), custom: t("profile.preset_custom") } as Record<EmailSettingsView["preset"], string>;
  },
  get host() { return t("profile.host"); },
  get port() { return t("profile.port"); },
  get starttls() { return t("profile.starttls"); },
  get username() { return t("profile.username"); },
  get fromName() { return t("profile.from_name"); },
  get password() { return t("profile.password"); },
  get passwordPlaceholder() { return t("profile.password_placeholder"); },
  passwordStatus: (status: string) => t("profile.password_status", { status }),
  get saveFirst() { return t("profile.save_first"); },
  get yamlRewriteNote() { return t("profile.yaml_note"); },
  // Búsqueda
  get search() { return t("profile.search"); },
  get searchHint() { return t("profile.search_hint"); },
  ackWarning: (label: string) => t("profile.ack_warning", { label }),
  ackCheckbox: (label: string) => t("profile.ack_checkbox", { label }),
  get rerunHint() { return t("profile.rerun_hint"); },
  get rerun() { return t("profile.rerun"); },
  loadError: (msg: string) => t("profile.load_error", { message: msg }),
  get retry() { return t("common.retry"); },
};

const LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2", "Nativo"];

/** Las secciones que guardan en jobhunter.yaml lo reescriben entero (sin comentarios): se avisa junto al botón. */
function YamlNote() {
  return <p className="text-xs text-gray-500">{T.yamlRewriteNote}</p>;
}

const input =
  "w-full rounded-lg border border-white/10 bg-[var(--bg-input)] px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-indigo-500/60 focus:outline-none disabled:opacity-50";
const label = "block text-xs font-medium text-gray-400 mb-1";
const card = "glass-card p-5 space-y-4";
const ghostBtn =
  "inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-gray-300 hover:bg-white/5 disabled:opacity-40";
const primaryBtn =
  "inline-flex items-center gap-1.5 rounded-lg bg-indigo-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-50";

type Feedback = CheckResult | null;

function FeedbackLine({ feedback }: { feedback: Feedback }) {
  if (!feedback) return null;
  const Icon = feedback.ok ? CheckCircle2 : XCircle;
  return (
    <p role="status" className={`flex items-start gap-2 text-sm ${feedback.ok ? "text-green-300" : "text-red-300"}`}>
      <Icon className="w-4 h-4 shrink-0 mt-0.5" /> {feedback.message}
    </p>
  );
}

/** Ejecuta una acción con estado «ocupado» y deja el resultado (o el error de la API) en `feedback`. */
function useAction() {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const run = async (fn: () => Promise<CheckResult>) => {
    setBusy(true);
    setFeedback(null);
    try {
      setFeedback(await fn());
    } catch (e) {
      setFeedback({ ok: false, message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  return { busy, feedback, run };
}

// ── Perfil ──────────────────────────────────────────────────────────────────────────────────────

function ProfileSection({ initial }: { initial: StoredProfile }) {
  const [stored, setStored] = useState(initial);
  const [form, setForm] = useState<ProfileForm>(() => profileToForm(initial));
  const { busy, feedback, run } = useAction();
  const set = (patch: Partial<ProfileForm>) => setForm(f => ({ ...f, ...patch }));
  const setLang = (i: number, patch: Partial<ProfileForm["languages"][number]>) =>
    set({ languages: form.languages.map((l, j) => (j === i ? { ...l, ...patch } : l)) });

  const save = () =>
    run(async () => {
      // PATCH: solo las claves que edita esta sección; lo demás del perfil (p. ej. las respuestas de cribado) no se toca.
      const { personal, languages } = formToProfile(stored, form);
      const saved = await patchProfile({ personal, languages });
      setStored(saved);
      setForm(profileToForm(saved));
      return { ok: true, message: T.saved };
    });

  return (
    <section className={card}>
      <h3 className="text-base font-semibold text-white">{T.profile}</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {(["full_name", "email", "phone", "city", "country"] as const).map(k => (
          <div key={k}>
            <label className={label} htmlFor={`p-${k}`}>{T[k === "full_name" ? "fullName" : k]}</label>
            <input id={`p-${k}`} className={input} value={form[k]} onChange={e => set({ [k]: e.target.value })} />
          </div>
        ))}
      </div>
      <h4 className="text-sm font-semibold text-white">{T.languages}</h4>
      {form.languages.map((l, i) => (
        <div key={i} className="grid gap-3 grid-cols-[1fr_8rem_auto] items-end">
          <div>
            <label className={label} htmlFor={`pl-name-${i}`}>{T.language}</label>
            <input id={`pl-name-${i}`} className={input} value={l.language} onChange={e => setLang(i, { language: e.target.value })} />
          </div>
          <div>
            <label className={label} htmlFor={`pl-level-${i}`}>{T.level}</label>
            <select id={`pl-level-${i}`} className={input} value={l.level} onChange={e => setLang(i, { level: e.target.value })}>
              {/* Un nivel guardado fuera de la lista (p. ej. a mano en profile.json) se conserva. */}
              {[...new Set([...LEVELS, l.level].filter(Boolean))].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <button className={ghostBtn} aria-label={T.remove} onClick={() => set({ languages: form.languages.filter((_, j) => j !== i) })}>
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <button className={ghostBtn} onClick={() => set({ languages: [...form.languages, { language: "", level: "B2" }] })}>
          <Plus className="w-4 h-4" /> {T.addLanguage}
        </button>
        <button className={primaryBtn} disabled={busy} onClick={save}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {T.save}
        </button>
      </div>
      <FeedbackLine feedback={feedback} />
    </section>
  );
}

// ── Respuestas de cribado ───────────────────────────────────────────────────────────────────────

/** Lista editable de `profile.screening_answers`. Guarda con PATCH /api/profile: solo cambia esa clave. */
function ScreeningSection({ initial }: { initial: StoredProfile }) {
  const [items, setItems] = useState<ScreeningAnswerSaved[]>(() => savedAnswers(initial));
  const { busy, feedback, run } = useAction();
  const edit = (i: number, patch: Partial<ScreeningAnswerSaved>) =>
    setItems(list => list.map((it, j) => (j === i ? { ...it, ...patch } : it)));

  const save = () =>
    run(async () => {
      const saved = await patchProfile({ screening_answers: withSavedAnswers({}, items).screening_answers });
      setItems(savedAnswers(saved));
      return { ok: true, message: T.saved };
    });

  return (
    <section className={`${card} lg:col-span-2`}>
      <h3 className="text-base font-semibold text-white">{T.screening}</h3>
      <p className="text-xs text-gray-500">{T.screeningHint}</p>
      {items.length === 0 && <p className="text-sm text-gray-400">{T.screeningEmpty}</p>}
      {items.map((it, i) => (
        <div key={i} className="grid gap-3 grid-cols-[1fr_auto] items-start">
          <div className="space-y-2">
            <div>
              <label className={label} htmlFor={`sa-q-${i}`}>{T.screeningQuestion}</label>
              <input id={`sa-q-${i}`} className={input} value={it.question} onChange={e => edit(i, { question: e.target.value })} />
            </div>
            <div>
              <label className={label} htmlFor={`sa-a-${i}`}>{T.screeningAnswer}</label>
              <textarea id={`sa-a-${i}`} rows={3} className={input} value={it.answer} onChange={e => edit(i, { answer: e.target.value })} />
            </div>
          </div>
          <button className={`${ghostBtn} mt-5`} aria-label={T.remove} onClick={() => setItems(list => list.filter((_, j) => j !== i))}>
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <button className={ghostBtn} onClick={() => setItems(list => [...list, { question: "", answer: "" }])}>
          <Plus className="w-4 h-4" /> {T.screeningAdd}
        </button>
        <button className={primaryBtn} disabled={busy} onClick={save}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {T.save}
        </button>
      </div>
      <FeedbackLine feedback={feedback} />
    </section>
  );
}

// ── IA ──────────────────────────────────────────────────────────────────────────────────────────

function TestButton({ dirty, busy, onClick }: { dirty: boolean; busy: boolean; onClick: () => void }) {
  return (
    <button className={ghostBtn} disabled={busy || dirty} title={dirty ? T.saveFirst : undefined} onClick={onClick}>
      {T.test}
    </button>
  );
}

function AISection({ initial }: { initial: AISettingsView }) {
  const [view, setView] = useState(initial);
  const [form, setForm] = useState<AIForm>(() => aiFormFromView(initial));
  const { busy, feedback, run } = useAction();
  const { provider } = form;
  const usesKey = KEY_PROVIDERS.includes(provider);
  const keyProvider = provider as "anthropic" | "openai";
  const dirty = aiFormDirty(view, form);

  const save = () =>
    run(async () => {
      const saved = await saveAISettings(buildAIUpdate(form));
      setView(saved);
      setForm(aiFormFromView(saved)); // la clave escrita se vacía: nunca vuelve de la API
      return { ok: true, message: T.saved };
    });

  return (
    <section className={card}>
      <h3 className="text-base font-semibold text-white">{T.ai}</h3>
      <p className="text-xs text-gray-500">{T.aiHint}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label} htmlFor="ai-provider">{T.provider}</label>
          <select
            id="ai-provider"
            className={input}
            value={provider}
            onChange={e => { const p = e.target.value as AIProviderId; setForm(f => changeAIProvider(view, f, p)); }}
          >
            {(Object.keys(T.providers) as AIProviderId[]).map(p => <option key={p} value={p}>{T.providers[p]}</option>)}
          </select>
        </div>
        {provider !== "none" && (
          <div>
            <label className={label} htmlFor="ai-model">{T.model}</label>
            <input id="ai-model" className={input} value={form.model} onChange={e => { const v = e.target.value; setForm(f => ({ ...f, model: v })); }} />
          </div>
        )}
        {BASE_URL_PROVIDERS.includes(provider) && (
          <div className="sm:col-span-2">
            <label className={label} htmlFor="ai-base-url">{T.baseUrl}</label>
            <input id="ai-base-url" className={input} value={form.baseUrl} onChange={e => { const v = e.target.value; setForm(f => ({ ...f, baseUrl: v })); }} />
            {provider === "openai" && <p className="mt-1 text-xs text-amber-300">{T.baseUrlOpenAI}</p>}
          </div>
        )}
        {usesKey && (
          <div className="sm:col-span-2">
            <label className={label} htmlFor="ai-key">{T.apiKey}</label>
            <input
              id="ai-key"
              type="password"
              autoComplete="new-password"
              className={input}
              placeholder={T.apiKeyPlaceholder}
              value={form.apiKey}
              onChange={e => { const v = e.target.value; setForm(f => ({ ...f, apiKey: v })); }}
            />
            <p className="mt-1 flex items-center gap-1.5 text-xs text-gray-400">
              <KeyRound className="w-3.5 h-3.5" />
              {T.keyStatus(secretStatus(view.has_key[keyProvider], view.key_source[keyProvider]))}
              {view.key_source[keyProvider] === "env" && <span className="text-gray-500"> · {T.envOverrides}</span>}
            </p>
          </div>
        )}
        {CLI_PROVIDERS.includes(provider) && <p className="sm:col-span-2 text-xs text-gray-500">{T.cliHint}</p>}
      </div>
      <div className="flex gap-3">
        <button className={primaryBtn} disabled={busy} onClick={save}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {T.save}
        </button>
        <TestButton dirty={dirty} busy={busy} onClick={() => run(testAI)} />
      </div>
      <YamlNote />
      <FeedbackLine feedback={feedback} />
    </section>
  );
}

// ── Email ───────────────────────────────────────────────────────────────────────────────────────

function EmailSection({ initial }: { initial: EmailSettingsView }) {
  const [view, setView] = useState(initial);
  const [form, setForm] = useState<EmailForm>(() => emailFormFromView(initial));
  const { busy, feedback, run } = useAction();
  const gmail = form.preset === "gmail";
  const set = (patch: Partial<EmailForm>) => setForm(f => ({ ...f, ...patch }));
  const dirty = emailFormDirty(view, form);

  const save = () =>
    run(async () => {
      const saved = await saveEmailSettings(buildEmailUpdate(form));
      setView(saved);
      setForm(emailFormFromView(saved)); // la contraseña escrita se vacía: nunca vuelve de la API
      return { ok: true, message: T.saved };
    });

  return (
    <section className={card}>
      <h3 className="text-base font-semibold text-white">{T.emailSection}</h3>
      <p className="text-xs text-gray-500">{T.emailHint}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label} htmlFor="em-preset">{T.preset}</label>
          <select
            id="em-preset"
            className={input}
            value={form.preset}
            onChange={e => {
              const preset = e.target.value as EmailSettingsView["preset"];
              set(preset === "gmail" ? { preset, ...GMAIL } : { preset });
            }}
          >
            {(Object.keys(T.presets) as EmailSettingsView["preset"][]).map(p => <option key={p} value={p}>{T.presets[p]}</option>)}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="em-host">{T.host}</label>
          <input id="em-host" className={input} disabled={gmail} value={form.smtp_host} onChange={e => set({ smtp_host: e.target.value })} />
        </div>
        <div>
          <label className={label} htmlFor="em-port">{T.port}</label>
          <input
            id="em-port"
            type="number"
            min={1}
            max={65535}
            className={input}
            disabled={gmail}
            value={form.smtp_port}
            onChange={e => set({ smtp_port: Number(e.target.value) })}
          />
        </div>
        <label className="inline-flex items-center gap-2 self-end pb-2 text-sm text-gray-300">
          <input type="checkbox" disabled={gmail} checked={form.use_starttls} onChange={e => set({ use_starttls: e.target.checked })} />
          {T.starttls}
        </label>
        <div>
          <label className={label} htmlFor="em-user">{T.username}</label>
          <input id="em-user" className={input} autoComplete="off" value={form.username} onChange={e => set({ username: e.target.value })} />
        </div>
        <div>
          <label className={label} htmlFor="em-from">{T.fromName}</label>
          <input id="em-from" className={input} value={form.from_name} onChange={e => set({ from_name: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className={label} htmlFor="em-password">{T.password}</label>
          <input
            id="em-password"
            type="password"
            autoComplete="new-password"
            className={input}
            placeholder={T.passwordPlaceholder}
            value={form.password}
            onChange={e => set({ password: e.target.value })}
          />
          <p className="mt-1 flex items-center gap-1.5 text-xs text-gray-400">
            <KeyRound className="w-3.5 h-3.5" />
            {T.passwordStatus(secretStatus(view.has_password, view.password_source))}
            {view.password_source === "env" && <span className="text-gray-500"> · {T.envOverrides}</span>}
          </p>
        </div>
      </div>
      <div className="flex gap-3">
        <button className={primaryBtn} disabled={busy} onClick={save}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {T.save}
        </button>
        <TestButton dirty={dirty} busy={busy} onClick={() => run(testEmail)} />
      </div>
      <YamlNote />
      <FeedbackLine feedback={feedback} />
    </section>
  );
}

// ── Búsqueda ────────────────────────────────────────────────────────────────────────────────────

function SourcesSection({ initial, onRerunWizard }: { initial: SourceSetting[]; onRerunWizard: () => void }) {
  const [list, setList] = useState(initial);
  const { busy, feedback, run } = useAction();
  const patch = (id: string, p: Partial<SourceSetting>) => setList(l => l.map(s => (s.id === id ? { ...s, ...p } : s)));

  const save = () =>
    run(async () => {
      const errs = sourcesErrors(list);
      if (errs.length) return { ok: false, message: errs.join(" ") };
      setList(await saveSourceSettings(sourcesUpdate(list)));
      return { ok: true, message: T.saved };
    });

  return (
    <section className={card}>
      <h3 className="text-base font-semibold text-white">{T.search}</h3>
      <p className="text-xs text-gray-500">{T.searchHint}</p>
      <ul className="space-y-3">
        {list.map(src => {
          const warningId = `p-warn-${src.id}`;
          return (
            <li key={src.id} className={src.requires_ack ? "rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-2" : "space-y-2"}>
              <label className="inline-flex items-center gap-2 text-sm text-gray-200">
                <input
                  type="checkbox"
                  name={`p-source-${src.id}`}
                  checked={src.enabled}
                  aria-describedby={src.requires_ack ? warningId : undefined}
                  onChange={e => patch(src.id, { enabled: e.target.checked })}
                />
                {src.label}
              </label>
              {src.id === "computrabajo" && src.enabled && (
                <div className="ml-6 flex items-center gap-2 text-xs text-gray-300">
                  <span>{t("profile.source_country")}:</span>
                  <select
                    id={`p-country-${src.id}`}
                    name={`p-country-${src.id}`}
                    value={src.country || "es"}
                    onChange={e => patch(src.id, { country: e.target.value })}
                    className="bg-[#16161f] border border-white/10 text-gray-300 rounded px-2 py-1 text-xs outline-none"
                  >
                    {COMPUTRABAJO_COUNTRIES.map(c => (
                      <option key={c} value={c}>
                        {t(`country.${c}`)} ({c})
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {(src.id === "tecnoempleo" || src.id === "indeed" || src.id === "computrabajo") && src.enabled && (
                <div className="ml-6 flex items-center gap-2 text-xs text-gray-300">
                  <span>{t("profile.source_locations")}:</span>
                  <input
                    id={`p-locations-${src.id}`}
                    name={`p-locations-${src.id}`}
                    type="text"
                    placeholder={t("profile.source_locations_placeholder")}
                    value={(src.locations || []).join(", ")}
                    onChange={e => patch(src.id, { locations: e.target.value.split(",").map(x => x.trim()).filter(Boolean) })}
                    className="bg-[#16161f] border border-white/10 text-gray-300 rounded px-2 py-1 text-xs outline-none flex-1 max-w-xs"
                  />
                </div>
              )}
              {src.requires_ack && (
                <>
                  <p id={warningId} className="flex items-start gap-2 text-xs text-amber-300">
                    <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden /> {T.ackWarning(src.label)}
                  </p>
                  <label className="inline-flex items-center gap-2 text-xs text-gray-300">
                    <input
                      type="checkbox"
                      name={`p-ack-${src.id}`}
                      checked={src.acknowledged}
                      aria-describedby={warningId}
                      onChange={e => patch(src.id, { acknowledged: e.target.checked })}
                    />
                    {T.ackCheckbox(src.label)}
                  </label>
                </>
              )}
            </li>
          );
        })}
      </ul>
      <FollowedCompaniesBlock />
      <button className={primaryBtn} disabled={busy} onClick={save}>
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {T.save}
      </button>
      <YamlNote />
      <FeedbackLine feedback={feedback} />
      <p className="text-sm text-gray-400 pt-2">{T.rerunHint}</p>
      <button className={ghostBtn} onClick={onRerunWizard}>
        <Wand2 className="w-4 h-4" /> {T.rerun}
      </button>
    </section>
  );
}

function FollowedCompaniesBlock() {
  const [companies, setCompanies] = useState<FollowedCompanySetting[]>([]);
  const [loading, setLoading] = useState(true);
  const { busy, feedback, run } = useAction();

  useEffect(() => {
    fetchFollowedCompaniesSettings()
      .then(setCompanies)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const addCompany = () => {
    setCompanies(prev => [...prev, { name: "", tier: 1, aliases: [] }]);
  };

  const removeCompany = (idx: number) => {
    setCompanies(prev => prev.filter((_, i) => i !== idx));
  };

  const updateCompany = (idx: number, patch: Partial<FollowedCompanySetting>) => {
    setCompanies(prev => prev.map((c, i) => (i === idx ? { ...c, ...patch } : c)));
  };

  const save = () =>
    run(async () => {
      const valid = companies.filter(c => c.name.trim());
      const saved = await saveFollowedCompaniesSettings(valid);
      setCompanies(saved);
      return { ok: true, message: "Empresas seguidas guardadas" };
    });

  if (loading) return null;

  return (
    <div className="pt-4 border-t border-white/5 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold text-white">{t("profile.followed_companies_title")}</h4>
          <p className="text-xs text-gray-500">{t("profile.followed_companies_hint")}</p>
        </div>
        <button
          type="button"
          onClick={addCompany}
          className="text-xs text-indigo-400 hover:text-indigo-300 font-medium px-2 py-1 rounded bg-indigo-500/10 border border-indigo-500/20"
        >
          {t("profile.add_followed_company")}
        </button>
      </div>

      {companies.length > 0 && (
        <div className="space-y-2">
          {companies.map((c, idx) => (
            <div key={idx} className="flex flex-wrap items-center gap-2 p-2 rounded-lg bg-black/20 border border-white/5">
              <input
                type="text"
                placeholder="Nombre de la empresa"
                value={c.name}
                onChange={e => updateCompany(idx, { name: e.target.value })}
                className="bg-[#16161f] border border-white/10 text-gray-300 text-xs rounded px-2.5 py-1.5 focus:ring-1 focus:ring-indigo-500 outline-none flex-1 min-w-[140px]"
              />
              <select
                value={c.tier}
                onChange={e => updateCompany(idx, { tier: Number(e.target.value) })}
                className="bg-[#16161f] border border-white/10 text-gray-300 text-xs rounded px-2 py-1.5 focus:ring-1 focus:ring-indigo-500 outline-none"
              >
                <option value={1}>{t("track.tier_label", { tier: 1 })}</option>
                <option value={2}>{t("track.tier_label", { tier: 2 })}</option>
                <option value={3}>{t("track.tier_label", { tier: 3 })}</option>
              </select>
              <input
                type="text"
                placeholder="Alias (separados por coma)"
                value={c.aliases?.join(", ") || ""}
                onChange={e => updateCompany(idx, { aliases: e.target.value.split(",").map(a => a.trim()).filter(Boolean) })}
                className="bg-[#16161f] border border-white/10 text-gray-300 text-xs rounded px-2.5 py-1.5 focus:ring-1 focus:ring-indigo-500 outline-none flex-1 min-w-[140px]"
              />
              <button
                type="button"
                onClick={() => removeCompany(idx)}
                className="text-xs text-red-400 hover:text-red-300 px-2 py-1"
              >
                ✕
              </button>
            </div>
          ))}
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="text-xs text-white bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 rounded-lg flex items-center gap-1.5 disabled:opacity-50"
              disabled={busy}
              onClick={save}
            >
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} {t("profile.save_followed_companies")}
            </button>
            <FeedbackLine feedback={feedback} />
          </div>
        </div>
      )}
    </div>
  );
}

// ── Pestaña ─────────────────────────────────────────────────────────────────────────────────────

export interface ProfileData {
  profile: StoredProfile;
  ai: AISettingsView;
  email: EmailSettingsView;
  sources: SourceSetting[];
}

type Slot<T> = { data: T } | { error: string } | null;
type Slots = { [K in keyof ProfileData]: Slot<ProfileData[K]> };

const LOADERS: { [K in keyof ProfileData]: () => Promise<ProfileData[K]> } = {
  profile: fetchProfile,
  ai: fetchAISettings,
  email: fetchEmailSettings,
  sources: fetchSourceSettings,
};

const fromInitial = (initial?: Partial<ProfileData>): Slots => ({
  profile: initial?.profile ? { data: initial.profile } : null,
  ai: initial?.ai ? { data: initial.ai } : null,
  email: initial?.email ? { data: initial.email } : null,
  sources: initial?.sources ? { data: initial.sources } : null,
});

function SlotView<T>({ slot, onRetry, children }: { slot: Slot<T>; onRetry: () => void; children: (data: T) => React.ReactNode }) {
  if (slot === null) return <p className="glass-card p-5 text-sm text-gray-400">{T.loading}</p>;
  if ("error" in slot) {
    return (
      <div role="alert" className="glass-card p-5 space-y-3 text-sm text-red-300">
        <p>{T.loadError(slot.error)}</p>
        <button className={ghostBtn} onClick={onRetry}><RotateCcw className="w-4 h-4" /> {T.retry}</button>
      </div>
    );
  }
  return <>{children(slot.data)}</>;
}

/** Pestaña «Perfil»: datos básicos e idiomas, IA, email y fuentes de búsqueda. Cada sección carga por su cuenta
 *  (si una falla, las demás siguen y se puede reintentar). Los secretos nunca se muestran: solo si existen y de
 *  dónde salen. `initial` (tests) evita las peticiones de las secciones que trae. */
export function ProfileTab({ initial, onRerunWizard }: { initial?: Partial<ProfileData>; onRerunWizard: () => void }) {
  useLocale();
  const [slots, setSlots] = useState<Slots>(() => fromInitial(initial));

  const loadSlot = useCallback(<K extends keyof ProfileData>(key: K) => {
    LOADERS[key]()
      .then(data => setSlots(s => ({ ...s, [key]: { data } })))
      .catch((e: Error) => setSlots(s => ({ ...s, [key]: { error: e.message } })));
  }, []);

  useEffect(() => {
    if (initial) return;
    (Object.keys(LOADERS) as (keyof ProfileData)[]).forEach(loadSlot);
  }, [initial, loadSlot]);

  const retry = (key: keyof ProfileData) => { setSlots(s => ({ ...s, [key]: null })); loadSlot(key); };

  return (
    <div className="grid gap-6 lg:grid-cols-2 animate-fade-in">
      <SlotView slot={slots.profile} onRetry={() => retry("profile")}>{d => <ProfileSection initial={d} />}</SlotView>
      <SlotView slot={slots.profile} onRetry={() => retry("profile")}>{d => <ScreeningSection initial={d} />}</SlotView>
      <SlotView slot={slots.profile} onRetry={() => retry("profile")}>{d => <ExpandProfilePanel initialProfile={d} />}</SlotView>
      <section className={`${card} lg:col-span-2`}><TemplatesPanel autoLoad={!initial} /></section>
      <SlotView slot={slots.ai} onRetry={() => retry("ai")}>{d => <AISection initial={d} />}</SlotView>
      <SlotView slot={slots.email} onRetry={() => retry("email")}>{d => <EmailSection initial={d} />}</SlotView>
      <SlotView slot={slots.sources} onRetry={() => retry("sources")}>
        {d => <SourcesSection initial={d} onRerunWizard={onRerunWizard} />}
      </SlotView>
    </div>
  );
}
