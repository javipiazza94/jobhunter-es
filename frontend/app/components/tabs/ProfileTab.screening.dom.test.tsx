// Interacción real: editar respuestas de cribado guarda con PUT /api/profile sin perder el resto del perfil.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

type Call = { method: string; path: string; body: unknown };
const calls: Call[] = [];
// Lo que hay "en disco": otra sección pudo cambiar la ciudad después de cargar la pestaña.
const DISK = { personal: { name: "Ana", city: "Sevilla" }, custom_key: 1, screening_answers: [{ question: "P1", answer: "R1" }] };

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const method = (init.method ?? "GET").toUpperCase();
    const body = init.body ? JSON.parse(String(init.body)) : null;
    calls.push({ method, path: new URL(String(url)).pathname, body });
    return { ok: true, status: 200, json: async () => (method === "PUT" ? body : DISK) } as Response;
  };
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("añadir y guardar una respuesta relee el perfil y solo cambia screening_answers", async () => {
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

  const put = calls.find(c => c.method === "PUT")!;
  expect(calls.map(c => c.method)).toEqual(["GET", "PUT"]);
  expect(put.path).toBe("/api/profile");
  expect(put.body).toEqual({
    personal: { name: "Ana", city: "Sevilla" }, custom_key: 1,
    screening_answers: [{ question: "P1", answer: "R1" }, { question: "¿Carné?", answer: "Sí, B." }],
  });
  await act(async () => { root.unmount(); });
});
