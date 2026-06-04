import type { ReactElement } from "react";

import { DashboardWidgetFrame } from "./DashboardWidgetFrame";
import { StatusPill, type StatusPillTone } from "./StatusPill";

interface AccountField {
  label: string;
  value: string;
}

/**
 * Vehicle Account Details — a mission-critical operations widget. Shows the
 * repo account/vehicle the operator is currently running (selected from
 * Recoveries or staged as a target): plate, vehicle identity, lender/account,
 * VIN, follow-up status, and recovery instructions. Renders a clear empty
 * state when no account is active so the slot never looks broken.
 */
export function VehicleAccountCard(props: {
  size?: "compact" | "standard" | "expanded";
  hasAccount: boolean;
  plate: string;
  vehicle: string;
  statusLabel: string;
  statusTone: StatusPillTone;
  fields: AccountField[];
  instructions?: string;
}): ReactElement {
  return (
    <DashboardWidgetFrame
      title="Vehicle Account"
      eyebrow="Active recovery target"
      size={props.size}
      meta={<StatusPill label={props.statusLabel} tone={props.statusTone} />}
    >
      {props.hasAccount ? (
        <div className="vehicle-account-card">
          <div className="vehicle-account-card__hero">
            <strong>{props.plate}</strong>
            <span>{props.vehicle}</span>
          </div>

          <div className="vehicle-account-card__grid">
            {props.fields.map((field) => (
              <div key={field.label} className="vehicle-account-card__field">
                <span>{field.label}</span>
                <strong>{field.value}</strong>
              </div>
            ))}
          </div>

          {props.instructions ? (
            <div className="vehicle-account-card__instructions">
              <span>Recovery Instructions</span>
              <p>{props.instructions}</p>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="dashboard-empty-state">
          <strong>No account selected</strong>
          <span>Pick a recovery from the Recoveries screen or stage a target to load its vehicle and account details here.</span>
        </div>
      )}
    </DashboardWidgetFrame>
  );
}
