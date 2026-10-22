import { expect, test } from "bun:test";
import { parseQuestions, savedAnswers, withSavedAnswers } from "./screening";

test("una pregunta por línea, con límite opcional «(max N)»", () => {
  expect(parseQuestions("¿Por qué nosotros? (max 300)\n\n  Experiencia con SQL  \nSalario (máx. 20 caracteres)\n(max 5)")).toEqual([
    { text: "¿Por qué nosotros?", max_chars: 300 },
    { text: "Experiencia con SQL" },
    { text: "Salario", max_chars: 20 },
  ]);
});

test("un número entre paréntesis que no es límite se conserva en la pregunta", () => {
  expect(parseQuestions("Años de experiencia (5+)")).toEqual([{ text: "Años de experiencia (5+)" }]);
});

test("savedAnswers ignora entradas mal formadas", () => {
  expect(savedAnswers({ screening_answers: [{ question: "a", answer: "b" }, { question: 1 }, null, "x"] })).toEqual([{ question: "a", answer: "b" }]);
  expect(savedAnswers({})).toEqual([]);
});

test("withSavedAnswers conserva el resto del perfil y descarta filas sin pregunta", () => {
  const out = withSavedAnswers({ personal: { name: "Ana" } }, [{ question: " P ", answer: " R " }, { question: " ", answer: "x" }]);
  expect(out).toEqual({ personal: { name: "Ana" }, screening_answers: [{ question: "P", answer: "R" }] });
});
