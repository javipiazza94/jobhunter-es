import { Sparkles, X } from "lucide-react";
import { t, useLocale } from "@/lib/i18n";

export const T = {
  get message() { return t("setup_banner.message"); },
  get open() { return t("setup_banner.open"); },
  get dismiss() { return t("setup_banner.dismiss"); },
};

interface Props {
  onOpen: () => void;
  onDismiss: () => void;
}

/** Aviso para instalaciones con profile.json pero sin jobhunter.yaml propio: el asistente es opcional. */
export function SetupBanner({ onOpen, onDismiss }: Props) {
  useLocale();
  return (
    <div className="mb-6 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200" role="status">
      <div className="flex flex-wrap items-center gap-3">
        <Sparkles className="w-4 h-4 shrink-0" aria-hidden />
        <span className="font-medium flex-1">{T.message}</span>
        <button
          type="button"
          onClick={onOpen}
          className="px-3 py-1.5 rounded-lg bg-indigo-500/20 border border-indigo-500/30 text-indigo-100 hover:bg-indigo-500/30 transition-all"
        >
          {T.open}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          aria-label={T.dismiss}
          title={T.dismiss}
          className="p-1.5 rounded-lg text-indigo-200/70 hover:text-white hover:bg-white/10 transition-all"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
