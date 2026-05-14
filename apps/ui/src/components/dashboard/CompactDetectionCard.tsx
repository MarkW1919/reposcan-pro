import type { ReactElement, ReactNode } from "react";

import { StatusPill, type StatusPillTone } from "./StatusPill";

export function CompactDetectionCard(props: {
  plate: string;
  vehicle: string;
  color?: string;
  distance?: string;
  confidence: string;
  statusLabel: string;
  statusTone: StatusPillTone;
  active?: boolean;
  snapshot: ReactNode;
  onSelect: () => void;
  onRoute?: () => void;
  onInspect?: () => void;
}): ReactElement {
  return (
    <article className={`compact-detection-card ${props.active ? "is-active" : ""}`.trim()}>
      <button className="compact-detection-card__body" type="button" onClick={props.onSelect}>
        <div className="compact-detection-card__snapshot">{props.snapshot}</div>
        <div className="compact-detection-card__copy">
          <div className="compact-detection-card__headline">
            <strong>{props.plate}</strong>
            <StatusPill label={props.statusLabel} tone={props.statusTone} />
          </div>
          <span>{props.vehicle}</span>
          <small>
            {[props.color, props.distance, props.confidence].filter(Boolean).join("  |  ")}
          </small>
        </div>
      </button>
      <div className="compact-detection-card__actions">
        {props.onRoute ? (
          <button className="compact-detection-card__action compact-detection-card__action--primary" type="button" onClick={props.onRoute}>
            Route
          </button>
        ) : null}
        {props.onInspect ? (
          <button className="compact-detection-card__action" type="button" onClick={props.onInspect}>
            Inspect
          </button>
        ) : null}
      </div>
    </article>
  );
}
