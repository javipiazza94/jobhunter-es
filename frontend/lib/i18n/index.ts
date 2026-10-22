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

/** Cambia el idioma activo (no soportados se ignoran), lo recuerda en localStorage y avisa a los componentes. */
export function setLocale(locale: string): void {
  if (!isSupported(locale)) return;
  if (locale !== current) {
    current = locale;
    listeners.forEach(l => l());
  }
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, locale);
  } catch { /* almacenamiento bloqueado: el idioma vale solo para esta sesión */ }
  if (typeof document !== "undefined" && document.documentElement) document.documentElement.lang = locale;
}

export function t(key: string, vars?: Vars): string {
  return translate(current, key, vars);
}

/** Orden de preferencia: perfil guardado, localStorage, idioma del navegador y por último es. */
export function resolveInitialLocale(src: { profile?: unknown; stored?: unknown; nav?: unknown }): string {
  const fromNav = typeof src.nav === "string" ? src.nav.toLowerCase().split("-")[0] : undefined;
  for (const c of [src.profile, src.stored, fromNav]) if (isSupported(c)) return c;
  return DEFAULT_LOCALE;
}

/** Fecha corta según el idioma activo (cadena vacía si no es una fecha válida). */
export function formatDate(value: string | number | Date, options?: Intl.DateTimeFormatOptions): string {
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(current, { timeZone: "UTC", ...options }).format(d);
}

/** Mensaje de un error de la API: traduce `errors.<code>` si existe; si no, el `detail` tal cual. */
export function errorMessage(code: string | undefined, detail: string | undefined): string {
  const key = code ? `errors.${code}` : "";
  if (key && (key in DICTIONARIES[current] || key in DICTIONARIES[DEFAULT_LOCALE])) return t(key);
  return detail?.trim() ? detail : t("errors.unknown");
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

const LocaleContext = createContext<{ locale: string; setLocale: (l: string) => void }>({ locale: DEFAULT_LOCALE, setLocale });

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

export function LocaleProvider({ children, profileLocale, loadProfileLocale, persist }: ProviderProps) {
  useEffect(() => {
    let stored: string | null = null;
    try { stored = globalThis.localStorage?.getItem(STORAGE_KEY) ?? null; } catch { /* ignorar */ }
    const apply = (profile: unknown) =>
      setLocale(resolveInitialLocale({ profile, stored, nav: globalThis.navigator?.language }));
    apply(profileLocale);
    if (profileLocale === undefined && loadProfileLocale) {
      let cancelled = false;
      loadProfileLocale().then(p => { if (!cancelled) apply(p); }).catch(() => { /* sin perfil: vale lo local */ });
      return () => { cancelled = true; };
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileLocale]);

  const choose = useCallback((locale: string) => {
    setLocale(locale);
    persist?.(locale).catch(() => { /* el idioma ya quedó en localStorage */ });
  }, [persist]);

  return createElement(LocaleContext.Provider, { value: { locale: current, setLocale: choose } }, children);
}
