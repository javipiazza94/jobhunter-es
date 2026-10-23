import { afterEach, beforeEach, expect, test } from "bun:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { renderToStaticMarkup } from "react-dom/server";
import { setLocale } from "./index";
import { DICTIONARIES } from "./languages.generated";
import { OffersTab } from "@/app/components/tabs/OffersTab";
import { CompaniesTab } from "@/app/components/tabs/CompaniesTab";
import { ContactsTab } from "@/app/components/tabs/ContactsTab";
import { ApplicationsTab } from "@/app/components/tabs/ApplicationsTab";
import { SetupBanner } from "@/app/components/SetupBanner";
import { InboxBanner } from "@/app/components/InboxBanner";
import type { Application, Company, Contact, JobOffer, Track } from "@/lib/types";

const FRONTEND_ROOT = join(import.meta.dir, "../..");
const APP_DIR = join(FRONTEND_ROOT, "app");

function findTsxFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      results.push(...findTsxFiles(full));
    } else if (entry.endsWith(".tsx") && !entry.endsWith(".test.tsx") && !entry.endsWith(".d.ts")) {
      results.push(full);
    }
  }
  return results;
}

// Símbolos, separadores y nombres propios permitidos en nodos de texto JSX
const ALLOWLIST = new Set([
  "•", "—", "·", "+", "%", "/", ":", "|", "(", ")", "->", "<-", ">", "<", "d", "x", "‹", "›",
  "Tecnoempleo", "InfoJobs", "Manfred", "LinkedIn", "Remotive", "RemoteOK", "Computrabajo",
]);

beforeEach(() => setLocale("es"));
afterEach(() => setLocale("es"));

test("no-hardcoded scan: ningún componente en app/ contiene texto JSX en prosa sin traducir", () => {
  const files = findTsxFiles(APP_DIR);
  expect(files.length).toBeGreaterThan(15);

  const violations: string[] = [];

  for (const file of files) {
    const code = readFileSync(file, "utf8");
    const sf = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

    function walk(node: ts.Node) {
      if (ts.isJsxText(node)) {
        const text = node.text.trim();
        // Si contiene letras alfabéticas y no está en la lista de excepciones
        if (text.length > 0 && !ALLOWLIST.has(text) && /[a-zA-ZáéíóúÁÉÍÓÚñÑ]/.test(text)) {
          const { line } = sf.getLineAndCharacterOfPosition(node.getStart());
          const relPath = file.replace(FRONTEND_ROOT + "/", "");
          violations.push(`${relPath}:${line + 1}: "${text}"`);
        }
      }
      ts.forEachChild(node, walk);
    }

    walk(sf);
  }

  expect(violations).toEqual([]);
});

test("renderizado con locale en: no aparecen cadenas exclusivas en español en los componentes principales", () => {
  setLocale("en");

  const noop = () => {};
  const mockTrack: Track = { id: "dev", label: { es: "Desarrollo", en: "Development" }, kind: "standard" };
  const mockOffer: JobOffer = {
    id: "off-1",
    title: "Senior Engineer",
    company_name: "Acme Corp",
    location: "Madrid",
    relevance_score: 0.85,
    url: "https://example.com/job/1",
    description: "Job details",
    cv_profile: "dev",
    modality: "remoto",
    salary_text: "50k",
    experience_level: "senior",
    contract_type: "indefinido",
    source: "tecnoempleo",
    is_applied: 0,
    followed_tier: null,
    track_tag: null,
    open_to_junior: null,
    job_kind: null,
    generic_score: null,
    review_flags: null,
  };
  const mockCompany: Company = {
    name: "Acme Corp",
    sector: "Tech",
    country: "Spain",
    remote_policy: "remoto",
    offer_count: 5,
    application_count: 1,
    tier: 1,
    website: "https://acme.test",
    careers_url: "https://acme.test/careers",
  };
  const mockContact: Contact = {
    value: "jobs@acme.test",
    type: "email",
    company_name: "Acme Corp",
    company_website: "https://acme.test",
    method: "spontaneous",
    offers: [{ id: "off-1", title: "Senior Engineer", relevance_score: 0.85, location: "Madrid", url: null }],
  };
  const mockApplication: Application = {
    id: "app-1",
    company_name: "Acme Corp",
    job_title: "Senior Engineer",
    job_offer_id: "off-1",
    offer_location: "Madrid",
    offer_source: "tecnoempleo",
    relevance_score: 0.85,
    offer_url: "https://example.com/job/1",
    status: "sent",
    sent_at: "2026-10-20T10:00:00Z",
    method: "email",
    notes: null,
  };

  const dummyFilters = {
    profileFilter: "all",
    setProfileFilter: noop,
    modalityFilter: "all",
    setModalityFilter: noop,
    sourceFilter: "all",
    setSourceFilter: noop,
    experienceFilter: "all",
    setExperienceFilter: noop,
    locationSearch: "",
    setLocationSearch: noop,
    textSearch: "",
    setTextSearch: noop,
    minScore: 0,
    setMinScore: noop,
    includeApplied: false,
    setIncludeApplied: noop,
    offersPage: 0,
    setOffersPage: noop,
    resetOfferFilters: noop,
    offerSortKey: "score" as const,
    setOfferSortKey: noop,
    offerSortDir: "desc" as const,
    setOfferSortDir: noop,
  };

  const offersHtml = renderToStaticMarkup(
    <OffersTab
      offers={[mockOffer]}
      tracks={[mockTrack]}
      filters={dummyFilters}
      selectedIds={new Set()}
      onToggleSelected={noop}
      onSelectMany={noop}
      onSelectOffer={noop}
    />
  );
  expect(offersHtml).toContain("All");
  expect(offersHtml).toContain("Company");
  expect(offersHtml).toContain("Score");
  expect(offersHtml).not.toContain("Todas");
  expect(offersHtml).not.toContain("Empresa");

  const companiesHtml = renderToStaticMarkup(
    <CompaniesTab
      companies={[mockCompany]}
      countryFilter=""
      onCountryFilterChange={noop}
      onSelectCompany={noop}
    />
  );
  expect(companiesHtml).toContain("Company");
  expect(companiesHtml).toContain("Country:");
  expect(companiesHtml).toContain("Applied");
  expect(companiesHtml).not.toContain("País:");
  expect(companiesHtml).not.toContain("Enviadas");

  const contactsHtml = renderToStaticMarkup(
    <ContactsTab contacts={[mockContact]} onSelectContact={noop} />
  );
  expect(contactsHtml).toContain("Contact");
  expect(contactsHtml).toContain("Relevant offers");
  expect(contactsHtml).not.toContain("Contacto");
  expect(contactsHtml).not.toContain("Ofertas relevantes");

  const dummyAppFilters = {
    applicationStatusFilter: "all",
    setApplicationStatusFilter: noop,
    applicationSortKey: "date" as const,
    setApplicationSortKey: noop,
    applicationSortDir: "desc" as const,
    setApplicationSortDir: noop,
  };

  const appsHtml = renderToStaticMarkup(
    <ApplicationsTab
      applications={[mockApplication]}
      filters={dummyAppFilters}
      onSelectApplication={noop}
    />
  );
  expect(appsHtml).toContain("Score / Date");
  expect(appsHtml).not.toContain("Score / Fecha");

  const bannerHtml = renderToStaticMarkup(
    <SetupBanner onOpen={noop} onDismiss={noop} />
  );
  expect(bannerHtml).toContain(DICTIONARIES.en["setup_banner.message"]);
  expect(bannerHtml).not.toContain(DICTIONARIES.es["setup_banner.message"]);

  const inboxHtml = renderToStaticMarkup(
    <InboxBanner
      status={{
        pending: ["file1.yaml"],
        last: { success: true, new: 1, updated: 0, doubtful: 0, to_review: 0, error: null, output: "" },
      }}
      syncing={false}
      onSync={noop}
    />
  );
  expect(inboxHtml).toContain(DICTIONARIES.en["inbox.sync_now"]);
  expect(inboxHtml).not.toContain(DICTIONARIES.es["inbox.sync_now"]);
});
