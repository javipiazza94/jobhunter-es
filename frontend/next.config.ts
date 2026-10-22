import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // La app de escritorio (desktop/) empaqueta el dashboard como web estática: `JH_DESKTOP_EXPORT=1 next build`
  // deja el resultado en `out/`. Sin la variable, el dashboard web funciona igual que siempre.
  ...(process.env.JH_DESKTOP_EXPORT === "1" ? { output: "export" as const } : {}),
};

export default nextConfig;
