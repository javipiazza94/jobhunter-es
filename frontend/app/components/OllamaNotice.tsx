"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchOllamaStatus } from "@/lib/api";
import { isDesktopApp } from "@/lib/apiBase";
import { t, useLocale } from "@/lib/i18n";
import type { OllamaStatus } from "@/lib/types";

export const T = {
  get missing() { return t("ollama_notice.missing"); },
  get install() { return t("ollama_notice.install"); },
  get stopped() { return t("ollama_notice.stopped"); },
  get noModels() { return t("ollama_notice.no_models"); },
  get recheck() { return t("ollama_notice.recheck"); },
};

export type NoticeKind = "missing" | "stopped" | "noModels" | null;

/** Qué hay que decirle al usuario (null = Ollama está listo). */
export function noticeKind(status: OllamaStatus): NoticeKind {
  if (status.running) return status.models.length === 0 ? "noModels" : null;
  return status.installed ? "stopped" : "missing";
}

/** Solo en la app de escritorio, donde Ollama no viene incluido. No aparece en el dashboard web. */
export function OllamaNotice() {
  useLocale();
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
