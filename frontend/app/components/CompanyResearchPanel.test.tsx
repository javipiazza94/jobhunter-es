// Marcado estático del panel de investigación de empresa. Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { CompanyResearchPanel, T } from "./CompanyResearchPanel";
import type { CompanyResearch } from "@/lib/types";

const R: CompanyResearch = {
  company: "Acme Robotics", summary: "Fabrica brazos robóticos.", products: ["Brazo R1", "<b>Cinta</b>"],
  culture_signals: ["Trabajo híbrido"], tech_stack: ["Python"], size_hint: "~120 personas",
  sources: ["https://acme.example", "https://acme.example/sobre-nosotros"], warnings: [],
  fetched_date: "2026-10-20", age_days: 2, provider: "ollama",
};

test("sin investigación ofrece investigar", () => {
  const h = renderToStaticMarkup(<CompanyResearchPanel company="Acme Robotics" initialResearch={null} />);
  expect(h).toContain(T.button);
  expect(h).not.toContain(T.sources);
});

test("muestra resumen, listas, fuentes y fecha de la investigación", () => {
  const h = renderToStaticMarkup(<CompanyResearchPanel company="Acme Robotics" initialResearch={R} />);
  expect(h).toContain("Fabrica brazos robóticos.");
  expect(h).toContain("Brazo R1");
  expect(h).toContain("&lt;b&gt;Cinta&lt;/b&gt;"); // texto de la IA escapado, nunca HTML
  expect(h).toContain("https://acme.example/sobre-nosotros");
  expect(h).toContain("2026-10-20");
  expect(h).toContain("hace 2 días");
  expect(h).toContain(T.refresh);
});

test("avisos y falta de fuentes se muestran", () => {
  const warn = "robots.txt no permite leer la web de la empresa: resumen solo con el texto de la oferta";
  const h = renderToStaticMarkup(<CompanyResearchPanel company="Acme" initialResearch={{ ...R, sources: [], warnings: [warn] }} />);
  expect(h).toContain(warn);
  expect(h).toContain(T.noSources);
});

test("los errores de la API (sin IA, sin fuentes) se muestran", () => {
  const msg = "IA no disponible: La IA está desactivada (proveedor «none»). Configura un proveedor en Perfil.";
  expect(renderToStaticMarkup(<CompanyResearchPanel company="Acme" initialResearch={null} initialError={msg} />)).toContain(msg);
});
