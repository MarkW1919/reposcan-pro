import type { ReactElement } from "react";

import type { DashboardAlertStatus } from "../../live-api";
import { detectionSeverityForRow, detectionSeverityLabel } from "../../presentation/detectionSeverity";

export interface DetectionFeedItem {
  id: string;
  plate1: string;
  plate2: string;
  camera: string;
  conf: number;
  time: string;
  hotlist: boolean;
  alertStatus?: DashboardAlertStatus;
}

function altReadLabel(plate: string): string {
  return plate.trim() ? plate : "No alternate OCR";
}

interface DetectionFeedRowProps {
  confidenceLabel: (value: number) => string;
  confidenceTone: (value: number) => "high" | "medium" | "low";
  onOpenDetail: () => void;
  onSelect: () => void;
  row: DetectionFeedItem;
  selected: boolean;
}

export function DetectionFeedRow(props: DetectionFeedRowProps): ReactElement {
  const severity = detectionSeverityForRow(props.row);
  const statusLabel = detectionSeverityLabel(props.row);

  return (
    <article className={`detection-feed-row severity-band severity-band--${severity} ${props.selected ? "is-selected" : ""}`} aria-selected={props.selected}>
      <button className="detection-feed-row__body" type="button" onClick={props.onSelect}>
        <div className="detection-feed-row__primary">
          <div className="detection-feed-row__plate-stack">
            <div className="detection-feed-row__plate-line">
              <strong>{props.row.plate1}</strong>
              {props.row.hotlist ? <span className="detection-feed-row__hit-tag">Hot</span> : null}
            </div>
            <span className="detection-feed-row__alt">{altReadLabel(props.row.plate2)}</span>
          </div>
          <div className="detection-feed-row__meta">
            <span>{props.row.camera}</span>
            <span>{props.row.time}</span>
          </div>
        </div>
        <div className="detection-feed-row__signals">
          <span className={`conf-inline conf-inline--${props.confidenceTone(props.row.conf)}`}>{props.confidenceLabel(props.row.conf)}</span>
          <span className={`detection-feed-row__status detection-feed-row__status--${severity}`}>{statusLabel}</span>
        </div>
      </button>
      <button className="detection-feed-row__inspect" type="button" onClick={props.onOpenDetail}>
        Inspect
      </button>
    </article>
  );
}
