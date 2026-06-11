import { useEffect, type ReactElement, type ReactNode } from "react";

import type { DetectionSeverity } from "../../presentation/detectionSeverity";
import { StatusPill, type StatusPillTone } from "./StatusPill";

/**
 * DetectionActionSheet is the focused action surface that opens when the
 * operator selects a detection card on the dashboard. The dashboard cards
 * themselves stay glance-only so the operator can scan the screen without
 * button noise; clicking a card opens this sheet with the full action
 * menu plus the verification context.
 *
 * Closes on Escape (matching the destination modal and customize panel
 * patterns) and on scrim click. The sheet does not own any data — it is a
 * pure projection of the selected detection plus callback handlers
 * supplied by the host.
 */

export interface DetectionActionSheetAction {
  id: string;
  label: string;
  detail?: string;
  tone?: "primary" | "default" | "danger" | "success";
  disabled?: boolean;
  onClick: () => void;
}

export function DetectionActionSheet(props: {
  open: boolean;
  plate: string;
  vehicle: string;
  meta?: string;
  statusLabel: string;
  statusTone: StatusPillTone;
  severity?: DetectionSeverity;
  snapshot?: ReactNode;
  actions: DetectionActionSheetAction[];
  onClose: () => void;
}): ReactElement | null {
  useEffect(() => {
    if (!props.open) {
      return;
    }
    function handleKey(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.stopPropagation();
        props.onClose();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [props.open, props.onClose]);

  if (!props.open) {
    return null;
  }

  const severityClass = props.severity ? `severity-band severity-band--${props.severity}` : "";

  return (
    <div className="detection-action-sheet__scrim" role="presentation" onClick={props.onClose}>
      <aside
        className={`detection-action-sheet ${severityClass}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="detection-action-sheet-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="detection-action-sheet__header">
          <div className="detection-action-sheet__title-group">
            <span className="detection-action-sheet__eyebrow">Selected detection</span>
            <strong id="detection-action-sheet-title">{props.plate}</strong>
            <span className="detection-action-sheet__vehicle">{props.vehicle}</span>
            {props.meta ? <small>{props.meta}</small> : null}
          </div>
          <div className="detection-action-sheet__title-meta">
            <StatusPill label={props.statusLabel} tone={props.statusTone} />
            <button
              className="detection-action-sheet__close"
              type="button"
              aria-label="Close detection actions"
              onClick={props.onClose}
            >
              ✕
            </button>
          </div>
        </header>

        {props.snapshot ? <div className="detection-action-sheet__snapshot">{props.snapshot}</div> : null}

        <div className="detection-action-sheet__actions">
          {props.actions.map((action) => (
            <button
              key={action.id}
              className={`detection-action-sheet__action detection-action-sheet__action--${action.tone ?? "default"}`}
              type="button"
              disabled={action.disabled}
              onClick={() => {
                action.onClick();
                props.onClose();
              }}
            >
              <strong>{action.label}</strong>
              {action.detail ? <span>{action.detail}</span> : null}
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}
