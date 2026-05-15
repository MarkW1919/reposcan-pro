import type { ReactElement } from "react";

import { StatusPill, type StatusPillTone } from "./StatusPill";

/**
 * Recovery hit lifecycle states agreed in UI_PRO_GRADE_STRATEGY.md for the
 * single-operator first-deployment scope:
 *
 *  active            -> amber, a matched account needs operator verification
 *  acknowledged      -> cyan,  operator has seen the hit and is verifying or routing
 *  dismissed         -> gray,  the hit is not actionable right now
 *  recovered         -> green, account has been completed after verification
 *  false_positive    -> red,   the read or vehicle match was rejected
 *
 * The API today (DashboardAlertStatus) only carries the first three states.
 * The recovered and false_positive states are operator-derived and may be
 * stored in review_action / follow-up status. This component accepts the
 * superset so callers can supply whichever projection they have.
 */
export type RecoveryState =
  | "active"
  | "acknowledged"
  | "dismissed"
  | "recovered"
  | "false_positive";

const RECOVERY_STATE_TONE: Record<RecoveryState, StatusPillTone> = {
  active: "amber",
  acknowledged: "cyan",
  dismissed: "gray",
  recovered: "green",
  false_positive: "red",
};

const RECOVERY_STATE_LABEL: Record<RecoveryState, string> = {
  active: "Active",
  acknowledged: "Acknowledged",
  dismissed: "Dismissed",
  recovered: "Recovered",
  false_positive: "False Positive",
};

export function RecoveryStatePill(props: {
  state: RecoveryState;
  detail?: string;
}): ReactElement {
  return (
    <StatusPill
      tone={RECOVERY_STATE_TONE[props.state]}
      label={RECOVERY_STATE_LABEL[props.state]}
      detail={props.detail}
    />
  );
}

export function recoveryStateTone(state: RecoveryState): StatusPillTone {
  return RECOVERY_STATE_TONE[state];
}

export function recoveryStateLabel(state: RecoveryState): string {
  return RECOVERY_STATE_LABEL[state];
}
