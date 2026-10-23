import { afterEach, expect, test } from "bun:test";
import { saveUiLanguage } from "./AppLocaleProvider";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

test("guardar el idioma conserva el resto de preferences", async () => {
  const sent: { method: string; body: unknown }[] = [];
  globalThis.fetch = (async (_u: string, init: RequestInit = {}) => {
    const method = (init.method ?? "GET").toUpperCase();
    if (method !== "GET") sent.push({ method, body: JSON.parse(String(init.body)) });
    return { ok: true, status: 200, json: async () => ({ preferences: { theme: "dark", ui_language: "es" } }) };
  }) as unknown as typeof fetch;
  await saveUiLanguage("en");
  expect(sent).toEqual([{ method: "PATCH", body: { preferences: { theme: "dark", ui_language: "en" } } }]);
});
