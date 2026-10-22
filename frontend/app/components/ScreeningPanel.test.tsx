// Marcado estático del panel «Responder preguntas». Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ScreeningPanel, T } from "./ScreeningPanel";

test("ofrece pegar preguntas y responderlas", () => {
  const h = renderToStaticMarkup(<ScreeningPanel applicationId="a1" />);
  expect(h).toContain(T.button);
  expect(h).toContain("<textarea");
});

test("cada respuesta lleva su insignia de origen y copiar; lo que falta avisa sin copiar", () => {
  const h = renderToStaticMarkup(
    <ScreeningPanel
      applicationId="a1"
      initialAnswers={[
        { question: "¿Permiso de trabajo?", answer: "Sí, <UE>.", source: "profile" },
        { question: "Experiencia con datos", answer: "Python y SQL.", source: "ai" },
        { question: "Pretensión salarial", answer: "", source: "needs_input" },
      ]}
    />,
  );
  for (const label of [T.sources.profile, T.sources.ai, T.sources.needs_input]) expect(h).toContain(label);
  expect(h).toContain("Sí, &lt;UE&gt;.");
  expect(h).toContain(T.chars("Sí, <UE>.".length));
  expect(h.match(new RegExp(`>${T.copy}<`, "g"))?.length).toBe(2);
  expect(h).toContain(T.noAnswer);
});

test("muestra el error de la API", () => {
  expect(renderToStaticMarkup(<ScreeningPanel applicationId="a1" initialError="Candidatura no encontrada" />)).toContain("Candidatura no encontrada");
});

test("avisa de la pregunta guardada parecida y de las respuestas recortadas", () => {
  const h = renderToStaticMarkup(
    <ScreeningPanel
      applicationId="a1"
      initialAnswers={[
        { question: "Python", answer: "", source: "needs_input", suggestion: "¿Experiencia con Java?" },
        { question: "Motivo", answer: "Corta.", source: "profile", truncated: true },
      ]}
    />,
  );
  expect(h).toContain("¿Experiencia con Java?");
  expect(h).toContain(T.truncated);
});
