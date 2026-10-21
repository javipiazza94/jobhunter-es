// Colores y etiquetas compartidos por las pestañas del dashboard.
import type { JobOffer, Track } from "@/lib/types";

export const STATUS_COLORS: Record<string, string> = {
  sent: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  replied: "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20",
  interview: "bg-green-500/10 text-green-400 border border-green-500/20",
  offer: "bg-emerald-500/15 text-emerald-300 border border-emerald-400/30",
  rejected: "bg-red-500/10 text-red-400 border border-red-500/20",
  pending: "bg-gray-500/10 text-gray-400 border border-gray-500/20",
  withdrawn: "bg-gray-500/10 text-gray-500 border border-gray-500/20",
  expired: "bg-gray-500/10 text-gray-500 border border-gray-500/20",
  no_response: "bg-slate-500/10 text-slate-400 border border-slate-500/20",
};

export const SOURCE_COLORS: Record<string, string> = {
  tecnoempleo: "text-blue-400 bg-blue-400/10",
  indeed: "text-indigo-400 bg-indigo-400/10",
  manfred: "text-emerald-400 bg-emerald-400/10",
  seed: "text-purple-400 bg-purple-400/10",
  linkedin: "text-sky-400 bg-sky-400/10",
  infojobs: "text-orange-400 bg-orange-400/10",
};

export const TIER_BADGE: Record<number, { label: string; className: string }> = {
  1: { label: "Tier 1", className: "bg-fuchsia-500/10 text-fuchsia-400 border border-fuchsia-500/20" },
  2: { label: "Tier 2", className: "bg-sky-500/10 text-sky-400 border border-sky-500/20" },
  3: { label: "Tier 3", className: "bg-gray-500/10 text-gray-300 border border-gray-500/20" },
  4: { label: "Fuera de lista", className: "bg-white/5 text-gray-500 border border-white/10" },
};

/** Colores de las insignias de track: se asignan por posición del track en la config (6 y vuelta a empezar). */
export const TRACK_PALETTE: string[] = [
  "bg-purple-500/10 text-purple-400 border border-purple-500/20",
  "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  "bg-orange-500/10 text-orange-400 border border-orange-500/20",
  "bg-pink-500/10 text-pink-400 border border-pink-500/20",
  "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20",
];

const MANUAL_REVIEW_BADGE = "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20";
const UNKNOWN_BADGE = "bg-white/5 text-gray-400 border border-white/10";

/** Etiqueta visible de un track: la española, la inglesa o el id. */
export function trackLabel(track: Track): string {
  return track.label.es || track.label.en || track.id;
}

/** Texto y color de la insignia de una oferta o borrador clasificado en `trackId` (o en `manual_review`). */
export function trackBadge(trackId: string, tracks: Track[]): { label: string; className: string } {
  if (trackId === "manual_review") return { label: "Revisar", className: MANUAL_REVIEW_BADGE };
  const idx = tracks.findIndex(t => t.id === trackId);
  if (idx < 0) return { label: trackId, className: UNKNOWN_BADGE };
  return { label: trackLabel(tracks[idx]), className: TRACK_PALETTE[idx % TRACK_PALETTE.length] };
}

/** Pestañas de track del dashboard, en el orden de la config, con su número de ofertas. */
export function trackTabs(tracks: Track[], offersByTrack: Record<string, JobOffer[]>) {
  return tracks.map(t => ({ id: `track:${t.id}`, label: trackLabel(t), count: (offersByTrack[t.id] ?? []).length }));
}

export const MODALITY_BADGE: Record<string, string> = {
  remoto: "bg-green-500/10 text-green-400 border border-green-500/20",
  hibrido: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  presencial: "bg-gray-500/10 text-gray-400 border border-gray-500/20",
};

/** Avisos guardados en job_offers.review_flags (JSON) por posting_guard y el filtro de idiomas. */
export function parseReviewFlags(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const flags = JSON.parse(raw);
    return Array.isArray(flags) ? flags.map(String) : [];
  } catch {
    return [];
  }
}
