// Marcado estático de la pestaña Perfil. Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { AISettingsView, EmailSettingsView, SourceSetting } from "@/lib/types";
import { ProfileTab, T, type ProfileData } from "./ProfileTab";

const ai = (extra: Partial<AISettingsView> = {}): AISettingsView => ({
  provider: "anthropic", model: null, base_url: null, timeout_seconds: 120,
  has_key: { anthropic: true, openai: false }, key_source: { anthropic: "keychain", openai: null }, ...extra,
});
const email = (extra: Partial<EmailSettingsView> = {}): EmailSettingsView => ({
  preset: "gmail", smtp_host: "smtp.gmail.com", smtp_port: 587, use_starttls: true,
  username: "ana@example.com", from_name: "Ana Villa", has_password: true, password_source: "env", ...extra,
});
const SOURCES: SourceSetting[] = [
  { id: "tecnoempleo", label: "Tecnoempleo", markets: ["spain"], requires_ack: false, enabled: true, acknowledged: false },
  { id: "infojobs", label: "InfoJobs", markets: ["spain"], requires_ack: true, enabled: false, acknowledged: false },
  { id: "linkedin", label: "LinkedIn", markets: ["global"], requires_ack: true, enabled: true, acknowledged: true },
];
const data = (extra: Partial<ProfileData> = {}): ProfileData => ({
  profile: { personal: { name: "Ana Villa", city: "Villanova" }, languages: [{ language: "Inglés", level: "C1" }] },
  ai: ai(), email: email(), sources: SOURCES, ...extra,
});
const inputTag = (h: string, name: string) => h.match(new RegExp(`<input[^>]*name="${name}"[^>]*>`))?.[0] ?? "";
const html = (d: ProfileData) => renderToStaticMarkup(<ProfileTab initial={d} onRerunWizard={() => {}} />);
const passwordInputs = (h: string) => h.match(/<input[^>]*type="password"[^>]*>/g) ?? [];

test("muestra las cuatro secciones y el acceso al asistente", () => {
  const h = html(data());
  for (const title of [T.profile, T.ai, T.emailSection, T.search, T.rerun]) expect(h).toContain(title);
  expect(h).toContain('value="Ana Villa"');
  expect(h).toContain('value="Villanova"');
  expect(h).toContain('<option value="C1" selected="">C1</option>');
});

test("dice de dónde sale cada secreto: llavero, variable de entorno o nada", () => {
  expect(html(data())).toContain(T.keyStatus("guardada en el llavero"));
  expect(html(data())).toContain(T.passwordStatus("configurada (variable de entorno)"));
  const none = html(data({
    ai: ai({ provider: "openai" }),
    email: email({ has_password: false, password_source: null }),
  }));
  expect(none).toContain(T.keyStatus("no configurada"));
  expect(none).toContain(T.passwordStatus("no configurada"));
});

test("nunca rellena un campo de secreto, ni con datos que sí viajan en la respuesta", () => {
  // Aunque una API defectuosa colara un secreto en la respuesta, la pestaña no lo pinta.
  const leaky = data({
    ai: { ...ai(), api_key: "sk-SECRETO" } as AISettingsView,
    email: { ...email(), password: "pw-SECRETO" } as EmailSettingsView,
  });
  const h = html(leaky);
  expect(h).not.toContain("SECRETO");
  const pw = passwordInputs(h);
  expect(pw.length).toBe(2);
  for (const tag of pw) expect(tag).toContain('value=""');
});

test("con un proveedor sin clave no hay campo de clave; con una CLI se explica que usa la sesión", () => {
  const h = html(data({ ai: ai({ provider: "claude_cli" }) }));
  expect(passwordInputs(h).length).toBe(1);
  expect(h).toContain(T.cliHint);
});

test("Gmail fija servidor y puerto; otro servidor deja editarlos", () => {
  expect(html(data())).toMatch(/<input id="em-host"[^>]*disabled=""/);
  expect(html(data({ email: email({ preset: "custom", smtp_host: "mail.villanova.test" }) }))).not.toMatch(/<input id="em-host"[^>]*disabled=""/);
});

test("Búsqueda: fuentes con su estado; las requires_ack con aviso y casilla propia enlazada al aviso", () => {
  const h = html(data());
  expect(h).toContain(T.search);
  expect(inputTag(h, "p-source-tecnoempleo")).toContain('checked=""');
  expect(inputTag(h, "p-source-infojobs")).not.toContain("checked");
  expect(inputTag(h, "p-ack-infojobs")).not.toContain("checked");
  expect(inputTag(h, "p-ack-infojobs")).toContain('aria-describedby="p-warn-infojobs"');
  expect(inputTag(h, "p-ack-linkedin")).toContain('checked=""');
  expect(h).toContain(T.ackWarning("InfoJobs"));
  expect(inputTag(h, "p-ack-tecnoempleo")).toBe("");
});

test("«Probar» no se bloquea con el formulario igual a lo guardado", () => {
  const h = html(data());
  expect(h).not.toContain(`title="${T.saveFirst}"`);
});

test("si una sección no carga, las demás siguen (cada una por su cuenta)", () => {
  const h = renderToStaticMarkup(<ProfileTab initial={{ ai: ai() }} onRerunWizard={() => {}} />);
  expect(h).toContain(T.ai);
  expect(h).toContain(T.loading);
});

test("sin datos todavía, muestra que está cargando", () => {
  expect(renderToStaticMarkup(<ProfileTab onRerunWizard={() => {}} />)).toContain(T.loading);
});

test("avisa junto a los «Guardar» que reescriben jobhunter.yaml (IA, email y fuentes) de que se pierden sus comentarios", () => {
  const h = html(data());
  expect(T.yamlRewriteNote).toContain("jobhunter.yaml");
  expect(h.split(T.yamlRewriteNote).length - 1).toBe(3);
});
