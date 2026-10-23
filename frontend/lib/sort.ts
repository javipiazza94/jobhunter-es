import type { Application, JobOffer } from "@/lib/types";
import { t } from "@/lib/i18n";

export type ApplicationSortKey = "date" | "company" | "location" | "score";
export type SortDirection = "asc" | "desc";

export const APPLICATION_SORT_LABELS: Record<ApplicationSortKey, string> = {
  get date() { return t("sort.date"); },
  get company() { return t("sort.company"); },
  get location() { return t("sort.location"); },
  get score() { return t("sort.score"); },
};

export type OfferSortKey = "score" | "company" | "title" | "location";

export const OFFER_SORT_LABELS: Record<OfferSortKey, string> = {
  get score() { return t("sort.score"); },
  get company() { return t("sort.company"); },
  get title() { return t("sort.title"); },
  get location() { return t("sort.location"); },
};

/** Dirección con la que arranca cada criterio: texto de la A a la Z, score de mayor a menor. */
export const defaultDirection = (key: ApplicationSortKey | OfferSortKey): SortDirection =>
  key === "company" || key === "location" || key === "title" ? "asc" : "desc";

const text = (v: string | null | undefined) => (v ?? "").trim();

/** Ordena por una clave (vacíos siempre al final) sin mutar la lista. */
function sortBy<T>(list: T[], value: (item: T) => string | number | null, dir: SortDirection): T[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...list].sort((a, b) => {
    const va = value(a), vb = value(b);
    if (va === null && vb === null) return 0;
    if (va === null) return 1;
    if (vb === null) return -1;
    const cmp = typeof va === "string" && typeof vb === "string"
      ? va.localeCompare(vb, "es", { sensitivity: "base" })
      : (va as number) - (vb as number);
    return cmp * sign;
  });
}

export function sortOffers(list: JobOffer[], key: OfferSortKey, dir: SortDirection): JobOffer[] {
  return sortBy(list, (o) => {
    switch (key) {
      case "company": return text(o.company_name) || null;
      case "title": return text(o.title) || null;
      case "location": return text(o.location) || null;
      case "score": return o.relevance_score;
    }
  }, dir);
}

/** Ordena sin mutar la lista; los valores vacíos van siempre al final, sea cual sea la dirección. */
export function sortApplications(list: Application[], key: ApplicationSortKey, dir: SortDirection): Application[] {
  return sortBy(list, (a) => {
    switch (key) {
      case "company": return text(a.company_name) || null;
      case "location": return text(a.offer_location) || null;
      case "score": return a.relevance_score;
      case "date": { const t = a.sent_at ? Date.parse(a.sent_at) : NaN; return Number.isNaN(t) ? null : t; }
    }
  }, dir);
}
