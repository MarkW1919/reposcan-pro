import { useEffect, useRef, type ReactElement } from "react";

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
  const { open, onClose } = props;
  const panelRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  // Esc-to-close + focus management: move focus into the drawer on open and
  // restore it to the trigger on close (keyboard/screen-reader accessible).
  useEffect(() => {
    if (!open) {
      return;
    }
    const previouslyFocused = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      // Simple focus trap: keep Tab focus within the panel.
      if (event.key === "Tab" && panelRef.current) {
        const focusables = panelRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) {
          return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }
  return (
    <div className="nav-drawer" role="dialog" aria-modal="true" aria-label="Navigation menu">
      <button className="nav-drawer__scrim" type="button" aria-label="Close menu" onClick={onClose} />
      <nav className="nav-drawer__panel" ref={panelRef} aria-label="Primary navigation">
        <div className="nav-drawer__head">
          <div className="nav-drawer__brand">
            <strong>RepoScan</strong>
            <small>Recovery intelligence</small>
          </div>
          <button className="nav-drawer__close" type="button" onClick={onClose} ref={closeRef}>
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
