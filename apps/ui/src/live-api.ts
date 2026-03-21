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

export type ReviewAction = "confirm" | "correct" | "flag" | "dismiss";

export interface ReviewRecord {
  review_id: string;
  detection_id: string;
  action: ReviewAction;
  operator_id: string | null;
  corrected_plate_text: string | null;
  notes: string | null;
  reviewed_at_utc: string;
}

export interface ReviewSubmission {
  action: ReviewAction;
  operator_id?: string;
  corrected_plate_text?: string;
  notes?: string;
  reviewed_at_utc: string;
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

export interface HotlistSubmission {
  plate_text: string;
  label?: string;
  notes?: string;
  active: boolean;
}

export interface DashboardPopupActivityEvent {
  event_id: string;
  event_type: "address" | "hotlist";
  source_record_id: string;
  detection_id: string;
  timestamp_utc: string;
  camera_id: string;
  plate_text: string | null;
  confidence: number;
  vehicle_color: string | null;
  vehicle_make: string | null;
  vehicle_model: string | null;
  optional_vehicle_year: string | null;
  hotlist_label: string | null;
  gps_latitude: number | null;
  gps_longitude: number | null;
  note: string | null;
}

export interface DemoRunSummary {
  frames_captured: number;
  candidates_processed: number;
  tracks_finalized: number;
  stored_detection_ids: string[];
  created_alert_ids: string[];
}

export interface DemoRuntimeStatus {
  state: "idle" | "running" | "succeeded" | "failed";
  run_id: string | null;
  started_at_utc: string | null;
  completed_at_utc: string | null;
  frames_directory: string | null;
  glob_pattern: string | null;
  sequence_id: string | null;
  plate_text: string | null;
  error_message: string | null;
  summary: DemoRunSummary | null;
}

export interface DemoRunSubmission {
  frames_directory: string;
  start_timestamp_utc?: string;
  frame_interval_ms?: number;
  glob_pattern?: string;
  start_frame_number?: number;
  sequence_id?: string;
  plate_text?: string;
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
  popup_activity: DashboardPopupActivityEvent[];
}

function apiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";
}

async function responseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload.detail) {
      return payload.detail;
    }
  } catch {
    // Ignore JSON parsing issues and use the fallback message below.
  }
  return fallback;
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

function buildPopupVehicleLabel(event: DashboardPopupActivityEvent): string {
  const parts = [titleCase(event.vehicle_color), titleCase(event.vehicle_make), titleCase(event.vehicle_model)].filter(Boolean);
  return parts.join(" ") || event.hotlist_label || "Live vehicle";
}

function buildPopupColorYearLabel(event: DashboardPopupActivityEvent): string {
  const color = titleCase(event.vehicle_color) || "Unknown";
  const year = event.optional_vehicle_year ?? "Live";
  return `${color} / ${year}`;
}

function buildPopupLocationLabel(event: DashboardPopupActivityEvent): string {
  return event.hotlist_label ?? cameraLabel(event.camera_id);
}

function buildPopupImageLabel(event: DashboardPopupActivityEvent): string {
  return event.event_type === "hotlist" ? "Live hotlist frame" : "Live scan frame";
}

export async function fetchDashboardOverview(signal?: AbortSignal): Promise<DashboardOverviewResponse> {
  const response = await fetch(`${apiBaseUrl()}/dashboard/overview`, { signal });
  if (!response.ok) {
    throw new Error(`Failed to load dashboard overview (${response.status})`);
  }
  return (await response.json()) as DashboardOverviewResponse;
}

export async function fetchDemoRuntimeStatus(signal?: AbortSignal): Promise<DemoRuntimeStatus> {
  const response = await fetch(`${apiBaseUrl()}/demo/runtime`, { signal });
  if (!response.ok) {
    throw new Error(`Failed to load demo runtime status (${response.status})`);
  }
  return (await response.json()) as DemoRuntimeStatus;
}

export async function startDemoRun(submission: DemoRunSubmission): Promise<DemoRuntimeStatus> {
  const response = await fetch(`${apiBaseUrl()}/demo/runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to start demo run (${response.status})`));
  }
  return (await response.json()) as DemoRuntimeStatus;
}

export async function fetchHotlists(signal?: AbortSignal): Promise<DashboardHotlist[]> {
  const response = await fetch(`${apiBaseUrl()}/hotlists?limit=100`, { signal });
  if (!response.ok) {
    throw new Error(`Failed to load hotlists (${response.status})`);
  }
  return (await response.json()) as DashboardHotlist[];
}

export async function createHotlist(submission: HotlistSubmission): Promise<DashboardHotlist> {
  const response = await fetch(`${apiBaseUrl()}/hotlists`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(`Failed to save hotlist (${response.status})`);
  }
  return (await response.json()) as DashboardHotlist;
}

export async function updateHotlist(entryId: string, submission: HotlistSubmission): Promise<DashboardHotlist> {
  const response = await fetch(`${apiBaseUrl()}/hotlists/${encodeURIComponent(entryId)}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(`Failed to update hotlist (${response.status})`);
  }
  return (await response.json()) as DashboardHotlist;
}

export async function fetchReviews(detectionId: string, signal?: AbortSignal): Promise<ReviewRecord[]> {
  const response = await fetch(`${apiBaseUrl()}/reviews/${encodeURIComponent(detectionId)}`, { signal });
  if (!response.ok) {
    throw new Error(`Failed to load reviews (${response.status})`);
  }
  return (await response.json()) as ReviewRecord[];
}

export async function createReview(detectionId: string, submission: ReviewSubmission): Promise<ReviewRecord> {
  const response = await fetch(`${apiBaseUrl()}/reviews/${encodeURIComponent(detectionId)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(`Failed to save review (${response.status})`);
  }
  return (await response.json()) as ReviewRecord;
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
      detectionId: alert.detection_id,
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

export function mapOverviewToPopupHistory(overview: DashboardOverviewResponse) {
  return overview.popup_activity.map((event) => ({
    id: event.event_id,
    type: event.event_type,
    plate: event.plate_text,
    vehicle: buildPopupVehicleLabel(event),
    colorYear: buildPopupColorYearLabel(event),
    timestamp: formatTime(event.timestamp_utc),
    gps: formatGps(event.gps_latitude, event.gps_longitude),
    camera: cameraLabel(event.camera_id),
    location: buildPopupLocationLabel(event),
    imageLabel: buildPopupImageLabel(event),
    confidence: event.confidence,
    note:
      event.note ??
      (event.event_type === "hotlist"
        ? "Hotlist match from the live API."
        : "General detection available from the live API."),
  }));
}
