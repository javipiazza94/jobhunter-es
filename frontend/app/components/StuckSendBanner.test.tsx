import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { Application } from "@/lib/types";
import { StuckSendBanner } from "./StuckSendBanner";

const candidatura = (extra: Partial<Application> = {}): Application => ({
  id: "app1", company_name: "ACME", job_title: "Python Dev", status: "sending", method: "email", sent_at: "",
  offer_url: null, offer_source: null, offer_location: null, relevance_score: null, job_offer_id: "o1", ...extra,
});
const html = (items: Application[], busyId: string | null = null, failed = false) =>
  renderToStaticMarkup(<StuckSendBanner items={items} busyId={busyId} failed={failed} onResolve={() => {}} />);

test("no se muestra si no hay candidaturas atascadas ni error", () => {
  expect(html([])).toBe("");
});

test("avisa de que el email pudo salir sin registrarse y deja decidir cada candidatura", () => {
  const h = html([candidatura()]);
  expect(h).toContain("1 candidatura quedó en «enviando»");
  expect(h).toContain("ACME");
  expect(h).toContain("Python Dev");
  expect(h).toContain("Sí, salió");
  expect(h).toContain("No salió, volver a pendiente");
});

test("plural con el número de candidaturas", () => {
  const h = html([candidatura(), candidatura({ id: "app2", company_name: "Globex" })]);
  expect(h).toContain("2 candidaturas quedaron en «enviando»");
  expect(h).toContain("Globex");
});

test("mientras se resuelve una, sus botones se bloquean y las demás no", () => {
  const h = html([candidatura(), candidatura({ id: "app2", company_name: "Globex" })], "app1");
  expect(h.match(/disabled=""/g)?.length).toBe(2);
});

test("muestra el error si no se pudo actualizar", () => {
  expect(html([candidatura()], null, true)).toContain("No se pudo actualizar la candidatura");
});
