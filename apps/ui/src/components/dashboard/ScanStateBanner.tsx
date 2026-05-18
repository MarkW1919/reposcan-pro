import type { ReactElement } from "react";

import type { ScanSessionState } from "../../live-api";

/**
 * Peripheral-vision scan state banner. The default scan state pill in the
 * toolbar is too small to read at a glance while driving; this banner sits
 * across the top of the dashboard content area and broadcasts the scan
 * state large enough to register from the corner of the eye.
 *
 * Renders nothing when state is "idle" so the dashboard stays uncluttered
 * outside of active recovery sessions.
 */

interface BannerCopy {
  eyebrow: string;
  label: string;
  detail: string;
  modifier: "approaching" | "active" | "post-scan" | "complete";
}

function bannerCopy(state: ScanSessionState, distanceFeet: number | null): BannerCopy | null {
  if (state === "idle") {
    return null;
  }
  if (state === "approaching_radius") {
    return {
      eyebrow: "Inbound",
      label: "Arming for scan",
      detail:
        distanceFeet !== null && Number.isFinite(distanceFeet)
          ? `${Math.round(distanceFeet)} ft to scan radius`
          : "Approaching the configured scan radius",
      modifier: "approaching",
    };
  }
  if (state === "active_lpr_scan") {
    return {
      eyebrow: "Armed",
      label: "Live LPR scan active",
      detail:
        distanceFeet !== null && Number.isFinite(distanceFeet)
          ? `Inside scan radius · ${Math.round(distanceFeet)} ft from target`
          : "Plate reader running in real time",
      modifier: "active",
    };
  }
  if (state === "post_scan_vehicle_enrichment") {
    return {
      eyebrow: "Reviewing",
      label: "Post-scan vehicle analysis",
      detail: "Make / model / color enrichment in progress on stored frames",
      modifier: "post-scan",
    };
  }
  return {
    eyebrow: "Complete",
    label: "Scan session closed",
    detail: "Latest detections promoted to evidence",
    modifier: "complete",
  };
}

export function ScanStateBanner(props: {
  state: ScanSessionState;
  distanceFeet?: number | null;
  primaryTarget?: string;
}): ReactElement | null {
  const copy = bannerCopy(props.state, props.distanceFeet ?? null);
  if (!copy) {
    return null;
  }
  return (
    <div
      className={`scan-state-banner scan-state-banner--${copy.modifier}`}
      role="status"
      aria-live="polite"
    >
      <span className="scan-state-banner__dot" aria-hidden="true" />
      <div className="scan-state-banner__copy">
        <span className="scan-state-banner__eyebrow">{copy.eyebrow}</span>
        <strong className="scan-state-banner__label">{copy.label}</strong>
      </div>
      <div className="scan-state-banner__meta">
        <span className="scan-state-banner__detail">{copy.detail}</span>
        {props.primaryTarget ? (
          <span className="scan-state-banner__target">
            <span>Target</span>
            <strong>{props.primaryTarget}</strong>
          </span>
        ) : null}
      </div>
    </div>
  );
}
