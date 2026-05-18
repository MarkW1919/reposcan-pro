import type { ReactElement, ReactNode } from "react";

import type { DetectionSeverity } from "../../presentation/detectionSeverity";
import { StatusPill, type StatusPillTone } from "./StatusPill";

/**
 * Glance-only detection card. Clicking the card opens the focused
 * DetectionActionSheet modal that holds the full action menu (Route,
 * Inspect, Copy plate, etc.). Keeps the dashboard scannable by removing
 * inline button clutter; the action surface only renders when the
 * operator commits to a card by tapping it.
 */
export function CompactDetectionCard(props: {
  plate: string;
  vehicle: string;
  color?: string;
  distance?: string;
  confidence: string;
  statusLabel: string;
  statusTone: StatusPillTone;
  severity?: DetectionSeverity;
  active?: boolean;
  snapshot: ReactNode;
  onSelect: () => void;
}): ReactElement {
  const severityClass = props.severity ? `severity-band severity-band--${props.severity}` : "";
  return (
    <article className={`compact-detection-card ${severityClass} ${props.active ? "is-active" : ""}`.trim()}>
      <button
        className="compact-detection-card__body"
        type="button"
        onClick={props.onSelect}
        aria-label={`Open actions for ${props.plate}, ${props.vehicle}`}
      >
        <div className="compact-detection-card__snapshot">{props.snapshot}</div>
        <div className="compact-detection-card__copy">
          <div className="compact-detection-card__headline">
            <strong>{props.plate}</strong>
            <StatusPill label={props.statusLabel} tone={props.statusTone} />
          </div>
          <span>{props.vehicle}</span>
          <small>
            {[props.color, props.distance, props.confidence].filter(Boolean).join(" · ")}
          </small>
        </div>
      </button>
    </article>
  );
}
