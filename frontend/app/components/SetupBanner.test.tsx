import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { SetupBanner, T } from "./SetupBanner";

test("sugiere el asistente con un botón para abrirlo y otro para descartar el aviso", () => {
  const h = renderToStaticMarkup(<SetupBanner onOpen={() => {}} onDismiss={() => {}} />);
  expect(h).toContain(T.message);
  expect(h).toContain(T.open);
  expect(h).toContain(`aria-label="${T.dismiss}"`);
  expect(T.message).toContain("Configura tu búsqueda con el asistente");
});
