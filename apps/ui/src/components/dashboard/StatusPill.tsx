import type { ReactElement, ReactNode } from "react";

export type StatusPillTone = "cyan" | "green" | "amber" | "red" | "purple" | "gray";

export function StatusPill(props: {
  tone: StatusPillTone;
  label: string;
  detail?: string;
  icon?: ReactNode;
}): ReactElement {
  return (
    <span className={`status-pill status-pill--${props.tone}`}>
      {props.icon ? <span className="status-pill__icon">{props.icon}</span> : null}
      <span className="status-pill__body">
        <strong>{props.label}</strong>
        {props.detail ? <small>{props.detail}</small> : null}
      </span>
    </span>
  );
}
