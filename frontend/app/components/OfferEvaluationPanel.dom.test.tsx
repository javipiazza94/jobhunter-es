// Interacción real (DOM de happy-dom): carga la evaluación guardada y «Evaluar con IA» la pide y la muestra.
// Se registra el DOM solo en este archivo y se retira al terminar. Se ejecuta con `bun test`.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { OfferEvaluation } from "@/lib/types";

const EVAL: OfferEvaluation = {
  offer_id: "o1", verdict: "Good Fit", score: 64, strengths: ["Python"], gaps: ["Kafka"],
  urgency: "unknown", expired: false, evaluated_at: "2026-10-22T10:00:00+00:00", provider: "ollama",
};
type Call = { method: string; path: string; client: string | null };
const calls: Call[] = [];

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const u = new URL(String(url));
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({ method: (init.method ?? "GET").toUpperCase(), path: u.pathname, client: headers["X-JH-Client"] ?? null });
    const reply = (status: number, body: unknown) => ({ ok: status < 300, status, json: async () => body }) as Response;
    if (u.pathname.endsWith("/evaluation")) return reply(200, null);
    if (u.pathname.endsWith("/evaluate")) return reply(200, EVAL);
    return reply(404, { detail: "no" });
  };
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("sin evaluación guardada, «Evaluar con IA» la pide con la cabecera del dashboard y la muestra", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { OfferEvaluationPanel, T, verdictLabel } = await import("./OfferEvaluationPanel");

  const got: OfferEvaluation[] = [];
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<OfferEvaluationPanel offerId="o1" onEvaluated={e => got.push(e)} />);
  });
  expect(calls[0]).toEqual({ method: "GET", path: "/api/offers/o1/evaluation", client: null });

  const button = [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.button)) as HTMLButtonElement;
  await act(async () => { button.click(); });
  expect(calls[1]).toEqual({ method: "POST", path: "/api/offers/o1/evaluate", client: "dashboard" });
  expect(container.textContent).toContain(verdictLabel("Good Fit"));
  expect(container.textContent).toContain("Kafka");
  expect(got).toEqual([EVAL]);
  await act(async () => { root.unmount(); });
});
