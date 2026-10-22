// Interacción real con el asistente (DOM de happy-dom): paso 3 → aplicar → lanzar búsquedas → onDone.
// Se registra el DOM solo en este archivo y se retira al terminar. Se ejecuta con `bun test`.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { MarketSource } from "@/lib/types";
import { emptyWizardState, type RunSummary, type WizardState } from "@/lib/setup";

const MARKETS: Record<string, MarketSource[]> = {
  spain: [
    { id: "tecnoempleo", label: "Tecnoempleo", requires_ack: false, default_on: true },
    { id: "infojobs", label: "InfoJobs", requires_ack: true, default_on: false },
    { id: "manfred", label: "Manfred", requires_ack: false, default_on: true },
  ],
};

type Call = { method: string; path: string; body: unknown };
const calls: Call[] = [];

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const u = new URL(String(url));
    calls.push({ method: (init.method ?? "GET").toUpperCase(), path: u.pathname + u.search, body: init.body ? JSON.parse(String(init.body)) : null });
    const reply = (status: number, body: unknown) => ({ ok: status < 300, status, json: async () => body }) as Response;
    if (u.pathname === "/api/setup/apply") return reply(200, { tracks: ["data_engineer"], sources: ["tecnoempleo", "infojobs", "manfred"] });
    if (u.search.includes("source=manfred")) return reply(429, { detail: "«manfred» se ejecutó hace poco; vuelve a intentarlo en 30 s." });
    return reply(200, { status: "started", source: "x", job_id: "1" });
  };
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("paso 3: bloquea una fuente con aviso sin aceptar; al aceptarla aplica, lanza y resume qué arrancó", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { SetupWizard, T } = await import("./SetupWizard");

  const state: WizardState = {
    ...emptyWizardState(),
    draft: { ...emptyWizardState().draft, targets: [{ title: "Data Engineer", keywords: [] }] },
    markets: ["spain"],
  };
  const done: RunSummary[] = [];
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<SetupWizard initialStep={3} initialState={state} initialMarkets={MARKETS} onDone={s => done.push(s)} />);
  });

  const q = (sel: string) => container.querySelector(sel) as HTMLElement;
  const finish = () => [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.finish)) as HTMLButtonElement;

  await act(async () => { q('input[name="source-infojobs"]').click(); });
  await act(async () => { finish().click(); });
  expect(container.querySelector('ul[role="alert"]')?.textContent).toContain("Acepta el aviso de InfoJobs");
  expect(calls.length).toBe(0);
  expect(done.length).toBe(0);

  await act(async () => { q('input[name="ack-infojobs"]').click(); });
  await act(async () => { finish().click(); });

  const apply = calls.find(c => c.path === "/api/setup/apply")!;
  expect((apply.body as { sources: string[] }).sources).toEqual(["tecnoempleo", "infojobs", "manfred"]);
  expect((apply.body as { acknowledged_sources: string[] }).acknowledged_sources).toEqual(["infojobs"]);
  expect(calls.filter(c => c.path.startsWith("/api/scraper/run")).map(c => c.path)).toEqual([
    "/api/scraper/run?tracks=data_engineer",
    "/api/scraper/run?source=manfred",
  ]);
  expect(done).toEqual([{
    started: ["data_engineer"],
    failed: [{ name: "manfred", message: "«manfred» se ejecutó hace poco; vuelve a intentarlo en 30 s." }],
  }]);
  await act(async () => { root.unmount(); });
});
