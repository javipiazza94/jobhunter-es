import { expect, test } from "bun:test";
import { noticeKind } from "./OllamaNotice";

const base = { install_url: "https://ollama.com/download" };

test("qué avisar según el estado de Ollama", () => {
  expect(noticeKind({ ...base, installed: false, running: false, models: [] })).toBe("missing");
  expect(noticeKind({ ...base, installed: true, running: false, models: [] })).toBe("stopped");
  expect(noticeKind({ ...base, installed: true, running: true, models: [] })).toBe("noModels");
  expect(noticeKind({ ...base, installed: true, running: true, models: ["llama3.1"] })).toBeNull();
});
