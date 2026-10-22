import { expect, test } from "bun:test";
import { attachmentsLabel, summarizeVerification } from "./documents";

test("resume páginas, palabras sin cubrir, recortes y avisos de maquetación", () => {
  const s = summarizeVerification({
    pages: { cv: 2, cover: 1 }, missing_keywords: ["kubernetes", 3], trimmed: ["quitado X"],
    layout: { cv: ["hueco grande"], cover: [] },
  });
  expect(s).toEqual({
    cvPages: 2, coverPages: 1, missingKeywords: ["kubernetes"], layoutSkipped: false,
    layoutWarnings: ["CV: hueco grande"], trimmed: ["quitado X"],
  });
});

test("tolera verificación ausente o con Poppler sin instalar", () => {
  expect(summarizeVerification(null).cvPages).toBeNull();
  expect(summarizeVerification({ layout: "skipped: poppler no instalado" }).layoutSkipped).toBe(true);
});

test("adjuntos: los PDFs preparados mandan; si no, el CV de siempre", () => {
  expect(attachmentsLabel([{ name: "cv.pdf" }, { name: "cover.pdf" }], "CV_SAP.pdf")).toContain("cv.pdf, cover.pdf");
  expect(attachmentsLabel([{ name: "cv.pdf" }], "CV_SAP.pdf")).toBe("CV_SAP.pdf");
  expect(attachmentsLabel([], "CV_SAP.pdf")).toBe("CV_SAP.pdf");
});
