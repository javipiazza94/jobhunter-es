import { expect, test } from "bun:test";
import type { Application } from "@/lib/types";
import type { JobOffer } from "@/lib/types";
import { defaultDirection, sortApplications, sortOffers } from "./sort";

const app = (id: string, extra: Partial<Application>): Application => ({
  id, company_name: "X", job_title: null, status: "sent", method: "portal", sent_at: "2026-10-01",
  offer_url: null, offer_source: null, offer_location: null, relevance_score: null, job_offer_id: null, ...extra,
});
const ids = (l: Application[]) => l.map(a => a.id).join(",");

test("empresa A-Z ignora mayúsculas y acentos", () => {
  const l = [app("1", { company_name: "zoi" }), app("2", { company_name: "Ábalos" }), app("3", { company_name: "Baseline" })];
  expect(ids(sortApplications(l, "company", "asc"))).toBe("2,3,1");
  expect(ids(sortApplications(l, "company", "desc"))).toBe("1,3,2");
});

test("fecha: más reciente primero en desc; sin fecha al final en ambos sentidos", () => {
  const l = [app("1", { sent_at: "2026-09-12" }), app("2", { sent_at: "" }), app("3", { sent_at: "2026-10-06" })];
  expect(ids(sortApplications(l, "date", "desc"))).toBe("3,1,2");
  expect(ids(sortApplications(l, "date", "asc"))).toBe("1,3,2");
});

test("score y ubicación: los vacíos van al final y no se muta la lista original", () => {
  const l = [app("1", { relevance_score: null, offer_location: "Villanova" }), app("2", { relevance_score: 0.9, offer_location: null }), app("3", { relevance_score: 0.4, offer_location: "Madrid" })];
  expect(ids(sortApplications(l, "score", "desc"))).toBe("2,3,1");
  expect(ids(sortApplications(l, "score", "asc"))).toBe("3,2,1");
  expect(ids(sortApplications(l, "location", "asc"))).toBe("3,1,2");
  expect(ids(l)).toBe("1,2,3");
});

test("ofertas: título A-Z, score descendente y vacíos al final", () => {
  const o = (id: string, extra: Partial<JobOffer>) => ({ id, title: "T" + id, company_name: null, location: null, relevance_score: 0.5, ...extra }) as JobOffer;
  const l = [o("1", { title: "beta", relevance_score: 0.2 }), o("2", { title: "Alfa", relevance_score: 0.9 }), o("3", { title: "", relevance_score: 0.5 })];
  expect(sortOffers(l, "title", "asc").map(x => x.id).join()).toBe("2,1,3");
  expect(sortOffers(l, "score", "desc").map(x => x.id).join()).toBe("2,3,1");
  expect(sortOffers([o("1", { company_name: "Zoi" }), o("2", { company_name: null }), o("3", { company_name: "Abalos" })], "company", "desc").map(x => x.id).join()).toBe("1,3,2");
});

test("dirección por defecto: texto ascendente, score y fecha descendentes", () => {
  expect(defaultDirection("company")).toBe("asc");
  expect(defaultDirection("title")).toBe("asc");
  expect(defaultDirection("score")).toBe("desc");
  expect(defaultDirection("date")).toBe("desc");
});
