import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { InboxReport, InboxStatus } from "@/lib/types";
import { InboxBanner } from "./InboxBanner";

const informe = (extra: Partial<InboxReport> = {}): InboxReport => ({
  at: "2026-10-07T12:00:00", files: ["candidaturas_a.txt"], new: 2, updated: 1, doubtful: 0, invalid: 0,
  to_review: 0, error: false, output: "", ...extra,
});
const estado = (extra: Partial<InboxStatus> = {}): InboxStatus => ({ pending: [], last: null, changes: 0, automatic: true, ...extra });
const html = (status: InboxStatus | null, syncing = false) =>
  renderToStaticMarkup(<InboxBanner status={status} syncing={syncing} onSync={() => {}} />);

test("no se muestra sin estado, o si todo está cargado", () => {
  expect(html(null)).toBe("");
  expect(html(estado())).toBe("");
  expect(html(estado({ last: informe() }))).toBe("");
});

test("avisa de los ficheros con filas por revisar, con las dudosas de la última carga", () => {
  const h = html(estado({ pending: [{ name: "a.txt", rows: 3 }, { name: "b.txt", rows: 1 }], last: informe({ doubtful: 2, to_review: 1 }) }));
  expect(h).toContain("2 ficheros con filas por revisar");
  expect(h).toContain("2 dudosas · 1 por revisar");
  expect(h).toContain("Sincronizar ahora");
});

test("singular, y el botón se bloquea mientras sincroniza", () => {
  const h = html(estado({ pending: [{ name: "a.txt", rows: 1 }] }), true);
  expect(h).toContain("1 fichero con filas por revisar");
  expect(h).toContain("Sincronizando");
  expect(h).toContain("disabled");
});

test("si la última carga falló lo dice y ofrece el informe", () => {
  const h = html(estado({ last: informe({ error: true, output: "Traceback..." }) }));
  expect(h).toContain("falló");
  expect(h).toContain("Traceback...");
});
