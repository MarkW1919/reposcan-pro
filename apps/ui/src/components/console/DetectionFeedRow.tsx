import type { ReactElement } from "react";

import type { DashboardAlertStatus } from "../../live-api";
import { detectionSeverityForRow, detectionSeverityLabel } from "../../presentation/detectionSeverity";

export interface DetectionFeedItem {
  id: string;
  plate1: string;
  plate2: string;
  camera: string;
  direction?: string;
  conf: number;
  gps?: string;
  time: string;
  hotlist: boolean;
  alertStatus?: DashboardAlertStatus;
  vehicle?: string;
}

function altReadLabel(plate: string): string {
  return plate.trim() ? plate : "No alternate OCR";
}

interface DetectionFeedRowProps {
  confidenceLabel: (value: number) => string;
  confidenceTone: (value: number) => "high" | "medium" | "low";
  onCopyPlate?: () => void;
  onOpenDetail: () => void;
  onRouteToDetection?: () => void;
  onSelect: () => void;
  row: DetectionFeedItem;
  selected: boolean;
}

export function DetectionFeedRow(props: DetectionFeedRowProps): ReactElement {
  const severity = detectionSeverityForRow(props.row);
  const statusLabel = detectionSeverityLabel(props.row);

  return (
    <article className={`detection-feed-row severity-band severity-band--${severity} ${props.selected ? "is-selected" : ""}`} aria-current={props.selected ? "true" : undefined}>
      <button className="detection-feed-row__body" type="button" onClick={props.onSelect}>
        <div className="detection-feed-row__primary">
          <div className="detection-feed-row__plate-stack">
            <div className="detection-feed-row__plate-line">
              <strong>{props.row.plate1}</strong>
              {props.row.hotlist ? <span className="detection-feed-row__hit-tag">Hot</span> : null}
            </div>
            <span className="detection-feed-row__alt">{altReadLabel(props.row.plate2)}</span>
            {props.row.vehicle ? <span className="detection-feed-row__vehicle">{props.row.vehicle}</span> : null}
          </div>
          <div className="detection-feed-row__meta">
            <span>{props.row.camera}</span>
            <span>{props.row.time}</span>
            {props.row.direction ? <span>{props.row.direction}</span> : null}
          </div>
        </div>
        <div className="detection-feed-row__signals">
          <span className={`conf-inline conf-inline--${props.confidenceTone(props.row.conf)}`}>{props.confidenceLabel(props.row.conf)}</span>
          <span className={`detection-feed-row__status detection-feed-row__status--${severity}`}>{statusLabel}</span>
          {props.row.gps ? <span className="detection-feed-row__gps">{props.row.gps}</span> : null}
        </div>
      </button>
      <div className="detection-feed-row__actions">
        {props.onRouteToDetection ? (
          <button className="detection-feed-row__quick-action detection-feed-row__quick-action--primary" type="button" onClick={props.onRouteToDetection}>
            Route
          </button>
        ) : null}
        {props.onCopyPlate ? (
          <button className="detection-feed-row__quick-action" type="button" onClick={props.onCopyPlate}>
            Copy
          </button>
        ) : null}
        <button className="detection-feed-row__inspect" type="button" onClick={props.onOpenDetail}>
          Inspect
        </button>
      </div>
    </article>
  );
}
