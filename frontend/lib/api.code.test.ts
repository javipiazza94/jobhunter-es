import { afterEach, expect, test } from "bun:test";
import { ApiError, fetchProfile } from "./api";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

function fail(body: unknown, status = 404) {
  globalThis.fetch = (async () => ({ ok: false, status, json: async () => body })) as unknown as typeof fetch;
}

test("ApiError.code sale de {detail, code}", async () => {
  fail({ detail: "Oferta no encontrada", code: "offer_not_found" });
  const err = await fetchProfile().catch(e => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err.code).toBe("offer_not_found");
  expect(err.message).toBe("Oferta no encontrada");
});

test("ApiError.code sale de detail.code y es undefined si no hay", async () => {
  fail({ detail: { message: "No", code: "unknown_track" } });
  expect((await fetchProfile().catch(e => e)).code).toBe("unknown_track");
  fail({ detail: "Sin código" }, 500);
  expect((await fetchProfile().catch(e => e)).code).toBeUndefined();
});
