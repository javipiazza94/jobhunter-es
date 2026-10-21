import { useCallback, useEffect, useRef, useState } from "react";
import { fetchInboxStatus, syncInbox } from "@/lib/api";
import type { InboxReport, InboxStatus } from "@/lib/types";

const POLL_MS = 30_000;

/**
 * Estado del inbox (lo que Cowork y n8n dejan en backend/inbox/). La API lo carga sola; aquí solo se
 * consulta cada 30 s y, cuando ha cargado algo nuevo, se avisa con `onChanged` para refrescar el panel.
 */
export function useInboxSync(onChanged: (report: InboxReport | null) => void) {
  const [status, setStatus] = useState<InboxStatus | null>(null);
  const [syncing, setSyncing] = useState(false);
  const seenChanges = useRef<number | null>(null);
  const onChangedRef = useRef(onChanged);

  useEffect(() => { onChangedRef.current = onChanged; });

  const apply = useCallback((next: InboxStatus) => {
    // La primera lectura solo fija el punto de partida: no es un cambio.
    if (seenChanges.current !== null && next.changes > seenChanges.current) onChangedRef.current(next.last);
    seenChanges.current = next.changes;
    setStatus(next);
  }, []);

  // API apagada o reiniciándose: se vuelve a intentar en el siguiente ciclo.
  const refresh = useCallback(() => fetchInboxStatus().then(apply).catch(() => {}), [apply]);

  useEffect(() => {
    const id = setInterval(refresh, POLL_MS);
    fetchInboxStatus().then(apply).catch(() => {});
    return () => clearInterval(id);
  }, [refresh, apply]);

  /** «Sincronizar ahora»: no espera al vigilante. */
  const sync = useCallback(async () => {
    setSyncing(true);
    try {
      const report = await syncInbox();
      await refresh();
      if (report && report.new + report.updated > 0) onChangedRef.current(report);
    } finally {
      setSyncing(false);
    }
  }, [refresh]);

  return { status, syncing, sync };
}
