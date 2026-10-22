// Interacción real (DOM de happy-dom): pegar preguntas con «(max N)» las envía parseadas y pinta las respuestas.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

type Call = { method: string; path: string; client: string | null; body: unknown };
const calls: Call[] = [];

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({
      method: (init.method ?? "GET").toUpperCase(), path: new URL(String(url)).pathname,
      client: headers["X-JH-Client"] ?? null, body: init.body ? JSON.parse(String(init.body)) : null,
    });
    const body = { answers: [{ question: "¿Por qué nosotros?", answer: "Me gusta el producto.", source: "ai" }] };
    return { ok: true, status: 200, json: async () => body } as Response;
  };
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("«Responder preguntas» envía las preguntas parseadas con la cabecera del dashboard y muestra el origen", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { ScreeningPanel, T } = await import("./ScreeningPanel");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<ScreeningPanel applicationId="a 1" initialText={"¿Por qué nosotros? (max 300)\n\nSalario"} />); });

  const button = [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.button))!;
  await act(async () => { button.click(); });

  expect(calls).toEqual([{
    method: "POST", path: "/api/applications/a%201/answers", client: "dashboard",
    body: { questions: [{ text: "¿Por qué nosotros?", max_chars: 300 }, { text: "Salario" }] },
  }]);
  expect(container.textContent).toContain("Me gusta el producto.");
  expect(container.textContent).toContain(T.sources.ai);
  await act(async () => { root.unmount(); });
});

test("sin preguntas no llama a la API", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { ScreeningPanel, T } = await import("./ScreeningPanel");
  calls.length = 0;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<ScreeningPanel applicationId="a1" initialText="   " />); });
  const button = [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.button))!;
  await act(async () => { button.click(); });
  expect(calls).toEqual([]);
  expect(container.textContent).toContain(T.empty);
  await act(async () => { root.unmount(); });
});
