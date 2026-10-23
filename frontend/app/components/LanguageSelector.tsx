"use client";

import { DICTIONARIES, SUPPORTED } from "@/lib/i18n/languages.generated";
import { useLocale, useT } from "@/lib/i18n";

/** Selector de idioma de la interfaz: lista los idiomas registrados (un `<lang>.json` por idioma). */
export function LanguageSelector() {
  const { locale, setLocale } = useLocale();
  const t = useT();
  return (
    <select
      aria-label={t("language.label")}
      title={t("language.label")}
      value={locale}
      onChange={e => setLocale(e.target.value)}
      className="px-2 py-1.5 text-xs font-medium text-gray-300 bg-white/5 border border-white/10 rounded-lg hover:bg-white/10 transition-all"
    >
      {SUPPORTED.map(code => (
        <option key={code} value={code} className="bg-[#0f0f14] text-gray-200">
          {DICTIONARIES[code]["meta.name"]}
        </option>
      ))}
    </select>
  );
}
