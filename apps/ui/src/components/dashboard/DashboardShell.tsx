import type { ReactElement, ReactNode } from "react";

export function DashboardShell(props: {
  header: ReactNode;
  toolbar: ReactNode;
  children: ReactNode;
  customizePanel?: ReactNode;
}): ReactElement {
  return (
    <section className="dashboard-shell">
      <div className="dashboard-shell__header">{props.header}</div>
      <div className="dashboard-shell__content">{props.children}</div>
      {props.toolbar ? <div className="dashboard-shell__toolbar">{props.toolbar}</div> : null}
      {props.customizePanel}
    </section>
  );
}
