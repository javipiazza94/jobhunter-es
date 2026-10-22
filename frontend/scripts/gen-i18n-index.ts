// Genera lib/i18n/languages.generated.ts a partir de los lib/i18n/<lang>.json existentes.
// Añadir un idioma = añadir <lang>.json (con `meta.name`) y ejecutar `bun run i18n:gen` (lo hacen predev/prebuild).
import { readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export function renderIndex(codes: string[]): string {
  const sorted = [...codes].sort((a, b) => (a === "es" ? -1 : b === "es" ? 1 : a.localeCompare(b)));
  const imports = sorted.map(c => `import dict_${c} from "./${c}.json";`).join("\n");
  const entries = sorted.map(c => `  ${c}: dict_${c},`).join("\n");
  return `// GENERADO por scripts/gen-i18n-index.ts: no editar a mano.\n${imports}\n\nexport const DICTIONARIES: Record<string, Record<string, string>> = {\n${entries}\n};\n\nexport const SUPPORTED: string[] = ${JSON.stringify(sorted)};\n`;
}

export function listLanguages(dir: string): string[] {
  return readdirSync(dir).filter(f => /^[a-z]{2,3}\.json$/.test(f)).map(f => f.replace(/\.json$/, ""));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "lib", "i18n");
  writeFileSync(join(dir, "languages.generated.ts"), renderIndex(listLanguages(dir)));
}
