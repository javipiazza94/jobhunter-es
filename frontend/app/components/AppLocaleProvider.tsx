"use client";

import type { ReactNode } from "react";
import { LocaleProvider } from "@/lib/i18n";
import { fetchProfile, patchProfile } from "@/lib/api";

/** Idioma de la interfaz: se lee de `preferences.ui_language` del perfil y se guarda ahí al cambiarlo. */
export function AppLocaleProvider({ children }: { children: ReactNode }) {
  return (
    <LocaleProvider
      loadProfileLocale={async () => {
        const profile = await fetchProfile();
        return (profile as { preferences?: { ui_language?: unknown } }).preferences?.ui_language;
      }}
      persist={locale => patchProfile({ preferences: { ui_language: locale } })}
    >
      {children}
    </LocaleProvider>
  );
}
