// Interacción real: editar respuestas de cribado guarda con PUT /api/profile sin perder el resto del perfil.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

type Call = { method: string; path: string; body: unknown };
const calls: Call[] = [];

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const method = (init.method ?? "GET").toUpperCase();
    const body = init.body ? JSON.parse(String(init.body)) : null;
    calls.push({ method, path: new URL(String(url)).pathname, body });
    return { ok: true, status: 200, json: async () => body } as Response;
  };
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("añadir y guardar una respuesta envía un PATCH solo con screening_answers", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { ProfileTab, T } = await import("./ProfileTab");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const stale = { personal: { name: "Ana", city: "Madrid" }, screening_answers: [{ question: "P1", answer: "R1" }] };
  await act(async () => { root.render(<ProfileTab initial={{ profile: stale }} onRerunWizard={() => {}} />); });

  const section = [...container.querySelectorAll("section")].find(s => s.textContent?.includes(T.screening))!;
  const click = async (text: string) => {
    const b = [...section.querySelectorAll("button")].find(x => x.textContent?.includes(text))!;
    await act(async () => { b.click(); });
  };
  await click(T.screeningAdd);
  const setValue = async (el: Element, value: string) => {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    await act(async () => {
      Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  await setValue(section.querySelector("#sa-q-1")!, "  ¿Carné?  ");
  await setValue(section.querySelector("#sa-a-1")!, "Sí, B.");
  await click(T.save);

  expect(calls.map(c => c.method)).toEqual(["PATCH"]);
  expect(calls[0].path).toBe("/api/profile");
  expect(calls[0].body).toEqual({
    screening_answers: [{ question: "P1", answer: "R1" }, { question: "¿Carné?", answer: "Sí, B." }],
  });
  await act(async () => { root.unmount(); });
});

test("guardar la sección Perfil envía un PATCH solo con personal e idiomas", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { ProfileTab, T } = await import("./ProfileTab");
  calls.length = 0;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const stored = { personal: { name: "Ana", city: "Madrid" }, languages: [], screening_answers: [{ question: "P1", answer: "R1" }] };
  await act(async () => { root.render(<ProfileTab initial={{ profile: stored }} onRerunWizard={() => {}} />); });
  const section = [...container.querySelectorAll("section")].find(s => s.textContent?.includes(T.fullName))!;
  const save = [...section.querySelectorAll("button")].find(b => b.textContent?.includes(T.save))!;
  await act(async () => { save.click(); });
  expect(calls.map(c => c.method)).toEqual(["PATCH"]);
  expect(Object.keys(calls[0].body as object).sort()).toEqual(["languages", "personal"]);
  await act(async () => { root.unmount(); });
});
