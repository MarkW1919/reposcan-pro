import type { ReactElement, ReactNode } from "react";

import type { StatusPillTone } from "./StatusPill";

interface InstrumentStatusItem {
  label: string;
  value: string;
  detail?: string;
  tone?: StatusPillTone;
}

interface InstrumentAction {
  label: string;
  onClick: () => void;
  icon?: ReactNode;
}

export function InstrumentStatusBar(props: {
  brand: string;
  subtitle: string;
  primaryTarget: InstrumentStatusItem;
  vehicle: InstrumentStatusItem;
  lastSeen: InstrumentStatusItem;
  recovery: InstrumentStatusItem;
  system: InstrumentStatusItem;
  weather?: InstrumentStatusItem;
  time?: InstrumentStatusItem;
  actions?: InstrumentAction[];
  customizeLabel: string;
  onCustomize: () => void;
}): ReactElement {
  const segments = [props.primaryTarget, props.vehicle, props.lastSeen, props.recovery, props.system, props.weather, props.time].filter(
    (item): item is InstrumentStatusItem => Boolean(item && item.value),
  );

  return (
    <header className="instrument-status-bar">
      <div className="instrument-status-bar__brand">
        <div className="instrument-status-bar__mark">RS</div>
        <div>
          <span className="instrument-status-bar__eyebrow">{props.subtitle}</span>
          <strong>{props.brand}</strong>
        </div>
      </div>

      <div className="instrument-status-bar__segments" aria-label="Active recovery status">
        {segments.map((item) => (
          <div key={`${item.label}-${item.value}`} className={`instrument-status-bar__segment ${item.tone ? `instrument-status-bar__segment--${item.tone}` : ""}`.trim()}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            {item.detail ? <small>{item.detail}</small> : null}
          </div>
        ))}
      </div>

      <div className="instrument-status-bar__actions">
        {props.actions?.map((action) => (
          <button key={action.label} className="instrument-status-bar__icon-button" type="button" onClick={action.onClick} aria-label={action.label}>
            {action.icon ?? action.label.slice(0, 1)}
          </button>
        ))}
        <button className="instrument-status-bar__customize" type="button" onClick={props.onCustomize}>
          <span>{props.customizeLabel}</span>
        </button>
      </div>
    </header>
  );
}
