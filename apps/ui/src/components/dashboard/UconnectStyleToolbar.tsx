import type { ReactElement } from "react";

import { StatusPill, type StatusPillTone } from "./StatusPill";

export interface ToolbarItem {
  id: string;
  label: string;
  value: string;
  tone: StatusPillTone;
  active?: boolean;
  onClick: () => void;
}

export function UconnectStyleToolbar(props: { items: ToolbarItem[] }): ReactElement {
  return (
    <nav className="uconnect-toolbar" aria-label="Primary dashboard controls">
      {props.items.map((item) => (
        <button
          key={item.id}
          className={`uconnect-toolbar__button ${item.active ? "is-active" : ""}`.trim()}
          type="button"
          onClick={item.onClick}
        >
          <span className="uconnect-toolbar__label">{item.label}</span>
          <StatusPill label={item.value} tone={item.tone} />
        </button>
      ))}
    </nav>
  );
}
