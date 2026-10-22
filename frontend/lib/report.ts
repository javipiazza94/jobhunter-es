// Informe Markdown del Upskill → bloques de datos. Se renderiza como texto de React (nunca HTML): un título, una
// lista o un párrafo con contenido de la IA no puede inyectar marcado. Solo se entiende un subconjunto mínimo.

export type ReportBlock =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "item"; text: string }
  | { kind: "paragraph"; text: string };

export function parseReport(markdown: string): ReportBlock[] {
  const blocks: ReportBlock[] = [];
  for (const raw of markdown.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) blocks.push({ kind: "heading", level: heading[1].length as 1 | 2 | 3, text: heading[2] });
    else if (/^[-*]\s+/.test(line)) blocks.push({ kind: "item", text: line.replace(/^[-*]\s+/, "") });
    else blocks.push({ kind: "paragraph", text: line });
  }
  return blocks;
}

/** Enlace seguro: solo http(s); cualquier otro esquema (javascript:, data:…) no se enlaza. */
export function safeHref(url: string | undefined | null): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

/** Una URL por línea (o separadas por comas/espacios), sin vacíos ni repetidas. */
export function parseSources(text: string): string[] {
  return [...new Set(text.split(/[\s,]+/).map(s => s.trim()).filter(Boolean))];
}
