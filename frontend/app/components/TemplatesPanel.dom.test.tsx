// Interacción real (happy-dom): listar, activar y borrar plantillas; los errores de la API (p. ej. 422 de la compilación de prueba) se muestran.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

type Call = { method: string; url: string };
const calls: Call[] = [];
const tpl = (name: string, kind: string, builtin: boolean, active: boolean) => ({
  name, kind, engine: "latex", builtin, active, main_file: "x", compile_cmd: null, page_limit: null, style_rules: "",
});

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const u = new URL(String(url));
    calls.push({ method: (init.method ?? "GET").toUpperCase(), url: u.pathname + u.search });
    if (u.pathname === "/api/templates" && (init.method ?? "GET") === "POST") {
      return { ok: false, status: 422, json: async () => ({ detail: "La compilación de prueba falló: macro desconocida" }) } as Response;
    }
    const list = [tpl("moderncv-banking", "cv", true, true), tpl("mia", "cv", false, false), tpl("cover-cls", "letter", true, true)];
    return { ok: true, status: 200, json: async () => (u.pathname === "/api/templates" ? list : {}) } as Response;
  };
});

afterAll(async () => { await GlobalRegistrator.unregister(); });

test("lista las plantillas, activa y borra una propia con el tipo en la query", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { TemplatesPanel, T } = await import("./TemplatesPanel");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<TemplatesPanel />); });
  await act(async () => { await new Promise(r => setTimeout(r, 10)); });
  expect(container.textContent).toContain("moderncv-banking");
  expect(container.textContent).toContain("mia");
  const activate = [...container.querySelectorAll("button")].find(b => b.textContent === T.activate)!;
  await act(async () => { activate.click(); });
  expect(calls).toContainEqual({ method: "POST", url: "/api/templates/mia/activate?kind=cv" });
  const remove = container.querySelector(`button[aria-label="${T.remove} mia"]`) as HTMLButtonElement;
  await act(async () => { remove.click(); });
  expect(calls).toContainEqual({ method: "DELETE", url: "/api/templates/mia?kind=cv" });
  await act(async () => { root.unmount(); });
});

test("sin nombre o sin archivo no llama a la API; el 422 de la compilación de prueba se muestra", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { TemplatesPanel, T } = await import("./TemplatesPanel");
  calls.length = 0;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<TemplatesPanel autoLoad={false} initial={[tpl("moderncv-banking", "cv", true, true)]} />); });
  const submit = () => [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.upload))!;
  await act(async () => { submit().click(); });
  expect(container.textContent).toContain(T.noName);
  expect(calls).toEqual([]);
  const input = container.querySelector(`input[aria-label="${T.name}"]`) as HTMLInputElement;
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setter.call(input, "mia");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => { submit().click(); });
  expect(container.textContent).toContain(T.noFile);
  expect(calls).toEqual([]);
  await act(async () => { root.unmount(); });
});
