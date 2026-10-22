// Interacción real (DOM de happy-dom): carga la investigación guardada y «Investigar empresa» la pide y la muestra.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { CompanyResearch } from "@/lib/types";

const R: CompanyResearch = {
  company: "Novartis A/S", summary: "Farmacéutica danesa.", products: [], culture_signals: [], tech_stack: [],
  size_hint: "", sources: ["https://novartis.example"], warnings: [], fetched_date: "2026-10-22", age_days: 0, provider: "ollama",
};
type Call = { method: string; path: string; client: string | null };
const calls: Call[] = [];
let postStatus = 200;

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const u = new URL(String(url));
    const headers = (init.headers ?? {}) as Record<string, string>;
    const method = (init.method ?? "GET").toUpperCase();
    calls.push({ method, path: decodeURIComponent(u.pathname), client: headers["X-JH-Client"] ?? null });
    const reply = (status: number, body: unknown) => ({ ok: status < 300, status, json: async () => body }) as Response;
    if (method === "GET") return reply(200, null);
    return postStatus === 200 ? reply(200, R) : reply(postStatus, { detail: "IA no disponible: sin proveedor" });
  };
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("«Investigar empresa» la pide con la cabecera del dashboard, el nombre codificado, y la muestra; un error se enseña", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { CompanyResearchPanel, T } = await import("./CompanyResearchPanel");

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<CompanyResearchPanel company="Novartis A/S" />); });
  expect(calls[0]).toEqual({ method: "GET", path: "/api/companies/Novartis A/S/research", client: null });

  const button = () => [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.button) || b.textContent?.includes(T.refresh)) as HTMLButtonElement;
  postStatus = 409;
  await act(async () => { button().click(); });
  expect(calls[1]).toEqual({ method: "POST", path: "/api/companies/Novartis A/S/research", client: "dashboard" });
  expect(container.querySelector("[role=alert]")?.textContent).toContain("IA no disponible");

  postStatus = 200;
  await act(async () => { button().click(); });
  expect(container.textContent).toContain("Farmacéutica danesa.");
  expect(container.textContent).toContain("https://novartis.example");
  expect(container.querySelector("[role=alert]")).toBeNull();
  await act(async () => { root.unmount(); });
});
