// Interacción real (happy-dom): el aviso solo existe en escritorio y pide el estado a la API.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

const paths: string[] = [];

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  (globalThis as unknown as { fetch: unknown }).fetch = async (url: string) => {
    paths.push(new URL(String(url)).pathname);
    const body = { installed: false, running: false, models: [], install_url: "https://ollama.com/download" };
    return { ok: true, status: 200, json: async () => body } as Response;
  };
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { OllamaNotice } = await import("./OllamaNotice");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<OllamaNotice />); });
  return { container, unmount: () => act(async () => { root.unmount(); }) };
}

test("en el navegador no pinta nada ni llama a la API", async () => {
  delete (window as unknown as Record<string, unknown>).__JH_DESKTOP__;
  paths.length = 0;
  const { container, unmount } = await mount();
  expect(container.textContent).toBe("");
  expect(paths).toEqual([]);
  await unmount();
});

test("en escritorio avisa de que falta Ollama y enlaza a la descarga", async () => {
  (window as unknown as Record<string, unknown>).__JH_DESKTOP__ = true;
  paths.length = 0;
  const { container, unmount } = await mount();
  const { T } = await import("./OllamaNotice");
  expect(paths).toEqual(["/api/ai/ollama"]);
  expect(container.textContent).toContain(T.missing);
  expect(container.querySelector("a")?.getAttribute("href")).toBe("https://ollama.com/download");
  await unmount();
});
