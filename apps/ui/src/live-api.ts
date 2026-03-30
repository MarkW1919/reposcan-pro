import type { AlertItem, RecoveryLogEntry } from "./demo-data";

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
export type DashboardAlertStatus = "active" | "acknowledged" | "dismissed";
export type DashboardAlertMatchType = "exact" | "normalized";
export type FollowUpPriority = "routine" | "priority" | "critical";
export type FollowUpStatus = "open" | "monitoring" | "resolved";
export type DispatchAssignmentPriority = "watch" | "priority" | "critical";
export type DispatchAssignmentStatus = "queued" | "assigned" | "en_route" | "onsite" | "completed" | "cancelled";

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

export interface BoundingBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PlateCandidate {
  text: string;
  confidence: number;
}

export interface DashboardDetection {
  detection_id: string;
  timestamp_utc: string;
  camera_id: string;
  gps_latitude: number | null;
  gps_longitude: number | null;
  plate_text: string | null;
  plate_confidence: number | null;
  plate_candidates: PlateCandidate[];
  vehicle_bbox: BoundingBox;
  plate_bbox: BoundingBox | null;
  vehicle_color: string | null;
  vehicle_color_confidence: number | null;
  vehicle_make: string | null;
  vehicle_make_confidence: number | null;
  vehicle_model: string | null;
  vehicle_model_confidence: number | null;
  optional_vehicle_year: string | null;
  optional_year_confidence: number | null;
  tracker_id: string | null;
  image_path: string;
  plate_crop_path: string | null;
  source_video_path: string | null;
  frame_number: number;
  local_only_flag: boolean;
  sync_status: string;
}

export interface DashboardAlert {
  alert_id: string;
  detection_id: string;
  hotlist_entry_id: string;
  timestamp_utc: string;
  camera_id: string;
  matched_plate_text: string;
  match_confidence: number;
  match_type: DashboardAlertMatchType;
  hotlist_label: string | null;
  notes: string | null;
  response_operator_id: string | null;
  response_notes: string | null;
  updated_at_utc: string | null;
  status: DashboardAlertStatus;
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

export interface AlertUpdateSubmission {
  status: DashboardAlertStatus;
  operator_id?: string;
  response_notes?: string;
}

export interface FollowUpRecord {
  follow_up_id: string;
  detection_id: string;
  alert_id: string | null;
  plate_text: string | null;
  priority: FollowUpPriority;
  status: FollowUpStatus;
  created_by_operator_id: string | null;
  assigned_operator_id: string | null;
  summary: string | null;
  notes: string | null;
  due_at_utc: string | null;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface FollowUpSubmission {
  detection_id: string;
  alert_id?: string;
  plate_text?: string;
  priority: FollowUpPriority;
  status: FollowUpStatus;
  assigned_operator_id?: string;
  summary?: string;
  notes?: string;
  due_at_utc?: string;
}

export interface DispatchAssignmentRecord {
  assignment_id: string;
  detection_id: string;
  alert_id: string | null;
  plate_text: string | null;
  priority: DispatchAssignmentPriority;
  status: DispatchAssignmentStatus;
  created_by_operator_id: string | null;
  assigned_operator_id: string | null;
  assigned_unit_label: string | null;
  destination_label: string | null;
  summary: string | null;
  notes: string | null;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface DispatchAssignmentSubmission {
  detection_id: string;
  alert_id?: string;
  plate_text?: string;
  priority: DispatchAssignmentPriority;
  status: DispatchAssignmentStatus;
  assigned_operator_id?: string;
  assigned_unit_label?: string;
  destination_label?: string;
  summary?: string;
  notes?: string;
}

export interface OperatorCapabilities {
  can_submit_reviews: boolean;
  can_update_alerts: boolean;
  can_manage_hotlists: boolean;
  can_manage_follow_ups: boolean;
  can_manage_dispatch: boolean;
  can_start_demo_runs: boolean;
  can_view_audit: boolean;
}

export type ApiRole = "viewer" | "operator" | "admin" | "integrator";

export interface OperatorPrincipal {
  principal_id: string;
  display_name: string | null;
  authenticated: boolean;
  roles: ApiRole[];
  capabilities: OperatorCapabilities;
}

export interface OperatorSessionRecord {
  session_id: string;
  principal_id: string;
  display_name: string | null;
  authenticated: boolean;
  roles: ApiRole[];
  client_label: string | null;
  workspace: string;
  selected_detection_id: string | null;
  selected_alert_id: string | null;
  navigation_active: boolean;
  last_seen_at_utc: string;
}

export interface OperatorSessionHeartbeatSubmission {
  session_id: string;
  client_label?: string;
  workspace: string;
  selected_detection_id?: string;
  selected_alert_id?: string;
  navigation_active: boolean;
}

export type AuditOutcome = "success" | "denied" | "rejected" | "error";

export interface ApiAuditEvent {
  event_id: string;
  occurred_at_utc: string;
  request_id: string;
  principal_id: string | null;
  principal_roles: string[];
  action: string;
  outcome: AuditOutcome;
  method: string;
  path: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
}

export interface AuditEventResponse {
  events: ApiAuditEvent[];
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
    open_follow_ups: number;
    active_assignments: number;
    active_sessions: number;
  };
  detections: DashboardDetection[];
  alerts: DashboardAlert[];
  follow_ups: FollowUpRecord[];
  assignments: DispatchAssignmentRecord[];
  hotlists: DashboardHotlist[];
  popup_activity: DashboardPopupActivityEvent[];
  current_principal: OperatorPrincipal;
  active_sessions: OperatorSessionRecord[];
}

export type SearchPlateMatchMode = "contains" | "exact" | "prefix" | "suffix";

export interface SearchPageInfo {
  total_results: number;
  limit: number;
  offset: number;
}

export interface DetectionSearchFilters {
  plate?: string;
  plate_match?: SearchPlateMatchMode;
  start_utc?: string;
  end_utc?: string;
  camera_id?: string;
  min_latitude?: number;
  max_latitude?: number;
  min_longitude?: number;
  max_longitude?: number;
  vehicle_color?: string;
  vehicle_make?: string;
  vehicle_model?: string;
  vehicle_year?: string;
  alert_status?: DashboardAlertStatus;
  limit?: number;
  offset?: number;
}

export interface DetectionSearchResult {
  page: SearchPageInfo;
  results: DashboardDetection[];
}

export interface AuditEventFilters {
  limit?: number;
  principal_id?: string;
  action_prefix?: string;
  outcome?: AuditOutcome;
  target_id?: string;
}

interface ApiClientConfig {
  apiKey: string;
}

const apiClientConfig: ApiClientConfig = {
  apiKey: ((import.meta.env.VITE_API_KEY as string | undefined) ?? "").trim(),
};

function configuredApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";
}

function apiPrefix(): string {
  const configured = (import.meta.env.VITE_API_PREFIX as string | undefined)?.trim();
  if (!configured) {
    return "/api/v1";
  }
  return configured.startsWith("/") ? configured.replace(/\/$/, "") : `/${configured.replace(/\/$/, "")}`;
}

function apiUrl(path: string): string {
  const baseUrl = configuredApiBaseUrl();
  const prefix = apiPrefix();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const rootUrl = baseUrl.endsWith(prefix) ? baseUrl.slice(0, -prefix.length) : baseUrl;
  return `${rootUrl}${prefix}${normalizedPath}`;
}

export function setApiClientConfig(config: Partial<ApiClientConfig>): void {
  if (typeof config.apiKey === "string") {
    apiClientConfig.apiKey = config.apiKey.trim();
  }
}

function authHeaders(): HeadersInit {
  return apiClientConfig.apiKey ? { "X-RepoScan-Api-Key": apiClientConfig.apiKey } : {};
}

function mediaUrl(path: string): string {
  return apiUrl(path);
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

function alertSortKey(alert: DashboardAlert): string {
  return alert.updated_at_utc ?? alert.timestamp_utc;
}

function sortAlerts(alerts: DashboardAlert[]): DashboardAlert[] {
  return [...alerts].sort((left, right) => alertSortKey(right).localeCompare(alertSortKey(left)));
}

function recoveryLogStatus(status: DashboardAlert["status"]): RecoveryLogEntry["status"] {
  switch (status) {
    case "acknowledged":
      return "watch";
    case "dismissed":
      return "closed";
    default:
      return "active";
  }
}

export async function fetchDashboardOverview(signal?: AbortSignal): Promise<DashboardOverviewResponse> {
  const response = await fetch(apiUrl("/dashboard/overview"), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to load dashboard overview (${response.status})`));
  }
  return (await response.json()) as DashboardOverviewResponse;
}

export async function fetchAuditEvents(filters: AuditEventFilters = {}, signal?: AbortSignal): Promise<ApiAuditEvent[]> {
  const query = new URLSearchParams();
  if (typeof filters.limit === "number") {
    query.set("limit", String(filters.limit));
  }
  if (filters.principal_id) {
    query.set("principal_id", filters.principal_id);
  }
  if (filters.action_prefix) {
    query.set("action_prefix", filters.action_prefix);
  }
  if (filters.outcome) {
    query.set("outcome", filters.outcome);
  }
  if (filters.target_id) {
    query.set("target_id", filters.target_id);
  }

  const suffix = query.toString();
  const response = await fetch(apiUrl(`/audit/events${suffix ? `?${suffix}` : ""}`), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to load audit events (${response.status})`));
  }
  return ((await response.json()) as AuditEventResponse).events;
}

export function buildDetectionFrameUrl(detectionId: string): string {
  return mediaUrl(`/detections/${encodeURIComponent(detectionId)}/frame`);
}

export function buildDetectionPlateCropUrl(detectionId: string): string {
  return mediaUrl(`/detections/${encodeURIComponent(detectionId)}/plate-crop`);
}

async function fetchMediaObjectUrl(path: string, signal?: AbortSignal): Promise<string> {
  const response = await fetch(apiUrl(path), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to load media (${response.status})`));
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export async function fetchDetectionFrameObjectUrl(detectionId: string, signal?: AbortSignal): Promise<string> {
  return fetchMediaObjectUrl(`/detections/${encodeURIComponent(detectionId)}/frame`, signal);
}

export async function fetchDetectionPlateCropObjectUrl(detectionId: string, signal?: AbortSignal): Promise<string> {
  return fetchMediaObjectUrl(`/detections/${encodeURIComponent(detectionId)}/plate-crop`, signal);
}

export async function fetchDemoRuntimeStatus(signal?: AbortSignal): Promise<DemoRuntimeStatus> {
  const response = await fetch(apiUrl("/demo/runtime"), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to load demo runtime status (${response.status})`));
  }
  return (await response.json()) as DemoRuntimeStatus;
}

export async function startDemoRun(submission: DemoRunSubmission): Promise<DemoRuntimeStatus> {
  const response = await fetch(apiUrl("/demo/runs"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to start demo run (${response.status})`));
  }
  return (await response.json()) as DemoRuntimeStatus;
}

export async function fetchHotlists(signal?: AbortSignal): Promise<DashboardHotlist[]> {
  const response = await fetch(apiUrl("/hotlists?limit=100"), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to load hotlists (${response.status})`));
  }
  return (await response.json()) as DashboardHotlist[];
}

export async function createHotlist(submission: HotlistSubmission): Promise<DashboardHotlist> {
  const response = await fetch(apiUrl("/hotlists"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(`Failed to save hotlist (${response.status})`);
  }
  return (await response.json()) as DashboardHotlist;
}

export async function updateHotlist(entryId: string, submission: HotlistSubmission): Promise<DashboardHotlist> {
  const response = await fetch(apiUrl(`/hotlists/${encodeURIComponent(entryId)}`), {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(`Failed to update hotlist (${response.status})`);
  }
  return (await response.json()) as DashboardHotlist;
}

export async function deleteHotlist(entryId: string): Promise<void> {
  const response = await fetch(apiUrl(`/hotlists/${encodeURIComponent(entryId)}`), {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to delete hotlist (${response.status})`));
  }
}

export async function updateAlert(entryId: string, submission: AlertUpdateSubmission): Promise<DashboardAlert> {
  const response = await fetch(apiUrl(`/alerts/${encodeURIComponent(entryId)}`), {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to update alert (${response.status})`));
  }
  return (await response.json()) as DashboardAlert;
}

export async function fetchReviews(detectionId: string, signal?: AbortSignal): Promise<ReviewRecord[]> {
  const response = await fetch(apiUrl(`/reviews/${encodeURIComponent(detectionId)}`), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to load reviews (${response.status})`));
  }
  return (await response.json()) as ReviewRecord[];
}

export async function createReview(detectionId: string, submission: ReviewSubmission): Promise<ReviewRecord> {
  const response = await fetch(apiUrl(`/reviews/${encodeURIComponent(detectionId)}`), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to save review (${response.status})`));
  }
  return (await response.json()) as ReviewRecord;
}

export async function createFollowUp(submission: FollowUpSubmission): Promise<FollowUpRecord> {
  const response = await fetch(apiUrl("/follow-ups"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to save follow-up (${response.status})`));
  }
  return (await response.json()) as FollowUpRecord;
}

export async function updateFollowUp(followUpId: string, submission: FollowUpSubmission): Promise<FollowUpRecord> {
  const response = await fetch(apiUrl(`/follow-ups/${encodeURIComponent(followUpId)}`), {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to update follow-up (${response.status})`));
  }
  return (await response.json()) as FollowUpRecord;
}

export async function createDispatchAssignment(
  submission: DispatchAssignmentSubmission,
): Promise<DispatchAssignmentRecord> {
  const response = await fetch(apiUrl("/assignments"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to save assignment (${response.status})`));
  }
  return (await response.json()) as DispatchAssignmentRecord;
}

export async function updateDispatchAssignment(
  assignmentId: string,
  submission: DispatchAssignmentSubmission,
): Promise<DispatchAssignmentRecord> {
  const response = await fetch(apiUrl(`/assignments/${encodeURIComponent(assignmentId)}`), {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to update assignment (${response.status})`));
  }
  return (await response.json()) as DispatchAssignmentRecord;
}

export async function sendOperatorSessionHeartbeat(
  submission: OperatorSessionHeartbeatSubmission,
  signal?: AbortSignal,
): Promise<OperatorSessionRecord> {
  const response = await fetch(apiUrl("/operator/sessions/heartbeat"), {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to update operator session (${response.status})`));
  }
  return (await response.json()) as OperatorSessionRecord;
}

export async function searchDetections(
  filters: DetectionSearchFilters,
  signal?: AbortSignal,
): Promise<DetectionSearchResult> {
  const query = new URLSearchParams();

  const addIfPresent = (key: string, value: string | number | null | undefined): void => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    query.set(key, String(value));
  };

  addIfPresent("plate", filters.plate?.trim());
  addIfPresent("plate_match", filters.plate_match);
  addIfPresent("start_utc", filters.start_utc);
  addIfPresent("end_utc", filters.end_utc);
  addIfPresent("camera_id", filters.camera_id);
  addIfPresent("min_latitude", filters.min_latitude);
  addIfPresent("max_latitude", filters.max_latitude);
  addIfPresent("min_longitude", filters.min_longitude);
  addIfPresent("max_longitude", filters.max_longitude);
  addIfPresent("vehicle_color", filters.vehicle_color?.trim());
  addIfPresent("vehicle_make", filters.vehicle_make?.trim());
  addIfPresent("vehicle_model", filters.vehicle_model?.trim());
  addIfPresent("vehicle_year", filters.vehicle_year?.trim());
  addIfPresent("alert_status", filters.alert_status);
  addIfPresent("limit", filters.limit);
  addIfPresent("offset", filters.offset);

  const response = await fetch(apiUrl(`/search/detections?${query.toString()}`), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to search detections (${response.status})`));
  }
  return (await response.json()) as DetectionSearchResult;
}

export interface AlertSearchFilters {
  plate?: string;
  plate_match?: SearchPlateMatchMode;
  start_utc?: string;
  end_utc?: string;
  camera_id?: string;
  min_latitude?: number;
  max_latitude?: number;
  min_longitude?: number;
  max_longitude?: number;
  vehicle_color?: string;
  vehicle_make?: string;
  vehicle_model?: string;
  vehicle_year?: string;
  status?: DashboardAlertStatus;
  limit?: number;
  offset?: number;
}

export interface AlertSearchResult {
  page: SearchPageInfo;
  results: DashboardAlert[];
}

export async function searchAlerts(
  filters: AlertSearchFilters,
  signal?: AbortSignal,
): Promise<AlertSearchResult> {
  const query = new URLSearchParams();

  const addIfPresent = (key: string, value: string | number | null | undefined): void => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    query.set(key, String(value));
  };

  addIfPresent("plate", filters.plate?.trim());
  addIfPresent("plate_match", filters.plate_match);
  addIfPresent("start_utc", filters.start_utc);
  addIfPresent("end_utc", filters.end_utc);
  addIfPresent("camera_id", filters.camera_id);
  addIfPresent("min_latitude", filters.min_latitude);
  addIfPresent("max_latitude", filters.max_latitude);
  addIfPresent("min_longitude", filters.min_longitude);
  addIfPresent("max_longitude", filters.max_longitude);
  addIfPresent("vehicle_color", filters.vehicle_color?.trim());
  addIfPresent("vehicle_make", filters.vehicle_make?.trim());
  addIfPresent("vehicle_model", filters.vehicle_model?.trim());
  addIfPresent("vehicle_year", filters.vehicle_year?.trim());
  addIfPresent("status", filters.status);
  addIfPresent("limit", filters.limit);
  addIfPresent("offset", filters.offset);

  const response = await fetch(apiUrl(`/search/alerts?${query.toString()}`), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to search alerts (${response.status})`));
  }
  return (await response.json()) as AlertSearchResult;
}

export function mapOverviewToAlertItems(
  overview: DashboardOverviewResponse,
  fallbackAlerts: AlertItem[],
): AlertItem[] {
  if (overview.alerts.length === 0) {
    return fallbackAlerts;
  }

  const detectionsById = new Map(overview.detections.map((record) => [record.detection_id, record]));

  return sortAlerts(overview.alerts).map((alert) => {
    const detection = detectionsById.get(alert.detection_id);
    const gps = formatGps(alert.gps_latitude ?? detection?.gps_latitude, alert.gps_longitude ?? detection?.gps_longitude);
    const severity = alert.status === "active" ? "critical" : alert.status === "acknowledged" ? "priority" : "watch";
    const scenario = alert.status === "active" ? "tow_ready" : alert.status === "acknowledged" ? "visual_match" : "assignment";
    const status = alert.status === "active" ? "monitoring" : alert.status === "acknowledged" ? "onsite" : "cleared";
    const routeAction = alert.status === "active" ? "Acknowledge" : alert.status === "acknowledged" ? "Stand down" : "Re-open";
    const fieldNotes = [`${titleCase(alert.match_type)} match`, alert.notes, alert.response_notes].filter(Boolean).join(" \u00b7 ");
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
      routeAction,
      location: gps,
      distance: "Live API",
      notes: fieldNotes || `Hotlist: ${alert.hotlist_label ?? "Unlabeled entry"}`,
      bestApproach: "Use the nearest safe lane and visually confirm before engagement.",
    };
  });
}

export function mapOverviewToRecoveryLog(overview: DashboardOverviewResponse): RecoveryLogEntry[] {
  const detectionsById = new Map(overview.detections.map((record) => [record.detection_id, record]));

  return sortAlerts(overview.alerts)
    .slice(0, 6)
    .map((alert) => {
      const detection = detectionsById.get(alert.detection_id);
      return {
        id: alert.alert_id,
        status: recoveryLogStatus(alert.status),
        title: alert.hotlist_label ?? buildVehicleLabel(detection, alert),
        plate: alert.matched_plate_text,
        updatedAt: formatTime(alert.updated_at_utc ?? alert.timestamp_utc),
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
