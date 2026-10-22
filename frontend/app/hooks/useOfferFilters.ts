import { useState } from "react";
import type { OfferSortKey, SortDirection } from "@/lib/sort";

/** Filtros y paginación de la pestaña Ofertas. El estado vive en el panel para que sobreviva al cambio de pestaña. */
export function useOfferFilters() {
  const [profileFilter, setProfileFilter] = useState("all");
  const [modalityFilter, setModalityFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [experienceFilter, setExperienceFilter] = useState("all");
  const [locationSearch, setLocationSearch] = useState("");
  const [textSearch, setTextSearch] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [includeApplied, setIncludeApplied] = useState(false);
  const [onlyFollowed, setOnlyFollowed] = useState(false);
  const [offersPage, setOffersPage] = useState(0);
  const [offerSortKey, setOfferSortKey] = useState<OfferSortKey>("score");
  const [offerSortDir, setOfferSortDir] = useState<SortDirection>("desc");

  /** Vacía los filtros de texto/desplegables (no toca score mínimo ni «incluir enviadas»). */
  const resetOfferFilters = () => {
    setTextSearch("");
    setProfileFilter("all");
    setModalityFilter("all");
    setSourceFilter("all");
    setExperienceFilter("all");
    setLocationSearch("");
    setOnlyFollowed(false);
    setOffersPage(0);
  };

  return {
    profileFilter, setProfileFilter, modalityFilter, setModalityFilter, sourceFilter, setSourceFilter,
    experienceFilter, setExperienceFilter, locationSearch, setLocationSearch, textSearch, setTextSearch,
    minScore, setMinScore, includeApplied, setIncludeApplied, onlyFollowed, setOnlyFollowed,
    offersPage, setOffersPage, resetOfferFilters,
    offerSortKey, setOfferSortKey, offerSortDir, setOfferSortDir,
  };
}

export type OfferFilters = ReturnType<typeof useOfferFilters>;
