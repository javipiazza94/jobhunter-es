import type { InboxStatus } from "@/lib/types";
import { t, useLocale } from "@/lib/i18n";

interface Props {
  status: InboxStatus | null;
  syncing: boolean;
  onSync: () => void;
}

/**
 * Aviso del inbox: solo aparece si queda un fichero (filas dudosas o comentarios «A REVISAR» que la API no
 * carga sola) o si la última carga falló. No cuenta filas: las ya cargadas pueden seguir en el fichero.
 */
export function InboxBanner({ status, syncing, onSync }: Props) {
  useLocale();
  if (!status) return null;
  const { pending, last } = status;
  if (pending.length === 0 && !last?.error) return null;

  return (
    <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200" role="status">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-medium">
          {last?.error
            ? t("inbox.failed")
            : pending.length === 1
            ? t("inbox.pending_files_one")
            : t("inbox.pending_files_other", { count: pending.length })}
        </span>
        {last && !last.error && (last.doubtful > 0 || last.to_review > 0) && (
          <span className="text-amber-200/80">
            {t("inbox.counts", { doubtful: last.doubtful, to_review: last.to_review })}
          </span>
        )}
        <button
          onClick={onSync}
          disabled={syncing}
          className="ml-auto rounded-lg border border-amber-500/40 px-3 py-1 font-medium hover:bg-amber-500/20 disabled:opacity-40"
        >
          {syncing ? t("inbox.syncing") : t("inbox.sync_now")}
        </button>
      </div>
      {last?.output && (
        <details className="mt-2">
          <summary className="cursor-pointer text-amber-200/80">{t("inbox.view_report")}</summary>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 text-xs text-gray-300">{last.output}</pre>
        </details>
      )}
    </div>
  );
}
