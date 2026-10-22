"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchOllamaStatus } from "@/lib/api";
import { isDesktopApp } from "@/lib/apiBase";
import type { OllamaStatus } from "@/lib/types";

export const T = {
  missing: "No hemos encontrado Ollama en este equipo. Instálalo desde ollama.com o elige otro proveedor de IA en el desplegable de arriba.",
  install: "Descargar Ollama",
  stopped: "Ollama está instalado pero no está en marcha. Ábrelo y pulsa «Comprobar de nuevo».",
  noModels: "Ollama responde pero no tiene ningún modelo descargado. Descarga uno desde la aplicación de Ollama o elige otro proveedor.",
  recheck: "Comprobar de nuevo",
};

export type NoticeKind = "missing" | "stopped" | "noModels" | null;

/** Qué hay que decirle al usuario (null = Ollama está listo). */
export function noticeKind(status: OllamaStatus): NoticeKind {
  if (status.running) return status.models.length === 0 ? "noModels" : null;
  return status.installed ? "stopped" : "missing";
}

/** Solo en la app de escritorio, donde Ollama no viene incluido. No aparece en el dashboard web. */
export function OllamaNotice() {
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const desktop = isDesktopApp();

  const check = useCallback(() => {
    fetchOllamaStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (desktop) check();
  }, [desktop, check]);

  if (!desktop || !status) return null;
  const kind = noticeKind(status);
  if (!kind) return null;
  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200 space-y-2" role="status">
      <p>{T[kind]}</p>
      <div className="flex gap-3">
        {kind === "missing" && (
          <a href={status.install_url} target="_blank" rel="noreferrer" className="underline hover:text-white">{T.install}</a>
        )}
        <button type="button" onClick={check} className="underline hover:text-white">{T.recheck}</button>
      </div>
    </div>
  );
}
