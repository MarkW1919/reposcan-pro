import type { ReactElement, ReactNode } from "react";

export function DashboardWidgetFrame(props: {
  title: string;
  eyebrow?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  size?: "compact" | "standard" | "expanded";
  className?: string;
  children: ReactNode;
}): ReactElement {
  return (
    <section className={`dashboard-widget dashboard-widget--${props.size ?? "standard"} ${props.className ?? ""}`.trim()}>
      <header className="dashboard-widget__header">
        <div className="dashboard-widget__title-group">
          {props.eyebrow ? <span className="dashboard-widget__eyebrow">{props.eyebrow}</span> : null}
          <div className="dashboard-widget__title-row">
            <h3>{props.title}</h3>
            {props.meta ? <div className="dashboard-widget__meta">{props.meta}</div> : null}
          </div>
        </div>
        {props.actions ? <div className="dashboard-widget__actions">{props.actions}</div> : null}
      </header>
      <div className="dashboard-widget__body">{props.children}</div>
    </section>
  );
}
