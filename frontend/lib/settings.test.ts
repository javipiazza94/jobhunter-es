// Formularios de ajustes de la pestaña Perfil (IA, email, fuentes). Se ejecuta con `bun test`.
import { describe, expect, test } from "bun:test";
import type { AISettingsView, EmailSettingsView, SourceSetting } from "@/lib/types";
import {
  aiFormFromView,
  aiFormDirty,
  buildAIUpdate,
  buildEmailUpdate,
  changeAIProvider,
  emailFormDirty,
  emailFormFromView,
  sourcesErrors,
  sourcesUpdate,
} from "./settings";

const aiView = (extra: Partial<AISettingsView> = {}): AISettingsView => ({
  provider: "ollama", model: "llama3.1", base_url: "http://localhost:11434", timeout_seconds: 120,
  has_key: { anthropic: false, openai: false }, key_source: { anthropic: null, openai: null }, ...extra,
});
const emailView = (extra: Partial<EmailSettingsView> = {}): EmailSettingsView => ({
  preset: "gmail", smtp_host: "smtp.gmail.com", smtp_port: 587, use_starttls: true, username: "ana@example.com",
  from_name: null, has_password: false, password_source: null, ...extra,
});

describe("IA", () => {
  test("el formulario parte de lo guardado y sin clave", () => {
    expect(aiFormFromView(aiView())).toEqual({ provider: "ollama", model: "llama3.1", baseUrl: "http://localhost:11434", apiKey: "" });
  });

  test("cambiar de proveedor vacía modelo y URL; volver al guardado los recupera", () => {
    const view = aiView();
    const other = changeAIProvider(view, aiFormFromView(view), "anthropic");
    expect(other).toEqual({ provider: "anthropic", model: "", baseUrl: "", apiKey: "" });
    expect(changeAIProvider(view, { ...other, apiKey: "k" }, "ollama")).toEqual({ ...aiFormFromView(view), apiKey: "k" });
  });

  test("buildAIUpdate: sin base_url para anthropic, clave solo si se escribió y el proveedor la usa", () => {
    const view = aiView();
    expect(buildAIUpdate({ provider: "anthropic", model: " ", baseUrl: "http://x", apiKey: " sk-1 " })).toEqual({
      provider: "anthropic", model: null, base_url: null, api_key: "sk-1",
    });
    expect(buildAIUpdate({ ...aiFormFromView(view), apiKey: "ignorada" })).toEqual({
      provider: "ollama", model: "llama3.1", base_url: "http://localhost:11434",
    });
    expect(buildAIUpdate({ provider: "openai", model: "", baseUrl: "", apiKey: "" })).toEqual({ provider: "openai", model: null, base_url: null });
  });

  test("tras guardar, el formulario sale de la respuesta: la clave se vacía y deja de haber cambios", () => {
    const saved = aiView({ provider: "anthropic", model: null, base_url: null, has_key: { anthropic: true, openai: false } });
    const form = aiFormFromView(saved);
    expect(form.apiKey).toBe("");
    expect(aiFormDirty(saved, form)).toBe(false);
    expect(aiFormDirty(saved, { ...form, apiKey: "x" })).toBe(true);
    expect(aiFormDirty(saved, { ...form, provider: "ollama" })).toBe(true);
  });
});

describe("email", () => {
  test("Gmail fuerza servidor, puerto y STARTTLS; la contraseña solo si se escribió", () => {
    const form = { ...emailFormFromView(emailView()), smtp_host: "otro", smtp_port: 25, use_starttls: false, from_name: " Ana ", password: "" };
    expect(buildEmailUpdate(form)).toEqual({
      preset: "gmail", smtp_host: "smtp.gmail.com", smtp_port: 587, use_starttls: true, username: "ana@example.com", from_name: "Ana",
    });
    expect(buildEmailUpdate({ ...form, preset: "custom", password: "pw" })).toMatchObject({ smtp_host: "otro", smtp_port: 25, password: "pw" });
  });

  test("hay cambios si difiere de lo guardado o hay contraseña escrita", () => {
    const view = emailView();
    expect(emailFormDirty(view, emailFormFromView(view))).toBe(false);
    expect(emailFormDirty(view, { ...emailFormFromView(view), username: "otra@example.com" })).toBe(true);
    expect(emailFormDirty(view, { ...emailFormFromView(view), password: "x" })).toBe(true);
  });
});

describe("fuentes", () => {
  const list: SourceSetting[] = [
    { id: "tecnoempleo", label: "Tecnoempleo", markets: ["spain"], requires_ack: false, enabled: true, acknowledged: false },
    { id: "infojobs", label: "InfoJobs", markets: ["spain"], requires_ack: true, enabled: true, acknowledged: true },
    { id: "linkedin", label: "LinkedIn", markets: ["global"], requires_ack: true, enabled: false, acknowledged: true },
  ];

  test("solo van como aceptadas las requires_ack activadas y aceptadas", () => {
    expect(sourcesUpdate(list)).toEqual({ enabled: ["tecnoempleo", "infojobs"], acknowledged: ["infojobs"] });
  });

  test("una requires_ack activada sin aceptar es un error; ninguna activada también", () => {
    expect(sourcesErrors(list)).toEqual([]);
    expect(sourcesErrors(list.map(s => (s.id === "infojobs" ? { ...s, acknowledged: false } : s)))).toEqual([
      "Acepta el aviso de InfoJobs o desactívala.",
    ]);
    expect(sourcesErrors(list.map(s => ({ ...s, enabled: false })))).toEqual(["Activa al menos una fuente de ofertas."]);
  });
});
