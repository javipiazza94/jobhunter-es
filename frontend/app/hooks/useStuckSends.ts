import { useCallback, useEffect, useState } from "react";
import { fetchApplications, resolveSendingApplication } from "@/lib/api";
import type { Application } from "@/lib/types";

/**
 * Candidaturas atascadas en «enviando»: el email pudo salir sin registrarse. Nunca se reenvían solas; la
 * persona confirma si salió (→ enviada) o no (→ pendiente de nuevo).
 */
export function useStuckSends() {
  const [items, setItems] = useState<Application[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(
    () => fetchApplications("sending").then((rows: Application[]) => { setItems(rows); setFailed(false); }).catch(() => {}),
    [],
  );

  // API apagada o reiniciándose: el banner simplemente no aparece hasta la siguiente carga.
  useEffect(() => { refresh(); }, [refresh]);

  const resolve = useCallback(async (id: string, sent: boolean) => {
    setBusyId(id);
    try {
      await resolveSendingApplication(id, sent);
      await refresh();
    } catch {
      setFailed(true);
    } finally {
      setBusyId(null);
    }
  }, [refresh]);

  return { items, busyId, failed, resolve };
}
