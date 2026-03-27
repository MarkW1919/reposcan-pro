import { startTransition, useEffect, useRef, useState, type CSSProperties, type FormEvent, type ReactElement, type ReactNode } from "react";
import { MapContainer, TileLayer, Marker, Popup, Circle, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  addressScanDetections,
  alerts,
  cameraFeeds,
  dashboardPresets,
  demoChatMessages,
  detectionPopupTypeLabels,
  defaultFieldSettings,
  hotlistPopupDetections,
  layoutSlotLabels,
  panelCatalog,
  presetDescriptions,
  recoveryLog,
  scenarioLabels,
  statusLabels,
  workspaceTabs,
  type AlertItem,
  type CameraMode,
  type CrewChatMessage,
  type DetectionPopupEvent,
  type DashboardLayout,
  type FieldSettings,
  type LayoutPresetId,
  type PanelId,
  type SlotId,
  type WorkspaceId,
} from "./demo-data";
import {
  createDispatchAssignment,
  createFollowUp,
  createHotlist,
  createReview,
  fetchDetectionFrameObjectUrl,
  fetchDetectionPlateCropObjectUrl,
  fetchDemoRuntimeStatus,
  fetchHotlists,
  fetchReviews,
  fetchDashboardOverview,
  mapOverviewToAlertItems,
  mapOverviewToPopupHistory,
  mapOverviewToRecoveryLog,
  searchDetections,
  sendOperatorSessionHeartbeat,
  setApiClientConfig,
  startDemoRun,
  updateAlert,
  updateDispatchAssignment,
  updateFollowUp,
  updateHotlist,
  type DispatchAssignmentPriority,
  type DispatchAssignmentRecord,
  type DispatchAssignmentStatus,
  type DashboardAlert,
  type DashboardDetection,
  type DemoRuntimeStatus as DemoRuntimeStatusRecord,
  type DashboardHotlist,
  type DashboardOverviewResponse,
  type FollowUpPriority,
  type FollowUpRecord,
  type FollowUpStatus,
  type OperatorCapabilities,
  type OperatorPrincipal,
  type OperatorSessionRecord,
  type ReviewAction,
  type ReviewRecord,
  type SearchPlateMatchMode,
} from "./live-api";

const layoutStorageKey = "reposcan.ui.dashboard-layout.v1";
const settingsStorageKey = "reposcan.ui.field-settings.v1";
const apiKeyStorageKey = "reposcan.ui.api-key.v1";
const sessionLabelStorageKey = "reposcan.ui.session-label.v1";
const operatorSessionIdStorageKey = "reposcan.ui.operator-session-id.v1";
const defaultPopupHistory: DetectionPopupEvent[] = [hotlistPopupDetections[0], addressScanDetections[0]];
const demoOperatorCapabilities: OperatorCapabilities = {
  can_submit_reviews: true,
  can_update_alerts: true,
  can_manage_hotlists: true,
  can_manage_follow_ups: true,
  can_manage_dispatch: true,
  can_start_demo_runs: true,
  can_view_audit: true,
};
const demoOperatorPrincipal: OperatorPrincipal = {
  principal_id: "local_dev",
  display_name: "Local Development",
  authenticated: false,
  roles: ["viewer", "operator", "admin", "integrator"],
  capabilities: demoOperatorCapabilities,
};

interface PopupNotification extends DetectionPopupEvent {
  instanceId: string;
}

interface SearchFormState {
  plate: string;
  plateMatch: SearchPlateMatchMode;
  startUtc: string;
  endUtc: string;
  cameraId: string;
  minLatitude: string;
  maxLatitude: string;
  minLongitude: string;
  maxLongitude: string;
  vehicleColor: string;
  vehicleMake: string;
  vehicleModel: string;
  vehicleYear: string;
  alertStatus: DashboardAlert["status"] | "";
}

type RouteStageState = "done" | "active" | "queued";

interface RouteStageItem {
  id: string;
  label: string;
  detail: string;
  state: RouteStageState;
}

type DashboardScreenId = "drive" | "queue" | "recover" | "crew";
type QueueViewId = "hotlist" | "radius" | "popups";
type TargetPanelTabId = "overview" | "workflow" | "reviews";

const dashboardScreenOptions: Array<{ id: DashboardScreenId; label: string; summary: string }> = [
  { id: "drive", label: "Drive", summary: "Route, radius trigger, and live vehicle detection state while rolling." },
  { id: "queue", label: "Queue", summary: "Hotlist matches and in-radius detections ready for a decision." },
  { id: "recover", label: "Recover", summary: "Target evidence, dispatch, and on-scene recovery workflow." },
  { id: "crew", label: "Crew", summary: "Case log, handoff notes, and field evidence captured by the team." },
];

const queueViewOptions: Array<{ id: QueueViewId; label: string }> = [
  { id: "hotlist", label: "Hotlist" },
  { id: "radius", label: "Radius detections" },
  { id: "popups", label: "Popup log" },
];

const targetPanelTabs: Array<{ id: TargetPanelTabId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "workflow", label: "Workflow" },
  { id: "reviews", label: "Reviews" },
];

function loadStoredString(key: string, fallback = ""): string {
  if (typeof window === "undefined") {
    return fallback;
  }

  try {
    const raw = window.localStorage.getItem(key);
    return raw ?? fallback;
  } catch {
    return fallback;
  }
}

function loadOrCreateOperatorSessionId(): string {
  if (typeof window === "undefined") {
    return "session_local_dev";
  }

  try {
    const existing = window.localStorage.getItem(operatorSessionIdStorageKey);
    if (existing && existing.trim()) {
      return existing;
    }
    const created = `session_${Math.random().toString(16).slice(2, 10)}`;
    window.localStorage.setItem(operatorSessionIdStorageKey, created);
    return created;
  } catch {
    return `session_${Math.random().toString(16).slice(2, 10)}`;
  }
}

function cloneLayout(layout: DashboardLayout): DashboardLayout {
  return {
    profile: layout.profile,
    cameraMode: layout.cameraMode,
    slots: { ...layout.slots },
  };
}

function loadLayout(): DashboardLayout {
  if (typeof window === "undefined") {
    return cloneLayout(dashboardPresets.route);
  }

  try {
    const raw = window.localStorage.getItem(layoutStorageKey);
    if (!raw) {
      return cloneLayout(dashboardPresets.route);
    }

    const parsed = JSON.parse(raw) as Partial<DashboardLayout>;
    const preset = cloneLayout(dashboardPresets.route);
    const nextSlots = { ...preset.slots };

    if (parsed.slots && typeof parsed.slots === "object") {
      for (const slot of Object.keys(nextSlots) as SlotId[]) {
        const candidate = parsed.slots[slot];
        if (candidate && candidate in panelCatalog) {
          nextSlots[slot] = candidate as PanelId;
        }
      }
    }

    return {
      profile: typeof parsed.profile === "string" && parsed.profile.trim() ? parsed.profile : preset.profile,
      cameraMode:
        parsed.cameraMode === "priority" || parsed.cameraMode === "quad" || parsed.cameraMode === "strip" || parsed.cameraMode === "dual"
          ? parsed.cameraMode
          : preset.cameraMode,
      slots: nextSlots,
    };
  } catch {
    return cloneLayout(dashboardPresets.route);
  }
}

function loadFieldSettings(): FieldSettings {
  if (typeof window === "undefined") {
    return { ...defaultFieldSettings };
  }

  try {
    const raw = window.localStorage.getItem(settingsStorageKey);
    if (!raw) {
      return { ...defaultFieldSettings };
    }

    const parsed = JSON.parse(raw) as Partial<FieldSettings>;
    return {
      targetRefreshInterval:
        typeof parsed.targetRefreshInterval === "string" && parsed.targetRefreshInterval.trim()
          ? parsed.targetRefreshInterval
          : defaultFieldSettings.targetRefreshInterval,
      arrivalTriggerDistance:
        typeof parsed.arrivalTriggerDistance === "number"
          ? parsed.arrivalTriggerDistance
          : defaultFieldSettings.arrivalTriggerDistance,
      routeTrafficOverlay:
        typeof parsed.routeTrafficOverlay === "boolean"
          ? parsed.routeTrafficOverlay
          : defaultFieldSettings.routeTrafficOverlay,
      ocrConfidenceThreshold:
        typeof parsed.ocrConfidenceThreshold === "number"
          ? parsed.ocrConfidenceThreshold
          : defaultFieldSettings.ocrConfidenceThreshold,
      maxActiveTargets:
        typeof parsed.maxActiveTargets === "number"
          ? parsed.maxActiveTargets
          : defaultFieldSettings.maxActiveTargets,
      autoMarkOnScene:
        typeof parsed.autoMarkOnScene === "boolean"
          ? parsed.autoMarkOnScene
          : defaultFieldSettings.autoMarkOnScene,
      silentShiftMode:
        typeof parsed.silentShiftMode === "boolean" ? parsed.silentShiftMode : defaultFieldSettings.silentShiftMode,
      lowStorageWarning:
        typeof parsed.lowStorageWarning === "boolean"
          ? parsed.lowStorageWarning
          : defaultFieldSettings.lowStorageWarning,
    };
  } catch {
    return { ...defaultFieldSettings };
  }
}

function confidenceLabel(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function severityTone(value: AlertItem["severity"]): string {
  if (value === "critical") {
    return "critical";
  }
  if (value === "priority") {
    return "priority";
  }
  return "watch";
}

function followUpPriorityTone(value: FollowUpPriority): string {
  if (value === "critical") {
    return "critical";
  }
  if (value === "priority") {
    return "priority";
  }
  return "muted";
}

function assignmentPriorityTone(value: DispatchAssignmentPriority): string {
  if (value === "critical") {
    return "critical";
  }
  if (value === "priority") {
    return "priority";
  }
  return "muted";
}

function followUpStatusLabel(value: FollowUpStatus): string {
  switch (value) {
    case "open":
      return "Open";
    case "monitoring":
      return "Monitoring";
    case "resolved":
      return "Resolved";
  }
}

function followUpStatusTone(value: FollowUpStatus): string {
  switch (value) {
    case "open":
      return "badge--critical";
    case "monitoring":
      return "badge--priority";
    case "resolved":
      return "badge--good";
  }
}

function assignmentStatusLabel(value: DispatchAssignmentStatus): string {
  switch (value) {
    case "queued":
      return "Queued";
    case "assigned":
      return "Assigned";
    case "en_route":
      return "En Route";
    case "onsite":
      return "On Scene";
    case "completed":
      return "Completed";
    case "cancelled":
      return "Cancelled";
  }
}

function assignmentStatusTone(value: DispatchAssignmentStatus): string {
  switch (value) {
    case "completed":
      return "badge--good";
    case "cancelled":
      return "badge--muted";
    case "onsite":
      return "badge--critical";
    case "en_route":
      return "badge--priority";
    default:
      return "badge--outlined";
  }
}

function operatorRoleLabel(role: OperatorSessionRecord["roles"][number]): string {
  switch (role) {
    case "admin":
      return "Admin";
    case "operator":
      return "Operator";
    case "integrator":
      return "Integrator";
    default:
      return "Viewer";
  }
}

function operatorDisplayName(record: Pick<OperatorPrincipal, "display_name" | "principal_id">): string {
  return record.display_name?.trim() || record.principal_id;
}

function workspaceLabel(workspaceId: string): string {
  return workspaceTabs.find((tab) => tab.id === workspaceId)?.label ?? titleCaseLabel(workspaceId) ?? workspaceId;
}

function routeStageTone(state: RouteStageState): string {
  switch (state) {
    case "done":
      return "badge--good";
    case "active":
      return "badge--priority";
    case "queued":
      return "badge--muted";
  }
}

function formatEtaFromFeet(feet: number, navigationActive: boolean): string {
  if (!navigationActive) {
    return "Standby";
  }
  if (feet <= 150) {
    return "<1 min";
  }
  const estimatedMinutes = Math.max(1, Math.round(feet / 850));
  return `${estimatedMinutes} min`;
}

function formatDistance(feet: number): string {
  if (feet >= 5280) {
    return `${(feet / 5280).toFixed(1)} mi`;
  }

  return `${feet} ft`;
}

function formatReviewTimestamp(timestampUtc: string): string {
  const parsed = new Date(timestampUtc);
  if (Number.isNaN(parsed.valueOf())) {
    return timestampUtc;
  }

  return parsed.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function reviewActionLabel(action: ReviewAction): string {
  switch (action) {
    case "confirm":
      return "Confirm";
    case "correct":
      return "Correct";
    case "flag":
      return "Flag";
    case "dismiss":
      return "Dismiss";
  }
}

function reviewActionBadgeTone(action: ReviewAction): string {
  switch (action) {
    case "confirm":
      return "badge--good";
    case "correct":
      return "badge--good";
    case "flag":
      return "badge--priority";
    case "dismiss":
      return "badge--muted";
  }
}

function formatHotlistTimestamp(timestampUtc: string): string {
  const parsed = new Date(timestampUtc);
  if (Number.isNaN(parsed.valueOf())) {
    return timestampUtc;
  }

  return parsed.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function demoRuntimeLabel(state: DemoRuntimeStatusRecord["state"] | undefined): string {
  switch (state) {
    case "running":
      return "Running";
    case "succeeded":
      return "Ready";
    case "failed":
      return "Failed";
    default:
      return "Idle";
  }
}

function demoRuntimeBadgeTone(state: DemoRuntimeStatusRecord["state"] | undefined): string {
  switch (state) {
    case "running":
      return "badge--priority";
    case "succeeded":
      return "badge--good";
    case "failed":
      return "badge--critical";
    default:
      return "badge--muted";
  }
}

function formatCameraLabel(cameraId: string | null | undefined): string {
  if (!cameraId) {
    return "Camera unavailable";
  }

  return cameraId
    .replace(/^cam_/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatGpsLabel(latitude: number | null | undefined, longitude: number | null | undefined): string {
  if (typeof latitude !== "number" || typeof longitude !== "number") {
    return "GPS unavailable";
  }

  return `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
}

function titleCaseLabel(value: string | null | undefined): string {
  if (!value) {
    return "";
  }

  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((segment) => segment[0].toUpperCase() + segment.slice(1).toLowerCase())
    .join(" ");
}

function buildDetectionVehicleLabel(detection: DashboardDetection | null | undefined, fallback: string): string {
  if (!detection) {
    return fallback;
  }

  const parts = [titleCaseLabel(detection.vehicle_color), titleCaseLabel(detection.vehicle_make), titleCaseLabel(detection.vehicle_model)].filter(
    Boolean,
  );
  return parts.join(" ") || fallback;
}

function buildDetectionColorYearLabel(detection: DashboardDetection | null | undefined, fallback: string): string {
  if (!detection) {
    return fallback;
  }

  const color = titleCaseLabel(detection.vehicle_color) || "Unknown";
  const year = detection.optional_vehicle_year ?? "Unknown";
  return `${color} / ${year}`;
}

function formatOptionalConfidence(value: number | null | undefined): string {
  return typeof value === "number" ? confidenceLabel(value) : "Unavailable";
}

function formatLocalDateTimeInput(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return "";
  }

  const offset = parsed.getTimezoneOffset();
  const local = new Date(parsed.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

function toUtcIsoString(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.valueOf())) {
    return undefined;
  }

  return parsed.toISOString();
}

function parseOptionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

const defaultSearchFormState: SearchFormState = {
  plate: "",
  plateMatch: "contains",
  startUtc: "",
  endUtc: "",
  cameraId: "",
  minLatitude: "",
  maxLatitude: "",
  minLongitude: "",
  maxLongitude: "",
  vehicleColor: "",
  vehicleMake: "",
  vehicleModel: "",
  vehicleYear: "",
  alertStatus: "",
};

function App() {
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceId>("dashboard");
  const [layout, setLayout] = useState<DashboardLayout>(() => loadLayout());
  const [fieldSettings, setFieldSettings] = useState<FieldSettings>(() => loadFieldSettings());
  const [dashboardScreen, setDashboardScreen] = useState<DashboardScreenId>("drive");
  const [queueView, setQueueView] = useState<QueueViewId>("hotlist");
  const [queuePage, setQueuePage] = useState(0);
  const [targetPanelTab, setTargetPanelTab] = useState<TargetPanelTabId>("overview");
  const [selectedAlertId, setSelectedAlertId] = useState<string>(alerts[0]?.id ?? "");
  const [focusedDetectionId, setFocusedDetectionId] = useState<string | null>(null);
  const [selectedCameraId, setSelectedCameraId] = useState<string>(cameraFeeds[0]?.id ?? "");
  const [destinationInput, setDestinationInput] = useState<string>(alerts[0]?.location ?? "");
  const [activeDestination, setActiveDestination] = useState<string>(alerts[0]?.location ?? "");
  const [navigationActive, setNavigationActive] = useState(false);
  const [addressDetectionEnabled, setAddressDetectionEnabled] = useState(true);
  const [currentDistanceFeet, setCurrentDistanceFeet] = useState(1400);
  const [popupStack, setPopupStack] = useState<PopupNotification[]>([]);
  const [popupHistory, setPopupHistory] = useState<DetectionPopupEvent[]>(defaultPopupHistory);
  const [addressPopupIndex, setAddressPopupIndex] = useState(0);
  const [hotlistPopupIndex, setHotlistPopupIndex] = useState(0);
  const [liveOverview, setLiveOverview] = useState<DashboardOverviewResponse | null>(null);
  const [apiKey, setApiKey] = useState<string>(() => loadStoredString(apiKeyStorageKey));
  const [sessionLabel, setSessionLabel] = useState<string>(() => loadStoredString(sessionLabelStorageKey, "cab_console_01"));
  const [operatorSessionError, setOperatorSessionError] = useState<string | null>(null);
  const [searchForm, setSearchForm] = useState<SearchFormState>(defaultSearchFormState);
  const [searchResults, setSearchResults] = useState<DashboardDetection[]>([]);
  const [searchTotalResults, setSearchTotalResults] = useState(0);
  const [searchOffset, setSearchOffset] = useState(0);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchExecuted, setSearchExecuted] = useState(false);
  const [liveDataSource, setLiveDataSource] = useState<"demo" | "live" | "fallback">("demo");
  const [liveError, setLiveError] = useState<string | null>(null);
  const [reviewHistory, setReviewHistory] = useState<ReviewRecord[]>([]);
  const [reviewAction, setReviewAction] = useState<ReviewAction>("confirm");
  const [reviewOperatorId, setReviewOperatorId] = useState("");
  const [reviewCorrectedPlate, setReviewCorrectedPlate] = useState(alerts[0]?.plate ?? "");
  const [reviewNotes, setReviewNotes] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewSuccess, setReviewSuccess] = useState<string | null>(null);
  const [followUpPriority, setFollowUpPriority] = useState<FollowUpPriority>("priority");
  const [followUpStatus, setFollowUpStatus] = useState<FollowUpStatus>("open");
  const [followUpAssignedOperatorId, setFollowUpAssignedOperatorId] = useState("");
  const [followUpSummary, setFollowUpSummary] = useState("");
  const [followUpNotes, setFollowUpNotes] = useState("");
  const [followUpDueAt, setFollowUpDueAt] = useState("");
  const [followUpSubmitting, setFollowUpSubmitting] = useState(false);
  const [followUpError, setFollowUpError] = useState<string | null>(null);
  const [followUpSuccess, setFollowUpSuccess] = useState<string | null>(null);
  const [assignmentPriority, setAssignmentPriority] = useState<DispatchAssignmentPriority>("priority");
  const [assignmentStatus, setAssignmentStatus] = useState<DispatchAssignmentStatus>("queued");
  const [assignmentOperatorId, setAssignmentOperatorId] = useState("");
  const [assignmentUnitLabel, setAssignmentUnitLabel] = useState("");
  const [assignmentDestination, setAssignmentDestination] = useState(alerts[0]?.location ?? "");
  const [assignmentSummary, setAssignmentSummary] = useState("");
  const [assignmentNotes, setAssignmentNotes] = useState("");
  const [assignmentSubmitting, setAssignmentSubmitting] = useState(false);
  const [assignmentError, setAssignmentError] = useState<string | null>(null);
  const [assignmentSuccess, setAssignmentSuccess] = useState<string | null>(null);
  const [alertActionOperatorId, setAlertActionOperatorId] = useState("");
  const [alertActionNotes, setAlertActionNotes] = useState("");
  const [alertActionSubmitting, setAlertActionSubmitting] = useState(false);
  const [alertActionPendingStatus, setAlertActionPendingStatus] = useState<DashboardAlert["status"] | null>(null);
  const [alertActionError, setAlertActionError] = useState<string | null>(null);
  const [alertActionSuccess, setAlertActionSuccess] = useState<string | null>(null);
  const [hotlistEntries, setHotlistEntries] = useState<DashboardHotlist[]>([]);
  const [selectedHotlistId, setSelectedHotlistId] = useState<string | null>(null);
  const [hotlistPlateText, setHotlistPlateText] = useState("");
  const [hotlistLabel, setHotlistLabel] = useState("");
  const [hotlistNotes, setHotlistNotes] = useState("");
  const [hotlistActive, setHotlistActive] = useState(true);
  const [hotlistLoading, setHotlistLoading] = useState(false);
  const [hotlistSaving, setHotlistSaving] = useState(false);
  const [hotlistError, setHotlistError] = useState<string | null>(null);
  const [hotlistSuccess, setHotlistSuccess] = useState<string | null>(null);
  const [demoRuntimeStatus, setDemoRuntimeStatus] = useState<DemoRuntimeStatusRecord | null>(null);
  const [demoFramesDirectory, setDemoFramesDirectory] = useState("");
  const [demoSequenceId, setDemoSequenceId] = useState("seq_console_demo");
  const [demoPlateText, setDemoPlateText] = useState(alerts[0]?.plate ?? "6BZN220");
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoSubmitting, setDemoSubmitting] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [demoSuccess, setDemoSuccess] = useState<string | null>(null);
  const [framePreviewUrl, setFramePreviewUrl] = useState<string | null>(null);
  const [plateCropPreviewUrl, setPlateCropPreviewUrl] = useState<string | null>(null);
  const [framePreviewUnavailable, setFramePreviewUnavailable] = useState(false);
  const [plateCropPreviewUnavailable, setPlateCropPreviewUnavailable] = useState(false);
  const [chatMessages, setChatMessages] = useState<CrewChatMessage[]>(demoChatMessages);
  const [chatDraftMessage, setChatDraftMessage] = useState("");
  const [fieldPhotoLog, setFieldPhotoLog] = useState<Array<{ id: string; label: string; timestamp: string; note: string }>>([]);
  const [fieldPhotoNote, setFieldPhotoNote] = useState("");
  const previousWithinArrivalRef = useRef(false);
  const queuedLivePopupIdsRef = useRef<Set<string>>(new Set());
  const previousAlertActionTargetRef = useRef<string | null>(null);
  const previousDemoRunStateRef = useRef<DemoRuntimeStatusRecord["state"]>("idle");
  const previousDemoRunIdRef = useRef<string | null>(null);
  const operatorSessionIdRef = useRef<string>(loadOrCreateOperatorSessionId());

  const operatorAlerts = liveOverview ? mapOverviewToAlertItems(liveOverview, alerts) : alerts;
  const detectionsById = new Map((liveOverview?.detections ?? []).map((record) => [record.detection_id, record]));
  const searchResultsById = new Map(searchResults.map((record) => [record.detection_id, record]));
  const selectedAlert = operatorAlerts.find((alert) => alert.id === selectedAlertId) ?? operatorAlerts[0];
  const selectedDetectionId = focusedDetectionId ?? selectedAlert?.detectionId ?? null;
  const selectedDetection =
    (selectedDetectionId ? searchResultsById.get(selectedDetectionId) ?? detectionsById.get(selectedDetectionId) : null) ?? null;
  const selectedLiveAlert =
    (selectedDetectionId ? liveOverview?.alerts.find((alert) => alert.detection_id === selectedDetectionId) ?? null : null) ??
    liveOverview?.alerts.find((alert) => alert.alert_id === selectedAlertId) ??
    null;
  const liveFollowUps = liveOverview?.follow_ups ?? [];
  const liveAssignments = liveOverview?.assignments ?? [];
  const activeSessions = liveOverview?.active_sessions ?? [];
  const currentOperator = liveOverview?.current_principal ?? demoOperatorPrincipal;
  const selectedFollowUp =
    (selectedDetectionId
      ? liveFollowUps.find((record) => record.detection_id === selectedDetectionId && record.status !== "resolved") ??
        liveFollowUps.find((record) => record.detection_id === selectedDetectionId) ??
        null
      : null) ?? null;
  const selectedAssignment =
    (selectedDetectionId
      ? liveAssignments.find(
          (record) =>
            record.detection_id === selectedDetectionId &&
            record.status !== "completed" &&
            record.status !== "cancelled",
        ) ??
        liveAssignments.find((record) => record.detection_id === selectedDetectionId) ??
        null
      : null) ?? null;
  const otherActiveSessions = activeSessions.filter((record) => record.session_id !== operatorSessionIdRef.current);
  const selectedHotlist = hotlistEntries.find((entry) => entry.entry_id === selectedHotlistId) ?? null;
  const selectedCamera = cameraFeeds.find((camera) => camera.id === selectedCameraId) ?? cameraFeeds[0];
  const onlineCameraCount = cameraFeeds.filter((camera) => camera.status === "Online").length;
  const liveHealthState = liveOverview?.health.state ?? "demo";
  const activeHotlistCount = liveOverview?.counts.active_hotlists ?? 0;
  const activeAlertCount = liveOverview?.counts.active_alerts ?? operatorAlerts.filter((alert) => alert.severity === "critical").length;
  const openFollowUpCount =
    liveOverview?.counts.open_follow_ups ?? liveFollowUps.filter((record) => record.status !== "resolved").length;
  const activeAssignmentCount =
    liveOverview?.counts.active_assignments ??
    liveAssignments.filter((record) => record.status !== "completed" && record.status !== "cancelled").length;
  const activeSessionCount = liveOverview?.counts.active_sessions ?? activeSessions.length;
  const recoveryLogEntries = liveOverview ? mapOverviewToRecoveryLog(liveOverview) : recoveryLog;
  const selectedAlertMatchesDetection = selectedDetectionId === null || selectedAlert?.detectionId === selectedDetectionId;
  const selectedDisplayPlate = selectedDetection?.plate_text ?? selectedLiveAlert?.matched_plate_text ?? selectedAlert?.plate ?? "Plate unavailable";
  const selectedDisplayVehicle = buildDetectionVehicleLabel(selectedDetection, selectedAlert?.vehicle ?? "Live vehicle");
  const selectedDisplayColorYear = buildDetectionColorYearLabel(selectedDetection, selectedAlert?.colorYear ?? "Unknown / Unknown");
  const selectedDisplayCamera = selectedDetection ? formatCameraLabel(selectedDetection.camera_id) : selectedAlert.camera;
  const selectedDisplayGps = selectedDetection
    ? formatGpsLabel(selectedDetection.gps_latitude, selectedDetection.gps_longitude)
    : selectedAlert.gps;
  const selectedDisplayConfidence = selectedDetection?.plate_confidence ?? selectedLiveAlert?.match_confidence ?? selectedAlert.confidence;
  const selectedDisplayPrimaryBadge = selectedAlertMatchesDetection
    ? scenarioLabels[selectedAlert.scenario]
    : selectedLiveAlert
      ? "Hotlist hit"
      : "Detection review";
  const selectedDisplaySecondaryBadge = selectedAlertMatchesDetection
    ? statusLabels[selectedAlert.status]
    : selectedAssignment
      ? assignmentStatusLabel(selectedAssignment.status)
      : selectedLiveAlert
        ? selectedLiveAlert.status
        : "No alert";
  const selectedDisplayBestApproach = selectedAlertMatchesDetection
    ? selectedAlert.bestApproach
    : selectedAssignment?.summary ??
      selectedFollowUp?.summary ??
      (selectedLiveAlert
        ? "Use the evidence frame and plate-crop confidence to confirm before escalating the live alert."
        : "Review OCR candidates, compare the crop, and pin only detections that need follow-up.");
  const selectedDisplayNotes = selectedAlertMatchesDetection
    ? selectedAlert.notes
    : selectedLiveAlert?.notes ??
      (selectedDetection
        ? `Frame ${selectedDetection.frame_number} / Sync status ${selectedDetection.sync_status}`
        : "Select a live detection to inspect OCR candidates and attribute confidence.");
  const searchCameraChoices = Array.from(
    new Set((liveOverview?.detections ?? []).map((record) => record.camera_id)),
  ).sort((left, right) => left.localeCompare(right));
  const knownHotlistPlates = new Set(
    [
      ...hotlistPopupDetections.map((event) => event.plate).filter((plate): plate is string => typeof plate === "string"),
      ...hotlistEntries.filter((entry) => entry.active).map((entry) => entry.plate_text),
    ].map((plate) => plate.toUpperCase()),
  );
  const selectedWorkflowNotes = selectedAssignment?.notes ?? selectedFollowUp?.notes ?? selectedDisplayNotes;
  const selectedIsHotlistMatch = selectedLiveAlert
    ? !!selectedLiveAlert.hotlist_entry_id
    : knownHotlistPlates.has(selectedDisplayPlate.toUpperCase());
  const selectedFramePreviewUrl = liveDataSource === "live" ? framePreviewUrl : null;
  const selectedPlateCropPreviewUrl = liveDataSource === "live" ? plateCropPreviewUrl : null;
  const withinArrivalRadius = navigationActive && currentDistanceFeet <= fieldSettings.arrivalTriggerDistance;
  const activeScanMode = withinArrivalRadius;
  const generalPopupsLive = navigationActive && addressDetectionEnabled && withinArrivalRadius;
  const currentDistanceLabel = formatDistance(currentDistanceFeet);
  const navigationModeLabel = activeScanMode ? "Active scan" : navigationActive ? "Transit monitor" : "Idle";
  const addressPopupPolicy = generalPopupsLive
    ? "General popups live"
    : addressDetectionEnabled
      ? "General popups suppressed"
      : "Address popups disabled";
  const radiusDetectionSummary = generalPopupsLive
    ? `All vehicles inside the ${fieldSettings.arrivalTriggerDistance} ft address radius are surfacing live.`
    : addressDetectionEnabled
      ? "Vehicles are still being classified in the background until the cab enters the arrival ring."
      : "Address-radius detection is paused by the operator. Hotlist alerts remain live.";
  const alertActionsAvailable = liveDataSource === "live" && selectedLiveAlert !== null;
  const alertActionsEnabled = alertActionsAvailable && currentOperator.capabilities.can_update_alerts;
  const reviewsEnabled = liveDataSource === "live" && selectedDetectionId !== null;
  const hotlistsEnabled = liveDataSource === "live";
  const demoRuntimeEnabled = liveDataSource === "live";
  const latestReview = reviewHistory[0] ?? null;
  const canSubmitReview =
    reviewsEnabled &&
    currentOperator.capabilities.can_submit_reviews &&
    !reviewSubmitting &&
    (reviewAction !== "correct" || reviewCorrectedPlate.trim().length > 0);
  const canManageFollowUps =
    liveDataSource === "live" && currentOperator.capabilities.can_manage_follow_ups && selectedDetectionId !== null;
  const canManageAssignments =
    liveDataSource === "live" && currentOperator.capabilities.can_manage_dispatch && selectedDetectionId !== null;
  const canSubmitHotlist =
    hotlistsEnabled &&
    currentOperator.capabilities.can_manage_hotlists &&
    !hotlistSaving &&
    hotlistPlateText.trim().length > 0;
  const canStartDemoRun =
    demoRuntimeEnabled &&
    currentOperator.capabilities.can_start_demo_runs &&
    !demoSubmitting &&
    demoFramesDirectory.trim().length > 0 &&
    demoRuntimeStatus?.state !== "running";
  const routeProgressPercent = Math.min(100, (Math.max(0, 1760 - currentDistanceFeet) / 1760) * 100);
  const routeEtaLabel = formatEtaFromFeet(currentDistanceFeet, navigationActive);
  const routeLeadLabel =
    selectedAssignment?.assigned_operator_id ??
    selectedFollowUp?.assigned_operator_id ??
    (alertActionOperatorId.trim() || reviewOperatorId.trim() || operatorDisplayName(currentOperator));
  const routeUnitLabel = selectedAssignment?.assigned_unit_label ?? "Cab console";
  const routeStages: RouteStageItem[] = [
    {
      id: "pin",
      label: "Pin",
      detail: selectedFollowUp
        ? `${followUpStatusLabel(selectedFollowUp.status)} / ${titleCaseLabel(selectedFollowUp.priority)}`
        : "Create a follow-up if this detection needs a second pass.",
      state: selectedFollowUp ? "done" : selectedDetectionId ? "active" : "queued",
    },
    {
      id: "dispatch",
      label: "Dispatch",
      detail: selectedAssignment
        ? `${assignmentStatusLabel(selectedAssignment.status)} / ${selectedAssignment.assigned_unit_label ?? "Unit pending"}`
        : "Assign a unit and operator before the approach.",
      state:
        selectedAssignment?.status === "completed"
          ? "done"
          : selectedAssignment
            ? "active"
            : selectedDetectionId
              ? "queued"
              : "queued",
    },
    {
      id: "transit",
      label: "Transit",
      detail: navigationActive ? `${routeEtaLabel} to ${activeDestination}` : "Route not started.",
      state: navigationActive ? (withinArrivalRadius ? "done" : "active") : "queued",
    },
    {
      id: "arrival",
      label: "Arrival ring",
      detail: withinArrivalRadius
        ? "Inside the trigger distance. General popups are live."
        : `${fieldSettings.arrivalTriggerDistance} ft trigger distance.`,
      state: withinArrivalRadius ? "active" : navigationActive ? "queued" : "queued",
    },
    {
      id: "confirm",
      label: "Confirm",
      detail:
        selectedAssignment?.status === "onsite"
          ? "Crew is on scene. Confirm plate, VIN, and a safe hookup position."
          : selectedAlert.status === "onsite"
            ? "On-scene confirmation is in progress."
            : "Use cameras and evidence to verify before engagement.",
      state:
        selectedAssignment?.status === "completed"
          ? "done"
          : selectedAssignment?.status === "onsite" || selectedAlert.status === "onsite"
            ? "active"
            : "queued",
    },
  ];
  const currentRouteStage =
    routeStages.find((stage) => stage.state === "active") ??
    [...routeStages].reverse().find((stage) => stage.state === "done") ??
    routeStages[0];
  const routeCommandCards = [
    {
      label: "Next move",
      value: selectedAssignment?.summary ?? selectedAlert.routeAction,
      tone: currentRouteStage.state === "active" ? "badge--priority" : "badge--outlined",
    },
    {
      label: "Unit",
      value: routeUnitLabel,
      tone: selectedAssignment ? "badge--good" : "badge--outlined",
    },
    {
      label: "Lead",
      value: routeLeadLabel,
      tone: "badge--good",
    },
    {
      label: "ETA",
      value: routeEtaLabel,
      tone: withinArrivalRadius ? "badge--good" : navigationActive ? "badge--priority" : "badge--muted",
    },
    {
      label: "Alert scope",
      value: generalPopupsLive ? "General + hotlist" : "Hotlist only",
      tone: generalPopupsLive ? "badge--good" : "badge--outlined",
    },
  ] as const;
  const routeFocusItems = [
    selectedDisplayBestApproach,
    selectedWorkflowNotes,
    radiusDetectionSummary,
    selectedFollowUp?.due_at_utc
      ? `Pinned follow-up due ${formatHotlistTimestamp(selectedFollowUp.due_at_utc)}.`
      : "No due time is set on the current follow-up.",
  ];
  const hotlistAlertCount = liveOverview
    ? liveOverview.alerts.filter((alert) => alert.hotlist_entry_id && alert.status === "active").length
    : operatorAlerts.filter((alert) => alert.severity === "critical").length;
  const glanceTiles = [
    {
      label: "Primary target",
      value: selectedDisplayPlate,
      sublabel: selectedDisplayVehicle,
    },
    {
      label: "Hotlist alerts",
      value: `${hotlistAlertCount} active`,
      sublabel: hotlistAlertCount > 0 ? "Unsuppressed. Requires immediate response." : "No active hotlist matches right now.",
    },
    {
      label: "Route window",
      value: routeEtaLabel,
      sublabel: generalPopupsLive
        ? `${currentDistanceLabel} to ${activeDestination} / radius alerts live`
        : `${currentDistanceLabel} to ${activeDestination} / background classify only`,
    },
    {
      label: "Mission stage",
      value: currentRouteStage.label,
      sublabel: currentRouteStage.detail,
    },
    {
      label: "Dispatch",
      value: selectedAssignment ? assignmentStatusLabel(selectedAssignment.status) : "Unassigned",
      sublabel: selectedAssignment?.assigned_unit_label ?? "No unit committed yet",
    },
    {
      label: "Follow-up",
      value: selectedFollowUp ? followUpStatusLabel(selectedFollowUp.status) : "Not pinned",
      sublabel: selectedFollowUp?.summary ?? "Pin the detection if it needs a second pass.",
    },
    {
      label: "Crew",
      value: `${activeSessionCount} live`,
      sublabel:
        liveDataSource === "live"
          ? `${operatorDisplayName(currentOperator)} + ${Math.max(0, activeSessionCount - 1)} other operators`
          : operatorDisplayName(currentOperator),
    },
    {
      label: "Cameras",
      value: `${onlineCameraCount}/4 online`,
      sublabel: `${selectedCamera.label} priority feed`,
    },
  ];
  const liveAlertsByAlertId = new Map((liveOverview?.alerts ?? []).map((record) => [record.alert_id, record]));
  const mapAlertMarkers = operatorAlerts.map((alert, index) => {
    const hasAssignment = !!liveAssignments.find(
      (record) =>
        record.detection_id === alert.detectionId &&
        record.status !== "completed" &&
        record.status !== "cancelled",
    );
    const hasFollowUp = !!liveFollowUps.find(
      (record) => record.detection_id === alert.detectionId && record.status !== "resolved",
    );
    const liveAlert = liveAlertsByAlertId.get(alert.id);
    const isHotlistMatch = liveAlert ? !!liveAlert.hotlist_entry_id : knownHotlistPlates.has(alert.plate.toUpperCase());
    return {
      alert,
      x: 18 + index * 19,
      y: 20 + (index % 3) * 18,
      hasAssignment,
      hasFollowUp,
      isHotlistMatch,
    };
  });
  const mapCameraNodes = cameraFeeds.map((camera, index) => ({
    ...camera,
    x: 14 + (index % 2) * 18,
    y: 18 + Math.floor(index / 2) * 40,
  }));
  const mapSessionNodes = otherActiveSessions.slice(0, 4).map((session, index) => ({
    session,
    x: 24 + index * 12,
    y: 78 - (index % 2) * 12,
  }));
  const mapUnitPosition = {
    x: `${12 + routeProgressPercent * 0.55}%`,
    y: `${74 - routeProgressPercent * 0.34}%`,
  };
  const queuePageSize = 5;
  const searchPageSize = 12;
  const dashboardScreenMeta = dashboardScreenOptions.find((screen) => screen.id === dashboardScreen) ?? dashboardScreenOptions[0];
  const alertRows = operatorAlerts.map((alert) => {
    const liveAlert = liveAlertsByAlertId.get(alert.id);
    return {
      alert,
      isHotlistMatch: liveAlert ? !!liveAlert.hotlist_entry_id : knownHotlistPlates.has(alert.plate.toUpperCase()),
    };
  });
  const hotlistQueueRows = alertRows.filter((row) => row.isHotlistMatch);
  const radiusQueueRows = alertRows.filter((row) => !row.isHotlistMatch);
  const queueItemsTotal =
    queueView === "popups" ? popupHistory.length : queueView === "hotlist" ? hotlistQueueRows.length : radiusQueueRows.length;
  const queuePageCount = Math.max(1, Math.ceil(Math.max(queueItemsTotal, 1) / queuePageSize));
  const queuePageIndex = Math.min(queuePage, queuePageCount - 1);
  const queueStart = queuePageIndex * queuePageSize;
  const visibleHotlistRows = hotlistQueueRows.slice(queueStart, queueStart + queuePageSize);
  const visibleRadiusRows = radiusQueueRows.slice(queueStart, queueStart + queuePageSize);
  const visiblePopupHistory = popupHistory.slice(queueStart, queueStart + queuePageSize);
  const activeQueueRows = queueView === "hotlist" ? visibleHotlistRows : visibleRadiusRows;
  const queueHeadline =
    queueView === "hotlist" ? "Hotlist targets" : queueView === "radius" ? "Radius detections" : "Popup activity";
  const queueDescription =
    queueView === "hotlist"
      ? "Unsuppressed hotlist targets that require immediate action."
      : queueView === "radius"
        ? "General vehicle detections surfacing inside the target radius."
        : "Recent popup activity shown in the cab.";
  const queueEmptyMessage =
    queueView === "hotlist"
      ? "No active hotlist targets in the queue."
      : "No general vehicle detections are currently surfacing inside the radius.";
  const searchPageCount = Math.max(1, Math.ceil(Math.max(searchTotalResults, 1) / searchPageSize));
  const searchPageIndex = Math.min(Math.floor(searchOffset / searchPageSize), searchPageCount - 1);
  const searchPageLabel =
    searchTotalResults === 0
      ? "No results yet"
      : `Showing ${Math.min(searchOffset + 1, searchTotalResults)}-${Math.min(searchOffset + searchResults.length, searchTotalResults)} of ${searchTotalResults}`;

  // Geo-coordinates for Leaflet: map percentages to lat/lng offsets around the demo center.
  const geoCenter = defaultMapCenter;
  const geoSpan = 0.015; // ~1 mile spread
  function pctToGeo(xPct: number, yPct: number): { lat: number; lng: number } {
    return {
      lat: geoCenter[0] + geoSpan * (0.5 - yPct / 100),
      lng: geoCenter[1] + geoSpan * (xPct / 100 - 0.5),
    };
  }
  const geoUnitPosition = pctToGeo(
    12 + routeProgressPercent * 0.55,
    74 - routeProgressPercent * 0.34,
  );
  const geoAlertMarkers = mapAlertMarkers.map((marker) => ({
    id: marker.alert.id,
    lat: pctToGeo(marker.x, marker.y).lat,
    lng: pctToGeo(marker.x, marker.y).lng,
    plate: marker.alert.plate,
    severity: marker.alert.severity,
    isHotlist: marker.isHotlistMatch,
    onSelect: () => {
      setSelectedAlertId(marker.alert.id);
      setFocusedDetectionId(marker.alert.detectionId ?? null);
    },
  }));
  const geoCameraNodes = mapCameraNodes.map((cam) => ({
    id: cam.id,
    lat: pctToGeo(cam.x, cam.y).lat,
    lng: pctToGeo(cam.x, cam.y).lng,
    zone: cam.zone,
  }));
  const geoSessionNodes = mapSessionNodes.map((sess) => ({
    id: sess.session.session_id,
    lat: pctToGeo(sess.x, sess.y).lat,
    lng: pctToGeo(sess.x, sess.y).lng,
    label: `${sess.session.display_name ?? sess.session.principal_id} - ${sess.session.workspace}`,
  }));
  const geoRoutePath: [number, number][] = [
    [pctToGeo(12, 74).lat, pctToGeo(12, 74).lng],
    [pctToGeo(35, 55).lat, pctToGeo(35, 55).lng],
    [pctToGeo(55, 38).lat, pctToGeo(55, 38).lng],
    [pctToGeo(67, 40).lat, pctToGeo(67, 40).lng],
  ];
  const geoDestinationPosition = {
    lat: geoRoutePath[geoRoutePath.length - 1]?.[0] ?? geoUnitPosition.lat,
    lng: geoRoutePath[geoRoutePath.length - 1]?.[1] ?? geoUnitPosition.lng,
  };

  async function refreshOverview(signal?: AbortSignal): Promise<void> {
    try {
      const overview = await fetchDashboardOverview(signal);
      if (signal?.aborted) {
        return;
      }

      setLiveOverview(overview);
      setLiveDataSource("live");
      setLiveError(null);
    } catch (error) {
      if (signal?.aborted) {
        return;
      }

      setLiveOverview(null);
      setLiveDataSource("fallback");
      setLiveError(error instanceof Error ? error.message : "Live API unavailable");
    }
  }

  async function refreshDemoStatus(signal?: AbortSignal): Promise<void> {
    if (!demoRuntimeEnabled) {
      return;
    }

    try {
      const status = await fetchDemoRuntimeStatus(signal);
      if (signal?.aborted) {
        return;
      }

      setDemoRuntimeStatus(status);
      setDemoError(null);
    } catch (error) {
      if (signal?.aborted) {
        return;
      }

      setDemoRuntimeStatus(null);
      setDemoError(error instanceof Error ? error.message : "Demo runtime unavailable");
    }
  }

  function sortHotlists(entries: DashboardHotlist[]): DashboardHotlist[] {
    return [...entries].sort((left, right) => right.updated_at_utc.localeCompare(left.updated_at_utc));
  }

  function loadHotlistForm(entry: DashboardHotlist | null): void {
    setSelectedHotlistId(entry?.entry_id ?? null);
    setHotlistPlateText(entry?.plate_text ?? "");
    setHotlistLabel(entry?.label ?? "");
    setHotlistNotes(entry?.notes ?? "");
    setHotlistActive(entry?.active ?? true);
    setHotlistError(null);
    setHotlistSuccess(null);
  }

  useEffect(() => {
    window.localStorage.setItem(layoutStorageKey, JSON.stringify(layout));
  }, [layout]);

  useEffect(() => {
    window.localStorage.setItem(settingsStorageKey, JSON.stringify(fieldSettings));
  }, [fieldSettings]);

  useEffect(() => {
    setQueuePage(0);
  }, [queueView]);

  useEffect(() => {
    const maxPage = Math.max(0, Math.ceil(Math.max(queueItemsTotal, 1) / queuePageSize) - 1);
    if (queuePage > maxPage) {
      setQueuePage(maxPage);
    }
  }, [queueItemsTotal, queuePage, queuePageSize]);

  useEffect(() => {
    setApiClientConfig({ apiKey });
    window.localStorage.setItem(apiKeyStorageKey, apiKey);
  }, [apiKey]);

  useEffect(() => {
    window.localStorage.setItem(sessionLabelStorageKey, sessionLabel);
  }, [sessionLabel]);

  useEffect(() => {
    if (operatorAlerts.some((alert) => alert.id === selectedAlertId)) {
      return;
    }

    setSelectedAlertId(operatorAlerts[0]?.id ?? "");
  }, [operatorAlerts, selectedAlertId]);

  useEffect(() => {
    if (liveDataSource === "live") {
      return;
    }

    setSearchResults([]);
    setSearchTotalResults(0);
    setSearchLoading(false);
    setSearchError(null);
    setSearchExecuted(false);
  }, [liveDataSource]);

  useEffect(() => {
    if (!focusedDetectionId) {
      return;
    }

    const existsInOverview = detectionsById.has(focusedDetectionId);
    const existsInSearch = searchResultsById.has(focusedDetectionId);
    const existsInAlerts = operatorAlerts.some((alert) => alert.detectionId === focusedDetectionId);
    if (existsInOverview || existsInSearch || existsInAlerts) {
      return;
    }

    setFocusedDetectionId(null);
  }, [detectionsById, focusedDetectionId, operatorAlerts, searchResultsById]);

  useEffect(() => {
    const controller = new AbortController();
    void refreshOverview(controller.signal);
    const interval = window.setInterval(() => {
      void refreshOverview();
    }, 15000);

    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [apiKey]);

  useEffect(() => {
    if (liveDataSource !== "live") {
      setOperatorSessionError(null);
      return;
    }

    let disposed = false;

    const sendHeartbeat = async (): Promise<void> => {
      try {
        await sendOperatorSessionHeartbeat({
          session_id: operatorSessionIdRef.current,
          client_label: sessionLabel.trim() || undefined,
          workspace: activeWorkspace,
          selected_detection_id: selectedDetectionId ?? undefined,
          selected_alert_id: (selectedLiveAlert?.alert_id ?? selectedAlertId) || undefined,
          navigation_active: navigationActive,
        });
        if (!disposed) {
          setOperatorSessionError(null);
        }
      } catch (error) {
        if (!disposed) {
          setOperatorSessionError(error instanceof Error ? error.message : "Operator presence unavailable");
        }
      }
    };

    void sendHeartbeat();
    const interval = window.setInterval(() => {
      void sendHeartbeat();
    }, 15000);

    return () => {
      disposed = true;
      window.clearInterval(interval);
    };
  }, [activeWorkspace, liveDataSource, navigationActive, selectedAlertId, selectedDetectionId, selectedLiveAlert, sessionLabel]);

  useEffect(() => {
    setReviewAction("confirm");
    setReviewCorrectedPlate(selectedDisplayPlate);
    setReviewNotes("");
    setReviewSuccess(null);
    setReviewError(null);
  }, [selectedDetectionId, selectedDisplayPlate]);

  useEffect(() => {
    if (reviewOperatorId.trim()) {
      return;
    }
    setReviewOperatorId(sessionLabel.trim() || currentOperator.principal_id);
  }, [currentOperator.principal_id, reviewOperatorId, sessionLabel]);

  useEffect(() => {
    const nextAlertId = selectedLiveAlert?.alert_id ?? null;
    if (liveDataSource === "live" && previousAlertActionTargetRef.current === nextAlertId) {
      return;
    }

    previousAlertActionTargetRef.current = nextAlertId;
    setAlertActionOperatorId(selectedLiveAlert?.response_operator_id ?? "");
    setAlertActionNotes(selectedLiveAlert?.response_notes ?? "");
    setAlertActionPendingStatus(null);
    setAlertActionSuccess(null);
    setAlertActionError(null);
  }, [liveDataSource, selectedLiveAlert]);

  useEffect(() => {
    setFollowUpPriority(
      selectedFollowUp?.priority ??
        (selectedAlert.severity === "critical" ? "critical" : selectedAlert.severity === "priority" ? "priority" : "routine"),
    );
    setFollowUpStatus(selectedFollowUp?.status ?? "open");
    setFollowUpAssignedOperatorId((selectedFollowUp?.assigned_operator_id ?? sessionLabel.trim()) || currentOperator.principal_id);
    setFollowUpSummary(selectedFollowUp?.summary ?? `Pin ${selectedDisplayPlate} for follow-up.`);
    setFollowUpNotes(selectedFollowUp?.notes ?? selectedAlert.notes);
    setFollowUpDueAt(selectedFollowUp?.due_at_utc ? formatLocalDateTimeInput(selectedFollowUp.due_at_utc) : "");
    setFollowUpSuccess(null);
    setFollowUpError(null);
  }, [
    currentOperator.principal_id,
    selectedAlert.notes,
    selectedAlert.severity,
    selectedDetectionId,
    selectedDisplayPlate,
    selectedFollowUp,
    sessionLabel,
  ]);

  useEffect(() => {
    setAssignmentPriority(
      selectedAssignment?.priority ??
        (selectedAlert.severity === "critical" ? "critical" : selectedAlert.severity === "priority" ? "priority" : "watch"),
    );
    setAssignmentStatus(selectedAssignment?.status ?? "queued");
    setAssignmentOperatorId((selectedAssignment?.assigned_operator_id ?? sessionLabel.trim()) || currentOperator.principal_id);
    setAssignmentUnitLabel(selectedAssignment?.assigned_unit_label ?? "Truck 4");
    setAssignmentDestination(selectedAssignment?.destination_label ?? selectedAlert.location);
    setAssignmentSummary(selectedAssignment?.summary ?? `Dispatch field crew to ${selectedAlert.location}.`);
    setAssignmentNotes(selectedAssignment?.notes ?? selectedAlert.bestApproach);
    setAssignmentSuccess(null);
    setAssignmentError(null);
  }, [
    currentOperator.principal_id,
    selectedAlert.bestApproach,
    selectedAlert.location,
    selectedAlert.severity,
    selectedAssignment,
    sessionLabel,
  ]);

  useEffect(() => {
    if (demoPlateText.trim().length > 0) {
      return;
    }
    setDemoPlateText(selectedAlert.plate);
  }, [demoPlateText, selectedAlert.plate]);

  useEffect(() => {
    let disposed = false;
    const controller = new AbortController();

    setFramePreviewUnavailable(false);
    setPlateCropPreviewUnavailable(false);
    setFramePreviewUrl((current) => {
      if (current) {
        URL.revokeObjectURL(current);
      }
      return null;
    });
    setPlateCropPreviewUrl((current) => {
      if (current) {
        URL.revokeObjectURL(current);
      }
      return null;
    });

    if (liveDataSource !== "live" || !selectedDetectionId) {
      return () => {
        disposed = true;
        controller.abort();
      };
    }

    fetchDetectionFrameObjectUrl(selectedDetectionId, controller.signal)
      .then((url) => {
        if (disposed) {
          URL.revokeObjectURL(url);
          return;
        }
        setFramePreviewUrl((current) => {
          if (current) {
            URL.revokeObjectURL(current);
          }
          return url;
        });
      })
      .catch((error) => {
        if (!controller.signal.aborted && !disposed) {
          setFramePreviewUnavailable(error instanceof Error);
        }
      });

    fetchDetectionPlateCropObjectUrl(selectedDetectionId, controller.signal)
      .then((url) => {
        if (disposed) {
          URL.revokeObjectURL(url);
          return;
        }
        setPlateCropPreviewUrl((current) => {
          if (current) {
            URL.revokeObjectURL(current);
          }
          return url;
        });
      })
      .catch((error) => {
        if (!controller.signal.aborted && !disposed) {
          setPlateCropPreviewUnavailable(error instanceof Error);
        }
      });

    return () => {
      disposed = true;
      controller.abort();
      setFramePreviewUrl((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
      setPlateCropPreviewUrl((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
    };
  }, [liveDataSource, selectedDetectionId]);

  useEffect(() => {
    if (!demoRuntimeEnabled) {
      setDemoRuntimeStatus(null);
      setDemoLoading(false);
      setDemoError(null);
      setDemoSuccess(null);
      previousDemoRunStateRef.current = "idle";
      previousDemoRunIdRef.current = null;
      return;
    }

    let disposed = false;
    const controller = new AbortController();
    setDemoLoading(true);

    fetchDemoRuntimeStatus(controller.signal)
      .then((status) => {
        if (disposed) {
          return;
        }

        setDemoRuntimeStatus(status);
        setDemoError(null);
        previousDemoRunStateRef.current = status.state;
        previousDemoRunIdRef.current = status.run_id;
      })
      .catch((error) => {
        if (controller.signal.aborted || disposed) {
          return;
        }

        setDemoRuntimeStatus(null);
        setDemoError(error instanceof Error ? error.message : "Demo runtime unavailable");
      })
      .finally(() => {
        if (!disposed) {
          setDemoLoading(false);
        }
      });

    const interval = window.setInterval(() => {
      void refreshDemoStatus();
    }, 4000);

    return () => {
      disposed = true;
      controller.abort();
      window.clearInterval(interval);
    };
  }, [demoRuntimeEnabled]);

  useEffect(() => {
    if (!demoRuntimeStatus?.run_id) {
      previousDemoRunStateRef.current = demoRuntimeStatus?.state ?? "idle";
      previousDemoRunIdRef.current = demoRuntimeStatus?.run_id ?? null;
      return;
    }

    const runJustCompleted =
      demoRuntimeStatus.run_id !== previousDemoRunIdRef.current ||
      (previousDemoRunStateRef.current === "running" && demoRuntimeStatus.state !== "running");

    if (runJustCompleted && demoRuntimeStatus.state === "succeeded") {
      setDemoSuccess(
        `Demo run ready: ${demoRuntimeStatus.summary?.stored_detection_ids.length ?? 0} detection${
          demoRuntimeStatus.summary?.stored_detection_ids.length === 1 ? "" : "s"
        } and ${demoRuntimeStatus.summary?.created_alert_ids.length ?? 0} alert${
          demoRuntimeStatus.summary?.created_alert_ids.length === 1 ? "" : "s"
        } recorded.`,
      );
      void refreshOverview();
    } else if (runJustCompleted && demoRuntimeStatus.state === "failed" && demoRuntimeStatus.error_message) {
      setDemoError(demoRuntimeStatus.error_message);
      setDemoSuccess(null);
    }

    previousDemoRunStateRef.current = demoRuntimeStatus.state;
    previousDemoRunIdRef.current = demoRuntimeStatus.run_id;
  }, [demoRuntimeStatus]);

  useEffect(() => {
    if (!hotlistsEnabled) {
      setHotlistEntries([]);
      setHotlistLoading(false);
      setHotlistError(null);
      setHotlistSuccess(null);
      loadHotlistForm(null);
      return;
    }

    let disposed = false;
    const controller = new AbortController();
    setHotlistLoading(true);

    fetchHotlists(controller.signal)
      .then((entries) => {
        if (disposed) {
          return;
        }

        setHotlistEntries(entries);
        setHotlistError(null);
        if (entries.length > 0) {
          loadHotlistForm(entries[0]);
        } else {
          loadHotlistForm(null);
        }
      })
      .catch((error) => {
        if (controller.signal.aborted || disposed) {
          return;
        }

        setHotlistEntries([]);
        setHotlistError(error instanceof Error ? error.message : "Hotlist management unavailable");
      })
      .finally(() => {
        if (!disposed) {
          setHotlistLoading(false);
        }
      });

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [hotlistsEnabled]);

  useEffect(() => {
    if (!reviewsEnabled || !selectedDetectionId) {
      setReviewHistory([]);
      setReviewLoading(false);
      setReviewError(null);
      return;
    }

    let disposed = false;
    const controller = new AbortController();
    setReviewLoading(true);

    fetchReviews(selectedDetectionId, controller.signal)
      .then((reviews) => {
        if (disposed) {
          return;
        }

        setReviewHistory(reviews);
        setReviewError(null);
      })
      .catch((error) => {
        if (controller.signal.aborted || disposed) {
          return;
        }

        setReviewHistory([]);
        setReviewError(error instanceof Error ? error.message : "Review history unavailable");
      })
      .finally(() => {
        if (!disposed) {
          setReviewLoading(false);
        }
      });

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [reviewsEnabled, selectedDetectionId]);

  function dismissPopup(instanceId: string): void {
    setPopupStack((current) => current.filter((popup) => popup.instanceId !== instanceId));
  }

  function queuePopup(event: DetectionPopupEvent, options?: { updateHistory?: boolean }): void {
    const instanceId = `${event.id}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const popup: PopupNotification = {
      ...event,
      instanceId,
    };
    const updateHistory = options?.updateHistory ?? true;

    setPopupStack((current) => [popup, ...current].slice(0, 4));
    if (updateHistory) {
      setPopupHistory((current) => [event, ...current.filter((item) => item.id !== event.id)].slice(0, 6));
    }

    window.setTimeout(() => {
      setPopupStack((current) => current.filter((item) => item.instanceId !== instanceId));
    }, event.type === "hotlist" ? 9000 : 6500);
  }

  useEffect(() => {
    const justEnteredArrivalRadius = withinArrivalRadius && !previousWithinArrivalRef.current;
    previousWithinArrivalRef.current = withinArrivalRadius;

    if (!justEnteredArrivalRadius) {
      return;
    }

    startTransition(() => {
      setActiveWorkspace("dashboard");
      setLayout((current) =>
        current.profile === dashboardPresets.route.profile ? cloneLayout(dashboardPresets.recovery) : current,
      );
      setChatMessages((current) => [
        ...current,
        {
          id: `sys-arrival-${Date.now()}`,
          sender: "System",
          body: `Geofence triggered - entered arrival radius (${fieldSettings.arrivalTriggerDistance} ft). Scan mode active.`,
          timestamp: new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false }),
          type: "system",
        },
      ]);
    });
  }, [withinArrivalRadius, fieldSettings.arrivalTriggerDistance]);

  useEffect(() => {
    if (!liveOverview) {
      setPopupHistory(defaultPopupHistory);
      return;
    }

    const livePopupActivity = mapOverviewToPopupHistory(liveOverview);
    const visibleLivePopupActivity = livePopupActivity.filter(
      (event) => generalPopupsLive || event.type === "hotlist",
    );

    if (visibleLivePopupActivity.length === 0) {
      setPopupHistory([]);
      return;
    }

    setPopupHistory(visibleLivePopupActivity);

    for (const event of [...visibleLivePopupActivity].reverse()) {
      if (queuedLivePopupIdsRef.current.has(event.id)) {
        continue;
      }

      queuePopup(event, { updateHistory: false });
      queuedLivePopupIdsRef.current.add(event.id);
    }
  }, [generalPopupsLive, liveOverview]);

  useEffect(() => {
    if (liveOverview) {
      return;
    }

    const kickoff = window.setTimeout(() => {
      setHotlistPopupIndex((index) => {
        queuePopup(hotlistPopupDetections[index]);
        return (index + 1) % hotlistPopupDetections.length;
      });
    }, 2500);

    const interval = window.setInterval(() => {
      setHotlistPopupIndex((index) => {
        queuePopup(hotlistPopupDetections[index]);
        return (index + 1) % hotlistPopupDetections.length;
      });
    }, 22000);

    return () => {
      window.clearTimeout(kickoff);
      window.clearInterval(interval);
    };
  }, [liveOverview]);

  useEffect(() => {
    if (liveOverview || !generalPopupsLive) {
      return;
    }

    const kickoff = window.setTimeout(() => {
      setAddressPopupIndex((index) => {
        queuePopup(addressScanDetections[index]);
        return (index + 1) % addressScanDetections.length;
      });
    }, 1400);

    const interval = window.setInterval(() => {
      setAddressPopupIndex((index) => {
        queuePopup(addressScanDetections[index]);
        return (index + 1) % addressScanDetections.length;
      });
    }, 12000);

    return () => {
      window.clearTimeout(kickoff);
      window.clearInterval(interval);
    };
  }, [generalPopupsLive, liveOverview]);

  function selectWorkspace(nextWorkspace: WorkspaceId): void {
    startTransition(() => {
      setActiveWorkspace(nextWorkspace);
      setTargetPanelTab(nextWorkspace === "search" ? "reviews" : nextWorkspace === "alerts" ? "workflow" : "overview");
      if (nextWorkspace === "dashboard") {
        setDashboardScreen("drive");
      }
    });
  }

  function updateSearchField<K extends keyof SearchFormState>(key: K, value: SearchFormState[K]): void {
    setSearchForm((current) => ({
      ...current,
      [key]: value,
    }));
    setSearchOffset(0);
  }

  function resetSearchFilters(): void {
    setSearchForm(defaultSearchFormState);
    setSearchResults([]);
    setSearchTotalResults(0);
    setSearchOffset(0);
    setSearchError(null);
    setSearchExecuted(false);
    setFocusedDetectionId(selectedAlert?.detectionId ?? null);
  }

  function focusDetection(detectionId: string, alertId?: string | null): void {
    setFocusedDetectionId(detectionId);
    if (alertId) {
      setSelectedAlertId(alertId);
    }
  }

  function applyPreset(presetId: LayoutPresetId): void {
    startTransition(() => {
      setLayout(cloneLayout(dashboardPresets[presetId]));
    });
  }

  function setCameraMode(cameraMode: CameraMode): void {
    setLayout((current) => ({
      ...current,
      cameraMode,
    }));
  }

  function movePanelToSlot(slot: SlotId, nextPanel: PanelId): void {
    setLayout((current) => {
      const nextSlots = { ...current.slots };
      const existingSlot = (Object.keys(nextSlots) as SlotId[]).find((candidate) => nextSlots[candidate] === nextPanel);
      const displacedPanel = nextSlots[slot];

      nextSlots[slot] = nextPanel;
      if (existingSlot && existingSlot !== slot) {
        nextSlots[existingSlot] = displacedPanel;
      }

      return {
        ...current,
        profile: "Custom Layout",
        slots: nextSlots,
      };
    });
  }

  function updateFieldSetting<K extends keyof FieldSettings>(key: K, value: FieldSettings[K]): void {
    setFieldSettings((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function handleNavigationToggle(): void {
    if (navigationActive) {
      setNavigationActive(false);
      return;
    }

    const nextDestination = destinationInput.trim() || selectedAlert.location;
    setDestinationInput(nextDestination);
    setActiveDestination(nextDestination);
    startTransition(() => {
      setNavigationActive(true);
      setActiveWorkspace("navigation");
      setLayout((current) =>
        current.profile === dashboardPresets.recovery.profile ? cloneLayout(dashboardPresets.route) : current,
      );
    });
  }

  async function runDetectionSearch(offset: number, focusFirstResult: boolean): Promise<void> {
    if (liveDataSource !== "live") {
      setSearchError("Connect the live API before running operator search.");
      return;
    }

    setSearchLoading(true);
    setSearchError(null);

    try {
      const response = await searchDetections({
        plate: searchForm.plate,
        plate_match: searchForm.plateMatch,
        start_utc: toUtcIsoString(searchForm.startUtc),
        end_utc: toUtcIsoString(searchForm.endUtc),
        camera_id: searchForm.cameraId || undefined,
        min_latitude: parseOptionalNumber(searchForm.minLatitude),
        max_latitude: parseOptionalNumber(searchForm.maxLatitude),
        min_longitude: parseOptionalNumber(searchForm.minLongitude),
        max_longitude: parseOptionalNumber(searchForm.maxLongitude),
        vehicle_color: searchForm.vehicleColor,
        vehicle_make: searchForm.vehicleMake,
        vehicle_model: searchForm.vehicleModel,
        vehicle_year: searchForm.vehicleYear,
        alert_status: searchForm.alertStatus || undefined,
        limit: searchPageSize,
        offset,
      });

      setSearchResults(response.results);
      setSearchTotalResults(response.page.total_results);
      setSearchOffset(offset);
      setSearchExecuted(true);

      if (focusFirstResult && response.results.length > 0) {
        const firstDetection = response.results[0];
        const matchingAlert = liveOverview?.alerts.find((alert) => alert.detection_id === firstDetection.detection_id) ?? null;
        focusDetection(firstDetection.detection_id, matchingAlert?.alert_id);
      }
    } catch (error) {
      setSearchResults([]);
      setSearchTotalResults(0);
      setSearchOffset(offset);
      setSearchExecuted(true);
      setSearchError(error instanceof Error ? error.message : "Failed to run search");
    } finally {
      setSearchLoading(false);
    }
  }

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await runDetectionSearch(0, true);
  }

  function changeSearchPage(direction: -1 | 1): void {
    const nextOffset = Math.max(0, searchOffset + direction * searchPageSize);
    void runDetectionSearch(nextOffset, false);
  }

  async function handleReviewSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!selectedDetectionId) {
      return;
    }

    const normalizedCorrection = reviewCorrectedPlate.trim().toUpperCase();
    if (reviewAction === "correct" && normalizedCorrection.length === 0) {
      setReviewError("Corrected plate text is required when saving a correction.");
      return;
    }

    setReviewSubmitting(true);
    setReviewError(null);
    setReviewSuccess(null);

    try {
      const review = await createReview(selectedDetectionId, {
        action: reviewAction,
        operator_id: reviewOperatorId.trim() || undefined,
        corrected_plate_text: reviewAction === "correct" ? normalizedCorrection : undefined,
        notes: reviewNotes.trim() || undefined,
        reviewed_at_utc: new Date().toISOString(),
      });

      setReviewHistory((current) => [review, ...current.filter((item) => item.review_id !== review.review_id)]);
      setReviewSuccess(
        review.action === "correct"
          ? `Correction saved locally as ${review.corrected_plate_text ?? normalizedCorrection}.`
          : `${reviewActionLabel(review.action)} review saved locally.`,
      );
      setReviewNotes("");
      if (review.action === "correct" && review.corrected_plate_text) {
        setReviewCorrectedPlate(review.corrected_plate_text);
      }
      void refreshOverview();
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : "Failed to save review");
    } finally {
      setReviewSubmitting(false);
    }
  }

  async function handleFollowUpSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!selectedDetectionId) {
      return;
    }

    setFollowUpSubmitting(true);
    setFollowUpError(null);
    setFollowUpSuccess(null);

    try {
      const submission = {
        detection_id: selectedDetectionId,
        alert_id: selectedLiveAlert?.alert_id ?? undefined,
        plate_text: selectedDisplayPlate !== "Plate unavailable" ? selectedDisplayPlate : undefined,
        priority: followUpPriority,
        status: followUpStatus,
        assigned_operator_id: followUpAssignedOperatorId.trim() || undefined,
        summary: followUpSummary.trim() || undefined,
        notes: followUpNotes.trim() || undefined,
        due_at_utc: toUtcIsoString(followUpDueAt),
      };

      const savedFollowUp = selectedFollowUp
        ? await updateFollowUp(selectedFollowUp.follow_up_id, submission)
        : await createFollowUp(submission);

      setFollowUpSuccess(
        selectedFollowUp
          ? `${followUpStatusLabel(savedFollowUp.status)} follow-up saved for ${savedFollowUp.plate_text ?? selectedDisplayPlate}.`
          : `Pinned ${savedFollowUp.plate_text ?? selectedDisplayPlate} for follow-up.`,
      );
      void refreshOverview();
    } catch (error) {
      setFollowUpError(error instanceof Error ? error.message : "Failed to save follow-up");
    } finally {
      setFollowUpSubmitting(false);
    }
  }

  async function handleAssignmentSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!selectedDetectionId) {
      return;
    }

    setAssignmentSubmitting(true);
    setAssignmentError(null);
    setAssignmentSuccess(null);

    try {
      const submission = {
        detection_id: selectedDetectionId,
        alert_id: selectedLiveAlert?.alert_id ?? undefined,
        plate_text: selectedDisplayPlate !== "Plate unavailable" ? selectedDisplayPlate : undefined,
        priority: assignmentPriority,
        status: assignmentStatus,
        assigned_operator_id: assignmentOperatorId.trim() || undefined,
        assigned_unit_label: assignmentUnitLabel.trim() || undefined,
        destination_label: assignmentDestination.trim() || undefined,
        summary: assignmentSummary.trim() || undefined,
        notes: assignmentNotes.trim() || undefined,
      };

      const savedAssignment = selectedAssignment
        ? await updateDispatchAssignment(selectedAssignment.assignment_id, submission)
        : await createDispatchAssignment(submission);

      setAssignmentSuccess(
        selectedAssignment
          ? `${assignmentStatusLabel(savedAssignment.status)} assignment saved for ${savedAssignment.plate_text ?? selectedDisplayPlate}.`
          : `Dispatch assignment created for ${savedAssignment.plate_text ?? selectedDisplayPlate}.`,
      );
      void refreshOverview();
    } catch (error) {
      setAssignmentError(error instanceof Error ? error.message : "Failed to save assignment");
    } finally {
      setAssignmentSubmitting(false);
    }
  }

  async function handleAlertAction(nextStatus: DashboardAlert["status"]): Promise<void> {
    if (!selectedLiveAlert) {
      return;
    }

    const operatorId = alertActionOperatorId.trim();
    const responseNotes = alertActionNotes.trim();
    const popupEventId = `popup_${selectedLiveAlert.alert_id}`;

    setAlertActionSubmitting(true);
    setAlertActionPendingStatus(nextStatus);
    setAlertActionError(null);
    setAlertActionSuccess(null);

    try {
      const updatedAlert = await updateAlert(selectedLiveAlert.alert_id, {
        status: nextStatus,
        operator_id: operatorId || undefined,
        response_notes: responseNotes || undefined,
      });

      setLiveOverview((current) => {
        if (!current) {
          return current;
        }

        const nextAlerts = current.alerts.map((alert) => (alert.alert_id === updatedAlert.alert_id ? updatedAlert : alert));
        return {
          ...current,
          counts: {
            ...current.counts,
            active_alerts: nextAlerts.filter((alert) => alert.status === "active").length,
          },
          alerts: nextAlerts,
          popup_activity:
            updatedAlert.status === "dismissed"
              ? current.popup_activity.filter((event) => event.event_id !== popupEventId)
              : current.popup_activity,
        };
      });
      setAlertActionOperatorId(updatedAlert.response_operator_id ?? "");
      setAlertActionNotes(updatedAlert.response_notes ?? "");
      setAlertActionSuccess(
        nextStatus === "acknowledged"
          ? "Alert acknowledged and saved locally."
          : nextStatus === "dismissed"
            ? "Alert stood down and removed from live popup activity."
            : "Alert reopened and returned to active monitoring.",
      );

      if (nextStatus === "dismissed") {
        queuedLivePopupIdsRef.current.delete(popupEventId);
        setPopupHistory((current) => current.filter((event) => event.id !== popupEventId));
        setPopupStack((current) => current.filter((popup) => popup.id !== popupEventId));
      }

      void refreshOverview();
    } catch (error) {
      setAlertActionError(error instanceof Error ? error.message : "Failed to update alert");
    } finally {
      setAlertActionSubmitting(false);
      setAlertActionPendingStatus(null);
    }
  }

  async function handleHotlistSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!hotlistsEnabled) {
      return;
    }

    const normalizedPlate = hotlistPlateText.trim().toUpperCase();
    if (normalizedPlate.length === 0) {
      setHotlistError("Plate text is required before saving a hotlist entry.");
      return;
    }

    setHotlistSaving(true);
    setHotlistError(null);
    setHotlistSuccess(null);

    try {
      const submission = {
        plate_text: normalizedPlate,
        label: hotlistLabel.trim() || undefined,
        notes: hotlistNotes.trim() || undefined,
        active: hotlistActive,
      };

      const savedEntry = selectedHotlist
        ? await updateHotlist(selectedHotlist.entry_id, submission)
        : await createHotlist(submission);

      setHotlistEntries((current) => {
        const remainingEntries = current.filter((entry) => entry.entry_id !== savedEntry.entry_id);
        return sortHotlists([savedEntry, ...remainingEntries]);
      });
      loadHotlistForm(savedEntry);
      setHotlistSuccess(
        selectedHotlist
          ? `Updated hotlist entry for ${savedEntry.plate_text}.`
          : `Created hotlist entry for ${savedEntry.plate_text}.`,
      );
      void refreshOverview();
    } catch (error) {
      setHotlistError(error instanceof Error ? error.message : "Failed to save hotlist entry");
    } finally {
      setHotlistSaving(false);
    }
  }

  async function handleDemoRunSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!demoRuntimeEnabled) {
      return;
    }

    const framesDirectory = demoFramesDirectory.trim();
    const plateText = demoPlateText.trim().toUpperCase();
    if (framesDirectory.length === 0) {
      setDemoError("A local frame folder is required before starting a demo run.");
      return;
    }
    if (plateText.length === 0) {
      setDemoError("A demo plate value is required before starting a demo run.");
      return;
    }

    setDemoSubmitting(true);
    setDemoError(null);
    setDemoSuccess(null);

    try {
      const status = await startDemoRun({
        frames_directory: framesDirectory,
        frame_interval_ms: 100.0,
        sequence_id: demoSequenceId.trim() || undefined,
        plate_text: plateText,
      });
      setDemoRuntimeStatus(status);
      setDemoSuccess(`Demo run started for ${plateText}. The dashboard will refresh when the ingest job completes.`);
    } catch (error) {
      setDemoError(error instanceof Error ? error.message : "Failed to start demo run");
    } finally {
      setDemoSubmitting(false);
    }
  }

  function renderPanel(panelId: PanelId): ReactElement {
    switch (panelId) {
      case "routePlanner":
        return (
          <PanelFrame panelId={panelId}>
            <div className="route-summary">
              <label className="field-group">
                <span>Destination</span>
                <input
                  className="input-control"
                  placeholder="Enter target address or recovery location"
                  type="text"
                  value={destinationInput}
                  onChange={(event) => setDestinationInput(event.target.value)}
                />
              </label>
              <div className="route-destination">
                <strong>{activeDestination}</strong>
                <span>{navigationActive ? "Navigation active" : "Ready to route"}</span>
              </div>
              <div className="mode-pills">
                <span className={`badge ${activeScanMode ? "badge--scan-live" : navigationActive ? "badge--scan-bg" : "badge--muted"}`}>
                  {activeScanMode ? "Scan live" : navigationActive ? "Transit" : "Idle"}
                </span>
                <span className={`badge ${addressDetectionEnabled ? "badge--good" : "badge--muted"}`}>
                  Address {addressDetectionEnabled ? "on" : "off"}
                </span>
                <span className="badge badge--hotlist-always">Hotlist always on</span>
                {hotlistAlertCount > 0 ? (
                  <span className="badge badge--critical">{hotlistAlertCount} hotlist alert{hotlistAlertCount === 1 ? "" : "s"}</span>
                ) : null}
              </div>
              <div className="route-meta-grid">
                <StatusLine label="Current range" value={currentDistanceLabel} />
                <StatusLine label="Scenario" value={scenarioLabels[selectedAlert.scenario]} />
                <StatusLine label="Arrival ring" value={`${fieldSettings.arrivalTriggerDistance} ft`} />
                <StatusLine label="Alert scope" value={generalPopupsLive ? "General + hotlist" : "Hotlist only"} />
              </div>
              <div className="proximity-shell">
                <div className="proximity-shell__header">
                  <span className="panel-label">Arrival simulator</span>
                  <strong>{currentDistanceLabel}</strong>
                </div>
                <input
                  aria-label="Arrival distance simulator"
                  className="range-control"
                  max="1760"
                  min="0"
                  step="25"
                  type="range"
                  value={currentDistanceFeet}
                  onChange={(event) => setCurrentDistanceFeet(Number(event.target.value))}
                />
                <p className="proximity-hint">
                  Crossing the arrival ring automatically flips the system into active scan mode.
                </p>
              </div>
              <div className={`trigger-meter ${withinArrivalRadius || routeProgressPercent > 80 ? "trigger-meter--near" : ""}`}>
                <div
                  className="trigger-meter__fill"
                  style={{ "--fill": `${routeProgressPercent}%` } as CSSProperties}
                />
              </div>
              <div className="route-stage-strip" aria-label="Mission stage strip">
                {routeStages.map((stage) => (
                  <article
                    key={stage.id}
                    className={`route-stage-card route-stage-card--${stage.state} ${
                      currentRouteStage.id === stage.id ? "is-current" : ""
                    }`}
                  >
                    <div className="route-stage-card__header">
                      <span className="panel-label">{stage.label}</span>
                      <span className={`badge ${routeStageTone(stage.state)}`}>{titleCaseLabel(stage.state)}</span>
                    </div>
                    <p>{stage.detail}</p>
                  </article>
                ))}
              </div>
              <div className="route-command-grid" aria-label="Route command cards">
                {routeCommandCards.map((card) => (
                  <div key={card.label} className="route-command-card">
                    <span>{card.label}</span>
                    <strong>{card.value}</strong>
                    <em className={`badge ${card.tone}`}>{card.label}</em>
                  </div>
                ))}
              </div>
              <div className="route-focus-board">
                <div className="route-focus-board__header">
                  <div>
                    <span className="panel-label">Crew focus</span>
                    <strong>{currentRouteStage.label}</strong>
                  </div>
                  <span className={`badge ${routeStageTone(currentRouteStage.state)}`}>
                    {routeProgressPercent.toFixed(0)}% route progress
                  </span>
                </div>
                <div className="route-focus-board__grid">
                  <StatusLine label="Assigned unit" value={routeUnitLabel} />
                  <StatusLine label="Lead operator" value={routeLeadLabel} />
                </div>
                <ul className="route-focus-list">
                  {routeFocusItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div className="panel-actions">
                <button className="button button--primary" type="button" onClick={handleNavigationToggle}>
                  {navigationActive ? "Stop navigation" : "Start navigation"}
                </button>
                <button
                  className={`button ${addressDetectionEnabled ? "" : "button--primary"}`}
                  type="button"
                  onClick={() => setAddressDetectionEnabled((current) => !current)}
                >
                  Address detection {addressDetectionEnabled ? "on" : "off"}
                </button>
                <button className="button" type="button" onClick={() => setCurrentDistanceFeet(fieldSettings.arrivalTriggerDistance)}>
                  Jump to arrival ring
                </button>
              </div>
            </div>
          </PanelFrame>
        );
      case "statusStack":
        return (
          <PanelFrame panelId={panelId}>
            <div className="status-stack">
              <StatusRow label="GPS" value="Locked" tone="good" />
              <StatusRow label="Navigation" value={navigationModeLabel} tone={navigationActive ? "good" : "neutral"} />
              <StatusRow label="Camera bank" value={`${onlineCameraCount}/4 online`} tone="good" />
              <StatusRow
                label="Crew"
                value={
                  liveDataSource === "live"
                    ? `${activeSessionCount} active / ${operatorDisplayName(currentOperator)}`
                    : operatorDisplayName(currentOperator)
                }
                tone={activeSessionCount > 1 ? "good" : "neutral"}
              />
              <StatusRow
                label="Radius detection"
                value={
                  addressDetectionEnabled
                    ? generalPopupsLive
                      ? "Popup alerts live"
                      : "Background detection only"
                    : "Disabled by operator"
                }
                tone={generalPopupsLive ? "good" : addressDetectionEnabled ? "neutral" : "warn"}
              />
              <StatusRow label="Hotlist alerting" value="Always active" tone="good" />
              <StatusRow label="Storage" value={fieldSettings.lowStorageWarning ? "Warn at 15%" : "No warning"} tone="neutral" />
              <StatusRow
                label="Alert tone"
                value={fieldSettings.silentShiftMode ? "Visual priority" : "Audible + visual"}
                tone={fieldSettings.silentShiftMode ? "warn" : "good"}
              />
            </div>
            <div className="status-ticker">
              {generalPopupsLive
                ? "Inside arrival radius. General detections now surface as popups."
                : `${addressPopupPolicy}. Standard detection still runs in the background.`}{" "}
              Hotlist matches remain unsuppressed at all times.
            </div>
          </PanelFrame>
        );
      case "opsMap":
        return (
          <PanelFrame panelId={panelId}>
            <div className="map-header">
              <div>
                <div className="eyebrow">Live route context</div>
                <h3>{activeDestination}</h3>
              </div>
              <div className="map-stats">
                <span>{currentDistanceLabel}</span>
                <span>{activeScanMode ? "Active scan live" : fieldSettings.routeTrafficOverlay ? "Traffic overlay on" : "Traffic overlay off"}</span>
              </div>
            </div>
            <OpsMapLeaflet
              unitPosition={geoUnitPosition}
              destinationPosition={geoDestinationPosition}
              destinationLabel={activeDestination}
              alertMarkers={geoAlertMarkers}
              cameraNodes={geoCameraNodes}
              sessionNodes={geoSessionNodes}
              arrivalRadius={fieldSettings.arrivalTriggerDistance}
              withinArrival={withinArrivalRadius}
              routePath={geoRoutePath}
            />
            <div className="map-legend map-legend--standalone">
              <span className="panel-label">Current mission call</span>
              <strong>{currentRouteStage.label}</strong>
              <p>{selectedAlert.bestApproach}</p>
              <div className="mode-pills">
                <span className={`badge ${activeScanMode ? "badge--scan-live" : navigationActive ? "badge--scan-bg" : "badge--outlined"}`}>
                  {activeScanMode ? "Scan live" : navigationActive ? "Transit" : "Idle"}
                </span>
                <span className="badge badge--hotlist-always">Hotlist on</span>
                {hotlistAlertCount > 0 ? (
                  <span className="badge badge--critical">{hotlistAlertCount} hotlist</span>
                ) : null}
              </div>
            </div>
            <div className="map-summary-grid">
              <div className="map-summary-card">
                <span className="panel-label">Drive screen</span>
                <strong>{routeUnitLabel}</strong>
                <div className="map-summary-card__grid">
                  <StatusLine label="ETA" value={routeEtaLabel} />
                  <StatusLine label="Lead" value={routeLeadLabel} />
                  <StatusLine label="Progress" value={`${routeProgressPercent.toFixed(0)}%`} />
                  <StatusLine
                    label="Scan mode"
                    value={activeScanMode ? "Live scan" : navigationActive ? "Transit / classify" : "Idle"}
                  />
                  <StatusLine label="Alert scope" value={generalPopupsLive ? "General + hotlist" : "Hotlist only"} />
                  <StatusLine label="Hotlist" value={hotlistAlertCount > 0 ? `${hotlistAlertCount} active` : "Clear"} />
                </div>
              </div>
              <div className="map-summary-card">
                <span className="panel-label">Mission stages</span>
                <div className="map-stage-list">
                  {routeStages.map((stage) => (
                    <article
                      key={stage.id}
                      className={`map-stage-row map-stage-row--${stage.state} ${
                        currentRouteStage.id === stage.id ? "is-current" : ""
                      }`}
                    >
                      <div className="map-stage-row__meta">
                        <strong>{stage.label}</strong>
                        <span className={`badge ${routeStageTone(stage.state)}`}>{titleCaseLabel(stage.state)}</span>
                      </div>
                      <p>{stage.detail}</p>
                    </article>
                  ))}
                </div>
              </div>
              <div className="map-summary-card">
                <span className="panel-label">Crew and field status</span>
                <div className="map-summary-card__grid">
                  <StatusLine label="Crew live" value={`${activeSessionCount} sessions`} />
                  <StatusLine label="Cameras" value={`${mapCameraNodes.length} mapped`} />
                  <StatusLine label="Hotlist alerts" value={hotlistAlertCount > 0 ? `${hotlistAlertCount} active` : "Clear"} />
                  <StatusLine label="Pinned work" value={selectedFollowUp ? followUpStatusLabel(selectedFollowUp.status) : "None"} />
                  <StatusLine
                    label="Dispatch"
                    value={selectedAssignment ? assignmentStatusLabel(selectedAssignment.status) : "Pending"}
                  />
                </div>
                <ul className="route-focus-list route-focus-list--compact">
                  {routeFocusItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </PanelFrame>
        );
      case "cameraMatrix":
        return (
          <PanelFrame
            panelId={panelId}
            actions={
              <div className="view-toggle">
                {(["priority", "quad", "strip", "dual"] as CameraMode[]).map((mode) => (
                  <button
                    key={mode}
                    className={`toggle-chip ${layout.cameraMode === mode ? "is-active" : ""}`}
                    type="button"
                    onClick={() => setCameraMode(mode)}
                  >
                    {mode === "priority" ? "Priority" : mode === "quad" ? "Quad" : mode === "dual" ? "Dual" : "Strip"}
                  </button>
                ))}
              </div>
            }
          >
            <div className={`camera-grid camera-grid--${layout.cameraMode}`}>
              {(layout.cameraMode === "dual" ? cameraFeeds.slice(0, 2) : cameraFeeds).map((camera) => (
                <button
                  key={camera.id}
                  className={`camera-tile ${camera.id === selectedCamera.id ? "is-selected" : ""}`}
                  type="button"
                  onClick={() => setSelectedCameraId(camera.id)}
                >
                  <div className="camera-tile__video">
                    <div className="camera-tile__overlay" />
                    <span className="camera-tile__zone">{camera.zone}</span>
                    <strong>{camera.label}</strong>
                  </div>
                  <div className="camera-tile__meta">
                    <span>{camera.id}</span>
                    <span className={`badge ${camera.status === "Online" ? "badge--good" : "badge--muted"}`}>
                      {camera.status}
                    </span>
                    <span>{camera.fps} FPS</span>
                    <span>{camera.status === "Online" ? `${camera.tempC}C` : "--"}</span>
                  </div>
                </button>
              ))}
            </div>
            <div className="camera-footnote">
              Selected view: {selectedCamera.label} / {selectedCamera.role}
            </div>
          </PanelFrame>
        );
      case "hotlistFeed":
        return (
          <PanelFrame panelId={panelId}>
            <div className="queue-shell">
              <div className="queue-shell__header">
                <div>
                  <strong>{queueHeadline}</strong>
                  <span>{queueDescription}</span>
                </div>
                <div className="queue-shell__controls">
                  <div className="view-toggle">
                    {queueViewOptions.map((option) => (
                      <button
                        key={option.id}
                        className={`toggle-chip ${queueView === option.id ? "is-active" : ""}`}
                        type="button"
                        onClick={() => setQueueView(option.id)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                  <div className="queue-pager">
                    <button
                      className="button"
                      disabled={queuePageIndex === 0}
                      type="button"
                      onClick={() => setQueuePage((current) => Math.max(0, current - 1))}
                    >
                      Back
                    </button>
                    <span>{queueItemsTotal === 0 ? "No items" : `Page ${queuePageIndex + 1} / ${queuePageCount}`}</span>
                    <button
                      className="button"
                      disabled={queuePageIndex >= queuePageCount - 1 || queueItemsTotal === 0}
                      type="button"
                      onClick={() => setQueuePage((current) => Math.min(queuePageCount - 1, current + 1))}
                    >
                      Next
                    </button>
                  </div>
                </div>
              </div>
              {queueView === "popups" ? (
                visiblePopupHistory.length === 0 ? (
                  <div className="queue-empty">No popup events are waiting in the current log view.</div>
                ) : (
                  <div className="queue-list">
                    {visiblePopupHistory.map((event) => (
                      <article key={event.id} className="queue-card queue-card--popup">
                        <div className="queue-card__header">
                          <span className={`badge ${event.type === "hotlist" ? "badge--critical" : "badge--priority"}`}>
                            {detectionPopupTypeLabels[event.type]}
                          </span>
                          <span>{event.timestamp}</span>
                        </div>
                        <strong>{event.plate ?? "Plate unavailable"}</strong>
                        <p>{`${event.vehicle} / ${event.camera}`}</p>
                        <div className="queue-card__meta">
                          <span>{event.location}</span>
                          <span>{confidenceLabel(event.confidence)}</span>
                        </div>
                        <p>{event.note}</p>
                      </article>
                    ))}
                  </div>
                )
              ) : (
                <div className="queue-list">
                  {activeQueueRows.length === 0 ? (
                    <div className="queue-empty">{queueEmptyMessage}</div>
                  ) : (
                    activeQueueRows.map(({ alert, isHotlistMatch }) => (
                      <button
                        key={alert.id}
                        className={`queue-card ${alert.id === selectedAlert.id ? "is-selected" : ""}`}
                        type="button"
                        onClick={() => {
                          setSelectedAlertId(alert.id);
                          setFocusedDetectionId(alert.detectionId ?? null);
                          setTargetPanelTab("workflow");
                        }}
                      >
                        <div className="queue-card__header">
                          <span className={`badge ${isHotlistMatch ? "badge--critical" : `badge--${severityTone(alert.severity)}`}`}>
                            {isHotlistMatch ? "Hotlist" : scenarioLabels[alert.scenario]}
                          </span>
                          <span>{alert.time}</span>
                        </div>
                        <strong>{alert.plate}</strong>
                        <p>{alert.vehicle}</p>
                        <div className="queue-card__meta">
                          <span>{alert.location}</span>
                          <span>{alert.distance}</span>
                        </div>
                        <div className="queue-card__meta">
                          <span>{alert.camera}</span>
                          <span>{alert.routeAction}</span>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </PanelFrame>
        );
      case "selectedAlert":
        return (
          <PanelFrame panelId={panelId}>
            <div className="target-card">
              <div className="target-card__hero">
                <div className="target-evidence">
                  <div className="target-photo">
                    {selectedFramePreviewUrl && !framePreviewUnavailable ? (
                      <img
                        alt={`Evidence frame for ${selectedDisplayPlate}`}
                        className="target-photo__image"
                        src={selectedFramePreviewUrl}
                        onError={() => setFramePreviewUnavailable(true)}
                      />
                    ) : (
                      <div className="target-photo__placeholder">
                        <span>{liveDataSource === "live" ? "Evidence frame unavailable" : "Target photo"}</span>
                        <strong>{selectedDisplayPlate}</strong>
                      </div>
                    )}
                    <div className="target-photo__overlay">
                      <span>{selectedFramePreviewUrl && !framePreviewUnavailable ? "Live evidence frame" : "Target photo"}</span>
                      <strong>{selectedDisplayPlate}</strong>
                    </div>
                  </div>
                  <div className="target-crop">
                    {selectedPlateCropPreviewUrl && !plateCropPreviewUnavailable ? (
                      <img
                        alt={`Plate crop for ${selectedDisplayPlate}`}
                        className="target-crop__image"
                        src={selectedPlateCropPreviewUrl}
                        onError={() => setPlateCropPreviewUnavailable(true)}
                      />
                    ) : (
                      <div className="target-crop__placeholder">
                        {liveDataSource === "live" ? "Plate crop unavailable for this detection." : "Live plate crop preview"}
                      </div>
                    )}
                    <span className="target-crop__label">Plate crop</span>
                  </div>
                </div>
                <div className="target-keyline">
                  {selectedIsHotlistMatch ? (
                    <span className="badge badge--hotlist-always">Hotlist match</span>
                  ) : null}
                  <span className={`badge ${selectedAlertMatchesDetection ? `badge--${severityTone(selectedAlert.severity)}` : "badge--priority"}`}>
                    {selectedDisplayPrimaryBadge}
                  </span>
                  <span className="badge badge--outlined">{selectedDisplaySecondaryBadge}</span>
                  {selectedFollowUp ? (
                    <span className={`badge badge--${followUpPriorityTone(selectedFollowUp.priority)}`}>
                      Pinned {followUpStatusLabel(selectedFollowUp.status)}
                    </span>
                  ) : null}
                  {selectedAssignment ? (
                    <span className={`badge ${assignmentStatusTone(selectedAssignment.status)}`}>
                      {assignmentStatusLabel(selectedAssignment.status)}
                    </span>
                  ) : null}
                  <h3>{selectedDisplayVehicle}</h3>
                  <p>{selectedDisplayColorYear}</p>
                </div>
              </div>
              <div className="target-details">
                <StatusLine label="Camera" value={selectedDisplayCamera} />
                <StatusLine label="Confidence" value={formatOptionalConfidence(selectedDisplayConfidence)} />
                <StatusLine label="GPS" value={selectedDisplayGps} />
                <StatusLine label={selectedDetection ? "Frame" : "Distance"} value={selectedDetection ? `#${selectedDetection.frame_number}` : currentDistanceLabel} />
                <StatusLine
                  label="Evidence"
                  value={
                    selectedFramePreviewUrl && !framePreviewUnavailable
                      ? "Live frame ready"
                      : liveDataSource === "live"
                        ? "Waiting on local media"
                        : "Live API only"
                  }
                />
                <StatusLine
                  label="Sync"
                  value={selectedDetection ? selectedDetection.sync_status : liveDataSource === "live" ? "Live API" : "Demo data"}
                />
                <StatusLine
                  label="Latest review"
                  value={
                    reviewLoading
                      ? "Loading..."
                      : latestReview
                        ? reviewActionLabel(latestReview.action)
                        : reviewsEnabled
                          ? "No reviews yet"
                          : "Live API only"
                  }
                />
                <StatusLine
                  label="Follow-up"
                  value={
                    selectedFollowUp
                      ? `${followUpStatusLabel(selectedFollowUp.status)} / ${titleCaseLabel(selectedFollowUp.priority)}`
                      : liveDataSource === "live"
                        ? "Not pinned"
                        : "Live API only"
                  }
                />
                <StatusLine
                  label="Dispatch"
                  value={
                    selectedAssignment
                      ? assignmentStatusLabel(selectedAssignment.status)
                      : liveDataSource === "live"
                        ? "Not assigned"
                        : "Live API only"
                  }
                />
              </div>
              <div className="target-tabs">
                {targetPanelTabs.map((tab) => (
                  <button
                    key={tab.id}
                    className={`toggle-chip ${targetPanelTab === tab.id ? "is-active" : ""}`}
                    type="button"
                    onClick={() => setTargetPanelTab(tab.id)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <div className="target-tab-panel">
                {targetPanelTab === "overview" ? (
                  <>
                    <div className="notes-box">
                      <label className="panel-label">Best approach</label>
                      <p>{selectedDisplayBestApproach}</p>
                    </div>
                    <div className="notes-box">
                      <label className="panel-label">Field notes</label>
                      <p>{selectedWorkflowNotes}</p>
                    </div>
                    <div className="notes-box">
                      <div className="live-activity__header">
                        <strong>Follow-up and dispatch</strong>
                        <span>
                          {selectedFollowUp
                            ? `${followUpStatusLabel(selectedFollowUp.status)} follow-up`
                            : selectedAssignment
                              ? `${assignmentStatusLabel(selectedAssignment.status)} dispatch`
                              : "No pinned workflow yet"}
                        </span>
                      </div>
                      <p>
                        {selectedAssignment?.assigned_unit_label ? `${selectedAssignment.assigned_unit_label} / ` : ""}
                        {selectedAssignment?.assigned_operator_id ?? selectedFollowUp?.assigned_operator_id ?? "Unassigned"}
                        {selectedFollowUp?.due_at_utc ? ` / Due ${formatHotlistTimestamp(selectedFollowUp.due_at_utc)}` : ""}
                      </p>
                    </div>
                    {selectedDetection ? (
                      <div className="detection-insights">
                        <div className="notes-box">
                          <div className="live-activity__header">
                            <strong>OCR candidates</strong>
                            <span>
                              {selectedDetection.plate_candidates.length} candidate
                              {selectedDetection.plate_candidates.length === 1 ? "" : "s"}
                            </span>
                          </div>
                          {selectedDetection.plate_candidates.length === 0 ? (
                            <p>No alternate OCR candidates were retained for this detection.</p>
                          ) : (
                            <div className="candidate-list">
                              {selectedDetection.plate_candidates.slice(0, 5).map((candidate, index) => (
                                <div
                                  key={`${candidate.text}-${index}`}
                                  className={`candidate-row ${candidate.text === selectedDetection.plate_text ? "is-primary" : ""}`}
                                >
                                  <strong>{candidate.text}</strong>
                                  <span>{confidenceLabel(candidate.confidence)}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="notes-box">
                          <div className="live-activity__header">
                            <strong>Confidence breakdown</strong>
                            <span>Stored with the detection record</span>
                          </div>
                          <div className="confidence-grid">
                            <StatusLine label="OCR" value={formatOptionalConfidence(selectedDetection.plate_confidence)} />
                            <StatusLine label="Color" value={formatOptionalConfidence(selectedDetection.vehicle_color_confidence)} />
                            <StatusLine label="Make" value={formatOptionalConfidence(selectedDetection.vehicle_make_confidence)} />
                            <StatusLine label="Model" value={formatOptionalConfidence(selectedDetection.vehicle_model_confidence)} />
                            <StatusLine label="Year" value={formatOptionalConfidence(selectedDetection.optional_year_confidence)} />
                            <StatusLine label="Tracker" value={selectedDetection.tracker_id ?? "Untracked"} />
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </>
                ) : targetPanelTab === "workflow" ? (
                  <>
                    <div className="notes-box">
                      <label className="panel-label">Best approach</label>
                      <p>{selectedDisplayBestApproach}</p>
                    </div>
                    <div className="notes-box">
                      <div className="live-activity__header">
                        <strong>Follow-up and dispatch</strong>
                        <span>
                          {selectedFollowUp
                            ? `${followUpStatusLabel(selectedFollowUp.status)} follow-up`
                            : selectedAssignment
                              ? `${assignmentStatusLabel(selectedAssignment.status)} dispatch`
                              : "No pinned workflow yet"}
                        </span>
                      </div>
                      <p>
                        {selectedAssignment?.assigned_unit_label ? `${selectedAssignment.assigned_unit_label} / ` : ""}
                        {selectedAssignment?.assigned_operator_id ?? selectedFollowUp?.assigned_operator_id ?? "Unassigned"}
                        {selectedFollowUp?.due_at_utc ? ` / Due ${formatHotlistTimestamp(selectedFollowUp.due_at_utc)}` : ""}
                      </p>
                    </div>
                    <div className="notes-box">
                      <label className="panel-label">Field notes</label>
                      <p>{selectedWorkflowNotes}</p>
                    </div>
                    <div className="workflow-summary-grid">
                      <StatusLine label="Follow-up owner" value={selectedFollowUp?.assigned_operator_id ?? "Unassigned"} />
                      <StatusLine label="Dispatch unit" value={selectedAssignment?.assigned_unit_label ?? "Unset"} />
                      <StatusLine
                        label="Dispatch status"
                        value={selectedAssignment ? assignmentStatusLabel(selectedAssignment.status) : "Pending"}
                      />
                      <StatusLine label="Queue state" value={selectedFollowUp ? followUpStatusLabel(selectedFollowUp.status) : "Not pinned"} />
                    </div>
                  </>
                ) : null}
                {targetPanelTab === "reviews" ? (
                  <div className="review-shell">
                <div className="live-activity__header">
                  <strong>Operator review</strong>
                  <span>
                    {reviewsEnabled && currentOperator.capabilities.can_submit_reviews
                      ? "Persisted locally through the live API."
                      : reviewsEnabled
                        ? `${operatorDisplayName(currentOperator)} is read-only for review actions.`
                      : "Review submission unlocks when the live API is connected."}
                  </span>
                </div>
                {reviewsEnabled ? (
                  <>
                    <form className="review-form" onSubmit={handleReviewSubmit}>
                      <div className="form-grid review-form__grid">
                        <label className="field-group">
                          <span>Review action</span>
                          <select
                            value={reviewAction}
                            onChange={(event) => setReviewAction(event.target.value as ReviewAction)}
                          >
                            <option value="confirm">Confirm read</option>
                            <option value="correct">Correct read</option>
                            <option value="flag">Flag for follow-up</option>
                            <option value="dismiss">Dismiss hit</option>
                          </select>
                        </label>
                        <label className="field-group">
                          <span>Operator ID</span>
                          <input
                            className="input-control"
                            placeholder="cab_demo_01"
                            type="text"
                            value={reviewOperatorId}
                            onChange={(event) => setReviewOperatorId(event.target.value)}
                          />
                        </label>
                        <label className="field-group">
                          <span>Corrected plate</span>
                          <input
                            className="input-control"
                            disabled={reviewAction !== "correct"}
                            placeholder="Required for corrections"
                            type="text"
                            value={reviewCorrectedPlate}
                            onChange={(event) => setReviewCorrectedPlate(event.target.value.toUpperCase())}
                          />
                        </label>
                      </div>
                      <label className="field-group">
                        <span>Review notes</span>
                        <textarea
                          className="input-control input-control--multiline"
                          placeholder="Add field notes, confidence callouts, or next-step guidance."
                          value={reviewNotes}
                          onChange={(event) => setReviewNotes(event.target.value)}
                        />
                      </label>
                      {reviewError ? <div className="review-feedback review-feedback--error">{reviewError}</div> : null}
                      {reviewSuccess ? <div className="review-feedback review-feedback--good">{reviewSuccess}</div> : null}
                      <div className="panel-actions">
                        <button className="button button--primary" disabled={!canSubmitReview} type="submit">
                          {reviewSubmitting ? "Saving review..." : "Save review"}
                        </button>
                        <span className="panel-label">
                          {reviewLoading ? "Loading review history..." : `${reviewHistory.length} review${reviewHistory.length === 1 ? "" : "s"} on file`}
                        </span>
                      </div>
                    </form>
                    <div className="review-history">
                      <div className="live-activity__header">
                        <strong>Recent review history</strong>
                        <span>
                          {latestReview
                            ? `Last update ${formatReviewTimestamp(latestReview.reviewed_at_utc)}`
                            : "No saved reviews for this detection yet."}
                        </span>
                      </div>
                      {reviewHistory.length === 0 ? (
                        <div className="review-empty">No operator reviews have been saved for this detection yet.</div>
                      ) : (
                        reviewHistory.slice(0, 4).map((review) => (
                          <div key={review.review_id} className="review-row">
                            <div className="review-row__header">
                              <span className={`badge ${reviewActionBadgeTone(review.action)}`}>
                                {reviewActionLabel(review.action)}
                              </span>
                              <span>{formatReviewTimestamp(review.reviewed_at_utc)}</span>
                            </div>
                            <strong>{review.corrected_plate_text ?? selectedDisplayPlate}</strong>
                            <p>
                              {review.operator_id ? `${review.operator_id} / ` : ""}
                              {review.notes ?? "No operator notes recorded."}
                            </p>
                          </div>
                        ))
                      )}
                    </div>
                  </>
                ) : (
                  <div className="review-empty">
                    Connect the live API to load local review history and save operator review actions.
                  </div>
                )}
                  </div>
                ) : null}
              </div>
            </div>
          </PanelFrame>
        );
      case "recoveryLog":
        return (
          <PanelFrame panelId={panelId}>
            <div className="log-list">
              {recoveryLogEntries.map((entry) => {
                const entryLiveAlert = liveOverview?.alerts.find((alert) => alert.alert_id === entry.id);
                const entryIsHotlist = entryLiveAlert ? !!entryLiveAlert.hotlist_entry_id : entry.status === "active";
                const entryFollowUp = liveFollowUps.find(
                  (record) => record.detection_id === entryLiveAlert?.detection_id && record.status !== "resolved",
                );
                const entryAssignment = liveAssignments.find(
                  (record) =>
                    record.detection_id === entryLiveAlert?.detection_id &&
                    record.status !== "completed" &&
                    record.status !== "cancelled",
                );
                return (
                  <div key={entry.id} className="log-row">
                    <span
                      className={`badge badge--${
                        entry.status === "active" ? "good" : entry.status === "watch" ? "priority" : "muted"
                      }`}
                    >
                      {entry.status}
                    </span>
                    <div>
                      <strong>
                        {entry.title}
                        {entryIsHotlist ? " [Hotlist]" : ""}
                      </strong>
                      <p>
                        {entry.plate}
                        {entryFollowUp ? ` / Pinned ${followUpStatusLabel(entryFollowUp.status)}` : ""}
                        {entryAssignment ? ` / ${assignmentStatusLabel(entryAssignment.status)}` : ""}
                      </p>
                    </div>
                    <span>{entry.updatedAt}</span>
                  </div>
                );
              })}
            </div>
          </PanelFrame>
        );
      case "dispatchBoard":
        return (
          <PanelFrame panelId={panelId}>
            <div className="runtime-shell">
              <div className="live-activity__header">
                <strong>Follow-up pin</strong>
                <span>
                  {canManageFollowUps
                    ? "Pin high-value detections and keep follow-up ownership visible."
                    : liveDataSource === "live" && selectedDetectionId
                      ? `${operatorDisplayName(currentOperator)} can view follow-ups but cannot edit them.`
                      : "Connect the live API and select a detection to pin follow-up work."}
                </span>
              </div>
              {liveDataSource === "live" && selectedDetectionId ? (
                <div className="review-shell">
                  <div className="runtime-summary">
                    <div className="runtime-summary__grid">
                      <StatusLine label="Selected plate" value={selectedDisplayPlate} />
                      <StatusLine
                        label="Follow-up state"
                        value={selectedFollowUp ? followUpStatusLabel(selectedFollowUp.status) : "Not pinned"}
                      />
                      <StatusLine
                        label="Priority"
                        value={selectedFollowUp ? titleCaseLabel(selectedFollowUp.priority) : titleCaseLabel(followUpPriority)}
                      />
                      <StatusLine
                        label="Assigned"
                        value={(selectedFollowUp?.assigned_operator_id ?? followUpAssignedOperatorId.trim()) || "Unassigned"}
                      />
                    </div>
                  </div>
                  <form className="review-form" onSubmit={handleFollowUpSubmit}>
                    <div className="form-grid review-form__grid">
                      <label className="field-group">
                        <span>Priority</span>
                        <select
                          value={followUpPriority}
                          onChange={(event) => setFollowUpPriority(event.target.value as FollowUpPriority)}
                        >
                          <option value="routine">Routine</option>
                          <option value="priority">Priority</option>
                          <option value="critical">Critical</option>
                        </select>
                      </label>
                      <label className="field-group">
                        <span>Status</span>
                        <select value={followUpStatus} onChange={(event) => setFollowUpStatus(event.target.value as FollowUpStatus)}>
                          <option value="open">Open</option>
                          <option value="monitoring">Monitoring</option>
                          <option value="resolved">Resolved</option>
                        </select>
                      </label>
                      <label className="field-group">
                        <span>Assigned operator</span>
                        <input
                          className="input-control"
                          placeholder="tow_lead_02"
                          type="text"
                          value={followUpAssignedOperatorId}
                          onChange={(event) => setFollowUpAssignedOperatorId(event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Follow-up due</span>
                        <input
                          className="input-control"
                          type="datetime-local"
                          value={followUpDueAt}
                          onChange={(event) => setFollowUpDueAt(event.target.value)}
                        />
                      </label>
                    </div>
                    <label className="field-group">
                      <span>Pin summary</span>
                      <input
                        className="input-control"
                        placeholder="Pin this read until the field crew is staged."
                        type="text"
                        value={followUpSummary}
                        onChange={(event) => setFollowUpSummary(event.target.value)}
                      />
                    </label>
                    <label className="field-group">
                      <span>Follow-up notes</span>
                      <textarea
                        className="input-control input-control--multiline"
                        placeholder="Capture the reason this detection stays pinned and what the next operator should do."
                        value={followUpNotes}
                        onChange={(event) => setFollowUpNotes(event.target.value)}
                      />
                    </label>
                    {followUpError ? <div className="review-feedback review-feedback--error">{followUpError}</div> : null}
                    {followUpSuccess ? <div className="review-feedback review-feedback--good">{followUpSuccess}</div> : null}
                    <div className="panel-actions">
                      <button className="button button--primary" disabled={!canManageFollowUps || followUpSubmitting} type="submit">
                        {followUpSubmitting ? "Saving follow-up..." : selectedFollowUp ? "Update follow-up" : "Pin detection"}
                      </button>
                      <span className="panel-label">
                        {openFollowUpCount} open follow-up{openFollowUpCount === 1 ? "" : "s"} across the dashboard
                      </span>
                    </div>
                  </form>
                </div>
              ) : (
                <div className="review-empty">Connect the live API to pin detections for follow-up.</div>
              )}

              <div className="live-activity__header">
                <strong>Dispatch assignment</strong>
                <span>
                  {canManageAssignments
                    ? "Create a field assignment that survives beyond the alert lifecycle buttons."
                    : liveDataSource === "live" && selectedDetectionId
                      ? `${operatorDisplayName(currentOperator)} can view assignments but cannot dispatch them.`
                      : "Connect the live API and select a detection to create dispatch work."}
                </span>
              </div>
              {liveDataSource === "live" && selectedDetectionId ? (
                <div className="review-shell">
                  <div className="runtime-summary">
                    <div className="runtime-summary__grid">
                      <StatusLine label="Assignment" value={selectedAssignment ? assignmentStatusLabel(selectedAssignment.status) : "None"} />
                      <StatusLine
                        label="Priority"
                        value={selectedAssignment ? titleCaseLabel(selectedAssignment.priority) : titleCaseLabel(assignmentPriority)}
                      />
                      <StatusLine
                        label="Assigned unit"
                        value={(selectedAssignment?.assigned_unit_label ?? assignmentUnitLabel.trim()) || "Unset"}
                      />
                      <StatusLine
                        label="Destination"
                        value={(selectedAssignment?.destination_label ?? assignmentDestination.trim()) || "Unset"}
                      />
                    </div>
                  </div>
                  <form className="review-form" onSubmit={handleAssignmentSubmit}>
                    <div className="form-grid review-form__grid">
                      <label className="field-group">
                        <span>Priority</span>
                        <select
                          value={assignmentPriority}
                          onChange={(event) => setAssignmentPriority(event.target.value as DispatchAssignmentPriority)}
                        >
                          <option value="watch">Watch</option>
                          <option value="priority">Priority</option>
                          <option value="critical">Critical</option>
                        </select>
                      </label>
                      <label className="field-group">
                        <span>Status</span>
                        <select
                          value={assignmentStatus}
                          onChange={(event) => setAssignmentStatus(event.target.value as DispatchAssignmentStatus)}
                        >
                          <option value="queued">Queued</option>
                          <option value="assigned">Assigned</option>
                          <option value="en_route">En Route</option>
                          <option value="onsite">On Scene</option>
                          <option value="completed">Completed</option>
                          <option value="cancelled">Cancelled</option>
                        </select>
                      </label>
                      <label className="field-group">
                        <span>Assigned operator</span>
                        <input
                          className="input-control"
                          placeholder="tow_lead_02"
                          type="text"
                          value={assignmentOperatorId}
                          onChange={(event) => setAssignmentOperatorId(event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Assigned unit</span>
                        <input
                          className="input-control"
                          placeholder="Truck 4"
                          type="text"
                          value={assignmentUnitLabel}
                          onChange={(event) => setAssignmentUnitLabel(event.target.value)}
                        />
                      </label>
                    </div>
                    <div className="form-grid review-form__grid">
                      <label className="field-group">
                        <span>Destination</span>
                        <input
                          className="input-control"
                          placeholder="1250 Shoreline Blvd"
                          type="text"
                          value={assignmentDestination}
                          onChange={(event) => setAssignmentDestination(event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Assignment brief</span>
                        <input
                          className="input-control"
                          placeholder="Tow team rolling to the pinned target."
                          type="text"
                          value={assignmentSummary}
                          onChange={(event) => setAssignmentSummary(event.target.value)}
                        />
                      </label>
                    </div>
                    <label className="field-group">
                      <span>Dispatch notes</span>
                      <textarea
                        className="input-control input-control--multiline"
                        placeholder="Record approach instructions, staging notes, and scene handoff details."
                        value={assignmentNotes}
                        onChange={(event) => setAssignmentNotes(event.target.value)}
                      />
                    </label>
                    {assignmentError ? <div className="review-feedback review-feedback--error">{assignmentError}</div> : null}
                    {assignmentSuccess ? <div className="review-feedback review-feedback--good">{assignmentSuccess}</div> : null}
                    <div className="panel-actions">
                      <button className="button button--primary" disabled={!canManageAssignments || assignmentSubmitting} type="submit">
                        {assignmentSubmitting ? "Saving assignment..." : selectedAssignment ? "Update assignment" : "Create assignment"}
                      </button>
                      <span className="panel-label">
                        {activeAssignmentCount} active assignment{activeAssignmentCount === 1 ? "" : "s"} on the board
                      </span>
                    </div>
                  </form>
                  {liveAssignments.length > 0 ? (
                    <div className="review-history">
                      <div className="live-activity__header">
                        <strong>Active dispatch board</strong>
                        <span>Recent assignments across the live dashboard.</span>
                      </div>
                      {liveAssignments.slice(0, 4).map((assignment) => (
                        <div key={assignment.assignment_id} className="review-row">
                          <div className="review-row__header">
                            <span className={`badge ${assignmentStatusTone(assignment.status)}`}>
                              {assignmentStatusLabel(assignment.status)}
                            </span>
                            <span>{formatHotlistTimestamp(assignment.updated_at_utc)}</span>
                          </div>
                          <strong>{assignment.plate_text ?? "Plate unavailable"}</strong>
                          <p>
                            {(assignment.assigned_unit_label ?? "No unit") + " / " + (assignment.assigned_operator_id ?? "No operator")}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="review-empty">Connect the live API to create and track dispatch assignments.</div>
              )}

              <div className="live-activity__header">
                <strong>Demo runtime</strong>
                <span className={`badge ${demoRuntimeBadgeTone(demoRuntimeStatus?.state)}`}>
                  {demoRuntimeLabel(demoRuntimeStatus?.state)}
                </span>
              </div>
              {demoRuntimeEnabled ? (
                <>
                  <div className="runtime-summary">
                    <div className="runtime-summary__grid">
                      <StatusLine label="Run ID" value={demoRuntimeStatus?.run_id ?? "Waiting"} />
                      <StatusLine
                        label="Started"
                        value={
                          demoRuntimeStatus?.started_at_utc
                            ? formatHotlistTimestamp(demoRuntimeStatus.started_at_utc)
                            : "Not started"
                        }
                      />
                      <StatusLine
                        label="Completed"
                        value={
                          demoRuntimeStatus?.completed_at_utc
                            ? formatHotlistTimestamp(demoRuntimeStatus.completed_at_utc)
                            : demoRuntimeStatus?.state === "running"
                              ? "In progress"
                              : "Not completed"
                        }
                      />
                      <StatusLine
                        label="Plate seed"
                        value={demoRuntimeStatus?.plate_text ?? (demoPlateText.trim().toUpperCase() || "Unset")}
                      />
                    </div>
                    <div className="runtime-summary__grid">
                      <StatusLine
                        label="Frames folder"
                        value={demoRuntimeStatus?.frames_directory ?? (demoFramesDirectory.trim() || "Set a local path")}
                      />
                      <StatusLine
                        label="Detections"
                        value={String(demoRuntimeStatus?.summary?.stored_detection_ids.length ?? 0)}
                      />
                      <StatusLine
                        label="Alerts"
                        value={String(demoRuntimeStatus?.summary?.created_alert_ids.length ?? 0)}
                      />
                      <StatusLine
                        label="Tracks"
                        value={String(demoRuntimeStatus?.summary?.tracks_finalized ?? 0)}
                      />
                    </div>
                  </div>
                  <form className="review-form" onSubmit={handleDemoRunSubmit}>
                    <div className="form-grid review-form__grid">
                      <label className="field-group">
                        <span>Frame folder</span>
                        <input
                          className="input-control"
                          placeholder="C:\\frames\\demo-run"
                          type="text"
                          value={demoFramesDirectory}
                          onChange={(event) => setDemoFramesDirectory(event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Sequence ID</span>
                        <input
                          className="input-control"
                          placeholder="seq_console_demo"
                          type="text"
                          value={demoSequenceId}
                          onChange={(event) => setDemoSequenceId(event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Plate seed</span>
                        <input
                          className="input-control"
                          placeholder="6BZN220"
                          type="text"
                          value={demoPlateText}
                          onChange={(event) => setDemoPlateText(event.target.value.toUpperCase())}
                        />
                      </label>
                    </div>
                    {demoLoading ? <div className="review-empty">Loading demo runtime status...</div> : null}
                    {demoError ? <div className="review-feedback review-feedback--error">{demoError}</div> : null}
                    {demoSuccess ? <div className="review-feedback review-feedback--good">{demoSuccess}</div> : null}
                    <div className="panel-actions">
                      <button className="button button--primary" disabled={!canStartDemoRun} type="submit">
                        {demoSubmitting
                          ? "Starting demo..."
                          : demoRuntimeStatus?.state === "running"
                            ? "Demo running..."
                            : "Run headless demo"}
                      </button>
                      <button
                        className="button"
                        disabled={!demoRuntimeEnabled || demoLoading}
                        type="button"
                        onClick={() => {
                          void refreshDemoStatus();
                        }}
                      >
                        Refresh status
                      </button>
                      <button className="button" type="button" onClick={() => setDemoPlateText(selectedAlert.plate)}>
                        Use selected plate
                      </button>
                    </div>
                  </form>
                </>
              ) : (
                <div className="review-empty">
                  Connect the live API to launch headless demo ingest runs from the app and watch new detections land live.
                </div>
              )}
              <div className="live-activity__header">
                <strong>Alert response</strong>
                <span>
                  {alertActionsEnabled
                    ? "Persisted locally through the live API."
                    : alertActionsAvailable
                      ? `${operatorDisplayName(currentOperator)} can view alert response history but cannot change status.`
                    : "Connect the live API to acknowledge, stand down, or reopen alerts."}
                </span>
              </div>
              {alertActionsAvailable && selectedLiveAlert ? (
                <div className="review-shell">
                  <div className="runtime-summary">
                    <div className="runtime-summary__grid">
                      <StatusLine label="Workflow state" value={statusLabels[selectedAlert.status]} />
                      <StatusLine label="Recommended action" value={selectedAlert.routeAction} />
                      <StatusLine label="Operator" value={selectedLiveAlert.response_operator_id ?? "Unassigned"} />
                      <StatusLine
                        label="Last update"
                        value={
                          selectedLiveAlert.updated_at_utc
                            ? formatHotlistTimestamp(selectedLiveAlert.updated_at_utc)
                            : "No field action recorded"
                        }
                      />
                    </div>
                  </div>
                  <div className="review-form">
                    <div className="form-grid review-form__grid">
                      <label className="field-group">
                        <span>Operator ID</span>
                        <input
                          className="input-control"
                          placeholder="cab_demo_01"
                          type="text"
                          value={alertActionOperatorId}
                          onChange={(event) => setAlertActionOperatorId(event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Selected target</span>
                        <input className="input-control" disabled type="text" value={`${selectedAlert.plate} / ${selectedAlert.vehicle}`} />
                      </label>
                    </div>
                    <label className="field-group">
                      <span>Response notes</span>
                      <textarea
                        className="input-control input-control--multiline"
                        placeholder="Record contact attempts, scene conditions, or stand-down context."
                        value={alertActionNotes}
                        onChange={(event) => setAlertActionNotes(event.target.value)}
                      />
                    </label>
                    {alertActionError ? (
                      <div className="review-feedback review-feedback--error">{alertActionError}</div>
                    ) : null}
                    {alertActionSuccess ? (
                      <div className="review-feedback review-feedback--good">{alertActionSuccess}</div>
                    ) : null}
                    <div className="action-grid">
                      <button
                        className={`button ${selectedLiveAlert.status === "active" ? "button--primary" : ""}`}
                        disabled={!alertActionsEnabled || alertActionSubmitting || selectedLiveAlert.status === "acknowledged"}
                        type="button"
                        onClick={() => {
                          void handleAlertAction("acknowledged");
                        }}
                      >
                        {alertActionPendingStatus === "acknowledged" ? "Saving..." : "Acknowledge"}
                      </button>
                      <button
                        className={`button ${selectedLiveAlert.status === "acknowledged" ? "button--primary" : ""}`}
                        disabled={!alertActionsEnabled || alertActionSubmitting || selectedLiveAlert.status === "dismissed"}
                        type="button"
                        onClick={() => {
                          void handleAlertAction("dismissed");
                        }}
                      >
                        {alertActionPendingStatus === "dismissed" ? "Saving..." : "Stand down"}
                      </button>
                      <button
                        className={`button ${selectedLiveAlert.status === "dismissed" ? "button--primary" : ""}`}
                        disabled={!alertActionsEnabled || alertActionSubmitting || selectedLiveAlert.status === "active"}
                        type="button"
                        onClick={() => {
                          void handleAlertAction("active");
                        }}
                      >
                        {alertActionPendingStatus === "active" ? "Saving..." : "Re-open"}
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="review-empty">
                  Connect the live API to save field actions and keep alert status changes across refreshes.
                </div>
              )}
            </div>
          </PanelFrame>
        );
      case "crewChat":
        return (
          <PanelFrame panelId={panelId}>
            <div className="crew-chat">
              <div className="crew-chat__messages">
                {chatMessages.map((msg) => (
                  <div key={msg.id} className={`crew-chat__row crew-chat__row--${msg.type}`}>
                    <div className="crew-chat__meta">
                      <strong>{msg.sender}</strong>
                      <span>{msg.timestamp}</span>
                    </div>
                    <p>{msg.body}</p>
                  </div>
                ))}
              </div>
              <form
                className="crew-chat__compose"
                onSubmit={(event: FormEvent) => {
                  event.preventDefault();
                  const body = chatDraftMessage.trim();
                  if (!body) return;
                  setChatMessages((current) => [
                    ...current,
                    {
                      id: `msg-${Date.now()}`,
                      sender: currentOperator.display_name ?? currentOperator.principal_id,
                      body,
                      timestamp: new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false }),
                      type: "message",
                    },
                  ]);
                  setChatDraftMessage("");
                }}
              >
                <input
                  className="input-control"
                  placeholder="Message crew..."
                  type="text"
                  value={chatDraftMessage}
                  onChange={(event) => setChatDraftMessage(event.target.value)}
                />
                <button className="button button--primary" type="submit">Send</button>
              </form>
              <div className="crew-chat__actions">
                <button
                  className="button"
                  type="button"
                  onClick={() => {
                    setChatMessages((current) => [
                      ...current,
                      {
                        id: `handoff-${Date.now()}`,
                        sender: "System",
                        body: `Handoff initiated by ${currentOperator.display_name ?? currentOperator.principal_id} for ${selectedAlert.plate} - ${selectedAlert.vehicle}`,
                        timestamp: new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false }),
                        type: "handoff",
                      },
                    ]);
                  }}
                >
                  Handoff current target
                </button>
                <button
                  className="button"
                  type="button"
                  onClick={() => {
                    const photoId = `photo-${Date.now()}`;
                    const timestamp = new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
                    setFieldPhotoLog((current) => [
                      ...current,
                      { id: photoId, label: `Evidence ${current.length + 1}`, timestamp, note: fieldPhotoNote.trim() || "No annotation" },
                    ]);
                    setChatMessages((current) => [
                      ...current,
                      {
                        id: `photo-msg-${Date.now()}`,
                        sender: "System",
                        body: `Field photo captured - ${fieldPhotoNote.trim() || "No annotation"}`,
                        timestamp,
                        type: "system",
                      },
                    ]);
                    setFieldPhotoNote("");
                  }}
                >
                  Capture field photo
                </button>
              </div>
              <label className="field-group">
                <span>Photo annotation</span>
                <input
                  className="input-control"
                  placeholder="Describe what you see before capture"
                  type="text"
                  value={fieldPhotoNote}
                  onChange={(event) => setFieldPhotoNote(event.target.value)}
                />
              </label>
              {fieldPhotoLog.length > 0 ? (
                <div className="crew-chat__photo-log">
                  <div className="live-activity__header">
                    <strong>Evidence log</strong>
                    <span>{fieldPhotoLog.length} captured</span>
                  </div>
                  {fieldPhotoLog.map((photo) => (
                    <div key={photo.id} className="crew-chat__row crew-chat__row--system">
                      <div className="crew-chat__meta">
                        <strong>{photo.label}</strong>
                        <span>{photo.timestamp}</span>
                      </div>
                      <p>{photo.note}</p>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </PanelFrame>
        );
      default:
        return (
          <PanelFrame panelId={panelId}>
            <div />
          </PanelFrame>
        );
    }
  }

  function renderWorkspace(): ReactElement {
    const dashboardWorkspace = (
      <section className="workspace-card">
        <div className="workspace-card__header">
          <div>
            <div className="eyebrow">Mission screens</div>
            <h2>Repossession workflow</h2>
            <p>
              Switch between drive, queue, recover, and crew screens so only the right layer of information stays in
              view for the current recovery phase.
            </p>
          </div>
          <div className="workspace-card__actions workspace-card__actions--stacked">
            <div className="mission-switcher">
              {dashboardScreenOptions.map((screen) => (
                <button
                  key={screen.id}
                  className={`toggle-chip ${dashboardScreen === screen.id ? "is-active" : ""}`}
                  type="button"
                  onClick={() => setDashboardScreen(screen.id)}
                >
                  {screen.label}
                </button>
              ))}
            </div>
            <label className="field-group mission-select">
              <span>Console screen</span>
              <select value={dashboardScreen} onChange={(event) => setDashboardScreen(event.target.value as DashboardScreenId)}>
                {dashboardScreenOptions.map((screen) => (
                  <option key={screen.id} value={screen.id}>
                    {screen.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <div className="mission-summary-card">
          <span className="panel-label">{dashboardScreenMeta.label}</span>
          <strong>{currentRouteStage.label}</strong>
          <p>{dashboardScreenMeta.summary}</p>
        </div>
        {dashboardScreen === "drive" ? (
          <div className="mission-board mission-board--drive">
            <div className="mission-board__hero">{renderPanel("opsMap")}</div>
            <div className="mission-board__aside">
              {renderPanel("routePlanner")}
              {renderPanel("statusStack")}
            </div>
            <div className="mission-board__full">{renderPanel("cameraMatrix")}</div>
          </div>
        ) : dashboardScreen === "queue" ? (
          <div className="mission-board mission-board--queue">
            <div className="mission-board__hero">{renderPanel("hotlistFeed")}</div>
            <div className="mission-board__aside">{renderPanel("selectedAlert")}</div>
          </div>
        ) : dashboardScreen === "recover" ? (
          <div className="mission-board mission-board--recover">
            <div className="mission-board__hero">{renderPanel("selectedAlert")}</div>
            <div className="mission-board__aside">{renderPanel("dispatchBoard")}</div>
            <div className="mission-board__full">{renderPanel("cameraMatrix")}</div>
          </div>
        ) : (
          <div className="mission-board mission-board--crew">
            <div className="mission-board__hero">{renderPanel("recoveryLog")}</div>
            <div className="mission-board__aside">{renderPanel("crewChat")}</div>
            <div className="mission-board__full">{renderPanel("statusStack")}</div>
          </div>
        )}
      </section>
    );

    if (activeWorkspace === "navigation") {
      return (
        <section className="workspace-card">
          <div className="workspace-card__header">
            <div>
              <div className="eyebrow">Driving screen</div>
              <h2>Drive</h2>
              <p>Keep the next move, target radius, and latest target changes visible while the truck is rolling.</p>
            </div>
          </div>
          <div className="navigation-shell">
            <aside className="navigation-rail">
              {renderPanel("routePlanner")}
              {renderPanel("statusStack")}
              {renderPanel("recoveryLog")}
            </aside>
            <div className="navigation-main">
              <div className="navigation-map">{renderPanel("opsMap")}</div>
              <div className="navigation-bottom">
                <div className="navigation-bottom__wide">{renderPanel("cameraMatrix")}</div>
                <div>{renderPanel("selectedAlert")}</div>
              </div>
            </div>
          </div>
        </section>
      );
    }

    if (activeWorkspace === "alerts") {
      return (
        <section className="workspace-card">
          <div className="workspace-card__header">
            <div>
              <div className="eyebrow">Target queue</div>
              <h2>Targets</h2>
              <p>Work the live queue, prioritize hotlists, and push the next field action without extra clicks.</p>
            </div>
          </div>
          <div className="alerts-shell">
            <div className="alerts-shell__feed">{renderPanel("hotlistFeed")}</div>
            <div className="alerts-shell__detail">
              {renderPanel("selectedAlert")}
              {renderPanel("dispatchBoard")}
            </div>
          </div>
        </section>
      );
    }

    if (activeWorkspace === "search") {
      return (
        <section className="workspace-card">
          <div className="workspace-card__header">
            <div>
              <div className="eyebrow">Evidence review</div>
              <h2>Review</h2>
              <p>Search full or partial plates, narrow by field filters, and jump straight into evidence review.</p>
            </div>
            <div className="workspace-card__actions">
              <button
                className="button"
                type="button"
                onClick={() =>
                  setSearchForm((current) => ({
                    ...current,
                    plate: selectedDisplayPlate,
                    plateMatch: "exact",
                  }))
                }
              >
                Use selected plate
              </button>
              <button className="button" type="button" onClick={resetSearchFilters}>
                Reset filters
              </button>
            </div>
          </div>
          {liveDataSource !== "live" ? (
            <div className="review-empty search-empty">
              Connect the live API to search live detections by plate, date, camera, GPS region, and vehicle attributes.
            </div>
          ) : (
            <div className="search-shell">
              <aside className="search-shell__filters">
                <PanelFrame panelId="routePlanner" titleOverride="Search Filters">
                  <form className="review-form" onSubmit={handleSearchSubmit}>
                    <div className="form-grid search-filter-grid">
                      <label className="field-group">
                        <span>Plate</span>
                        <input
                          className="input-control"
                          placeholder="6BZN220 or partial"
                          type="text"
                          value={searchForm.plate}
                          onChange={(event) => updateSearchField("plate", event.target.value.toUpperCase())}
                        />
                      </label>
                      <label className="field-group">
                        <span>Match mode</span>
                        <select value={searchForm.plateMatch} onChange={(event) => updateSearchField("plateMatch", event.target.value as SearchPlateMatchMode)}>
                          <option value="contains">Contains</option>
                          <option value="exact">Exact</option>
                          <option value="prefix">Prefix</option>
                          <option value="suffix">Suffix</option>
                        </select>
                      </label>
                      <label className="field-group">
                        <span>Camera</span>
                        <select value={searchForm.cameraId} onChange={(event) => updateSearchField("cameraId", event.target.value)}>
                          <option value="">All cameras</option>
                          {searchCameraChoices.map((cameraId) => (
                            <option key={cameraId} value={cameraId}>
                              {formatCameraLabel(cameraId)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field-group">
                        <span>Alert state</span>
                        <select value={searchForm.alertStatus} onChange={(event) => updateSearchField("alertStatus", event.target.value as SearchFormState["alertStatus"])}>
                          <option value="">Any status</option>
                          <option value="active">Active</option>
                          <option value="acknowledged">Acknowledged</option>
                          <option value="dismissed">Dismissed</option>
                        </select>
                      </label>
                      <label className="field-group">
                        <span>Start UTC</span>
                        <input
                          className="input-control"
                          type="datetime-local"
                          value={searchForm.startUtc}
                          onChange={(event) => updateSearchField("startUtc", event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>End UTC</span>
                        <input
                          className="input-control"
                          type="datetime-local"
                          value={searchForm.endUtc}
                          onChange={(event) => updateSearchField("endUtc", event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Min latitude</span>
                        <input
                          className="input-control"
                          placeholder="37.4200"
                          type="text"
                          value={searchForm.minLatitude}
                          onChange={(event) => updateSearchField("minLatitude", event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Max latitude</span>
                        <input
                          className="input-control"
                          placeholder="37.4300"
                          type="text"
                          value={searchForm.maxLatitude}
                          onChange={(event) => updateSearchField("maxLatitude", event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Min longitude</span>
                        <input
                          className="input-control"
                          placeholder="-122.0900"
                          type="text"
                          value={searchForm.minLongitude}
                          onChange={(event) => updateSearchField("minLongitude", event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Max longitude</span>
                        <input
                          className="input-control"
                          placeholder="-122.0700"
                          type="text"
                          value={searchForm.maxLongitude}
                          onChange={(event) => updateSearchField("maxLongitude", event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Vehicle color</span>
                        <input
                          className="input-control"
                          placeholder="white"
                          type="text"
                          value={searchForm.vehicleColor}
                          onChange={(event) => updateSearchField("vehicleColor", event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Vehicle make</span>
                        <input
                          className="input-control"
                          placeholder="toyota"
                          type="text"
                          value={searchForm.vehicleMake}
                          onChange={(event) => updateSearchField("vehicleMake", event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Vehicle model</span>
                        <input
                          className="input-control"
                          placeholder="camry"
                          type="text"
                          value={searchForm.vehicleModel}
                          onChange={(event) => updateSearchField("vehicleModel", event.target.value)}
                        />
                      </label>
                      <label className="field-group">
                        <span>Vehicle year</span>
                        <input
                          className="input-control"
                          placeholder="2019"
                          type="text"
                          value={searchForm.vehicleYear}
                          onChange={(event) => updateSearchField("vehicleYear", event.target.value)}
                        />
                      </label>
                    </div>
                    {searchError ? <div className="review-feedback review-feedback--error">{searchError}</div> : null}
                    <div className="panel-actions">
                      <button className="button button--primary" disabled={searchLoading} type="submit">
                        {searchLoading ? "Searching..." : "Run search"}
                      </button>
                      <button
                        className="button"
                        type="button"
                        onClick={() =>
                          setSearchForm((current) => ({
                            ...current,
                            startUtc: liveOverview?.generated_at_utc ? formatLocalDateTimeInput(liveOverview.generated_at_utc) : current.startUtc,
                          }))
                        }
                      >
                        Use current time
                      </button>
                    </div>
                  </form>
                </PanelFrame>
              </aside>
              <div className="search-shell__content">
                <PanelFrame panelId="hotlistFeed" titleOverride="Search Results">
                  <div className="search-results">
                    <div className="search-results__header">
                      <div className="live-activity__header">
                        <strong>{searchExecuted ? `${searchTotalResults} result${searchTotalResults === 1 ? "" : "s"}` : "Awaiting search"}</strong>
                        <span>
                          {searchLoading
                            ? "Querying the live API..."
                            : searchExecuted
                              ? searchPageLabel
                              : "Search by full or partial plate and refine by field filters."}
                        </span>
                      </div>
                      <div className="queue-pager">
                        <button
                          className="button"
                          disabled={!searchExecuted || searchLoading || searchOffset === 0}
                          type="button"
                          onClick={() => changeSearchPage(-1)}
                        >
                          Back
                        </button>
                        <span>{searchExecuted ? `Page ${searchPageIndex + 1} / ${searchPageCount}` : "Page 0 / 0"}</span>
                        <button
                          className="button"
                          disabled={!searchExecuted || searchLoading || searchOffset + searchResults.length >= searchTotalResults}
                          type="button"
                          onClick={() => changeSearchPage(1)}
                        >
                          Next
                        </button>
                      </div>
                    </div>
                    {searchExecuted && searchResults.length === 0 ? (
                      <div className="review-empty">No detections matched the current search filters.</div>
                    ) : (
                      <div className="search-results__list">
                        {searchResults.map((result) => {
                          const matchingAlert = liveOverview?.alerts.find((alert) => alert.detection_id === result.detection_id) ?? null;
                          const matchingFollowUp =
                            liveFollowUps.find((record) => record.detection_id === result.detection_id && record.status !== "resolved") ??
                            liveFollowUps.find((record) => record.detection_id === result.detection_id) ??
                            null;
                          const matchingAssignment =
                            liveAssignments.find(
                              (record) =>
                                record.detection_id === result.detection_id &&
                                record.status !== "completed" &&
                                record.status !== "cancelled",
                            ) ??
                            liveAssignments.find((record) => record.detection_id === result.detection_id) ??
                            null;
                          return (
                            <button
                              key={result.detection_id}
                              className={`search-result-card ${result.detection_id === selectedDetectionId ? "is-selected" : ""}`}
                              type="button"
                              onClick={() => focusDetection(result.detection_id, matchingAlert?.alert_id)}
                            >
                              <div className="search-result-card__header">
                                <div>
                                  <strong>{result.plate_text ?? "Plate unavailable"}</strong>
                                  <p>{buildDetectionVehicleLabel(result, "Live vehicle")}</p>
                                </div>
                                <div className="search-result-card__badges">
                                  {matchingAlert ? (
                                    <span className={`badge ${matchingAlert.status === "active" ? "badge--critical" : matchingAlert.status === "acknowledged" ? "badge--priority" : "badge--muted"}`}>
                                      {matchingAlert.status}
                                    </span>
                                  ) : (
                                    <span className="badge badge--outlined">No alert</span>
                                  )}
                                  {matchingFollowUp ? (
                                    <span className={`badge badge--${followUpPriorityTone(matchingFollowUp.priority)}`}>
                                      {followUpStatusLabel(matchingFollowUp.status)}
                                    </span>
                                  ) : null}
                                  {matchingAssignment ? (
                                    <span className={`badge ${assignmentStatusTone(matchingAssignment.status)}`}>
                                      {assignmentStatusLabel(matchingAssignment.status)}
                                    </span>
                                  ) : null}
                                  <span className="badge badge--outlined">{formatOptionalConfidence(result.plate_confidence)}</span>
                                </div>
                              </div>
                              <div className="search-result-card__meta">
                                <span>{formatCameraLabel(result.camera_id)}</span>
                                <span>{formatReviewTimestamp(result.timestamp_utc)}</span>
                              </div>
                              <div className="search-result-card__meta">
                                <span>{buildDetectionColorYearLabel(result, "Unknown / Unknown")}</span>
                                <span>{formatGpsLabel(result.gps_latitude, result.gps_longitude)}</span>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </PanelFrame>
                <div className="search-shell__detail">{renderPanel("selectedAlert")}</div>
              </div>
            </div>
          )}
        </section>
      );
    }

    if (activeWorkspace === "cameras") {
      return (
        <section className="workspace-card">
          <div className="workspace-card__header">
            <div>
              <div className="eyebrow">Vehicle confirmation</div>
              <h2>Cameras</h2>
              <p>Keep the truck camera bank clean, large, and easy to read when confirming plates and vehicles.</p>
            </div>
          </div>
          <div className="camera-shell">
            <div className="camera-shell__grid">{renderPanel("cameraMatrix")}</div>
            <div className="camera-shell__detail">
              {renderPanel("hotlistFeed")}
              {renderPanel("selectedAlert")}
            </div>
          </div>
        </section>
      );
    }

    if (activeWorkspace === "settings") {
      return (
        <section className="workspace-card">
          <div className="workspace-card__header">
            <div>
              <div className="eyebrow">Cab profile</div>
              <h2>Settings</h2>
              <p>
                Saved in this browser so each truck can tune the repo workflow layout and alert behavior for the agent using it.
              </p>
            </div>
            <div className="workspace-card__actions">
              <button className="button" type="button" onClick={() => setLayout(cloneLayout(dashboardPresets.route))}>
                Restore default screens
              </button>
              <button className="button" type="button" onClick={() => setFieldSettings({ ...defaultFieldSettings })}>
                Reset field settings
              </button>
            </div>
          </div>
          <div className="settings-grid">
            <PanelFrame panelId="routePlanner" titleOverride="Screen presets">
              <div className="settings-section">
                <div className="preset-list">
                  {(["route", "recovery", "streetSweep", "cameraOps", "navLpr", "dualCamNav"] as LayoutPresetId[]).map((presetId) => (
                    <button key={presetId} className="preset-card" type="button" onClick={() => applyPreset(presetId)}>
                      <strong>{dashboardPresets[presetId].profile}</strong>
                      <p>{presetDescriptions[presetId]}</p>
                    </button>
                  ))}
                </div>
                <div className="layout-editor__grid">
                  {(Object.keys(layout.slots) as SlotId[]).map((slot) => (
                    <label key={slot} className="field-group">
                      <span>{layoutSlotLabels[slot]}</span>
                      <select value={layout.slots[slot]} onChange={(event) => movePanelToSlot(slot, event.target.value as PanelId)}>
                        {(Object.keys(panelCatalog) as PanelId[]).map((panelId) => (
                          <option key={panelId} value={panelId}>
                            {panelCatalog[panelId].label}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                  <label className="field-group">
                    <span>Camera mode</span>
                    <select value={layout.cameraMode} onChange={(event) => setCameraMode(event.target.value as CameraMode)}>
                      <option value="priority">Priority</option>
                      <option value="quad">Quad</option>
                      <option value="strip">Strip</option>
                      <option value="dual">Dual</option>
                    </select>
                  </label>
                </div>
              </div>
            </PanelFrame>
            <PanelFrame panelId="statusStack" titleOverride="Drive and detection">
              <div className="form-grid">
                <label className="field-group">
                  <span>Target refresh interval</span>
                  <select
                    value={fieldSettings.targetRefreshInterval}
                    onChange={(event) => updateFieldSetting("targetRefreshInterval", event.target.value)}
                  >
                    <option value="30 sec">30 sec</option>
                    <option value="60 sec">60 sec</option>
                    <option value="2 min">2 min</option>
                  </select>
                </label>
                <label className="field-group">
                  <span>Arrival trigger distance</span>
                  <select
                    value={String(fieldSettings.arrivalTriggerDistance)}
                    onChange={(event) => updateFieldSetting("arrivalTriggerDistance", Number(event.target.value))}
                  >
                    <option value="150">150 ft</option>
                    <option value="300">300 ft</option>
                    <option value="600">600 ft</option>
                  </select>
                </label>
                <label className="field-check">
                  <span>Show route traffic overlay</span>
                  <input
                    checked={fieldSettings.routeTrafficOverlay}
                    type="checkbox"
                    onChange={(event) => updateFieldSetting("routeTrafficOverlay", event.target.checked)}
                  />
                </label>
                <label className="field-check">
                  <span>Auto mark on scene</span>
                  <input
                    checked={fieldSettings.autoMarkOnScene}
                    type="checkbox"
                    onChange={(event) => updateFieldSetting("autoMarkOnScene", event.target.checked)}
                  />
                </label>
              </div>
            </PanelFrame>
            <PanelFrame panelId="selectedAlert" titleOverride="Detection review">
              <div className="form-grid">
                <label className="field-group">
                  <span>OCR confidence floor</span>
                  <select
                    value={fieldSettings.ocrConfidenceThreshold.toFixed(2)}
                    onChange={(event) => updateFieldSetting("ocrConfidenceThreshold", Number(event.target.value))}
                  >
                    <option value="0.70">0.70</option>
                    <option value="0.80">0.80</option>
                    <option value="0.90">0.90</option>
                  </select>
                </label>
                <label className="field-group">
                  <span>Max active targets</span>
                  <select
                    value={String(fieldSettings.maxActiveTargets)}
                    onChange={(event) => updateFieldSetting("maxActiveTargets", Number(event.target.value))}
                  >
                    <option value="5">5</option>
                    <option value="10">10</option>
                    <option value="20">20</option>
                  </select>
                </label>
                <label className="field-check">
                  <span>Silent shift mode</span>
                  <input
                    checked={fieldSettings.silentShiftMode}
                    type="checkbox"
                    onChange={(event) => updateFieldSetting("silentShiftMode", event.target.checked)}
                  />
                </label>
                <label className="field-check">
                  <span>Low storage warning</span>
                  <input
                    checked={fieldSettings.lowStorageWarning}
                    type="checkbox"
                    onChange={(event) => updateFieldSetting("lowStorageWarning", event.target.checked)}
                  />
                </label>
              </div>
            </PanelFrame>
            <PanelFrame panelId="dispatchBoard" titleOverride="Operator Workflow">
              <div className="settings-section">
                <div className="live-activity__header">
                  <strong>Live identity and permissions</strong>
                  <span>
                    {liveDataSource === "live"
                      ? `Heartbeat active for ${operatorDisplayName(currentOperator)}.`
                      : "Paste an API key here when the deployment requires authenticated access."}
                  </span>
                </div>
                <form
                  className="review-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    setApiClientConfig({ apiKey });
                    void refreshOverview();
                  }}
                >
                  <div className="form-grid review-form__grid">
                    <label className="field-group">
                      <span>API key</span>
                      <input
                        autoComplete="off"
                        className="input-control"
                        placeholder="viewer-demo-token / operator-demo-token / admin-demo-token"
                        type="password"
                        value={apiKey}
                        onChange={(event) => setApiKey(event.target.value)}
                      />
                    </label>
                    <label className="field-group">
                      <span>Session label</span>
                      <input
                        className="input-control"
                        placeholder="cab_console_01"
                        type="text"
                        value={sessionLabel}
                        onChange={(event) => setSessionLabel(event.target.value)}
                      />
                    </label>
                  </div>
                  <div className="panel-actions">
                    <button className="button button--primary" type="submit">
                      Reconnect live API
                    </button>
                    <button
                      className="button"
                      type="button"
                      onClick={() => {
                        setApiClientConfig({ apiKey: "" });
                        setApiKey("");
                        void refreshOverview();
                      }}
                    >
                      Clear key
                    </button>
                  </div>
                </form>
                <div className="notes-box">
                  <div className="live-activity__header">
                    <strong>{operatorDisplayName(currentOperator)}</strong>
                    <span>{currentOperator.authenticated ? "Authenticated" : "Local development mode"}</span>
                  </div>
                  <div className="badge-group">
                    {currentOperator.roles.map((role) => (
                      <span key={role} className="badge badge--outlined">
                        {operatorRoleLabel(role)}
                      </span>
                    ))}
                    {!currentOperator.capabilities.can_manage_hotlists ? (
                      <span className="badge badge--muted">Hotlist read-only</span>
                    ) : null}
                    {!currentOperator.capabilities.can_manage_dispatch ? (
                      <span className="badge badge--muted">Dispatch read-only</span>
                    ) : null}
                  </div>
                </div>
                <div className="review-history">
                  <div className="live-activity__header">
                    <strong>Active crew sessions</strong>
                    <span>{activeSessionCount} active session{activeSessionCount === 1 ? "" : "s"} on the live console.</span>
                  </div>
                  {liveDataSource !== "live" ? (
                    <div className="review-empty">Connect the live API to see other operator sessions and workspaces.</div>
                  ) : otherActiveSessions.length === 0 ? (
                    <div className="review-empty">No other live sessions are active right now.</div>
                  ) : (
                    otherActiveSessions.slice(0, 6).map((session) => (
                      <div key={session.session_id} className="review-row">
                        <div className="review-row__header">
                          <span className="badge badge--outlined">{workspaceLabel(session.workspace)}</span>
                          <span>{formatHotlistTimestamp(session.last_seen_at_utc)}</span>
                        </div>
                        <strong>{session.client_label ?? operatorDisplayName(session)}</strong>
                        <p>
                          {operatorDisplayName(session)} / {session.selected_detection_id ?? session.selected_alert_id ?? "No active target"}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </PanelFrame>
            <PanelFrame panelId="hotlistFeed" titleOverride="Hotlist Control">
              <div className="hotlist-manager">
                <div className="live-activity__header">
                  <strong>Local hotlist control</strong>
                  <span>
                    {hotlistsEnabled && currentOperator.capabilities.can_manage_hotlists
                      ? `${hotlistEntries.length} hotlist entr${hotlistEntries.length === 1 ? "y" : "ies"} loaded from the live API.`
                      : hotlistsEnabled
                        ? `${operatorDisplayName(currentOperator)} can view hotlists but cannot edit them.`
                      : "Connect the live API to create and update local hotlist entries."}
                  </span>
                </div>
                {hotlistsEnabled ? (
                  <>
                    <div className="hotlist-list">
                      {hotlistLoading ? (
                        <div className="review-empty">Loading hotlist entries...</div>
                      ) : hotlistEntries.length === 0 ? (
                        <div className="review-empty">No hotlist entries saved yet. Create the first one below.</div>
                      ) : (
                        hotlistEntries.map((entry) => (
                          <button
                            key={entry.entry_id}
                            className={`hotlist-row ${entry.entry_id === selectedHotlistId ? "is-selected" : ""}`}
                            type="button"
                            onClick={() => loadHotlistForm(entry)}
                          >
                            <div className="hotlist-row__header">
                              <strong>{entry.plate_text}</strong>
                              <span className={`badge ${entry.active ? "badge--critical" : "badge--muted"}`}>
                                {entry.active ? "Active" : "Paused"}
                              </span>
                            </div>
                            <p>{entry.label ?? "Unlabeled entry"}</p>
                            <div className="hotlist-row__meta">
                              <span>{entry.notes ?? "No operator notes."}</span>
                              <span>{formatHotlistTimestamp(entry.updated_at_utc)}</span>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                    <form className="review-form" onSubmit={handleHotlistSubmit}>
                      <div className="form-grid review-form__grid">
                        <label className="field-group">
                          <span>Plate text</span>
                          <input
                            className="input-control"
                            placeholder="8ABC123"
                            type="text"
                            value={hotlistPlateText}
                            onChange={(event) => setHotlistPlateText(event.target.value.toUpperCase())}
                          />
                        </label>
                        <label className="field-group">
                          <span>Label</span>
                          <input
                            className="input-control"
                            placeholder="Tow-ready / watch / case name"
                            type="text"
                            value={hotlistLabel}
                            onChange={(event) => setHotlistLabel(event.target.value)}
                          />
                        </label>
                        <label className="field-check">
                          <span>Entry active</span>
                          <input
                            checked={hotlistActive}
                            type="checkbox"
                            onChange={(event) => setHotlistActive(event.target.checked)}
                          />
                        </label>
                      </div>
                      <label className="field-group">
                        <span>Hotlist notes</span>
                        <textarea
                          className="input-control input-control--multiline"
                          placeholder="Describe why this vehicle is being monitored and what the field crew should do next."
                          value={hotlistNotes}
                          onChange={(event) => setHotlistNotes(event.target.value)}
                        />
                      </label>
                      {hotlistError ? <div className="review-feedback review-feedback--error">{hotlistError}</div> : null}
                      {hotlistSuccess ? <div className="review-feedback review-feedback--good">{hotlistSuccess}</div> : null}
                      <div className="panel-actions">
                        <button className="button button--primary" disabled={!canSubmitHotlist} type="submit">
                          {hotlistSaving ? "Saving hotlist..." : selectedHotlist ? "Update hotlist" : "Create hotlist"}
                        </button>
                        <button className="button" type="button" onClick={() => loadHotlistForm(null)}>
                          New entry
                        </button>
                        <button
                          className="button"
                          type="button"
                          onClick={() =>
                            loadHotlistForm({
                              entry_id: "",
                              plate_text: selectedAlert.plate,
                              label: selectedAlert.vehicle,
                              notes: selectedAlert.notes,
                              active: true,
                              created_at_utc: "",
                              updated_at_utc: "",
                            })
                          }
                        >
                          Seed from selected alert
                        </button>
                      </div>
                    </form>
                  </>
                ) : (
                  <div className="review-empty">
                    Connect the live API to load local hotlist entries and manage watchlists from this panel.
                  </div>
                )}
              </div>
            </PanelFrame>
          </div>
        </section>
      );
    }

    return dashboardWorkspace;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-eyebrow">RepoScan Pro</div>
          <h1>Recovery Ops Console</h1>
          <p>Cab-first repo workflow for Windows 11 field laptops.</p>
        </div>
        <nav className="tabbar" aria-label="Primary workspace">
          {workspaceTabs.map((tab) => (
            <button
              key={tab.id}
              className={`tabbar__button ${tab.id === activeWorkspace ? "is-active" : ""}`}
              type="button"
              onClick={() => selectWorkspace(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      <section className="glance-strip" aria-label="Current cab summary">
        {glanceTiles.map((tile) => (
          <GlanceTile key={tile.label} label={tile.label} value={tile.value} sublabel={tile.sublabel} />
        ))}
      </section>

      <section className="mode-banner">
        <div className="mode-banner__group">
          <span className={`badge ${liveDataSource === "live" ? "badge--good" : "badge--outlined"}`}>
            {liveDataSource === "live" ? "Live API" : liveDataSource === "fallback" ? "Demo fallback" : "Demo only"}
          </span>
          <span className={`badge ${activeScanMode ? "badge--scan-live" : navigationActive ? "badge--scan-bg" : "badge--outlined"}`}>
            {activeScanMode ? "Scan live" : navigationActive ? "Transit" : "Idle"}
          </span>
          <span className="badge badge--hotlist-always">Hotlist always on</span>
        </div>
        <div className="mode-banner__divider" />
        <div className="mode-banner__group">
          <span>{operatorDisplayName(currentOperator)}</span>
          <span>Alerts: {activeAlertCount}</span>
          <span>Pins: {openFollowUpCount}</span>
          <span>Dispatch: {activeAssignmentCount}</span>
          <span>Crew: {activeSessionCount}</span>
        </div>
        <div className="mode-banner__divider" />
        <span>
          {generalPopupsLive
            ? "Inside radius. General + hotlist popups live."
            : !addressDetectionEnabled
              ? "Address popups off. Hotlist unsuppressed."
              : "Outside radius. Background classify. Hotlist unsuppressed."}
        </span>
        {liveError ? <span>{liveError}</span> : null}
        {operatorSessionError ? <span>{operatorSessionError}</span> : null}
      </section>

      {popupStack.length > 0 ? (
        <aside className="popup-stack" aria-live="polite">
          {popupStack.map((popup) => (
            <article key={popup.instanceId} className={`popup-card popup-card--${popup.type}`}>
              <div className="popup-card__media">
                <span>{popup.imageLabel}</span>
                <strong>{popup.plate ?? "Plate unavailable"}</strong>
              </div>
              <div className="popup-card__body">
                <div className="popup-card__header">
                  <span className={`badge ${popup.type === "hotlist" ? "badge--critical" : "badge--priority"}`}>
                    {detectionPopupTypeLabels[popup.type]}
                  </span>
                  <span className="popup-card__signal">
                    {popup.type === "hotlist"
                      ? fieldSettings.silentShiftMode
                        ? "Visual priority alert"
                        : "Audible + visual alert"
                      : "Visual popup"}
                  </span>
                  <button className="icon-button" type="button" onClick={() => dismissPopup(popup.instanceId)}>
                    Dismiss
                  </button>
                </div>
                <strong>{popup.vehicle}</strong>
                <p>{popup.colorYear}</p>
                <div className="popup-card__meta">
                  <span>{popup.timestamp}</span>
                  <span>{popup.camera}</span>
                </div>
                <div className="popup-card__meta">
                  <span>{popup.location}</span>
                  <span>{popup.gps}</span>
                </div>
                <p>{popup.note}</p>
              </div>
            </article>
          ))}
        </aside>
      ) : null}

      <main>{renderWorkspace()}</main>
    </div>
  );
}

/* Leaflet helpers */

const defaultMapCenter: [number, number] = [33.749, -84.388]; // Atlanta demo coords
const defaultMapZoom = 14;

function makeIcon(color: string, size: number = 12): L.DivIcon {
  return L.divIcon({
    className: "leaflet-marker-custom",
    html: `<span style="display:block;width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 0 6px ${color}"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

const unitIcon = makeIcon("#4a90ff", 16);
const alertIconCritical = makeIcon("#ff4d6a", 14);
const alertIconPriority = makeIcon("#ffb347", 12);
const alertIconWatch = makeIcon("#7eb8ff", 10);
const cameraIcon = makeIcon("#53d6a0", 10);
const sessionIcon = makeIcon("#c084fc", 10);
const destinationIcon = makeIcon("#f2f6ff", 12);

function alertMarkerIcon(severity: string, isHotlist: boolean): L.DivIcon {
  if (isHotlist) return alertIconCritical;
  if (severity === "critical") return alertIconCritical;
  if (severity === "priority") return alertIconPriority;
  return alertIconWatch;
}

function MapAutoFit(props: { points: [number, number][]; zoom: number }): null {
  const map = useMap();
  const pointsKey = props.points.map(([lat, lng]) => `${lat.toFixed(6)},${lng.toFixed(6)}`).join("|");
  useEffect(() => {
    if (props.points.length === 0) {
      return;
    }

    if (props.points.length === 1) {
      map.setView(props.points[0], props.zoom, { animate: true });
      return;
    }

    const bounds = L.latLngBounds(props.points);
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.16), { animate: true });
    }
  }, [map, pointsKey, props.zoom]);
  return null;
}

interface OpsMapLeafletProps {
  unitPosition: { lat: number; lng: number };
  destinationPosition: { lat: number; lng: number };
  destinationLabel: string;
  alertMarkers: Array<{
    id: string;
    lat: number;
    lng: number;
    plate: string;
    severity: string;
    isHotlist: boolean;
    onSelect: () => void;
  }>;
  cameraNodes: Array<{ id: string; lat: number; lng: number; zone: string }>;
  sessionNodes: Array<{ id: string; lat: number; lng: number; label: string }>;
  arrivalRadius: number;
  withinArrival: boolean;
  routePath: [number, number][];
}

function OpsMapLeaflet(props: OpsMapLeafletProps): ReactElement {
  const fitPoints: [number, number][] = [
    [props.unitPosition.lat, props.unitPosition.lng],
    [props.destinationPosition.lat, props.destinationPosition.lng],
    ...props.routePath,
    ...props.alertMarkers.map((marker) => [marker.lat, marker.lng] as [number, number]),
    ...props.cameraNodes.map((camera) => [camera.lat, camera.lng] as [number, number]),
    ...props.sessionNodes.map((session) => [session.lat, session.lng] as [number, number]),
  ];

  return (
    <div className="leaflet-map-wrapper">
      <MapContainer
        center={[props.destinationPosition.lat, props.destinationPosition.lng]}
        zoom={defaultMapZoom}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%", borderRadius: "22px" }}
        zoomControl={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapAutoFit points={fitPoints} zoom={defaultMapZoom} />

        <Marker position={[props.destinationPosition.lat, props.destinationPosition.lng]} icon={destinationIcon}>
          <Popup>
            <strong>{props.destinationLabel}</strong>
            <br />
            Arrival radius: {props.arrivalRadius} ft
          </Popup>
        </Marker>

        {/* Unit marker */}
        <Marker position={[props.unitPosition.lat, props.unitPosition.lng]} icon={unitIcon}>
          <Popup>
            <strong>Recovery unit</strong>
          </Popup>
        </Marker>

        {/* Arrival ring */}
        <Circle
          center={[props.destinationPosition.lat, props.destinationPosition.lng]}
          radius={props.arrivalRadius * 0.3048}
          pathOptions={{
            color: props.withinArrival ? "#53d6a0" : "#4a90ff",
            fillColor: props.withinArrival ? "rgba(83,214,160,0.12)" : "rgba(74,144,255,0.08)",
            fillOpacity: 0.3,
            weight: 2,
            dashArray: props.withinArrival ? undefined : "6 4",
          }}
        />

        {/* Route path */}
        {props.routePath.length > 1 ? (
          <Polyline
            positions={props.routePath}
            pathOptions={{ color: "#78b0ff", weight: 3, opacity: 0.75 }}
          />
        ) : null}

        {/* Alert markers */}
        {props.alertMarkers.map((marker) => (
          <Marker
            key={marker.id}
            position={[marker.lat, marker.lng]}
            icon={alertMarkerIcon(marker.severity, marker.isHotlist)}
            eventHandlers={{ click: marker.onSelect }}
          >
            <Popup>
              <strong>{marker.plate}</strong>
              <br />
              {marker.isHotlist ? "Hotlist match" : marker.severity}
            </Popup>
          </Marker>
        ))}

        {/* Camera nodes */}
        {props.cameraNodes.map((cam) => (
          <Marker key={cam.id} position={[cam.lat, cam.lng]} icon={cameraIcon}>
            <Popup>
              {cam.id} - {cam.zone}
            </Popup>
          </Marker>
        ))}

        {/* Session nodes */}
        {props.sessionNodes.map((sess) => (
          <Marker key={sess.id} position={[sess.lat, sess.lng]} icon={sessionIcon}>
            <Popup>{sess.label}</Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}

function PanelFrame(props: {
  panelId: PanelId;
  children: ReactNode;
  actions?: ReactNode;
  titleOverride?: string;
}): ReactElement {
  const meta = panelCatalog[props.panelId];
  return (
    <section className="panel-frame">
      <div className="panel-frame__header">
        <div>
          <h3>{props.titleOverride ?? meta.label}</h3>
          <p>{meta.description}</p>
        </div>
        {props.actions}
      </div>
      {props.children}
    </section>
  );
}

function StatusLine(props: { label: string; value: string }): ReactElement {
  return (
    <div className="status-line">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

function StatusRow(props: { label: string; value: string; tone: "good" | "warn" | "neutral" }): ReactElement {
  return (
    <div className="status-row">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      <em className={`status-dot status-dot--${props.tone}`} />
    </div>
  );
}

function GlanceTile(props: { label: string; value: string; sublabel: string }): ReactElement {
  return (
    <div className="glance-tile">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      <small>{props.sublabel}</small>
    </div>
  );
}

export default App;
