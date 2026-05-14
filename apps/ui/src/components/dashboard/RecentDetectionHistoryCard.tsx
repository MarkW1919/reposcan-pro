import type { ReactElement } from "react";

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
          <div className="recent-history-card__empty">No recent sightings in the active dashboard context.</div>
        ) : (
          props.items.map((item) => (
            <button key={item.id} className="recent-history-card__row" type="button" onClick={item.onSelect}>
              <div className="recent-history-card__copy">
                <strong>{item.plate}</strong>
                <span>{item.vehicle}</span>
                <small>{[item.time, item.location].filter(Boolean).join("  |  ")}</small>
              </div>
              <StatusPill label={item.statusLabel} tone={item.statusTone} />
            </button>
          ))
        )}
      </div>
    </DashboardWidgetFrame>
  );
}
