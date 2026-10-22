// Interacción real (happy-dom): elegir otro idioma cambia los textos, <html lang> y se guarda.
import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("el selector lista es/en, cambia la interfaz, <html lang>, localStorage y el perfil", async () => {
  const { createRoot } = await import("react-dom/client");
  const { act } = await import("react");
  const { LocaleProvider, useT, getLocale, setLocale } = await import("@/lib/i18n");
  const { LanguageSelector } = await import("./LanguageSelector");

  setLocale("es");
  const saved: string[] = [];
  function Probe() {
    const t = useT();
    return <h1>{t("tabs.offers")}</h1>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <LocaleProvider profileLocale={null} persist={async l => { saved.push(l); }}>
        <LanguageSelector /><Probe />
      </LocaleProvider>,
    );
  });
  const select = host.querySelector("select") as HTMLSelectElement;
  expect([...select.options].map(o => o.value)).toEqual(["es", "en"]);
  expect([...select.options].map(o => o.text)).toEqual(["Español", "English"]);
  expect(host.querySelector("h1")!.textContent).toBe("Ofertas");

  await act(async () => {
    select.value = "en";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(getLocale()).toBe("en");
  expect(host.querySelector("h1")!.textContent).toBe("Offers");
  expect(document.documentElement.lang).toBe("en");
  expect(localStorage.getItem("jh.locale")).toBe("en");
  expect(saved).toEqual(["en"]);
  expect(select.getAttribute("aria-label")).toBe("Language");

  await act(async () => root.unmount());
  setLocale("es");
});

test("el proveedor aplica el idioma del perfil por encima de localStorage", async () => {
  const { createRoot } = await import("react-dom/client");
  const { act } = await import("react");
  const { LocaleProvider, getLocale, setLocale } = await import("@/lib/i18n");
  setLocale("es");
  localStorage.setItem("jh.locale", "es");
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<LocaleProvider loadProfileLocale={async () => "en"}><span /></LocaleProvider>);
  });
  expect(getLocale()).toBe("en");
  await act(async () => root.unmount());
  setLocale("es");
});
