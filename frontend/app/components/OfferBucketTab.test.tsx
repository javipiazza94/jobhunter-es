// Render del componente de las pestañas SAP / DS / puente. Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { Application, JobOffer } from "@/lib/types";
import { ISOLATED_COLUMN, OfferBucketTab, STANDARD_COLUMN } from "./OfferBucketTab";

const oferta = (id: string, extra: Partial<JobOffer> = {}): JobOffer => ({
  id, title: `Oferta ${id}`, company_name: "ACME", location: "Villanova", relevance_score: 0.7, url: "http://x/" + id,
  description: null, cv_profile: null, modality: null, salary_text: null, experience_level: null, contract_type: null,
  source: "tecnoempleo", is_applied: 0, followed_tier: 1, track_tag: "PS", open_to_junior: 1,
  job_kind: null, generic_score: 0.5, ...extra,
});
const app = { id: "a1", job_offer_id: "t1", status: "interview" } as Application;
const noop = () => {};
const base = {
  newOffers: [oferta("n1", { salary_text: "30.000 €" })], trackedOffers: [oferta("t1")], applications: [app],
  selectedIds: new Set<string>(), emptyNew: "Sin novedades", onToggleSelected: noop, onSelectMany: noop,
  onSelectOffer: noop, onSelectApplication: noop,
};
const html = (props: object) => renderToStaticMarkup(<OfferBucketTab {...base} {...props} />);

test("muestra contadores, ofertas y el estado de la candidatura", () => {
  const h = html({ column: STANDARD_COLUMN });
  expect(h).toContain("1 sin candidatura");
  expect(h).toContain("1 con candidatura");
  expect(h).toContain("Oferta n1");
  expect(h).toContain("interview");
});

test("la columna de clasificación cambia según la pestaña", () => {
  expect(html({ column: STANDARD_COLUMN })).toContain("Tier / Etiqueta");
  expect(html({ column: ISOLATED_COLUMN })).toContain("Afinidad");
});

test("un track estándar muestra la insignia de tier y el track_tag", () => {
  const h = html({ column: STANDARD_COLUMN, newOffers: [oferta("n1", { followed_tier: 1, track_tag: "PS" })] });
  expect(h).toContain("Tier 1");
  expect(h).toContain(">PS<");
});

test("un track aislado muestra la afinidad y no el tier", () => {
  const h = html({ column: ISOLATED_COLUMN, newOffers: [oferta("n1", { followed_tier: 1, generic_score: 0.73 })] });
  expect(h).toContain("0.73");
  expect(h).not.toContain("Tier 1");
});

test("la afinidad solo sale en la tabla de nuevas, no en la de con candidatura", () => {
  const h = html({ column: ISOLATED_COLUMN });
  expect(h.split("Afinidad").length - 1).toBe(1);
  expect(html({ column: STANDARD_COLUMN }).split("Tier / Etiqueta").length - 1).toBe(2);
});

test("el aviso de junior y el chip de salario son opcionales", () => {
  expect(html({ column: STANDARD_COLUMN })).not.toContain("Abierto a junior");
  expect(html({ column: STANDARD_COLUMN, showJuniorBadge: true })).toContain("Abierto a junior");
  expect(html({ column: STANDARD_COLUMN })).not.toContain("30.000 €");
  expect(html({ column: STANDARD_COLUMN, showSalary: true })).toContain("30.000 €");
});

test("sin ofertas nuevas se muestra el mensaje vacío y la introducción opcional", () => {
  const h = html({ column: STANDARD_COLUMN, newOffers: [], intro: "Texto introductorio" });
  expect(h).toContain("Sin novedades");
  expect(h).toContain("Texto introductorio");
  expect(h).toContain("0 sin candidatura");
});

test("el tope de animación limita el retardo escalonado", () => {
  const muchas = Array.from({ length: 40 }, (_, i) => oferta("m" + i));
  const h = html({ column: ISOLATED_COLUMN, newOffers: muchas, maxAnimationIndex: 30 });
  expect(h).toContain("animation-delay:0.8999999999999999s");
  expect(h).not.toContain("animation-delay:1.17");
});

test("las casillas reflejan la selección y no hay botones de acción por fila", () => {
  const h = html({ column: STANDARD_COLUMN, selectedIds: new Set(["n1"]) });
  expect(h).toContain("Seleccionar Oferta n1");
  expect(h).toContain("checked");
  expect(html({ column: STANDARD_COLUMN })).not.toContain("checked");
});
