// Carga tolerante: una petición que falla (o responde con un error JSON de la API) no debe vaciar
// todo el panel. Cada llamada cae a su valor vacío y el nombre de la que falló se acumula.

export interface Failures {
  names: string[];
}

export async function settle<T>(
  name: string,
  call: Promise<unknown>,
  fallback: T,
  failures: Failures,
  valid: (value: unknown) => boolean = Array.isArray,
): Promise<T> {
  try {
    const value = await call;
    if (valid(value)) return value as T;
  } catch {
    // se registra abajo
  }
  failures.names.push(name);
  return fallback;
}

export const isObject = (value: unknown): boolean =>
  typeof value === "object" && value !== null && !Array.isArray(value) && !("detail" in value);

export function failureMessage(names: string[]): string {
  return names.length ? `No se pudo cargar: ${names.join(", ")}. El resto del panel sigue disponible.` : "";
}
