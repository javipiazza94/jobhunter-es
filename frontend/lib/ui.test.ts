// Etiquetas y colores de los tracks. Se ejecuta con `bun test`.
import { expect, test } from "bun:test";
import type { Track } from "@/lib/types";
import { TRACK_PALETTE, trackBadge, trackLabel } from "./ui";

const track = (id: string, label: Record<string, string>): Track => ({ id, label, kind: "standard" });

test("la etiqueta del track es la española, la inglesa o el id", () => {
  expect(trackLabel(track("a", { es: "Alfa", en: "Alpha" }))).toBe("Alfa");
  expect(trackLabel(track("b", { en: "Beta" }))).toBe("Beta");
  expect(trackLabel(track("c", {}))).toBe("c");
});

test("el color del track depende de su posición y la paleta es de 6", () => {
  expect(TRACK_PALETTE).toHaveLength(6);
  const tracks = Array.from({ length: 7 }, (_, i) => track(`t${i}`, { es: `T${i}` }));
  expect(trackBadge("t0", tracks).className).toBe(TRACK_PALETTE[0]);
  expect(trackBadge("t1", tracks).className).toBe(TRACK_PALETTE[1]);
  expect(trackBadge("t6", tracks).className).toBe(TRACK_PALETTE[0]);
  expect(trackBadge("t1", tracks).label).toBe("T1");
});

test("manual_review y los ids desconocidos tienen insignia propia", () => {
  expect(trackBadge("manual_review", []).label).toBe("Revisar");
  expect(trackBadge("viejo", []).label).toBe("viejo");
  expect(trackBadge("viejo", []).className).not.toBe(TRACK_PALETTE[0]);
});
