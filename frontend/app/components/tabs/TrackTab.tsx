import { OfferBucketTab, ISOLATED_COLUMN, STANDARD_COLUMN } from "@/app/components/OfferBucketTab";
import type { Application, JobOffer, Track } from "@/lib/types";
import { trackLabel } from "@/lib/ui";
import { t } from "@/lib/i18n";

interface Props {
  track: Track;
  offers: JobOffer[];
  applications: Application[];
  selectedIds: Set<string>;
  onToggleSelected: (id: string) => void;
  onSelectMany: (ids: string[], selected: boolean) => void;
  onSelectOffer: (o: JobOffer) => void;
  onSelectApplication: (a: Application) => void;
}

/** Pestaña de un track de la config: sus ofertas clasificadas, «Nuevas» y «Con candidatura». */
export function TrackTab({ track, offers, ...rest }: Props) {
  const isolated = track.kind === "isolated";
  const label = trackLabel(track);
  return (
    <OfferBucketTab
      {...rest}
      newOffers={offers.filter(o => !o.is_applied)}
      trackedOffers={offers.filter(o => o.is_applied)}
      column={isolated ? ISOLATED_COLUMN : STANDARD_COLUMN}
      showJuniorBadge={!isolated}
      showSalary
      maxAnimationIndex={isolated ? 30 : undefined}
      intro={isolated
        ? t("track.isolated_intro", { label })
        : undefined}
      emptyNew={t("track.empty_new", { label })}
    />
  );
}
