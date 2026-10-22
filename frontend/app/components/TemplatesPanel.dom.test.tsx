// Interacción real (happy-dom): listar, activar y borrar plantillas; los errores de la API (p. ej. 422 de la compilación de prueba) se muestran.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

type Call = { method: string; url: string };
const calls: Call[] = [];
let lastForm: FormData | null = null;
const tpl = (name: string, kind: string, builtin: boolean, active: boolean, invalid_reason: string | null = null) => ({
  name, kind, engine: "latex", builtin, active, main_file: "x", compiler: null, page_limit: null, style_rules: "",
  invalid_reason, trusted: !builtin,
});

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const u = new URL(String(url));
    calls.push({ method: (init.method ?? "GET").toUpperCase(), url: u.pathname + u.search });
    if (u.pathname === "/api/templates" && (init.method ?? "GET") === "POST") {
      lastForm = init.body as FormData;
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

async function typeInto(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const { act } = await import("react");
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  await act(async () => {
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

test("subir: envía motor, compilador, páginas y reglas en el multipart y enseña el 422", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { TemplatesPanel, T } = await import("./TemplatesPanel");
  calls.length = 0;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<TemplatesPanel autoLoad={false} initial={[tpl("moderncv-banking", "cv", true, true)]} />); });
  const q = <E extends Element>(sel: string) => container.querySelector(sel) as unknown as E;
  await typeInto(q<HTMLInputElement>(`input[aria-label="${T.name}"]`), "mia-typ");
  await typeInto(q<HTMLInputElement>(`input[aria-label="${T.pageLimit}"]`), "1");
  await typeInto(q<HTMLTextAreaElement>(`textarea[aria-label="${T.styleRules}"]`), "Resumen de una frase");
  const fileInput = q<HTMLInputElement>(`input[aria-label="${T.file}"]`);
  Object.defineProperty(fileInput, "files", { value: [new File(["= hola"], "cv.typ.j2")], configurable: true });
  await act(async () => { fileInput.dispatchEvent(new Event("change", { bubbles: true })); });
  // el nombre .typ.j2 elige Typst y su único compilador
  expect(q<HTMLSelectElement>(`select[aria-label="${T.engine}"]`).value).toBe("typst");
  const compiler = q<HTMLSelectElement>(`select[aria-label="${T.compiler}"]`);
  expect([...compiler.options].map(o => o.value)).toEqual(["", "typst"]);
  await act(async () => {
    compiler.value = "typst";
    compiler.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const submit = [...container.querySelectorAll("button")].find(b => b.textContent?.includes(T.upload))!;
  // sin confirmar la confianza no se sube nada
  expect(container.textContent).toContain(T.trust);
  await act(async () => { submit.click(); });
  expect(container.querySelector('[role="alert"]')!.textContent).toBe(T.noTrust);
  expect(calls).toEqual([]);
  const trust = [...container.querySelectorAll("label")].find(l => l.textContent?.includes(T.trustCheck))!
    .querySelector("input") as HTMLInputElement;
  await act(async () => { trust.click(); });
  await act(async () => { submit.click(); });
  await act(async () => { await new Promise(r => setTimeout(r, 10)); });
  expect(calls).toContainEqual({ method: "POST", url: "/api/templates" });
  const form = lastForm!;
  expect(form.get("name")).toBe("mia-typ");
  expect(form.get("kind")).toBe("cv");
  expect(form.get("engine")).toBe("typst");
  expect(form.get("compiler")).toBe("typst");
  expect(form.get("page_limit")).toBe("1");
  expect(form.get("style_rules")).toBe("Resumen de una frase");
  expect((form.get("file") as File).name).toBe("cv.typ.j2");
  expect(form.get("trusted")).toBe("true");
  expect(form.has("compile_cmd")).toBe(false);
  expect(container.querySelector('[role="alert"]')!.textContent).toBe("La compilación de prueba falló: macro desconocida");
  await act(async () => { root.unmount(); });
});

test("una plantilla antigua no válida se marca, explica el motivo y no se puede activar", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { TemplatesPanel, T } = await import("./TemplatesPanel");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const reason = "Su comando de compilación (latexmk) ya no se admite";
  await act(async () => {
    root.render(<TemplatesPanel autoLoad={false} initial={[tpl("moderncv-banking", "cv", true, true), tpl("vieja", "cv", false, false, reason)]} />);
  });
  expect(container.textContent).toContain(T.invalid);
  expect(container.textContent).toContain(reason);
  expect([...container.querySelectorAll("button")].some(b => b.textContent === T.activate)).toBe(false);
  await act(async () => { root.unmount(); });
});
