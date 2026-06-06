export type DashboardWidgetId =
  | "map"
  | "accountDetails"
  | "addressIntelligence"
  | "liveDetections"
  | "lprCameras"
  | "recentHistory"
  | "aiInsight"
  | "routePanel"
  | "notes"
  | "reports";

export type DashboardWidgetSize = "compact" | "standard" | "expanded";
export type DashboardLayoutMode = "default" | "driving" | "scanning" | "review" | "minimal";

export interface DashboardWidgetConfig {
  id: DashboardWidgetId;
  visible: boolean;
  size: DashboardWidgetSize;
  order: number;
}

export interface DashboardConfig {
  mode: DashboardLayoutMode;
  widgets: DashboardWidgetConfig[];
}

// v2: mission-critical default (map hero + cam feed + vehicle account + address
// intelligence) and the new accountDetails widget. Bumped from v1 so existing
// browsers reset to the new default layout instead of restoring a stale one
// (which could leave the map in a non-hero slot or hide the new widgets).
export const dashboardConfigStorageKey = "reprovision.dashboard.config.v2";

export interface DashboardWidgetDefinition {
  id: DashboardWidgetId;
  label: string;
  description: string;
}

export const dashboardWidgetDefinitions: DashboardWidgetDefinition[] = [
  { id: "map", label: "Map", description: "Primary navigation and target map." },
  { id: "accountDetails", label: "Vehicle Account", description: "Active recovery target: plate, vehicle, lender, instructions." },
  { id: "addressIntelligence", label: "Address Intelligence", description: "Destination location context and recovery guidance." },
  { id: "liveDetections", label: "Live Detections", description: "Compact recent LPR and vehicle reads." },
  { id: "lprCameras", label: "LPR Cameras", description: "Two camera feeds for active scanning." },
  { id: "recentHistory", label: "Recent History", description: "Recent sightings and match status." },
  { id: "aiInsight", label: "AI Insight", description: "Recommended next action and recovery cue." },
  { id: "routePanel", label: "Route Panel", description: "Distance, ETA, and scan posture." },
  { id: "notes", label: "Notes", description: "Account and follow-up notes for the active target." },
  { id: "reports", label: "Reports", description: "Reserved for future report shortcuts." },
];

const widgetOrder: DashboardWidgetId[] = [
  "map",
  "lprCameras",
  "accountDetails",
  "addressIntelligence",
  "routePanel",
  "aiInsight",
  "liveDetections",
  "recentHistory",
  "notes",
  "reports",
];

const presetWidgets: Record<DashboardLayoutMode, Record<DashboardWidgetId, { visible: boolean; size: DashboardWidgetSize }>> = {
  // Default foregrounds the four mission-critical operations widgets only —
  // map, cam feed, vehicle account, address intelligence — and leaves the rest
  // off so the screen stays uncluttered. Everything else remains available via
  // Customize. (Operators get exactly what drives a recovery, nothing more.)
  default: {
    map: { visible: true, size: "expanded" },
    accountDetails: { visible: true, size: "standard" },
    addressIntelligence: { visible: true, size: "standard" },
    lprCameras: { visible: true, size: "standard" },
    routePanel: { visible: false, size: "compact" },
    aiInsight: { visible: false, size: "compact" },
    liveDetections: { visible: false, size: "standard" },
    recentHistory: { visible: false, size: "compact" },
    notes: { visible: false, size: "compact" },
    reports: { visible: false, size: "compact" },
  },
  driving: {
    map: { visible: true, size: "expanded" },
    accountDetails: { visible: true, size: "compact" },
    addressIntelligence: { visible: true, size: "compact" },
    lprCameras: { visible: true, size: "compact" },
    routePanel: { visible: false, size: "compact" },
    aiInsight: { visible: false, size: "compact" },
    liveDetections: { visible: false, size: "compact" },
    recentHistory: { visible: false, size: "compact" },
    notes: { visible: false, size: "compact" },
    reports: { visible: false, size: "compact" },
  },
  scanning: {
    map: { visible: true, size: "standard" },
    accountDetails: { visible: true, size: "compact" },
    addressIntelligence: { visible: true, size: "compact" },
    lprCameras: { visible: true, size: "expanded" },
    liveDetections: { visible: true, size: "standard" },
    routePanel: { visible: false, size: "compact" },
    aiInsight: { visible: false, size: "compact" },
    recentHistory: { visible: false, size: "compact" },
    notes: { visible: false, size: "compact" },
    reports: { visible: false, size: "compact" },
  },
  review: {
    map: { visible: true, size: "standard" },
    accountDetails: { visible: true, size: "standard" },
    addressIntelligence: { visible: true, size: "standard" },
    lprCameras: { visible: true, size: "compact" },
    recentHistory: { visible: true, size: "expanded" },
    notes: { visible: true, size: "standard" },
    routePanel: { visible: false, size: "compact" },
    aiInsight: { visible: false, size: "compact" },
    liveDetections: { visible: false, size: "standard" },
    reports: { visible: false, size: "compact" },
  },
  minimal: {
    map: { visible: true, size: "expanded" },
    accountDetails: { visible: true, size: "compact" },
    addressIntelligence: { visible: true, size: "compact" },
    lprCameras: { visible: true, size: "compact" },
    routePanel: { visible: false, size: "compact" },
    aiInsight: { visible: false, size: "compact" },
    liveDetections: { visible: false, size: "compact" },
    recentHistory: { visible: false, size: "compact" },
    notes: { visible: false, size: "compact" },
    reports: { visible: false, size: "compact" },
  },
};

function buildPreset(mode: DashboardLayoutMode): DashboardConfig {
  return {
    mode,
    widgets: widgetOrder.map((id, index) => ({
      id,
      visible: presetWidgets[mode][id].visible,
      size: presetWidgets[mode][id].size,
      order: index,
    })),
  };
}

function isWidgetId(value: unknown): value is DashboardWidgetId {
  return typeof value === "string" && widgetOrder.includes(value as DashboardWidgetId);
}

function isWidgetSize(value: unknown): value is DashboardWidgetSize {
  return value === "compact" || value === "standard" || value === "expanded";
}

function isLayoutMode(value: unknown): value is DashboardLayoutMode {
  return value === "default" || value === "driving" || value === "scanning" || value === "review" || value === "minimal";
}

function normalizeWidgetConfig(value: unknown, fallback: DashboardWidgetConfig): DashboardWidgetConfig {
  const candidate = value as Partial<DashboardWidgetConfig> | null | undefined;
  return {
    id: isWidgetId(candidate?.id) ? candidate.id : fallback.id,
    visible: typeof candidate?.visible === "boolean" ? candidate.visible : fallback.visible,
    size: isWidgetSize(candidate?.size) ? candidate.size : fallback.size,
    order: typeof candidate?.order === "number" && Number.isFinite(candidate.order) ? candidate.order : fallback.order,
  };
}

function normalizeConfig(value: unknown): DashboardConfig {
  const fallback = getDefaultDashboardConfig();
  const candidate = value as Partial<DashboardConfig> | null | undefined;
  const mode = isLayoutMode(candidate?.mode) ? candidate.mode : fallback.mode;
  const fallbackMap = new Map(fallback.widgets.map((widget) => [widget.id, widget]));
  const rawWidgets = Array.isArray(candidate?.widgets) ? candidate.widgets : [];
  const seen = new Set<DashboardWidgetId>();
  const widgets = rawWidgets
    .map((widget) => {
      const id = (widget as Partial<DashboardWidgetConfig> | undefined)?.id;
      if (!isWidgetId(id) || seen.has(id)) {
        return null;
      }
      seen.add(id);
      return normalizeWidgetConfig(widget, fallbackMap.get(id) ?? fallback.widgets[0]);
    })
    .filter((widget): widget is DashboardWidgetConfig => widget !== null);

  for (const fallbackWidget of fallback.widgets) {
    if (!seen.has(fallbackWidget.id)) {
      widgets.push(fallbackWidget);
    }
  }

  // Fail-safe: if a persisted config ended up with zero visible widgets
  // the dashboard would render blank with no obvious way for the user to
  // recover. Force the map widget back on so the operator always has the
  // primary surface available — they can re-hide it via Customize if they
  // really want to.
  const anyVisible = widgets.some((widget) => widget.visible);
  if (!anyVisible) {
    const mapWidget = widgets.find((widget) => widget.id === "map");
    if (mapWidget) {
      mapWidget.visible = true;
      mapWidget.size = "expanded";
    }
  }

  return {
    mode,
    widgets: widgets.sort((a, b) => a.order - b.order),
  };
}

export function getDefaultDashboardConfig(mode: DashboardLayoutMode = "default"): DashboardConfig {
  return buildPreset(mode);
}

export function loadDashboardConfig(): DashboardConfig {
  if (typeof window === "undefined") {
    return getDefaultDashboardConfig();
  }

  try {
    const raw = window.localStorage.getItem(dashboardConfigStorageKey);
    if (!raw) {
      return getDefaultDashboardConfig();
    }
    return normalizeConfig(JSON.parse(raw));
  } catch {
    return getDefaultDashboardConfig();
  }
}

export function saveDashboardConfig(config: DashboardConfig): DashboardConfig {
  const normalized = normalizeConfig(config);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(dashboardConfigStorageKey, JSON.stringify(normalized));
    } catch {
      // ignore persistence failures
    }
  }
  return normalized;
}

export function resetDashboardConfig(mode: DashboardLayoutMode = "default"): DashboardConfig {
  return saveDashboardConfig(getDefaultDashboardConfig(mode));
}

export function updateWidgetVisibility(
  config: DashboardConfig,
  widgetId: DashboardWidgetId,
  visible: boolean,
): DashboardConfig {
  return saveDashboardConfig({
    ...config,
    widgets: config.widgets.map((widget) => (widget.id === widgetId ? { ...widget, visible } : widget)),
  });
}

export function updateWidgetSize(
  config: DashboardConfig,
  widgetId: DashboardWidgetId,
  size: DashboardWidgetSize,
): DashboardConfig {
  return saveDashboardConfig({
    ...config,
    widgets: config.widgets.map((widget) => (widget.id === widgetId ? { ...widget, size } : widget)),
  });
}

export function updateLayoutMode(config: DashboardConfig, mode: DashboardLayoutMode): DashboardConfig {
  const preset = buildPreset(mode);
  const currentOrder = new Map(config.widgets.map((widget) => [widget.id, widget.order]));
  return saveDashboardConfig({
    mode,
    widgets: preset.widgets.map((widget) => ({
      ...widget,
      order: currentOrder.get(widget.id) ?? widget.order,
    })),
  });
}

export function reorderDashboardWidget(
  config: DashboardConfig,
  sourceWidgetId: DashboardWidgetId,
  targetWidgetId: DashboardWidgetId,
): DashboardConfig {
  if (sourceWidgetId === targetWidgetId) {
    return saveDashboardConfig(config);
  }

  const ordered = [...config.widgets].sort((a, b) => a.order - b.order);
  const sourceIndex = ordered.findIndex((widget) => widget.id === sourceWidgetId);
  const targetIndex = ordered.findIndex((widget) => widget.id === targetWidgetId);

  if (sourceIndex < 0 || targetIndex < 0) {
    return saveDashboardConfig(config);
  }

  const [moved] = ordered.splice(sourceIndex, 1);
  ordered.splice(targetIndex, 0, moved);

  return saveDashboardConfig({
    ...config,
    widgets: ordered.map((widget, index) => ({
      ...widget,
      order: index,
    })),
  });
}
