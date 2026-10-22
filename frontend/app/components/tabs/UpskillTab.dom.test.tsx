// Interacción real (DOM de happy-dom): «Generar» pide el informe y lo muestra como texto, sin interpretar HTML.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

const calls: { method: string; path: string; client: string | null; body: unknown }[] = [];
const REPORT = {
  report_path: "/home/ana/jh/reports/upskill-2026-10-22.md",
  markdown: "# Mapa de huecos\n\n## Huecos\n- Kafka — 2 oferta(s)\n## Recursos sugeridos por la IA (sin verificar)\n- Curso <img src=x onerror=alert(1)> (sin verificar)\n",
  offers_analyzed: 2, gaps: [{ skill: "Kafka", count: 2 }], ai_used: true,
};

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const u = new URL(String(url));
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({ method: (init.method ?? "GET").toUpperCase(), path: u.pathname, client: headers["X-JH-Client"] ?? null, body: init.body ? JSON.parse(String(init.body)) : null });
    return { ok: true, status: 200, json: async () => REPORT } as Response;
  };
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("«Generar mapa de huecos» pide el informe y lo pinta como texto", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { UpskillTab, T } = await import("./UpskillTab");

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<UpskillTab />); });
  const button = [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.button)) as HTMLButtonElement;
  await act(async () => { button.click(); });

  expect(calls[0]).toEqual({ method: "POST", path: "/api/upskill", client: "dashboard", body: { scope: "saved", offer_ids: [] } });
  expect(container.textContent).toContain("Kafka — 2 oferta(s)");
  expect(container.textContent).toContain("(sin verificar)");
  expect(container.textContent).toContain("<img src=x onerror=alert(1)>"); // texto literal
  expect(container.querySelector("img")).toBeNull();
  await act(async () => { root.unmount(); });
});
