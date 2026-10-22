import type { DocumentFile } from "@/lib/types";

export interface VerificationSummary {
  cvPages: number | null;
  coverPages: number | null;
  missingKeywords: string[];
  layoutSkipped: boolean;
  layoutWarnings: string[];
  trimmed: string[];
}

const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Resumen legible del `verification` de PreparedDocs (campos ausentes o raros se toleran). */
export function summarizeVerification(verification: Record<string, unknown> | null | undefined): VerificationSummary {
  const v = verification ?? {};
  const pages = (v.pages ?? {}) as Record<string, unknown>;
  const layout = v.layout;
  const layoutWarnings: string[] = [];
  if (layout && typeof layout === "object") {
    for (const [doc, value] of Object.entries(layout as Record<string, unknown>)) {
      for (const w of strings(value)) layoutWarnings.push(`${doc === "cv" ? "CV" : "Carta"}: ${w}`);
    }
  }
  return {
    cvPages: num(pages.cv),
    coverPages: num(pages.cover),
    missingKeywords: strings(v.missing_keywords),
    layoutSkipped: typeof layout === "string" && layout.startsWith("skipped"),
    layoutWarnings,
    trimmed: strings(v.trimmed),
  };
}

/** Adjuntos que se enviarán al aprobar: los PDFs preparados si existen; si no, el CV de siempre. */
export function attachmentsLabel(files: Pick<DocumentFile, "name">[], fallbackCv: string): string {
  const names = new Set(files.map(f => f.name));
  if (names.has("cv.pdf") && names.has("cover.pdf")) return "cv.pdf, cover.pdf (preparados para esta oferta)";
  return fallbackCv;
}
