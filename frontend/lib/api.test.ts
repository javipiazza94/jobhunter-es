// Contrato del cliente con la API (ADR-001): las llamadas que modifican llevan X-JH-Client y las de
// lectura no. Se ejecuta con `bun test`.
import { beforeAll, expect, test } from "bun:test";

type Llamada = { method: string; url: string; header: string | null };
const llamadas: Llamada[] = [];

beforeAll(() => {
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    llamadas.push({
      method: (init.method ?? "GET").toUpperCase(),
      url: String(url),
      header: new Headers(init.headers).get("x-jh-client"),
    });
    return { json: async () => ({}), blob: async () => new Blob([]) } as Response;
  };
  Object.assign(globalThis, {
    document: { createElement: () => ({ click() {} }), body: { appendChild() {}, removeChild() {} } },
  });
  URL.createObjectURL = () => "blob:x";
  URL.revokeObjectURL = () => {};
});

test("las llamadas que modifican llevan la cabecera y las de lectura no", async () => {
  const api = await import("./api");
  await api.fetchStats(); await api.fetchCompanies(); await api.fetchOffers({}); await api.fetchApplications("sent");
  await api.fetchContacts(); await api.fetchPendingApplications(); await api.fetchDashboardStats();
  await api.fetchHistory(); await api.exportHistoryCSV();
  await api.updateApplicationStatus("a", "sent"); await api.markOfferSent("o"); await api.unmarkOfferSent("o");
  await api.discardOffer("o"); await api.restoreOffer("o"); await api.triggerScraper("seed");
  await api.triggerApplications(); await api.createDrafts(1); await api.approveApplication("a");
  await api.updateCoverLetter("a", "x"); await api.rejectApplication("a"); await api.markApplicationSentManual("a");

  const lecturas = llamadas.filter((c) => c.method === "GET");
  const escrituras = llamadas.filter((c) => c.method !== "GET");
  expect(lecturas.length).toBe(9);
  expect(lecturas.every((c) => c.header === null)).toBe(true);
  expect(escrituras.length).toBe(12);
  expect(escrituras.filter((c) => c.header !== "dashboard").map((c) => `${c.method} ${c.url}`)).toEqual([]);
});

test("updateCoverLetter conserva su Content-Type junto a la cabecera propia", async () => {
  const api = await import("./api");
  llamadas.length = 0;
  let enviadas: Headers | undefined;
  (globalThis as unknown as { fetch: unknown }).fetch = async (_u: string, init: RequestInit = {}) => {
    enviadas = new Headers(init.headers);
    return { json: async () => ({}) } as Response;
  };
  await api.updateCoverLetter("a", "texto");
  expect(enviadas?.get("content-type")).toBe("application/json");
  expect(enviadas?.get("x-jh-client")).toBe("dashboard");
});
