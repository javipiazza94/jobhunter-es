// Exporta el dashboard como web estática (frontend/out) para empaquetarlo en la app de escritorio.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend");
const run = (args) => {
  const res = spawnSync("bun", args, { cwd: frontend, stdio: "inherit", shell: process.platform === "win32" });
  if (res.status !== 0) process.exit(res.status ?? 1);
};

if (!existsSync(join(frontend, "node_modules"))) run(["install", "--frozen-lockfile"]);
const res = spawnSync("bun", ["run", "build"], {
  cwd: frontend,
  stdio: "inherit",
  shell: process.platform === "win32",
  env: { ...process.env, JH_DESKTOP_EXPORT: "1" },
});
if (res.status !== 0) process.exit(res.status ?? 1);
if (!existsSync(join(frontend, "out", "index.html"))) {
  console.error("El export estático no generó frontend/out/index.html");
  process.exit(1);
}
