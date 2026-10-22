import { expect, test } from "bun:test";
import { parseReport, parseSources, safeHref } from "./report";

test("subconjunto mínimo de Markdown: títulos, elementos de lista y párrafos", () => {
  expect(parseReport("# Título\n\nÁmbito: saved\n## Huecos\n- Kafka — 2 oferta(s)\n### Kafka (~3 semanas)\n* paso")).toEqual([
    { kind: "heading", level: 1, text: "Título" },
    { kind: "paragraph", text: "Ámbito: saved" },
    { kind: "heading", level: 2, text: "Huecos" },
    { kind: "item", text: "Kafka — 2 oferta(s)" },
    { kind: "heading", level: 3, text: "Kafka (~3 semanas)" },
    { kind: "item", text: "paso" },
  ]);
});

test("el HTML del informe queda como texto, sin interpretarse", () => {
  expect(parseReport("- <img src=x onerror=alert(1)>")).toEqual([{ kind: "item", text: "<img src=x onerror=alert(1)>" }]);
});

test("safeHref solo admite http(s)", () => {
  expect(safeHref("https://github.com/ana")).toBe("https://github.com/ana");
  expect(safeHref("javascript:alert(1)")).toBeNull();
  expect(safeHref("data:text/html,x")).toBeNull();
  expect(safeHref("no es url")).toBeNull();
  expect(safeHref(undefined)).toBeNull();
});

test("parseSources separa por líneas o comas y quita repetidas", () => {
  expect(parseSources("https://a.example\n https://b.example, https://a.example\n\n")).toEqual(["https://a.example", "https://b.example"]);
});
