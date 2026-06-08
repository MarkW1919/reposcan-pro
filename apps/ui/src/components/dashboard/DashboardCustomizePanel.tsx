import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactElement } from "react";

import {
  dashboardLayoutTemplates,
  dashboardWidgetDefinitions,
  type DashboardConfig,
  type DashboardLayoutMode,
  type DashboardLayoutTemplate,
  type DashboardWidgetId,
  type DashboardWidgetSize,
} from "../../dashboard-config";
import { StatusPill } from "./StatusPill";

const layoutModes: DashboardLayoutMode[] = ["default", "driving", "scanning", "review", "minimal"];
const sizeOptions: DashboardWidgetSize[] = ["compact", "standard", "expanded"];

function labelize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function DashboardCustomizePanel(props: {
  config: DashboardConfig;
  widgetAvailability?: Partial<Record<DashboardWidgetId, boolean>>;
  onClose: () => void;
  onReset: () => void;
  onModeChange: (mode: DashboardLayoutMode) => void;
  onLayoutChange: (layout: DashboardLayoutTemplate) => void;
  onWidgetMove: (sourceWidgetId: DashboardWidgetId, targetWidgetId: DashboardWidgetId) => void;
  onWidgetVisibilityChange: (widgetId: DashboardWidgetId, visible: boolean) => void;
  onWidgetSizeChange: (widgetId: DashboardWidgetId, size: DashboardWidgetSize) => void;
}): ReactElement {
  const [draggingWidgetId, setDraggingWidgetId] = useState<DashboardWidgetId | null>(null);
  const [dropTargetWidgetId, setDropTargetWidgetId] = useState<DashboardWidgetId | null>(null);
  const rowRefs = useRef<Partial<Record<DashboardWidgetId, HTMLDivElement | null>>>({});
  const activeDragRef = useRef<{ pointerId: number; widgetId: DashboardWidgetId } | null>(null);
  const widgetMap = new Map(props.config.widgets.map((widget) => [widget.id, widget]));
  const orderedDefinitions = [...dashboardWidgetDefinitions].sort((a, b) => {
    const orderA = widgetMap.get(a.id)?.order ?? Number.MAX_SAFE_INTEGER;
    const orderB = widgetMap.get(b.id)?.order ?? Number.MAX_SAFE_INTEGER;
    return orderA - orderB;
  });
  const availableOrderedDefinitions = orderedDefinitions.filter(
    (definition) => (props.widgetAvailability?.[definition.id] ?? true) && widgetMap.has(definition.id),
  );

  function clearPointerDrag(): void {
    activeDragRef.current = null;
    setDraggingWidgetId(null);
    setDropTargetWidgetId(null);
  }

  function resolveDropTarget(clientY: number): DashboardWidgetId | null {
    for (const definition of availableOrderedDefinitions) {
      const row = rowRefs.current[definition.id];
      if (!row) {
        continue;
      }
      const bounds = row.getBoundingClientRect();
      if (clientY < bounds.top + bounds.height / 2) {
        return definition.id;
      }
    }
    return availableOrderedDefinitions[availableOrderedDefinitions.length - 1]?.id ?? null;
  }

  function moveWidgetByStep(widgetId: DashboardWidgetId, step: -1 | 1): void {
    const currentIndex = availableOrderedDefinitions.findIndex((definition) => definition.id === widgetId);
    const targetIndex = currentIndex + step;
    const target = availableOrderedDefinitions[targetIndex];
    if (currentIndex < 0 || !target) {
      return;
    }
    props.onWidgetMove(widgetId, target.id);
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>, widgetId: DashboardWidgetId): void {
    if (!(props.widgetAvailability?.[widgetId] ?? true)) {
      return;
    }
    event.preventDefault();
    activeDragRef.current = { pointerId: event.pointerId, widgetId };
    setDraggingWidgetId(widgetId);
    setDropTargetWidgetId(widgetId);
  }

  useEffect(() => {
    function handleEscape(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.stopPropagation();
        props.onClose();
      }
    }
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [props.onClose]);

  useEffect(() => {
    if (!draggingWidgetId) {
      return;
    }

    const previousUserSelect = document.body.style.userSelect;
    const previousCursor = document.body.style.cursor;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "grabbing";

    function handleWindowPointerMove(event: PointerEvent): void {
      if (!activeDragRef.current || activeDragRef.current.pointerId !== event.pointerId) {
        return;
      }
      const nextTarget = resolveDropTarget(event.clientY);
      if (nextTarget) {
        setDropTargetWidgetId(nextTarget);
      }
    }

    function finalizePointerDrag(event: PointerEvent): void {
      if (!activeDragRef.current || activeDragRef.current.pointerId !== event.pointerId) {
        return;
      }
      const sourceWidgetId = activeDragRef.current.widgetId;
      const targetWidgetId = resolveDropTarget(event.clientY);
      if (sourceWidgetId && targetWidgetId && sourceWidgetId !== targetWidgetId) {
        props.onWidgetMove(sourceWidgetId, targetWidgetId);
      }
      clearPointerDrag();
    }

    function cancelPointerDrag(): void {
      clearPointerDrag();
    }

    window.addEventListener("pointermove", handleWindowPointerMove);
    window.addEventListener("pointerup", finalizePointerDrag);
    window.addEventListener("pointercancel", cancelPointerDrag);

    return () => {
      window.removeEventListener("pointermove", handleWindowPointerMove);
      window.removeEventListener("pointerup", finalizePointerDrag);
      window.removeEventListener("pointercancel", cancelPointerDrag);
      document.body.style.userSelect = previousUserSelect;
      document.body.style.cursor = previousCursor;
    };
  }, [availableOrderedDefinitions, draggingWidgetId, props.onWidgetMove]);

  return (
    <div className="dashboard-customize__scrim" role="presentation" onClick={props.onClose}>
      <aside
        className="dashboard-customize"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dashboard-customize-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="dashboard-customize__header">
          <div>
            <span className="dashboard-widget__eyebrow">Display setup</span>
            <h3 id="dashboard-customize-title">Customize Dashboard</h3>
            <p>Choose what appears on the recovery screen and how much space each module gets.</p>
          </div>
          <button className="dashboard-customize__close" type="button" onClick={props.onClose}>
            Done
          </button>
        </header>

        <section className="dashboard-customize__section">
          <div className="dashboard-customize__section-header">
            <strong>Screen Layout</strong>
            <span>{dashboardLayoutTemplates.find((t) => t.id === props.config.layout)?.label ?? "Console"}</span>
          </div>
          <div className="dashboard-customize__layout-grid">
            {dashboardLayoutTemplates.map((template) => (
              <button
                key={template.id}
                className={`dashboard-customize__layout-button ${props.config.layout === template.id ? "is-active" : ""}`.trim()}
                type="button"
                onClick={() => props.onLayoutChange(template.id)}
              >
                <span className="dashboard-customize__layout-name">{template.label}</span>
                <span className="dashboard-customize__layout-desc">{template.description}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="dashboard-customize__section">
          <div className="dashboard-customize__section-header">
            <strong>Widget Preset</strong>
            <span>{labelize(props.config.mode)}</span>
          </div>
          <div className="dashboard-customize__mode-grid">
            {layoutModes.map((mode) => (
              <button
                key={mode}
                className={`dashboard-customize__mode-button ${props.config.mode === mode ? "is-active" : ""}`.trim()}
                type="button"
                onClick={() => props.onModeChange(mode)}
              >
                {labelize(mode)}
              </button>
            ))}
          </div>
        </section>

        <section className="dashboard-customize__section">
          <div className="dashboard-customize__section-header">
            <strong>Widgets</strong>
            <button className="dashboard-customize__reset" type="button" onClick={props.onReset}>
              Reset Default
            </button>
          </div>
          <p className="dashboard-customize__hint">Top to bottom order controls the dashboard layout. The first visible widget becomes the main display.</p>
          <div className="dashboard-customize__widget-list">
            {orderedDefinitions.map((definition) => {
              const widget = widgetMap.get(definition.id);
              const available = props.widgetAvailability?.[definition.id] ?? true;
              if (!widget) {
                return null;
              }
              return (
                <div
                  key={definition.id}
                  className={`dashboard-customize__widget-row ${!available ? "is-disabled" : ""} ${draggingWidgetId === definition.id ? "is-dragging" : ""} ${dropTargetWidgetId === definition.id && draggingWidgetId !== definition.id ? "is-drop-target" : ""}`.trim()}
                  ref={(node) => {
                    rowRefs.current[definition.id] = node;
                  }}
                >
                  <div className="dashboard-customize__widget-copy">
                    <div
                      className="dashboard-customize__drag-handle"
                      aria-disabled={!available}
                      aria-label={`Drag to reorder ${definition.label}`}
                      role="button"
                      tabIndex={available ? 0 : -1}
                      onPointerDown={(event) => handlePointerDown(event, definition.id)}
                      onPointerCancel={clearPointerDrag}
                    >
                      <svg
                        aria-hidden="true"
                        focusable="false"
                        viewBox="0 0 12 16"
                        width="12"
                        height="16"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <circle cx="3" cy="3" r="1.4" fill="currentColor" />
                        <circle cx="9" cy="3" r="1.4" fill="currentColor" />
                        <circle cx="3" cy="8" r="1.4" fill="currentColor" />
                        <circle cx="9" cy="8" r="1.4" fill="currentColor" />
                        <circle cx="3" cy="13" r="1.4" fill="currentColor" />
                        <circle cx="9" cy="13" r="1.4" fill="currentColor" />
                      </svg>
                    </div>
                    <div className="dashboard-customize__widget-text">
                      <strong>{definition.label}</strong>
                      <p>{definition.description}</p>
                    </div>
                  </div>
                  <div className="dashboard-customize__widget-controls">
                    {!available ? <StatusPill label="Unavailable" tone="gray" /> : null}
                    <label className="dashboard-customize__toggle">
                      <input
                        checked={widget.visible}
                        disabled={!available}
                        type="checkbox"
                        onChange={(event) => props.onWidgetVisibilityChange(definition.id, event.target.checked)}
                      />
                      <span>{widget.visible ? "Shown" : "Hidden"}</span>
                    </label>
                    <div className="dashboard-customize__size-group">
                      <button
                        className="dashboard-customize__move-button"
                        disabled={!available || availableOrderedDefinitions[0]?.id === definition.id}
                        type="button"
                        onClick={() => moveWidgetByStep(definition.id, -1)}
                      >
                        Up
                      </button>
                      <button
                        className="dashboard-customize__move-button"
                        disabled={!available || availableOrderedDefinitions[availableOrderedDefinitions.length - 1]?.id === definition.id}
                        type="button"
                        onClick={() => moveWidgetByStep(definition.id, 1)}
                      >
                        Down
                      </button>
                      {sizeOptions.map((size) => (
                        <button
                          key={size}
                          className={`dashboard-customize__size-button ${widget.size === size ? "is-active" : ""}`.trim()}
                          disabled={!available}
                          type="button"
                          onClick={() => props.onWidgetSizeChange(definition.id, size)}
                        >
                          {labelize(size)}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </aside>
    </div>
  );
}
