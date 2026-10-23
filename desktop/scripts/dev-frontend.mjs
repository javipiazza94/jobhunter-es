// `tauri dev`: levanta el dashboard en modo desarrollo (puerto 3010, como en el resto del proyecto).
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend");
const child = spawn("bun", ["run", "dev"], { cwd: frontend, stdio: "inherit", shell: process.platform === "win32" });
child.on("exit", (code) => process.exit(code ?? 0));
