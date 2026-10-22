"use client";

import { useState } from "react";
import { Check, X, FileText, Mail, ExternalLink } from "lucide-react";
import type { DocumentFile, Track } from "@/lib/types";
import { PrepareDocsPanel } from "@/app/components/PrepareDocsPanel";
import { ScreeningPanel } from "@/app/components/ScreeningPanel";
import { attachmentsLabel } from "@/lib/documents";
import { trackBadge } from "@/lib/ui";
import { approveApplication, rejectApplication, updateCoverLetter, markApplicationSentManual, type PendingApplication } from "@/lib/api";

interface PendingCardProps {
  app: PendingApplication;
  tracks: Track[];
  onAction: () => void;
}

export function PendingCard({ app, tracks, onAction }: PendingCardProps) {
  const currentLetter = app.cover_letter_edited ?? app.cover_letter_used ?? "";
  const [body, setBody] = useState(currentLetter);
  const [saved, setSaved] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualSendStarted, setManualSendStarted] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const [files, setFiles] = useState<DocumentFile[]>([]);

  const handleSave = async () => {
    setBusy(true);
    try {
      await updateCoverLetter(app.id, body);
      setSaved(true);
    } finally {
      setBusy(false);
    }
  };

  const handleApprove = async () => {
    setError(null);
    if (!saved) await handleSave();
    setBusy(true);
    try {
      const result = await approveApplication(app.id);
      if (!result.success) {
        setError("Error al enviar. Revisa el límite diario o la conexión SMTP.");
        return;
      }
      onAction();
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    setBusy(true);
    try {
      await rejectApplication(app.id);
      onAction();
    } finally {
      setBusy(false);
    }
  };

  // mailto: only carries to/subject — a full cover letter in the body can push some
  // webmail-registered handlers (e.g. Outlook web) over their URL length limit
  // (AADSTS90015). The body is copied to the clipboard instead, to paste by hand.
  const handleSendManually = async () => {
    setError(null);
    if (!saved) await handleSave();
    try {
      await navigator.clipboard.writeText(body);
      setCopyFeedback("Carta copiada al portapapeles");
    } catch {
      setCopyFeedback("No se pudo copiar automáticamente — cópiala a mano del cuadro de arriba");
    }
    const to = app.contact_value ?? "";
    const subject = app.job_title ? `Candidatura: ${app.job_title}` : `Candidatura — ${app.company_name ?? ""}`;
    const mailto = `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}`;
    window.open(mailto, "_blank");
    setManualSendStarted(true);
  };

  const handleOpenOfferAndTrack = () => {
    setError(null);
    if (app.job_url) window.open(app.job_url, "_blank");
    setManualSendStarted(true);
  };

  const handleConfirmManualSent = async () => {
    setError(null);
    setBusy(true);
    try {
      const result = await markApplicationSentManual(app.id);
      if (!result.success) {
        setError("No se pudo marcar como enviada. Inténtalo de nuevo.");
        return;
      }
      onAction();
    } finally {
      setBusy(false);
      setManualSendStarted(false);
    }
  };

  const badge = trackBadge(app.cv_profile ?? "—", tracks);
  const cvFile = app.cv_file ?? "sin CV";
  const attachments = attachmentsLabel(files, cvFile);
  const hasContact = !!app.contact_value;
  const isEmailContact = hasContact && app.contact_value!.includes("@");

  return (
    <div className="glass-card p-5 space-y-4 hover:border-white/20 transition-all">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-gray-200">{app.company_name ?? "—"}</p>
          <p className="text-sm text-gray-400">{app.job_title ?? "Candidatura espontánea"}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-md font-bold ${badge.className}`}>
            {badge.label}
          </span>
          <span className="text-xs bg-black/40 text-gray-400 border border-white/5 px-2 py-0.5 rounded-md font-mono">
            {cvFile}
          </span>
        </div>
      </div>

      <div className="text-xs text-gray-500 flex items-center gap-1.5 bg-black/20 p-2 rounded-lg border border-white/5 w-fit">
        <FileText className="w-3 h-3 flex-shrink-0" />
        <span className="font-mono truncate">{app.contact_value ?? "—"}</span>
      </div>

      {error && (
        <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Carta de presentación
          </span>
          {!saved && (
            <button
              onClick={handleSave}
              disabled={busy}
              className="text-xs text-indigo-400 hover:text-indigo-300 disabled:opacity-40 font-medium transition-colors"
            >
              Guardar cambios
            </button>
          )}
          {saved && body !== currentLetter && (
            <span className="text-xs text-emerald-400 font-medium">Guardado</span>
          )}
        </div>
        <textarea
          value={body}
          onChange={(e) => { setBody(e.target.value); setSaved(false); }}
          rows={10}
          disabled={busy}
          className="w-full text-xs font-mono text-gray-300 border border-white/10 rounded-xl p-3 resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500/50 bg-[#16161f] disabled:opacity-60 transition-all"
        />
      </div>

      <PrepareDocsPanel applicationId={app.id} onChange={setFiles} />

      <ScreeningPanel applicationId={app.id} />

      {hasContact && !manualSendStarted && (
        <p className="text-xs text-gray-500">
          Al aprobar se adjuntará: <span className="font-mono text-gray-400">{attachments}</span>
        </p>
      )}

      {isEmailContact && !manualSendStarted && (
        <p className="text-xs text-gray-500">
          &quot;Enviar manualmente&quot; copia la carta al portapapeles y abre tu cliente de correo con el
          destinatario y asunto ya rellenos — pega la carta y adjunta{" "}
          <span className="font-mono text-gray-400">{attachments}</span> a mano antes de darle a enviar.
        </p>
      )}

      {!hasContact && !manualSendStarted && (
        <p className="text-xs text-gray-500">
          No se encontró email de contacto para esta empresa — no se puede usar &quot;Aprobar y
          enviar&quot;. Abre la oferta, aplica desde el propio portal (adjuntando{" "}
          <span className="font-mono text-gray-400">{cvFile}</span> y pegando la carta de arriba) y
          luego márcala como enviada.
        </p>
      )}

      {copyFeedback && !manualSendStarted && (
        <p className="text-xs text-emerald-400">{copyFeedback}</p>
      )}

      {manualSendStarted && (
        <div className="text-xs bg-sky-500/10 border border-sky-500/20 rounded-lg px-3 py-2.5 flex items-center justify-between gap-3 flex-wrap">
          <span className="text-sky-300">
            {hasContact
              ? `${copyFeedback} · ¿Ya enviaste el correo a ${app.contact_value}?`
              : "¿Ya aplicaste a esta oferta desde el portal?"}
          </span>
          <div className="flex gap-2 flex-shrink-0">
            <button
              onClick={() => setManualSendStarted(false)}
              disabled={busy}
              className="px-3 py-1 text-xs font-medium text-gray-400 hover:text-gray-200 disabled:opacity-40"
            >
              Todavía no
            </button>
            <button
              onClick={handleConfirmManualSent}
              disabled={busy}
              className="px-3 py-1 text-xs font-semibold bg-sky-600 hover:bg-sky-500 text-white rounded-md disabled:opacity-40"
            >
              {busy ? "Marcando…" : "Sí, marcar como enviada"}
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap justify-end gap-3 pt-2">
        <button
          onClick={handleReject}
          disabled={busy}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-red-400 border border-red-500/20 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-40"
        >
          <X className="w-4 h-4" /> Rechazar
        </button>
        {isEmailContact && (
          <button
            onClick={handleSendManually}
            disabled={busy}
            title="Copia la carta y abre tu cliente de correo — no marca nada como enviado todavía"
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-sky-400 border border-sky-500/20 hover:bg-sky-500/10 rounded-lg transition-colors disabled:opacity-40"
          >
            <Mail className="w-4 h-4" /> Enviar manualmente
          </button>
        )}
        {hasContact ? (
          <button
            onClick={handleApprove}
            disabled={busy}
            className="flex items-center gap-1.5 px-5 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg shadow-[0_0_15px_rgba(99,102,241,0.3)] transition-all disabled:opacity-40"
          >
            <Check className="w-4 h-4" /> {busy ? "Enviando…" : "Aprobar y enviar"}
          </button>
        ) : (
          <button
            onClick={handleOpenOfferAndTrack}
            disabled={busy || !app.job_url}
            title={app.job_url ?? "Sin URL de oferta guardada"}
            className="flex items-center gap-1.5 px-5 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg shadow-[0_0_15px_rgba(99,102,241,0.3)] transition-all disabled:opacity-40"
          >
            <ExternalLink className="w-4 h-4" /> Ver oferta y aplicar
          </button>
        )}
      </div>
    </div>
  );
}
