export type DashboardWidgetId =
  | "map"
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

export const dashboardConfigStorageKey = "reprovision.dashboard.config.v1";

export interface DashboardWidgetDefinition {
  id: DashboardWidgetId;
  label: string;
  description: string;
}

export const dashboardWidgetDefinitions: DashboardWidgetDefinition[] = [
  { id: "map", label: "Map", description: "Primary navigation and target map." },
  { id: "addressIntelligence", label: "Address Intelligence", description: "Recovery location context and field snapshot." },
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
  "addressIntelligence",
  "routePanel",
  "aiInsight",
  "lprCameras",
  "liveDetections",
  "recentHistory",
  "notes",
  "reports",
];

const presetWidgets: Record<DashboardLayoutMode, Record<DashboardWidgetId, { visible: boolean; size: DashboardWidgetSize }>> = {
  default: {
    map: { visible: true, size: "expanded" },
    addressIntelligence: { visible: true, size: "standard" },
    routePanel: { visible: true, size: "compact" },
    aiInsight: { visible: true, size: "compact" },
    lprCameras: { visible: true, size: "standard" },
    liveDetections: { visible: true, size: "standard" },
    recentHistory: { visible: true, size: "compact" },
    notes: { visible: false, size: "compact" },
    reports: { visible: false, size: "compact" },
  },
  driving: {
    map: { visible: true, size: "expanded" },
    addressIntelligence: { visible: true, size: "compact" },
    routePanel: { visible: true, size: "compact" },
    aiInsight: { visible: true, size: "compact" },
    lprCameras: { visible: true, size: "compact" },
    liveDetections: { visible: true, size: "compact" },
    recentHistory: { visible: false, size: "compact" },
    notes: { visible: false, size: "compact" },
    reports: { visible: false, size: "compact" },
  },
  scanning: {
    map: { visible: true, size: "standard" },
    addressIntelligence: { visible: true, size: "standard" },
    routePanel: { visible: true, size: "compact" },
    aiInsight: { visible: true, size: "compact" },
    lprCameras: { visible: true, size: "expanded" },
    liveDetections: { visible: true, size: "expanded" },
    recentHistory: { visible: true, size: "compact" },
    notes: { visible: false, size: "compact" },
    reports: { visible: false, size: "compact" },
  },
  review: {
    map: { visible: true, size: "standard" },
    addressIntelligence: { visible: true, size: "standard" },
    routePanel: { visible: true, size: "compact" },
    aiInsight: { visible: true, size: "compact" },
    lprCameras: { visible: true, size: "compact" },
    liveDetections: { visible: true, size: "standard" },
    recentHistory: { visible: true, size: "expanded" },
    notes: { visible: true, size: "standard" },
    reports: { visible: false, size: "compact" },
  },
  minimal: {
    map: { visible: true, size: "expanded" },
    addressIntelligence: { visible: true, size: "compact" },
    routePanel: { visible: true, size: "compact" },
    aiInsight: { visible: false, size: "compact" },
    lprCameras: { visible: false, size: "compact" },
    liveDetections: { visible: true, size: "compact" },
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
