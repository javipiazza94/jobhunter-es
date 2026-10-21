// La pestaña de un track y la barra de pestañas generadas desde la config. Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { JobOffer, Track } from "@/lib/types";
import { trackTabs } from "@/lib/ui";
import { TrackTab } from "./TrackTab";

const noop = () => {};
const track = (id: string, kind: Track["kind"], label: Record<string, string>): Track => ({ id, kind, label });
const oferta = (id: string, extra: Partial<JobOffer> = {}): JobOffer => ({
  id, title: `Oferta ${id}`, company_name: "ACME", location: "Villanova", relevance_score: 0.7, url: null,
  description: null, cv_profile: null, modality: null, salary_text: null, experience_level: null, contract_type: null,
  source: "tecnoempleo", is_applied: 0, followed_tier: 2, track_tag: "ETL", open_to_junior: null,
  job_kind: null, generic_score: 0.61, review_flags: null, ...extra,
});
const props = { applications: [], selectedIds: new Set<string>(), onToggleSelected: noop, onSelectMany: noop,
  onSelectOffer: noop, onSelectApplication: noop };

test("las pestañas salen de los tracks, en orden, con etiqueta y número de ofertas", () => {
  const tracks = [track("uno", "standard", { es: "Datos" }), track("dos", "isolated", { en: "Bridge" })];
  const tabs = trackTabs(tracks, { uno: [oferta("a"), oferta("b")] });
  expect(tabs).toEqual([
    { id: "track:uno", label: "Datos", count: 2 },
    { id: "track:dos", label: "Bridge", count: 0 },
  ]);
});

test("sin tracks no hay pestañas de track ni textos de SAP o Data Science", () => {
  expect(trackTabs([], {})).toEqual([]);
  const h = renderToStaticMarkup(<TrackTab track={track("x", "standard", { es: "Logística" })} offers={[]} {...props} />);
  expect(h).toContain("Logística");
  expect(h).not.toContain("SAP Public Cloud");
  expect(h).not.toContain("Data Science / IA");
});

test("un track estándar usa tier + etiqueta y uno aislado, afinidad y el aviso de candidaturas", () => {
  const std = renderToStaticMarkup(<TrackTab track={track("a", "standard", { es: "A" })} offers={[oferta("n")]} {...props} />);
  expect(std).toContain("Tier 2");
  expect(std).toContain(">ETL<");
  const iso = renderToStaticMarkup(<TrackTab track={track("b", "isolated", { es: "B" })} offers={[oferta("n")]} {...props} />);
  expect(iso).toContain("0.61");
  expect(iso).toContain("No entran en candidaturas automáticas");
});

test("las ofertas con candidatura van a su tabla y las nuevas a la otra", () => {
  const h = renderToStaticMarkup(<TrackTab track={track("a", "standard", { es: "A" })}
    offers={[oferta("n"), oferta("t", { is_applied: 1 })]} {...props} />);
  expect(h).toContain("1 sin candidatura");
  expect(h).toContain("1 con candidatura");
});
