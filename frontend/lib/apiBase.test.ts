import { expect, test } from "bun:test";
import { DEFAULT_API_URL, isDesktopApp, resolveApiBase } from "./apiBase";

test("sin nada inyectado usa NEXT_PUBLIC_API_URL y luego el puerto de siempre", () => {
  expect(resolveApiBase(undefined, "http://localhost:9000")).toBe("http://localhost:9000");
  expect(resolveApiBase(undefined, undefined)).toBe(DEFAULT_API_URL);
  expect(resolveApiBase({}, "")).toBe(DEFAULT_API_URL);
});

test("la URL inyectada por Tauri manda sobre el entorno y pierde la barra final", () => {
  expect(resolveApiBase({ __JH_API_URL__: "http://127.0.0.1:53211/" }, "http://localhost:9000")).toBe("http://127.0.0.1:53211");
});

test("una URL inyectada que no es de loopback se ignora", () => {
  for (const bad of ["http://evil.example:80", "https://127.0.0.1:5000", "http://127.0.0.1", "http://127.0.0.1:5000@evil.example", "javascript:1", 42, null]) {
    expect(resolveApiBase({ __JH_API_URL__: bad }, undefined)).toBe(DEFAULT_API_URL);
  }
});

test("isDesktopApp solo con la marca exacta", () => {
  expect(isDesktopApp({ __JH_DESKTOP__: true })).toBe(true);
  expect(isDesktopApp({ __JH_DESKTOP__: "true" })).toBe(false);
  expect(isDesktopApp(undefined)).toBe(false);
});
