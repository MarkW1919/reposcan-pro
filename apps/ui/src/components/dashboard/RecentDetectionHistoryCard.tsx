import type { ReactElement } from "react";

import type { DetectionSeverity } from "../../presentation/detectionSeverity";
import { DashboardWidgetFrame } from "./DashboardWidgetFrame";
import { StatusPill, type StatusPillTone } from "./StatusPill";

interface HistoryItem {
  id: string;
  plate: string;
  vehicle: string;
  time: string;
  location?: string;
  statusLabel: string;
  statusTone: StatusPillTone;
  severity?: DetectionSeverity;
  onSelect?: () => void;
}

export function RecentDetectionHistoryCard(props: {
  title?: string;
  eyebrow?: string;
  size?: "compact" | "standard" | "expanded";
  items: HistoryItem[];
}): ReactElement {
  return (
    <DashboardWidgetFrame title={props.title ?? "Recent Detection History"} eyebrow={props.eyebrow ?? "Recent sightings"} size={props.size}>
      <div className="recent-history-card">
        {props.items.length === 0 ? (
          <div className="recent-history-card__empty">
            <strong>No recent sightings</strong>
            <span>Past detections will appear here once the LPR pipeline records reads for the active target or session.</span>
          </div>
        ) : (
          props.items.map((item) => {
            const severityClass = item.severity ? `severity-band severity-band--${item.severity}` : "";
            return (
              <button
                key={item.id}
                className={`recent-history-card__row ${severityClass}`.trim()}
                type="button"
                onClick={item.onSelect}
              >
                <div className="recent-history-card__copy">
                  <strong>{item.plate}</strong>
                  <span>{item.vehicle}</span>
                  <small>{[item.time, item.location].filter(Boolean).join(" · ")}</small>
                </div>
                <StatusPill label={item.statusLabel} tone={item.statusTone} />
              </button>
            );
          })
        )}
      </div>
    </DashboardWidgetFrame>
  );
}
