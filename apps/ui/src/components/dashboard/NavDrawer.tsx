import type { ReactElement } from "react";

export interface NavDrawerItem {
  id: string;
  label: string;
  detail?: string;
  active?: boolean;
  onClick: () => void;
}

export interface NavDrawerSection {
  title: string;
  items: NavDrawerItem[];
}

/**
 * Slide-in navigation drawer. Single home for full navigation (screens grouped
 * by Operations / Admin), Settings, and the Customize Dashboard entry — so the
 * header and footer stay slim. Tapping the scrim or an item closes the drawer.
 */
export function NavDrawer(props: {
  open: boolean;
  onClose: () => void;
  sections: NavDrawerSection[];
  onOpenCustomize: () => void;
}): ReactElement | null {
  if (!props.open) {
    return null;
  }
  return (
    <div className="nav-drawer" role="dialog" aria-modal="true" aria-label="Navigation menu">
      <button className="nav-drawer__scrim" type="button" aria-label="Close menu" onClick={props.onClose} />
      <nav className="nav-drawer__panel">
        <div className="nav-drawer__head">
          <div className="nav-drawer__brand">
            <strong>RepoScan</strong>
            <small>Recovery intelligence</small>
          </div>
          <button className="nav-drawer__close" type="button" onClick={props.onClose}>
            Close
          </button>
        </div>

        {props.sections.map((section) => (
          <div key={section.title} className="nav-drawer__section">
            <span className="nav-drawer__section-title">{section.title}</span>
            {section.items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`nav-drawer__item ${item.active ? "is-active" : ""}`.trim()}
                onClick={() => {
                  item.onClick();
                  props.onClose();
                }}
              >
                <span className="nav-drawer__item-label">{item.label}</span>
                {item.detail ? <small className="nav-drawer__item-detail">{item.detail}</small> : null}
              </button>
            ))}
          </div>
        ))}

        <div className="nav-drawer__section">
          <span className="nav-drawer__section-title">Dashboard</span>
          <button
            type="button"
            className="nav-drawer__item"
            onClick={() => {
              props.onOpenCustomize();
              props.onClose();
            }}
          >
            <span className="nav-drawer__item-label">Customize Dashboard</span>
            <small className="nav-drawer__item-detail">Screen layout, widgets, sizes</small>
          </button>
        </div>
      </nav>
    </div>
  );
}
