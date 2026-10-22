// Marcado estático del panel de evaluación con IA de una oferta. Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { BATCH_SIZE, OfferEvaluationPanel, T, batchSummary, runBatchEvaluation, verdictLabel } from "./OfferEvaluationPanel";
import type { EvaluationBatchItem, EvaluationBatchResult, OfferEvaluation } from "@/lib/types";

const EVAL: OfferEvaluation = {
  offer_id: "o1", verdict: "Strong Fit", score: 78, strengths: ["Python a diario", "<b>SQL</b>"], gaps: ["Kafka"],
  urgency: "urgent", expired: false, evaluated_at: "2026-10-22T10:00:00+00:00", provider: "ollama",
};

test("sin evaluación ofrece evaluar con IA", () => {
  const h = renderToStaticMarkup(<OfferEvaluationPanel offerId="o1" initialEvaluation={null} />);
  expect(h).toContain(T.button);
  expect(h).not.toContain(T.strengths);
});

test("muestra veredicto, nota, puntos fuertes, huecos, urgencia y que no cambia el score", () => {
  const h = renderToStaticMarkup(<OfferEvaluationPanel offerId="o1" initialEvaluation={EVAL} />);
  expect(h).toContain(verdictLabel("Strong Fit"));
  expect(h).toContain("78");
  expect(h).toContain("Python a diario");
  expect(h).toContain("&lt;b&gt;SQL&lt;/b&gt;"); // texto de la IA escapado, nunca HTML
  expect(h).toContain("Kafka");
  expect(h).toContain(T.urgency.urgent);
  expect(h).toContain(T.note);
  expect(h).toContain(T.reevaluate);
});

test("caducada se avisa", () => {
  const h = renderToStaticMarkup(<OfferEvaluationPanel offerId="o1" initialEvaluation={{ ...EVAL, urgency: "expired", expired: true }} />);
  expect(h).toContain(T.urgency.expired);
});

test("sin IA muestra el mensaje de la API", () => {
  const msg = "IA no disponible: La IA está desactivada (proveedor «none»). Configura un proveedor en Perfil.";
  expect(renderToStaticMarkup(<OfferEvaluationPanel offerId="o1" initialEvaluation={null} initialError={msg} />)).toContain(msg);
});

test("veredictos traducidos y desconocidos tal cual", () => {
  expect(verdictLabel("Poor Fit")).toBe(T.verdicts["Poor Fit"]);
  expect(verdictLabel("Otro")).toBe("Otro");
});

test("resumen del lote: evaluadas siempre; pendientes por presupuesto y errores solo si hay", () => {
  expect(batchSummary({ evaluated: 2, skipped: 0, failed: 0 })).toBe(T.bulkEvaluated(2));
  expect(batchSummary({ evaluated: 1, skipped: 3, failed: 1 })).toBe(
    `${T.bulkEvaluated(1)}, ${T.bulkSkipped(3)}, ${T.bulkFailed(1)}`,
  );
});

const item = (offer_id: string, status: EvaluationBatchItem["status"], error: string | null = null): EvaluationBatchItem =>
  ({ offer_id, status, evaluation: status === "evaluated" ? { ...EVAL, offer_id } : null, error });
const result = (results: EvaluationBatchItem[]): EvaluationBatchResult => ({
  results,
  evaluated: results.filter(r => r.status === "evaluated").length,
  skipped: results.filter(r => r.status === "skipped").length,
  failed: results.filter(r => r.status === "error").length,
});

test("lote: quedan seleccionadas las sin presupuesto y con error, y se muestra el primer error", async () => {
  const sent: string[][] = [];
  const out = await runBatchEvaluation(["a", "b", "c", "d", "e"], async ids => {
    sent.push(ids);
    return result([item("a", "evaluated"), item("b", "error", "Error inesperado al guardar (OperationalError)"),
      item("c", "not_found"), item("d", "error", "La IA no pudo evaluar la oferta (AIError)"), item("e", "skipped")]);
  });
  expect(sent).toEqual([["a", "b", "c", "d", "e"]]);
  expect(out.remaining).toEqual(["b", "d", "e"]);
  expect(out.message).toBe(`${batchSummary({ evaluated: 1, skipped: 1, failed: 2 })}. Error inesperado al guardar (OperationalError)`);
});

test("lote: trocea en peticiones de BATCH_SIZE y si una petición falla deja seleccionado lo que falta", async () => {
  const ids = Array.from({ length: BATCH_SIZE * 2 + 1 }, (_, i) => `o${i}`);
  let calls = 0;
  const out = await runBatchEvaluation(ids, async chunk => {
    calls += 1;
    if (calls === 2) throw new Error("IA no disponible: sin proveedor. Configura un proveedor en Perfil.");
    return result(chunk.map(id => item(id, "evaluated")));
  });
  expect(calls).toBe(2);
  expect(out.remaining).toEqual(ids.slice(BATCH_SIZE));
  expect(out.message).toBe(`${T.bulkEvaluated(BATCH_SIZE)}. IA no disponible: sin proveedor. Configura un proveedor en Perfil.`);
});

test("lote: un 409 de entrada solo muestra el mensaje de la API y no suelta nada", async () => {
  const out = await runBatchEvaluation(["a"], async () => { throw new Error("IA no disponible"); });
  expect(out).toEqual({ message: "IA no disponible", remaining: ["a"] });
});
