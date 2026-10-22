// Contrato de las llamadas del asistente, el perfil y los ajustes: las que modifican llevan X-JH-Client,
// todas comprueban res.ok y lanzan Error(detail). Se ejecuta con `bun test`.
import { afterEach, expect, test } from "bun:test";
import * as api from "./api";

type Call = { method: string; url: string; headers: Headers; body: unknown };
let calls: Call[] = [];
const realFetch = globalThis.fetch;

function stub(status = 200, body: unknown = {}) {
  calls = [];
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    calls.push({ method: (init.method ?? "GET").toUpperCase(), url: String(url), headers: new Headers(init.headers), body: init.body });
    return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
  };
}

afterEach(() => { (globalThis as unknown as { fetch: unknown }).fetch = realFetch; });

const answers = {
  draft: { full_name: "", email: "", phone: "", city: "", country: "", targets: [], years_experience: null, experience: [], tools: [], languages: [], modality: [], eligibility: { work_permit_countries: [], needs_sponsorship: null, driving_license: null } },
  markets: [], sources: [], acknowledged_sources: [], followed_companies: [],
};

const mutating: [string, () => Promise<unknown>][] = [
  ["POST /api/setup/cv", () => api.uploadCv(new File(["x"], "cv.pdf"))],
  ["POST /api/setup/propose", () => api.proposeProfile("texto")],
  ["POST /api/setup/apply", () => api.applySetup(answers)],
  ["PUT /api/profile", () => api.saveProfile({ personal: {} })],
  ["PUT /api/settings/ai", () => api.saveAISettings({ provider: "none" })],
  ["POST /api/settings/ai/test", () => api.testAI()],
  ["PUT /api/settings/email", () => api.saveEmailSettings({ preset: "gmail" })],
  ["POST /api/settings/email/test", () => api.testEmail()],
  ["POST /api/applications/a1/interview-pack", () => api.generateInterviewPack("a1")],
  ["PUT /api/settings/sources", () => api.saveSourceSettings({ enabled: [], acknowledged: [] })],
  ["POST /api/settings/ai/key", () => api.saveAIKey({ provider: "openai", api_key: "k" })],
  ["POST /api/scraper/run", () => api.startScraperRun({ track: "data_engineer" })],
];
const reading: [string, () => Promise<unknown>][] = [
  ["GET /api/setup/status", () => api.fetchSetupStatus()],
  ["GET /api/setup/markets", () => api.fetchMarkets()],
  ["GET /api/profile", () => api.fetchProfile()],
  ["GET /api/settings/ai", () => api.fetchAISettings()],
  ["GET /api/settings/email", () => api.fetchEmailSettings()],
  ["GET /api/setup/current", () => api.fetchSetupCurrent()],
  ["GET /api/settings/sources", () => api.fetchSourceSettings()],
];

test("las que modifican llevan la cabecera; las de lectura no", async () => {
  for (const [label, call] of [...mutating, ...reading]) {
    stub();
    await call();
    const c = calls[0];
    expect(`${c.method} ${new URL(c.url).pathname}`).toBe(label);
    expect(c.headers.get("x-jh-client")).toBe(c.method === "GET" ? null : "dashboard");
  }
});

test("todas lanzan Error con el detail si la API responde con error", async () => {
  for (const [label, call] of [...mutating, ...reading]) {
    stub(409, { detail: "Completa primero el asistente" });
    let message = "";
    try { await call(); } catch (e) { message = (e as Error).message; }
    expect(`${label}: ${message}`).toBe(`${label}: Completa primero el asistente`);
  }
});

test("uploadCv envía el archivo en el campo `file` sin forzar Content-Type", async () => {
  stub(200, { draft: answers.draft, source: "empty", text_chars: 0, cv_path: "cv/cv.pdf" });
  const res = await api.uploadCv(new File(["x"], "cv.pdf"));
  expect(res.cv_path).toBe("cv/cv.pdf");
  expect(calls[0].body).toBeInstanceOf(FormData);
  expect((calls[0].body as FormData).get("file")).toBeInstanceOf(File);
  expect(calls[0].headers.get("content-type")).toBeNull();
});

test("los cuerpos JSON llevan su Content-Type y devuelven la respuesta", async () => {
  stub(200, { ok: true, message: "bien" });
  expect(await api.saveAISettings({ provider: "ollama", api_key: "k" })).toEqual({ ok: true, message: "bien" } as never);
  expect(calls[0].headers.get("content-type")).toBe("application/json");
  expect(JSON.parse(String(calls[0].body))).toEqual({ provider: "ollama", api_key: "k" });
});

test("el error lleva el código HTTP (p. ej. para ignorar un 404 de un backend antiguo)", async () => {
  stub(404, { detail: "Not Found" });
  const err = await api.fetchSetupStatus().catch(e => e);
  expect(err).toBeInstanceOf(api.ApiError);
  expect(err.status).toBe(404);
});

test("startScraperRun usa track= o source= y uploadCv añade el proveedor del asistente", async () => {
  stub(200, { status: "started", source: "track:x", job_id: "1" });
  await api.startScraperRun({ track: "data engineer" });
  expect(new URL(calls.at(-1)!.url).search).toBe("?track=data%20engineer");
  await api.startScraperRun({ source: "manfred" });
  expect(new URL(calls.at(-1)!.url).search).toBe("?source=manfred");
  await api.startScraperRun({ tracks: ["data_engineer", "analista"] });
  expect(new URL(calls.at(-1)!.url).search).toBe("?tracks=data_engineer%2Canalista");
  await api.uploadCv(new File(["x"], "cv.pdf"), "cv.pdf", { provider: "ollama", model: null, base_url: null, timeout_seconds: 120 });
  expect(JSON.parse(String((calls.at(-1)!.body as FormData).get("ai")))).toMatchObject({ provider: "ollama" });
  await api.proposeProfile("t", { provider: "none", model: null, base_url: null, timeout_seconds: 120 });
  expect(JSON.parse(String(calls.at(-1)!.body))).toMatchObject({ text: "t", ai: { provider: "none" } });
});
