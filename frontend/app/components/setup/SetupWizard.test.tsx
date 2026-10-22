// Marcado estático de cada paso del asistente con props dadas. Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { MarketSource } from "@/lib/types";
import { emptyWizardState, type WizardState } from "@/lib/setup";
import { AIPicker, SetupWizard, StepCv, StepReview, StepSources, T } from "./SetupWizard";

const MARKETS: Record<string, MarketSource[]> = {
  spain: [
    { id: "tecnoempleo", label: "Tecnoempleo", requires_ack: false, default_on: true },
    { id: "infojobs", label: "InfoJobs", requires_ack: true, default_on: false },
  ],
  global: [{ id: "linkedin", label: "LinkedIn", requires_ack: true, default_on: true }],
};

const noop = () => {};
const state = (extra: Partial<WizardState> = {}): WizardState => ({ ...emptyWizardState(), ...extra });

/** Atributos de un <input> localizado por su `name`. */
const inputTag = (html: string, name: string) => html.match(new RegExp(`<input[^>]*name="${name}"[^>]*>`))?.[0] ?? "";

test("paso 1: subir CV (PDF/DOCX), pegar texto o rellenar a mano", () => {
  const h = renderToStaticMarkup(<StepCv busy={false} onUpload={noop} onPaste={noop} onManual={noop} />);
  expect(h).toContain(T.cvUpload);
  expect(h).toContain('accept=".pdf,.docx');
  expect(h).toContain(T.manual);
  expect(h).toContain(T.pasteButton);
});

test("paso 1 ocupado: el botón dice que está leyendo y la subida se bloquea", () => {
  const h = renderToStaticMarkup(<StepCv busy onUpload={noop} onPaste={noop} onManual={noop} />);
  expect(h).toContain(T.cvUploading);
  expect(h).toMatch(/<input type="file"[^>]*disabled=""/);
});

test("paso 2: muestra el borrador editable con niveles MCER, modalidad y elegibilidad", () => {
  const draft = {
    ...emptyWizardState().draft,
    full_name: "Ana Villa",
    city: "Villanova",
    targets: [{ title: "Data Engineer", keywords: ["Spark", "Airflow"] }],
    tools: ["Python", "SQL"],
    languages: [{ language: "Inglés", level: "C1" as const }],
    modality: ["remote" as const],
    eligibility: { work_permit_countries: ["España"], needs_sponsorship: false, driving_license: null },
  };
  const h = renderToStaticMarkup(<StepReview draft={draft} onChange={noop} />);
  expect(h).toContain('value="Ana Villa"');
  expect(h).toContain('value="Villanova"');
  expect(h).toContain('value="Data Engineer"');
  expect(h).toContain('value="Spark, Airflow"');
  expect(h).toContain('value="Python, SQL"');
  expect(h).toContain('<option value="C1" selected="">C1</option>');
  expect(h).toContain(">Nativo</option>");
  expect(h).toMatch(/<input type="checkbox" checked=""\/>Remoto/);
  expect(h).toContain('value="España"');
  expect(h).toContain('<option value="no" selected="">');
  expect(h).toContain(T.sponsorship);
  expect(h).toContain(T.drivingLicense);
});

test("paso 1: selector de IA con modelo; la clave solo para anthropic/openai y nunca prellenada", () => {
  const ai = { provider: "ollama" as const, model: "llama3.1", base_url: null, timeout_seconds: 120 };
  const h = renderToStaticMarkup(<AIPicker ai={ai} keyStatus={null} keyBusy={false} onChange={noop} onSaveKey={noop} />);
  expect(h).toContain('<option value="ollama" selected="">');
  expect(h).toContain('value="llama3.1"');
  expect(h).not.toContain('type="password"');
  const k = renderToStaticMarkup(
    <AIPicker ai={{ ...ai, provider: "anthropic", model: null }} keyStatus="guardada en el llavero" keyBusy={false} onChange={noop} onSaveKey={noop} />,
  );
  expect(k).toMatch(/<input id="w-ai-key" type="password" autoComplete="new-password"[^>]*value=""/);
  expect(k).toContain(T.aiKeySave);
  expect(k).toContain(T.aiKeyStatus("guardada en el llavero"));
});

test("paso 1 dentro del asistente incluye el selector de IA", () => {
  const h = renderToStaticMarkup(<SetupWizard initialMarkets={MARKETS} onDone={noop} />);
  expect(h).toContain(T.ai);
  expect(h).toContain('role="dialog"');
  expect(h).toContain('aria-modal="true"');
  expect(h).toContain('aria-labelledby="setup-wizard-title"');
  expect(h).toContain('aria-current="step"');
  expect(h).toContain(`<span class="sr-only">${T.stepOf(1)}`);
});

test("al reabrirlo (prefill) avisa de que carga la configuración actual y bloquea el paso 1", () => {
  const h = renderToStaticMarkup(<SetupWizard prefill initialMarkets={MARKETS} onDone={noop} onCancel={noop} />);
  expect(h).toContain(T.loadingCurrent);
  expect(h).toMatch(/<input type="file"[^>]*disabled=""/);
});

test("paso 3: las fuentes requires_ack salen desmarcadas, con aviso y casilla de aceptación propia", () => {
  const h = renderToStaticMarkup(<StepSources state={state({ markets: ["spain", "global"] })} markets={MARKETS} onChange={noop} />);
  expect(inputTag(h, "source-tecnoempleo")).toContain('checked=""');
  for (const [id, label] of [["infojobs", "InfoJobs"], ["linkedin", "LinkedIn"]]) {
    expect(inputTag(h, `source-${id}`)).not.toContain("checked");
    expect(inputTag(h, `ack-${id}`)).not.toContain("checked");
    expect(h).toContain(T.ackWarning(label));
    expect(h).toContain(T.ackCheckbox(label));
  }
  expect(inputTag(h, "ack-tecnoempleo")).toBe("");
  expect(inputTag(h, "ack-infojobs")).toContain('aria-describedby="warn-infojobs"');
  expect(inputTag(h, "source-infojobs")).toContain('aria-describedby="warn-infojobs"');
  expect(h).toContain('id="warn-infojobs"');
  expect(h).toContain(T.followed);
});

test("paso 3: la aceptación marcada se refleja en su casilla", () => {
  const s = state({ markets: ["spain"], sources: { infojobs: true }, acknowledged: { infojobs: true } });
  const h = renderToStaticMarkup(<StepSources state={s} markets={MARKETS} onChange={noop} />);
  expect(inputTag(h, "source-infojobs")).toContain('checked=""');
  expect(inputTag(h, "ack-infojobs")).toContain('checked=""');
});

test("paso 3 sin mercados lo explica", () => {
  const h = renderToStaticMarkup(<StepSources state={state()} markets={MARKETS} onChange={noop} />);
  expect(h).toContain(T.noSources);
});

test("el asistente completo: paso 3 con «Buscar ofertas»; solo se puede cerrar si se reabre desde Perfil", () => {
  const first = renderToStaticMarkup(
    <SetupWizard initialStep={3} initialState={state({ markets: ["spain"] })} initialMarkets={MARKETS} onDone={noop} />,
  );
  expect(first).toContain(T.stepOf(3));
  expect(first).toContain(T.finish);
  expect(first).not.toContain(T.close);
  const again = renderToStaticMarkup(<SetupWizard initialMarkets={MARKETS} onDone={noop} onCancel={noop} />);
  expect(again).toContain(T.stepNames[1]);
  expect(again).toContain(T.close);
});
