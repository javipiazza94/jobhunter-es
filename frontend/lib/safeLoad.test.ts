import { expect, test } from "bun:test";
import { failureMessage, isObject, settle, type Failures } from "./safeLoad";

test("una llamada que falla cae a su valor vacío y se registra; las demás siguen", async () => {
  const failures: Failures = { names: [] };
  const [ok, broken, errJson] = await Promise.all([
    settle("ofertas", Promise.resolve([1, 2]), [] as number[], failures),
    settle("candidaturas pendientes", Promise.reject(new Error("500")), [] as number[], failures),
    settle("estadísticas", Promise.resolve({ detail: "boom" }), null, failures, isObject),
  ]);
  expect(ok).toEqual([1, 2]);
  expect(broken).toEqual([]);
  expect(errJson).toBeNull();
  expect(failures.names.sort()).toEqual(["candidaturas pendientes", "estadísticas"]);
});

test("una respuesta que no es lista se trata como fallo", async () => {
  const failures: Failures = { names: [] };
  expect(await settle("x", Promise.resolve({ detail: "no" }), [], failures)).toEqual([]);
  expect(failures.names).toEqual(["x"]);
});

test("el mensaje es corto y vacío si todo fue bien", () => {
  expect(failureMessage([])).toBe("");
  expect(failureMessage(["a", "b"])).toContain("a, b");
});
