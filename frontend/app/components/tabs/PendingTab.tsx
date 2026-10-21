import { Check } from "lucide-react";
import { PendingCard } from "@/app/components/PendingCard";
import type { PendingApplication } from "@/lib/api";
import type { Track } from "@/lib/types";

/** Pestaña «Revisión»: borradores pendientes de aprobar. */
export function PendingTab({ pendingApps, tracks, onAction }: { pendingApps: PendingApplication[]; tracks: Track[]; onAction: () => void }) {
  return (
    <div className="space-y-6 animate-fade-in">
      {pendingApps.length === 0 ? (
        <div className="glass-card p-16 text-center border-dashed border-white/10">
          <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-4">
            <Check className="w-8 h-8 text-gray-500" />
          </div>
          <h3 className="text-lg font-medium text-gray-300 mb-2">Bandeja limpia</h3>
          <p className="text-sm text-gray-500">Pulsa &quot;Generar borradores&quot; en la barra superior para evaluar nuevas ofertas.</p>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-gray-200">Revisión de Candidaturas</h2>
            <span className="text-sm font-mono text-amber-400 bg-amber-400/10 px-3 py-1 rounded-lg border border-amber-400/20">
              {pendingApps.length} esperando
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
