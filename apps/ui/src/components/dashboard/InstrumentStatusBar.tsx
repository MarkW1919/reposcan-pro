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
  active?: boolean;
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
        <span className="instrument-status-bar__eyebrow">{props.subtitle}</span>
        <strong>{props.brand}</strong>
      </div>

      <div className="instrument-status-bar__segments" aria-label="Active recovery status">
        {segments.map((item) => {
          const isHero = item === props.primaryTarget;
          const heroActive = isHero && item.value !== "Standby" && item.value !== "--";
          const classes = [
            "instrument-status-bar__segment",
            isHero ? "instrument-status-bar__segment--hero" : "",
            heroActive ? "instrument-status-bar__segment--hero-active" : "",
            item.tone ? `instrument-status-bar__segment--${item.tone}` : "",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <div key={`${item.label}-${item.value}`} className={classes}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              {item.detail ? <small>{item.detail}</small> : null}
            </div>
          );
        })}
      </div>

      <div className="instrument-status-bar__actions">
        {props.actions?.map((action) => (
          <button
            key={action.label}
            className={`instrument-status-bar__icon-button ${action.active ? "is-active" : ""}`.trim()}
            type="button"
            onClick={action.onClick}
            aria-label={action.label}
            aria-pressed={action.active}
          >
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
