// Marcado estático del pack de entrevista. Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { InterviewPackPanel, T } from "./InterviewPackPanel";

test("ofrece generarlo", () => {
  expect(renderToStaticMarkup(<InterviewPackPanel applicationId="a1" />)).toContain(T.button);
});

test("muestra el Markdown tal cual (pre, saltos conservados) y dónde se guardó", () => {
  const h = renderToStaticMarkup(
    <InterviewPackPanel applicationId="a1" initialPack={{ path: "applications/acme/interview.md", markdown: "# Acme Robotics\n- <b>pregunta</b>" }} />,
  );
  expect(h).toMatch(/<pre[^>]*whitespace-pre-wrap[^>]*># Acme Robotics\n- &lt;b&gt;pregunta&lt;\/b&gt;<\/pre>/);
  expect(h).toContain(T.savedAt("applications/acme/interview.md"));
});

test("sin IA muestra el mensaje de la API", () => {
  const msg = "IA no disponible: sin proveedor. Configura un proveedor en Perfil.";
  expect(renderToStaticMarkup(<InterviewPackPanel applicationId="a1" initialError={msg} />)).toContain(msg);
});
