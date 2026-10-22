// Interacción real (DOM de happy-dom): buscar propone con su fuente sin guardar; aceptar guarda solo esa; rechazar la quita.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

type Call = { method: string; path: string; client: string | null; body: unknown };
const calls: Call[] = [];
const PROPOSALS = [
  { name: "Rust", evidence: "2 repositorio(s) públicos", source_url: "https://github.com/ana-test" },
  { name: "Terraform", evidence: "Cita Terraform", source_url: "javascript:alert(1)" },
];

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const u = new URL(String(url));
    const headers = (init.headers ?? {}) as Record<string, string>;
    const body = init.body ? JSON.parse(String(init.body)) : null;
    calls.push({ method: (init.method ?? "GET").toUpperCase(), path: u.pathname, client: headers["X-JH-Client"] ?? null, body });
    const reply = (status: number, data: unknown) => ({ ok: status < 300, status, json: async () => data }) as Response;
    if (u.pathname === "/api/profile/expand") return reply(200, { proposals: PROPOSALS, errors: [{ url: "https://roto.example", error: "No se pudo leer" }] });
    if (u.pathname === "/api/profile/expand/accept") return reply(200, { added: [body.items[0].name], skipped: [] });
    return reply(404, { detail: "no" });
  };
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("buscar propone con fuente; solo se guarda lo aceptado; los enlaces no seguros no son enlaces", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { ExpandProfilePanel, T } = await import("./ExpandProfilePanel");

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<ExpandProfilePanel initialText={"https://github.com/ana-test\nhttps://roto.example"} />); });

  const find = (label: string) => [...container.querySelectorAll("button")].find(b => b.textContent?.includes(label)) as HTMLButtonElement;
  await act(async () => { find(T.button).click(); });

  expect(calls).toHaveLength(1);
  expect(calls[0]).toMatchObject({ method: "POST", path: "/api/profile/expand", client: "dashboard", body: { sources: ["https://github.com/ana-test", "https://roto.example"] } });
  expect(container.textContent).toContain("Rust");
  expect(container.textContent).toContain("No se pudo leer");
  const links = [...container.querySelectorAll("a")].map(a => a.getAttribute("href"));
  expect(links).toEqual(["https://github.com/ana-test"]); // javascript: no se enlaza
  expect(container.textContent).toContain("javascript:alert(1)"); // se muestra como texto

  await act(async () => { find(T.accept).click(); }); // acepta la primera: Rust
  expect(calls[1]).toMatchObject({ path: "/api/profile/expand/accept", body: { items: [PROPOSALS[0]] } });
  expect(container.textContent).toContain(T.accepted(1));
  expect(container.textContent).not.toContain("2 repositorio(s)");

  await act(async () => { find(T.reject).click(); }); // rechaza Terraform: sin llamada al servidor
  expect(calls).toHaveLength(2);
  expect(container.querySelectorAll("li")).toHaveLength(0);
  await act(async () => { root.unmount(); });
});
