// Render de las pestañas extraídas de page.tsx. Se ejecuta con `bun test` (react-dom/server, sin DOM).
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { Application, Company, Contact, JobOffer, QuietApplication, Track } from "@/lib/types";
import type { ApplicationFilters } from "@/app/hooks/useApplicationFilters";
import type { OfferFilters } from "@/app/hooks/useOfferFilters";
import { ApplicationsTab } from "./ApplicationsTab";
import { CompaniesTab } from "./CompaniesTab";
import { FollowupsTab } from "./FollowupsTab";
import { ContactsTab } from "./ContactsTab";
import { OffersTab } from "./OffersTab";
import { PendingTab } from "./PendingTab";

const noop = () => {};
const oferta = (id: string, extra: Partial<JobOffer> = {}): JobOffer => ({
  id, title: `Oferta ${id}`, company_name: "ACME", location: "Villanova", relevance_score: 0.7, url: null,
  description: null, cv_profile: "alfa", modality: "remoto", salary_text: null, experience_level: null, contract_type: null,
  source: "tecnoempleo", is_applied: 0, followed_tier: null, track_tag: null, open_to_junior: null,
  job_kind: null, generic_score: null, review_flags: null, ...extra,
});
const offerFilters = (extra: Partial<OfferFilters> = {}): OfferFilters => ({
  profileFilter: "all", setProfileFilter: noop, modalityFilter: "all", setModalityFilter: noop, sourceFilter: "all",
  setSourceFilter: noop, experienceFilter: "all", setExperienceFilter: noop, locationSearch: "", setLocationSearch: noop,
  textSearch: "", setTextSearch: noop, minScore: 0, setMinScore: noop, includeApplied: false, setIncludeApplied: noop,
  offersPage: 0, setOffersPage: noop, resetOfferFilters: noop,
  offerSortKey: "score", setOfferSortKey: noop, offerSortDir: "desc", setOfferSortDir: noop, ...extra,
});
const TRACKS: Track[] = [
  { id: "alfa", label: { es: "Alfa ES", en: "Alfa" }, kind: "standard" },
  { id: "beta", label: { en: "Beta EN" }, kind: "standard" },
  { id: "puente", label: { es: "Puente" }, kind: "isolated" },
];
const offersHtml = (offers: JobOffer[], filters = offerFilters(), selected: string[] = []) =>
  renderToStaticMarkup(<OffersTab offers={offers} tracks={TRACKS} filters={filters} selectedIds={new Set(selected)}
    onToggleSelected={noop} onSelectMany={noop} onSelectOffer={noop} />);

test("ofertas: cuenta las visibles, oculta las enviadas por defecto y marca la selección", () => {
  const offers = [oferta("a"), oferta("b", { is_applied: 1 })];
  const h = offersHtml(offers, offerFilters(), ["a"]);
  expect(h).toContain("1 / 2 ofertas");
  expect(h).toContain("Oferta a");
  expect(h).not.toContain("Oferta b");
  expect(h).toContain("checked");
  expect(offersHtml(offers, offerFilters({ includeApplied: true }))).toContain("2 / 2 ofertas");
});

test("ofertas: los filtros por texto, fuente y score recortan la lista", () => {
  const offers = [oferta("a", { title: "Dev Python", relevance_score: 0.9 }), oferta("b", { source: "infojobs", relevance_score: 0.2 })];
  expect(offersHtml(offers, offerFilters({ textSearch: "python" }))).toContain("1 / 2 ofertas");
  expect(offersHtml(offers, offerFilters({ sourceFilter: "infojobs" }))).toContain("Oferta b");
  expect(offersHtml(offers, offerFilters({ minScore: 0.5 }))).not.toContain("Oferta b");
});

test("ofertas: pagina de 100 en 100", () => {
  const muchas = Array.from({ length: 150 }, (_, i) => oferta("m" + i));
  const h = offersHtml(muchas);
  expect(h).toContain("1–100 de 150");
  expect(h).not.toContain("Oferta m120");
  expect(offersHtml(muchas, offerFilters({ offersPage: 1 }))).toContain("Oferta m120");
});

const app = (id: string, extra: Partial<Application> = {}): Application => ({
  id, company_name: "ACME", job_title: `Puesto ${id}`, status: "sent", method: "portal", sent_at: "2026-10-01",
  offer_url: null, offer_source: null, offer_location: null, relevance_score: null, job_offer_id: null, ...extra,
});
const appFilters = (extra: Partial<ApplicationFilters> = {}): ApplicationFilters => ({
  applicationStatusFilter: "all", setApplicationStatusFilter: noop, applicationSortKey: "date", setApplicationSortKey: noop,
  applicationSortDir: "desc", setApplicationSortDir: noop, ...extra,
});
const appsHtml = (apps: Application[], filters = appFilters()) =>
  renderToStaticMarkup(<ApplicationsTab applications={apps} filters={filters} onSelectApplication={noop} />);

test("candidaturas: filtra por estado y ordena por empresa", () => {
  const apps = [app("1", { company_name: "Zoi", status: "rejected" }), app("2", { company_name: "Abalos" })];
  expect(appsHtml(apps)).toContain("2 / 2 candidaturas");
  const sent = appsHtml(apps, appFilters({ applicationStatusFilter: "sent" }));
  expect(sent).toContain("1 / 2 candidaturas");
  expect(sent).not.toContain("Zoi");
  const h = appsHtml(apps, appFilters({ applicationSortKey: "company", applicationSortDir: "asc" }));
  expect(h.indexOf("Abalos")).toBeLessThan(h.indexOf("Zoi"));
});

test("candidaturas: sin datos y sin coincidencias muestran su mensaje", () => {
  expect(appsHtml([])).toContain("Aún no hay candidaturas enviadas");
  expect(appsHtml([app("1")], appFilters({ applicationStatusFilter: "expired" }))).toContain("Ninguna candidatura coincide");
});

test("revisión: bandeja vacía", () => {
  expect(renderToStaticMarkup(<PendingTab pendingApps={[]} tracks={TRACKS} onAction={noop} />)).toContain("Bandeja limpia");
});

test("empresas y contactos: se renderizan con y sin datos", () => {
  const empresa = { id: "c1", name: "Acme Corp", website: "https://acme.test", sector: "IT", city: "Villanova", country: "ES" } as unknown as Company;
  expect(renderToStaticMarkup(<CompaniesTab companies={[empresa]} countryFilter="" onCountryFilterChange={noop} onSelectCompany={noop} />))
    .toContain("Acme Corp");
  const contacto = { id: "k1", company_name: "Acme Corp", type: "email", value: "rrhh@acme.test", offers: [] } as unknown as Contact;
  expect(renderToStaticMarkup(<ContactsTab contacts={[contacto]} onSelectContact={noop} />)).toContain("rrhh@acme.test");
  expect(renderToStaticMarkup(<ContactsTab contacts={[]} onSelectContact={noop} />)).toContain("Contactos");
});

test("empresas: el filtro de país recorta la lista y el desplegable ofrece los países que hay", () => {
  const emp = (id: string, name: string, country: string) => ({ id, name, country, website: "", sector: "IT" }) as unknown as Company;
  const lista = [emp("1", "Acme", "ES"), emp("2", "Globex", "US"), emp("3", "Initech", "DE")];
  const html = (country: string) => renderToStaticMarkup(
    <CompaniesTab companies={lista} countryFilter={country} onCountryFilterChange={noop} onSelectCompany={noop} />);
  const todas = html("");
  expect(todas).toContain("Acme");
  expect(todas).toContain("Globex");
  expect(todas).toContain("Initech");
  expect(todas).toContain(">España<");
  expect(todas).toContain(">DE<");   // un país que antes no se podía elegir
  const us = html("US");
  expect(us).toContain("Globex");
  expect(us).not.toContain("Acme");
  expect(us).not.toContain("Initech");
});

test("ofertas: se pueden ordenar por empresa y el orden se invierte", () => {
  const offers = [oferta("z", { company_name: "Zoi" }), oferta("a", { company_name: "Abalos" })];
  const asc = offersHtml(offers, offerFilters({ offerSortKey: "company", offerSortDir: "asc" }));
  expect(asc.indexOf("Abalos")).toBeLessThan(asc.indexOf("Zoi"));
  const desc = offersHtml(offers, offerFilters({ offerSortKey: "company", offerSortDir: "desc" }));
  expect(desc.indexOf("Zoi")).toBeLessThan(desc.indexOf("Abalos"));
  expect(asc).toContain("Ordenar por");
});

test("ofertas: los avisos de revisión salen como insignia", () => {
  const h = offersHtml([oferta("a", { review_flags: JSON.stringify(["idioma: exige alemán, que no tienes"]) })]);
  expect(h).toContain("⚠ 1 aviso");
  expect(h).toContain("idioma: exige alemán");
});

const silenciosa = (id: string, extra: Partial<QuietApplication> = {}): QuietApplication => ({
  id, status: "sent", method: "email", channel: "email", sent_at: "2026-09-10", cv_profile: "alfa", followup_count: 0,
  last_followup_at: null, days_quiet: 20, company_name: `Empresa ${id}`, job_title: "SAP FI", offer_url: null,
  contact_value: "rrhh@acme.es", contact_type: "email", draft: "Hola", ...extra,
});

test("seguimiento: recordatorios con canal y días, y bloque de sin respuesta solo si hay", () => {
  const h = renderToStaticMarkup(<FollowupsTab followups={[silenciosa("a"), silenciosa("b", { channel: "linkedin" })]} stale={[]} onAction={noop} />);
  expect(h).toContain("Empresa a");
  expect(h).toContain("20 d");
  expect(h).toContain("LinkedIn");
  expect(h).not.toContain("Sin respuesta");
  const h2 = renderToStaticMarkup(<FollowupsTab followups={[]} stale={[silenciosa("c", { days_quiet: 75 })]} onAction={noop} />);
  expect(h2).toContain("Sin respuesta");
  expect(h2).toContain("75 d");
  expect(h2).toContain("Nada que recordar");
});

test("ofertas: el filtro de perfil sale de los tracks estándar de la config", () => {
  const h = offersHtml([oferta("a")]);
  expect(h).toContain('<option value="alfa">Alfa ES</option>');
  expect(h).toContain('<option value="beta">Beta EN</option>');
  expect(h).not.toContain('value="puente"');
  expect(h).toContain('value="manual_review"');
});

test("revisión: la insignia del borrador usa la etiqueta del track", () => {
  const pend = { id: "p1", company_name: "ACME", job_title: "Dev", job_url: null, contact_value: null, contact_type: null,
    cover_letter_used: "x", cover_letter_edited: null, cv_profile: "beta", cv_file: "cv.pdf", method: "email" };
  const h = renderToStaticMarkup(<PendingTab pendingApps={[pend]} tracks={TRACKS} onAction={noop} />);
  expect(h).toContain("Beta EN");
  expect(h).not.toContain(">beta<");
});
