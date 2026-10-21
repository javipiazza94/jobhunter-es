import { useState } from "react";
import type { ApplicationSortKey, SortDirection } from "@/lib/sort";

/** Filtro de estado y orden de la pestaña Candidaturas. */
export function useApplicationFilters() {
  const [applicationStatusFilter, setApplicationStatusFilter] = useState("all");
  const [applicationSortKey, setApplicationSortKey] = useState<ApplicationSortKey>("date");
  const [applicationSortDir, setApplicationSortDir] = useState<SortDirection>("desc");
  return {
    applicationStatusFilter, setApplicationStatusFilter,
    applicationSortKey, setApplicationSortKey, applicationSortDir, setApplicationSortDir,
  };
}

export type ApplicationFilters = ReturnType<typeof useApplicationFilters>;
