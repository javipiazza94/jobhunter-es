// Lógica pura del asistente de primer arranque y de la pestaña Perfil. Se ejecuta con `bun test`.
import { describe, expect, test } from "bun:test";
import type { MarketSource } from "@/lib/types";
import {
  answersToState,
  searchRuns,
  summarizeRuns,
  addTarget,
  emptyDraft,
  emptyWizardState,
  errorDetail,
  joinList,
  profileToForm,
  formToProfile,
  removeTarget,
  secretStatus,
  setupPrompt,
  splitList,
  suggestedSources,
  toAnswers,
  validateStep,
  type WizardState,
} from "./setup";

const src = (id: string, extra: Partial<MarketSource> = {}): MarketSource => ({
  id, label: id.toUpperCase(), requires_ack: false, default_on: true, ...extra,
});

const MARKETS: Record<string, MarketSource[]> = {
  spain: [src("tecnoempleo"), src("infojobs", { requires_ack: true, default_on: false })],
  remote: [src("tecnoempleo", { label: "Tecnoempleo (remoto)" }), src("linkedin", { requires_ack: true, default_on: false })],
  global: [src("indeed", { default_on: false })],
};

const withTarget = (state: WizardState, title = "Data Engineer"): WizardState => ({
  ...state,
  draft: { ...state.draft, targets: [{ title, keywords: [] }] },
});

describe("borrador", () => {
  test("emptyDraft no trae datos y sí la forma completa", () => {
    const d = emptyDraft();
    expect(d.full_name).toBe("");
    expect(d.targets).toEqual([]);
    expect(d.languages).toEqual([]);
    expect(d.modality).toEqual([]);
    expect(d.eligibility).toEqual({ work_permit_countries: [], needs_sponsorship: null, driving_license: null });
    expect(d.years_experience).toBeNull();
  });

  test("addTarget y removeTarget no mutan el borrador", () => {
    const d = emptyDraft();
    const one = addTarget(d);
    expect(d.targets).toEqual([]);
    expect(one.targets).toEqual([{ title: "", keywords: [] }]);
    const two = addTarget({ ...one, targets: [{ title: "A", keywords: ["x"] }] });
    expect(two.targets.length).toBe(2);
    expect(removeTarget(two, 0).targets).toEqual([{ title: "", keywords: [] }]);
    expect(two.targets.length).toBe(2);
  });
});

describe("listas separadas por comas", () => {
  test("splitList limpia vacíos y duplicados sin distinguir mayúsculas", () => {
    expect(splitList(" Python, sql ,, SQL , Airflow ")).toEqual(["Python", "sql", "Airflow"]);
    expect(splitList("")).toEqual([]);
    expect(joinList(["a", "b"])).toBe("a, b");
  });
});

describe("fuentes sugeridas", () => {
  test("une las de los mercados elegidos sin repetir y respeta default_on", () => {
    const s = suggestedSources(MARKETS, ["spain", "remote"]);
    expect(s.map(x => x.id)).toEqual(["tecnoempleo", "infojobs", "linkedin"]);
    expect(s[0]).toMatchObject({ label: "TECNOEMPLEO", checked: true, requires_ack: false });
  });

  test("las requires_ack salen desmarcadas aunque el catálogo diga default_on", () => {
    const markets = { spain: [src("infojobs", { requires_ack: true, default_on: true })] };
    expect(suggestedSources(markets, ["spain"])[0]).toMatchObject({ requires_ack: true, checked: false });
  });

  test("conserva lo que el usuario ya marcó o desmarcó", () => {
    const s = suggestedSources(MARKETS, ["spain"], { tecnoempleo: false, infojobs: true });
    expect(s.map(x => [x.id, x.checked])).toEqual([["tecnoempleo", false], ["infojobs", true]]);
  });

  test("sin mercados, ninguna fuente; mercados desconocidos se ignoran", () => {
    expect(suggestedSources(MARKETS, [])).toEqual([]);
    expect(suggestedSources(MARKETS, ["mars"])).toEqual([]);
  });
});

describe("validación por paso", () => {
  test("paso 1 siempre vale (subir CV o rellenar a mano)", () => {
    expect(validateStep(1, emptyWizardState())).toEqual([]);
  });

  test("paso 2 exige al menos un objetivo con título", () => {
    const s = emptyWizardState();
    expect(validateStep(2, s)).toEqual(["Añade al menos un objetivo profesional con título."]);
    expect(validateStep(2, withTarget(s, "   "))).toHaveLength(1);
    expect(validateStep(2, withTarget(s))).toEqual([]);
  });

  test("paso 3 exige al menos una fuente marcada", () => {
    const s = { ...withTarget(emptyWizardState()), markets: ["spain"], sources: { tecnoempleo: false } };
    expect(validateStep(3, s, MARKETS)).toEqual(["Elige al menos una fuente de ofertas."]);
    expect(validateStep(3, { ...s, sources: {} }, MARKETS)).toEqual([]);
  });

  test("paso 3: una fuente requires_ack marcada sin aceptar el aviso es un error", () => {
    const s = { ...withTarget(emptyWizardState()), markets: ["spain"], sources: { infojobs: true } };
    expect(validateStep(3, s, MARKETS)).toEqual(["Acepta el aviso de INFOJOBS o desmárcala."]);
    expect(validateStep(3, { ...s, acknowledged: { infojobs: true } }, MARKETS)).toEqual([]);
  });
});

describe("toAnswers", () => {
  test("solo envía las fuentes marcadas y solo las aceptadas como acknowledged", () => {
    const s: WizardState = {
      ...withTarget(emptyWizardState()),
      markets: ["spain", "remote"],
      sources: { infojobs: true, linkedin: false },
      acknowledged: { infojobs: true, linkedin: true },
      followedCompanies: [" Acme Robotics ", "", "Globex Data"],
      cvPath: "cv/cv.pdf",
      ai: { provider: "none", model: null, base_url: null, timeout_seconds: 120 },
    };
    const a = toAnswers(s, MARKETS);
    expect(a.markets).toEqual(["spain", "remote"]);
    expect(a.sources).toEqual(["tecnoempleo", "infojobs"]);
    expect(a.acknowledged_sources).toEqual(["infojobs"]);
    expect(a.followed_companies).toEqual(["Acme Robotics", "Globex Data"]);
    expect(a.cv_path).toBe("cv/cv.pdf");
    expect(a.ai).toEqual({ provider: "none", model: null, base_url: null, timeout_seconds: 120 });
    expect(a.draft.targets).toEqual([{ title: "Data Engineer", keywords: [] }]);
  });

  test("una fuente requires_ack marcada pero sin aceptar no va en acknowledged_sources", () => {
    const s = { ...withTarget(emptyWizardState()), markets: ["spain"], sources: { infojobs: true } };
    expect(toAnswers(s, MARKETS).acknowledged_sources).toEqual([]);
  });
});

describe("secretos", () => {
  test("dice de dónde sale el secreto sin mostrarlo", () => {
    expect(secretStatus(true, "env")).toBe("configurada (variable de entorno)");
    expect(secretStatus(true, "keychain")).toBe("guardada en el llavero");
    expect(secretStatus(false, null)).toBe("no configurada");
  });
});

describe("errores de la API", () => {
  test("usa el detail en texto, une los de validación o cae al código", () => {
    expect(errorDetail({ detail: "Completa primero el asistente" }, 409)).toBe("Completa primero el asistente");
    expect(errorDetail({ detail: [{ msg: "campo obligatorio" }, { msg: "otro" }] }, 422)).toBe("campo obligatorio; otro");
    expect(errorDetail(null, 500)).toBe("Error 500 de la API");
  });
});

describe("perfil guardado ↔ formulario", () => {
  const stored = {
    personal: { name: "Ana Villa", email: "ana@example.com", phone: "600", city: "Villanova", country: "España", linkedin: "x" },
    languages: [{ language: "Inglés", level: "B2" }],
    stack: { other_tools: ["SQL"] },
  };

  test("lee los campos básicos e idiomas", () => {
    const f = profileToForm(stored);
    expect(f).toEqual({
      full_name: "Ana Villa", email: "ana@example.com", phone: "600", city: "Villanova", country: "España",
      languages: [{ language: "Inglés", level: "B2" }],
    });
    expect(profileToForm({}).full_name).toBe("");
  });

  test("escribe sin perder el resto del perfil", () => {
    const f = { ...profileToForm(stored), city: "Puerto Real", languages: [{ language: "Francés", level: "A2" }, { language: " ", level: "B1" }] };
    const out = formToProfile(stored, f);
    expect(out.personal).toMatchObject({ city: "Puerto Real", linkedin: "x", name: "Ana Villa" });
    expect(out.languages).toEqual([{ language: "Francés", level: "A2" }]);
    expect(out.stack).toEqual({ other_tools: ["SQL"] });
    expect(stored.personal.city).toBe("Villanova");
  });
});

describe("volver a ejecutar el asistente", () => {
  test("answersToState marca solo las fuentes activadas (el resto, desmarcadas) y conserva la IA", () => {
    const answers = {
      draft: { ...emptyDraft(), full_name: "Ana Villa" },
      markets: ["spain", "remote"],
      sources: ["tecnoempleo", "infojobs"],
      acknowledged_sources: ["infojobs"],
      followed_companies: ["Acme Robotics"],
      ai: { provider: "anthropic" as const, model: "claude-sonnet-5-5", base_url: null, timeout_seconds: 90 },
      cv_path: "cv/cv.pdf",
    };
    const s = answersToState(answers, MARKETS);
    expect(s.draft.full_name).toBe("Ana Villa");
    expect(s.sources).toEqual({ tecnoempleo: true, infojobs: true, linkedin: false });
    expect(s.acknowledged).toEqual({ infojobs: true });
    expect(s.ai).toEqual(answers.ai);
    expect(s.cvPath).toBe("cv/cv.pdf");
    expect(s.followedCompanies).toEqual(["Acme Robotics"]);
    // y vuelve a dar las mismas respuestas
    const back = toAnswers(s, MARKETS);
    expect(back.sources).toEqual(["tecnoempleo", "infojobs"]);
    expect(back.acknowledged_sources).toEqual(["infojobs"]);
    expect(back.ai).toEqual(answers.ai);
  });

  test("sin ai en las respuestas, se queda la sugerida", () => {
    const s = answersToState({ draft: emptyDraft(), markets: [], sources: [], acknowledged_sources: [], followed_companies: [] }, MARKETS);
    expect(s.ai.provider).toBe("ollama");
  });
});

describe("búsqueda tras el asistente", () => {
  test("un trabajo por track (cubre Tecnoempleo, InfoJobs, Computrabajo y LinkedIn) más Manfred/Indeed si están", () => {
    // Todos los tracks en UN trabajo que los recorre uno detrás de otro: nunca dos navegadores a la vez.
    expect(searchRuns({ tracks: ["data_engineer", "analista"], sources: ["tecnoempleo", "manfred", "infojobs", "computrabajo"] })).toEqual([
      { tracks: ["data_engineer", "analista"] }, { source: "manfred" },
    ]);
    expect(searchRuns({ tracks: [], sources: ["indeed"] })).toEqual([{ source: "indeed" }]);
  });

  test("resume lo que arrancó y lo que no, con el motivo", () => {
    const runs = [{ tracks: ["data_engineer", "analista"] }, { source: "manfred" }];
    expect(summarizeRuns(runs, [{ status: "fulfilled", value: {} }, { status: "rejected", reason: new Error("ya en marcha") }])).toEqual({
      started: ["data_engineer, analista"],
      failed: [{ name: "manfred", message: "ya en marcha" }],
    });
  });
});

describe("arranque del dashboard", () => {
  test("sin perfil: asistente obligatorio; perfil sin jobhunter.yaml: solo aviso; todo listo: nada", () => {
    expect(setupPrompt({ needs_setup: true, has_profile: false, has_config: false })).toBe("wizard");
    expect(setupPrompt({ needs_setup: true, has_profile: false, has_config: true })).toBe("wizard");
    expect(setupPrompt({ needs_setup: false, has_profile: true, has_config: false })).toBe("banner");
    expect(setupPrompt({ needs_setup: false, has_profile: true, has_config: true })).toBe("none");
  });
});
