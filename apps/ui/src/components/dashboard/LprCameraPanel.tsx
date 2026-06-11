import type { ReactElement, ReactNode } from "react";

import { DashboardWidgetFrame } from "./DashboardWidgetFrame";
import { StatusPill, type StatusPillTone } from "./StatusPill";

interface CameraTile {
  id: string;
  label: string;
  statusLabel: string;
  statusTone: StatusPillTone;
  meta?: string;
  feed: ReactNode;
}

export function LprCameraPanel(props: {
  size?: "compact" | "standard" | "expanded";
  tiles: CameraTile[];
}): ReactElement {
  return (
    <DashboardWidgetFrame
      title="LPR Cameras"
      eyebrow="Vehicle camera view"
      size={props.size}
      meta={<StatusPill label={`${props.tiles.filter((tile) => tile.statusTone !== "gray").length}/${props.tiles.length} live`} tone="cyan" />}
    >
      <div className="lpr-camera-panel">
        {props.tiles.slice(0, 2).map((tile) => (
          <section key={tile.id} className="lpr-camera-panel__tile">
            <div className="lpr-camera-panel__tile-header">
              <div>
                <strong>{tile.label}</strong>
                {tile.meta ? <span>{tile.meta}</span> : null}
              </div>
              <StatusPill label={tile.statusLabel} tone={tile.statusTone} />
            </div>
            <div className="lpr-camera-panel__feed">{tile.feed}</div>
          </section>
        ))}
      </div>
    </DashboardWidgetFrame>
  );
}
