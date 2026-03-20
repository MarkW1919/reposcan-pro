import type { AlertItem } from "./demo-data";

export interface HealthDependency {
  name: string;
  state: string;
  message: string;
}

export interface HealthResponse {
  service: string;
  version: string;
  state: string;
  timestamp_utc: string;
  dependencies: HealthDependency[];
}

export interface DashboardDetection {
  detection_id: string;
  timestamp_utc: string;
  camera_id: string;
  gps_latitude: number | null;
  gps_longitude: number | null;
  plate_text: string | null;
  plate_confidence: number | null;
  vehicle_color: string | null;
  vehicle_make: string | null;
  vehicle_model: string | null;
  optional_vehicle_year: string | null;
}

export interface DashboardAlert {
  alert_id: string;
  detection_id: string;
  hotlist_entry_id: string;
  timestamp_utc: string;
  camera_id: string;
  matched_plate_text: string;
  match_confidence: number;
  hotlist_label: string | null;
  notes: string | null;
  status: string;
  gps_latitude: number | null;
  gps_longitude: number | null;
}

export interface DashboardHotlist {
  entry_id: string;
  plate_text: string;
  label: string | null;
  notes: string | null;
  active: boolean;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface DashboardOverviewResponse {
  generated_at_utc: string;
  health: HealthResponse;
  counts: {
    active_alerts: number;
    recent_detections: number;
    active_hotlists: number;
  };
  detections: DashboardDetection[];
  alerts: DashboardAlert[];
  hotlists: DashboardHotlist[];
}

function apiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";
}

function titleCase(value: string | null | undefined): string {
  if (!value) {
    return "";
  }

  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((segment) => segment[0].toUpperCase() + segment.slice(1).toLowerCase())
    .join(" ");
}

function cameraLabel(cameraId: string): string {
  return titleCase(cameraId.replace(/^cam_/, "").replace(/\d+$/, "").replace(/_+/g, " ").trim()) || cameraId;
}

function formatTime(timestampUtc: string): string {
  const parsed = new Date(timestampUtc);
  if (Number.isNaN(parsed.valueOf())) {
    return timestampUtc;
  }

  return parsed.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatGps(latitude: number | null | undefined, longitude: number | null | undefined): string {
  if (typeof latitude !== "number" || typeof longitude !== "number") {
    return "GPS unavailable";
  }

  return `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
}

function buildVehicleLabel(detection: DashboardDetection | undefined, alert: DashboardAlert): string {
  if (!detection) {
    return alert.hotlist_label ?? "Live hotlist vehicle";
  }

  const parts = [titleCase(detection.vehicle_color), titleCase(detection.vehicle_make), titleCase(detection.vehicle_model)].filter(
    Boolean,
  );
  return parts.join(" ") || alert.hotlist_label || "Live vehicle";
}

function buildColorYearLabel(detection: DashboardDetection | undefined): string {
  if (!detection) {
    return "Attributes / live";
  }

  const color = titleCase(detection.vehicle_color) || "Unknown";
  const year = detection.optional_vehicle_year ?? "Live";
  return `${color} / ${year}`;
}

export async function fetchDashboardOverview(signal?: AbortSignal): Promise<DashboardOverviewResponse> {
  const response = await fetch(`${apiBaseUrl()}/dashboard/overview`, { signal });
  if (!response.ok) {
    throw new Error(`Failed to load dashboard overview (${response.status})`);
  }
  return (await response.json()) as DashboardOverviewResponse;
}

export function mapOverviewToAlertItems(
  overview: DashboardOverviewResponse,
  fallbackAlerts: AlertItem[],
): AlertItem[] {
  if (overview.alerts.length === 0) {
    return fallbackAlerts;
  }

  const detectionsById = new Map(overview.detections.map((record) => [record.detection_id, record]));

  return overview.alerts.map((alert) => {
    const detection = detectionsById.get(alert.detection_id);
    const gps = formatGps(alert.gps_latitude ?? detection?.gps_latitude, alert.gps_longitude ?? detection?.gps_longitude);
    const severity = alert.status === "active" ? "critical" : alert.status === "acknowledged" ? "priority" : "watch";
    const scenario = alert.status === "active" ? "tow_ready" : alert.status === "acknowledged" ? "visual_match" : "assignment";
    const status = alert.status === "active" ? "monitoring" : alert.status === "acknowledged" ? "onsite" : "cleared";
    return {
      id: alert.alert_id,
      plate: alert.matched_plate_text,
      vehicle: buildVehicleLabel(detection, alert),
      colorYear: buildColorYearLabel(detection),
      time: formatTime(alert.timestamp_utc),
      camera: cameraLabel(alert.camera_id),
      confidence: alert.match_confidence,
      gps,
      severity,
      scenario,
      status,
      routeAction: alert.status === "active" ? "Open Route" : "Review Alert",
      location: gps,
      distance: "Live API",
      notes: alert.notes ?? `Hotlist: ${alert.hotlist_label ?? "Unlabeled entry"}`,
      bestApproach: "Use the nearest safe lane and visually confirm before engagement.",
    };
  });
}
