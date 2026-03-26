import { startTransition, useEffect, useRef, useState, type CSSProperties, type FormEvent, type ReactElement, type ReactNode } from "react";

import {
  addressScanDetections,
  alerts,
  cameraFeeds,
  dashboardPresets,
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
        parsed.cameraMode === "priority" || parsed.cameraMode === "quad" || parsed.cameraMode === "strip"
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
  const [layoutEditorOpen, setLayoutEditorOpen] = useState(false);
  const [layout, setLayout] = useState<DashboardLayout>(() => loadLayout());
  const [fieldSettings, setFieldSettings] = useState<FieldSettings>(() => loadFieldSettings());
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
        ? `Frame ${selectedDetection.frame_number} · Sync status ${selectedDetection.sync_status}`
        : "Select a live detection to inspect OCR candidates and attribute confidence.");
  const searchCameraChoices = Array.from(
    new Set((liveOverview?.detections ?? []).map((record) => record.camera_id)),
  ).sort((left, right) => left.localeCompare(right));
  const selectedWorkflowNotes = selectedAssignment?.notes ?? selectedFollowUp?.notes ?? selectedDisplayNotes;
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
    });
  }, [withinArrivalRadius]);

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
    });
  }

  function updateSearchField<K extends keyof SearchFormState>(key: K, value: SearchFormState[K]): void {
    setSearchForm((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function resetSearchFilters(): void {
    setSearchForm(defaultSearchFormState);
    setSearchResults([]);
    setSearchTotalResults(0);
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

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
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
        limit: 50,
        offset: 0,
      });

      setSearchResults(response.results);
      setSearchTotalResults(response.page.total_results);
      setSearchExecuted(true);

      if (response.results.length > 0) {
        const firstDetection = response.results[0];
        const matchingAlert = liveOverview?.alerts.find((alert) => alert.detection_id === firstDetection.detection_id) ?? null;
        focusDetection(firstDetection.detection_id, matchingAlert?.alert_id);
      }
    } catch (error) {
      setSearchResults([]);
      setSearchTotalResults(0);
      setSearchExecuted(true);
      setSearchError(error instanceof Error ? error.message : "Failed to run search");
    } finally {
      setSearchLoading(false);
    }
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
                  placeholder="Enter repo address or lot name"
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
                <span className={`badge ${activeScanMode ? "badge--good" : navigationActive ? "badge--priority" : "badge--muted"}`}>
                  {navigationModeLabel}
                </span>
                <span className={`badge ${addressDetectionEnabled ? "badge--good" : "badge--muted"}`}>
                  Address alerts {addressDetectionEnabled ? "on" : "off"}
                </span>
                <span className="badge badge--critical">Hotlist always on</span>
              </div>
              <div className="route-meta-grid">
                <StatusLine label="Current range" value={currentDistanceLabel} />
                <StatusLine label="Scenario" value={scenarioLabels[selectedAlert.scenario]} />
                <StatusLine label="Arrival ring" value={`${fieldSettings.arrivalTriggerDistance} ft`} />
                <StatusLine label="Popup policy" value={generalPopupsLive ? "General + hotlist" : "Hotlist only"} />
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
              <div className="trigger-meter">
                <div
                  className="trigger-meter__fill"
                  style={{ "--fill": `${Math.min(100, (Math.max(0, 1760 - currentDistanceFeet) / 1760) * 100)}%` } as CSSProperties}
                />
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
                label="Address scan"
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
            <div className="map-canvas">
              <div className="map-grid" />
              <div className="map-route map-route--one" />
              <div className="map-route map-route--two" />
              <div className="map-arrival-ring" />
              {operatorAlerts.map((alert, index) => (
                <button
                  key={alert.id}
                  className={`map-marker map-marker--${severityTone(alert.severity)} ${
                    alert.id === selectedAlert.id ? "is-active" : ""
                  }`}
                  style={{ "--x": `${18 + index * 19}%`, "--y": `${20 + (index % 3) * 18}%` } as CSSProperties}
                  type="button"
                  onClick={() => {
                    setSelectedAlertId(alert.id);
                    setFocusedDetectionId(alert.detectionId ?? null);
                  }}
                >
                  {index + 1}
                </button>
              ))}
              <div className="map-legend">
                <span>{selectedAlert.bestApproach}</span>
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
                {(["priority", "quad", "strip"] as CameraMode[]).map((mode) => (
                  <button
                    key={mode}
                    className={`toggle-chip ${layout.cameraMode === mode ? "is-active" : ""}`}
                    type="button"
                    onClick={() => setCameraMode(mode)}
                  >
                    {mode === "priority" ? "Priority" : mode === "quad" ? "Quad" : "Strip"}
                  </button>
                ))}
              </div>
            }
          >
            <div className={`camera-grid camera-grid--${layout.cameraMode}`}>
              {cameraFeeds.map((camera) => (
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
            <div className="alert-table">
              <div className="alert-table__header">
                <span>Time</span>
                <span>Plate</span>
                <span>Scenario</span>
                <span>Location</span>
                <span>Action</span>
              </div>
              {operatorAlerts.map((alert) => (
                <button
                  key={alert.id}
                  className={`alert-row ${alert.id === selectedAlert.id ? "is-selected" : ""}`}
                  type="button"
                  onClick={() => {
                    setSelectedAlertId(alert.id);
                    setFocusedDetectionId(alert.detectionId ?? null);
                  }}
                >
                  <span>{alert.time}</span>
                  <span>
                    <strong>{alert.plate}</strong>
                    <em className={`badge badge--${severityTone(alert.severity)}`}>{alert.severity}</em>
                  </span>
                  <span>{scenarioLabels[alert.scenario]}</span>
                  <span>{alert.location}</span>
                  <span>{alert.routeAction}</span>
                </button>
              ))}
            </div>
            <div className="live-activity">
              <div className="live-activity__header">
                <strong>Live popup activity</strong>
                <span>{generalPopupsLive ? "Address scan and hotlist popups are flowing." : "Only hotlist popups are unsuppressed."}</span>
              </div>
              {popupHistory.length === 0 ? (
                <div className="live-activity__row">
                  <span className="badge badge--outlined">Idle</span>
                  <div>
                    <strong>No active popup events</strong>
                    <p>Waiting for the next unsuppressed live event.</p>
                  </div>
                  <span>Live</span>
                </div>
              ) : (
                popupHistory.map((event) => (
                <div key={event.id} className="live-activity__row">
                  <span className={`badge ${event.type === "hotlist" ? "badge--critical" : "badge--priority"}`}>
                    {detectionPopupTypeLabels[event.type]}
                  </span>
                  <div>
                    <strong>{event.plate ?? "Plate unavailable"}</strong>
                    <p>
                      {event.vehicle} · {event.camera}
                    </p>
                  </div>
                  <span>{event.timestamp}</span>
                </div>
                ))
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
                  {selectedAssignment?.assigned_unit_label
                    ? `${selectedAssignment.assigned_unit_label} · `
                    : ""}
                  {selectedAssignment?.assigned_operator_id ?? selectedFollowUp?.assigned_operator_id ?? "Unassigned"}
                  {selectedFollowUp?.due_at_utc ? ` · Due ${formatHotlistTimestamp(selectedFollowUp.due_at_utc)}` : ""}
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
                              {review.operator_id ? `${review.operator_id} · ` : ""}
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
            </div>
          </PanelFrame>
        );
      case "recoveryLog":
        return (
          <PanelFrame panelId={panelId}>
            <div className="log-list">
              {recoveryLogEntries.map((entry) => (
                <div key={entry.id} className="log-row">
                  <span
                    className={`badge badge--${
                      entry.status === "active" ? "good" : entry.status === "watch" ? "priority" : "muted"
                    }`}
                  >
                    {entry.status}
                  </span>
                  <div>
                    <strong>{entry.title}</strong>
                    <p>{entry.plate}</p>
                  </div>
                  <span>{entry.updatedAt}</span>
                </div>
              ))}
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
                          placeholder="Shoreline Marina south lot"
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
                            {(assignment.assigned_unit_label ?? "No unit") + " · " + (assignment.assigned_operator_id ?? "No operator")}
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
                        <input className="input-control" disabled type="text" value={`${selectedAlert.plate} · ${selectedAlert.vehicle}`} />
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
            <div className="eyebrow">Custom operator layout</div>
            <h2>Recovery dashboard</h2>
            <p>
              Move map, cameras, alerts, and target details into the positions that work best inside the cab.
            </p>
          </div>
          <div className="workspace-card__actions">
            <div className="preset-switcher">
              {(["route", "recovery", "lotScan"] as LayoutPresetId[]).map((presetId) => (
                <button
                  key={presetId}
                  className={`toggle-chip ${
                    layout.profile === dashboardPresets[presetId].profile ? "is-active" : ""
                  }`}
                  type="button"
                  onClick={() => applyPreset(presetId)}
                >
                  {dashboardPresets[presetId].profile}
                </button>
              ))}
            </div>
            <button className="button" type="button" onClick={() => setLayoutEditorOpen((current) => !current)}>
              {layoutEditorOpen ? "Hide layout tools" : "Customize layout"}
            </button>
          </div>
        </div>
        {layoutEditorOpen ? (
          <div className="layout-editor">
            <div className="layout-editor__header">
              <div>
                <strong>{layout.profile}</strong>
                <p>Saved in this browser for this laptop profile.</p>
              </div>
              <div className="view-toggle">
                {(["priority", "quad", "strip"] as CameraMode[]).map((mode) => (
                  <button
                    key={mode}
                    className={`toggle-chip ${layout.cameraMode === mode ? "is-active" : ""}`}
                    type="button"
                    onClick={() => setCameraMode(mode)}
                  >
                    {mode}
                  </button>
                ))}
              </div>
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
            </div>
          </div>
        ) : null}
        <div className="dashboard-shell">
          <div className="dashboard-rail">
            <div className="slot-frame">{renderPanel(layout.slots.railTop)}</div>
            <div className="slot-frame">{renderPanel(layout.slots.railBottom)}</div>
          </div>
          <div className="dashboard-stage">
            <div className="slot-frame slot-frame--hero">{renderPanel(layout.slots.hero)}</div>
            <div className="slot-frame">{renderPanel(layout.slots.support)}</div>
            <div className="slot-frame slot-frame--board">{renderPanel(layout.slots.board)}</div>
            <div className="slot-frame slot-frame--detail">{renderPanel(layout.slots.detail)}</div>
          </div>
        </div>
      </section>
    );

    if (activeWorkspace === "navigation") {
      return (
        <section className="workspace-card">
          <div className="workspace-card__header">
            <div>
              <div className="eyebrow">Driving mode</div>
              <h2>Route HUD</h2>
              <p>Keep the next move, arrival ring, and latest target changes visible while you are rolling.</p>
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
              <div className="eyebrow">Fast triage</div>
              <h2>Recovery alerts</h2>
              <p>Filter to the live target that matters and push the next field action without extra clicks.</p>
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
              <div className="eyebrow">Lookup and review</div>
              <h2>Detection search</h2>
              <p>Search full or partial plates, tighten with field filters, and jump straight into detailed review.</p>
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
                    <div className="live-activity__header">
                      <strong>{searchExecuted ? `${searchTotalResults} result${searchTotalResults === 1 ? "" : "s"}` : "Awaiting search"}</strong>
                      <span>
                        {searchLoading
                          ? "Querying the live API..."
                          : searchExecuted
                            ? "Select a result to open detailed review."
                            : "Search by full or partial plate and refine by field filters."}
                      </span>
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
              <div className="eyebrow">Visual confirmation</div>
              <h2>Camera views</h2>
              <p>Keep the truck camera bank clean, large, and easy to read at a glance from the driver seat.</p>
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
              <div className="eyebrow">Local laptop profile</div>
              <h2>Field settings</h2>
              <p>
                Saved in this browser so each truck can tune the cab layout and alert behavior to the agent using it.
              </p>
            </div>
            <div className="workspace-card__actions">
              <button className="button" type="button" onClick={() => setLayout(cloneLayout(dashboardPresets.route))}>
                Restore dashboard
              </button>
              <button className="button" type="button" onClick={() => setFieldSettings({ ...defaultFieldSettings })}>
                Reset field settings
              </button>
            </div>
          </div>
          <div className="settings-grid">
            <PanelFrame panelId="routePlanner" titleOverride="Dashboard Layout">
              <div className="settings-section">
                <div className="preset-list">
                  {(["route", "recovery", "lotScan"] as LayoutPresetId[]).map((presetId) => (
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
                    </select>
                  </label>
                </div>
              </div>
            </PanelFrame>
            <PanelFrame panelId="statusStack" titleOverride="Alert and Navigation">
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
            <PanelFrame panelId="selectedAlert" titleOverride="Detection and Workflow">
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
            <PanelFrame panelId="dispatchBoard" titleOverride="Operator Session">
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
                          {operatorDisplayName(session)} · {session.selected_detection_id ?? session.selected_alert_id ?? "No active target"}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </PanelFrame>
            <PanelFrame panelId="hotlistFeed" titleOverride="Hotlist Manager">
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
          <div className="brand-eyebrow">Seen-It-First</div>
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
        <GlanceTile label="Primary target" value={selectedAlert.plate} sublabel={selectedAlert.vehicle} />
        <GlanceTile label="Distance" value={currentDistanceLabel} sublabel={activeDestination} />
        <GlanceTile label="Scan mode" value={navigationModeLabel} sublabel={addressDetectionEnabled ? "Address alerts armed" : "Address alerts off"} />
        <GlanceTile label="Cameras" value={`${onlineCameraCount}/4`} sublabel={`${selectedCamera.label} selected`} />
        <GlanceTile label="Alert policy" value="Hotlist always on" sublabel={generalPopupsLive ? "General popups live" : addressDetectionEnabled ? "Suppressed until arrival" : "Disabled by operator"} />
      </section>

      <section className="mode-banner">
        <span className={`badge ${liveDataSource === "live" ? "badge--good" : "badge--outlined"}`}>
          {liveDataSource === "live" ? "Live API connected" : liveDataSource === "fallback" ? "Demo fallback" : "Demo data only"}
        </span>
        <span>Profile: {layout.profile}</span>
        <span>API health: {liveHealthState}</span>
        <span>Operator: {operatorDisplayName(currentOperator)}</span>
        <span>Roles: {currentOperator.roles.map((role) => operatorRoleLabel(role)).join(", ") || "Local"}</span>
        <span>
          Active alerts: {activeAlertCount} / Active hotlists: {liveOverview ? activeHotlistCount : "demo"}
        </span>
        <span>
          Follow-ups: {openFollowUpCount} / Dispatch: {activeAssignmentCount} / Crew: {activeSessionCount}
        </span>
        <span>
          {generalPopupsLive
            ? "Inside the destination radius. Address-based detections are surfacing as popup alerts."
            : !addressDetectionEnabled
              ? "Address-based popup detection is disabled by the operator. Hotlist matches remain unsuppressed."
              : "Outside the destination radius. General detections stay in the background until the operator enters the arrival ring."}
        </span>
        <span>Hotlist matches remain high-priority and never suppressed.</span>
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
