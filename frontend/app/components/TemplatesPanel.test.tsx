import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { T, TemplatesPanel } from "./TemplatesPanel";

const t = (name: string, kind: "cv" | "letter", builtin: boolean, active: boolean) => ({
  name, kind, engine: "latex" as const, builtin, active, main_file: "x", compile_cmd: null, page_limit: null, style_rules: "",
});

test("marca la activa y solo ofrece borrar las propias", () => {
  const html = renderToStaticMarkup(
    <TemplatesPanel autoLoad={false} initial={[t("moderncv-banking", "cv", true, true), t("mia", "cv", false, false), t("cover-cls", "letter", true, true)]} />,
  );
  expect(html).toContain(T.active);
  expect(html).toContain(`${T.remove} mia`);
  expect(html).not.toContain(`${T.remove} moderncv-banking`);
  expect(html).toContain(T.upload);
});
