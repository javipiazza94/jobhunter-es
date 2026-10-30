import type { Application } from "@/lib/types";
import { t, useLocale } from "@/lib/i18n";

interface Props {
  items: Application[];
  busyId: string | null;
  failed: boolean;
  onResolve: (id: string, sent: boolean) => void;
}

/**
 * Aviso de candidaturas atascadas en «enviando»: el proceso murió o falló el registro tras el SMTP, así que el
 * email pudo salir. No se reenvían solas: la persona comprueba su carpeta de enviados y lo confirma aquí.
 */
export function StuckSendBanner({ items, busyId, failed, onResolve }: Props) {
  useLocale();
  if (items.length === 0 && !failed) return null;

  return (
    <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200" role="alert">
      {items.length > 0 && (
        <>
          <p className="font-medium">
            {items.length === 1 ? t("stuck.title_one") : t("stuck.title_other", { count: items.length })}
          </p>
          <p className="mt-1 text-amber-200/80">{t("stuck.hint")}</p>
          <ul className="mt-3 space-y-2">
            {items.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-3">
                <span>
                  <span className="font-medium">{item.company_name}</span>
                  {item.job_title && <span className="text-amber-200/80"> · {item.job_title}</span>}
                </span>
                <span className="ml-auto flex gap-2">
                  <button
                    onClick={() => onResolve(item.id, true)}
                    disabled={busyId === item.id}
                    className="rounded-lg border border-amber-500/40 px-3 py-1 font-medium hover:bg-amber-500/20 disabled:opacity-40"
                  >
                    {t("stuck.sent")}
                  </button>
                  <button
                    onClick={() => onResolve(item.id, false)}
                    disabled={busyId === item.id}
                    className="rounded-lg border border-amber-500/40 px-3 py-1 font-medium hover:bg-amber-500/20 disabled:opacity-40"
                  >
                    {t("stuck.not_sent")}
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {failed && <p className="mt-2 text-red-300">{t("stuck.failed")}</p>}
    </div>
  );
}
