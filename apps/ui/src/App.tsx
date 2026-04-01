import { startTransition, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type ReactElement } from "react";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { cameraFeeds, defaultFieldSettings } from "./demo-data";
import {
  fetchAuditEvents,
  createDispatchAssignment,
  createFollowUp,
  createHotlist,
  createReview,
  deleteHotlist,
  fetchDashboardOverview,
  fetchDetectionFrameObjectUrl,
  fetchDetectionPlateCropObjectUrl,
  fetchHotlists,
  fetchReviews,
  searchAlerts,
  searchDetections,
  sendOperatorSessionHeartbeat,
  setApiClientConfig,
  updateAlert,
  updateDispatchAssignment,
  updateFollowUp,
  updateHotlist,
  type AlertSearchFilters,
  type ApiAuditEvent,
  type DispatchAssignmentPriority,
  type DispatchAssignmentRecord,
  type DispatchAssignmentStatus,
  type DashboardAlert,
  type DashboardAlertStatus,
  type DashboardDetection,
  type DashboardHotlist,
  type DashboardOverviewResponse,
  type DashboardPopupActivityEvent,
  type DetectionSearchFilters,
  type FollowUpPriority,
  type FollowUpRecord,
  type FollowUpStatus,
  type OperatorPrincipal,
  type OperatorSessionRecord,
  type PlateCandidate,
  type ReviewAction,
  type ReviewRecord,
} from "./live-api";

type AppScreen = "console" | "search" | "hotlists" | "settings";
type StageView = "camera" | "map";
type ConsoleLayoutMode = "overview" | "focus";
type SearchMode = "plate" | "camera" | "vehicle" | "alert";
type DataSource = "demo" | "live" | "fallback";
type AlertPersistence = "until-dismissed" | "15 sec" | "60 sec";
type HotlistsWorkspaceTab = "accounts" | "alerts" | "recognition";
type SettingsSection = "workspace" | "alerts" | "cameras" | "map" | "system";

interface UiSettings {
  autoArrivalScan: boolean;
  arrivalScanEnabled: boolean;
  arrivalRadiusFeet: number;
  duplicateSuppressionSeconds: number;
  minConfidence: number;
  hotlistAlerts: boolean;
  soundEnabled: boolean;
  vibrationEnabled: boolean;
  alertVolume: number;
  alertPersistence: AlertPersistence;
  nightMode: boolean;
  irControl: boolean;
  exposureLock: boolean;
  resolution: string;
  streamQuality: string;
  overlayLabels: boolean;
  autoDeleteTempCaptures: boolean;
  mapMode: string;
  autoCenterVehicle: boolean;
  showRadiusRing: boolean;
  navProvider: string;
  showTraffic: boolean;
}

interface ConsoleDetectionRow {
  id: string;
  detectionId?: string;
  alertId?: string;
  plate1: string;
  plate2: string;
  plateCandidates: PlateCandidate[];
  state: string;
  camera: string;
  cameraId: string;
  conf: number;
  time: string;
  timestampUtc: string;
  hotlist: boolean;
  vehicle: string;
  gps: string;
  direction: string;
  lane: string;
  lat: number;
  lng: number;
  source: string;
  frameNumber?: number;
  syncStatus?: string;
  alertStatus?: DashboardAlertStatus;
  alertMatchType?: DashboardAlert["match_type"];
  alertNotes?: string;
}

interface CameraUiFeed {
  id: string;
  label: string;
  shortLabel: string;
  status: "Online" | "Offline";
  fps: number | null;
}

interface HotlistAlertItem {
  alert: DashboardAlert;
  row: ConsoleDetectionRow | null;
}

interface RecognitionActivityItem {
  event: DashboardPopupActivityEvent;
  row: ConsoleDetectionRow | null;
}

interface HotlistDraft {
  plateText: string;
  label: string;
  notes: string;
  active: boolean;
}

interface FollowUpDraftState {
  priority: FollowUpPriority;
  status: FollowUpStatus;
  assignedOperatorId: string;
  summary: string;
  notes: string;
  dueAtLocal: string;
}

interface AssignmentDraftState {
  priority: DispatchAssignmentPriority;
  status: DispatchAssignmentStatus;
  assignedOperatorId: string;
  assignedUnitLabel: string;
  destinationLabel: string;
  summary: string;
  notes: string;
}

interface FollowUpSaveRequest {
  alertId: string | null;
  detectionId: string;
  existing: FollowUpRecord | null;
  plateText: string;
  draft: FollowUpDraftState;
}

interface AssignmentSaveRequest {
  alertId: string | null;
  detectionId: string;
  existing: DispatchAssignmentRecord | null;
  plateText: string;
  draft: AssignmentDraftState;
}

interface PlateGroup {
  plate: string;
  rows: ConsoleDetectionRow[];
}

const uiSettingsStorageKey = "reposcan.ui.desktop-settings.v1";
const apiKeyStorageKey = "reposcan.ui.api-key.v2";
const targetAddressStorageKey = "reposcan.ui.target-address.v1";
const sessionIdStorageKey = "reposcan.ui.session-id.v1";

function loadOrCreateSessionId(): string {
  if (typeof window === "undefined") {
    return `sess_${Math.random().toString(16).slice(2, 14)}`;
  }
  try {
    const stored = window.localStorage.getItem(sessionIdStorageKey);
    if (stored) {
      return stored;
    }
  } catch {
    // ignore
  }
  const created = `sess_${Math.random().toString(16).slice(2, 14)}`;
  try {
    window.localStorage.setItem(sessionIdStorageKey, created);
  } catch {
    // ignore
  }
  return created;
}

const operatorSessionId = loadOrCreateSessionId();

const targetRoute = {
  address: "4128 W Fulton St, Chicago, IL",
  lat: 41.8862,
  lng: -87.7282,
};

const routeStart = {
  lat: 41.8746,
  lng: -87.7528,
};

const defaultUiSettings: UiSettings = {
  autoArrivalScan: true,
  arrivalScanEnabled: true,
  arrivalRadiusFeet: defaultFieldSettings.arrivalTriggerDistance,
  duplicateSuppressionSeconds: 90,
  minConfidence: Math.round(defaultFieldSettings.ocrConfidenceThreshold * 100),
  hotlistAlerts: true,
  soundEnabled: !defaultFieldSettings.silentShiftMode,
  vibrationEnabled: true,
  alertVolume: 82,
  alertPersistence: "until-dismissed",
  nightMode: true,
  irControl: true,
  exposureLock: false,
  resolution: "1920x1080",
  streamQuality: "High",
  overlayLabels: true,
  autoDeleteTempCaptures: false,
  mapMode: "Dark route",
  autoCenterVehicle: true,
  showRadiusRing: true,
  navProvider: "Internal",
  showTraffic: defaultFieldSettings.routeTrafficOverlay,
};

const seedHotlists: DashboardHotlist[] = [
  {
    entry_id: "hl_demo_9kpn665",
    plate_text: "9KPN665",
    label: "Fulton tow-ready",
    notes: "Confirm the rear plate before engaging. Driver reported away from the vehicle.",
    active: true,
    created_at_utc: "2026-03-27T21:34:00Z",
    updated_at_utc: "2026-03-27T22:10:00Z",
  },
  {
    entry_id: "hl_demo_8abc123",
    plate_text: "8ABC123",
    label: "High-priority recovery",
    notes: "Escalate immediately if seen on any inbound approach camera.",
    active: true,
    created_at_utc: "2026-03-27T20:20:00Z",
    updated_at_utc: "2026-03-27T22:14:08Z",
  },
  {
    entry_id: "hl_demo_6ucj466",
    plate_text: "6UCJ466",
    label: "Manual review watch",
    notes: "OCR confusion with 6UCI466 has been seen twice this shift.",
    active: false,
    created_at_utc: "2026-03-27T19:48:00Z",
    updated_at_utc: "2026-03-27T21:56:00Z",
  },
];

function loadStoredString(key: string, fallback = ""): string {
  if (typeof window === "undefined") {
    return fallback;
  }

  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function loadStoredSettings(): UiSettings {
  if (typeof window === "undefined") {
    return defaultUiSettings;
  }

  try {
    const raw = window.localStorage.getItem(uiSettingsStorageKey);
    if (!raw) {
      return defaultUiSettings;
    }
    const parsed = JSON.parse(raw) as Partial<UiSettings>;
    return {
      ...defaultUiSettings,
      ...parsed,
    };
  } catch {
    return defaultUiSettings;
  }
}

function formatClock(timestampUtc: string): string {
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

function formatDateTime(timestampUtc: string): string {
  const parsed = new Date(timestampUtc);
  if (Number.isNaN(parsed.valueOf())) {
    return timestampUtc;
  }

  return parsed.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatGpsValue(latitude: number | null | undefined, longitude: number | null | undefined): string {
  if (typeof latitude !== "number" || typeof longitude !== "number") {
    return "GPS unavailable";
  }
  return `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
}

function confidencePercent(value: number): number {
  return value > 1 ? Math.round(value) : Math.round(value * 100);
}

function confidenceLabel(value: number): string {
  return `${confidencePercent(value)}%`;
}

function formatDistance(feet: number): string {
  if (feet >= 5280) {
    return `${(feet / 5280).toFixed(1)} mi`;
  }
  return `${feet} ft`;
}

function formatEta(feet: number, active: boolean): string {
  if (!active) {
    return "Standby";
  }
  if (feet <= 150) {
    return "<1 min";
  }
  return `${Math.max(1, Math.round(feet / 850))} min`;
}

function normalizePlate(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, "").toUpperCase();
}

function matchesHotlist(plate1: string, plate2: string, hotlists: DashboardHotlist[]): boolean {
  const candidates = new Set([normalizePlate(plate1), normalizePlate(plate2)]);
  return hotlists.some((entry) => entry.active && candidates.has(normalizePlate(entry.plate_text)));
}

function hotlistEntryForRow(row: ConsoleDetectionRow, hotlists: DashboardHotlist[]): DashboardHotlist | null {
  const candidates = new Set([normalizePlate(row.plate1), normalizePlate(row.plate2)]);
  return hotlists.find((entry) => entry.active && candidates.has(normalizePlate(entry.plate_text))) ?? null;
}

function hotlistLabelForRow(row: ConsoleDetectionRow, hotlists: DashboardHotlist[]): string | null {
  return hotlistEntryForRow(row, hotlists)?.label ?? null;
}

const cameraDirectionTokens = new Set(["north", "south", "east", "west", "front", "rear", "left", "right"]);
const cameraAcronyms = new Map([
  ["lpr", "LPR"],
  ["usb", "USB"],
  ["rtsp", "RTSP"],
]);

function formatCameraToken(token: string): string {
  const normalized = token.toLowerCase();
  if (cameraAcronyms.has(normalized)) {
    return cameraAcronyms.get(normalized) ?? token;
  }
  if (/^\d+$/.test(token)) {
    return token;
  }
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function parseCameraId(cameraId: string): { locationLabel: string; indexLabel: string | null } {
  const rawTokens = cameraId
    .replace(/^cam[_-]?/i, "")
    .split(/[_-]+/)
    .filter(Boolean);

  const tokens = [...rawTokens];
  const lastToken = tokens.at(-1);
  const indexLabel = lastToken && /^\d+$/.test(lastToken) ? tokens.pop() ?? null : null;
  const directionIndex = tokens.findIndex((token) => cameraDirectionTokens.has(token.toLowerCase()));

  if (directionIndex > 0) {
    const [directionToken] = tokens.splice(directionIndex, 1);
    tokens.unshift(directionToken);
  }

  const locationLabel = tokens.map((token) => formatCameraToken(token)).join(" ").trim();
  return {
    locationLabel: locationLabel || cameraId,
    indexLabel,
  };
}

function humanizeCameraId(cameraId: string, variant: "short" | "full" = "short"): string {
  const parsed = parseCameraId(cameraId);
  if (variant === "full") {
    return parsed.indexLabel ? `${parsed.locationLabel} Camera ${parsed.indexLabel}` : `${parsed.locationLabel} Camera`;
  }
  return parsed.indexLabel ? `${parsed.locationLabel} ${parsed.indexLabel}` : parsed.locationLabel;
}

function buildCameraShortLabel(cameraId: string): string {
  const index = cameraFeeds.findIndex((feed) => feed.id === cameraId);
  if (index >= 0) {
    return `Cam ${index + 1}`;
  }
  return humanizeCameraId(cameraId, "short");
}

function buildCameraDisplayName(cameraId: string): string {
  const camera = cameraFeeds.find((feed) => feed.id === cameraId);
  return camera?.label ?? humanizeCameraId(cameraId, "full");
}

function titleCase(value: string | null | undefined): string {
  if (!value) {
    return "";
  }

  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function fallbackPoint(index: number): { lat: number; lng: number } {
  const latOffset = ((index % 4) - 1.5) * 0.0016;
  const lngOffset = ((index % 5) - 2) * 0.0012;
  return {
    lat: targetRoute.lat + latOffset,
    lng: targetRoute.lng + lngOffset,
  };
}

function buildVehicleLabel(record: DashboardDetection): string {
  const parts = [
    record.optional_vehicle_year,
    titleCase(record.vehicle_color),
    titleCase(record.vehicle_make),
    titleCase(record.vehicle_model),
  ].filter(Boolean);
  return parts.join(" ") || "Unclassified vehicle";
}

function buildCameraUiFeeds(rows: ConsoleDetectionRow[], source: DataSource): CameraUiFeed[] {
  if (source === "live") {
    const liveCameraIds = [...new Set(rows.map((row) => row.cameraId))];
    return liveCameraIds.map((cameraId) => {
      const demoFeed = cameraFeeds.find((feed) => feed.id === cameraId);
      return {
        id: cameraId,
        label: buildCameraDisplayName(cameraId),
        shortLabel: humanizeCameraId(cameraId, "short"),
        status: "Online",
        fps: demoFeed?.fps ?? null,
      };
    });
  }

  return cameraFeeds.map((feed, index) => ({
    id: feed.id,
    label: feed.label,
    shortLabel: `Cam ${index + 1}`,
    status: feed.status,
    fps: feed.fps,
  }));
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function alertStatusTone(status: DashboardAlertStatus): "critical" | "warn" | "muted" {
  if (status === "active") {
    return "critical";
  }
  if (status === "acknowledged") {
    return "warn";
  }
  return "muted";
}

function alertStatusLabel(status: DashboardAlertStatus): string {
  if (status === "acknowledged") {
    return "Acknowledged";
  }
  if (status === "dismissed") {
    return "Dismissed";
  }
  return "Active";
}

function alertResponseGuidance(status: DashboardAlertStatus): string {
  if (status === "active") {
    return "Route to the vehicle immediately. Visually confirm the tag and VIN before engaging. Keep the account armed until confirmed.";
  }
  if (status === "acknowledged") {
    return "Vehicle under active field review. Maintain visual contact and update dispatch when ready to hook or when the debtor moves.";
  }
  return "Case dismissed. Reopen only if the vehicle needs active repo attention again.";
}

function followUpStatusTone(status: FollowUpStatus): "critical" | "warn" | "success" {
  if (status === "open") {
    return "critical";
  }
  if (status === "monitoring") {
    return "warn";
  }
  return "success";
}

function dispatchStatusTone(status: DispatchAssignmentStatus): "critical" | "warn" | "success" | "muted" {
  if (status === "queued" || status === "assigned") {
    return "warn";
  }
  if (status === "en_route" || status === "onsite") {
    return "critical";
  }
  if (status === "completed") {
    return "success";
  }
  return "muted";
}

function buildRecognitionVehicleLabel(event: DashboardPopupActivityEvent): string {
  const parts = [event.optional_vehicle_year, titleCase(event.vehicle_color), titleCase(event.vehicle_make), titleCase(event.vehicle_model)].filter(Boolean);
  return parts.join(" ") || event.hotlist_label || "Unclassified vehicle";
}

function buildBlankHotlistDraft(seedPlate = ""): HotlistDraft {
  return {
    plateText: normalizePlate(seedPlate),
    label: "",
    notes: "",
    active: true,
  };
}

function hotlistDraftFromEntry(entry: DashboardHotlist): HotlistDraft {
  return {
    plateText: entry.plate_text,
    label: entry.label ?? "",
    notes: entry.notes ?? "",
    active: entry.active,
  };
}

function toUtcIso(value: string): string | undefined {
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

function toLocalDateTimeInput(value: string | null | undefined): string {
  if (!value) {
    return "";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return "";
  }

  const offset = parsed.getTimezoneOffset();
  const local = new Date(parsed.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

function buildFollowUpDraft(record: FollowUpRecord | null | undefined): FollowUpDraftState {
  return {
    priority: record?.priority ?? "priority",
    status: record?.status ?? "open",
    assignedOperatorId: record?.assigned_operator_id ?? "",
    summary: record?.summary ?? "",
    notes: record?.notes ?? "",
    dueAtLocal: toLocalDateTimeInput(record?.due_at_utc),
  };
}

function buildAssignmentDraft(record: DispatchAssignmentRecord | null | undefined, destinationFallback = ""): AssignmentDraftState {
  return {
    priority: record?.priority ?? "priority",
    status: record?.status ?? "queued",
    assignedOperatorId: record?.assigned_operator_id ?? "",
    assignedUnitLabel: record?.assigned_unit_label ?? "",
    destinationLabel: record?.destination_label ?? destinationFallback,
    summary: record?.summary ?? "",
    notes: record?.notes ?? "",
  };
}

function sortByUpdatedDesc<T extends { updated_at_utc: string }>(records: T[]): T[] {
  return [...records].sort((left, right) => right.updated_at_utc.localeCompare(left.updated_at_utc));
}

function matchingFollowUpsForRow(row: ConsoleDetectionRow, followUps: FollowUpRecord[]): FollowUpRecord[] {
  return sortByUpdatedDesc(
    followUps.filter(
      (item) =>
        item.detection_id === row.detectionId ||
        (item.plate_text ? normalizePlate(item.plate_text) === normalizePlate(row.plate1) : false),
    ),
  );
}

function matchingAssignmentsForRow(row: ConsoleDetectionRow, assignments: DispatchAssignmentRecord[]): DispatchAssignmentRecord[] {
  return sortByUpdatedDesc(
    assignments.filter(
      (item) =>
        item.detection_id === row.detectionId ||
        (item.plate_text ? normalizePlate(item.plate_text) === normalizePlate(row.plate1) : false),
    ),
  );
}

function buildSeedRows(hotlists: DashboardHotlist[]): ConsoleDetectionRow[] {
  const seeds = [
    {
      id: "seed-9kpn665",
      plate1: "9KPN665",
      plate2: "PN665",
      state: "CA",
      cameraId: "cam-rear-3",
      conf: 95,
      timestampUtc: "2026-03-27T22:14:08Z",
      vehicle: "2021 Toyota Camry",
      gps: "41.88624, -87.72819",
      direction: "Northbound",
      lane: "Right lane",
      lat: 41.88624,
      lng: -87.72819,
      source: "Fulton curbside",
      frameNumber: 21844,
      syncStatus: "local",
    },
    {
      id: "seed-9aja734",
      plate1: "9AJA734",
      plate2: "9AIA734",
      state: "CA",
      cameraId: "cam-side-2",
      conf: 88,
      timestampUtc: "2026-03-27T22:12:41Z",
      vehicle: "2019 Honda Civic",
      gps: "41.88584, -87.73094",
      direction: "Eastbound",
      lane: "Center lane",
      lat: 41.88584,
      lng: -87.73094,
      source: "West alley entrance",
      frameNumber: 21731,
      syncStatus: "local",
    },
    {
      id: "seed-5hcg067",
      plate1: "5HCG067",
      plate2: "5MCG067",
      state: "CA",
      cameraId: "cam-side-2",
      conf: 82,
      timestampUtc: "2026-03-27T22:11:16Z",
      vehicle: "2017 Ford Fusion",
      gps: "41.88498, -87.73182",
      direction: "Southbound",
      lane: "Curb lane",
      lat: 41.88498,
      lng: -87.73182,
      source: "Plymouth cross street",
      frameNumber: 21610,
      syncStatus: "local",
    },
    {
      id: "seed-6ucj466",
      plate1: "6UCJ466",
      plate2: "6UCI466",
      state: "CA",
      cameraId: "cam-rear-3",
      conf: 91,
      timestampUtc: "2026-03-27T22:09:58Z",
      vehicle: "2020 Nissan Altima",
      gps: "41.88702, -87.72755",
      direction: "Westbound",
      lane: "Driveway exit",
      lat: 41.88702,
      lng: -87.72755,
      source: "North lot exit",
      frameNumber: 21498,
      syncStatus: "local",
    },
    {
      id: "seed-8abc123",
      plate1: "8ABC123",
      plate2: "8A8C123",
      state: "IL",
      cameraId: "cam-front-1",
      conf: 97,
      timestampUtc: "2026-03-27T22:07:44Z",
      vehicle: "2022 Kia Sportage",
      gps: "41.88366, -87.73018",
      direction: "Northbound",
      lane: "Approach lane",
      lat: 41.88366,
      lng: -87.73018,
      source: "South approach",
      frameNumber: 21376,
      syncStatus: "local",
    },
    {
      id: "seed-7trm221",
      plate1: "7TRM221",
      plate2: "7TRN221",
      state: "IN",
      cameraId: "cam-front-1",
      conf: 79,
      timestampUtc: "2026-03-27T22:05:32Z",
      vehicle: "2018 Chevy Malibu",
      gps: "41.88291, -87.73210",
      direction: "Stopped",
      lane: "Loading lane",
      lat: 41.88291,
      lng: -87.73210,
      source: "Warehouse frontage",
      frameNumber: 21241,
      syncStatus: "local",
    },
  ];

  return seeds.map((row) => ({
    ...row,
    camera: buildCameraShortLabel(row.cameraId),
    time: formatClock(row.timestampUtc),
    hotlist: matchesHotlist(row.plate1, row.plate2, hotlists),
    plateCandidates: [
      { text: row.plate1, confidence: row.conf / 100 },
      { text: row.plate2, confidence: Math.max(0.38, row.conf / 100 - 0.18) },
    ],
  }));
}

function mapDetectionToRow(record: DashboardDetection, index: number, hotlists: DashboardHotlist[]): ConsoleDetectionRow {
  const primaryPlate = record.plate_text ?? record.plate_candidates[0]?.text ?? `UNREAD-${index + 1}`;
  const alternatePlate = record.plate_candidates.find((candidate) => candidate.text !== primaryPlate)?.text ?? "--";
  const fallback = fallbackPoint(index);
  const confidence = confidencePercent(record.plate_confidence ?? record.plate_candidates[0]?.confidence ?? 0.78);
  const latitude = record.gps_latitude ?? fallback.lat;
  const longitude = record.gps_longitude ?? fallback.lng;
  const lane = ["Left lane", "Center lane", "Right lane", "Shoulder"][index % 4];
  const direction = ["Northbound", "Eastbound", "Southbound", "Westbound"][index % 4];

  return {
    id: `live-${record.detection_id}`,
    detectionId: record.detection_id,
    plate1: normalizePlate(primaryPlate) || "UNKNOWN",
    plate2: normalizePlate(alternatePlate) || "--",
    plateCandidates: record.plate_candidates.length > 0 ? record.plate_candidates : [{ text: normalizePlate(primaryPlate) || "UNKNOWN", confidence: record.plate_confidence ?? 0 }],
    state: "--",
    camera: buildCameraShortLabel(record.camera_id),
    cameraId: record.camera_id,
    conf: confidence,
    time: formatClock(record.timestamp_utc),
    timestampUtc: record.timestamp_utc,
    hotlist: matchesHotlist(primaryPlate, alternatePlate, hotlists),
    vehicle: buildVehicleLabel(record),
    gps: `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`,
    direction,
    lane,
    lat: latitude,
    lng: longitude,
    source: buildCameraDisplayName(record.camera_id),
    frameNumber: record.frame_number,
    syncStatus: record.sync_status,
  };
}

function mapAlertToRow(
  alert: DashboardAlert,
  detection: DashboardDetection | undefined,
  index: number,
  hotlists: DashboardHotlist[],
): ConsoleDetectionRow {
  if (detection) {
    const baseRow = mapDetectionToRow(detection, index, hotlists);
    return {
      ...baseRow,
      id: `alert-${alert.alert_id}`,
      alertId: alert.alert_id,
      alertStatus: alert.status,
      alertMatchType: alert.match_type,
      alertNotes: [alert.notes, alert.response_notes].filter(Boolean).join(" · ") || undefined,
    };
  }

  const fallback = fallbackPoint(index);
  const latitude = alert.gps_latitude ?? fallback.lat;
  const longitude = alert.gps_longitude ?? fallback.lng;

  return {
    id: `alert-${alert.alert_id}`,
    detectionId: alert.detection_id,
    alertId: alert.alert_id,
    plate1: normalizePlate(alert.matched_plate_text) || "UNKNOWN",
    plate2: "--",
    plateCandidates: [{ text: normalizePlate(alert.matched_plate_text) || "UNKNOWN", confidence: alert.match_confidence }],
    state: "--",
    camera: buildCameraShortLabel(alert.camera_id),
    cameraId: alert.camera_id,
    conf: confidencePercent(alert.match_confidence),
    time: formatClock(alert.updated_at_utc ?? alert.timestamp_utc),
    timestampUtc: alert.updated_at_utc ?? alert.timestamp_utc,
    hotlist: true,
    vehicle: alert.hotlist_label ?? "Recovery case",
    gps: `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`,
    direction: ["Northbound", "Eastbound", "Southbound", "Westbound"][index % 4],
    lane: ["Left lane", "Center lane", "Right lane", "Shoulder"][index % 4],
    lat: latitude,
    lng: longitude,
    source: buildCameraDisplayName(alert.camera_id),
    syncStatus: "local",
    alertStatus: alert.status,
    alertMatchType: alert.match_type,
    alertNotes: [alert.notes, alert.response_notes].filter(Boolean).join(" · ") || undefined,
  };
}

function buildPlateGroups(rows: ConsoleDetectionRow[]): PlateGroup[] {
  const groups = new Map<string, ConsoleDetectionRow[]>();
  for (const row of rows) {
    const key = normalizePlate(row.plate1) || row.id;
    const existing = groups.get(key);
    if (existing) {
      existing.push(row);
    } else {
      groups.set(key, [row]);
    }
  }

  return [...groups.entries()]
    .map(([plate, groupRows]) => ({
      plate,
      rows: [...groupRows].sort((left, right) => right.timestampUtc.localeCompare(left.timestampUtc)),
    }))
    .sort((left, right) => {
      const leftLead = left.rows[0];
      const rightLead = right.rows[0];
      if (leftLead.hotlist !== rightLead.hotlist) {
        return leftLead.hotlist ? -1 : 1;
      }
      return rightLead.timestampUtc.localeCompare(leftLead.timestampUtc);
    });
}

function rowMatchesQuery(row: ConsoleDetectionRow, mode: SearchMode, query: string): boolean {
  const normalizedQuery = query.trim().toUpperCase();
  if (!normalizedQuery) {
    return true;
  }

  if (mode === "plate") {
    return normalizePlate(row.plate1).includes(normalizedQuery) || normalizePlate(row.plate2).includes(normalizedQuery);
  }
  if (mode === "camera") {
    return row.camera.toUpperCase().includes(normalizedQuery) || row.source.toUpperCase().includes(normalizedQuery);
  }
  if (mode === "vehicle") {
    return row.vehicle.toUpperCase().includes(normalizedQuery);
  }
  if (mode === "alert") {
    return (
      normalizePlate(row.plate1).includes(normalizedQuery) ||
      normalizePlate(row.plate2).includes(normalizedQuery) ||
      row.source.toUpperCase().includes(normalizedQuery) ||
      (row.alertNotes ?? "").toUpperCase().includes(normalizedQuery) ||
      (row.alertMatchType ?? "").toUpperCase().includes(normalizedQuery)
    );
  }
  return row.timestampUtc.includes(normalizedQuery) || row.time.includes(normalizedQuery);
}

function filterRowsLocally(options: {
  alerts: DashboardAlert[];
  rows: ConsoleDetectionRow[];
  mode: SearchMode;
  query: string;
  fromUtc?: string;
  toUtc?: string;
  vehicleColor: string;
  vehicleMake: string;
  vehicleModel: string;
  vehicleYear: string;
  alertStatus: DashboardAlertStatus | "";
  minLatitude: string;
  maxLatitude: string;
  minLongitude: string;
  maxLongitude: string;
  hotlistOnly: boolean;
  highConfidenceOnly: boolean;
  currentCameraOnly: boolean;
  currentShiftOnly: boolean;
  currentCameraId: string;
}): ConsoleDetectionRow[] {
  const shiftCutoff = new Date(Date.now() - 8 * 60 * 60 * 1000).valueOf();
  const fromValue = options.fromUtc ? new Date(options.fromUtc).valueOf() : null;
  const toValue = options.toUtc ? new Date(options.toUtc).valueOf() : null;
  const minLatitude = options.minLatitude.trim() ? Number(options.minLatitude) : null;
  const maxLatitude = options.maxLatitude.trim() ? Number(options.maxLatitude) : null;
  const minLongitude = options.minLongitude.trim() ? Number(options.minLongitude) : null;
  const maxLongitude = options.maxLongitude.trim() ? Number(options.maxLongitude) : null;
  const colorQuery = options.vehicleColor.trim().toUpperCase();
  const makeQuery = options.vehicleMake.trim().toUpperCase();
  const modelQuery = options.vehicleModel.trim().toUpperCase();
  const yearQuery = options.vehicleYear.trim().toUpperCase();

  return options.rows.filter((row) => {
    if (!rowMatchesQuery(row, options.mode, options.query)) {
      return false;
    }
    if (options.hotlistOnly && !row.hotlist) {
      return false;
    }
    if (options.highConfidenceOnly && row.conf < 90) {
      return false;
    }
    if (colorQuery && !row.vehicle.toUpperCase().includes(colorQuery)) {
      return false;
    }
    if (makeQuery && !row.vehicle.toUpperCase().includes(makeQuery)) {
      return false;
    }
    if (modelQuery && !row.vehicle.toUpperCase().includes(modelQuery)) {
      return false;
    }
    if (yearQuery && !row.vehicle.toUpperCase().includes(yearQuery)) {
      return false;
    }
    if (options.currentCameraOnly && row.cameraId !== options.currentCameraId) {
      return false;
    }
    if (options.alertStatus) {
      const matchingAlert = options.alerts.find(
        (alert) =>
          alert.detection_id === row.detectionId ||
          normalizePlate(alert.matched_plate_text) === normalizePlate(row.plate1),
      );
      if (!matchingAlert || matchingAlert.status !== options.alertStatus) {
        return false;
      }
    }
    if (minLatitude !== null && row.lat < minLatitude) {
      return false;
    }
    if (maxLatitude !== null && row.lat > maxLatitude) {
      return false;
    }
    if (minLongitude !== null && row.lng < minLongitude) {
      return false;
    }
    if (maxLongitude !== null && row.lng > maxLongitude) {
      return false;
    }

    const timestamp = new Date(row.timestampUtc).valueOf();
    if (options.currentShiftOnly && timestamp < shiftCutoff) {
      return false;
    }
    if (fromValue !== null && timestamp < fromValue) {
      return false;
    }
    if (toValue !== null && timestamp > toValue) {
      return false;
    }
    return true;
  });
}

function statusTone(online: boolean): "good" | "off" {
  return online ? "good" : "off";
}

function confidenceTone(value: number): "high" | "medium" | "low" {
  if (value >= 90) {
    return "high";
  }
  if (value >= 82) {
    return "medium";
  }
  return "low";
}

function readStatusTone(row: ConsoleDetectionRow): "active" | "acknowledged" | "dismissed" | "recovery" | "observed" {
  if (row.alertStatus) {
    return row.alertStatus;
  }
  if (row.hotlist) {
    return "recovery";
  }
  return "observed";
}

function readStatusLabel(row: ConsoleDetectionRow): string {
  if (row.alertStatus) {
    return alertStatusLabel(row.alertStatus);
  }
  if (row.hotlist) {
    return "Recovery";
  }
  return "Observed";
}

function interpolatePosition(progress: number): { lat: number; lng: number } {
  return {
    lat: routeStart.lat + (targetRoute.lat - routeStart.lat) * progress,
    lng: routeStart.lng + (targetRoute.lng - routeStart.lng) * progress,
  };
}

function buildDetectionBoxPosition(cameraId: string, compact = false): CSSProperties {
  const positions = compact
    ? {
        "cam-front-1": { left: "18%", top: "42%" },
        "cam-side-2": { left: "50%", top: "34%" },
        "cam-rear-3": { left: "31%", top: "37%" },
        "cam-roof-4": { left: "44%", top: "29%" },
      }
    : {
        "cam-front-1": { left: "20%", top: "35%" },
        "cam-side-2": { left: "54%", top: "32%" },
        "cam-rear-3": { left: "36%", top: "38%" },
        "cam-roof-4": { left: "48%", top: "28%" },
      };

  const fallback = compact ? { left: "30%", top: "36%" } : { left: "36%", top: "38%" };
  const resolved = positions[cameraId as keyof typeof positions] ?? fallback;
  return {
    "--box-left": resolved.left,
    "--box-top": resolved.top,
  } as CSSProperties;
}

function buildRoutePath(position: { lat: number; lng: number }): [number, number][] {
  const mid1: [number, number] = [
    position.lat + (targetRoute.lat - position.lat) * 0.4 + 0.0032,
    position.lng + (targetRoute.lng - position.lng) * 0.2,
  ];
  const mid2: [number, number] = [
    position.lat + (targetRoute.lat - position.lat) * 0.72 - 0.0016,
    position.lng + (targetRoute.lng - position.lng) * 0.68 + 0.0024,
  ];
  return [
    [position.lat, position.lng],
    mid1,
    mid2,
    [targetRoute.lat, targetRoute.lng],
  ];
}

function makeDotIcon(color: string, size: number): L.DivIcon {
  return L.divIcon({
    className: "map-dot-icon",
    html: `<span class="map-dot" style="width:${size}px;height:${size}px;background:${color}"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function makePlateIcon(plate: string, critical: boolean): L.DivIcon {
  return L.divIcon({
    className: "map-plate-icon",
    html: `<span class="plate-marker ${critical ? "critical" : ""}">${plate}</span>`,
    iconSize: [74, 24],
    iconAnchor: [37, 12],
  });
}

const unitIcon = makeDotIcon("#38E8FF", 14);
const targetIcon = makeDotIcon("#F0F4F8", 12);

function OpsMap(props: {
  unitPosition: { lat: number; lng: number };
  routePath: [number, number][];
  rows: ConsoleDetectionRow[];
  radiusFeet: number;
  showRadiusRing: boolean;
  selectedRowId: string | null;
  onSelect: (rowId: string) => void;
}): ReactElement {
  return (
    <MapContainer center={[targetRoute.lat, targetRoute.lng]} zoom={14} scrollWheelZoom={true} style={{ height: "100%", width: "100%" }}>
      <TileLayer attribution="OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

      <Marker position={[props.unitPosition.lat, props.unitPosition.lng]} icon={unitIcon}>
        <Popup>Recovery unit</Popup>
      </Marker>

      <Marker position={[targetRoute.lat, targetRoute.lng]} icon={targetIcon}>
        <Popup>{targetRoute.address}</Popup>
      </Marker>

      {props.showRadiusRing ? (
        <Circle
          center={[targetRoute.lat, targetRoute.lng]}
          radius={props.radiusFeet * 0.3048}
          pathOptions={{
            color: "#38E8FF",
            fillColor: "rgba(56,232,255,0.10)",
            fillOpacity: 0.3,
            weight: 2,
            dashArray: "6 5",
          }}
        />
      ) : null}

      <Polyline positions={props.routePath} pathOptions={{ color: "#38E8FF", opacity: 0.8, weight: 4 }} />

      {props.rows.map((row) => (
        <Marker
          key={row.id}
          position={[row.lat, row.lng]}
          icon={makePlateIcon(row.plate1, row.hotlist || row.id === props.selectedRowId)}
          eventHandlers={{
            click: () => props.onSelect(row.id),
          }}
        >
          <Popup>
            <strong>{row.plate1}</strong>
            <br />
            {row.vehicle}
            <br />
            {row.gps}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}

function Toggle(props: { checked: boolean; onChange: (checked: boolean) => void; label: string }): ReactElement {
  return (
    <label className="toggle" aria-label={props.label}>
      <input checked={props.checked} type="checkbox" onChange={(event) => props.onChange(event.target.checked)} />
      <span className="toggle-track" />
      <span className="toggle-thumb" />
    </label>
  );
}

function Badge(props: { tone: "cyan" | "critical" | "success" | "warn" | "muted"; children: string }): ReactElement {
  return <span className={`badge badge--${props.tone}`}>{props.children}</span>;
}

function useDetectionFrameImage(detectionId: string | null | undefined, enabled: boolean): string | null {
  const [frameUrl, setFrameUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !detectionId) {
      setFrameUrl((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
      return;
    }

    const controller = new AbortController();
    let nextUrl: string | null = null;
    const detectionIdToLoad = detectionId;

    async function loadFrame(): Promise<void> {
      try {
        nextUrl = await fetchDetectionFrameObjectUrl(detectionIdToLoad, controller.signal);
        if (!controller.signal.aborted) {
          setFrameUrl((current) => {
            if (current && current !== nextUrl) {
              URL.revokeObjectURL(current);
            }
            return nextUrl;
          });
        }
      } catch {
        if (!controller.signal.aborted) {
          setFrameUrl((current) => {
            if (current) {
              URL.revokeObjectURL(current);
            }
            return null;
          });
        }
      }
    }

    void loadFrame();

    return () => {
      controller.abort();
      if (nextUrl) {
        URL.revokeObjectURL(nextUrl);
      }
    };
  }, [detectionId, enabled]);

  return frameUrl;
}

function useDetectionPlateCropImage(detectionId: string | null | undefined, enabled: boolean): string | null {
  const [cropUrl, setCropUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !detectionId) {
      setCropUrl((current) => {
        if (current) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
      return;
    }

    const controller = new AbortController();
    let nextUrl: string | null = null;
    const idToLoad = detectionId;

    async function loadCrop(): Promise<void> {
      try {
        nextUrl = await fetchDetectionPlateCropObjectUrl(idToLoad, controller.signal);
        if (!controller.signal.aborted) {
          setCropUrl((current) => {
            if (current && current !== nextUrl) {
              URL.revokeObjectURL(current);
            }
            return nextUrl;
          });
        }
      } catch {
        if (!controller.signal.aborted) {
          setCropUrl((current) => {
            if (current) {
              URL.revokeObjectURL(current);
            }
            return null;
          });
        }
      }
    }

    void loadCrop();

    return () => {
      controller.abort();
      if (nextUrl) {
        URL.revokeObjectURL(nextUrl);
      }
    };
  }, [detectionId, enabled]);

  return cropUrl;
}

function CameraViewport(props: {
  cameraId: string;
  row: ConsoleDetectionRow | null;
  dataSource: DataSource;
  compact?: boolean;
}): ReactElement {
  const frameUrl = useDetectionFrameImage(props.row?.detectionId, props.dataSource === "live");
  const hasLiveFrame = Boolean(frameUrl);
  const ariaLabel = props.row ? `${props.row.plate1} on ${buildCameraDisplayName(props.cameraId)}` : buildCameraDisplayName(props.cameraId);

  return (
    <div className={`camera-stage ${props.compact ? "camera-stage--compact" : ""}`}>
      <div className={`camera-feed ${props.compact ? "camera-feed--compact" : ""} ${hasLiveFrame ? "camera-feed--image" : "camera-feed--placeholder"}`} aria-label={ariaLabel}>
        {hasLiveFrame ? <img alt={ariaLabel} className="camera-feed__image" src={frameUrl ?? undefined} /> : null}
        {!hasLiveFrame ? (
          <div className="camera-feed__placeholder" aria-hidden="true">
            <div className="camera-feed__placeholder-glow" />
            <div className="camera-feed__placeholder-road" />
            <div className="camera-feed__placeholder-road camera-feed__placeholder-road--secondary" />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ScreenHeader(props: { title: string; subtitle?: string; meta?: ReactElement; actions?: ReactElement }): ReactElement {
  return (
    <header className="screen-header">
      <div>
        <h1>{props.title}</h1>
        {props.subtitle ? <p className="screen-subtitle">{props.subtitle}</p> : null}
      </div>
      {props.meta || props.actions ? (
        <div className="screen-header__aside">
          {props.meta ? <div className="screen-header__meta">{props.meta}</div> : null}
          {props.actions ? <div className="screen-header__actions">{props.actions}</div> : null}
        </div>
      ) : null}
    </header>
  );
}

function App(): ReactElement {
  const [screen, setScreen] = useState<AppScreen>("console");
  const [consoleLayoutMode, setConsoleLayoutMode] = useState<ConsoleLayoutMode>("overview");
  const [stageView, setStageView] = useState<StageView>("camera");
  const [selectedCameraId, setSelectedCameraId] = useState<string>("");
  const [selectedDetectionId, setSelectedDetectionId] = useState<string | null>(null);
  const [detailDetectionId, setDetailDetectionId] = useState<string | null>(null);
  const [detailImageUrl, setDetailImageUrl] = useState<string | null>(null);
  const [settings, setSettings] = useState<UiSettings>(() => loadStoredSettings());
  const [apiKey, setApiKey] = useState<string>(() => loadStoredString(apiKeyStorageKey));
  const [apiKeyInput, setApiKeyInput] = useState<string>(() => loadStoredString(apiKeyStorageKey));
  const [activeDestination, setActiveDestination] = useState<string>(() => loadStoredString(targetAddressStorageKey, targetRoute.address));
  const [destinationInput, setDestinationInput] = useState<string>(() => loadStoredString(targetAddressStorageKey, targetRoute.address));
  const [navigationActive, setNavigationActive] = useState(true);
  const [distanceFeet, setDistanceFeet] = useState(1400);
  const [dataSource, setDataSource] = useState<DataSource>("demo");
  const [overview, setOverview] = useState<DashboardOverviewResponse | null>(null);
  const [hotlists, setHotlists] = useState<DashboardHotlist[]>(seedHotlists);
  const [dataError, setDataError] = useState<string | null>(null);
  const [auditEvents, setAuditEvents] = useState<ApiAuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [searchMode, setSearchMode] = useState<SearchMode>("plate");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFromLocal, setSearchFromLocal] = useState("");
  const [searchToLocal, setSearchToLocal] = useState("");
  const [searchVehicleColor, setSearchVehicleColor] = useState("");
  const [searchVehicleMake, setSearchVehicleMake] = useState("");
  const [searchVehicleModel, setSearchVehicleModel] = useState("");
  const [searchVehicleYear, setSearchVehicleYear] = useState("");
  const [searchAlertStatus, setSearchAlertStatus] = useState<DashboardAlertStatus | "">("");
  const [searchMinLatitude, setSearchMinLatitude] = useState("");
  const [searchMaxLatitude, setSearchMaxLatitude] = useState("");
  const [searchMinLongitude, setSearchMinLongitude] = useState("");
  const [searchMaxLongitude, setSearchMaxLongitude] = useState("");
  const [searchHotlistOnly, setSearchHotlistOnly] = useState(false);
  const [searchHighConfidenceOnly, setSearchHighConfidenceOnly] = useState(false);
  const [searchCurrentCameraOnly, setSearchCurrentCameraOnly] = useState(false);
  const [searchCurrentShiftOnly, setSearchCurrentShiftOnly] = useState(false);
  const [searchGroupByPlate, setSearchGroupByPlate] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const [searchResults, setSearchResults] = useState<ConsoleDetectionRow[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchExecuted, setSearchExecuted] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [selectedHotlistId, setSelectedHotlistId] = useState<string | null>(null);
  const [hotlistDraft, setHotlistDraft] = useState<HotlistDraft>(buildBlankHotlistDraft("9KPN665"));
  const [hotlistSaving, setHotlistSaving] = useState(false);
  const [hotlistDeleting, setHotlistDeleting] = useState(false);
  const [hotlistError, setHotlistError] = useState<string | null>(null);
  const [hotlistMessage, setHotlistMessage] = useState<string | null>(null);
  const [localFollowUps, setLocalFollowUps] = useState<FollowUpRecord[]>([]);
  const [localAssignments, setLocalAssignments] = useState<DispatchAssignmentRecord[]>([]);
  const [followUpSaving, setFollowUpSaving] = useState(false);
  const [followUpError, setFollowUpError] = useState<string | null>(null);
  const [followUpMessage, setFollowUpMessage] = useState<string | null>(null);
  const [assignmentSaving, setAssignmentSaving] = useState(false);
  const [assignmentError, setAssignmentError] = useState<string | null>(null);
  const [assignmentMessage, setAssignmentMessage] = useState<string | null>(null);
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [alertResponseNotes, setAlertResponseNotes] = useState("");
  const [hotlistsTab, setHotlistsTab] = useState<HotlistsWorkspaceTab>("accounts");
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("workspace");
  const [alertActionId, setAlertActionId] = useState<string | null>(null);
  const [alertActionError, setAlertActionError] = useState<string | null>(null);
  const [alertActionMessage, setAlertActionMessage] = useState<string | null>(null);
  const [hotlistOverlayId, setHotlistOverlayId] = useState<string | null>(null);
  const [hotlistAudioMuted, setHotlistAudioMuted] = useState(false);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [detailReviews, setDetailReviews] = useState<ReviewRecord[]>([]);
  const [detailReviewsLoading, setDetailReviewsLoading] = useState(false);
  const [detailReviewsError, setDetailReviewsError] = useState<string | null>(null);
  const prevActiveAlertIdsRef = useRef<Set<string>>(new Set());
  const alertSurfaceInitializedRef = useRef(false);

  useEffect(() => {
    setApiClientConfig({ apiKey });
    if (typeof window !== "undefined") {
      window.localStorage.setItem(apiKeyStorageKey, apiKey);
    }
  }, [apiKey]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(uiSettingsStorageKey, JSON.stringify(settings));
    }
  }, [settings]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(targetAddressStorageKey, activeDestination);
    }
  }, [activeDestination]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadLiveData(): Promise<void> {
      try {
        const [nextOverview, nextHotlists] = await Promise.all([
          fetchDashboardOverview(controller.signal),
          fetchHotlists(controller.signal),
        ]);

        if (controller.signal.aborted) {
          return;
        }

        setOverview(nextOverview);
        setHotlists(nextHotlists.length > 0 ? nextHotlists : seedHotlists);
        setLocalFollowUps([]);
        setLocalAssignments([]);
        setDataSource("live");
        setDataError(null);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        setOverview(null);
        setDataSource(apiKey.trim() ? "fallback" : "demo");
        setDataError(error instanceof Error ? error.message : "Unable to reach the live API");
      }
    }

    void loadLiveData();

    return () => {
      controller.abort();
    };
  }, [apiKey, refreshToken]);

  // Auto-poll live data every 15 seconds when connected to the API.
  useEffect(() => {
    if (dataSource !== "live") {
      return;
    }
    const pollId = setInterval(() => setRefreshToken((v) => v + 1), 15_000);
    return () => clearInterval(pollId);
  }, [dataSource]);

  useEffect(() => {
    if (dataSource !== "live") {
      return;
    }

    const controller = new AbortController();
    const overlayAlertId =
      screen !== "hotlists" && hotlistOverlayId
        ? (overview?.alerts ?? []).find((alert) => alert.detection_id === hotlistOverlayId.replace(/^live-/, ""))?.alert_id
        : undefined;

    async function sendHeartbeat(): Promise<void> {
      try {
        await sendOperatorSessionHeartbeat(
          {
            session_id: operatorSessionId,
            client_label: "reposcan-ops-console",
            workspace: screen,
            selected_detection_id: selectedDetectionId ?? undefined,
            selected_alert_id: screen === "hotlists" ? selectedAlertId ?? undefined : overlayAlertId,
            navigation_active: navigationActive,
          },
          controller.signal,
        );
      } catch {
        // heartbeat failures are silent — the backend will expire stale sessions
      }
    }

    void sendHeartbeat();
    const intervalId = setInterval(() => void sendHeartbeat(), 30_000);

    return () => {
      controller.abort();
      clearInterval(intervalId);
    };
  }, [dataSource, screen, selectedDetectionId, selectedAlertId, hotlistOverlayId, overview?.alerts, navigationActive]);

  const allRows = useMemo(() => {
    const rows =
      dataSource === "live"
        ? (overview?.detections ?? []).map((record, index) => {
            const row = mapDetectionToRow(record, index, hotlists);
            const matchingAlert = (overview?.alerts ?? []).find(
              (alert) =>
                alert.detection_id === record.detection_id ||
                normalizePlate(alert.matched_plate_text) === normalizePlate(row.plate1),
            );

            if (!matchingAlert) {
              return row;
            }

            return {
              ...row,
              alertId: matchingAlert.alert_id,
              alertStatus: matchingAlert.status,
              alertMatchType: matchingAlert.match_type,
              alertNotes: [matchingAlert.notes, matchingAlert.response_notes].filter(Boolean).join(" · ") || undefined,
            };
          })
        : buildSeedRows(hotlists);

    return rows.sort((left, right) => right.timestampUtc.localeCompare(left.timestampUtc));
  }, [dataSource, overview?.alerts, overview?.detections, hotlists]);

  const availableCameraFeeds = useMemo(() => buildCameraUiFeeds(allRows, dataSource), [allRows, dataSource]);

  useEffect(() => {
    const currentRowStillExists = selectedDetectionId ? allRows.some((row) => row.id === selectedDetectionId) : false;
    if (!currentRowStillExists && allRows[0]) {
      setSelectedDetectionId(allRows[0].id);
    }
  }, [allRows, selectedDetectionId]);

  useEffect(() => {
    if (availableCameraFeeds.length === 0) {
      if (selectedCameraId) {
        setSelectedCameraId("");
      }
      return;
    }

    const cameraStillExists = availableCameraFeeds.some((feed) => feed.id === selectedCameraId);
    if (!cameraStillExists) {
      setSelectedCameraId(availableCameraFeeds[0].id);
    }
  }, [availableCameraFeeds, selectedCameraId]);

  useEffect(() => {
    const stillExists = selectedHotlistId ? hotlists.some((entry) => entry.entry_id === selectedHotlistId) : false;
    if (stillExists) {
      return;
    }

    const firstEntry = hotlists[0];
    if (firstEntry) {
      setSelectedHotlistId(firstEntry.entry_id);
      setHotlistDraft(hotlistDraftFromEntry(firstEntry));
      return;
    }

    setSelectedHotlistId(null);
    setHotlistDraft(buildBlankHotlistDraft(allRows[0]?.plate1 ?? ""));
  }, [hotlists, selectedHotlistId, allRows]);

  useEffect(() => {
    if (searchExecuted) {
      return;
    }
    const initialRows = allRows.slice(0, 8);
    setSearchResults(initialRows);
    setSearchTotal(initialRows.length);
  }, [allRows, searchExecuted]);

  useEffect(() => {
    const detailRow = [...allRows, ...searchResults].find((row) => row.id === detailDetectionId);
    if (!detailRow?.detectionId || dataSource !== "live") {
      setDetailImageUrl(null);
      return;
    }

    const controller = new AbortController();
    let nextUrl: string | null = null;

    async function loadDetailImage(): Promise<void> {
      try {
        const detectionId = detailRow?.detectionId ?? "";
        nextUrl = await fetchDetectionFrameObjectUrl(detectionId, controller.signal);
        if (!controller.signal.aborted) {
          setDetailImageUrl(nextUrl);
        }
      } catch {
        if (!controller.signal.aborted) {
          setDetailImageUrl(null);
        }
      }
    }

    void loadDetailImage();

    return () => {
      controller.abort();
      if (nextUrl) {
        URL.revokeObjectURL(nextUrl);
      }
    };
  }, [detailDetectionId, dataSource, allRows, searchResults]);

  useEffect(() => {
    const currentDetailRow = [...allRows, ...searchResults].find((row) => row.id === detailDetectionId);
    if (!currentDetailRow?.detectionId || dataSource !== "live") {
      setDetailReviews([]);
      setDetailReviewsError(null);
      setDetailReviewsLoading(false);
      return;
    }

    const controller = new AbortController();

    async function loadDetailReviews(): Promise<void> {
      try {
        setDetailReviewsLoading(true);
        setDetailReviewsError(null);
        const detectionId = currentDetailRow?.detectionId;
        if (!detectionId) {
          setDetailReviews([]);
          return;
        }
        const reviews = await fetchReviews(detectionId, controller.signal);
        if (!controller.signal.aborted) {
          setDetailReviews(reviews);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setDetailReviews([]);
          setDetailReviewsError(error instanceof Error ? error.message : "Unable to load review history.");
        }
      } finally {
        if (!controller.signal.aborted) {
          setDetailReviewsLoading(false);
        }
      }
    }

    void loadDetailReviews();

    return () => {
      controller.abort();
    };
  }, [detailDetectionId, dataSource, allRows, searchResults, refreshToken]);

  const selectedRow = allRows.find((row) => row.id === selectedDetectionId) ?? allRows[0] ?? null;
  const detailRow = [...allRows, ...searchResults].find((row) => row.id === detailDetectionId) ?? null;
  const hotlistOverlayRow = allRows.find((row) => row.id === hotlistOverlayId) ?? null;
  const currentCamera = availableCameraFeeds.find((feed) => feed.id === selectedCameraId) ?? availableCameraFeeds[0];
  const currentCameraIndex = currentCamera ? availableCameraFeeds.findIndex((feed) => feed.id === currentCamera.id) : -1;
  const secondaryCamera =
    availableCameraFeeds.length > 1 && currentCameraIndex >= 0 ? availableCameraFeeds[(currentCameraIndex + 1) % availableCameraFeeds.length] : currentCamera;
  const primaryCameraId = currentCamera?.id ?? selectedRow?.cameraId ?? selectedCameraId;
  const secondaryCameraId = secondaryCamera?.id ?? primaryCameraId;
  const cameraRows = allRows.filter((row) => row.cameraId === primaryCameraId);
  const secondaryCameraRows = allRows.filter((row) => row.cameraId === secondaryCameraId);
  const cameraFocusRow = cameraRows[0] ?? selectedRow;
  const secondaryCameraFocusRow = secondaryCameraRows[0] ?? allRows.find((row) => row.cameraId === secondaryCameraId) ?? selectedRow;
  const routeProgress = navigationActive ? clamp(1 - distanceFeet / 4800, 0, 1) : 0;
  const unitPosition = interpolatePosition(routeProgress);
  const routePath = buildRoutePath(unitPosition);
  const withinRadius = navigationActive && distanceFeet <= settings.arrivalRadiusFeet;
  const totalReads = overview?.counts.recent_detections ?? 142;
  const activeAlerts = overview?.counts.active_alerts ?? allRows.filter((row) => row.hotlist).length;
  const activeSessions = overview?.counts.active_sessions ?? 3;
  const followUps = overview?.follow_ups ?? localFollowUps;
  const assignments = overview?.assignments ?? localAssignments;
  const openFollowUps = overview?.counts.open_follow_ups ?? followUps.filter((item) => item.status !== "resolved").length;
  const activeAssignments =
    overview?.counts.active_assignments ??
    assignments.filter((item) => item.status !== "completed" && item.status !== "cancelled").length;
  const onlineCameraCount = availableCameraFeeds.filter((feed) => feed.status === "Online").length;
  const routeStatusLabel = !navigationActive
    ? "Route idle"
    : withinRadius
      ? settings.arrivalScanEnabled
        ? "Within radius - scan armed"
        : "Within radius - scan off"
      : "En route";
  const routeEta = formatEta(distanceFeet, navigationActive);
  const routeDistance = formatDistance(distanceFeet);
  const detailTimeline = detailRow ? allRows.filter((row) => normalizePlate(row.plate1) === normalizePlate(detailRow.plate1)) : [];
  const groupedSearchResults = searchGroupByPlate ? buildPlateGroups(searchResults) : [];
  const hotlistWarning = !settings.hotlistAlerts || !settings.soundEnabled;
  const serviceHealthState = overview?.health.state ?? (dataSource === "live" ? "healthy" : dataSource === "demo" ? "demo mode" : "offline");
  const degradedDependencyCount = overview?.health.dependencies.filter((dependency) => dependency.state.toLowerCase() !== "healthy").length ?? 0;
  const hotlistAlertItems = useMemo<HotlistAlertItem[]>(
    () =>
      [...(overview?.alerts ?? [])]
        .sort((left, right) => (right.updated_at_utc ?? right.timestamp_utc).localeCompare(left.updated_at_utc ?? left.timestamp_utc))
        .map((alert) => ({
          alert,
          row: allRows.find((row) => row.detectionId === alert.detection_id) ?? null,
        })),
    [overview?.alerts, allRows],
  );
  const recognitionActivityItems = useMemo<RecognitionActivityItem[]>(
    () =>
      [...(overview?.popup_activity ?? [])]
        .sort((left, right) => right.timestamp_utc.localeCompare(left.timestamp_utc))
        .map((event) => ({
          event,
          row: allRows.find((row) => row.detectionId === event.detection_id) ?? null,
        })),
    [overview?.popup_activity, allRows],
  );
  const canManageHotlistAccounts = dataSource !== "live" || overview?.current_principal.capabilities.can_manage_hotlists === true;
  const canUpdateVehicleAlerts = dataSource !== "live" || overview?.current_principal.capabilities.can_update_alerts === true;
  const canManageFollowUps = dataSource !== "live" || overview?.current_principal.capabilities.can_manage_follow_ups === true;
  const canManageDispatch = dataSource !== "live" || overview?.current_principal.capabilities.can_manage_dispatch === true;
  const canViewAudit = dataSource === "live" && overview?.current_principal.capabilities.can_view_audit === true;
  const currentPrincipal = overview?.current_principal ?? null;
  const activeSessionRecords = overview?.active_sessions ?? [];

  useEffect(() => {
    if (dataSource !== "live") {
      setAuditEvents([]);
      setAuditError(null);
      setAuditLoading(false);
      return;
    }

    if (!canViewAudit) {
      setAuditEvents([]);
      setAuditError(null);
      setAuditLoading(false);
      return;
    }

    const controller = new AbortController();

    async function loadAuditEvents(): Promise<void> {
      try {
        setAuditLoading(true);
        setAuditError(null);
        const events = await fetchAuditEvents({ limit: 12 }, controller.signal);
        if (!controller.signal.aborted) {
          setAuditEvents(events);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setAuditError(error instanceof Error ? error.message : "Unable to load audit activity.");
        }
      } finally {
        if (!controller.signal.aborted) {
          setAuditLoading(false);
        }
      }
    }

    void loadAuditEvents();

    return () => {
      controller.abort();
    };
  }, [dataSource, canViewAudit, refreshToken]);

  useEffect(() => {
    if (!settings.hotlistAlerts) {
      return;
    }
    const currentActiveIds = new Set(
      (overview?.alerts ?? []).filter((alert) => alert.status === "active").map((alert) => alert.alert_id),
    );
    const prev = prevActiveAlertIdsRef.current;

    // Only initialize once we have real data — if overview is still null the
    // active set is empty, which would make all subsequent alerts look "new."
    if (!alertSurfaceInitializedRef.current) {
      if (!overview) {
        return;
      }
      alertSurfaceInitializedRef.current = true;
      prevActiveAlertIdsRef.current = currentActiveIds;
      return;
    }

    const newAlertId = [...currentActiveIds].find((id) => !prev.has(id));
    prevActiveAlertIdsRef.current = currentActiveIds;

    if (!newAlertId) {
      return;
    }

    const newAlert = (overview?.alerts ?? []).find((alert) => alert.alert_id === newAlertId);
    if (!newAlert) {
      return;
    }

    const matchingRow =
      allRows.find((row) => row.detectionId === newAlert.detection_id) ??
      allRows.find((row) => normalizePlate(row.plate1) === normalizePlate(newAlert.matched_plate_text));

    if (matchingRow) {
      setSelectedDetectionId(matchingRow.id);
      setHotlistOverlayId(matchingRow.id);
      setHotlistAudioMuted(false);
    }
  }, [overview?.alerts, settings.hotlistAlerts, allRows]);

  function switchScreen(nextScreen: AppScreen): void {
    startTransition(() => setScreen(nextScreen));
  }

  function updateSetting<Key extends keyof UiSettings>(key: Key, value: UiSettings[Key]): void {
    setSettings((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function openDetail(row: ConsoleDetectionRow): void {
    setSelectedDetectionId(row.id);
    setDetailDetectionId(row.id);
  }

  function centerMapOnRow(row: ConsoleDetectionRow): void {
    setSelectedDetectionId(row.id);
    setStageView("map");
    switchScreen("console");
  }

  function sendRowToHotlistWorkspace(row: ConsoleDetectionRow): void {
    setSelectedDetectionId(row.id);
    beginHotlistDraft(row.plate1);
    switchScreen("hotlists");
  }

  function openRecordForDetectionId(detectionId: string | null | undefined): void {
    if (!detectionId) {
      return;
    }
    const row = allRows.find((item) => item.detectionId === detectionId);
    if (!row) {
      return;
    }
    openDetail(row);
  }

  function centerMapOnDetectionId(detectionId: string | null | undefined): void {
    if (!detectionId) {
      return;
    }
    const row = allRows.find((item) => item.detectionId === detectionId);
    if (!row) {
      return;
    }
    centerMapOnRow(row);
  }

  function openLatestHotlistAlert(): void {
    const latestActiveAlert = [...(overview?.alerts ?? [])]
      .filter((alert) => alert.status === "active")
      .sort((left, right) => (right.updated_at_utc ?? right.timestamp_utc).localeCompare(left.updated_at_utc ?? left.timestamp_utc))[0];

    if (latestActiveAlert) {
      const matchingAlertRow =
        allRows.find((row) => row.detectionId === latestActiveAlert.detection_id) ??
        allRows.find(
          (row) =>
            row.cameraId === latestActiveAlert.camera_id &&
            normalizePlate(row.plate1) === normalizePlate(latestActiveAlert.matched_plate_text),
        );

      if (matchingAlertRow) {
        setSelectedDetectionId(matchingAlertRow.id);
        setHotlistOverlayId(matchingAlertRow.id);
        return;
      }
    }

    const latestHotlistRow = allRows.find((row) => row.hotlist);
    if (!latestHotlistRow) {
      switchScreen("hotlists");
      return;
    }
    setSelectedDetectionId(latestHotlistRow.id);
    setHotlistOverlayId(latestHotlistRow.id);
  }

  function beginHotlistDraft(seedPlate?: string): void {
    setSelectedHotlistId(null);
    setHotlistDraft(buildBlankHotlistDraft(seedPlate ?? selectedRow?.plate1 ?? ""));
    setHotlistError(null);
    setHotlistMessage(null);
  }

  function loadHotlist(entry: DashboardHotlist): void {
    setSelectedHotlistId(entry.entry_id);
    setHotlistDraft(hotlistDraftFromEntry(entry));
    setHotlistError(null);
    setHotlistMessage(null);
  }

  function clearSearchFilters(): void {
    setSearchVehicleColor("");
    setSearchVehicleMake("");
    setSearchVehicleModel("");
    setSearchVehicleYear("");
    setSearchAlertStatus("");
    setSearchMinLatitude("");
    setSearchMaxLatitude("");
    setSearchMinLongitude("");
    setSearchMaxLongitude("");
    setSearchHotlistOnly(false);
    setSearchHighConfidenceOnly(false);
    setSearchCurrentCameraOnly(false);
    setSearchCurrentShiftOnly(false);
  }

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSearchLoading(true);
    setSearchError(null);
    setSearchMessage(null);

    const fromUtc = toUtcIso(searchFromLocal);
    const toUtc = toUtcIso(searchToLocal);

    const localFallback = (): void => {
      const nextRows = filterRowsLocally({
        alerts: overview?.alerts ?? [],
        rows: allRows,
        mode: searchMode,
        query: searchQuery,
        fromUtc,
        toUtc,
        vehicleColor: searchVehicleColor,
        vehicleMake: searchVehicleMake,
        vehicleModel: searchVehicleModel,
        vehicleYear: searchVehicleYear,
        alertStatus: searchAlertStatus,
        minLatitude: searchMinLatitude,
        maxLatitude: searchMaxLatitude,
        minLongitude: searchMinLongitude,
        maxLongitude: searchMaxLongitude,
        hotlistOnly: searchHotlistOnly,
        highConfidenceOnly: searchHighConfidenceOnly,
        currentCameraOnly: searchCurrentCameraOnly,
        currentShiftOnly: searchCurrentShiftOnly,
        currentCameraId: selectedCameraId,
      });
      startTransition(() => {
        setSearchResults(nextRows);
        setSearchTotal(nextRows.length);
        setSearchExecuted(true);
      });
    };

    if (dataSource === "live") {
      try {
        const filters: DetectionSearchFilters = {
          limit: 200,
          start_utc: fromUtc,
          end_utc: toUtc,
        };
        const alertFilters: AlertSearchFilters = {
          limit: 200,
          start_utc: fromUtc,
          end_utc: toUtc,
        };

        if (searchCurrentCameraOnly && selectedCameraId) {
          filters.camera_id = selectedCameraId;
          alertFilters.camera_id = selectedCameraId;
        }
        if (searchVehicleColor.trim()) {
          filters.vehicle_color = searchVehicleColor.trim();
          alertFilters.vehicle_color = searchVehicleColor.trim();
        }
        if (searchVehicleMake.trim()) {
          filters.vehicle_make = searchVehicleMake.trim();
          alertFilters.vehicle_make = searchVehicleMake.trim();
        }
        if (searchVehicleModel.trim()) {
          filters.vehicle_model = searchVehicleModel.trim();
          alertFilters.vehicle_model = searchVehicleModel.trim();
        }
        if (searchVehicleYear.trim()) {
          filters.vehicle_year = searchVehicleYear.trim();
          alertFilters.vehicle_year = searchVehicleYear.trim();
        }
        if (searchAlertStatus) {
          filters.alert_status = searchAlertStatus;
          alertFilters.status = searchAlertStatus;
        }
        if (searchMinLatitude.trim()) {
          filters.min_latitude = Number(searchMinLatitude);
          alertFilters.min_latitude = Number(searchMinLatitude);
        }
        if (searchMaxLatitude.trim()) {
          filters.max_latitude = Number(searchMaxLatitude);
          alertFilters.max_latitude = Number(searchMaxLatitude);
        }
        if (searchMinLongitude.trim()) {
          filters.min_longitude = Number(searchMinLongitude);
          alertFilters.min_longitude = Number(searchMinLongitude);
        }
        if (searchMaxLongitude.trim()) {
          filters.max_longitude = Number(searchMaxLongitude);
          alertFilters.max_longitude = Number(searchMaxLongitude);
        }

        if (searchMode === "plate") {
          filters.plate = searchQuery.trim();
          filters.plate_match = "contains";
          alertFilters.plate = searchQuery.trim();
          alertFilters.plate_match = "contains";
        } else if (searchMode === "camera") {
          const normalizedCameraQuery = searchQuery.trim().toUpperCase();
          const matchedCamera = availableCameraFeeds.find(
            (feed) =>
              feed.id.toUpperCase().includes(normalizedCameraQuery) ||
              feed.label.toUpperCase().includes(normalizedCameraQuery) ||
              feed.shortLabel.toUpperCase().includes(normalizedCameraQuery),
          );
          if (matchedCamera?.id) {
            filters.camera_id = matchedCamera.id;
            alertFilters.camera_id = matchedCamera.id;
          } else if (searchCurrentCameraOnly && selectedCameraId) {
            filters.camera_id = selectedCameraId;
            alertFilters.camera_id = selectedCameraId;
          }
        } else if (searchMode === "vehicle") {
          const [make, ...modelParts] = searchQuery.trim().split(/\s+/).filter(Boolean);
          if (make && !filters.vehicle_make) {
            filters.vehicle_make = make;
            alertFilters.vehicle_make = make;
          }
          if (modelParts.length > 0 && !filters.vehicle_model) {
            filters.vehicle_model = modelParts.join(" ");
            alertFilters.vehicle_model = modelParts.join(" ");
          }
        } else if (searchMode === "alert") {
          alertFilters.plate = searchQuery.trim();
          alertFilters.plate_match = "contains";
        }

        if (searchMode === "alert") {
          const result = await searchAlerts(alertFilters);
          const detectionsById = new Map((overview?.detections ?? []).map((record) => [record.detection_id, record]));
          const mappedRows = result.results.map((alert, index) =>
            mapAlertToRow(alert, detectionsById.get(alert.detection_id), index, hotlists),
          );
          const filteredRows = filterRowsLocally({
            alerts: result.results,
            rows: mappedRows,
            mode: searchMode,
            query: searchQuery,
            fromUtc,
            toUtc,
            vehicleColor: searchVehicleColor,
            vehicleMake: searchVehicleMake,
            vehicleModel: searchVehicleModel,
            vehicleYear: searchVehicleYear,
            alertStatus: searchAlertStatus,
            minLatitude: searchMinLatitude,
            maxLatitude: searchMaxLatitude,
            minLongitude: searchMinLongitude,
            maxLongitude: searchMaxLongitude,
            hotlistOnly: searchHotlistOnly,
            highConfidenceOnly: searchHighConfidenceOnly,
            currentCameraOnly: searchCurrentCameraOnly,
            currentShiftOnly: searchCurrentShiftOnly,
            currentCameraId: selectedCameraId,
          });

          startTransition(() => {
            setSearchResults(filteredRows);
            setSearchTotal(result.page.total_results);
            setSearchExecuted(true);
          });
        } else {
          const result = await searchDetections(filters);
          const mappedRows = result.results.map((record, index) => mapDetectionToRow(record, index, hotlists));
          const filteredRows = filterRowsLocally({
            alerts: overview?.alerts ?? [],
            rows: mappedRows,
            mode: searchMode,
            query: searchQuery,
            fromUtc,
            toUtc,
            vehicleColor: searchVehicleColor,
            vehicleMake: searchVehicleMake,
            vehicleModel: searchVehicleModel,
            vehicleYear: searchVehicleYear,
            alertStatus: searchAlertStatus,
            minLatitude: searchMinLatitude,
            maxLatitude: searchMaxLatitude,
            minLongitude: searchMinLongitude,
            maxLongitude: searchMaxLongitude,
            hotlistOnly: searchHotlistOnly,
            highConfidenceOnly: searchHighConfidenceOnly,
            currentCameraOnly: searchCurrentCameraOnly,
            currentShiftOnly: searchCurrentShiftOnly,
            currentCameraId: selectedCameraId,
          });

          startTransition(() => {
            setSearchResults(filteredRows);
            setSearchTotal(result.page.total_results);
            setSearchExecuted(true);
          });
        }
      } catch (error) {
        localFallback();
        setSearchError(error instanceof Error ? `${error.message}. Showing cached results.` : "Showing cached results.");
      }
    } else {
      localFallback();
    }

    setSearchLoading(false);
  }

  async function handleCopyPlate(plate: string): Promise<void> {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(plate);
        setSearchMessage(`Copied ${plate} to clipboard.`);
      } else {
        setSearchMessage(`Clipboard is unavailable. Plate: ${plate}`);
      }
    } catch {
      setSearchMessage(`Clipboard write failed. Plate: ${plate}`);
    }
  }

  async function persistHotlist(
    action: "save" | "recover",
    entryOverride?: DashboardHotlist,
    activeOverride?: boolean,
  ): Promise<void> {
    const entry =
      entryOverride ??
      (selectedHotlistId ? hotlists.find((hotlist) => hotlist.entry_id === selectedHotlistId) ?? null : null);

    const nextPlateText = normalizePlate(entry?.plate_text ?? hotlistDraft.plateText);
    const nextLabel = entry?.label ?? hotlistDraft.label;
    const nextNotes = entry?.notes ?? hotlistDraft.notes;
    const nextActive = activeOverride ?? entry?.active ?? hotlistDraft.active;

    if (!nextPlateText) {
      setHotlistError("Plate text is required.");
      return;
    }

    try {
      setHotlistSaving(true);
      setHotlistError(null);
      setHotlistMessage(null);

      if (dataSource === "live") {
        if (entry) {
          await updateHotlist(entry.entry_id, {
            plate_text: nextPlateText,
            label: nextLabel || undefined,
            notes: nextNotes || undefined,
            active: nextActive,
          });
        } else {
          const created = await createHotlist({
            plate_text: nextPlateText,
            label: nextLabel || undefined,
            notes: nextNotes || undefined,
            active: nextActive,
          });
          setSelectedHotlistId(created.entry_id);
        }
        setRefreshToken((value) => value + 1);
      } else {
        const now = new Date().toISOString();
        if (entry) {
          setHotlists((current) =>
            current.map((item) =>
              item.entry_id === entry.entry_id
                ? {
                    ...item,
                    plate_text: nextPlateText,
                    label: nextLabel || null,
                    notes: nextNotes || null,
                    active: nextActive,
                    updated_at_utc: now,
                  }
                : item,
            ),
          );
        } else {
          const created: DashboardHotlist = {
            entry_id: `hl_local_${Math.random().toString(16).slice(2, 10)}`,
            plate_text: nextPlateText,
            label: nextLabel || null,
            notes: nextNotes || null,
            active: nextActive,
            created_at_utc: now,
            updated_at_utc: now,
          };
          setHotlists((current) => [created, ...current]);
          setSelectedHotlistId(created.entry_id);
        }
      }

      setHotlistMessage(action === "recover" ? "Recovery account marked inactive." : entry ? "Recovery account updated." : "Recovery account created.");
    } catch (error) {
      setHotlistError(error instanceof Error ? error.message : "Unable to save the recovery account.");
    } finally {
      setHotlistSaving(false);
    }
  }

  async function handleHotlistSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await persistHotlist("save");
  }

  async function handleDeleteHotlist(): Promise<void> {
    if (!selectedHotlistId) {
      return;
    }

    try {
      setHotlistDeleting(true);
      setHotlistError(null);
      setHotlistMessage(null);

      if (dataSource === "live") {
        await deleteHotlist(selectedHotlistId);
        setRefreshToken((value) => value + 1);
      } else {
        setHotlists((current) => current.filter((entry) => entry.entry_id !== selectedHotlistId));
      }

      setSelectedHotlistId(null);
      setHotlistDraft(buildBlankHotlistDraft(selectedRow?.plate1 ?? ""));
      setHotlistMessage("Recovery account deleted.");
    } catch (error) {
      setHotlistError(error instanceof Error ? error.message : "Unable to delete the recovery account.");
    } finally {
      setHotlistDeleting(false);
    }
  }

  async function handleSaveFollowUp(request: FollowUpSaveRequest): Promise<void> {
    const summary = request.draft.summary.trim();
    const notes = request.draft.notes.trim();
    const assignedOperatorId = request.draft.assignedOperatorId.trim();
    const dueAtUtc = toUtcIso(request.draft.dueAtLocal) ?? null;

    if (!request.detectionId) {
      setFollowUpError("A detection is required before a follow-up can be saved.");
      return;
    }

    try {
      setFollowUpSaving(true);
      setFollowUpError(null);
      setFollowUpMessage(null);

      if (dataSource === "live") {
        if (request.existing) {
          await updateFollowUp(request.existing.follow_up_id, {
            detection_id: request.detectionId,
            alert_id: request.alertId ?? undefined,
            plate_text: request.plateText || undefined,
            priority: request.draft.priority,
            status: request.draft.status,
            assigned_operator_id: assignedOperatorId || undefined,
            summary: summary || undefined,
            notes: notes || undefined,
            due_at_utc: dueAtUtc ?? undefined,
          });
        } else {
          await createFollowUp({
            detection_id: request.detectionId,
            alert_id: request.alertId ?? undefined,
            plate_text: request.plateText || undefined,
            priority: request.draft.priority,
            status: request.draft.status,
            assigned_operator_id: assignedOperatorId || undefined,
            summary: summary || undefined,
            notes: notes || undefined,
            due_at_utc: dueAtUtc ?? undefined,
          });
        }

        setRefreshToken((value) => value + 1);
      } else {
        const now = new Date().toISOString();
        const nextRecord: FollowUpRecord = {
          follow_up_id: request.existing?.follow_up_id ?? `fu_local_${Math.random().toString(16).slice(2, 10)}`,
          detection_id: request.detectionId,
          alert_id: request.alertId,
          plate_text: request.plateText || null,
          priority: request.draft.priority,
          status: request.draft.status,
          created_by_operator_id: request.existing?.created_by_operator_id ?? currentPrincipal?.principal_id ?? "local-operator",
          assigned_operator_id: assignedOperatorId || null,
          summary: summary || null,
          notes: notes || null,
          due_at_utc: dueAtUtc,
          created_at_utc: request.existing?.created_at_utc ?? now,
          updated_at_utc: now,
        };

        setLocalFollowUps((current) =>
          sortByUpdatedDesc([nextRecord, ...current.filter((item) => item.follow_up_id !== nextRecord.follow_up_id)]),
        );
      }

      setFollowUpMessage(request.existing ? "Follow-up updated." : "Follow-up created.");
    } catch (error) {
      setFollowUpError(error instanceof Error ? error.message : "Unable to save the follow-up.");
    } finally {
      setFollowUpSaving(false);
    }
  }

  async function handleSaveAssignment(request: AssignmentSaveRequest): Promise<void> {
    const summary = request.draft.summary.trim();
    const notes = request.draft.notes.trim();
    const assignedOperatorId = request.draft.assignedOperatorId.trim();
    const assignedUnitLabel = request.draft.assignedUnitLabel.trim();
    const destinationLabel = request.draft.destinationLabel.trim();

    if (!request.detectionId) {
      setAssignmentError("A detection is required before a dispatch assignment can be saved.");
      return;
    }

    try {
      setAssignmentSaving(true);
      setAssignmentError(null);
      setAssignmentMessage(null);

      if (dataSource === "live") {
        if (request.existing) {
          await updateDispatchAssignment(request.existing.assignment_id, {
            detection_id: request.detectionId,
            alert_id: request.alertId ?? undefined,
            plate_text: request.plateText || undefined,
            priority: request.draft.priority,
            status: request.draft.status,
            assigned_operator_id: assignedOperatorId || undefined,
            assigned_unit_label: assignedUnitLabel || undefined,
            destination_label: destinationLabel || undefined,
            summary: summary || undefined,
            notes: notes || undefined,
          });
        } else {
          await createDispatchAssignment({
            detection_id: request.detectionId,
            alert_id: request.alertId ?? undefined,
            plate_text: request.plateText || undefined,
            priority: request.draft.priority,
            status: request.draft.status,
            assigned_operator_id: assignedOperatorId || undefined,
            assigned_unit_label: assignedUnitLabel || undefined,
            destination_label: destinationLabel || undefined,
            summary: summary || undefined,
            notes: notes || undefined,
          });
        }

        setRefreshToken((value) => value + 1);
      } else {
        const now = new Date().toISOString();
        const nextRecord: DispatchAssignmentRecord = {
          assignment_id: request.existing?.assignment_id ?? `asg_local_${Math.random().toString(16).slice(2, 10)}`,
          detection_id: request.detectionId,
          alert_id: request.alertId,
          plate_text: request.plateText || null,
          priority: request.draft.priority,
          status: request.draft.status,
          created_by_operator_id: request.existing?.created_by_operator_id ?? currentPrincipal?.principal_id ?? "local-operator",
          assigned_operator_id: assignedOperatorId || null,
          assigned_unit_label: assignedUnitLabel || null,
          destination_label: destinationLabel || null,
          summary: summary || null,
          notes: notes || null,
          created_at_utc: request.existing?.created_at_utc ?? now,
          updated_at_utc: now,
        };

        setLocalAssignments((current) =>
          sortByUpdatedDesc([nextRecord, ...current.filter((item) => item.assignment_id !== nextRecord.assignment_id)]),
        );
      }

      setAssignmentMessage(request.existing ? "Dispatch assignment updated." : "Dispatch assignment created.");
    } catch (error) {
      setAssignmentError(error instanceof Error ? error.message : "Unable to save the dispatch assignment.");
    } finally {
      setAssignmentSaving(false);
    }
  }

  async function handleSubmitReview(detectionId: string, action: ReviewAction, correctedPlate?: string, notes?: string): Promise<void> {
    try {
      setReviewSaving(true);
      setReviewError(null);
      setReviewMessage(null);

      if (dataSource === "live") {
        await createReview(detectionId, {
          action,
          operator_id: overview?.current_principal.principal_id ?? undefined,
          corrected_plate_text: correctedPlate?.trim() || undefined,
          notes: notes?.trim() || undefined,
          reviewed_at_utc: new Date().toISOString(),
        });
        setRefreshToken((value) => value + 1);
      }

      setReviewMessage(
        action === "confirm"
          ? "Detection confirmed."
          : action === "correct"
            ? "OCR correction saved."
            : action === "flag"
              ? "Detection flagged for review."
              : "Detection dismissed as false positive.",
      );
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : "Unable to save review.");
    } finally {
      setReviewSaving(false);
    }
  }

  async function handleRecoverFromAlert(): Promise<void> {
    if (!hotlistOverlayRow) {
      return;
    }

    const entry = hotlists.find((hotlist) => normalizePlate(hotlist.plate_text) === normalizePlate(hotlistOverlayRow.plate1));
    if (!entry) {
      setHotlistOverlayId(null);
      return;
    }

    await persistHotlist("recover", entry, false);
    setHotlistOverlayId(null);
    switchScreen("hotlists");
  }

  async function handleAlertStatusChange(alert: DashboardAlert, status: DashboardAlertStatus, responseNotes?: string): Promise<void> {
    try {
      setAlertActionId(alert.alert_id);
      setAlertActionError(null);
      setAlertActionMessage(null);

      const notes = responseNotes?.trim() || undefined;

      if (dataSource === "live") {
        await updateAlert(alert.alert_id, {
          status,
          operator_id: overview?.current_principal.principal_id,
          response_notes: notes,
        });
        setRefreshToken((value) => value + 1);
      } else {
        setOverview((current) =>
          current
            ? {
                ...current,
                alerts: current.alerts.map((item) =>
                  item.alert_id === alert.alert_id
                    ? {
                        ...item,
                        status,
                        response_operator_id: current.current_principal.principal_id,
                        response_notes: notes ?? item.response_notes,
                        updated_at_utc: new Date().toISOString(),
                      }
                    : item,
                ),
              }
            : current,
        );
      }

      setAlertActionMessage(
        status === "acknowledged"
          ? "Vehicle alert acknowledged."
          : status === "dismissed"
            ? "Vehicle alert dismissed."
            : "Vehicle alert reopened.",
      );
    } catch (error) {
      setAlertActionError(error instanceof Error ? error.message : "Unable to update the alert.");
    } finally {
      setAlertActionId(null);
    }
  }

  const footerIndicators = [
    { label: "GPS", value: "Locked", tone: "good" },
    { label: "API", value: dataSource === "live" ? "Live" : dataSource === "fallback" ? "Fallback" : "Demo", tone: dataSource === "live" ? "good" : "off" },
    { label: "LPR", value: settings.arrivalScanEnabled ? "Scanning" : "Off", tone: settings.arrivalScanEnabled ? "good" : "off" },
    { label: "Cams", value: `${onlineCameraCount}/${availableCameraFeeds.length}`, tone: onlineCameraCount > 0 ? "good" : "off" },
    { label: "Reads", value: `${totalReads}`, tone: "good" },
    { label: "Cases", value: `${activeAlerts}`, tone: activeAlerts > 0 ? "warn" : "good" },
  ] as const;

  return (
    <>
      <div className="ops-app">
        <NavPanel
          activeScreen={screen}
          activeAlerts={activeAlerts}
          activeHotlists={hotlists.filter((entry) => entry.active).length}
          dataSource={dataSource}
          destinationInput={destinationInput}
          navigationActive={navigationActive}
          onDestinationChange={setDestinationInput}
          onOpenAlert={openLatestHotlistAlert}
          onResolve={() => {
            setActiveDestination(destinationInput.trim() || targetRoute.address);
            setStageView("map");
          }}
          onScreenChange={switchScreen}
          onToggleNavigation={() => setNavigationActive((current) => !current)}
          routeDistance={routeDistance}
          routeEta={routeEta}
          routeStatusLabel={routeStatusLabel}
          settings={settings}
          systemDetectionCount={totalReads}
          totalReads={totalReads}
          withinRadius={withinRadius}
          distanceFeet={distanceFeet}
          onDistanceChange={setDistanceFeet}
        />

        <main className="workspace">
          {screen === "console" ? (
            <ConsoleScreen
              activeAlerts={activeAlerts}
              allRows={allRows}
              cameraFeedsList={availableCameraFeeds}
              cameraFocusRow={cameraFocusRow}
              currentCamera={currentCamera}
              dataSource={dataSource}
              selectedCameraId={primaryCameraId}
              selectedDetectionId={selectedDetectionId}
              settings={settings}
              stageView={stageView}
              consoleLayoutMode={consoleLayoutMode}
              unitPosition={unitPosition}
              routePath={routePath}
              withinRadius={withinRadius}
              secondaryCamera={secondaryCamera}
              secondaryCameraFocusRow={secondaryCameraFocusRow}
              onOpenDetail={openDetail}
              onConsoleLayoutChange={setConsoleLayoutMode}
              onSelectCamera={setSelectedCameraId}
              onSelectDetection={setSelectedDetectionId}
              onStageViewChange={setStageView}
            />
          ) : null}

          {screen === "search" ? (
            <SearchScreen
              assignments={assignments}
              dataSource={dataSource}
              expandedGroups={expandedGroups}
              followUps={followUps}
              groupedResults={groupedSearchResults}
              hotlists={hotlists}
              loading={searchLoading}
              query={searchQuery}
              results={searchResults}
              resultsTotal={searchTotal}
              searchError={searchError}
              searchExecuted={searchExecuted}
              searchFromLocal={searchFromLocal}
              searchGroupByPlate={searchGroupByPlate}
              searchHighConfidenceOnly={searchHighConfidenceOnly}
              searchHotlistOnly={searchHotlistOnly}
              searchMaxLatitude={searchMaxLatitude}
              searchMaxLongitude={searchMaxLongitude}
              searchMessage={searchMessage}
              searchMinLatitude={searchMinLatitude}
              searchMinLongitude={searchMinLongitude}
              searchMode={searchMode}
              searchAlertStatus={searchAlertStatus}
              searchToLocal={searchToLocal}
              searchVehicleColor={searchVehicleColor}
              searchVehicleMake={searchVehicleMake}
              searchVehicleModel={searchVehicleModel}
              searchVehicleYear={searchVehicleYear}
              searchCurrentCameraOnly={searchCurrentCameraOnly}
              searchCurrentShiftOnly={searchCurrentShiftOnly}
              onAddToHotlist={sendRowToHotlistWorkspace}
              onClearFilters={clearSearchFilters}
              onCopyPlate={handleCopyPlate}
              onDetails={openDetail}
              onMap={centerMapOnRow}
              onSearchSubmit={handleSearchSubmit}
              onToggleExpanded={(plate) =>
                setExpandedGroups((current) => ({
                  ...current,
                  [plate]: !(current[plate] ?? false),
                }))
              }
              setQuery={setSearchQuery}
              setSearchFromLocal={setSearchFromLocal}
              setSearchGroupByPlate={setSearchGroupByPlate}
              setSearchHighConfidenceOnly={setSearchHighConfidenceOnly}
              setSearchHotlistOnly={setSearchHotlistOnly}
              setSearchMaxLatitude={setSearchMaxLatitude}
              setSearchMaxLongitude={setSearchMaxLongitude}
              setSearchMinLatitude={setSearchMinLatitude}
              setSearchMinLongitude={setSearchMinLongitude}
              setSearchMode={setSearchMode}
              setSearchAlertStatus={setSearchAlertStatus}
              setSearchToLocal={setSearchToLocal}
              setSearchVehicleColor={setSearchVehicleColor}
              setSearchVehicleMake={setSearchVehicleMake}
              setSearchVehicleModel={setSearchVehicleModel}
              setSearchVehicleYear={setSearchVehicleYear}
              setSearchCurrentCameraOnly={setSearchCurrentCameraOnly}
              setSearchCurrentShiftOnly={setSearchCurrentShiftOnly}
            />
          ) : null}

          {screen === "hotlists" ? (
            <HotlistsScreen
              activeAssignments={activeAssignments}
              activeDestination={activeDestination}
              alertActionError={alertActionError}
              alertActionId={alertActionId}
              alertActionMessage={alertActionMessage}
              assignmentActionError={assignmentError}
              assignmentActionMessage={assignmentMessage}
              assignmentSaving={assignmentSaving}
              alerts={hotlistAlertItems}
              canManageAccounts={canManageHotlistAccounts}
              canManageDispatch={canManageDispatch}
              canManageFollowUps={canManageFollowUps}
              canUpdateAlerts={canUpdateVehicleAlerts}
              dataSource={dataSource}
              draft={hotlistDraft}
              error={hotlistError}
              followUps={followUps}
              followUpActionError={followUpError}
              followUpActionMessage={followUpMessage}
              followUpSaving={followUpSaving}
              hotlists={hotlists}
              assignments={assignments}
              activity={recognitionActivityItems}
              activeTab={hotlistsTab}
              message={hotlistMessage}
              openFollowUps={openFollowUps}
              saving={hotlistSaving}
              deleting={hotlistDeleting}
              selectedDetectionPlate={selectedRow?.plate1 ?? ""}
              selectedHotlistId={selectedHotlistId}
              selectedAlertId={selectedAlertId}
              alertResponseNotes={alertResponseNotes}
              onAlertResponseNotesChange={setAlertResponseNotes}
              onAlertStatusChange={(alert, status, notes) => void handleAlertStatusChange(alert, status, notes)}
              onClearDraft={() => beginHotlistDraft()}
              onDelete={() => void handleDeleteHotlist()}
              onDraftChange={setHotlistDraft}
              onMapDetection={centerMapOnDetectionId}
              onOpenRecord={openRecordForDetectionId}
              onSaveAssignment={handleSaveAssignment}
              onSaveFollowUp={handleSaveFollowUp}
              onSelect={loadHotlist}
              onSelectAlert={setSelectedAlertId}
              onSeedFromDetection={() => beginHotlistDraft(selectedRow?.plate1)}
              onSubmit={handleHotlistSubmit}
              onTabChange={setHotlistsTab}
            />
          ) : null}

          {screen === "settings" ? (
            <SettingsScreen
              activeSessions={activeSessions}
              activeSessionRecords={activeSessionRecords}
              auditError={auditError}
              auditEvents={auditEvents}
              auditLoading={auditLoading}
              apiKeyInput={apiKeyInput}
              canManageAccounts={canManageHotlistAccounts}
              canManageDispatch={canManageDispatch}
              canManageFollowUps={canManageFollowUps}
              canViewAudit={canViewAudit}
              canUpdateAlerts={canUpdateVehicleAlerts}
              currentPrincipal={currentPrincipal}
              dataError={dataError}
              dataSource={dataSource}
              degradedDependencyCount={degradedDependencyCount}
              hotlistWarning={hotlistWarning}
              onSettingsSectionChange={setSettingsSection}
              onApiKeyApply={() => setApiKey(apiKeyInput.trim())}
              onApiKeyChange={setApiKeyInput}
              onRefresh={() => setRefreshToken((value) => value + 1)}
              onlineCameras={onlineCameraCount}
              settings={settings}
              settingsSection={settingsSection}
              serviceHealthState={serviceHealthState}
              totalCameras={availableCameraFeeds.length}
              updateSetting={updateSetting}
            />
          ) : null}
        </main>

        <footer className="status-footer">
          {footerIndicators.map((indicator) => (
            <div key={indicator.label} className="status-footer__item">
              <span className={`status-dot status-dot--${indicator.tone}`} />
              <strong>{indicator.label}</strong>
              <span>{indicator.value}</span>
            </div>
          ))}
        </footer>
      </div>

      {detailRow ? (
        <DetailOverlay
          activeDestination={activeDestination}
          assignments={matchingAssignmentsForRow(detailRow, assignments)}
          canSubmitReview={dataSource !== "live" || overview?.current_principal.capabilities.can_submit_reviews === true}
          currentOperatorId={currentPrincipal?.principal_id ?? null}
          dataSource={dataSource}
          detailImageUrl={detailImageUrl}
          hotlistEntry={hotlistEntryForRow(detailRow, hotlists)}
          detailRow={detailRow}
          detailTimeline={detailTimeline}
          detailReviews={detailReviews}
          detailReviewsError={detailReviewsError}
          detailReviewsLoading={detailReviewsLoading}
          followUps={matchingFollowUpsForRow(detailRow, followUps)}
          reviewError={reviewError}
          reviewMessage={reviewMessage}
          reviewSaving={reviewSaving}
          onAddToHotlist={() => {
            beginHotlistDraft(detailRow.plate1);
            switchScreen("hotlists");
            setDetailDetectionId(null);
          }}
          onClose={() => setDetailDetectionId(null)}
          onCopyPlate={handleCopyPlate}
          onOpenMap={() => {
            centerMapOnRow(detailRow);
            setDetailDetectionId(null);
          }}
          onSubmitReview={handleSubmitReview}
        />
      ) : null}

      {hotlistOverlayRow ? (
        <HotlistAlertOverlay
          activeDestination={activeDestination}
          assignment={matchingAssignmentsForRow(hotlistOverlayRow, assignments)[0] ?? null}
          followUp={matchingFollowUpsForRow(hotlistOverlayRow, followUps)[0] ?? null}
          hotlistAudioMuted={hotlistAudioMuted}
          hotlistEntry={hotlistEntryForRow(hotlistOverlayRow, hotlists)}
          hotlistRow={hotlistOverlayRow}
          onDismiss={() => setHotlistOverlayId(null)}
          onMuteToggle={() => setHotlistAudioMuted((value) => !value)}
          onNavigate={() => {
            centerMapOnRow(hotlistOverlayRow);
            setHotlistOverlayId(null);
          }}
          onRecover={() => void handleRecoverFromAlert()}
          onViewRecord={() => {
            openDetail(hotlistOverlayRow);
            setHotlistOverlayId(null);
          }}
        />
      ) : null}
    </>
  );
}

function SearchResultCard(props: {
  assignment: DispatchAssignmentRecord | null;
  dataSource: DataSource;
  followUp: FollowUpRecord | null;
  row: ConsoleDetectionRow;
  hotlistLabel: string | null;
  onAddToHotlist: () => void;
  onDetails: () => void;
  onMap: () => void;
  onCopy: (plate: string) => Promise<void>;
}): ReactElement {
  const frameUrl = useDetectionFrameImage(props.row.detectionId, props.dataSource === "live");

  return (
    <article className="search-result-card">
      <div className={`search-result-card__thumb ${frameUrl ? "search-result-card__thumb--image" : ""}`}>
        {frameUrl ? <img alt={`${props.row.plate1} evidence`} src={frameUrl} /> : <span>{props.row.camera}</span>}
      </div>
      <div className="search-result-card__body">
        <div className="search-result-card__header">
          <div>
            <strong>{props.row.plate1}</strong>
            <p className="search-result-card__eyebrow">{`Last seen ${formatDateTime(props.row.timestampUtc)}`}</p>
            <span>{props.row.vehicle}</span>
          </div>
          <div className="search-result-card__badges">
            {props.row.hotlist ? <Badge tone="critical">Recovery</Badge> : null}
            {props.hotlistLabel ? <Badge tone="warn">{props.hotlistLabel}</Badge> : null}
            {props.row.alertStatus ? <Badge tone={alertStatusTone(props.row.alertStatus)}>{alertStatusLabel(props.row.alertStatus)}</Badge> : null}
            {props.row.alertMatchType ? <Badge tone={props.row.alertMatchType === "exact" ? "success" : "warn"}>{`${titleCase(props.row.alertMatchType)} match`}</Badge> : null}
            {props.followUp ? <Badge tone={followUpStatusTone(props.followUp.status)}>{`Follow-up ${titleCase(props.followUp.status)}`}</Badge> : null}
            {props.assignment ? <Badge tone={dispatchStatusTone(props.assignment.status)}>{`Dispatch ${titleCase(props.assignment.status)}`}</Badge> : null}
          </div>
        </div>
        <div className="search-result-card__meta">
          <span>{props.row.source}</span>
          <span>{props.row.gps}</span>
          <span>{`Confidence ${confidenceLabel(props.row.conf)}`}</span>
        </div>
        {props.followUp || props.assignment ? (
          <div className="search-result-card__workflow">
            {props.followUp ? (
              <span>
                {props.followUp.summary ?? `Follow-up ${titleCase(props.followUp.status)}`}
                {props.followUp.due_at_utc ? ` - Due ${formatDateTime(props.followUp.due_at_utc)}` : ""}
              </span>
            ) : null}
            {props.assignment ? (
              <span>
                {props.assignment.summary ?? `Dispatch ${titleCase(props.assignment.status)}`}
                {props.assignment.assigned_unit_label ? ` - ${props.assignment.assigned_unit_label}` : ""}
                {props.assignment.destination_label ? ` to ${props.assignment.destination_label}` : ""}
              </span>
            ) : null}
          </div>
        ) : null}
        {props.row.alertNotes ? (
          <div className="search-result-card__workflow">
            <span>{props.row.alertNotes}</span>
          </div>
        ) : null}
        <div className="search-result-card__actions">
          <button className="link-button" type="button" onClick={props.onDetails}>
            Evidence
          </button>
          <button className="link-button" type="button" onClick={props.onMap}>
            Last Seen
          </button>
          <button className="link-button" type="button" onClick={props.onAddToHotlist}>
            Recovery Account
          </button>
          <button className="link-button" type="button" onClick={() => void props.onCopy(props.row.plate1)}>
            Copy Tag
          </button>
        </div>
      </div>
    </article>
  );
}

function StatusRow(props: { label: string; value: string; tone: "good" | "off" }): ReactElement {
  return (
    <div className="status-row">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      <i className={`status-dot status-dot--${props.tone}`} />
    </div>
  );
}

function SettingsToggleRow(props: {
  title: string;
  detail: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}): ReactElement {
  return (
    <div className="settings-row">
      <div>
        <strong>{props.title}</strong>
        <span>{props.detail}</span>
      </div>
      <Toggle checked={props.checked} label={props.title} onChange={props.onChange} />
    </div>
  );
}

function SettingsRangeRow(props: {
  title: string;
  detail: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
}): ReactElement {
  return (
    <div className="settings-row settings-row--stacked">
      <div className="settings-row__copy">
        <strong>{props.title}</strong>
        <span>{props.detail}</span>
      </div>
      <input
        max={props.max}
        min={props.min}
        step={props.step}
        type="range"
        value={props.value}
        onChange={(event) => props.onChange(Number(event.target.value))}
      />
    </div>
  );
}

function SettingsSelectRow(props: {
  title: string;
  detail: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}): ReactElement {
  return (
    <div className="settings-row">
      <div>
        <strong>{props.title}</strong>
        <span>{props.detail}</span>
      </div>
      <select className="select-input" value={props.value} onChange={(event) => props.onChange(event.target.value)}>
        {props.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

function ReadOnlyRow(props: { title: string; detail: string; value: string }): ReactElement {
  return (
    <div className="settings-row">
      <div>
        <strong>{props.title}</strong>
        <span>{props.detail}</span>
      </div>
      <span className="read-only-value">{props.value}</span>
    </div>
  );
}

function DetailField(props: { label: string; value: string; tone?: "critical" | "cyan" }): ReactElement {
  return (
    <div className="detail-field">
      <span>{props.label}</span>
      <strong className={props.tone ? `detail-field__value detail-field__value--${props.tone}` : "detail-field__value"}>{props.value}</strong>
    </div>
  );
}

function NavPanel(props: {
  activeScreen: AppScreen;
  activeAlerts: number;
  activeHotlists: number;
  dataSource: DataSource;
  destinationInput: string;
  navigationActive: boolean;
  onDestinationChange: (value: string) => void;
  onOpenAlert: () => void;
  onResolve: () => void;
  onScreenChange: (screen: AppScreen) => void;
  onToggleNavigation: () => void;
  routeDistance: string;
  routeEta: string;
  routeStatusLabel: string;
  settings: UiSettings;
  systemDetectionCount: number;
  totalReads: number;
  withinRadius: boolean;
  distanceFeet: number;
  onDistanceChange: (value: number) => void;
}): ReactElement {
  return (
    <aside className="nav-panel">
      <div className="brand-card">
        <div className="brand-mark">SIF</div>
        <div>
          <p className="eyebrow">Seen-It-First</p>
          <h2>RepoScan Pro</h2>
          <p className="brand-copy">Recovery operations console</p>
        </div>
      </div>

      <div className="nav-tabs">
        {[
          { id: "console", label: "Dashboard", count: null },
          { id: "search", label: "Investigation", count: null },
          { id: "hotlists", label: "Recovery", count: props.activeAlerts > 0 ? props.activeAlerts : null },
          { id: "settings", label: "Settings", count: null },
        ].map((item) => (
          <button
            key={item.id}
            className={`nav-tab ${props.activeScreen === item.id ? "is-active" : ""}`}
            type="button"
            onClick={() => props.onScreenChange(item.id as AppScreen)}
          >
            <span className="nav-tab__label">{item.label}</span>
            {typeof item.count === "number" ? <span className="nav-tab__count">{item.count}</span> : null}
          </button>
        ))}
      </div>

      <div className="nav-action-row">
        <button className="nav-action nav-action--primary" disabled={props.activeAlerts === 0} type="button" onClick={props.onOpenAlert}>
          <span>Active Alerts</span>
          <span className="nav-action__count">{props.activeAlerts}</span>
        </button>
      </div>

      <div className="nav-compact-summary" aria-label="Compact route summary">
        <div className="nav-compact-chip">
          <span>Status</span>
          <strong>{props.routeStatusLabel}</strong>
        </div>
        <div className="nav-compact-chip">
          <span>Reads</span>
          <strong>{props.totalReads}</strong>
        </div>
        <div className="nav-compact-chip">
          <span>ETA</span>
          <strong>{props.routeEta}</strong>
        </div>
        <div className="nav-compact-chip">
          <span>Radius</span>
          <strong>{props.settings.arrivalRadiusFeet} ft</strong>
        </div>
      </div>

      <div className="panel-card">
        <div className="panel-card__header">
          <h3>System</h3>
          <Badge tone={props.dataSource === "live" ? "success" : "warn"}>{props.dataSource.toUpperCase()}</Badge>
        </div>
        <div className="status-list">
          <StatusRow label="GPS" value="Locked" tone="good" />
          <StatusRow label="Network" value={props.dataSource === "live" ? "Connected" : "Local cache"} tone={statusTone(props.dataSource === "live")} />
          <StatusRow label="LPR" value={props.settings.arrivalScanEnabled ? "Active" : "Paused"} tone={statusTone(props.settings.arrivalScanEnabled)} />
          <StatusRow label="Detections" value={`${props.systemDetectionCount}`} tone="good" />
        </div>
      </div>

      <div className="panel-card">
        <div className="panel-card__header">
          <h3>Destination</h3>
          <Badge tone={props.withinRadius ? "success" : props.navigationActive ? "cyan" : "muted"}>{props.routeStatusLabel}</Badge>
        </div>
        <label className="field-label" htmlFor="destination-input">
          Target address
        </label>
        <input
          id="destination-input"
          className="text-input"
          placeholder="4128 W Fulton St, Chicago, IL"
          type="text"
          value={props.destinationInput}
          onChange={(event) => props.onDestinationChange(event.target.value)}
        />
        <div className="range-row">
          <div>
            <strong>Distance to target</strong>
            <span>{props.routeDistance}</span>
          </div>
          <input
            max="5280"
            min="0"
            type="range"
            value={props.distanceFeet}
            onChange={(event) => props.onDistanceChange(Number(event.target.value))}
          />
        </div>
        <div className="button-row">
          <button className="btn btn--ghost" type="button" onClick={props.onResolve}>
            Resolve
          </button>
          <button className={`btn ${props.navigationActive ? "btn--danger" : "btn--primary"}`} type="button" onClick={props.onToggleNavigation}>
            {props.navigationActive ? "End Route" : "Start Nav"}
          </button>
        </div>
        <div className="target-summary">
          <div>
            <span>ETA</span>
            <strong>{props.routeEta}</strong>
          </div>
          <div>
            <span>Radius</span>
            <strong>{props.settings.arrivalRadiusFeet} ft</strong>
          </div>
          <div>
            <span>Scan</span>
            <strong>{props.settings.arrivalScanEnabled ? "ON" : "OFF"}</strong>
          </div>
        </div>
      </div>
    </aside>
  );
}

function ConsoleScreen(props: {
  activeAlerts: number;
  allRows: ConsoleDetectionRow[];
  cameraFeedsList: CameraUiFeed[];
  cameraFocusRow: ConsoleDetectionRow | null;
  consoleLayoutMode: ConsoleLayoutMode;
  currentCamera: CameraUiFeed | undefined;
  dataSource: DataSource;
  secondaryCamera: CameraUiFeed | undefined;
  secondaryCameraFocusRow: ConsoleDetectionRow | null;
  selectedCameraId: string;
  selectedDetectionId: string | null;
  settings: UiSettings;
  stageView: StageView;
  unitPosition: { lat: number; lng: number };
  routePath: [number, number][];
  withinRadius: boolean;
  onOpenDetail: (row: ConsoleDetectionRow) => void;
  onConsoleLayoutChange: (mode: ConsoleLayoutMode) => void;
  onSelectCamera: (cameraId: string) => void;
  onSelectDetection: (rowId: string) => void;
  onStageViewChange: (view: StageView) => void;
}): ReactElement {
  return (
    <section className="screen">
      <div className={`console-layout ${props.consoleLayoutMode === "overview" ? "console-layout--overview" : "console-layout--focus"}`}>
        <section className="stage-card">
          <div className="stage-toolbar">
            <div className="camera-tab-strip">
              {props.cameraFeedsList.map((feed) => (
                <button
                  key={feed.id}
                  className={`camera-tab ${props.selectedCameraId === feed.id ? "is-active" : ""}`}
                  type="button"
                  onClick={() => props.onSelectCamera(feed.id)}
                >
                  <span className={`camera-dot camera-dot--${feed.status === "Online" ? "live" : "off"}`} />
                  {feed.shortLabel}
                </button>
              ))}
            </div>
            <div className="stage-toolbar__right">
              <button
                className={`pill-button ${props.consoleLayoutMode === "overview" ? "is-active" : ""}`}
                type="button"
                onClick={() => props.onConsoleLayoutChange("overview")}
              >
                Overview
              </button>
              <button
                className={`pill-button ${props.consoleLayoutMode === "focus" ? "is-active" : ""}`}
                type="button"
                onClick={() => props.onConsoleLayoutChange("focus")}
              >
                Focus
              </button>
              {props.consoleLayoutMode === "focus" ? (
                <>
                  <button className={`pill-button ${props.stageView === "camera" ? "is-active" : ""}`} type="button" onClick={() => props.onStageViewChange("camera")}>
                    Camera
                  </button>
                  <button className={`pill-button ${props.stageView === "map" ? "is-active" : ""}`} type="button" onClick={() => props.onStageViewChange("map")}>
                    Map
                  </button>
                </>
              ) : null}
              <Badge tone={props.currentCamera?.status === "Online" ? "success" : "muted"}>{props.currentCamera?.status === "Online" ? "SCANNING" : "OFFLINE"}</Badge>
            </div>
          </div>

          <div className="stage-surface">
            {props.consoleLayoutMode === "overview" ? (
              <div className="console-overview-grid">
                <article className="console-overview-card console-overview-card--primary">
                  <CameraViewport cameraId={props.selectedCameraId} row={props.cameraFocusRow} dataSource={props.dataSource} compact />
                </article>

                <article className="console-overview-card console-overview-card--secondary">
                  <CameraViewport
                    cameraId={props.secondaryCamera?.id ?? props.selectedCameraId}
                    row={props.secondaryCameraFocusRow}
                    dataSource={props.dataSource}
                    compact
                  />
                </article>

                <article className="console-overview-card console-overview-card--map">
                  <div className="map-stage map-stage--overview">
                    <OpsMap
                      unitPosition={props.unitPosition}
                      routePath={props.routePath}
                      rows={props.allRows.slice(0, 8)}
                      radiusFeet={props.settings.arrivalRadiusFeet}
                      showRadiusRing={props.settings.showRadiusRing}
                      selectedRowId={props.selectedDetectionId}
                      onSelect={props.onSelectDetection}
                    />
                    <div className="map-stage__badge">{props.withinRadius ? "IN RADIUS" : "EN ROUTE"}</div>
                  </div>
                </article>
              </div>
            ) : props.stageView === "camera" ? (
              <CameraViewport cameraId={props.selectedCameraId} row={props.cameraFocusRow} dataSource={props.dataSource} />
            ) : (
              <div className="map-stage">
                <OpsMap
                  unitPosition={props.unitPosition}
                  routePath={props.routePath}
                  rows={props.allRows.slice(0, 8)}
                  radiusFeet={props.settings.arrivalRadiusFeet}
                  showRadiusRing={props.settings.showRadiusRing}
                  selectedRowId={props.selectedDetectionId}
                  onSelect={props.onSelectDetection}
                />
                <div className="map-stage__badge">{props.withinRadius ? "IN RADIUS" : "EN ROUTE"}</div>
              </div>
            )}
          </div>
        </section>

        <section className="table-card">
          <div className="table-card__header">
            <div className="table-card__title-row">
              <h3>Live Reads</h3>
              <span className="table-card__count">{props.allRows.length}</span>
            </div>
            <div className="table-card__meta">
              {props.activeAlerts > 0 ? <Badge tone="critical">{`${props.activeAlerts} alert${props.activeAlerts === 1 ? "" : "s"}`}</Badge> : null}
            </div>
          </div>
          <div className="table-scroll">
            <table className="detection-table">
              <thead>
                <tr>
                  <th>Evidence</th>
                  <th>Plate</th>
                  <th>Alt</th>
                  <th>Cam</th>
                  <th>Conf</th>
                  <th>Time</th>
                  <th>Case</th>
                </tr>
              </thead>
              <tbody>
                {props.allRows.map((row) => (
                  <tr
                    key={row.id}
                    className={`${props.selectedDetectionId === row.id ? "is-selected" : ""} ${row.hotlist ? "is-hotlist" : ""}`}
                    onClick={() => props.onSelectDetection(row.id)}
                  >
                    <td>
                      <button className="thumb-cell" type="button" onClick={() => props.onOpenDetail(row)}>
                        {row.hotlist ? <span className="thumb-cell__alert-dot" /> : null}
                        <span>{row.camera}</span>
                      </button>
                    </td>
                    <td className="plate-cell">{row.plate1}</td>
                    <td className="muted-cell">{row.plate2}</td>
                    <td>{row.camera}</td>
                    <td><span className={`conf-inline conf-inline--${confidenceTone(row.conf)}`}>{confidenceLabel(row.conf)}</span></td>
                    <td>{row.time}</td>
                    <td className={`sync-cell sync-cell--${readStatusTone(row)}`}>{readStatusLabel(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </section>
  );
}

function SearchScreen(props: {
  assignments: DispatchAssignmentRecord[];
  dataSource: DataSource;
  expandedGroups: Record<string, boolean>;
  followUps: FollowUpRecord[];
  groupedResults: PlateGroup[];
  hotlists: DashboardHotlist[];
  loading: boolean;
  query: string;
  results: ConsoleDetectionRow[];
  resultsTotal: number;
  searchError: string | null;
  searchExecuted: boolean;
  searchFromLocal: string;
  searchGroupByPlate: boolean;
  searchHighConfidenceOnly: boolean;
  searchHotlistOnly: boolean;
  searchMaxLatitude: string;
  searchMaxLongitude: string;
  searchMessage: string | null;
  searchMinLatitude: string;
  searchMinLongitude: string;
  searchMode: SearchMode;
  searchAlertStatus: DashboardAlertStatus | "";
  searchToLocal: string;
  searchVehicleColor: string;
  searchVehicleMake: string;
  searchVehicleModel: string;
  searchVehicleYear: string;
  searchCurrentCameraOnly: boolean;
  searchCurrentShiftOnly: boolean;
  onAddToHotlist: (row: ConsoleDetectionRow) => void;
  onClearFilters: () => void;
  onCopyPlate: (plate: string) => Promise<void>;
  onDetails: (row: ConsoleDetectionRow) => void;
  onMap: (row: ConsoleDetectionRow) => void;
  onSearchSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onToggleExpanded: (plate: string) => void;
  setQuery: (value: string) => void;
  setSearchFromLocal: (value: string) => void;
  setSearchGroupByPlate: (value: boolean) => void;
  setSearchHighConfidenceOnly: (value: boolean) => void;
  setSearchHotlistOnly: (value: boolean) => void;
  setSearchMaxLatitude: (value: string) => void;
  setSearchMaxLongitude: (value: string) => void;
  setSearchMinLatitude: (value: string) => void;
  setSearchMinLongitude: (value: string) => void;
  setSearchMode: (mode: SearchMode) => void;
  setSearchAlertStatus: (value: DashboardAlertStatus | "") => void;
  setSearchToLocal: (value: string) => void;
  setSearchVehicleColor: (value: string) => void;
  setSearchVehicleMake: (value: string) => void;
  setSearchVehicleModel: (value: string) => void;
  setSearchVehicleYear: (value: string) => void;
  setSearchCurrentCameraOnly: (value: boolean) => void;
  setSearchCurrentShiftOnly: (value: boolean) => void;
}): ReactElement {
  const hotlistMatches = props.results.filter((row) => row.hotlist).length;
  const latestResult = props.results[0] ?? null;
  const modeLabel =
    {
      plate: "Plate / Tag",
      camera: "Camera",
      vehicle: "Vehicle Profile",
      alert: "Recovery Alerts",
    }[props.searchMode] ?? titleCase(props.searchMode);
  const advancedFilterCount = [
    props.searchVehicleColor,
    props.searchVehicleMake,
    props.searchVehicleModel,
    props.searchVehicleYear,
    props.searchAlertStatus,
    props.searchMinLatitude,
    props.searchMaxLatitude,
    props.searchMinLongitude,
    props.searchMaxLongitude,
  ].filter((value) => value.trim().length > 0).length;

  return (
    <section className="screen search-screen">
      <ScreenHeader
        title="Vehicle Investigation"
        meta={
          <>
            <Badge tone={props.loading ? "warn" : "cyan"}>{props.loading ? "Searching" : "Ready"}</Badge>
            <Badge tone={props.dataSource === "live" ? "success" : "muted"}>{props.dataSource.toUpperCase()}</Badge>
          </>
        }
      />

      <div className="search-screen__layout">
        <form className="search-toolbar-card search-toolbar-card--sidebar" onSubmit={(event) => void props.onSearchSubmit(event)}>
          <div className="search-mode-tabs">
            {([
              { id: "plate" as const, label: "Plate / Tag" },
              { id: "camera" as const, label: "Camera" },
              { id: "vehicle" as const, label: "Vehicle Profile" },
              { id: "alert" as const, label: "Recovery Alerts" },
            ]).map((mode) => (
              <button key={mode.id} className={props.searchMode === mode.id ? "is-active" : ""} type="button" onClick={() => props.setSearchMode(mode.id)}>
                {mode.label}
              </button>
            ))}
          </div>

          <div className="search-input-row">
            <input
              className="text-input text-input--large"
              placeholder={
                props.searchMode === "plate"
                  ? "Plate or tag number (full or partial)"
                  : props.searchMode === "camera"
                    ? "Camera name or location"
                    : props.searchMode === "vehicle"
                      ? "Make, model, color, or year"
                      : "Recovery alert plate or case notes"
              }
              type="text"
              value={props.query}
              onChange={(event) => props.setQuery(event.target.value)}
            />
            <button className="btn btn--primary" disabled={props.loading} type="submit">
              {props.loading ? "Searching..." : "Search"}
            </button>
          </div>

          <div className="search-filter-grid">
            <label>
              <span>From</span>
              <input className="text-input" type="datetime-local" value={props.searchFromLocal} onChange={(event) => props.setSearchFromLocal(event.target.value)} />
            </label>
            <label>
              <span>To</span>
              <input className="text-input" type="datetime-local" value={props.searchToLocal} onChange={(event) => props.setSearchToLocal(event.target.value)} />
            </label>
          </div>

          <div className="search-sidebar-section">
            <div className="search-sidebar-section__header">
              <strong>Vehicle description</strong>
            </div>
            <div className="search-filter-grid">
              <label>
                <span>Color</span>
                <input className="text-input" type="text" value={props.searchVehicleColor} onChange={(event) => props.setSearchVehicleColor(event.target.value)} />
              </label>
              <label>
                <span>Make</span>
                <input className="text-input" type="text" value={props.searchVehicleMake} onChange={(event) => props.setSearchVehicleMake(event.target.value)} />
              </label>
              <label>
                <span>Model</span>
                <input className="text-input" type="text" value={props.searchVehicleModel} onChange={(event) => props.setSearchVehicleModel(event.target.value)} />
              </label>
              <label>
                <span>Year</span>
                <input className="text-input" type="text" value={props.searchVehicleYear} onChange={(event) => props.setSearchVehicleYear(event.target.value)} />
              </label>
            </div>
          </div>

          <div className="search-sidebar-section">
            <div className="search-sidebar-section__header">
              <strong>Recovery status</strong>
            </div>
            <label className="settings-input-row">
              <span>Status</span>
              <select className="select-input" value={props.searchAlertStatus} onChange={(event) => props.setSearchAlertStatus(event.target.value as DashboardAlertStatus | "")}>
                <option value="">Any alert state</option>
                <option value="active">Active</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="dismissed">Dismissed</option>
              </select>
            </label>
          </div>

          <div className="search-sidebar-section">
            <div className="search-sidebar-section__header">
              <strong>Location area</strong>
            </div>
            <div className="search-filter-grid">
              <label>
                <span>Min lat</span>
                <input className="text-input" type="number" step="0.00001" value={props.searchMinLatitude} onChange={(event) => props.setSearchMinLatitude(event.target.value)} />
              </label>
              <label>
                <span>Max lat</span>
                <input className="text-input" type="number" step="0.00001" value={props.searchMaxLatitude} onChange={(event) => props.setSearchMaxLatitude(event.target.value)} />
              </label>
              <label>
                <span>Min lon</span>
                <input className="text-input" type="number" step="0.00001" value={props.searchMinLongitude} onChange={(event) => props.setSearchMinLongitude(event.target.value)} />
              </label>
              <label>
                <span>Max lon</span>
                <input className="text-input" type="number" step="0.00001" value={props.searchMaxLongitude} onChange={(event) => props.setSearchMaxLongitude(event.target.value)} />
              </label>
            </div>
          </div>

          <div className="button-row">
            <button className="btn btn--ghost" type="button" onClick={props.onClearFilters}>
              Clear Filters
            </button>
          </div>

          <div className="chip-row">
            <button className={`chip ${props.searchHotlistOnly ? "is-active" : ""}`} type="button" onClick={() => props.setSearchHotlistOnly(!props.searchHotlistOnly)}>
              Recovery accounts only
            </button>
            <button className={`chip ${props.searchCurrentShiftOnly ? "is-active" : ""}`} type="button" onClick={() => props.setSearchCurrentShiftOnly(!props.searchCurrentShiftOnly)}>
              This shift
            </button>
            <button className={`chip ${props.searchCurrentCameraOnly ? "is-active" : ""}`} type="button" onClick={() => props.setSearchCurrentCameraOnly(!props.searchCurrentCameraOnly)}>
              Active camera
            </button>
            <button className={`chip ${props.searchHighConfidenceOnly ? "is-active" : ""}`} type="button" onClick={() => props.setSearchHighConfidenceOnly(!props.searchHighConfidenceOnly)}>
              High confidence
            </button>
            <button className={`chip ${props.searchGroupByPlate ? "is-active" : ""}`} type="button" onClick={() => props.setSearchGroupByPlate(!props.searchGroupByPlate)}>
              Group sightings
            </button>
          </div>
        </form>

        <div className="search-screen__content">
          <div className="search-summary-strip">
            <div className="search-summary-card">
              <span>Search</span>
              <strong>{modeLabel}</strong>
            </div>
            <div className="search-summary-card">
              <span>Sightings</span>
              <strong>{props.resultsTotal}</strong>
            </div>
            <div className="search-summary-card">
              <span>Recovery matches</span>
              <strong>{hotlistMatches}</strong>
            </div>
            <div className="search-summary-card">
              <span>Last seen</span>
              <strong>{latestResult ? formatDateTime(latestResult.timestampUtc) : "--"}</strong>
            </div>
          </div>

          <section className="results-panel">
            <div className="results-panel__header">
              <div>
                <h3>{props.searchExecuted ? `${props.resultsTotal} sighting${props.resultsTotal === 1 ? "" : "s"} found` : "Recent sightings"}</h3>
              </div>
              <div className="results-panel__feedback">
                {props.searchError ? <span className="feedback feedback--warn">{props.searchError}</span> : null}
                {props.searchMessage ? <span className="feedback feedback--good">{props.searchMessage}</span> : null}
              </div>
            </div>

            <div className="search-results">
              {props.results.length === 0 ? (
                <div className="empty-state">
                  <strong>No sightings matched.</strong>
                  <p>Widen the plate fragment, adjust the time window, or remove active filters.</p>
                </div>
              ) : props.searchGroupByPlate ? (
                props.groupedResults.map((group) => {
                  const expanded = props.expandedGroups[group.plate] ?? false;
                  const rows = expanded ? group.rows : group.rows.slice(0, 1);
                  const lead = group.rows[0];
                  const leadFollowUp = matchingFollowUpsForRow(lead, props.followUps)[0] ?? null;
                  const leadAssignment = matchingAssignmentsForRow(lead, props.assignments)[0] ?? null;
                  return (
                    <article key={group.plate} className="result-group-card">
                      <div className="result-group-card__header">
                        <div>
                          <strong>{group.plate}</strong>
                          <span>{`${lead.vehicle} - ${group.rows.length} sighting${group.rows.length === 1 ? "" : "s"}`}</span>
                        </div>
                        <div className="result-group-card__meta">
                          {lead.hotlist ? <Badge tone="critical">Recovery</Badge> : null}
                          {leadFollowUp ? <Badge tone={followUpStatusTone(leadFollowUp.status)}>{`Follow-up ${titleCase(leadFollowUp.status)}`}</Badge> : null}
                          {leadAssignment ? <Badge tone={dispatchStatusTone(leadAssignment.status)}>{`Dispatch ${titleCase(leadAssignment.status)}`}</Badge> : null}
                          <Badge tone="cyan">{`Last seen ${formatDateTime(lead.timestampUtc)}`}</Badge>
                          {group.rows.length > 1 ? (
                            <button className="link-button" type="button" onClick={() => props.onToggleExpanded(group.plate)}>
                              {expanded ? "Collapse" : `${group.rows.length} sightings`}
                            </button>
                          ) : null}
                        </div>
                      </div>
                      <div className="result-group-list">
                        {rows.map((row) => (
                          <SearchResultCard
                            assignment={matchingAssignmentsForRow(row, props.assignments)[0] ?? null}
                            key={row.id}
                            dataSource={props.dataSource}
                            followUp={matchingFollowUpsForRow(row, props.followUps)[0] ?? null}
                            row={row}
                            hotlistLabel={hotlistLabelForRow(row, props.hotlists)}
                            onAddToHotlist={() => props.onAddToHotlist(row)}
                            onCopy={props.onCopyPlate}
                            onDetails={() => props.onDetails(row)}
                            onMap={() => props.onMap(row)}
                          />
                        ))}
                      </div>
                    </article>
                  );
                })
              ) : (
                props.results.map((row) => (
                  <SearchResultCard
                    assignment={matchingAssignmentsForRow(row, props.assignments)[0] ?? null}
                    key={row.id}
                    dataSource={props.dataSource}
                    followUp={matchingFollowUpsForRow(row, props.followUps)[0] ?? null}
                    row={row}
                    hotlistLabel={hotlistLabelForRow(row, props.hotlists)}
                    onAddToHotlist={() => props.onAddToHotlist(row)}
                    onCopy={props.onCopyPlate}
                    onDetails={() => props.onDetails(row)}
                    onMap={() => props.onMap(row)}
                  />
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}

function HotlistsScreen(props: {
  activeAssignments: number;
  activeDestination: string;
  alertActionError: string | null;
  alertActionId: string | null;
  alertActionMessage: string | null;
  assignmentActionError: string | null;
  assignmentActionMessage: string | null;
  assignmentSaving: boolean;
  alerts: HotlistAlertItem[];
  canManageAccounts: boolean;
  canManageDispatch: boolean;
  canManageFollowUps: boolean;
  canUpdateAlerts: boolean;
  activity: RecognitionActivityItem[];
  activeTab: HotlistsWorkspaceTab;
  dataSource: DataSource;
  draft: HotlistDraft;
  error: string | null;
  followUps: FollowUpRecord[];
  followUpActionError: string | null;
  followUpActionMessage: string | null;
  followUpSaving: boolean;
  hotlists: DashboardHotlist[];
  assignments: DispatchAssignmentRecord[];
  message: string | null;
  openFollowUps: number;
  saving: boolean;
  deleting: boolean;
  selectedDetectionPlate: string;
  selectedHotlistId: string | null;
  selectedAlertId: string | null;
  alertResponseNotes: string;
  onAlertResponseNotesChange: (notes: string) => void;
  onAlertStatusChange: (alert: DashboardAlert, status: DashboardAlertStatus, responseNotes?: string) => void;
  onClearDraft: () => void;
  onDelete: () => void;
  onDraftChange: (draft: HotlistDraft | ((current: HotlistDraft) => HotlistDraft)) => void;
  onMapDetection: (detectionId: string | null | undefined) => void;
  onOpenRecord: (detectionId: string | null | undefined) => void;
  onSaveAssignment: (request: AssignmentSaveRequest) => Promise<void>;
  onSaveFollowUp: (request: FollowUpSaveRequest) => Promise<void>;
  onSelect: (entry: DashboardHotlist) => void;
  onSelectAlert: (alertId: string | null) => void;
  onSeedFromDetection: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onTabChange: (tab: HotlistsWorkspaceTab) => void;
}): ReactElement {
  const activeAlertCount = props.alerts.filter((item) => item.alert.status === "active").length;
  const acknowledgedAlertCount = props.alerts.filter((item) => item.alert.status === "acknowledged").length;
  const dismissedAlertCount = props.alerts.filter((item) => item.alert.status === "dismissed").length;
  const alertCases = props.alerts.map(({ alert, row }) => ({
    alert,
    row,
    entry:
      props.hotlists.find((entry) => entry.entry_id === alert.hotlist_entry_id) ??
      (row ? hotlistEntryForRow(row, props.hotlists) : null),
    followUps: props.followUps.filter(
      (item) =>
        item.alert_id === alert.alert_id ||
        (item.plate_text ? normalizePlate(item.plate_text) === normalizePlate(alert.matched_plate_text) : false),
    ),
    assignments: props.assignments.filter(
      (item) =>
        item.alert_id === alert.alert_id ||
        (item.plate_text ? normalizePlate(item.plate_text) === normalizePlate(alert.matched_plate_text) : false),
    ),
  }));
  const focusedAlertCase = alertCases.find((item) => item.alert.alert_id === props.selectedAlertId) ?? alertCases[0] ?? null;
  const [followUpDraft, setFollowUpDraft] = useState<FollowUpDraftState>(() => buildFollowUpDraft(null));
  const [assignmentDraft, setAssignmentDraft] = useState<AssignmentDraftState>(() => buildAssignmentDraft(null, props.activeDestination));

  useEffect(() => {
    if (!alertCases[0]) {
      if (props.selectedAlertId) {
        props.onSelectAlert(null);
      }
      return;
    }

    const stillExists = props.selectedAlertId ? alertCases.some((item) => item.alert.alert_id === props.selectedAlertId) : false;
    if (!stillExists) {
      props.onSelectAlert(alertCases[0].alert.alert_id);
    }
  }, [alertCases, props.onSelectAlert, props.selectedAlertId]);

  useEffect(() => {
    setFollowUpDraft(buildFollowUpDraft(focusedAlertCase?.followUps[0] ?? null));
    setAssignmentDraft(buildAssignmentDraft(focusedAlertCase?.assignments[0] ?? null, props.activeDestination));
  }, [
    focusedAlertCase?.alert.alert_id,
    focusedAlertCase?.followUps[0]?.updated_at_utc,
    focusedAlertCase?.assignments[0]?.updated_at_utc,
    props.activeDestination,
  ]);

  return (
    <section className="screen hotlists-screen">
      <ScreenHeader
        title="Recovery Queue"
        meta={
          <>
            <Badge tone="critical">{`${props.hotlists.filter((entry) => entry.active).length} armed`}</Badge>
            <Badge tone={activeAlertCount > 0 ? "warn" : "muted"}>{`${activeAlertCount} active`}</Badge>
            <Badge tone={props.dataSource === "live" ? "success" : "muted"}>{props.dataSource.toUpperCase()}</Badge>
          </>
        }
      />

      <div className="hotlists-summary-strip">
        <div className="search-summary-card">
          <span>Accounts armed</span>
          <strong>{props.hotlists.filter((entry) => entry.active).length}</strong>
        </div>
        <div className="search-summary-card">
          <span>Active cases</span>
          <strong>{activeAlertCount}</strong>
        </div>
        <div className="search-summary-card">
          <span>Pending follow-up</span>
          <strong>{props.openFollowUps}</strong>
        </div>
        <div className="search-summary-card">
          <span>Dispatched</span>
          <strong>{props.activeAssignments}</strong>
        </div>
      </div>

      <div className="segmented-control hotlists-toolbar-tabs">
        <button className={props.activeTab === "accounts" ? "is-active" : ""} type="button" onClick={() => props.onTabChange("accounts")}>
          {`Accounts (${props.hotlists.length})`}
        </button>
        <button className={props.activeTab === "alerts" ? "is-active" : ""} type="button" onClick={() => props.onTabChange("alerts")}>
          {`Case Queue (${props.alerts.length})`}
        </button>
        <button className={props.activeTab === "recognition" ? "is-active" : ""} type="button" onClick={() => props.onTabChange("recognition")}>
          {`Activity (${props.activity.length})`}
        </button>
      </div>

      {props.activeTab === "accounts" ? (
        <div className="hotlists-grid">
          <section className="panel-card hotlists-list-card">
            <div className="panel-card__header">
              <h3>Recovery Accounts</h3>
              <button className="btn btn--ghost" disabled={!props.canManageAccounts} type="button" onClick={props.onClearDraft}>
                New Account
              </button>
            </div>
            <div className="hotlist-list">
              {props.hotlists.length === 0 ? (
                <div className="empty-state">
                  <strong>No recovery accounts.</strong>
                  <p>Add a plate to begin tracking a repossession target.</p>
                </div>
              ) : (
                props.hotlists.map((entry) => (
                  <button
                    key={entry.entry_id}
                    className={`hotlist-row ${props.selectedHotlistId === entry.entry_id ? "is-selected" : ""}`}
                    type="button"
                    onClick={() => props.onSelect(entry)}
                  >
                    <div>
                      <strong>{entry.plate_text}</strong>
                      <span>{entry.label ?? "Unlabeled account"}</span>
                    </div>
                    <div className="hotlist-row__meta">
                      <Badge tone={entry.active ? "critical" : "muted"}>{entry.active ? "Armed" : "Paused"}</Badge>
                      <span>{formatDateTime(entry.updated_at_utc)}</span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="panel-card hotlist-editor-card">
            <div className="panel-card__header">
              <h3>{props.selectedHotlistId ? "Edit Account" : "Create Account"}</h3>
              <button className="btn btn--ghost" disabled={!props.canManageAccounts} type="button" onClick={props.onSeedFromDetection}>
                Use Current Plate
              </button>
            </div>
            <form className="hotlist-form" onSubmit={(event) => void props.onSubmit(event)}>
              <label>
                <span>Plate text</span>
                <input
                  className="text-input"
                  placeholder="8ABC123"
                  type="text"
                  value={props.draft.plateText}
                  onChange={(event) =>
                    props.onDraftChange((current) => ({
                      ...current,
                      plateText: normalizePlate(event.target.value),
                    }))
                  }
                />
              </label>

              <label>
                <span>Account / repo label</span>
                <input
                  className="text-input"
                  placeholder="Lender name, case ID, or repo priority"
                  type="text"
                  value={props.draft.label}
                  onChange={(event) =>
                    props.onDraftChange((current) => ({
                      ...current,
                      label: event.target.value,
                    }))
                  }
                />
              </label>

              <label>
                <span>Recovery instructions</span>
                <textarea
                  className="text-area"
                  placeholder="Tow instructions, debtor notes, parking pattern, or escalation steps"
                  value={props.draft.notes}
                  onChange={(event) =>
                    props.onDraftChange((current) => ({
                      ...current,
                      notes: event.target.value,
                    }))
                  }
                />
              </label>

              <div className="inline-setting">
                <div>
                  <strong>Account armed</strong>
                  <span>Triggers an alert when this plate is scanned.</span>
                </div>
                <Toggle
                  checked={props.draft.active}
                  label="Account armed"
                  onChange={(checked) =>
                    props.onDraftChange((current) => ({
                      ...current,
                      active: checked,
                    }))
                  }
                />
              </div>

              {props.error ? <div className="feedback feedback--error">{props.error}</div> : null}
              {props.message ? <div className="feedback feedback--good">{props.message}</div> : null}

              <div className="button-stack">
                <button className="btn btn--primary" disabled={!props.canManageAccounts || props.saving} type="submit">
                  {props.saving ? "Saving..." : props.selectedHotlistId ? "Save Account" : "Create Account"}
                </button>
                <button className="btn btn--ghost" disabled={!props.canManageAccounts} type="button" onClick={props.onClearDraft}>
                  Clear Draft
                </button>
                <button className="btn btn--ghost" disabled={!props.canManageAccounts} type="button" onClick={props.onSeedFromDetection}>
                  Seed {props.selectedDetectionPlate || "selection"}
                </button>
                <button className="btn btn--danger" disabled={!props.canManageAccounts || !props.selectedHotlistId || props.deleting} type="button" onClick={props.onDelete}>
                  {props.deleting ? "Deleting..." : "Delete Account"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {props.activeTab === "alerts" ? (
        <div className="recovery-queue-grid">
          <section className="panel-card hotlists-workspace-card hotlists-queue-card">
            <div className="panel-card__header">
              <div>
                <h3>Case Queue</h3>
              </div>
              <div className="record-row__stats">
                <Badge tone="critical">{`${activeAlertCount} active`}</Badge>
                <Badge tone="warn">{`${acknowledgedAlertCount} acknowledged`}</Badge>
                <Badge tone="muted">{`${dismissedAlertCount} dismissed`}</Badge>
              </div>
            </div>
            {props.alertActionError ? <div className="feedback feedback--error">{props.alertActionError}</div> : null}
            {props.alertActionMessage ? <div className="feedback feedback--good">{props.alertActionMessage}</div> : null}
            <div className="record-list">
              {alertCases.length === 0 ? (
                <div className="empty-state">
                  <strong>No active recovery cases.</strong>
                  <p>Scanned plates matching armed accounts will appear here.</p>
                </div>
              ) : (
                alertCases.map(({ alert, row, entry }) => {
                  const matchConfidence = confidenceLabel(confidencePercent(alert.match_confidence));
                  return (
                    <button
                      key={alert.alert_id}
                      className={`queue-row ${props.selectedAlertId === alert.alert_id ? "is-selected" : ""}`}
                      type="button"
                      onClick={() => props.onSelectAlert(alert.alert_id)}
                    >
                      <div className="queue-row__header">
                        <div>
                          <strong>{alert.matched_plate_text}</strong>
                          <span>{entry?.label ?? alert.hotlist_label ?? row?.vehicle ?? "Recovery case"}</span>
                        </div>
                        <div className="queue-row__badges">
                          <Badge tone={alertStatusTone(alert.status)}>{alertStatusLabel(alert.status)}</Badge>
                          <Badge tone={alert.match_type === "exact" ? "success" : "warn"}>{`${titleCase(alert.match_type)} match`}</Badge>
                          <Badge tone="cyan">{matchConfidence}</Badge>
                        </div>
                      </div>
                      <div className="queue-row__meta">
                        <span>{buildCameraDisplayName(alert.camera_id)}</span>
                        <span>{formatDateTime(alert.updated_at_utc ?? alert.timestamp_utc)}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>

          <section className="panel-card hotlists-workspace-card hotlists-case-card">
            {focusedAlertCase ? (
              <>
                <div className="panel-card__header">
                  <div>
                    <h3>{focusedAlertCase.alert.matched_plate_text}</h3>
                    <p>{focusedAlertCase.entry?.label ?? focusedAlertCase.alert.hotlist_label ?? focusedAlertCase.row?.vehicle ?? "Recovery case"}</p>
                  </div>
                  <div className="record-row__stats">
                    <Badge tone={alertStatusTone(focusedAlertCase.alert.status)}>{alertStatusLabel(focusedAlertCase.alert.status)}</Badge>
                    <Badge tone={focusedAlertCase.alert.match_type === "exact" ? "success" : "warn"}>{`${titleCase(focusedAlertCase.alert.match_type)} match`}</Badge>
                    <Badge tone="cyan">{confidenceLabel(confidencePercent(focusedAlertCase.alert.match_confidence))}</Badge>
                  </div>
                </div>

                <div className="detail-summary-strip detail-summary-strip--compact">
                  <div className="detail-summary-card">
                    <span>Last seen</span>
                    <strong>{formatDateTime(focusedAlertCase.alert.updated_at_utc ?? focusedAlertCase.alert.timestamp_utc)}</strong>
                  </div>
                  <div className="detail-summary-card">
                    <span>Camera</span>
                    <strong>{buildCameraDisplayName(focusedAlertCase.alert.camera_id)}</strong>
                  </div>
                  <div className="detail-summary-card">
                    <span>Follow-ups</span>
                    <strong>{focusedAlertCase.followUps.length}</strong>
                  </div>
                  <div className="detail-summary-card">
                    <span>Dispatch</span>
                    <strong>{focusedAlertCase.assignments.length}</strong>
                  </div>
                </div>

                <div className="case-note-stack">
                  <div className="detail-note-callout">
                    <strong>Repo instructions</strong>
                    <p>{focusedAlertCase.entry?.notes ?? focusedAlertCase.alert.notes ?? "No instructions on this account."}</p>
                  </div>
                  <div className="detail-note-callout">
                    <strong>Next action</strong>
                    <p>{alertResponseGuidance(focusedAlertCase.alert.status)}</p>
                  </div>
                  {focusedAlertCase.followUps[0] ? (
                    <div className="detail-note-callout">
                      <strong>{`Follow-up - ${titleCase(focusedAlertCase.followUps[0].status)}`}</strong>
                      <p>
                        {focusedAlertCase.followUps[0].summary ?? focusedAlertCase.followUps[0].notes ?? "Follow-up record exists for this case."}
                        {focusedAlertCase.followUps[0].due_at_utc ? ` Due ${formatDateTime(focusedAlertCase.followUps[0].due_at_utc)}.` : ""}
                      </p>
                    </div>
                  ) : null}
                  {focusedAlertCase.assignments[0] ? (
                    <div className="detail-note-callout">
                      <strong>{`Dispatch - ${titleCase(focusedAlertCase.assignments[0].status)}`}</strong>
                      <p>
                        {focusedAlertCase.assignments[0].summary ?? focusedAlertCase.assignments[0].notes ?? "Dispatch assignment exists for this case."}
                        {focusedAlertCase.assignments[0].destination_label ? ` Destination ${focusedAlertCase.assignments[0].destination_label}.` : ""}
                      </p>
                    </div>
                  ) : null}
                </div>

                <div className="detail-grid">
                  <DetailField label="Vehicle" value={focusedAlertCase.row?.vehicle ?? "Unclassified vehicle"} />
                  <DetailField label="GPS" value={focusedAlertCase.row?.gps ?? formatGpsValue(focusedAlertCase.alert.gps_latitude, focusedAlertCase.alert.gps_longitude)} />
                  <DetailField
                    label="Dispatch destination"
                    value={focusedAlertCase.assignments[0]?.destination_label ?? props.activeDestination}
                  />
                  <DetailField label="Permissions" value={`${props.canManageFollowUps ? "Follow-up" : "Read-only"} / ${props.canManageDispatch ? "Dispatch" : "Read-only"}`} />
                </div>

                <div className="form-row">
                  <label className="form-label" htmlFor="alert-response-notes">Response notes</label>
                  <textarea
                    className="form-input"
                    id="alert-response-notes"
                    placeholder="Optional notes for this status change…"
                    rows={2}
                    value={props.alertResponseNotes}
                    onChange={(e) => props.onAlertResponseNotesChange(e.target.value)}
                  />
                </div>

                <div className="record-row__actions record-row__actions--case">
                  {focusedAlertCase.alert.status !== "acknowledged" ? (
                    <button
                      className="btn btn--primary"
                      disabled={!props.canUpdateAlerts || props.alertActionId === focusedAlertCase.alert.alert_id}
                      type="button"
                      onClick={() => props.onAlertStatusChange(focusedAlertCase.alert, "acknowledged", props.alertResponseNotes || undefined)}
                    >
                      {props.alertActionId === focusedAlertCase.alert.alert_id ? "Updating..." : "Acknowledge"}
                    </button>
                  ) : null}
                  {focusedAlertCase.alert.status !== "dismissed" ? (
                    <button
                      className="btn btn--ghost"
                      disabled={!props.canUpdateAlerts || props.alertActionId === focusedAlertCase.alert.alert_id}
                      type="button"
                      onClick={() => props.onAlertStatusChange(focusedAlertCase.alert, "dismissed", props.alertResponseNotes || undefined)}
                    >
                      {props.alertActionId === focusedAlertCase.alert.alert_id ? "Updating..." : "Stand Down"}
                    </button>
                  ) : null}
                  {focusedAlertCase.alert.status !== "active" ? (
                    <button
                      className="btn btn--ghost"
                      disabled={!props.canUpdateAlerts || props.alertActionId === focusedAlertCase.alert.alert_id}
                      type="button"
                      onClick={() => props.onAlertStatusChange(focusedAlertCase.alert, "active", props.alertResponseNotes || undefined)}
                    >
                      {props.alertActionId === focusedAlertCase.alert.alert_id ? "Updating..." : "Reopen"}
                    </button>
                  ) : null}
                  <button className="btn btn--ghost" disabled={!focusedAlertCase.row} type="button" onClick={() => props.onOpenRecord(focusedAlertCase.alert.detection_id)}>
                    Evidence
                  </button>
                  <button className="btn btn--ghost" disabled={!focusedAlertCase.row} type="button" onClick={() => props.onMapDetection(focusedAlertCase.alert.detection_id)}>
                    Route to Vehicle
                  </button>
                </div>

                <div className="case-workflow-grid">
                  <section className="case-workflow-card">
                    <div className="panel-card__header">
                      <div>
                        <h3>Follow-up</h3>
                      </div>
                      <Badge tone={props.canManageFollowUps ? "success" : "muted"}>
                        {props.canManageFollowUps ? "Writable" : "Read only"}
                      </Badge>
                    </div>
                    {props.followUpActionError ? <div className="feedback feedback--error">{props.followUpActionError}</div> : null}
                    {props.followUpActionMessage ? <div className="feedback feedback--good">{props.followUpActionMessage}</div> : null}
                    <div className="case-editor-grid">
                      <label className="settings-input-row">
                        <span>Summary</span>
                        <input
                          className="text-input"
                          type="text"
                          value={followUpDraft.summary}
                          onChange={(event) => setFollowUpDraft((current) => ({ ...current, summary: event.target.value }))}
                        />
                      </label>
                      <div className="case-editor-grid case-editor-grid--split">
                        <label className="settings-input-row">
                          <span>Priority</span>
                          <select
                            className="select-input"
                            value={followUpDraft.priority}
                            onChange={(event) =>
                              setFollowUpDraft((current) => ({ ...current, priority: event.target.value as FollowUpPriority }))
                            }
                          >
                            <option value="routine">Routine</option>
                            <option value="priority">Priority</option>
                            <option value="critical">Critical</option>
                          </select>
                        </label>
                        <label className="settings-input-row">
                          <span>Status</span>
                          <select
                            className="select-input"
                            value={followUpDraft.status}
                            onChange={(event) =>
                              setFollowUpDraft((current) => ({ ...current, status: event.target.value as FollowUpStatus }))
                            }
                          >
                            <option value="open">Open</option>
                            <option value="monitoring">Monitoring</option>
                            <option value="resolved">Resolved</option>
                          </select>
                        </label>
                      </div>
                      <div className="case-editor-grid case-editor-grid--split">
                        <label className="settings-input-row">
                          <span>Assigned operator</span>
                          <input
                            className="text-input"
                            type="text"
                            value={followUpDraft.assignedOperatorId}
                            onChange={(event) => setFollowUpDraft((current) => ({ ...current, assignedOperatorId: event.target.value }))}
                          />
                        </label>
                        <label className="settings-input-row">
                          <span>Due</span>
                          <input
                            className="text-input"
                            type="datetime-local"
                            value={followUpDraft.dueAtLocal}
                            onChange={(event) => setFollowUpDraft((current) => ({ ...current, dueAtLocal: event.target.value }))}
                          />
                        </label>
                      </div>
                      <label className="settings-input-row">
                        <span>Notes</span>
                        <textarea
                          className="text-area text-area--compact"
                          value={followUpDraft.notes}
                          onChange={(event) => setFollowUpDraft((current) => ({ ...current, notes: event.target.value }))}
                        />
                      </label>
                    </div>
                    <div className="case-editor-actions">
                      <button
                        className="btn btn--primary"
                        disabled={!props.canManageFollowUps || props.followUpSaving || !focusedAlertCase.alert.detection_id}
                        type="button"
                        onClick={() =>
                          void props.onSaveFollowUp({
                            alertId: focusedAlertCase.alert.alert_id,
                            detectionId: focusedAlertCase.row?.detectionId ?? focusedAlertCase.alert.detection_id,
                            existing: focusedAlertCase.followUps[0] ?? null,
                            plateText: focusedAlertCase.alert.matched_plate_text,
                            draft: followUpDraft,
                          })
                        }
                      >
                        {props.followUpSaving ? "Saving..." : focusedAlertCase.followUps[0] ? "Update Follow-up" : "Create Follow-up"}
                      </button>
                    </div>
                  </section>

                  <section className="case-workflow-card">
                    <div className="panel-card__header">
                      <div>
                        <h3>Dispatch</h3>
                      </div>
                      <Badge tone={props.canManageDispatch ? "success" : "muted"}>
                        {props.canManageDispatch ? "Writable" : "Read only"}
                      </Badge>
                    </div>
                    {props.assignmentActionError ? <div className="feedback feedback--error">{props.assignmentActionError}</div> : null}
                    {props.assignmentActionMessage ? <div className="feedback feedback--good">{props.assignmentActionMessage}</div> : null}
                    <div className="case-editor-grid">
                      <label className="settings-input-row">
                        <span>Summary</span>
                        <input
                          className="text-input"
                          type="text"
                          value={assignmentDraft.summary}
                          onChange={(event) => setAssignmentDraft((current) => ({ ...current, summary: event.target.value }))}
                        />
                      </label>
                      <div className="case-editor-grid case-editor-grid--split">
                        <label className="settings-input-row">
                          <span>Priority</span>
                          <select
                            className="select-input"
                            value={assignmentDraft.priority}
                            onChange={(event) =>
                              setAssignmentDraft((current) => ({ ...current, priority: event.target.value as DispatchAssignmentPriority }))
                            }
                          >
                            <option value="watch">Watch</option>
                            <option value="priority">Priority</option>
                            <option value="critical">Critical</option>
                          </select>
                        </label>
                        <label className="settings-input-row">
                          <span>Status</span>
                          <select
                            className="select-input"
                            value={assignmentDraft.status}
                            onChange={(event) =>
                              setAssignmentDraft((current) => ({ ...current, status: event.target.value as DispatchAssignmentStatus }))
                            }
                          >
                            <option value="queued">Queued</option>
                            <option value="assigned">Assigned</option>
                            <option value="en_route">En route</option>
                            <option value="onsite">Onsite</option>
                            <option value="completed">Completed</option>
                            <option value="cancelled">Cancelled</option>
                          </select>
                        </label>
                      </div>
                      <div className="case-editor-grid case-editor-grid--split">
                        <label className="settings-input-row">
                          <span>Assigned operator</span>
                          <input
                            className="text-input"
                            type="text"
                            value={assignmentDraft.assignedOperatorId}
                            onChange={(event) => setAssignmentDraft((current) => ({ ...current, assignedOperatorId: event.target.value }))}
                          />
                        </label>
                        <label className="settings-input-row">
                          <span>Unit label</span>
                          <input
                            className="text-input"
                            type="text"
                            value={assignmentDraft.assignedUnitLabel}
                            onChange={(event) => setAssignmentDraft((current) => ({ ...current, assignedUnitLabel: event.target.value }))}
                          />
                        </label>
                      </div>
                      <label className="settings-input-row">
                        <span>Destination</span>
                        <input
                          className="text-input"
                          type="text"
                          value={assignmentDraft.destinationLabel}
                          onChange={(event) => setAssignmentDraft((current) => ({ ...current, destinationLabel: event.target.value }))}
                        />
                      </label>
                      <label className="settings-input-row">
                        <span>Notes</span>
                        <textarea
                          className="text-area text-area--compact"
                          value={assignmentDraft.notes}
                          onChange={(event) => setAssignmentDraft((current) => ({ ...current, notes: event.target.value }))}
                        />
                      </label>
                    </div>
                    <div className="case-editor-actions">
                      <button
                        className="btn btn--primary"
                        disabled={!props.canManageDispatch || props.assignmentSaving || !focusedAlertCase.alert.detection_id}
                        type="button"
                        onClick={() =>
                          void props.onSaveAssignment({
                            alertId: focusedAlertCase.alert.alert_id,
                            detectionId: focusedAlertCase.row?.detectionId ?? focusedAlertCase.alert.detection_id,
                            existing: focusedAlertCase.assignments[0] ?? null,
                            plateText: focusedAlertCase.alert.matched_plate_text,
                            draft: assignmentDraft,
                          })
                        }
                      >
                        {props.assignmentSaving ? "Saving..." : focusedAlertCase.assignments[0] ? "Update Dispatch" : "Create Dispatch"}
                      </button>
                    </div>
                  </section>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <strong>No case selected.</strong>
                <p>Select a recovery case from the queue or wait for a new plate match.</p>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {props.activeTab === "recognition" ? (
        <section className="panel-card hotlists-workspace-card">
          <div className="panel-card__header">
            <div>
              <h3>Scan Activity</h3>
            </div>
            <Badge tone="cyan">{`${props.activity.length} events`}</Badge>
          </div>
          <div className="record-list">
            {props.activity.length === 0 ? (
              <div className="empty-state">
                <strong>No scan activity.</strong>
                <p>LPR reads and recovery matches will appear here as they occur.</p>
              </div>
            ) : (
              props.activity.map(({ event, row }) => {
                const eventConfidence = confidenceLabel(confidencePercent(event.confidence));
                return (
                  <article key={event.event_id} className="record-row">
                    <div className="record-row__header">
                      <div className="record-row__title">
                        <strong>{event.plate_text ?? "Unread plate"}</strong>
                        <span>{buildRecognitionVehicleLabel(event)}</span>
                      </div>
                      <div className="record-row__stats">
                        <Badge tone={event.event_type === "hotlist" ? "critical" : "cyan"}>{event.event_type === "hotlist" ? "Recovery hit" : "LPR read"}</Badge>
                        <Badge tone="cyan">{eventConfidence}</Badge>
                      </div>
                    </div>
                    <div className="record-row__meta">
                      <span>{buildCameraDisplayName(event.camera_id)}</span>
                      <span>{row?.gps ?? formatGpsValue(event.gps_latitude, event.gps_longitude)}</span>
                      <span>{formatDateTime(event.timestamp_utc)}</span>
                    </div>
                    <p className="record-row__note">{event.note ?? "Scan event from live LPR feed."}</p>
                    <div className="record-row__actions">
                      <button className="link-button" disabled={!row} type="button" onClick={() => props.onOpenRecord(event.detection_id)}>
                        View Record
                      </button>
                      <button className="link-button" disabled={!row} type="button" onClick={() => props.onMapDetection(event.detection_id)}>
                        Map
                      </button>
                    </div>
                  </article>
                );
              })
            )}
          </div>
        </section>
      ) : null}
    </section>
  );
}

function SettingsScreen(props: {
  activeSessions: number;
  activeSessionRecords: OperatorSessionRecord[];
  auditError: string | null;
  auditEvents: ApiAuditEvent[];
  auditLoading: boolean;
  apiKeyInput: string;
  canManageAccounts: boolean;
  canManageDispatch: boolean;
  canManageFollowUps: boolean;
  canViewAudit: boolean;
  canUpdateAlerts: boolean;
  currentPrincipal: OperatorPrincipal | null;
  dataError: string | null;
  dataSource: DataSource;
  degradedDependencyCount: number;
  hotlistWarning: boolean;
  onSettingsSectionChange: (section: SettingsSection) => void;
  onApiKeyApply: () => void;
  onApiKeyChange: (value: string) => void;
  onRefresh: () => void;
  onlineCameras: number;
  settings: UiSettings;
  settingsSection: SettingsSection;
  serviceHealthState: string;
  totalCameras: number;
  updateSetting: <Key extends keyof UiSettings>(key: Key, value: UiSettings[Key]) => void;
}): ReactElement {
  const sections: Array<{ id: SettingsSection; title: string; description: string }> = [
    { id: "workspace", title: "Scan workflow", description: "Arrival scan, suppression, and confidence thresholds." },
    { id: "alerts", title: "Recovery alerts", description: "Alert behavior, audio, and permissions." },
    { id: "cameras", title: "Cameras", description: "Resolution, night mode, and feed controls." },
    { id: "map", title: "Map and geofence", description: "Radius, route display, and navigation." },
    { id: "system", title: "System and API", description: "Health, connection, sessions, and audit." },
  ];
  const activeSection = sections.find((section) => section.id === props.settingsSection) ?? sections[0];

  return (
    <section className="screen settings-screen">
      <ScreenHeader
        title="System Settings"
        meta={
          <>
            {props.hotlistWarning ? <Badge tone="warn">Review alert settings</Badge> : <Badge tone="success">Operational</Badge>}
            <Badge tone={props.dataSource === "live" ? "success" : "muted"}>{props.dataSource.toUpperCase()}</Badge>
            <Badge tone={props.degradedDependencyCount === 0 ? "success" : "warn"}>{props.degradedDependencyCount === 0 ? "HEALTHY" : `${props.degradedDependencyCount} WARNINGS`}</Badge>
          </>
        }
      />

      <div className="settings-summary-strip">
        <div className="settings-summary-tile">
          <span>Cameras</span>
          <strong>{`${props.onlineCameras}/${Math.max(props.totalCameras, 1)}`}</strong>
        </div>
        <div className="settings-summary-tile">
          <span>System</span>
          <strong>{titleCase(props.serviceHealthState)}</strong>
        </div>
        <div className="settings-summary-tile">
          <span>Alerts</span>
          <strong>{props.settings.hotlistAlerts ? "Armed" : "Off"}</strong>
        </div>
        <div className="settings-summary-tile">
          <span>Operators</span>
          <strong>{props.activeSessions}</strong>
        </div>
      </div>

      <div className="settings-workspace">
        <aside className="panel-card settings-nav-card">
          <div className="panel-card__header">
            <h3>Sections</h3>
            <Badge tone="cyan">{activeSection.title}</Badge>
          </div>
          <div className="settings-nav-list">
            {sections.map((section) => (
              <button
                key={section.id}
                className={`settings-nav-item ${props.settingsSection === section.id ? "is-active" : ""}`}
                type="button"
                onClick={() => props.onSettingsSectionChange(section.id)}
              >
                <strong>{section.title}</strong>
                <span>{section.description}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="settings-card settings-card--detail">
          <div className="settings-card__header">
            <div>
              <h3>{activeSection.title}</h3>
              <p>{activeSection.description}</p>
            </div>
            <div className="settings-capability-row">
              {props.settingsSection === "alerts" ? <Badge tone={props.canManageAccounts ? "success" : "muted"}>{props.canManageAccounts ? "Recovery write" : "Recovery read only"}</Badge> : null}
              {props.settingsSection === "alerts" ? <Badge tone={props.canUpdateAlerts ? "success" : "muted"}>{props.canUpdateAlerts ? "Alert updates" : "Alert read only"}</Badge> : null}
              {props.settingsSection === "cameras" ? <Badge tone={props.onlineCameras > 0 ? "success" : "muted"}>{`${props.onlineCameras}/${Math.max(props.totalCameras, 1)} feeds online`}</Badge> : null}
              {props.settingsSection === "system" ? <Badge tone={props.degradedDependencyCount === 0 ? "success" : "warn"}>{titleCase(props.serviceHealthState)}</Badge> : null}
            </div>
          </div>

          <div className="settings-detail-stack">
            {props.settingsSection === "workspace" ? (
              <>
                <SettingsToggleRow title="Auto-arm on arrival" detail="Start scanning when unit enters the geofence radius." checked={props.settings.autoArrivalScan} onChange={(checked) => props.updateSetting("autoArrivalScan", checked)} />
                <SettingsToggleRow title="Arrival scan active" detail="Master switch for address-proximity scanning." checked={props.settings.arrivalScanEnabled} onChange={(checked) => props.updateSetting("arrivalScanEnabled", checked)} />
                <SettingsRangeRow title="Duplicate suppression" detail={`${props.settings.duplicateSuppressionSeconds} sec`} min={15} max={300} step={15} value={props.settings.duplicateSuppressionSeconds} onChange={(value) => props.updateSetting("duplicateSuppressionSeconds", value)} />
                <SettingsRangeRow title="Min OCR confidence" detail={`${props.settings.minConfidence}%`} min={60} max={99} step={1} value={props.settings.minConfidence} onChange={(value) => props.updateSetting("minConfidence", value)} />
                <ReadOnlyRow title="Scan mode" value={props.settings.autoArrivalScan ? "Arrival assist" : "Manual"} detail="Based on auto-arm setting above." />
              </>
            ) : null}

            {props.settingsSection === "alerts" ? (
              <>
                <SettingsToggleRow title="Recovery alerts" detail="Show full-screen alert when a repo target is scanned." checked={props.settings.hotlistAlerts} onChange={(checked) => props.updateSetting("hotlistAlerts", checked)} />
                <SettingsToggleRow title="Audible alerts" detail="Play tone on recovery match." checked={props.settings.soundEnabled} onChange={(checked) => props.updateSetting("soundEnabled", checked)} />
                <SettingsToggleRow title="Vibration" detail="Haptic feedback for field devices." checked={props.settings.vibrationEnabled} onChange={(checked) => props.updateSetting("vibrationEnabled", checked)} />
                <SettingsRangeRow title="Alert volume" detail={`${props.settings.alertVolume}%`} min={0} max={100} step={5} value={props.settings.alertVolume} onChange={(value) => props.updateSetting("alertVolume", value)} />
                <SettingsSelectRow title="Banner persistence" detail="How long non-critical alerts stay visible." value={props.settings.alertPersistence} options={["until-dismissed", "15 sec", "60 sec"]} onChange={(value) => props.updateSetting("alertPersistence", value as AlertPersistence)} />
                <ReadOnlyRow title="Account management" value={props.canManageAccounts ? "Write access" : "Read only"} detail="Controls recovery account CRUD." />
                <ReadOnlyRow title="Alert management" value={props.canUpdateAlerts ? "Write access" : "Read only"} detail="Controls acknowledge / dismiss / reopen." />
              </>
            ) : null}

            {props.settingsSection === "cameras" ? (
              <>
                <SettingsSelectRow title="Resolution" detail="Frame capture size for evidence." value={props.settings.resolution} options={["1920x1080", "1600x900", "1280x720"]} onChange={(value) => props.updateSetting("resolution", value)} />
                <SettingsSelectRow title="Stream quality" detail="Balance between latency and image quality." value={props.settings.streamQuality} options={["High", "Balanced", "Low latency"]} onChange={(value) => props.updateSetting("streamQuality", value)} />
                <SettingsToggleRow title="Night mode" detail="Optimize for low-light plate reads." checked={props.settings.nightMode} onChange={(checked) => props.updateSetting("nightMode", checked)} />
                <SettingsToggleRow title="IR assist" detail="Enable infrared for stationary scans." checked={props.settings.irControl} onChange={(checked) => props.updateSetting("irControl", checked)} />
                <SettingsToggleRow title="Exposure lock" detail="Hold exposure steady against headlights." checked={props.settings.exposureLock} onChange={(checked) => props.updateSetting("exposureLock", checked)} />
                <ReadOnlyRow title="Active feeds" value={`${props.onlineCameras}/${Math.max(props.totalCameras, 1)}`} detail="Online camera count." />
              </>
            ) : null}

            {props.settingsSection === "map" ? (
              <>
                <SettingsRangeRow title="Arrival radius" detail={`${props.settings.arrivalRadiusFeet} ft`} min={100} max={1000} step={25} value={props.settings.arrivalRadiusFeet} onChange={(value) => props.updateSetting("arrivalRadiusFeet", value)} />
                <SettingsSelectRow title="Map style" detail="Route map visualization." value={props.settings.mapMode} options={["Dark route", "Street", "Satellite-style"]} onChange={(value) => props.updateSetting("mapMode", value)} />
                <SettingsToggleRow title="Auto-center" detail="Keep map centered on the unit." checked={props.settings.autoCenterVehicle} onChange={(checked) => props.updateSetting("autoCenterVehicle", checked)} />
                <SettingsToggleRow title="Geofence ring" detail="Show arrival radius on map." checked={props.settings.showRadiusRing} onChange={(checked) => props.updateSetting("showRadiusRing", checked)} />
                <SettingsToggleRow title="Traffic overlay" detail="Show route congestion data." checked={props.settings.showTraffic} onChange={(checked) => props.updateSetting("showTraffic", checked)} />
                <SettingsSelectRow title="Navigation" detail="Route to target method." value={props.settings.navProvider} options={["Internal", "External"]} onChange={(value) => props.updateSetting("navProvider", value)} />
              </>
            ) : null}

            {props.settingsSection === "system" ? (
              <>
                <ReadOnlyRow title="Health" value={titleCase(props.serviceHealthState)} detail={props.degradedDependencyCount === 0 ? "All systems normal." : `${props.degradedDependencyCount} warning${props.degradedDependencyCount === 1 ? "" : "s"}.`} />
                <ReadOnlyRow title="Data source" value={props.dataSource.toUpperCase()} detail={props.dataError ?? "Connected to live API."} />
                <ReadOnlyRow title="Sync" value={props.dataSource === "live" ? "Online" : "Offline queue"} detail={`${props.activeSessions} active session${props.activeSessions === 1 ? "" : "s"}.`} />
                <ReadOnlyRow
                  title="Operator"
                  value={props.currentPrincipal?.display_name ?? props.currentPrincipal?.principal_id ?? "Local operator"}
                  detail={
                    props.currentPrincipal
                      ? `${props.currentPrincipal.authenticated ? "Auth" : "Unauth"} - ${props.currentPrincipal.roles.map((role) => titleCase(role)).join(", ")}`
                      : "Local mode."
                  }
                />
                <ReadOnlyRow title="Follow-ups" value={props.canManageFollowUps ? "Write" : "Read only"} detail="Follow-up case management." />
                <ReadOnlyRow title="Dispatch" value={props.canManageDispatch ? "Write" : "Read only"} detail="Field dispatch assignments." />
                <ReadOnlyRow title="Export path" value="runtime/exports" detail="Evidence export directory." />
                <SettingsToggleRow title="Auto-delete captures" detail="Clean up temp files after sync." checked={props.settings.autoDeleteTempCaptures} onChange={(checked) => props.updateSetting("autoDeleteTempCaptures", checked)} />
                <label className="settings-input-row">
                  <span>API key</span>
                  <input className="text-input" type="password" value={props.apiKeyInput} onChange={(event) => props.onApiKeyChange(event.target.value)} />
                </label>
                <div className="button-row">
                  <button className="btn btn--primary" type="button" onClick={props.onApiKeyApply}>
                    Apply Key
                  </button>
                  <button className="btn btn--ghost" type="button" onClick={props.onRefresh}>
                    Refresh Live Data
                  </button>
                </div>
                <section className="settings-subsection">
                  <div className="panel-card__header">
                    <div>
                      <h3>Active sessions</h3>
                    </div>
                  </div>
                  <div className="settings-session-list">
                    {props.activeSessionRecords.length === 0 ? (
                      <div className="empty-state">
                        <strong>No active sessions.</strong>
                      </div>
                    ) : (
                      props.activeSessionRecords.map((session) => (
                        <div key={session.session_id} className="settings-session-row">
                          <div>
                            <strong>{session.display_name ?? session.principal_id}</strong>
                            <span>{`${titleCase(session.workspace)} workspace${session.navigation_active ? " - navigating" : ""}`}</span>
                          </div>
                          <div className="settings-session-row__meta">
                            <span>{session.client_label ?? "Local console"}</span>
                            <span>{formatDateTime(session.last_seen_at_utc)}</span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>
                <section className="settings-subsection">
                  <div className="panel-card__header">
                    <div>
                      <h3>Audit log</h3>
                    </div>
                    <Badge tone={props.canViewAudit ? "success" : "muted"}>{props.canViewAudit ? "Visible" : "Restricted"}</Badge>
                  </div>
                  {props.auditError ? <div className="feedback feedback--error">{props.auditError}</div> : null}
                  <div className="settings-session-list">
                    {!props.canViewAudit ? (
                      <div className="empty-state">
                        <strong>Audit access restricted.</strong>
                      </div>
                    ) : props.auditLoading ? (
                      <div className="empty-state">
                        <strong>Loading audit log...</strong>
                      </div>
                    ) : props.auditEvents.length === 0 ? (
                      <div className="empty-state">
                        <strong>No audit events.</strong>
                      </div>
                    ) : (
                      props.auditEvents.map((event) => (
                        <div key={event.event_id} className="settings-session-row">
                          <div>
                            <strong>{event.action}</strong>
                            <span>{`${titleCase(event.outcome)} - ${event.method} ${event.path}`}</span>
                            <span>{event.target_id ? `${event.target_type ?? "target"} ${event.target_id}` : event.request_id}</span>
                          </div>
                          <div className="settings-session-row__meta">
                            <span>{event.principal_id ?? "system"}</span>
                            <span>{formatDateTime(event.occurred_at_utc)}</span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>
              </>
            ) : null}
          </div>
        </section>
      </div>
    </section>
  );
}

function DetailOverlay(props: {
  activeDestination: string;
  assignments: DispatchAssignmentRecord[];
  canSubmitReview: boolean;
  currentOperatorId: string | null;
  dataSource: DataSource;
  detailImageUrl: string | null;
  detailReviews: ReviewRecord[];
  detailReviewsError: string | null;
  detailReviewsLoading: boolean;
  detailRow: ConsoleDetectionRow;
  detailTimeline: ConsoleDetectionRow[];
  followUps: FollowUpRecord[];
  hotlistEntry: DashboardHotlist | null;
  reviewError: string | null;
  reviewMessage: string | null;
  reviewSaving: boolean;
  onAddToHotlist: () => void;
  onClose: () => void;
  onCopyPlate: (plate: string) => Promise<void>;
  onOpenMap: () => void;
  onSubmitReview: (detectionId: string, action: ReviewAction, correctedPlate?: string, notes?: string) => Promise<void>;
}): ReactElement {
  const sightingCount = Math.max(props.detailTimeline.length, 1);
  const activeFollowUp = props.followUps[0] ?? null;
  const activeAssignment = props.assignments[0] ?? null;
  const plateCropUrl = useDetectionPlateCropImage(props.detailRow.detectionId, props.dataSource === "live");
  const [reviewAction, setReviewAction] = useState<ReviewAction>("confirm");
  const [reviewCorrectedPlate, setReviewCorrectedPlate] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");

  return (
    <div className="overlay-shell">
      <div className="overlay-scrim" onClick={props.onClose} />
      <aside className="detail-overlay">
        <div className="detail-overlay__header">
          <button className="link-button" type="button" onClick={props.onClose}>
            Close
          </button>
          <div>
            <h3>{props.detailRow.plate1}</h3>
            <span className="detail-overlay__vehicle">{props.detailRow.vehicle}</span>
          </div>
          {props.hotlistEntry?.label ? <Badge tone="warn">{props.hotlistEntry.label}</Badge> : null}
          {props.detailRow.hotlist ? <Badge tone="critical">Recovery</Badge> : null}
        </div>

        <div className="detail-overlay__body">
          <div className="detail-evidence-pair">
            <div className="detail-hero">
              {props.detailImageUrl ? <img alt={`${props.detailRow.plate1} frame`} src={props.detailImageUrl} /> : <div className="detail-hero__placeholder">{props.detailRow.vehicle}</div>}
              <span className="detail-evidence-label">Source frame</span>
            </div>
            <div className="detail-plate-crop">
              {plateCropUrl ? <img alt={`${props.detailRow.plate1} plate crop`} src={plateCropUrl} /> : <div className="detail-hero__placeholder">{props.detailRow.plate1}</div>}
              <span className="detail-evidence-label">Plate crop</span>
            </div>
          </div>

          {props.detailRow.plateCandidates.length > 0 ? (
            <section className="detail-section">
              <div className="detail-section__header">
                <div className="detail-section__copy">
                  <h4>OCR Reads</h4>
                </div>
              </div>
              <div className="ocr-candidates-list">
                {props.detailRow.plateCandidates.map((candidate, index) => (
                  <div key={`${candidate.text}-${index}`} className={`ocr-candidate-row ${index === 0 ? "ocr-candidate-row--primary" : ""}`}>
                    <strong>{candidate.text}</strong>
                    <span className={`conf-badge conf-badge--${confidenceTone(confidencePercent(candidate.confidence))}`}>{confidenceLabel(candidate.confidence)}</span>
                    {index === 0 ? <Badge tone="cyan">Promoted</Badge> : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <div className="detail-summary-strip">
            <div className="detail-summary-card">
              <span>Last seen</span>
              <strong>{formatDateTime(props.detailRow.timestampUtc)}</strong>
            </div>
            <div className="detail-summary-card">
              <span>Camera</span>
              <strong>{props.detailRow.source}</strong>
            </div>
            <div className="detail-summary-card">
              <span>Account state</span>
              <strong>{props.hotlistEntry ? "Assigned" : "Unassigned"}</strong>
            </div>
            <div className="detail-summary-card">
              <span>Sightings</span>
              <strong>{sightingCount}</strong>
            </div>
            <div className="detail-summary-card">
              <span>Follow-up</span>
              <strong>{activeFollowUp ? titleCase(activeFollowUp.status) : "None"}</strong>
            </div>
            <div className="detail-summary-card">
              <span>Dispatch</span>
              <strong>{activeAssignment ? titleCase(activeAssignment.status) : "None"}</strong>
            </div>
            <div className="detail-summary-card">
              <span>Alert match</span>
              <strong>{props.detailRow.alertMatchType ? `${titleCase(props.detailRow.alertMatchType)} match` : "No alert"}</strong>
            </div>
          </div>

          <section className="detail-section">
            <div className="detail-section__header">
              <div className="detail-section__copy">
                <h4>Repo Instructions</h4>
              </div>
            </div>
            <div className="detail-note-callout">
              <strong>{props.hotlistEntry?.label ?? "Unassigned vehicle"}</strong>
              <p>
                {props.hotlistEntry?.notes
                  ? props.hotlistEntry.notes
                  : `No recovery account for ${props.detailRow.plate1}. Add to recovery queue to begin tracking.`}
              </p>
            </div>
            {activeFollowUp ? (
              <div className="detail-note-callout">
                <strong>{`Follow-up - ${titleCase(activeFollowUp.status)}`}</strong>
                <p>
                  {activeFollowUp.summary ?? activeFollowUp.notes ?? "Follow-up record attached to this vehicle."}
                  {activeFollowUp.due_at_utc ? ` Due ${formatDateTime(activeFollowUp.due_at_utc)}.` : ""}
                </p>
              </div>
            ) : null}
            {activeAssignment ? (
              <div className="detail-note-callout">
                <strong>{`Dispatch - ${titleCase(activeAssignment.status)}`}</strong>
                <p>
                  {activeAssignment.summary ?? activeAssignment.notes ?? "Dispatch assignment attached to this vehicle."}
                  {activeAssignment.assigned_unit_label ? ` Unit ${activeAssignment.assigned_unit_label}.` : ""}
                  {activeAssignment.destination_label ? ` Destination ${activeAssignment.destination_label}.` : ""}
                </p>
              </div>
            ) : null}
          </section>

          <div className="detail-grid">
            <DetailField label="Plate" value={props.detailRow.plate1} tone={props.detailRow.hotlist ? "critical" : "cyan"} />
            <DetailField label="Vehicle" value={props.detailRow.vehicle} />
            <DetailField label="Confidence" value={confidenceLabel(props.detailRow.conf)} />
            <DetailField label="Camera" value={props.detailRow.source} />
            <DetailField label="GPS" value={props.detailRow.gps} />
            <DetailField label="Direction" value={`${props.detailRow.direction} / ${props.detailRow.lane}`} />
            <DetailField label="Dispatch destination" value={activeAssignment?.destination_label ?? props.activeDestination} />
            <DetailField label="Time" value={formatDateTime(props.detailRow.timestampUtc)} />
            <DetailField label="Sync" value={props.detailRow.syncStatus ?? "local"} />
            <DetailField label="Alert state" value={props.detailRow.alertStatus ? alertStatusLabel(props.detailRow.alertStatus) : "None"} />
            <DetailField label="Alt read" value={props.detailRow.plate2 || "--"} />
          </div>

          {props.detailReviewsLoading || props.detailReviews.length > 0 || props.detailReviewsError ? (
            <section className="detail-section">
              <div className="detail-section__header">
                <div className="detail-section__copy">
                  <h4>Review History</h4>
                </div>
              </div>
              {props.detailReviewsError ? <div className="feedback feedback--warn">{props.detailReviewsError}</div> : null}
              {props.detailReviewsLoading ? <div className="feedback">Loading review history...</div> : null}
              {props.detailReviews.length > 0 ? (
                <div className="review-history-list">
                  {props.detailReviews.map((review) => (
                    <div key={review.review_id} className="review-history-row">
                      <div className="review-history-row__header">
                        <strong>{titleCase(review.action)}</strong>
                        <span>{formatDateTime(review.reviewed_at_utc)}</span>
                      </div>
                      <div className="review-history-row__meta">
                        <span>{review.operator_id ?? props.currentOperatorId ?? "Unknown operator"}</span>
                        {review.corrected_plate_text ? <span>{`Corrected to ${review.corrected_plate_text}`}</span> : null}
                      </div>
                      {review.notes ? <p>{review.notes}</p> : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
          ) : null}

          {props.detailRow.detectionId ? (
            <section className="detail-section">
              <div className="detail-section__header">
                <div className="detail-section__copy">
                  <h4>OCR Review</h4>
                </div>
                <Badge tone={props.canSubmitReview ? "success" : "muted"}>{props.canSubmitReview ? "Writable" : "Read only"}</Badge>
              </div>
              {props.reviewError ? <div className="feedback feedback--error">{props.reviewError}</div> : null}
              {props.reviewMessage ? <div className="feedback feedback--good">{props.reviewMessage}</div> : null}
              <div className="review-form">
                <div className="review-form__row">
                  <label className="settings-input-row">
                    <span>Action</span>
                    <select
                      className="select-input"
                      value={reviewAction}
                      onChange={(event) => setReviewAction(event.target.value as ReviewAction)}
                    >
                      <option value="confirm">Confirm — plate read is correct</option>
                      <option value="correct">Correct — OCR needs editing</option>
                      <option value="flag">Flag — needs further review</option>
                      <option value="dismiss">Dismiss — false positive</option>
                    </select>
                  </label>
                </div>
                {reviewAction === "correct" ? (
                  <label className="settings-input-row">
                    <span>Corrected plate</span>
                    <input
                      className="text-input"
                      placeholder={props.detailRow.plate1}
                      type="text"
                      value={reviewCorrectedPlate}
                      onChange={(event) => setReviewCorrectedPlate(event.target.value.toUpperCase())}
                    />
                  </label>
                ) : null}
                <label className="settings-input-row">
                  <span>Notes</span>
                  <input
                    className="text-input"
                    placeholder="Optional operator notes"
                    type="text"
                    value={reviewNotes}
                    onChange={(event) => setReviewNotes(event.target.value)}
                  />
                </label>
                <button
                  className="btn btn--primary"
                  disabled={!props.canSubmitReview || props.reviewSaving || (reviewAction === "correct" && !reviewCorrectedPlate.trim())}
                  type="button"
                  onClick={() =>
                    void props.onSubmitReview(
                      props.detailRow.detectionId ?? "",
                      reviewAction,
                      reviewAction === "correct" ? reviewCorrectedPlate : undefined,
                      reviewNotes || undefined,
                    )
                  }
                >
                  {props.reviewSaving ? "Saving..." : "Submit Review"}
                </button>
              </div>
            </section>
          ) : null}

          <section className="detail-section">
            <div className="detail-section__header">
              <div className="detail-section__copy">
                <h4>Sighting History</h4>
              </div>
            </div>
            <div className="timeline-list">
              {props.detailTimeline.length > 0 ? (
                props.detailTimeline.map((row) => (
                  <div key={row.id} className="timeline-row">
                    <strong>{formatDateTime(row.timestampUtc)}</strong>
                    <span>{row.source}</span>
                    <span>{row.gps}</span>
                  </div>
                ))
              ) : (
                <p>No repeat sightings were grouped for this plate.</p>
              )}
            </div>
          </section>
        </div>

        <div className="detail-overlay__actions">
          <button className="btn btn--primary" type="button" onClick={props.onOpenMap}>
            Route to Vehicle
          </button>
          <button className="btn btn--ghost" type="button" onClick={props.onAddToHotlist}>
            Add to Recovery
          </button>
          <button className="btn btn--ghost" type="button" onClick={() => void props.onCopyPlate(props.detailRow.plate1)}>
            Copy Tag
          </button>
        </div>
      </aside>
    </div>
  );
}

function HotlistAlertOverlay(props: {
  activeDestination: string;
  assignment: DispatchAssignmentRecord | null;
  followUp: FollowUpRecord | null;
  hotlistAudioMuted: boolean;
  hotlistEntry: DashboardHotlist | null;
  hotlistRow: ConsoleDetectionRow;
  onDismiss: () => void;
  onMuteToggle: () => void;
  onNavigate: () => void;
  onRecover: () => void;
  onViewRecord: () => void;
}): ReactElement {
  return (
    <>
      <div className="hotlist-alert__scrim" onClick={props.onDismiss} />
      <div className="hotlist-alert">
      <div className="hotlist-alert__header">
        <div>
          <p className="eyebrow">Recovery Alert</p>
          <h2>Repo Target Located</h2>
        </div>
        <div className="hotlist-alert__header-right">
          <Badge tone="critical">{props.hotlistAudioMuted ? "Muted" : "Audio + visual"}</Badge>
          <button className="hotlist-alert__close" type="button" aria-label="Dismiss alert" onClick={props.onDismiss}>✕</button>
        </div>
      </div>

      <div className="hotlist-alert__hero">
        <div className="hotlist-alert__snapshot">{props.hotlistRow.vehicle}</div>
        <div className="hotlist-alert__identity">
          <strong>{props.hotlistRow.plate1}</strong>
          <span>{props.hotlistRow.vehicle}</span>
          {props.hotlistEntry?.label ? <Badge tone="warn">{props.hotlistEntry.label}</Badge> : null}
          <span>
            {props.hotlistRow.direction} | Conf {confidenceLabel(props.hotlistRow.conf)}
          </span>
        </div>
      </div>

      <div className="hotlist-alert__note">
        <strong>{props.hotlistEntry?.label ?? "Recovery account"}</strong>
        <p>{props.hotlistEntry?.notes ?? "Route to location, visually confirm the vehicle, and update the account after recovery."}</p>
      </div>

      {props.followUp || props.assignment ? (
        <div className="hotlist-alert__workflow">
          {props.followUp ? <Badge tone={followUpStatusTone(props.followUp.status)}>{`Follow-up ${titleCase(props.followUp.status)}`}</Badge> : null}
          {props.assignment ? <Badge tone={dispatchStatusTone(props.assignment.status)}>{`Dispatch ${titleCase(props.assignment.status)}`}</Badge> : null}
        </div>
      ) : null}

      <div className="hotlist-alert__grid">
        <DetailField label="Last seen" value={formatDateTime(props.hotlistRow.timestampUtc)} />
        <DetailField label="Camera" value={props.hotlistRow.source} />
        <DetailField label="GPS" value={props.hotlistRow.gps} />
        <DetailField label="Dispatch destination" value={props.assignment?.destination_label ?? props.activeDestination} />
      </div>

      <div className="hotlist-alert__actions">
        <button className="btn btn--primary" type="button" onClick={props.onNavigate}>
          Route to Vehicle
        </button>
        <button className="btn btn--ghost" type="button" onClick={props.onViewRecord}>
          Evidence
        </button>
        <button className="btn btn--ghost" type="button" onClick={props.onRecover}>
          Mark Recovered
        </button>
        <button className="btn btn--ghost" type="button" onClick={props.onMuteToggle}>
          {props.hotlistAudioMuted ? "Unmute" : "Mute"}
        </button>
        <button className="btn btn--danger" type="button" onClick={props.onDismiss}>
          Dismiss
        </button>
      </div>
    </div>
    </>
  );
}

export default App;
