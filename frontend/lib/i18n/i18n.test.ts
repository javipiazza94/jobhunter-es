import { afterEach, beforeEach, expect, test } from "bun:test";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { renderIndex, listLanguages } from "../../scripts/gen-i18n-index";
import { DICTIONARIES, SUPPORTED } from "./languages.generated";
import { errorMessage, formatDate, getLocale, resolveInitialLocale, setLocale, t, translate } from "./index";

const DIR = import.meta.dir;

beforeEach(() => setLocale("es"));
afterEach(() => setLocale("es"));

test("es y en tienen exactamente las mismas claves", () => {
  const es = Object.keys(DICTIONARIES.es).sort();
  const en = Object.keys(DICTIONARIES.en).sort();
  expect(en).toEqual(es);
});

test("todo idioma registrado tiene las mismas claves que es y un nombre propio", () => {
  const base = Object.keys(DICTIONARIES.es).sort();
  for (const lang of SUPPORTED) {
    expect(Object.keys(DICTIONARIES[lang]).sort()).toEqual(base);
    expect(DICTIONARIES[lang]["meta.name"].length).toBeGreaterThan(0);
  }
});

test("las variables {x} coinciden entre idiomas en cada clave", () => {
  const vars = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();
  for (const key of Object.keys(DICTIONARIES.es)) {
    expect(vars(DICTIONARIES.en[key])).toEqual(vars(DICTIONARIES.es[key]));
  }
});

test("el índice generado está al día con los ficheros <lang>.json", () => {
  const codes = listLanguages(DIR);
  expect(SUPPORTED).toEqual(["es", ...codes.filter(c => c !== "es").sort()]);
  expect(readFileSync(join(DIR, "languages.generated.ts"), "utf8")).toBe(renderIndex(codes));
  expect(readdirSync(DIR).filter(f => f.endsWith(".json")).length).toBe(codes.length);
});

test("t interpola variables y usa el idioma activo", () => {
  expect(translate("es", "errors.with_code", { message: "Hola", status: 404 })).toBe("Hola (404)");
  setLocale("en");
  expect(t("tabs.offers")).toBe("Offers");
  setLocale("es");
  expect(t("tabs.offers")).toBe("Ofertas");
});

test("una variable ausente se deja visible y un idioma desconocido cae a es", () => {
  expect(translate("es", "errors.with_code", { message: "x" })).toBe("x ({status})");
  expect(translate("xx", "tabs.offers")).toBe("Ofertas");
});

test("clave inexistente: devuelve la propia clave", () => {
  expect(t("no.existe")).toBe("no.existe");
  expect(translate("en", "no.existe")).toBe("no.existe");
});

test("si falta una clave en el idioma activo cae a es", () => {
  DICTIONARIES.en["solo.es"] = "";
  delete DICTIONARIES.en["solo.es"];
  DICTIONARIES.es["solo.es"] = "solo en español";
  try {
    expect(translate("en", "solo.es")).toBe("solo en español");
  } finally {
    delete DICTIONARIES.es["solo.es"];
  }
});

test("setLocale ignora idiomas no soportados", () => {
  setLocale("klingon");
  expect(getLocale()).toBe("es");
});

test("resolveInitialLocale: perfil, luego localStorage, luego navegador, luego es", () => {
  expect(resolveInitialLocale({ profile: "en", stored: "es", nav: "es-ES" })).toBe("en");
  expect(resolveInitialLocale({ profile: "xx", stored: "en", nav: "es-ES" })).toBe("en");
  expect(resolveInitialLocale({ nav: "en-GB" })).toBe("en");
  expect(resolveInitialLocale({ nav: "fr-FR" })).toBe("es");
  expect(resolveInitialLocale({})).toBe("es");
});

test("formatDate usa el idioma activo", () => {
  const d = "2026-03-05T12:00:00Z";
  setLocale("es");
  expect(formatDate(d)).toBe("5/3/2026");
  setLocale("en");
  expect(formatDate(d)).toBe("3/5/2026");
  expect(formatDate("no es fecha")).toBe("");
});

test("errorMessage traduce por err.code o err.detail.code y cae a message/detail", () => {
  setLocale("en");
  expect(errorMessage({ code: "offer_not_found", message: "Oferta no encontrada" })).toBe("Offer not found");
  expect(errorMessage({ detail: { code: "unknown_track" }, message: "x" })).toBe("Unknown track");
  expect(errorMessage({ code: "codigo_raro", message: "Mensaje del servidor" })).toBe("Mensaje del servidor");
  expect(errorMessage({ detail: "Solo detail" })).toBe("Solo detail");
  expect(errorMessage(new Error("boom"))).toBe("boom");
  expect(errorMessage(undefined)).toBe("Something went wrong. Please try again.");
});

test("setLocale con remember:false no escribe jh.locale", () => {
  const store = new Map<string, string>();
  (globalThis as { localStorage?: unknown }).localStorage = {
    getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k),
  };
  localStorage.removeItem("jh.locale");
  setLocale("en", { remember: false });
  expect(localStorage.getItem("jh.locale")).toBeNull();
  setLocale("es");
  expect(localStorage.getItem("jh.locale")).toBe("es");
  delete (globalThis as { localStorage?: unknown }).localStorage;
});

test("resolveInitialLocale acepta códigos con región si hay fichero", () => {
  DICTIONARIES["pt-BR"] = {};
  SUPPORTED.push("pt-BR");
  try {
    expect(resolveInitialLocale({ nav: "pt-br" })).toBe("pt-BR");
  } finally {
    delete DICTIONARIES["pt-BR"];
    SUPPORTED.pop();
  }
});

test("el generador acepta xx y xx-YY", () => {
  const out = renderIndex(["es", "pt-BR", "en"]);
  expect(out).toContain('"pt-BR": dict_pt_BR');
  expect(out).toContain('SUPPORTED: string[] = ["es","en","pt-BR"]');
});
