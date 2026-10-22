// URL base de la API. En la app de escritorio la inyecta Tauri antes de cargar la página
// (window.__JH_API_URL__, con el puerto libre que eligió el backend); en el dashboard web sale de
// NEXT_PUBLIC_API_URL y, si no, del puerto de siempre.
export const DEFAULT_API_URL = "http://localhost:8020";

// Solo se acepta una URL de loopback con puerto: lo inyectado nunca puede apuntar a otro servidor.
const LOOPBACK = /^http:\/\/(127\.0\.0\.1|localhost):\d{2,5}$/;

interface InjectedWindow {
  __JH_API_URL__?: unknown;
}

export function resolveApiBase(
  win: InjectedWindow | undefined = typeof window === "undefined" ? undefined : (window as InjectedWindow),
  envUrl: string | undefined = process.env.NEXT_PUBLIC_API_URL,
): string {
  const injected = win?.__JH_API_URL__;
  if (typeof injected === "string" && LOOPBACK.test(injected.replace(/\/+$/, ""))) return injected.replace(/\/+$/, "");
  return (envUrl || DEFAULT_API_URL).replace(/\/+$/, "");
}

/** ¿Corre dentro de la app de escritorio? (lo marca el script de inicialización de Tauri) */
export function isDesktopApp(win: { __JH_DESKTOP__?: unknown } | undefined = typeof window === "undefined" ? undefined : (window as { __JH_DESKTOP__?: unknown })): boolean {
  return win?.__JH_DESKTOP__ === true;
}
