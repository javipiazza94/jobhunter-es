"use client";

import { useState } from "react";
import { GraduationCap, Loader2 } from "lucide-react";
import { generateInterviewPack } from "@/lib/api";
import { t, useLocale } from "@/lib/i18n";
import type { InterviewPack } from "@/lib/types";

// Textos de la interfaz traducidos vía i18n (con getters para retrocompatibilidad).
export const T = {
  get button() { return t("interview_pack.button"); },
  get busy() { return t("interview_pack.busy"); },
  savedAt: (path: string) => t("interview_pack.saved_at", { path }),
};

/** Pack de entrevista de una candidatura (generado con IA en el backend). Si no hay IA configurada, la API
 *  responde 409 y se muestra su mensaje (indica configurar un proveedor en Perfil). */
export function InterviewPackPanel({ applicationId, initialPack = null, initialError = "" }: {
  applicationId: string;
  initialPack?: InterviewPack | null;
  initialError?: string;
}) {
  useLocale();
  const [pack, setPack] = useState<InterviewPack | null>(initialPack);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);

  const generate = async () => {
    setBusy(true);
    setError("");
    try {
      setPack(await generateInterviewPack(applicationId));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <button
        onClick={generate}
        disabled={busy}
        className="inline-flex items-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50"
      >
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <GraduationCap className="w-4 h-4" />}
        {busy ? T.busy : T.button}
      </button>
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      {pack && (
        <div className="space-y-1">
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/30 p-3 text-xs text-gray-200 font-mono">
            {pack.markdown}
          </pre>
          <p className="text-xs text-gray-500 break-all">{T.savedAt(pack.path)}</p>
        </div>
      )}
    </div>
  );
}
