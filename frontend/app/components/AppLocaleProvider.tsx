"use client";

import type { ReactNode } from "react";
import { LocaleProvider } from "@/lib/i18n";
import { fetchProfile, patchProfile } from "@/lib/api";

/** Guarda el idioma sin borrar el resto de `preferences` (el PATCH sustituye la clave de primer nivel entera). */
export async function saveUiLanguage(locale: string) {
  const profile = await fetchProfile();
  const prefs = (profile as { preferences?: unknown }).preferences;
  const preferences = { ...(prefs && typeof prefs === "object" ? prefs : {}), ui_language: locale };
  return patchProfile({ preferences });
}

/** Idioma de la interfaz: se lee de `preferences.ui_language` del perfil y se guarda ahí al cambiarlo. */
export function AppLocaleProvider({ children }: { children: ReactNode }) {
  return (
    <LocaleProvider
      loadProfileLocale={async () => {
        const profile = await fetchProfile();
        return (profile as { preferences?: { ui_language?: unknown } }).preferences?.ui_language;
      }}
      persist={saveUiLanguage}
    >
      {children}
    </LocaleProvider>
  );
}
