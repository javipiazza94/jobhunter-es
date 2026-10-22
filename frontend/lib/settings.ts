// Formularios de ajustes de la pestaña Perfil (IA, email y fuentes): lógica pura, se prueba con bun test.
import type {
  AIProviderId,
  AISettingsUpdate,
  AISettingsView,
  EmailSettingsUpdate,
  EmailSettingsView,
  SourceSetting,
  SourcesUpdate,
} from "@/lib/types";

export const KEY_PROVIDERS: AIProviderId[] = ["anthropic", "openai"];
export const BASE_URL_PROVIDERS: AIProviderId[] = ["ollama", "openai"];
export const CLI_PROVIDERS: AIProviderId[] = ["claude_cli", "codex_cli"];
export const GMAIL = { smtp_host: "smtp.gmail.com", smtp_port: 587, use_starttls: true };

export interface AIForm {
  provider: AIProviderId;
  model: string;
  baseUrl: string;
  /** Nunca se rellena desde la API: solo lo que escribe el usuario. */
  apiKey: string;
}

export function aiFormFromView(view: AISettingsView): AIForm {
  return { provider: view.provider, model: view.model ?? "", baseUrl: view.base_url ?? "", apiKey: "" };
}

/** Al cambiar de proveedor, modelo y URL dejan de valer: se vacían, salvo al volver al proveedor guardado. */
export function changeAIProvider(view: AISettingsView, form: AIForm, provider: AIProviderId): AIForm {
  if (provider === view.provider) return { ...aiFormFromView(view), apiKey: form.apiKey };
  return { provider, model: "", baseUrl: "", apiKey: form.apiKey };
}

export function buildAIUpdate(form: AIForm): AISettingsUpdate {
  const update: AISettingsUpdate = {
    provider: form.provider,
    model: form.model.trim() || null,
    base_url: BASE_URL_PROVIDERS.includes(form.provider) ? form.baseUrl.trim() || null : null,
  };
  const key = form.apiKey.trim();
  if (key && KEY_PROVIDERS.includes(form.provider)) update.api_key = key;
  return update;
}

export function aiFormDirty(view: AISettingsView, form: AIForm): boolean {
  const saved = aiFormFromView(view);
  return form.provider !== saved.provider || form.model.trim() !== saved.model || form.baseUrl.trim() !== saved.baseUrl || !!form.apiKey.trim();
}

export interface EmailForm {
  preset: EmailSettingsView["preset"];
  smtp_host: string;
  smtp_port: number;
  use_starttls: boolean;
  username: string;
  from_name: string;
  /** Nunca se rellena desde la API. */
  password: string;
}

export function emailFormFromView(view: EmailSettingsView): EmailForm {
  return {
    preset: view.preset,
    smtp_host: view.smtp_host,
    smtp_port: view.smtp_port,
    use_starttls: view.use_starttls,
    username: view.username ?? "",
    from_name: view.from_name ?? "",
    password: "",
  };
}

export function buildEmailUpdate(form: EmailForm): EmailSettingsUpdate {
  const update: EmailSettingsUpdate = {
    preset: form.preset,
    smtp_host: form.smtp_host.trim(),
    smtp_port: form.smtp_port,
    use_starttls: form.use_starttls,
    ...(form.preset === "gmail" ? GMAIL : {}),
    username: form.username.trim() || null,
    from_name: form.from_name.trim() || null,
  };
  if (form.password) update.password = form.password;
  return update;
}

export function emailFormDirty(view: EmailSettingsView, form: EmailForm): boolean {
  const a = buildEmailUpdate({ ...form, password: "" });
  const b = buildEmailUpdate(emailFormFromView(view));
  return JSON.stringify(a) !== JSON.stringify(b) || !!form.password;
}

/** Cuerpo de PUT /api/settings/sources: solo cuentan como aceptadas las `requires_ack` activadas y aceptadas. */
export function sourcesUpdate(list: SourceSetting[]): SourcesUpdate {
  const on = list.filter(s => s.enabled);
  return { enabled: on.map(s => s.id), acknowledged: on.filter(s => s.requires_ack && s.acknowledged).map(s => s.id) };
}

export function sourcesErrors(list: SourceSetting[]): string[] {
  const on = list.filter(s => s.enabled);
  if (!on.length) return ["Activa al menos una fuente de ofertas."];
  return on.filter(s => s.requires_ack && !s.acknowledged).map(s => `Acepta el aviso de ${s.label} o desactívala.`);
}
