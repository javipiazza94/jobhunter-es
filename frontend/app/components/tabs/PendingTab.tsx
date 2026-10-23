import { Check } from "lucide-react";
import { PendingCard } from "@/app/components/PendingCard";
import type { PendingApplication } from "@/lib/api";
import type { Track } from "@/lib/types";
import { t, useLocale } from "@/lib/i18n";

/** Pestaña «Revisión»: borradores pendientes de aprobar. */
export function PendingTab({ pendingApps, tracks, onAction }: { pendingApps: PendingApplication[]; tracks: Track[]; onAction: () => void }) {
  useLocale();
  return (
    <div className="space-y-6 animate-fade-in">
      {pendingApps.length === 0 ? (
        <div className="glass-card p-16 text-center border-dashed border-white/10">
          <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-4">
            <Check className="w-8 h-8 text-gray-500" />
          </div>
          <h3 className="text-lg font-medium text-gray-300 mb-2">{t("pending.clean_title")}</h3>
          <p className="text-sm text-gray-500">{t("pending.clean_hint")}</p>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-gray-200">{t("pending.review_title")}</h2>
            <span className="text-sm font-mono text-amber-400 bg-amber-400/10 px-3 py-1 rounded-lg border border-amber-400/20">
              {t("pending.waiting_count", { count: pendingApps.length })}
            </span>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            {pendingApps.map((a, idx) => (
              <div key={a.id} className="stagger-row" style={{ animationDelay: `${idx * 0.05}s` }}>
                <PendingCard app={a} tracks={tracks} onAction={onAction} />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
