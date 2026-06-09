export type HealthState = "ok" | "degraded" | "down";

export interface HealthDependency {
  name: string;
  state: HealthState;
  latency_ms: number | null;
  message: string | null;
}

export interface HealthResponse {
  service: string;
  version: string;
  state: HealthState;
  timestamp_utc: string;
  dependencies: HealthDependency[];
  uptime_seconds: number | null;
}

export type CameraHealthStatus = "online" | "offline" | "unknown";

export interface DashboardCameraHealth {
  camera_id: string;
  label: string;
  status: CameraHealthStatus;
  last_seen_at_utc: string | null;
  fps: number | null;
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
  plate_text: string | null;
  vin: string | null;
  vehicle_year: string | null;
  vehicle_make: string | null;
  vehicle_model: string | null;
  vehicle_color: string | null;
  address_label: string | null;
  address_line1: string | null;
  address_line2: string | null;
  address_city: string | null;
  address_state: string | null;
  address_postal_code: string | null;
  address_latitude: number | null;
  address_longitude: number | null;
  label: string | null;
  notes: string | null;
  active: boolean;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface HotlistSubmission {
  plate_text?: string;
  vin?: string;
  vehicle_year?: string;
  vehicle_make?: string;
  vehicle_model?: string;
  vehicle_color?: string;
  address_label?: string;
  address_line1?: string;
  address_line2?: string;
  address_city?: string;
  address_state?: string;
  address_postal_code?: string;
  address_latitude?: number;
  address_longitude?: number;
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
  can_control_edge_runtime: boolean;
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
  destination_label: string | null;
  arrival_radius_feet: number | null;
  current_distance_feet: number | null;
  idle_scan_enabled: boolean;
  visible_map_layers: string[];
  navigation_active: boolean;
  scan_state: ScanSessionState;
  scan_processing_mode: ScanProcessingMode;
  lpr_realtime_enabled: boolean;
  vehicle_enrichment_deferred: boolean;
  primary_ai_camera_id: string | null;
  secondary_context_camera_id: string | null;
  last_seen_at_utc: string;
}

export type ScanSessionState =
  | "idle"
  | "approaching_radius"
  | "active_lpr_scan"
  | "post_scan_vehicle_enrichment"
  | "completed";
export type ScanProcessingMode = "standby" | "realtime_lpr" | "deferred_vehicle_recognition";

export interface OperatorSessionHeartbeatSubmission {
  session_id: string;
  client_label?: string;
  workspace: string;
  selected_detection_id?: string;
  selected_alert_id?: string;
  destination_label?: string;
  arrival_radius_feet?: number;
  current_distance_feet?: number;
  idle_scan_enabled?: boolean;
  visible_map_layers?: string[];
  navigation_active: boolean;
  scan_state?: ScanSessionState;
  scan_processing_mode?: ScanProcessingMode;
  lpr_realtime_enabled?: boolean;
  vehicle_enrichment_deferred?: boolean;
  primary_ai_camera_id?: string;
  secondary_context_camera_id?: string;
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

export type EdgeCaptureState = "stopped" | "starting" | "running" | "stopping" | "degraded" | "faulted" | "unknown";
export type EdgeRuntimeCommand = "start_capture" | "stop_capture" | "restart_capture" | "mark_faulted";

export interface EdgeRuntimeStatus {
  edge_node_id: string;
  capture_state: EdgeCaptureState;
  desired_capture_state: EdgeCaptureState;
  last_command: EdgeRuntimeCommand | null;
  last_commanded_by: string | null;
  last_commanded_at_utc: string | null;
  last_heartbeat_at_utc: string | null;
  active_camera_count: number;
  total_camera_count: number;
  inference_runtime: string | null;
  plate_ocr_provider: string | null;
  vehicle_attribute_provider: string | null;
  scan_state: ScanSessionState;
  scan_processing_mode: ScanProcessingMode;
  primary_ai_camera_id: string | null;
  secondary_context_camera_id: string | null;
  realtime_lpr_enabled: boolean;
  deferred_vehicle_recognition_enabled: boolean;
  message: string | null;
}

export interface EdgeRuntimeCommandSubmission {
  command: EdgeRuntimeCommand;
  operator_id?: string;
  reason?: string;
}

export interface DashboardOverviewResponse {
  generated_at_utc: string;
  health: HealthResponse;
  camera_health: DashboardCameraHealth[];
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
  geo_shape?: "circle" | "polygon";
  geo_center_latitude?: number;
  geo_center_longitude?: number;
  geo_radius_meters?: number;
  geo_polygon_latitude?: number[];
  geo_polygon_longitude?: number[];
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

export interface AddressAreaContext {
  owner_occupied_pct: number | null;
  renter_occupied_pct: number | null;
  vacancy_pct: number | null;
  total_housing_units: number | null;
  summary: string | null;
}

export interface AddressIntelligenceReport {
  query_address: string;
  generated_at_utc: string;
  matched: boolean;
  match_quality: "exact" | "approximate" | "none";
  standardized_address: string | null;
  latitude: number | null;
  longitude: number | null;
  state_fips: string | null;
  county_name: string | null;
  census_tract: string | null;
  block_geoid: string | null;
  dwelling_type: "single_family" | "multi_unit" | "commercial" | "vacant_land" | "unknown";
  dwelling_evidence: string[];
  area_context: AddressAreaContext | null;
  data_sources: string[];
  caveats: string[];
  from_cache: boolean;
}

export async function fetchAddressIntelligence(
  address: string,
  coords?: { lat: number; lng: number } | null,
  signal?: AbortSignal,
): Promise<AddressIntelligenceReport> {
  const params = new URLSearchParams({ address });
  if (coords) {
    params.set("latitude", String(coords.lat));
    params.set("longitude", String(coords.lng));
  }
  const response = await fetch(apiUrl(`/address-intelligence?${params.toString()}`), {
    signal,
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to load address intelligence (${response.status})`));
  }
  return (await response.json()) as AddressIntelligenceReport;
}

export type OccupantLookupStatus =
  | "ok"
  | "no_match"
  | "unavailable"
  | "offline"
  | "disabled"
  | "unconfigured";

export interface Occupant {
  name: string;
  phones: string[];
  associated_people: string[];
  is_current: boolean;
  previous_addresses: string[];
}

export interface OccupantIntelligenceReport {
  lookup_address: string;
  generated_at_utc: string;
  status: OccupantLookupStatus;
  source: string | null;
  high_confidence: Occupant[];
  other_possible: Occupant[];
  previous_addresses: string[];
  from_cache: boolean;
  cache_age_days: number | null;
  address: AddressIntelligenceReport | null;
  caveats: string[];
}

export async function fetchOccupantIntelligence(
  address: string,
  coords?: { lat: number; lng: number } | null,
  signal?: AbortSignal,
): Promise<OccupantIntelligenceReport> {
  const params = new URLSearchParams({ address });
  if (coords) {
    params.set("latitude", String(coords.lat));
    params.set("longitude", String(coords.lng));
  }
  const response = await fetch(apiUrl(`/occupant-intelligence?${params.toString()}`), {
    signal,
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to load occupant intelligence (${response.status})`));
  }
  return (await response.json()) as OccupantIntelligenceReport;
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

export async function fetchEdgeRuntimeStatus(signal?: AbortSignal): Promise<EdgeRuntimeStatus> {
  const response = await fetch(apiUrl("/edge/runtime"), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to load edge runtime status (${response.status})`));
  }
  return (await response.json()) as EdgeRuntimeStatus;
}

export async function sendEdgeRuntimeCommand(submission: EdgeRuntimeCommandSubmission): Promise<EdgeRuntimeStatus> {
  const response = await fetch(apiUrl("/edge/runtime/command"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(submission),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to command edge runtime (${response.status})`));
  }
  return (await response.json()) as EdgeRuntimeStatus;
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
    throw new Error(await responseErrorMessage(response, `Failed to save hotlist (${response.status})`));
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
    throw new Error(await responseErrorMessage(response, `Failed to update hotlist (${response.status})`));
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

  const appendAll = (key: string, values: number[] | undefined): void => {
    values?.forEach((value) => {
      if (value !== null && value !== undefined && !Number.isNaN(value)) {
        query.append(key, String(value));
      }
    });
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
  addIfPresent("geo_shape", filters.geo_shape);
  addIfPresent("geo_center_latitude", filters.geo_center_latitude);
  addIfPresent("geo_center_longitude", filters.geo_center_longitude);
  addIfPresent("geo_radius_meters", filters.geo_radius_meters);
  appendAll("geo_polygon_latitude", filters.geo_polygon_latitude);
  appendAll("geo_polygon_longitude", filters.geo_polygon_longitude);
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
  geo_shape?: "circle" | "polygon";
  geo_center_latitude?: number;
  geo_center_longitude?: number;
  geo_radius_meters?: number;
  geo_polygon_latitude?: number[];
  geo_polygon_longitude?: number[];
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

export interface AddressSearchSuggestion {
  suggestion_id: string;
  display_name: string;
  latitude: number;
  longitude: number;
  provider: string;
}

export interface AddressSearchResult {
  results: AddressSearchSuggestion[];
}

export interface ReverseAddressResult {
  display_name: string;
  latitude: number;
  longitude: number;
  house_number: string | null;
  road: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  provider: string;
}

export interface AddressSearchOptions {
  bias_latitude?: number;
  bias_longitude?: number;
  limit?: number;
  signal?: AbortSignal;
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

  const appendAll = (key: string, values: number[] | undefined): void => {
    values?.forEach((value) => {
      if (value !== null && value !== undefined && !Number.isNaN(value)) {
        query.append(key, String(value));
      }
    });
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
  addIfPresent("geo_shape", filters.geo_shape);
  addIfPresent("geo_center_latitude", filters.geo_center_latitude);
  addIfPresent("geo_center_longitude", filters.geo_center_longitude);
  addIfPresent("geo_radius_meters", filters.geo_radius_meters);
  appendAll("geo_polygon_latitude", filters.geo_polygon_latitude);
  appendAll("geo_polygon_longitude", filters.geo_polygon_longitude);
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

export async function searchAddresses(
  query: string,
  options: AddressSearchOptions = {},
): Promise<AddressSearchResult> {
  const { bias_latitude, bias_longitude, limit = 8, signal } = options;
  const params = new URLSearchParams({
    q: query.trim(),
    limit: String(limit),
  });
  if (bias_latitude !== undefined && !Number.isNaN(bias_latitude)) {
    params.set("bias_latitude", String(bias_latitude));
  }
  if (bias_longitude !== undefined && !Number.isNaN(bias_longitude)) {
    params.set("bias_longitude", String(bias_longitude));
  }
  const response = await fetch(apiUrl(`/search/addresses?${params.toString()}`), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to search addresses (${response.status})`));
  }
  return (await response.json()) as AddressSearchResult;
}

export async function reverseAddressLookup(
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
): Promise<ReverseAddressResult> {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
  });
  const response = await fetch(apiUrl(`/search/reverse-address?${params.toString()}`), { signal, headers: authHeaders() });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, `Failed to resolve current address (${response.status})`));
  }
  return (await response.json()) as ReverseAddressResult;
}

