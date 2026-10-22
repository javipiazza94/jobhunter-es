// Capa mínima de i18n sin dependencias: diccionarios planos `lib/i18n/<lang>.json`, `t()`, `useT()` y proveedor.
// Añadir un idioma = añadir `<lang>.json` y ejecutar `bun run i18n:gen` (sin tocar componentes).
import { createContext, createElement, useCallback, useContext, useEffect, useSyncExternalStore, type ReactNode } from "react";
import { DICTIONARIES, SUPPORTED } from "./languages.generated";

export { SUPPORTED };
export const DEFAULT_LOCALE = "es";
export const STORAGE_KEY = "jh.locale";

type Vars = Record<string, string | number>;

let current = DEFAULT_LOCALE;
const listeners = new Set<() => void>();

export function isSupported(locale: unknown): locale is string {
  return typeof locale === "string" && SUPPORTED.includes(locale);
}

/** Texto de `key` en `locale`; si falta cae a es y, si tampoco está, devuelve la propia clave. */
export function translate(locale: string, key: string, vars?: Vars): string {
  const raw = DICTIONARIES[locale]?.[key] ?? DICTIONARIES[DEFAULT_LOCALE]?.[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole));
}

export function getLocale(): string {
  return current;
}

/** Cambia el idioma activo (no soportados se ignoran) y avisa a los componentes. Solo la elección del usuario
 *  (`remember`, por defecto) se guarda en localStorage; el idioma deducido del navegador o del perfil, no. */
export function setLocale(locale: string, opts: { remember?: boolean } = {}): void {
  if (!isSupported(locale)) return;
  if (locale !== current) {
    current = locale;
    listeners.forEach(l => l());
  }
  if (opts.remember ?? true) {
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, locale);
    } catch { /* almacenamiento bloqueado: el idioma vale solo para esta sesión */ }
  }
  if (typeof document !== "undefined" && document.documentElement) document.documentElement.lang = locale;
}

export function t(key: string, vars?: Vars): string {
  return translate(current, key, vars);
}

/** Soportado por código exacto (`pt-BR`) o por su idioma base (`pt`). */
function matchSupported(code: unknown): string | undefined {
  if (typeof code !== "string") return undefined;
  const lower = code.toLowerCase();
  return SUPPORTED.find(c => c.toLowerCase() === lower) ?? SUPPORTED.find(c => c.toLowerCase() === lower.split("-")[0]);
}

/** Orden de preferencia: perfil guardado, localStorage, idioma del navegador y por último es. */
export function resolveInitialLocale(src: { profile?: unknown; stored?: unknown; nav?: unknown }): string {
  for (const c of [src.profile, src.stored, src.nav]) {
    const found = matchSupported(c);
    if (found) return found;
  }
  return DEFAULT_LOCALE;
}

/** Fecha corta según el idioma activo (cadena vacía si no es una fecha válida). */
export function formatDate(value: string | number | Date, options?: Intl.DateTimeFormatOptions): string {
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(current, { timeZone: "UTC", ...options }).format(d);
}

/** Mensaje de un error de la API: traduce `errors.<code>` (de `err.code` o `err.detail.code`) si existe; si no,
 *  su `message`/`detail` tal cual. */
export function errorMessage(err: unknown): string {
  const e = (err && typeof err === "object" ? err : {}) as { code?: unknown; detail?: unknown; message?: unknown };
  const nested = e.detail && typeof e.detail === "object" ? (e.detail as { code?: unknown; message?: unknown }) : undefined;
  const code = [e.code, nested?.code].find((c): c is string => typeof c === "string" && c !== "");
  const key = code ? `errors.${code}` : "";
  if (key && (key in (DICTIONARIES[current] ?? {}) || key in (DICTIONARIES[DEFAULT_LOCALE] ?? {}))) return t(key);
  const text = [e.message, e.detail, nested?.message].find((m): m is string => typeof m === "string" && m.trim() !== "");
  return text ?? t("errors.unknown");
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

const LocaleContext = createContext<{ setLocale: (l: string) => void }>({ setLocale });

/** Idioma activo (se vuelve a pintar al cambiarlo) y su setter, que además lo guarda en el perfil si hay `persist`. */
export function useLocale() {
  const ctx = useContext(LocaleContext);
  const locale = useSyncExternalStore(subscribe, getLocale, () => DEFAULT_LOCALE);
  return { locale, setLocale: ctx.setLocale };
}

export function useT() {
  const { locale } = useLocale();
  return useCallback((key: string, vars?: Vars) => translate(locale, key, vars), [locale]);
}

type ProviderProps = {
  children: ReactNode;
  /** Idioma guardado en el perfil (`preferences.ui_language`), si ya se conoce. */
  profileLocale?: unknown;
  /** Carga el idioma del perfil si no se pasa `profileLocale` (null/undefined = sin dato). */
  loadProfileLocale?: () => Promise<unknown>;
  /** Guarda el idioma elegido en el perfil. */
  persist?: (locale: string) => Promise<unknown>;
};

let userChose = false;

export function LocaleProvider({ children, profileLocale, loadProfileLocale, persist }: ProviderProps) {
  // Si el usuario elige idioma antes de que llegue el perfil, la carga tardía no debe pisarlo.
  useEffect(() => {
    userChose = false;
    let stored: string | null = null;
    try { stored = globalThis.localStorage?.getItem(STORAGE_KEY) ?? null; } catch { /* ignorar */ }
    const apply = (profile: unknown) => {
      if (userChose) return;
      setLocale(resolveInitialLocale({ profile, stored, nav: globalThis.navigator?.language }), { remember: false });
    };
    apply(profileLocale);
    if (profileLocale === undefined && loadProfileLocale) {
      let cancelled = false;
      loadProfileLocale().then(p => { if (!cancelled) apply(p); }).catch(() => { /* sin perfil: vale lo local */ });
      return () => { cancelled = true; };
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileLocale]);

  const choose = useCallback((locale: string) => {
    userChose = true;
    setLocale(locale);
    try {
      Promise.resolve(persist?.(locale)).catch(() => { /* el idioma ya quedó en localStorage */ });
    } catch { /* persist síncrono que lanza: idem */ }
  }, [persist]);

  return createElement(LocaleContext.Provider, { value: { setLocale: choose } }, children);
}
