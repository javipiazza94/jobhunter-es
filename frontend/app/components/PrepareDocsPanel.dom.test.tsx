// Interacción real (happy-dom): «Preparar candidatura» llama a /prepare con IA solo si hay proveedor y enseña el resultado.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

type Call = { method: string; path: string; client: string | null; body: unknown };
const calls: Call[] = [];
let provider = "ollama";
let prepared = false;
// Respuestas de error guionizadas para /prepare (se consumen en orden; vacío = éxito).
const prepareErrors: { status: number; detail: unknown }[] = [];

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const headers = (init.headers ?? {}) as Record<string, string>;
    const path = new URL(String(url)).pathname;
    calls.push({ method: (init.method ?? "GET").toUpperCase(), path, client: headers["X-JH-Client"] ?? null, body: init.body ? JSON.parse(String(init.body)) : null });
    let body: unknown = {};
    if (path.endsWith("/prepare") && prepareErrors.length) {
      const { status, detail } = prepareErrors.shift()!;
      return { ok: false, status, json: async () => ({ detail }) } as Response;
    }
    if (path.endsWith("/prepare")) {
      prepared = true;
      body = {
        application_id: "a1", cv_pdf: "/x/cv.pdf", cover_pdf: "/x/cover.pdf", source: "ai",
        verification: { pages: { cv: 2, cover: 1 }, missing_keywords: ["kubernetes"], layout: "skipped: poppler no instalado" },
        warnings: ["IA: se acortó el CV"],
      };
    } else if (path.endsWith("/documents")) {
      body = prepared ? [{ name: "cv.pdf", size: 1, modified_at: "x" }, { name: "cover.pdf", size: 1, modified_at: "x" }] : [];
    } else if (path.endsWith("/settings/ai")) {
      body = { provider, model: null, base_url: null, timeout_seconds: 120, has_key: {}, key_source: {} };
    }
    return { ok: true, status: 200, json: async () => body } as Response;
  };
});

afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(element: React.ReactElement) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(element); });
  await act(async () => { await new Promise(r => setTimeout(r, 10)); });
  return { container, act, unmount: () => act(async () => { root.unmount(); }) };
}

test("con proveedor de IA envía use_ai, y muestra origen, páginas, huecos y avisos", async () => {
  const { PrepareDocsPanel, T } = await import("./PrepareDocsPanel");
  const { container, act, unmount } = await mount(<PrepareDocsPanel applicationId="a 1" />);
  expect(container.textContent).toContain(T.withAi);
  const button = [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.button))!;
  await act(async () => { button.click(); });
  const post = calls.find(c => c.method === "POST")!;
  expect(post).toEqual({ method: "POST", path: "/api/applications/a%201/prepare", client: "dashboard", body: { use_ai: true } });
  expect(container.textContent).toContain("CV 2 pág. · Carta 1 pág.");
  expect(container.textContent).toContain("kubernetes");
  expect(container.textContent).toContain("IA: se acortó el CV");
  expect(container.textContent).toContain(T.layoutSkipped);
  expect([...container.querySelectorAll("a")].map(a => a.getAttribute("href"))).toContain(
    "http://localhost:8020/api/applications/a%201/documents/cv.pdf?inline=1",
  );
  await unmount();
});

test("sin proveedor de IA no hay interruptor y se pide use_ai false", async () => {
  provider = "none";
  prepared = false;
  calls.length = 0;
  const { PrepareDocsPanel, T } = await import("./PrepareDocsPanel");
  const { container, act, unmount } = await mount(<PrepareDocsPanel applicationId="a1" />);
  expect(container.textContent).not.toContain(T.withAi);
  const button = [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.button))!;
  await act(async () => { button.click(); });
  expect(calls.find(c => c.method === "POST")!.body).toEqual({ use_ai: false });
  await unmount();
});

test("un 422 enseña los motivos y, si falla una plantilla propia, ofrece reintentar con las integradas", async () => {
  provider = "none";
  prepared = false;
  calls.length = 0;
  prepareErrors.push({
    status: 422,
    detail: {
      message: "Los PDFs no superan la verificación",
      reasons: ["La plantilla propia falló: UndefinedError: 'foto' is undefined", "Corrige la plantilla propia"],
      builtin_fallback: true,
    },
  });
  const { PrepareDocsPanel, T } = await import("./PrepareDocsPanel");
  const { container, act, unmount } = await mount(<PrepareDocsPanel applicationId="a1" />);
  const button = [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.button))!;
  await act(async () => { button.click(); });
  const alert = container.querySelector('[role="alert"]')!.textContent!;
  expect(alert).toBe(
    "Los PDFs no superan la verificación: La plantilla propia falló: UndefinedError: 'foto' is undefined; Corrige la plantilla propia",
  );
  const fallback = [...container.querySelectorAll("button")].find(b => b.textContent === T.fallback)!;
  expect(fallback).toBeTruthy();
  await act(async () => { fallback.click(); });
  const posts = calls.filter(c => c.method === "POST");
  expect(posts.at(-1)!.body).toEqual({ use_ai: false, builtin_templates: true });
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect([...container.querySelectorAll("button")].some(b => b.textContent === T.fallback)).toBe(false);
  await unmount();
});

test("un 422 de verificación normal no ofrece la reserva; un 409 enseña la pista de instalación", async () => {
  provider = "none";
  calls.length = 0;
  prepareErrors.push(
    { status: 422, detail: { message: "Los PDFs no superan la verificación", reasons: ["Falta el teléfono en el CV"], builtin_fallback: false } },
    { status: 409, detail: "Instala Tectonic (https://tectonic-typesetting.github.io; Linux/macOS: curl …)" },
  );
  const { PrepareDocsPanel, T } = await import("./PrepareDocsPanel");
  const { container, act, unmount } = await mount(<PrepareDocsPanel applicationId="a1" />);
  const button = () => [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.button) || b.textContent?.includes(T.rebuild))!;
  await act(async () => { button().click(); });
  expect(container.querySelector('[role="alert"]')!.textContent).toContain("Falta el teléfono en el CV");
  expect([...container.querySelectorAll("button")].some(b => b.textContent === T.fallback)).toBe(false);
  await act(async () => { button().click(); });
  expect(container.querySelector('[role="alert"]')!.textContent).toStartWith("Instala Tectonic");
  await unmount();
});
