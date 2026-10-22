// Marcado estático del panel de evaluación con IA de una oferta. Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { OfferEvaluationPanel, T, batchSummary, verdictLabel } from "./OfferEvaluationPanel";
import type { OfferEvaluation } from "@/lib/types";

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
