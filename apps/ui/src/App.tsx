import { startTransition, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent, type ReactElement, type ReactNode } from "react";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { AddressIntelligenceCard } from "./components/dashboard/AddressIntelligenceCard";
import { CompactDetectionCard } from "./components/dashboard/CompactDetectionCard";
import { DetectionActionSheet, type DetectionActionSheetAction } from "./components/dashboard/DetectionActionSheet";
import { RecoveryStatePill } from "./components/dashboard/RecoveryStatePill";
import { ScanStateBanner } from "./components/dashboard/ScanStateBanner";
import { DashboardCustomizePanel } from "./components/dashboard/DashboardCustomizePanel";
import { DashboardShell } from "./components/dashboard/DashboardShell";
import { DashboardWidgetFrame } from "./components/dashboard/DashboardWidgetFrame";
import { InstrumentStatusBar } from "./components/dashboard/InstrumentStatusBar";
import { LprCameraPanel } from "./components/dashboard/LprCameraPanel";
import { RecentDetectionHistoryCard } from "./components/dashboard/RecentDetectionHistoryCard";
import { StatusPill, type StatusPillTone } from "./components/dashboard/StatusPill";
import { UconnectStyleToolbar, type ToolbarItem } from "./components/dashboard/UconnectStyleToolbar";
import { DetectionEvidenceHero } from "./components/detections/DetectionEvidenceHero";
import {
  loadDashboardConfig,
  reorderDashboardWidget,
  resetDashboardConfig,
  updateLayoutMode,
  updateWidgetSize,
  updateWidgetVisibility,
  type DashboardConfig,
  type DashboardLayoutMode,
  type DashboardWidgetId,
  type DashboardWidgetSize,
} from "./dashboard-config";
import { cameraFeeds, defaultFieldSettings } from "./demo-data";
import {
  fetchAuditEvents,
  createFollowUp,
  createHotlist,
  createReview,
  deleteHotlist,
  fetchDashboardOverview,
  fetchDetectionFrameObjectUrl,
  fetchDetectionPlateCropObjectUrl,
  fetchEdgeRuntimeStatus,
  fetchHotlists,
  fetchReviews,
  reverseAddressLookup,
  searchAlerts,
  searchAddresses,
  searchDetections,
  sendEdgeRuntimeCommand,
  sendOperatorSessionHeartbeat,
  setApiClientConfig,
  updateAlert,
  updateFollowUp,
  updateHotlist,
  type AlertSearchFilters,
  type ApiAuditEvent,
  type DashboardAlert,
  type DashboardAlertStatus,
  type DashboardCameraHealth,
  type DashboardDetection,
  type DashboardHotlist,
  type DashboardOverviewResponse,
  type DashboardPopupActivityEvent,
  type DetectionSearchFilters,
  type EdgeCaptureState,
  type EdgeRuntimeCommand,
  type EdgeRuntimeStatus,
  type FollowUpPriority,
  type FollowUpRecord,
  type FollowUpStatus,
  type HealthState,
  type OperatorPrincipal,
  type OperatorSessionRecord,
  type PlateCandidate,
  type ReverseAddressResult,
  type ReviewAction,
  type ReviewRecord,
  type ScanProcessingMode,
  type ScanSessionState,
} from "./live-api";
import { detectionSeverityForRow, detectionSeverityLabel } from "./presentation/detectionSeverity";

type AppScreen = "console" | "search" | "accounts" | "hotlists" | "settings";
type AppShell = "operations" | "admin";
type StageView = "camera" | "map";
type SearchMode = "plate" | "camera" | "vehicle" | "alert";
type DataSource = "demo" | "live" | "fallback";
type AlertPersistence = "until-dismissed" | "15 sec" | "60 sec";
type HotlistsWorkspaceTab = "alerts" | "recognition";
type SettingsSection = "workspace" | "alerts" | "cameras" | "map" | "system";
type ServiceHealthState = HealthState | "demo" | "offline";

function shellForScreen(screen: AppScreen): AppShell {
  switch (screen) {
    case "accounts":
    case "settings":
      return "admin";
    case "console":
    case "search":
    case "hotlists":
    default:
      return "operations";
  }
}

function resolveScanSessionState(params: {
  navigationActive: boolean;
  arrivalScanEnabled: boolean;
  withinRadius: boolean;
  activeRouteFeet: number | null;
}): { state: ScanSessionState; mode: ScanProcessingMode; lprRealtime: boolean } {
  if (params.navigationActive && params.withinRadius && params.arrivalScanEnabled) {
    return { state: "active_lpr_scan", mode: "realtime_lpr", lprRealtime: true };
  }
  if (params.navigationActive && params.activeRouteFeet !== null && !params.withinRadius) {
    return { state: "approaching_radius", mode: "standby", lprRealtime: false };
  }
  return { state: "idle", mode: "standby", lprRealtime: false };
}

function scanSessionLabel(state: ScanSessionState): string {
  switch (state) {
    case "active_lpr_scan":
      return "Live LPR";
    case "post_scan_vehicle_enrichment":
      return "Vehicle AI Queue";
    case "approaching_radius":
      return "Armed";
    case "completed":
      return "Complete";
    case "idle":
    default:
      return "Idle";
  }
}

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
  showActiveAlertPins: boolean;
  showHistoricalAlertPins: boolean;
  showDetectionPins: boolean;
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
  status: "Online" | "Offline" | "Unknown";
  fps: number | null;
  lastSeenAtUtc?: string | null;
}

interface DestinationCoords {
  lat: number;
  lng: number;
}

interface RecentDestination {
  id: string;
  address: string;
  label?: string;
  coords: DestinationCoords | null;
  lastUsedAtUtc: string;
}

type DestinationTargetSource = "recent" | "account" | "alert" | "read" | "manual";

interface DestinationTarget {
  id: string;
  source: DestinationTargetSource;
  address: string;
  label: string;
  subtitle?: string;
  coords: DestinationCoords | null;
  accent?: "critical" | "warn" | "success" | "cyan" | "muted";
  relativeTime?: string;
}

interface HotlistAlertItem {
  alert: DashboardAlert;
  row: ConsoleDetectionRow | null;
}

interface RecognitionActivityItem {
  event: DashboardPopupActivityEvent;
  row: ConsoleDetectionRow | null;
}

interface MapAlertMarker {
  id: string;
  alertId: string;
  plate: string;
  label: string;
  camera: string;
  lat: number;
  lng: number;
  status: DashboardAlertStatus;
  timestampUtc: string;
}

interface HotlistDraft {
  plateText: string;
  vin: string;
  vehicleYear: string;
  vehicleMake: string;
  vehicleModel: string;
  vehicleColor: string;
  addressLabel: string;
  addressLine1: string;
  addressLine2: string;
  addressCity: string;
  addressState: string;
  addressPostalCode: string;
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

interface FollowUpSaveRequest {
  alertId: string | null;
  detectionId: string;
  existing: FollowUpRecord | null;
  plateText: string;
  draft: FollowUpDraftState;
}

interface PlateGroup {
  plate: string;
  rows: ConsoleDetectionRow[];
}

interface SearchActivityPattern {
  detail: string;
  label: string;
  tone: "cyan" | "muted" | "success" | "warn";
}

interface SearchTimelineMarker {
  id: string;
  isLead: boolean;
  leftPercent: number;
  severity: ReturnType<typeof searchResultSeverity>;
  timestampLabel: string;
}

interface OperationalSignal {
  label: string;
  detail: string;
  tone: "critical" | "warn" | "success" | "muted" | "cyan";
}

interface NavigationGuidance {
  active: boolean;
  mode: "idle" | "preview" | "routing" | "arrival" | "blocked";
  primary: string;
  secondary: string;
  distanceToNext: string;
  distanceToDestination: string;
  eta: string;
  bearingLabel: string;
  progressPercent: number;
}

interface VerificationChecklistItem {
  label: string;
  detail: string;
  complete: boolean;
}

const uiSettingsStorageKey = "reposcan.ui.desktop-settings.v1";
const apiKeyStorageKey = "reposcan.ui.api-key.v2";
const targetAddressStorageKey = "reposcan.ui.target-address.v1";
const targetCoordsStorageKey = "reposcan.ui.target-coords.v1";
const recentDestinationsStorageKey = "reposcan.ui.recent-destinations.v1";
const recentDestinationsLimit = 6;
const sessionIdStorageKey = "reposcan.ui.session-id.v1";
const geocodeDebounceMs = 500;
const geocodeMinChars = 3;
const reverseGeocodeMinMoveFeet = 45;
const destinationLocalSuggestionMinChars = 2;

interface GeocodeSuggestion {
  id: string;
  displayName: string;
  lat: number;
  lng: number;
}

function useGeocodeSuggestions(
  query: string,
  biasCoords: DestinationCoords | null,
): { suggestions: GeocodeSuggestion[]; loading: boolean; error: string | null } {
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < geocodeMinChars) {
      setSuggestions([]);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    const timer = window.setTimeout(() => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      searchAddresses(trimmed, {
        signal: controller.signal,
        limit: 8,
        bias_latitude: biasCoords?.lat,
        bias_longitude: biasCoords?.lng,
      })
        .then((data) => {
          setSuggestions(
            data.results.map((item) => ({
              id: item.suggestion_id,
              displayName: item.display_name,
              lat: item.latitude,
              lng: item.longitude,
            })),
          );
          setLoading(false);
        })
        .catch((err) => {
          if ((err as DOMException)?.name !== "AbortError") {
            setSuggestions([]);
            setLoading(false);
            setError(err instanceof Error ? err.message : "Address search unavailable");
          }
        });
    }, geocodeDebounceMs);

    return () => {
      window.clearTimeout(timer);
      abortRef.current?.abort();
    };
  }, [biasCoords?.lat, biasCoords?.lng, query]);

  return { suggestions, loading, error };
}

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
  arrivalRadiusFeet: 50,
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
  showActiveAlertPins: true,
  showHistoricalAlertPins: true,
  showDetectionPins: true,
  navProvider: "Internal",
  showTraffic: defaultFieldSettings.routeTrafficOverlay,
};

const seedHotlists: DashboardHotlist[] = [
  {
    entry_id: "hl_demo_9kpn665",
    plate_text: "9KPN665",
    vin: null,
    vehicle_year: null,
    vehicle_make: null,
    vehicle_model: null,
    vehicle_color: null,
    address_label: "Fulton address",
    address_line1: "4128 W Fulton St",
    address_line2: null,
    address_city: "Chicago",
    address_state: "IL",
    address_postal_code: null,
    address_latitude: null,
    address_longitude: null,
    label: "Fulton tow-ready",
    notes: "Confirm the rear plate before engaging. Driver reported away from the vehicle.",
    active: true,
    created_at_utc: "2026-03-27T21:34:00Z",
    updated_at_utc: "2026-03-27T22:10:00Z",
  },
  {
    entry_id: "hl_demo_8abc123",
    plate_text: "8ABC123",
    vin: null,
    vehicle_year: null,
    vehicle_make: null,
    vehicle_model: null,
    vehicle_color: null,
    address_label: "Inbound approach watch",
    address_line1: null,
    address_line2: null,
    address_city: null,
    address_state: null,
    address_postal_code: null,
    address_latitude: null,
    address_longitude: null,
    label: "High-priority recovery",
    notes: "Escalate immediately if seen on any inbound approach camera.",
    active: true,
    created_at_utc: "2026-03-27T20:20:00Z",
    updated_at_utc: "2026-03-27T22:14:08Z",
  },
  {
    entry_id: "hl_demo_6ucj466",
    plate_text: "6UCJ466",
    vin: null,
    vehicle_year: null,
    vehicle_make: null,
    vehicle_model: null,
    vehicle_color: null,
    address_label: "Manual review",
    address_line1: null,
    address_line2: null,
    address_city: null,
    address_state: null,
    address_postal_code: null,
    address_latitude: null,
    address_longitude: null,
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

function loadStoredCoords(key: string): DestinationCoords | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DestinationCoords>;
    if (typeof parsed.lat === "number" && typeof parsed.lng === "number") {
      return { lat: parsed.lat, lng: parsed.lng };
    }
  } catch {
    return null;
  }
  return null;
}

function loadRecentDestinations(): RecentDestination[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(recentDestinationsStorageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as RecentDestination[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((entry): entry is RecentDestination =>
        typeof entry?.id === "string" && typeof entry.address === "string" && typeof entry.lastUsedAtUtc === "string",
      )
      .slice(0, recentDestinationsLimit);
  } catch {
    return [];
  }
}

function haversineFeet(a: DestinationCoords, b: DestinationCoords): number {
  const earthRadiusMeters = 6371000;
  const toRad = (value: number): number => (value * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  const meters = 2 * earthRadiusMeters * Math.asin(Math.min(1, Math.sqrt(h)));
  return Math.round(meters * 3.28084);
}

function bearingDegrees(a: DestinationCoords, b: DestinationCoords): number {
  const toRad = (value: number): number => (value * Math.PI) / 180;
  const toDeg = (value: number): number => (value * 180) / Math.PI;
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const dLng = toRad(b.lng - a.lng);
  const y = Math.sin(dLng) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

function bearingDeltaDegrees(from: number, to: number): number {
  return ((to - from + 540) % 360) - 180;
}

function bearingCardinalLabel(degrees: number): string {
  const labels = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"];
  return labels[Math.round(degrees / 45) % labels.length];
}

function guidanceVerb(delta: number): string {
  const abs = Math.abs(delta);
  if (abs < 22) return "Continue";
  if (abs < 65) return delta > 0 ? "Bear right" : "Bear left";
  if (abs < 135) return delta > 0 ? "Turn right" : "Turn left";
  return "Make a U-turn";
}

function formatMph(speedMetersPerSecond: number | null): string {
  if (speedMetersPerSecond == null || !Number.isFinite(speedMetersPerSecond) || speedMetersPerSecond < 0.25) return "0 mph";
  return `${Math.round(speedMetersPerSecond * 2.23694)} mph`;
}

function formatRelativeTime(timestampUtc: string, now: number = Date.now()): string {
  const ts = Date.parse(timestampUtc);
  if (Number.isNaN(ts)) return "";
  const diffSec = Math.round((now - ts) / 1000);
  if (diffSec < 45) return "just now";
  if (diffSec < 90) return "1 min ago";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hr ago`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 7) return `${diffDay} day${diffDay === 1 ? "" : "s"} ago`;
  return new Date(ts).toLocaleDateString();
}

type GpsFixStatus =
  | "unsupported"
  | "denied"
  | "error"
  | "acquiring"
  | "weak"
  | "fair"
  | "locked"
  | "stale";

interface GpsFixState {
  status: GpsFixStatus;
  lat: number | null;
  lng: number | null;
  accuracyMeters: number | null;
  headingDegrees: number | null;
  speedMetersPerSecond: number | null;
  lastFixAtMs: number | null;
  message: string | null;
}

const initialGpsFixState: GpsFixState = {
  status: "acquiring",
  lat: null,
  lng: null,
  accuracyMeters: null,
  headingDegrees: null,
  speedMetersPerSecond: null,
  lastFixAtMs: null,
  message: null,
};

function classifyGpsAccuracy(accuracyMeters: number): Extract<GpsFixStatus, "weak" | "fair" | "locked"> {
  if (accuracyMeters <= 15) return "locked";
  if (accuracyMeters <= 45) return "fair";
  return "weak";
}

function buildGpsIndicator(fix: GpsFixState): { value: string; tone: "good" | "off" | "warn"; tip: string } {
  switch (fix.status) {
    case "locked":
      return {
        value: "Locked",
        tone: "good",
        tip: `GPS locked (+/-${Math.round(fix.accuracyMeters ?? 0)} m) - click to open map settings`,
      };
    case "fair":
      return {
        value: "Fair",
        tone: "good",
        tip: `GPS fair (+/-${Math.round(fix.accuracyMeters ?? 0)} m) - click to open map settings`,
      };
    case "weak":
      return {
        value: "Weak",
        tone: "warn",
        tip: `GPS weak signal (+/-${Math.round(fix.accuracyMeters ?? 0)} m) - click to open map settings`,
      };
    case "stale":
      return { value: "Stale", tone: "warn", tip: "GPS fix stale - click to open map settings" };
    case "acquiring":
      return { value: "Acquiring", tone: "warn", tip: "Waiting for first GPS fix - click to open map settings" };
    case "denied":
      return { value: "Denied", tone: "off", tip: "Location permission denied - click to open map settings" };
    case "unsupported":
      return { value: "Unavail", tone: "off", tip: "Geolocation unsupported in this browser - click to open map settings" };
    case "error":
    default:
      return { value: "Error", tone: "off", tip: fix.message ?? "GPS error - click to open map settings" };
  }
}

function gpsFixToCoords(fix: GpsFixState): DestinationCoords | null {
  if (
    (fix.status === "locked" || fix.status === "fair" || fix.status === "weak" || fix.status === "stale") &&
    typeof fix.lat === "number" &&
    typeof fix.lng === "number"
  ) {
    return { lat: fix.lat, lng: fix.lng };
  }
  return null;
}

interface LiveAddressState {
  status: "idle" | "loading" | "resolved" | "error";
  address: ReverseAddressResult | null;
  error: string | null;
  requestedCoords: DestinationCoords | null;
}

function useLiveReverseAddress(coords: DestinationCoords | null): LiveAddressState {
  const [state, setState] = useState<LiveAddressState>({
    status: "idle",
    address: null,
    error: null,
    requestedCoords: null,
  });
  const lastRequestedRef = useRef<DestinationCoords | null>(null);

  useEffect(() => {
    if (!coords) {
      lastRequestedRef.current = null;
      setState((current) => ({ ...current, status: "idle", error: null, requestedCoords: null }));
      return;
    }

    const lastRequested = lastRequestedRef.current;
    if (lastRequested && haversineFeet(lastRequested, coords) < reverseGeocodeMinMoveFeet) {
      return;
    }

    const controller = new AbortController();
    const requestCoords = coords;
    lastRequestedRef.current = requestCoords;
    setState((current) => ({
      ...current,
      status: current.address ? "resolved" : "loading",
      error: null,
      requestedCoords: requestCoords,
    }));

    reverseAddressLookup(requestCoords.lat, requestCoords.lng, controller.signal)
      .then((address) => {
        setState({
          status: "resolved",
          address,
          error: null,
          requestedCoords: requestCoords,
        });
      })
      .catch((error) => {
        if ((error as DOMException)?.name === "AbortError") {
          return;
        }
        setState((current) => ({
          ...current,
          status: "error",
          error: error instanceof Error ? error.message : "Current address unavailable",
          requestedCoords: requestCoords,
        }));
      });

    return () => controller.abort();
  }, [coords?.lat, coords?.lng]);

  return state;
}

function useBrowserGeolocation(): GpsFixState {
  const [fix, setFix] = useState<GpsFixState>(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      return { ...initialGpsFixState, status: "unsupported", message: "Geolocation not supported" };
    }
    return initialGpsFixState;
  });

  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      return;
    }

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        const accuracyMeters = position.coords.accuracy ?? 9999;
        setFix({
          status: classifyGpsAccuracy(accuracyMeters),
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          accuracyMeters,
          headingDegrees: typeof position.coords.heading === "number" && Number.isFinite(position.coords.heading) ? position.coords.heading : null,
          speedMetersPerSecond: typeof position.coords.speed === "number" && Number.isFinite(position.coords.speed) ? position.coords.speed : null,
          lastFixAtMs: position.timestamp ?? Date.now(),
          message: null,
        });
      },
      (error) => {
        setFix((current) => ({
          ...current,
          status: error.code === error.PERMISSION_DENIED ? "denied" : "error",
          message: error.message || null,
        }));
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
    );

    const staleInterval = window.setInterval(() => {
      setFix((current) => {
        if (!current.lastFixAtMs) return current;
        if (current.status !== "locked" && current.status !== "fair" && current.status !== "weak") {
          return current;
        }
        if (Date.now() - current.lastFixAtMs > 12000) {
          return { ...current, status: "stale" };
        }
        return current;
      });
    }, 3000);

    return () => {
      navigator.geolocation.clearWatch(watchId);
      window.clearInterval(staleInterval);
    };
  }, []);

  return fix;
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

function buildNavigationGuidance(options: {
  active: boolean;
  destination: string;
  destinationCoords: DestinationCoords | null;
  routePath: [number, number][];
  unitPosition: DestinationCoords;
  gpsFix: GpsFixState;
  routeDistance: string;
  routeEta: string;
  routeFeet: number | null;
  arrivalRadiusFeet: number;
}): NavigationGuidance {
  const destinationLabel = options.destination.trim() || "No destination set";

  if (!options.destinationCoords) {
    return {
      active: false,
      mode: options.destination ? "blocked" : "idle",
      primary: options.destination ? "Resolve destination coordinates" : "Set a destination",
      secondary: options.destination ? destinationLabel : "Pick an address or route to a recovery read.",
      distanceToNext: "--",
      distanceToDestination: options.routeDistance,
      eta: options.routeEta,
      bearingLabel: "--",
      progressPercent: 0,
    };
  }

  const routeFeet = options.routeFeet ?? haversineFeet(options.unitPosition, options.destinationCoords);
  if (options.active && routeFeet <= options.arrivalRadiusFeet) {
    return {
      active: true,
      mode: "arrival",
      primary: "Arriving at target",
      secondary: destinationLabel,
      distanceToNext: formatDistance(routeFeet),
      distanceToDestination: formatDistance(routeFeet),
      eta: "<1 min",
      bearingLabel: "arrival",
      progressPercent: 100,
    };
  }

  const nextPointTuple = options.routePath[1] ?? [options.destinationCoords.lat, options.destinationCoords.lng];
  const nextPoint = { lat: nextPointTuple[0], lng: nextPointTuple[1] };
  const nextBearing = bearingDegrees(options.unitPosition, nextPoint);
  const referenceHeading = options.gpsFix.headingDegrees ?? nextBearing;
  const delta = bearingDeltaDegrees(referenceHeading, nextBearing);
  const verb = guidanceVerb(delta);
  const nextDistanceFeet = Math.max(25, haversineFeet(options.unitPosition, nextPoint));
  const bearingLabel = bearingCardinalLabel(nextBearing);
  const routeStartFeet = Math.max(routeFeet + nextDistanceFeet, routeFeet, 1);
  const progressPercent = Math.max(0, Math.min(100, Math.round(((routeStartFeet - routeFeet) / routeStartFeet) * 100)));

  return {
    active: options.active,
    mode: options.active ? "routing" : "preview",
    primary: `${verb} ${bearingLabel}`,
    secondary: options.active ? `Toward ${destinationLabel}` : `Preview to ${destinationLabel}`,
    distanceToNext: formatDistance(nextDistanceFeet),
    distanceToDestination: options.routeDistance,
    eta: options.routeEta,
    bearingLabel,
    progressPercent,
  };
}

function normalizePlate(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, "").toUpperCase();
}

function matchesHotlist(plate1: string, plate2: string, hotlists: DashboardHotlist[]): boolean {
  const candidates = new Set([normalizePlate(plate1), normalizePlate(plate2)]);
  return hotlists.some((entry) => entry.active && !!entry.plate_text && candidates.has(normalizePlate(entry.plate_text)));
}

function hotlistEntryForRow(row: ConsoleDetectionRow, hotlists: DashboardHotlist[]): DashboardHotlist | null {
  const candidates = new Set([normalizePlate(row.plate1), normalizePlate(row.plate2)]);
  return hotlists.find((entry) => entry.active && !!entry.plate_text && candidates.has(normalizePlate(entry.plate_text))) ?? null;
}

function hotlistLabelForRow(row: ConsoleDetectionRow, hotlists: DashboardHotlist[]): string | null {
  return hotlistEntryForRow(row, hotlists)?.label ?? null;
}

function normalizeUpperValue(value: string | null | undefined): string {
  return (value ?? "").trim().toUpperCase();
}

function trimValue(value: string | null | undefined): string {
  return (value ?? "").trim();
}

function hotlistIdentifierSummary(entry: Pick<DashboardHotlist, "plate_text" | "vin" | "vehicle_year" | "vehicle_make" | "vehicle_model">): string {
  if (trimValue(entry.plate_text)) {
    return trimValue(entry.plate_text);
  }
  if (trimValue(entry.vin)) {
    return `VIN ${trimValue(entry.vin)}`;
  }
  const profile = [trimValue(entry.vehicle_year), trimValue(entry.vehicle_make), trimValue(entry.vehicle_model)].filter(Boolean).join(" ");
  return profile || "Unidentified vehicle";
}

function hotlistAddressSummary(
  entry: Pick<DashboardHotlist, "address_label" | "address_line1" | "address_city" | "address_state">,
): string {
  const label = trimValue(entry.address_label);
  if (label) {
    return label;
  }
  const line = trimValue(entry.address_line1);
  const city = trimValue(entry.address_city);
  const state = trimValue(entry.address_state);
  return [line, [city, state].filter(Boolean).join(", ")].filter(Boolean).join(" - ") || "No target address";
}

function accountAlertingMode(entry: Pick<DashboardHotlist, "plate_text">): "plate" | "manual" {
  return trimValue(entry.plate_text) ? "plate" : "manual";
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

function mapCameraHealthStatus(status: DashboardCameraHealth["status"]): CameraUiFeed["status"] {
  if (status === "online") {
    return "Online";
  }
  if (status === "offline") {
    return "Offline";
  }
  return "Unknown";
}

function cameraFeedTone(status: CameraUiFeed["status"]): "success" | "warn" | "muted" {
  if (status === "Online") {
    return "success";
  }
  if (status === "Unknown") {
    return "warn";
  }
  return "muted";
}

function cameraFeedBadgeLabel(status: CameraUiFeed["status"]): string {
  if (status === "Online") {
    return "Scanning";
  }
  if (status === "Unknown") {
    return "Unknown";
  }
  return "Offline";
}

function cameraFeedDotTone(status: CameraUiFeed["status"]): "live" | "warn" | "off" {
  if (status === "Online") {
    return "live";
  }
  if (status === "Unknown") {
    return "warn";
  }
  return "off";
}

function dashboardToneForDetection(row: ConsoleDetectionRow): StatusPillTone {
  const severity = detectionSeverityForRow(row);
  if (severity === "critical") {
    return "red";
  }
  if (severity === "priority") {
    return "amber";
  }
  if (severity === "watch") {
    return "cyan";
  }
  return "gray";
}

function dashboardToneForCamera(status: CameraUiFeed["status"]): StatusPillTone {
  if (status === "Online") {
    return "green";
  }
  if (status === "Unknown") {
    return "amber";
  }
  return "gray";
}

function dashboardToneForService(state: ServiceHealthState): StatusPillTone {
  if (state === "ok") {
    return "green";
  }
  if (state === "degraded") {
    return "amber";
  }
  if (state === "down") {
    return "red";
  }
  return "gray";
}

function dashboardToneForFollowUp(status: FollowUpStatus | null | undefined): StatusPillTone {
  if (status === "resolved") {
    return "green";
  }
  if (status === "monitoring") {
    return "amber";
  }
  if (status === "open") {
    return "cyan";
  }
  return "gray";
}

function recoveryProbabilityForRow(
  row: ConsoleDetectionRow | null,
  hotlistEntry: DashboardHotlist | null,
  followUp: FollowUpRecord | null,
): { label: string; tone: StatusPillTone } {
  if (!row) {
    return { label: "Standby", tone: "gray" };
  }
  const score = confidencePercent(row.conf) + (hotlistEntry ? 15 : 0) + (followUp ? 10 : 0);
  if (score >= 108) {
    return { label: "High", tone: "red" };
  }
  if (score >= 92) {
    return { label: "Elevated", tone: "amber" };
  }
  if (score >= 80) {
    return { label: "Ready", tone: "cyan" };
  }
  return { label: "Low", tone: "gray" };
}

function summarizeVehicleIdentity(row: ConsoleDetectionRow | null, hotlistEntry: DashboardHotlist | null): string {
  if (hotlistEntry) {
    const parts = [hotlistEntry.vehicle_year, hotlistEntry.vehicle_color, hotlistEntry.vehicle_make, hotlistEntry.vehicle_model].filter(Boolean);
    if (parts.length > 0) {
      return parts.join(" ");
    }
  }
  return row?.vehicle ?? "Vehicle not identified";
}

function inferNoteField(notes: string | null | undefined, keywords: string[], whenFound: string, whenMissing = "Not logged"): string {
  const source = (notes ?? "").toLowerCase();
  return keywords.some((keyword) => source.includes(keyword)) ? whenFound : whenMissing;
}

function widgetConfigForId(config: DashboardConfig, id: DashboardWidgetId): { visible: boolean; size: DashboardWidgetSize } {
  const widget = config.widgets.find((item) => item.id === id);
  return {
    visible: widget?.visible ?? false,
    size: widget?.size ?? "standard",
  };
}

function buildCameraUiFeeds(
  rows: ConsoleDetectionRow[],
  source: DataSource,
  liveCameraHealth: DashboardCameraHealth[] | undefined,
): CameraUiFeed[] {
  if (source === "live" && liveCameraHealth && liveCameraHealth.length > 0) {
    return liveCameraHealth.map((camera) => ({
      id: camera.camera_id,
      label: camera.label,
      shortLabel: humanizeCameraId(camera.camera_id, "short"),
      status: mapCameraHealthStatus(camera.status),
      fps: camera.fps,
      lastSeenAtUtc: camera.last_seen_at_utc,
    }));
  }

  if (source === "live") {
    const liveCameraIds = [...new Set(rows.map((row) => row.cameraId))];
    return liveCameraIds.map((cameraId) => {
      const demoFeed = cameraFeeds.find((feed) => feed.id === cameraId);
      const lastRow = rows.find((row) => row.cameraId === cameraId);
      return {
        id: cameraId,
        label: buildCameraDisplayName(cameraId),
        shortLabel: humanizeCameraId(cameraId, "short"),
        status: "Online",
        fps: demoFeed?.fps ?? null,
        lastSeenAtUtc: lastRow?.timestampUtc ?? null,
      };
    });
  }

  return cameraFeeds.map((feed, index) => ({
    id: feed.id,
    label: feed.label,
    shortLabel: `Cam ${index + 1}`,
    status: feed.status,
    fps: feed.fps,
    lastSeenAtUtc: null,
  }));
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
    return "Vehicle under active review. Verify the read, vehicle, and account notes before closing or dismissing the hit.";
  }
  return "Recovery dismissed. Reopen only if the vehicle needs active repo attention again.";
}

function buildVerificationChecklist(options: {
  accountLabel: string | null | undefined;
  confidence: number | null | undefined;
  gps: string | null | undefined;
  hasFrame: boolean;
  hasPlateCrop: boolean;
  notes: string | null | undefined;
  plateText: string | null | undefined;
  vehicleLabel: string | null | undefined;
}): VerificationChecklistItem[] {
  const confidence = confidencePercent(options.confidence ?? 0);
  return [
    {
      label: "OCR",
      detail: options.plateText ? `${options.plateText}${confidence ? ` / ${confidence}%` : ""}` : "Unread plate",
      complete: Boolean(options.plateText && confidence >= 80),
    },
    {
      label: "Vehicle",
      detail: options.vehicleLabel?.trim() || "Vehicle overview needed",
      complete: Boolean(options.vehicleLabel?.trim()),
    },
    {
      label: "Account",
      detail: options.accountLabel?.trim() || options.notes?.trim() || "Review account notes",
      complete: Boolean(options.accountLabel?.trim() || options.notes?.trim()),
    },
    {
      label: "Location",
      detail: options.gps?.trim() || "GPS unavailable",
      complete: Boolean(options.gps?.trim()),
    },
  ];
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tagName = target.tagName.toLowerCase();
  return target.isContentEditable || tagName === "input" || tagName === "textarea" || tagName === "select";
}

function followUpOperationalSignal(record: FollowUpRecord): OperationalSignal {
  if (record.status === "resolved") {
    return {
      label: "Resolved",
      detail: "No further follow-up is currently required.",
      tone: "success",
    };
  }
  if (record.status === "monitoring") {
    return {
      label: "Monitor",
      detail: record.summary ?? "Keep the account under watch and verify before advancing.",
      tone: "warn",
    };
  }
  return {
    label: "Follow-up Due",
    detail: record.summary ?? "This read needs operator follow-up before closure.",
    tone: "critical",
  };
}

function buildOperationalSignal(
  row: ConsoleDetectionRow,
  followUp: FollowUpRecord | null,
  _assignment: null,
): OperationalSignal {
  if (followUp) {
    return followUpOperationalSignal(followUp);
  }
  if (row.hotlist || row.alertStatus === "active") {
    return {
      label: "Route Now",
      detail: "Verify the evidence pair, then move directly toward the vehicle.",
      tone: "critical",
    };
  }
  if (row.alertStatus === "acknowledged") {
    return {
      label: "Field Review",
      detail: "The hit has been acknowledged. Confirm the read, vehicle, and account notes before closing it.",
      tone: "warn",
    };
  }
  return {
    label: "Verify Only",
    detail: "Confirm the plate, vehicle, and location before taking account action.",
    tone: "cyan",
  };
}

function formatDetectionLocationLine(row: ConsoleDetectionRow): string {
  return row.source || row.camera;
}

function formatDetectionTimestampGpsLine(row: ConsoleDetectionRow): string {
  return `${formatDateTime(row.timestampUtc)} • ${row.gps}`;
}

function formatDetectionCameraLine(row: ConsoleDetectionRow, activityScore?: string): string {
  return activityScore ? `${row.camera} • Score ${activityScore}` : row.camera;
}

function resolveServiceHealthState(
  overviewState: HealthState | undefined,
  dataSource: DataSource,
): ServiceHealthState {
  if (overviewState) {
    return overviewState;
  }
  if (dataSource === "demo") {
    return "demo";
  }
  if (dataSource === "fallback") {
    return "offline";
  }
  return "ok";
}

function serviceHealthLabel(state: ServiceHealthState): string {
  if (state === "ok") {
    return "Healthy";
  }
  if (state === "degraded") {
    return "Degraded";
  }
  if (state === "down") {
    return "Down";
  }
  if (state === "demo") {
    return "Demo";
  }
  return "Offline";
}

function serviceHealthTone(state: ServiceHealthState): "success" | "warn" | "critical" | "muted" {
  if (state === "ok") {
    return "success";
  }
  if (state === "degraded") {
    return "warn";
  }
  if (state === "down") {
    return "critical";
  }
  return "muted";
}

function edgeCaptureLabel(state: EdgeCaptureState | null | undefined): string {
  if (state === "running") {
    return "Running";
  }
  if (state === "starting") {
    return "Starting";
  }
  if (state === "stopping") {
    return "Stopping";
  }
  if (state === "stopped") {
    return "Stopped";
  }
  if (state === "degraded") {
    return "Degraded";
  }
  if (state === "faulted") {
    return "Faulted";
  }
  return "Unknown";
}

function edgeCaptureBadgeTone(state: EdgeCaptureState | null | undefined): "success" | "warn" | "critical" | "muted" {
  if (state === "running") {
    return "success";
  }
  if (state === "starting" || state === "stopping" || state === "degraded") {
    return "warn";
  }
  if (state === "faulted") {
    return "critical";
  }
  return "muted";
}

function edgeCaptureFooterTone(state: EdgeCaptureState | null | undefined): "good" | "off" | "warn" {
  if (state === "running") {
    return "good";
  }
  if (state === "starting" || state === "stopping" || state === "degraded" || state === "faulted") {
    return "warn";
  }
  return "off";
}

function edgeHeartbeatLabel(edgeRuntime: EdgeRuntimeStatus | null): string {
  if (!edgeRuntime?.last_heartbeat_at_utc) {
    return "No heartbeat";
  }
  return formatDateTime(edgeRuntime.last_heartbeat_at_utc);
}

function buildRecognitionVehicleLabel(event: DashboardPopupActivityEvent): string {
  const parts = [event.optional_vehicle_year, titleCase(event.vehicle_color), titleCase(event.vehicle_make), titleCase(event.vehicle_model)].filter(Boolean);
  return parts.join(" ") || event.hotlist_label || "Unclassified vehicle";
}

function buildBlankHotlistDraft(seedPlate = ""): HotlistDraft {
  return {
    plateText: normalizePlate(seedPlate),
    vin: "",
    vehicleYear: "",
    vehicleMake: "",
    vehicleModel: "",
    vehicleColor: "",
    addressLabel: "",
    addressLine1: "",
    addressLine2: "",
    addressCity: "",
    addressState: "",
    addressPostalCode: "",
    label: "",
    notes: "",
    active: true,
  };
}

function hotlistDraftFromEntry(entry: DashboardHotlist): HotlistDraft {
  return {
    plateText: entry.plate_text ?? "",
    vin: entry.vin ?? "",
    vehicleYear: entry.vehicle_year ?? "",
    vehicleMake: entry.vehicle_make ?? "",
    vehicleModel: entry.vehicle_model ?? "",
    vehicleColor: entry.vehicle_color ?? "",
    addressLabel: entry.address_label ?? "",
    addressLine1: entry.address_line1 ?? "",
    addressLine2: entry.address_line2 ?? "",
    addressCity: entry.address_city ?? "",
    addressState: entry.address_state ?? "",
    addressPostalCode: entry.address_postal_code ?? "",
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

function buildSearchActivityScore(rows: ConsoleDetectionRow[], referenceTimeMs = Date.now()): string {
  const buckets = [0, 0, 0, 0];

  for (const row of rows) {
    const timestamp = Date.parse(row.timestampUtc);
    if (Number.isNaN(timestamp)) {
      continue;
    }

    const ageDays = Math.max(0, (referenceTimeMs - timestamp) / 86_400_000);
    if (ageDays <= 30) {
      buckets[0] += 1;
    } else if (ageDays <= 90) {
      buckets[1] += 1;
    } else if (ageDays <= 180) {
      buckets[2] += 1;
    } else {
      buckets[3] += 1;
    }
  }

  return buckets.map((count) => Math.min(count, 9)).join("");
}

function inferSearchActivityPattern(rows: ConsoleDetectionRow[]): SearchActivityPattern {
  if (rows.length < 2) {
    return {
      label: "Single sighting",
      detail: "Need repeat reads before routine tagging is reliable.",
      tone: "muted",
    };
  }

  let daytimeReads = 0;
  let overnightReads = 0;

  for (const row of rows) {
    const timestamp = new Date(row.timestampUtc);
    if (Number.isNaN(timestamp.valueOf())) {
      continue;
    }

    const hour = timestamp.getHours();
    if (hour >= 6 && hour < 18) {
      daytimeReads += 1;
    } else {
      overnightReads += 1;
    }
  }

  const dominantCount = Math.max(daytimeReads, overnightReads);
  const share = dominantCount / rows.length;
  if (dominantCount >= 2 && share >= 0.6) {
    if (daytimeReads > overnightReads) {
      return {
        label: "Likely workplace",
        detail: `${daytimeReads} of ${rows.length} reads landed between 06:00 and 18:00.`,
        tone: "cyan",
      };
    }

    return {
      label: "Likely residential",
      detail: `${overnightReads} of ${rows.length} reads landed between 18:00 and 06:00.`,
      tone: "success",
    };
  }

  return {
    label: "Mixed routine",
    detail: "Sightings split across daytime and overnight windows.",
    tone: "warn",
  };
}

function summarizeFilterCount(count: number, singular: string, emptyLabel = "Optional"): string {
  if (count <= 0) {
    return emptyLabel;
  }
  return `${count} ${count === 1 ? singular : `${singular}s`} active`;
}

function buildLeadResponseCue(
  row: ConsoleDetectionRow,
  followUp: FollowUpRecord | null,
  _assignment: null,
  hotlistLabel: string | null,
): OperationalSignal {
  if (followUp) {
    if (followUp.status === "open") {
      return {
        label: "Action required",
        detail: followUp.summary ?? followUp.notes ?? "An open follow-up is attached. Verify the vehicle and update the case.",
        tone: "critical",
      };
    }
    if (followUp.status === "monitoring") {
      return {
        label: "Monitor target",
        detail: followUp.summary ?? followUp.notes ?? "Keep the vehicle in sight and wait for a stronger recovery cue.",
        tone: "warn",
      };
    }
    return {
      label: "Follow-up resolved",
      detail: followUp.summary ?? followUp.notes ?? "The follow-up is resolved. Review the record before taking new action.",
      tone: "muted",
    };
  }

  if (row.hotlist || hotlistLabel) {
    return {
      label: "Verify and route",
      detail: "Recovery account match found. Confirm the vehicle, then route or open the account.",
      tone: "critical",
    };
  }

  return {
    label: "Unassigned lead",
    detail: "Review the evidence, map the sighting, or create a recovery account for continued tracking.",
    tone: "cyan",
  };
}

function buildSearchTimelineMarkers(rows: ConsoleDetectionRow[]): SearchTimelineMarker[] {
  if (rows.length === 0) {
    return [];
  }

  const chronological = [...rows]
    .sort((left, right) => left.timestampUtc.localeCompare(right.timestampUtc))
    .slice(-10);

  const timestamps = chronological
    .map((row) => Date.parse(row.timestampUtc))
    .filter((value) => !Number.isNaN(value));

  if (timestamps.length === 0) {
    return chronological.map((row, index) => ({
      id: row.id,
      isLead: index === chronological.length - 1,
      leftPercent: chronological.length === 1 ? 50 : (index / Math.max(chronological.length - 1, 1)) * 100,
      severity: searchResultSeverity(row),
      timestampLabel: formatClock(row.timestampUtc),
    }));
  }

  const minTimestamp = Math.min(...timestamps);
  const maxTimestamp = Math.max(...timestamps);
  const span = Math.max(maxTimestamp - minTimestamp, 1);
  const leadId = chronological[chronological.length - 1]?.id;

  return chronological.map((row) => {
    const timestamp = Date.parse(row.timestampUtc);
    const leftPercent = Number.isNaN(timestamp) ? 50 : ((timestamp - minTimestamp) / span) * 100;
    return {
      id: row.id,
      isLead: row.id === leadId,
      leftPercent,
      severity: searchResultSeverity(row),
      timestampLabel: formatClock(row.timestampUtc),
    };
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

function buildRoutePath(position: { lat: number; lng: number }, destination: { lat: number; lng: number }): [number, number][] {
  const mid1: [number, number] = [
    position.lat + (destination.lat - position.lat) * 0.4 + 0.0032,
    position.lng + (destination.lng - position.lng) * 0.2,
  ];
  const mid2: [number, number] = [
    position.lat + (destination.lat - position.lat) * 0.72 - 0.0016,
    position.lng + (destination.lng - position.lng) * 0.68 + 0.0024,
  ];
  return [
    [position.lat, position.lng],
    mid1,
    mid2,
    [destination.lat, destination.lng],
  ];
}

function MapViewportSync(props: {
  autoCenter: boolean;
  unitPosition: DestinationCoords;
  destinationCoords: DestinationCoords | null;
  showRoute: boolean;
}): null {
  const map = useMap();

  useEffect(() => {
    if (!props.autoCenter) {
      return;
    }

    if (props.showRoute && props.destinationCoords) {
      map.fitBounds(
        [
          [props.unitPosition.lat, props.unitPosition.lng],
          [props.destinationCoords.lat, props.destinationCoords.lng],
        ],
        { padding: [40, 40], maxZoom: 15 },
      );
      return;
    }

    const focus = props.destinationCoords ?? props.unitPosition;
    map.setView([focus.lat, focus.lng], map.getZoom(), { animate: false });
  }, [
    props.autoCenter,
    map,
    props.destinationCoords?.lat,
    props.destinationCoords?.lng,
    props.showRoute,
    props.unitPosition.lat,
    props.unitPosition.lng,
  ]);

  return null;
}

function formatCoords(coords: DestinationCoords): string {
  return `${coords.lat.toFixed(5)}, ${coords.lng.toFixed(5)}`;
}

function formatAccuracy(accuracyMeters: number | null): string {
  if (accuracyMeters == null) return "accuracy --";
  return `+/-${Math.round(accuracyMeters)} m`;
}

function MapResizeSync(): null {
  const map = useMap();

  useLayoutEffect(() => {
    const container = map.getContainer();
    const invalidate = (): void => {
      map.invalidateSize({ animate: false });
    };

    invalidate();
    const frame = window.requestAnimationFrame(invalidate);
    const timeout = window.setTimeout(invalidate, 250);
    const observer = new ResizeObserver(invalidate);
    observer.observe(container);

    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timeout);
      observer.disconnect();
    };
  }, [map]);

  return null;
}

function makeDotIcon(color: string, size: number): L.DivIcon {
  return L.divIcon({
    className: "map-dot-icon",
    html: `<span class="map-dot" style="width:${size}px;height:${size}px;background:${color}"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function makeUnitIcon(headingDegrees: number | null): L.DivIcon {
  const rotation = typeof headingDegrees === "number" && Number.isFinite(headingDegrees) ? headingDegrees : 0;
  return L.divIcon({
    className: "map-unit-icon",
    html: `<span class="map-unit" style="--unit-heading:${rotation}deg"><span></span></span>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
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

const targetIcon = makeDotIcon("#F8FBF7", 12);
const activeAlertIcon = makeDotIcon("#FB7185", 12);
const acknowledgedAlertIcon = makeDotIcon("#FBBF24", 10);
const historicalAlertIcon = makeDotIcon("#A9BBB4", 10);

function OpsMap(props: {
  autoCenter: boolean;
  unitPosition: { lat: number; lng: number };
  unitHeadingDegrees: number | null;
  destinationCoords: DestinationCoords | null;
  routePath: [number, number][];
  rows: ConsoleDetectionRow[];
  alertMarkers: MapAlertMarker[];
  destinationLabel: string;
  radiusFeet: number;
  showRoute: boolean;
  showDestination: boolean;
  showRadiusRing: boolean;
  showActiveAlertPins: boolean;
  showHistoricalAlertPins: boolean;
  showDetectionPins: boolean;
  selectedRowId: string | null;
  onSelect: (rowId: string) => void;
}): ReactElement {
  const initialCenter = props.destinationCoords ?? props.unitPosition;
  return (
    <MapContainer center={[initialCenter.lat, initialCenter.lng]} zoom={14} scrollWheelZoom={true} className="map-stage__canvas">
      <TileLayer attribution="OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <MapResizeSync />
      <MapViewportSync
        autoCenter={props.autoCenter}
        unitPosition={props.unitPosition}
        destinationCoords={props.destinationCoords}
        showRoute={props.showRoute}
      />

      <Marker position={[props.unitPosition.lat, props.unitPosition.lng]} icon={makeUnitIcon(props.unitHeadingDegrees)}>
        <Popup>Recovery unit</Popup>
      </Marker>

      {props.showDestination && props.destinationCoords ? (
        <Marker position={[props.destinationCoords.lat, props.destinationCoords.lng]} icon={targetIcon}>
          <Popup>{props.destinationLabel || "Destination"}</Popup>
        </Marker>
      ) : null}

      {props.showDestination && props.showRadiusRing && props.destinationCoords ? (
        <Circle
          center={[props.destinationCoords.lat, props.destinationCoords.lng]}
          radius={props.radiusFeet * 0.3048}
          pathOptions={{
            color: "#5EEAD4",
            fillColor: "rgba(56,232,255,0.10)",
            fillOpacity: 0.3,
            weight: 2,
            dashArray: "6 5",
          }}
        />
      ) : null}

      {props.showRoute && props.routePath.length >= 2 ? <Polyline positions={props.routePath} pathOptions={{ color: "#5EEAD4", opacity: 0.8, weight: 4 }} /> : null}

      {props.showDetectionPins
        ? props.rows.map((row) => (
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
          ))
        : null}

      {props.alertMarkers
        .filter((marker) => (marker.status === "active" ? props.showActiveAlertPins : props.showHistoricalAlertPins))
        .map((marker) => (
          <Marker
            key={marker.id}
            position={[marker.lat, marker.lng]}
            icon={marker.status === "active" ? activeAlertIcon : marker.status === "acknowledged" ? acknowledgedAlertIcon : historicalAlertIcon}
          >
            <Popup>
              <strong>{marker.plate}</strong>
              <br />
              {marker.label}
              <br />
              {titleCase(marker.status)}
            </Popup>
          </Marker>
        ))}
    </MapContainer>
  );
}

function MapStagePanel(props: {
  compact?: boolean;
  alertMarkers: MapAlertMarker[];
  activeDestination: string;
  destinationCoords: DestinationCoords | null;
  destinationInput: string;
  destinationModalOpen: boolean;
  destinationTargets: DestinationTarget[];
  destinationPreview: { distance: string; eta: string; feet: number } | null;
  idleScanEnabled: boolean;
  layerMenuOpen: boolean;
  navigationActive: boolean;
  navigationGuidance: NavigationGuidance;
  routeDistance: string;
  routeEta: string;
  routePath: [number, number][];
  routeStatusLabel: string;
  rows: ConsoleDetectionRow[];
  selectedRowId: string | null;
  settings: UiSettings;
  gpsFix: GpsFixState;
  liveAddress: LiveAddressState;
  unitPosition: { lat: number; lng: number };
  withinRadius: boolean;
  onApplyDestinationTarget: (target: DestinationTarget) => void;
  onClearDestinationDraft: () => void;
  onCloseDestinationModal: () => void;
  onDestinationChange: (value: string) => void;
  onEndRoute: () => void;
  onOpenDestinationModal: () => void;
  onRemoveRecentDestination: (id: string) => void;
  onSelect: (rowId: string) => void;
  onSelectGeocodedAddress: (address: string, coords: DestinationCoords) => void;
  onStageResolvedDestination: (address: string, coords: DestinationCoords) => void;
  onStageDestination: () => void;
  onStartResolvedRoute: (address: string, coords: DestinationCoords) => void;
  onStartRoute: () => void;
  onToggleActiveAlertPins: () => void;
  onToggleDetectionPins: () => void;
  onToggleHistoricalAlertPins: () => void;
  onToggleLayerMenu: () => void;
  onToggleRadiusRing: () => void;
}): ReactElement {
  const compact = props.compact === true;
  const hasDestination = props.activeDestination.trim().length > 0;
  const activeAlertCount = props.alertMarkers.filter((marker) => marker.status === "active").length;
  const historicalAlertCount = props.alertMarkers.filter((marker) => marker.status !== "active").length;
  const gpsCoords = gpsFixToCoords(props.gpsFix);
  const liveAddressLine = props.liveAddress.address
    ? [props.liveAddress.address.house_number, props.liveAddress.address.road].filter(Boolean).join(" ") || props.liveAddress.address.display_name
    : props.gpsFix.status === "denied"
      ? "Location permission denied"
      : props.gpsFix.status === "unsupported"
        ? "GPS unavailable"
        : props.liveAddress.status === "loading"
          ? "Resolving current address..."
          : "Current address pending";
  const liveAddressMeta = props.liveAddress.address
    ? [props.liveAddress.address.city, props.liveAddress.address.state, props.liveAddress.address.postal_code].filter(Boolean).join(", ")
    : gpsCoords
      ? formatCoords(gpsCoords)
      : "Enable location access for live street numerics";
  const liveLocationTone =
    props.gpsFix.status === "locked" || props.gpsFix.status === "fair"
      ? "good"
      : props.gpsFix.status === "weak" || props.gpsFix.status === "stale" || props.gpsFix.status === "acquiring"
        ? "warn"
        : "off";
  const scanStatusLabel = props.navigationActive
    ? props.settings.autoArrivalScan
      ? `Auto-scan ${props.settings.arrivalRadiusFeet} ft`
      : "Auto-scan off"
    : props.idleScanEnabled
      ? "Idle scan on"
      : "Idle scan off";

  return (
    <div className={`map-stage ${compact ? "map-stage--overview" : ""}`.trim()}>
      <OpsMap
        autoCenter={props.settings.autoCenterVehicle}
        unitPosition={props.unitPosition}
        unitHeadingDegrees={props.gpsFix.headingDegrees}
        destinationCoords={props.destinationCoords}
        routePath={props.routePath}
        rows={props.rows}
        alertMarkers={props.alertMarkers}
        destinationLabel={props.activeDestination}
        radiusFeet={props.settings.arrivalRadiusFeet}
        showRoute={props.navigationActive || hasDestination}
        showDestination={hasDestination}
        showRadiusRing={props.settings.showRadiusRing}
        showActiveAlertPins={props.settings.showActiveAlertPins}
        showHistoricalAlertPins={props.settings.showHistoricalAlertPins}
        showDetectionPins={props.settings.showDetectionPins}
        selectedRowId={props.selectedRowId}
        onSelect={props.onSelect}
      />

      <div
        className={`map-stage__badge ${
          props.withinRadius ? "map-stage__badge--success" : props.navigationActive ? "map-stage__badge--cyan" : "map-stage__badge--muted"
        }`.trim()}
      >
        {props.routeStatusLabel}
      </div>

      <div className={`map-stage__location-chip map-stage__location-chip--${liveLocationTone}`} aria-live="polite">
        <span className="map-stage__location-label">Current location</span>
        <strong>{liveAddressLine}</strong>
        <span>{liveAddressMeta || formatCoords(props.unitPosition)}</span>
        <small>
          {gpsCoords
            ? `${formatCoords(gpsCoords)} / ${formatAccuracy(props.gpsFix.accuracyMeters)} / ${formatMph(props.gpsFix.speedMetersPerSecond)}`
            : "Map is showing demo fallback position"}
        </small>
      </div>

      {hasDestination || props.navigationActive ? (
        <div className={`map-stage__guidance map-stage__guidance--${props.navigationGuidance.mode}`} aria-live="polite">
          <div className="map-stage__guidance-turn">
            <span>{props.navigationGuidance.mode === "arrival" ? "ARR" : props.navigationGuidance.bearingLabel.slice(0, 2).toUpperCase()}</span>
          </div>
          <div className="map-stage__guidance-main">
            <span className="map-stage__location-label">{props.navigationGuidance.active ? "Next guidance" : "Route preview"}</span>
            <strong>{props.navigationGuidance.primary}</strong>
            <small>{props.navigationGuidance.secondary}</small>
          </div>
          <div className="map-stage__guidance-metrics">
            <span>{props.navigationGuidance.distanceToNext}</span>
            <strong>{props.navigationGuidance.eta}</strong>
          </div>
          <div className="map-stage__guidance-progress" aria-hidden="true">
            <span style={{ width: `${props.navigationGuidance.progressPercent}%` }} />
          </div>
        </div>
      ) : null}

      <div className="map-stage__controls tooltip-zone--below" role="toolbar" aria-label="Map controls">
        <Tooltip text="Stage or update the route destination">
          <button className="map-stage__control" type="button" onClick={props.onOpenDestinationModal}>
            {hasDestination ? "Change" : "Destination"}
          </button>
        </Tooltip>
        {!props.navigationActive && hasDestination ? (
          <Tooltip text="Begin navigation to the staged destination">
            <button className="map-stage__control map-stage__control--primary" type="button" onClick={props.onStartRoute}>
              Start
            </button>
          </Tooltip>
        ) : null}
        {props.navigationActive ? (
          <Tooltip text="End the current route">
            <button className="map-stage__control" type="button" onClick={props.onEndRoute}>
              End
            </button>
          </Tooltip>
        ) : null}
        <Tooltip text="Toggle map layers">
          <button className={`map-stage__control ${props.layerMenuOpen ? "is-active" : ""}`.trim()} type="button" aria-pressed={props.layerMenuOpen ? "true" : "false"} onClick={props.onToggleLayerMenu}>
            Layers
          </button>
        </Tooltip>
      </div>

      {props.layerMenuOpen ? (
        <div className="map-stage__layer-menu" role="menu">
          <div className="map-stage__layer-menu-header">
            <strong>Map Layers</strong>
            <span>{`${activeAlertCount} active · ${historicalAlertCount} prior · ${props.rows.length} reads`}</span>
          </div>
          <button className={`map-stage__layer-toggle ${props.settings.showActiveAlertPins ? "is-active" : ""}`.trim()} type="button" onClick={props.onToggleActiveAlertPins}>
            <span>Active alerts</span>
            <strong>{props.settings.showActiveAlertPins ? "On" : "Off"}</strong>
          </button>
          <button className={`map-stage__layer-toggle ${props.settings.showHistoricalAlertPins ? "is-active" : ""}`.trim()} type="button" onClick={props.onToggleHistoricalAlertPins}>
            <span>Prior alerts</span>
            <strong>{props.settings.showHistoricalAlertPins ? "On" : "Off"}</strong>
          </button>
          <button className={`map-stage__layer-toggle ${props.settings.showDetectionPins ? "is-active" : ""}`.trim()} type="button" onClick={props.onToggleDetectionPins}>
            <span>Live reads</span>
            <strong>{props.settings.showDetectionPins ? "On" : "Off"}</strong>
          </button>
          <button className={`map-stage__layer-toggle ${props.settings.showRadiusRing ? "is-active" : ""}`.trim()} type="button" onClick={props.onToggleRadiusRing}>
            <span>Arrival ring</span>
            <strong>{props.settings.showRadiusRing ? "On" : "Off"}</strong>
          </button>
        </div>
      ) : null}

      <div className="map-stage__footer">
        <span className="map-stage__footer-meta">{scanStatusLabel}</span>
        <span className="map-stage__footer-meta map-stage__footer-meta--muted">{`${activeAlertCount} active · ${props.rows.length} reads`}</span>
      </div>

      {props.destinationModalOpen ? (
        <DestinationModal
          destinationInput={props.destinationInput}
          destinationTargets={props.destinationTargets}
          destinationPreview={props.destinationPreview}
          hasDestination={hasDestination}
          arrivalRadiusFeet={props.settings.arrivalRadiusFeet}
          unitPosition={props.unitPosition}
          onApplyTarget={props.onApplyDestinationTarget}
          onClearDraft={props.onClearDestinationDraft}
          onClose={props.onCloseDestinationModal}
          onDestinationChange={props.onDestinationChange}
          onRemoveRecent={props.onRemoveRecentDestination}
          onSelectGeocodedAddress={props.onSelectGeocodedAddress}
          onStageResolvedDestination={props.onStageResolvedDestination}
          onStageDestination={props.onStageDestination}
          onStartResolvedRoute={props.onStartResolvedRoute}
          onStartRoute={props.onStartRoute}
        />
      ) : null}
    </div>
  );
}

function DestinationModal(props: {
  destinationInput: string;
  destinationTargets: DestinationTarget[];
  destinationPreview: { distance: string; eta: string; feet: number } | null;
  hasDestination: boolean;
  arrivalRadiusFeet: number;
  unitPosition: DestinationCoords;
  onApplyTarget: (target: DestinationTarget) => void;
  onClearDraft: () => void;
  onClose: () => void;
  onDestinationChange: (value: string) => void;
  onRemoveRecent: (id: string) => void;
  onSelectGeocodedAddress: (address: string, coords: DestinationCoords) => void;
  onStageResolvedDestination: (address: string, coords: DestinationCoords) => void;
  onStageDestination: () => void;
  onStartResolvedRoute: (address: string, coords: DestinationCoords) => void;
  onStartRoute: () => void;
}): ReactElement {
  const inputRef = useRef<HTMLInputElement>(null);
  const { suggestions: geocodeSuggestions, loading: geocodeLoading, error: geocodeError } = useGeocodeSuggestions(
    props.destinationInput,
    props.unitPosition,
  );
  const [suggestionsOpen, setSuggestionsOpen] = useState(true);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  useEffect(() => {
    setSuggestionsOpen(true);
  }, [props.destinationInput]);

  useEffect(() => {
    function handleKey(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        props.onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [props.onClose]);

  const trimmed = props.destinationInput.trim();
  const canCommit = trimmed.length > 0;
  const groupedTargets = {
    alert: props.destinationTargets.filter((target) => target.source === "alert"),
    read: props.destinationTargets.filter((target) => target.source === "read"),
    account: props.destinationTargets.filter((target) => target.source === "account"),
    recent: props.destinationTargets.filter((target) => target.source === "recent"),
  };
  const localSuggestions =
    trimmed.length < destinationLocalSuggestionMinChars
      ? []
      : props.destinationTargets
          .filter((target) => target.coords != null)
          .filter((target) => {
            const normalizedQuery = trimmed.toLowerCase();
            const haystack = [target.label, target.address, target.subtitle].filter(Boolean).join(" ").toLowerCase();
            return haystack.includes(normalizedQuery);
          })
          .slice(0, 4);
  const normalizedLocalAddresses = new Set(localSuggestions.map((target) => target.address.trim().toLowerCase()));
  const combinedGeocodeSuggestions = geocodeSuggestions.filter(
    (suggestion) => !normalizedLocalAddresses.has(suggestion.displayName.trim().toLowerCase()),
  );
  const showSuggestions =
    suggestionsOpen &&
    trimmed.length >= destinationLocalSuggestionMinChars &&
    (localSuggestions.length > 0 || combinedGeocodeSuggestions.length > 0 || geocodeLoading);
  const topResolvedSuggestion =
    localSuggestions[0]?.coords != null
      ? { address: localSuggestions[0].address, coords: localSuggestions[0].coords }
      : combinedGeocodeSuggestions[0]
        ? {
            address: combinedGeocodeSuggestions[0].displayName,
            coords: { lat: combinedGeocodeSuggestions[0].lat, lng: combinedGeocodeSuggestions[0].lng },
          }
        : null;
  const canStartRoute = canCommit && (props.destinationPreview != null || topResolvedSuggestion != null);

  function handleInputKeyDown(event: ReactKeyboardEvent<HTMLInputElement>): void {
    if (event.key === "Enter" && canStartRoute) {
      event.preventDefault();
      if (props.destinationPreview) {
        props.onStartRoute();
        return;
      }
      if (topResolvedSuggestion) {
        props.onStartResolvedRoute(topResolvedSuggestion.address, topResolvedSuggestion.coords);
      }
    }
  }

  function handleSelectSuggestion(suggestion: GeocodeSuggestion): void {
    setSuggestionsOpen(false);
    props.onSelectGeocodedAddress(suggestion.displayName, { lat: suggestion.lat, lng: suggestion.lng });
  }

  function handleSelectLocalSuggestion(target: DestinationTarget): void {
    setSuggestionsOpen(false);
    props.onApplyTarget(target);
  }

  function handleStageTarget(): void {
    if (props.destinationPreview) {
      props.onStageDestination();
      return;
    }
    if (topResolvedSuggestion) {
      props.onStageResolvedDestination(topResolvedSuggestion.address, topResolvedSuggestion.coords);
      return;
    }
    props.onStageDestination();
  }

  function handleStartTargetRoute(): void {
    if (props.destinationPreview) {
      props.onStartRoute();
      return;
    }
    if (topResolvedSuggestion) {
      props.onStartResolvedRoute(topResolvedSuggestion.address, topResolvedSuggestion.coords);
    }
  }

  return (
    <div className="destination-modal__scrim" role="presentation" onClick={props.onClose}>
      <div
        className="destination-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="destination-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="destination-modal__header">
          <div>
            <span className="eyebrow">Route Planner</span>
            <h3 id="destination-modal-title">{props.hasDestination ? "Change Destination" : "Set Destination"}</h3>
            <p className="destination-modal__hint">
              Type an address to search, or pick a recovery account, recent stop, or last-seen point below.
            </p>
          </div>
          <button
            className="destination-modal__close"
            type="button"
            onClick={props.onClose}
            aria-label="Close destination planner"
          >
            Close
          </button>
        </div>

        <div className="destination-modal__field">
          <label className="field-label" htmlFor="destination-modal-input">
            Destination address
          </label>
          <div className="destination-modal__input-row">
            {showSuggestions ? (
              <input
                ref={inputRef}
                id="destination-modal-input"
                className="text-input destination-modal__input"
                placeholder="Start typing an address…"
                type="text"
                value={props.destinationInput}
                autoComplete="off"
                spellCheck={false}
                onChange={(event) => props.onDestinationChange(event.target.value)}
                onKeyDown={handleInputKeyDown}
                role="combobox"
                aria-expanded="true"
                aria-autocomplete="list"
                aria-controls="destination-suggestions"
              />
            ) : (
              <input
                ref={inputRef}
                id="destination-modal-input"
                className="text-input destination-modal__input"
                placeholder="Start typing an address…"
                type="text"
                value={props.destinationInput}
                autoComplete="off"
                spellCheck={false}
                onChange={(event) => props.onDestinationChange(event.target.value)}
                onKeyDown={handleInputKeyDown}
                role="combobox"
                aria-expanded="false"
                aria-autocomplete="list"
                aria-controls="destination-suggestions"
              />
            )}
            {trimmed.length > 0 ? (
              <button
                className="destination-modal__clear"
                type="button"
                onClick={props.onClearDraft}
                aria-label="Clear destination"
              >
                Clear
              </button>
            ) : null}
          </div>
          {showSuggestions ? (
            <ul id="destination-suggestions" className="destination-modal__suggestions" role="listbox">
              {localSuggestions.map((target) => (
                <li
                  key={`local-${target.id}`}
                  className="destination-modal__suggestion"
                  role="option"
                  aria-selected="false"
                  tabIndex={0}
                  onClick={() => handleSelectLocalSuggestion(target)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      handleSelectLocalSuggestion(target);
                    }
                  }}
                >
                  <span className="destination-modal__suggestion-name">{target.label}</span>
                  <span className="destination-modal__suggestion-meta">
                    <span>{target.address}</span>
                    <span className="destination-modal__suggestion-source">Recovery address</span>
                  </span>
                </li>
              ))}
              {geocodeLoading && geocodeSuggestions.length === 0 ? (
                <li className="destination-modal__suggestion destination-modal__suggestion--loading" role="option" aria-selected="false">
                  Searching addresses…
                </li>
              ) : (
                combinedGeocodeSuggestions.map((suggestion) => (
                  <li
                    key={suggestion.id}
                    className="destination-modal__suggestion"
                    role="option"
                    aria-selected="false"
                    tabIndex={0}
                    onClick={() => handleSelectSuggestion(suggestion)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleSelectSuggestion(suggestion); } }}
                  >
                    <span className="destination-modal__suggestion-name">{suggestion.displayName}</span>
                    <span className="destination-modal__suggestion-meta">
                      <span>{`${suggestion.lat.toFixed(5)}, ${suggestion.lng.toFixed(5)}`}</span>
                      <span className="destination-modal__suggestion-source">Address search</span>
                    </span>
                  </li>
                ))
              )}
            </ul>
          ) : null}
          {geocodeError && trimmed.length >= geocodeMinChars ? (
            <p className="destination-modal__status destination-modal__status--error" role="status">
              {geocodeError}
            </p>
          ) : null}
        </div>

        {props.destinationPreview ? (
          <div className="destination-modal__preview">
            <div>
              <span className="eyebrow">Route preview</span>
              <strong>{props.destinationPreview.distance}</strong>
              <span className="destination-modal__preview-sub">ETA {props.destinationPreview.eta}</span>
            </div>
            <div className="destination-modal__preview-meta">
              <span>Auto-scan arms at {props.arrivalRadiusFeet} ft</span>
            </div>
          </div>
        ) : canCommit ? (
          <div className="destination-modal__preview destination-modal__preview--pending">
            <span>Location coordinates not available — route preview will appear once coordinates resolve.</span>
          </div>
        ) : null}

        <div className="destination-modal__targets">
          <TargetGroup
            label="Latest recovery match"
            targets={groupedTargets.alert}
            onApply={props.onApplyTarget}
            emptyHint="No active recovery match with a mapped location"
          />
          <TargetGroup
            label="Last-seen vehicles"
            targets={groupedTargets.read}
            onApply={props.onApplyTarget}
            emptyHint="No recent last-seen points with GPS"
          />
          <TargetGroup
            label="Recovery accounts"
            targets={groupedTargets.account}
            onApply={props.onApplyTarget}
            emptyHint="Add address details on account cards to see them here"
          />
          <TargetGroup
            label="Recent stops"
            targets={groupedTargets.recent}
            onApply={props.onApplyTarget}
            onRemove={props.onRemoveRecent}
            emptyHint="Saved stops show up here after you use them"
          />
        </div>

        <div className="destination-modal__actions">
          <button
            className="btn btn--ghost"
            type="button"
            onClick={handleStageTarget}
            disabled={!canCommit}
          >
            Save Target
          </button>
          <button
            className="btn btn--primary"
            type="button"
            onClick={handleStartTargetRoute}
            disabled={!canStartRoute}
          >
            Start Route
          </button>
        </div>
      </div>
    </div>
  );
}

function TargetGroup(props: {
  label: string;
  targets: DestinationTarget[];
  onApply: (target: DestinationTarget) => void;
  onRemove?: (id: string) => void;
  emptyHint: string;
}): ReactElement {
  return (
    <section className="target-group" aria-label={props.label}>
      <header className="target-group__header">
        <span className="eyebrow">{props.label}</span>
      </header>
      {props.targets.length === 0 ? (
        <p className="target-group__empty">{props.emptyHint}</p>
      ) : (
        <ul className="target-group__list">
          {props.targets.map((target) => (
            <li key={target.id} className={`target-card target-card--${target.accent ?? "muted"}`}>
              <button
                type="button"
                className="target-card__body"
                onClick={() => props.onApply(target)}
              >
                <div className="target-card__headline">
                  <strong>{target.label}</strong>
                  {target.relativeTime ? <span className="target-card__time">{target.relativeTime}</span> : null}
                </div>
                <span className="target-card__address">{target.address}</span>
                {target.subtitle ? <span className="target-card__subtitle">{target.subtitle}</span> : null}
                {target.coords == null ? (
                  <span className="target-card__badge">Address only</span>
                ) : null}
              </button>
              {props.onRemove ? (
                <button
                  type="button"
                  className="target-card__remove"
                  aria-label={`Remove ${target.label}`}
                  onClick={() => props.onRemove?.(target.id)}
                >
                  ×
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
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

function VerificationChecklist(props: { compact?: boolean; items: VerificationChecklistItem[] }): ReactElement {
  return (
    <div className={`verification-checklist ${props.compact ? "verification-checklist--compact" : ""}`.trim()}>
      {props.items.map((item) => (
        <div key={item.label} className={`verification-checklist__item ${item.complete ? "is-complete" : ""}`.trim()}>
          <span aria-hidden="true">{item.complete ? "OK" : "!"}</span>
          <div>
            <strong>{item.label}</strong>
            <small>{item.detail}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

type StateViewVariant = "empty" | "loading" | "error" | "restricted";

interface StateViewAction {
  label: string;
  onClick: () => void;
  tone?: "primary" | "ghost";
}

function StateViewIcon(props: { variant: StateViewVariant }): ReactElement {
  if (props.variant === "loading") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
        <path d="M12 3 a9 9 0 1 0 9 9" />
      </svg>
    );
  }
  if (props.variant === "error") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.3 3.9 1.9 18.4 A2 2 0 0 0 3.6 21.4 H20.4 A2 2 0 0 0 22.1 18.4 L13.7 3.9 A2 2 0 0 0 10.3 3.9 Z" />
        <path d="M12 9 V13" />
        <path d="M12 17 H12.01" />
      </svg>
    );
  }
  if (props.variant === "restricted") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
        <path d="M8 10.5 V7 A4 4 0 0 1 16 7 V10.5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="10.5" cy="10.5" r="6" />
      <path d="M20 20 L15 15" />
    </svg>
  );
}

function StateView(props: {
  variant?: StateViewVariant;
  size?: "default" | "compact";
  title: string;
  description?: string;
  icon?: ReactElement;
  action?: StateViewAction;
  secondaryAction?: StateViewAction;
}): ReactElement {
  const variant: StateViewVariant = props.variant ?? "empty";
  const size = props.size ?? "default";
  const content = (
    <>
      <div className="state-view__icon" aria-hidden="true">
        {props.icon ?? <StateViewIcon variant={variant} />}
      </div>
      <div className="state-view__copy">
        <strong className="state-view__title">{props.title}</strong>
        {props.description ? <p className="state-view__description">{props.description}</p> : null}
      </div>
      {props.action || props.secondaryAction ? (
        <div className="state-view__actions">
          {props.action ? (
            <button
              className={`btn btn--${props.action.tone ?? "primary"}`}
              type="button"
              onClick={props.action.onClick}
            >
              {props.action.label}
            </button>
          ) : null}
          {props.secondaryAction ? (
            <button
              className={`btn btn--${props.secondaryAction.tone ?? "ghost"}`}
              type="button"
              onClick={props.secondaryAction.onClick}
            >
              {props.secondaryAction.label}
            </button>
          ) : null}
        </div>
      ) : null}
    </>
  );
  if (variant === "loading") {
    return (
      <div className={`state-view state-view--${variant} state-view--${size}`} role="status" aria-live="polite">
        {content}
      </div>
    );
  }
  if (variant === "error") {
    return (
      <div className={`state-view state-view--${variant} state-view--${size}`} role="alert">
        {content}
      </div>
    );
  }
  return <div className={`state-view state-view--${variant} state-view--${size}`}>{content}</div>;
}

function workflowVariantForTone(tone: OperationalSignal["tone"]): "verify" | "follow-up" | "proceed" | "cancel" | "muted" {
  if (tone === "critical") {
    return "cancel";
  }
  if (tone === "warn") {
    return "follow-up";
  }
  if (tone === "success") {
    return "proceed";
  }
  if (tone === "cyan") {
    return "verify";
  }
  return "muted";
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

function CompactDetectionSnapshot(props: {
  dataSource: DataSource;
  detectionId?: string;
  plate: string;
  vehicle: string;
}): ReactElement {
  const plateCropUrl = useDetectionPlateCropImage(props.detectionId, props.dataSource === "live");

  return (
    <div className="compact-detection-snapshot" aria-hidden="true">
      {plateCropUrl ? <img alt="" src={plateCropUrl} /> : <span>{props.plate || props.vehicle}</span>}
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
  const gpsFix = useBrowserGeolocation();
  const [screen, setScreen] = useState<AppScreen>("console");
  const [lastOperationsScreen, setLastOperationsScreen] = useState<AppScreen>("console");
  const [lastAdminScreen, setLastAdminScreen] = useState<AppScreen>("accounts");
  const [stageView, setStageView] = useState<StageView>("map");
  const [selectedCameraId, setSelectedCameraId] = useState<string>("");
  const [selectedDetectionId, setSelectedDetectionId] = useState<string | null>(null);
  const [detailDetectionId, setDetailDetectionId] = useState<string | null>(null);
  const [detailImageUrl, setDetailImageUrl] = useState<string | null>(null);
  const [settings, setSettings] = useState<UiSettings>(() => loadStoredSettings());
  const [dashboardConfig, setDashboardConfig] = useState<DashboardConfig>(() => loadDashboardConfig());
  const [dashboardCustomizeOpen, setDashboardCustomizeOpen] = useState(false);
  const [actionSheetRow, setActionSheetRow] = useState<ConsoleDetectionRow | null>(null);
  const [apiKey, setApiKey] = useState<string>(() => loadStoredString(apiKeyStorageKey));
  const [apiKeyInput, setApiKeyInput] = useState<string>(() => loadStoredString(apiKeyStorageKey));
  const [activeDestination, setActiveDestination] = useState<string>(() => loadStoredString(targetAddressStorageKey));
  const [activeDestinationCoords, setActiveDestinationCoords] = useState<DestinationCoords | null>(() => loadStoredCoords(targetCoordsStorageKey));
  const [destinationInput, setDestinationInput] = useState<string>(() => loadStoredString(targetAddressStorageKey));
  const [destinationDraftCoords, setDestinationDraftCoords] = useState<DestinationCoords | null>(() => loadStoredCoords(targetCoordsStorageKey));
  const [destinationInitialInput, setDestinationInitialInput] = useState<string>("");
  const [destinationModalOpen, setDestinationModalOpen] = useState(false);
  const [recentDestinations, setRecentDestinations] = useState<RecentDestination[]>(() => loadRecentDestinations());
  const [mapLayerMenuOpen, setMapLayerMenuOpen] = useState(false);
  const [navigationActive, setNavigationActive] = useState(false);
  const [dataSource, setDataSource] = useState<DataSource>("demo");
  const [overview, setOverview] = useState<DashboardOverviewResponse | null>(null);
  const [edgeRuntime, setEdgeRuntime] = useState<EdgeRuntimeStatus | null>(null);
  const [edgeRuntimeError, setEdgeRuntimeError] = useState<string | null>(null);
  const [edgeRuntimeAction, setEdgeRuntimeAction] = useState<EdgeRuntimeCommand | null>(null);
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
  const [searchSelectedDetectionId, setSearchSelectedDetectionId] = useState<string | null>(null);
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
  const [followUpSaving, setFollowUpSaving] = useState(false);
  const [followUpError, setFollowUpError] = useState<string | null>(null);
  const [followUpMessage, setFollowUpMessage] = useState<string | null>(null);
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [alertResponseNotes, setAlertResponseNotes] = useState("");
  const [hotlistsTab, setHotlistsTab] = useState<HotlistsWorkspaceTab>("alerts");
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
    if (typeof window === "undefined") return;
    if (activeDestinationCoords) {
      window.localStorage.setItem(targetCoordsStorageKey, JSON.stringify(activeDestinationCoords));
    } else {
      window.localStorage.removeItem(targetCoordsStorageKey);
    }
  }, [activeDestinationCoords]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(recentDestinationsStorageKey, JSON.stringify(recentDestinations));
  }, [recentDestinations]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadLiveData(): Promise<void> {
      try {
        const [nextOverview, nextHotlists, nextEdgeRuntime] = await Promise.all([
          fetchDashboardOverview(controller.signal),
          fetchHotlists(controller.signal),
          fetchEdgeRuntimeStatus(controller.signal),
        ]);

        if (controller.signal.aborted) {
          return;
        }

        setOverview(nextOverview);
        setEdgeRuntime(nextEdgeRuntime);
        setEdgeRuntimeError(null);
        setHotlists(nextHotlists.length > 0 ? nextHotlists : seedHotlists);
        setLocalFollowUps([]);
        setDataSource("live");
        setDataError(null);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        setOverview(null);
        setEdgeRuntime(null);
        setEdgeRuntimeError(error instanceof Error ? error.message : "Unable to load edge runtime status.");
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

  const availableCameraFeeds = useMemo(
    () => buildCameraUiFeeds(allRows, dataSource, overview?.camera_health),
    [allRows, dataSource, overview?.camera_health],
  );

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
    if (searchResults.length === 0) {
      if (searchSelectedDetectionId) {
        setSearchSelectedDetectionId(null);
      }
      return;
    }

    const currentSearchRowStillExists = searchSelectedDetectionId
      ? searchResults.some((row) => row.id === searchSelectedDetectionId)
      : false;
    if (currentSearchRowStillExists) {
      return;
    }

    const selectedConsoleRow =
      selectedDetectionId ? searchResults.find((row) => row.id === selectedDetectionId) ?? null : null;
    const nextSearchRow = selectedConsoleRow ?? searchResults[0] ?? null;
    setSearchSelectedDetectionId(nextSearchRow?.id ?? null);
  }, [searchResults, searchSelectedDetectionId, selectedDetectionId]);

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
  const primaryCameraId = currentCamera?.id ?? selectedRow?.cameraId ?? selectedCameraId;
  const cameraRows = allRows.filter((row) => row.cameraId === primaryCameraId);
  const cameraFocusRow = cameraRows[0] ?? selectedRow;
  const unitPosition = gpsFixToCoords(gpsFix) ?? routeStart;
  const liveAddress = useLiveReverseAddress(gpsFixToCoords(gpsFix));
  const activeRouteFeet = activeDestinationCoords ? haversineFeet(unitPosition, activeDestinationCoords) : null;
  const routePath = activeDestinationCoords ? buildRoutePath(unitPosition, activeDestinationCoords) : [];
  const withinRadius = navigationActive && activeRouteFeet != null && activeRouteFeet <= settings.arrivalRadiusFeet;
  const idleScanEnabled = !navigationActive && settings.arrivalScanEnabled;
  const scanSession = resolveScanSessionState({
    navigationActive,
    arrivalScanEnabled: settings.arrivalScanEnabled,
    withinRadius,
    activeRouteFeet,
  });
  const totalReads = overview?.counts.recent_detections ?? 142;
  const activeAlerts = overview?.counts.active_alerts ?? allRows.filter((row) => row.hotlist).length;
  const activeSessions = overview?.counts.active_sessions ?? 3;
  const followUps = overview?.follow_ups ?? localFollowUps;
  const openFollowUps = overview?.counts.open_follow_ups ?? followUps.filter((item) => item.status !== "resolved").length;
  const onlineCameraCount = availableCameraFeeds.filter((feed) => feed.status === "Online").length;
  const activeHotlistCount = hotlists.filter((entry) => entry.active).length;
  const routeStatusLabel = !navigationActive
    ? idleScanEnabled
      ? "Manual scan armed"
      : "Route idle"
    : activeDestinationCoords == null
      ? "Route pending coordinates"
    : withinRadius
      ? settings.autoArrivalScan
        ? "Within radius - auto scan"
        : "Within radius - scan off"
      : "Routing";
  const routeEta = activeRouteFeet != null ? formatEta(activeRouteFeet, navigationActive) : navigationActive ? "Resolve loc" : "Standby";
  const routeDistance = activeRouteFeet != null ? formatDistance(activeRouteFeet) : navigationActive ? "Pending" : "--";
  const navigationGuidance = buildNavigationGuidance({
    active: navigationActive,
    destination: activeDestination,
    destinationCoords: activeDestinationCoords,
    routePath,
    unitPosition,
    gpsFix,
    routeDistance,
    routeEta,
    routeFeet: activeRouteFeet,
    arrivalRadiusFeet: settings.arrivalRadiusFeet,
  });
  const detailTimeline = detailRow ? allRows.filter((row) => normalizePlate(row.plate1) === normalizePlate(detailRow.plate1)) : [];
  const groupedSearchResults = searchGroupByPlate ? buildPlateGroups(searchResults) : [];
  const hotlistWarning = !settings.hotlistAlerts || !settings.soundEnabled;
  const serviceHealthState = resolveServiceHealthState(overview?.health.state, dataSource);
  const degradedDependencyCount = overview?.health.dependencies.filter((dependency) => dependency.state !== "ok").length ?? 0;
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

  useEffect(() => {
    if (dataSource !== "live") {
      return;
    }

    const controller = new AbortController();
    const overlayAlertId =
      screen !== "hotlists" && hotlistOverlayId
        ? (overview?.alerts ?? []).find((alert) => alert.detection_id === hotlistOverlayId.replace(/^live-/, ""))?.alert_id
        : undefined;

    async function sendScanHeartbeat(): Promise<void> {
      try {
        await sendOperatorSessionHeartbeat(
          {
            session_id: operatorSessionId,
            client_label: "reposcan-ops-console",
            workspace: screen,
            selected_detection_id: selectedDetectionId ?? undefined,
            selected_alert_id: screen === "hotlists" ? selectedAlertId ?? undefined : overlayAlertId,
            destination_label: activeDestination || undefined,
            arrival_radius_feet: settings.arrivalRadiusFeet,
            current_distance_feet: activeRouteFeet ?? undefined,
            idle_scan_enabled: idleScanEnabled,
            visible_map_layers: [
              settings.showActiveAlertPins ? "active_alerts" : null,
              settings.showHistoricalAlertPins ? "historical_alerts" : null,
              settings.showDetectionPins ? "detections" : null,
              settings.showRadiusRing ? "arrival_ring" : null,
            ].filter((value): value is string => value !== null),
            navigation_active: navigationActive,
            scan_state: scanSession.state,
            scan_processing_mode: scanSession.mode,
            lpr_realtime_enabled: scanSession.lprRealtime,
            vehicle_enrichment_deferred: true,
            primary_ai_camera_id: primaryCameraId || undefined,
            secondary_context_camera_id: availableCameraFeeds.find((feed) => feed.id !== primaryCameraId)?.id,
          },
          controller.signal,
        );
      } catch {
        // Presence and scan-state heartbeats are best-effort.
      }
    }

    void sendScanHeartbeat();
    const intervalId = setInterval(() => void sendScanHeartbeat(), 30_000);

    return () => {
      controller.abort();
      clearInterval(intervalId);
    };
  }, [
    activeDestination,
    activeRouteFeet,
    availableCameraFeeds,
    dataSource,
    hotlistOverlayId,
    idleScanEnabled,
    navigationActive,
    operatorSessionId,
    overview?.alerts,
    primaryCameraId,
    scanSession.lprRealtime,
    scanSession.mode,
    scanSession.state,
    screen,
    selectedAlertId,
    selectedDetectionId,
    settings.arrivalRadiusFeet,
    settings.showActiveAlertPins,
    settings.showDetectionPins,
    settings.showHistoricalAlertPins,
    settings.showRadiusRing,
  ]);
  const mapAlertMarkers = useMemo<MapAlertMarker[]>(
    () => {
      const liveMarkers = hotlistAlertItems.flatMap(({ alert, row }) => {
        const latitude = row?.lat ?? alert.gps_latitude;
        const longitude = row?.lng ?? alert.gps_longitude;
        if (latitude == null || longitude == null) {
          return [];
        }

        return [
          {
            id: `map-alert-${alert.alert_id}`,
            alertId: alert.alert_id,
            plate: row?.plate1 ?? (normalizePlate(alert.matched_plate_text) || "UNKNOWN"),
            label: row?.vehicle ?? alert.hotlist_label ?? "Recovery case",
            camera: row?.source ?? buildCameraDisplayName(alert.camera_id),
            lat: latitude,
            lng: longitude,
            status: alert.status,
            timestampUtc: alert.updated_at_utc ?? alert.timestamp_utc,
          },
        ];
      });

      const knownMarkerIds = new Set(liveMarkers.map((marker) => marker.id));
      const fallbackMarkers = allRows.flatMap((row) =>
        row.alertStatus
          ? [
              {
                id: `map-alert-${row.alertId ?? row.id}`,
                alertId: row.alertId ?? row.id,
                plate: row.plate1,
                label: row.vehicle,
                camera: row.source,
                lat: row.lat,
                lng: row.lng,
                status: row.alertStatus,
                timestampUtc: row.timestampUtc,
              },
            ]
          : [],
      );

      return [...liveMarkers, ...fallbackMarkers.filter((marker) => !knownMarkerIds.has(marker.id))];
    },
    [hotlistAlertItems, allRows],
  );
  const destinationTargets = useMemo<DestinationTarget[]>(() => {
    const targets: DestinationTarget[] = [];
    const now = Date.now();

    const latestAlert = hotlistAlertItems.find(({ row, alert }) => {
      const linkedEntry = hotlists.find((entry) => entry.entry_id === alert.hotlist_entry_id);
      const hasCoords =
        (row?.lat != null && row?.lng != null) ||
        (alert.gps_latitude != null && alert.gps_longitude != null) ||
        (linkedEntry?.address_latitude != null && linkedEntry?.address_longitude != null);
      return hasCoords;
    });
    if (latestAlert) {
      const { alert, row } = latestAlert;
      const linkedEntry = hotlists.find((entry) => entry.entry_id === alert.hotlist_entry_id) ?? null;
      const lat = row?.lat ?? alert.gps_latitude ?? linkedEntry?.address_latitude ?? null;
      const lng = row?.lng ?? alert.gps_longitude ?? linkedEntry?.address_longitude ?? null;
      const addressFromEntry = linkedEntry
        ? [linkedEntry.address_line1, linkedEntry.address_city, linkedEntry.address_state]
            .filter((value): value is string => Boolean(value && value.trim()))
            .join(", ")
        : "";
      const fallbackAddress = row ? `${row.plate1} • ${row.source}` : alert.hotlist_label ?? "Latest alert";
      const plate = row?.plate1 ?? normalizePlate(alert.matched_plate_text);
      targets.push({
        id: `target-alert-${alert.alert_id}`,
        source: "alert",
        address: addressFromEntry || fallbackAddress,
        label: plate ? `Last alert • ${plate}` : "Last alert",
        subtitle: alert.hotlist_label ?? (row ? row.vehicle : undefined),
        coords: typeof lat === "number" && typeof lng === "number" ? { lat, lng } : null,
        accent: "critical",
        relativeTime: formatRelativeTime(alert.updated_at_utc ?? alert.timestamp_utc, now),
      });
    }

    const latestRow = allRows.find((row) => typeof row.lat === "number" && typeof row.lng === "number");
    if (latestRow) {
      targets.push({
        id: `target-read-${latestRow.id}`,
        source: "read",
        address: latestRow.gps || `${latestRow.lat.toFixed(5)}, ${latestRow.lng.toFixed(5)}`,
        label: `Last read • ${latestRow.plate1}`,
        subtitle: latestRow.source,
        coords: { lat: latestRow.lat, lng: latestRow.lng },
        accent: "cyan",
        relativeTime: formatRelativeTime(latestRow.timestampUtc, now),
      });
    }

    const activeHotlistsWithAddress = hotlists.filter(
      (entry) => entry.active && (entry.address_line1 || entry.address_label),
    );
    for (const entry of activeHotlistsWithAddress.slice(0, 4)) {
      const parts = [entry.address_line1, entry.address_city, entry.address_state]
        .filter((value): value is string => Boolean(value && value.trim()));
      const address = parts.length > 0 ? parts.join(", ") : entry.address_label ?? "";
      if (!address) continue;
      const lat = entry.address_latitude;
      const lng = entry.address_longitude;
      const plate = normalizePlate(entry.plate_text);
      targets.push({
        id: `target-account-${entry.entry_id}`,
        source: "account",
        address,
        label: entry.address_label ?? (plate ? `Account • ${plate}` : "Account address"),
        subtitle: plate || hotlistIdentifierSummary(entry),
        coords: typeof lat === "number" && typeof lng === "number" ? { lat, lng } : null,
        accent: "warn",
      });
    }

    for (const entry of recentDestinations) {
      targets.push({
        id: `target-recent-${entry.id}`,
        source: "recent",
        address: entry.address,
        label: entry.label ?? "Recent",
        subtitle: formatRelativeTime(entry.lastUsedAtUtc, now),
        coords: entry.coords,
        accent: "muted",
        relativeTime: formatRelativeTime(entry.lastUsedAtUtc, now),
      });
    }

    const seen = new Set<string>();
    return targets.filter((target) => {
      const key = target.address.trim().toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [hotlistAlertItems, allRows, hotlists, recentDestinations]);

  const destinationPreview = useMemo(() => {
    if (!destinationDraftCoords) return null;
    const feet = haversineFeet(unitPosition, destinationDraftCoords);
    return {
      distance: formatDistance(feet),
      eta: formatEta(feet, true),
      feet,
    };
  }, [destinationDraftCoords, unitPosition]);

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
  const canViewAudit = dataSource === "live" && overview?.current_principal.capabilities.can_view_audit === true;
  const currentPrincipal = overview?.current_principal ?? null;
  const activeSessionRecords = overview?.active_sessions ?? [];

  async function handleEdgeRuntimeCommand(command: EdgeRuntimeCommand): Promise<void> {
    if (dataSource !== "live") {
      setEdgeRuntimeError("Edge controls require the live API.");
      return;
    }

    setEdgeRuntimeAction(command);
    setEdgeRuntimeError(null);
    try {
      const updated = await sendEdgeRuntimeCommand({
        command,
        operator_id: currentPrincipal?.principal_id ?? "local-operator",
      });
      setEdgeRuntime(updated);
      setRefreshToken((value) => value + 1);
    } catch (error) {
      setEdgeRuntimeError(error instanceof Error ? error.message : "Unable to command the edge runtime.");
    } finally {
      setEdgeRuntimeAction(null);
    }
  }

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
    if (nextScreen !== "console") {
      setDashboardCustomizeOpen(false);
    }
    if (shellForScreen(nextScreen) === "operations") {
      setLastOperationsScreen(nextScreen);
    } else {
      setLastAdminScreen(nextScreen);
    }
    startTransition(() => setScreen(nextScreen));
  }

  function switchShell(nextShell: AppShell): void {
    switchScreen(nextShell === "operations" ? lastOperationsScreen : lastAdminScreen);
  }

  function updateSetting<Key extends keyof UiSettings>(key: Key, value: UiSettings[Key]): void {
    setSettings((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function handleDashboardModeChange(mode: DashboardLayoutMode): void {
    setDashboardConfig((current) => updateLayoutMode(current, mode));
  }

  function handleDashboardWidgetVisibility(widgetId: DashboardWidgetId, visible: boolean): void {
    setDashboardConfig((current) => updateWidgetVisibility(current, widgetId, visible));
  }

  function handleDashboardWidgetSize(widgetId: DashboardWidgetId, size: DashboardWidgetSize): void {
    setDashboardConfig((current) => updateWidgetSize(current, widgetId, size));
  }

  function handleDashboardWidgetMove(sourceWidgetId: DashboardWidgetId, targetWidgetId: DashboardWidgetId): void {
    setDashboardConfig((current) => reorderDashboardWidget(current, sourceWidgetId, targetWidgetId));
  }

  function handleDashboardReset(): void {
    setDashboardConfig(resetDashboardConfig());
  }

  // Global Ctrl+1..5 shortcuts for dashboard layout modes. The polish review
  // calls this out so an operator who drives all day can switch layouts with
  // one keypress instead of opening the customize panel.
  useEffect(() => {
    const modeShortcuts: Record<string, DashboardLayoutMode> = {
      "1": "default",
      "2": "driving",
      "3": "scanning",
      "4": "review",
      "5": "minimal",
    };
    function handleLayoutShortcut(event: KeyboardEvent): void {
      if (!event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) {
        return;
      }
      const target = event.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable) {
          return;
        }
      }
      const mode = modeShortcuts[event.key];
      if (!mode) {
        return;
      }
      event.preventDefault();
      handleDashboardModeChange(mode);
    }
    window.addEventListener("keydown", handleLayoutShortcut);
    return () => window.removeEventListener("keydown", handleLayoutShortcut);
  }, []);

  function rememberDestination(address: string, coords: DestinationCoords | null, label?: string): void {
    const trimmed = address.trim();
    if (!trimmed) return;
    const nextEntry: RecentDestination = {
      id: `rd_${trimmed.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 48)}_${Date.now().toString(36)}`,
      address: trimmed,
      label,
      coords,
      lastUsedAtUtc: new Date().toISOString(),
    };
    setRecentDestinations((current) => {
      const deduped = current.filter((entry) => entry.address.trim().toLowerCase() !== trimmed.toLowerCase());
      return [nextEntry, ...deduped].slice(0, recentDestinationsLimit);
    });
  }

  function applyDestinationTarget(target: DestinationTarget): void {
    setDestinationInput(target.address);
    setDestinationDraftCoords(target.coords);
  }

  function selectGeocodedAddress(address: string, coords: DestinationCoords): void {
    setDestinationInput(address);
    setDestinationDraftCoords(coords);
  }

  function handleDestinationInputChange(value: string): void {
    const trimmed = value.trim();
    setDestinationInput(value);
    if (!trimmed) {
      setDestinationDraftCoords(null);
      return;
    }

    const normalizedValue = trimmed.toLowerCase();
    const matchedTarget = destinationTargets.find((target) => target.address.trim().toLowerCase() === normalizedValue);
    if (matchedTarget) {
      setDestinationDraftCoords(matchedTarget.coords);
      return;
    }

    if (normalizedValue === activeDestination.trim().toLowerCase()) {
      setDestinationDraftCoords(activeDestinationCoords);
      return;
    }

    setDestinationDraftCoords(null);
  }

  function clearDestinationDraft(): void {
    setDestinationInput("");
    setDestinationDraftCoords(null);
  }

  function removeRecentDestination(id: string): void {
    setRecentDestinations((current) => current.filter((entry) => entry.id !== id));
  }

  function openDestinationModal(): void {
    const initial = activeDestination || "";
    setDestinationInput(initial);
    setDestinationDraftCoords(activeDestinationCoords);
    setDestinationInitialInput(initial);
    setMapLayerMenuOpen(false);
    setStageView("map");
    switchScreen("console");
    setDestinationModalOpen(true);
  }

  function closeDestinationModal(): void {
    const currentTrim = destinationInput.trim();
    const initialTrim = destinationInitialInput.trim();
    if (currentTrim && currentTrim !== initialTrim) {
      const confirmed =
        typeof window === "undefined"
          ? true
          : window.confirm("Discard the destination you just entered?");
      if (!confirmed) return;
    }
    setDestinationModalOpen(false);
    setDestinationInput(activeDestination);
    setDestinationDraftCoords(activeDestinationCoords);
  }

  function stageDestination(): void {
    const nextDestination = destinationInput.trim();
    if (!nextDestination) return;
    setActiveDestination(nextDestination);
    setActiveDestinationCoords(destinationDraftCoords);
    setDestinationInput(nextDestination);
    setDestinationInitialInput(nextDestination);
    rememberDestination(nextDestination, destinationDraftCoords);
    setMapLayerMenuOpen(false);
    setDestinationModalOpen(false);
    setStageView("map");
    switchScreen("console");
  }

  function stageResolvedDestination(address: string, coords: DestinationCoords): void {
    const nextDestination = address.trim();
    if (!nextDestination) return;
    setActiveDestination(nextDestination);
    setActiveDestinationCoords(coords);
    setDestinationInput(nextDestination);
    setDestinationDraftCoords(coords);
    setDestinationInitialInput(nextDestination);
    rememberDestination(nextDestination, coords);
    setMapLayerMenuOpen(false);
    setDestinationModalOpen(false);
    setStageView("map");
    switchScreen("console");
  }

  function startRoute(): void {
    const nextDestination = destinationInput.trim() || activeDestination;
    if (!nextDestination) return;
    const nextCoords = destinationDraftCoords ?? activeDestinationCoords;
    if (!nextCoords) return;
    setActiveDestination(nextDestination);
    setActiveDestinationCoords(nextCoords);
    setDestinationInput(nextDestination);
    setDestinationInitialInput(nextDestination);
    rememberDestination(nextDestination, nextCoords);
    setMapLayerMenuOpen(false);
    setDestinationModalOpen(false);
    setNavigationActive(true);
    setStageView("map");
    switchScreen("console");
  }

  function startResolvedRoute(address: string, coords: DestinationCoords): void {
    const nextDestination = address.trim();
    if (!nextDestination) return;
    setActiveDestination(nextDestination);
    setActiveDestinationCoords(coords);
    setDestinationInput(nextDestination);
    setDestinationDraftCoords(coords);
    setDestinationInitialInput(nextDestination);
    rememberDestination(nextDestination, coords);
    setMapLayerMenuOpen(false);
    setDestinationModalOpen(false);
    setNavigationActive(true);
    setStageView("map");
    switchScreen("console");
  }

  function endRoute(): void {
    setMapLayerMenuOpen(false);
    setNavigationActive(false);
    setStageView("map");
    switchScreen("console");
  }

  function armIdleScan(): void {
    setSettings((current) => ({
      ...current,
      arrivalScanEnabled: !current.arrivalScanEnabled,
    }));
    setMapLayerMenuOpen(false);
    setDestinationModalOpen(false);
    setNavigationActive(false);
    setStageView("map");
    switchScreen("console");
  }

  function openDetail(row: ConsoleDetectionRow): void {
    setSelectedDetectionId(row.id);
    setDetailDetectionId(row.id);
  }

  function focusSearchRow(rowId: string): void {
    setSearchSelectedDetectionId(rowId);
    setSelectedDetectionId(rowId);
  }

  function openSearchDetail(row: ConsoleDetectionRow): void {
    setSearchSelectedDetectionId(row.id);
    openDetail(row);
  }

  function routeSearchRow(row: ConsoleDetectionRow): void {
    setSearchSelectedDetectionId(row.id);
    routeToRow(row);
  }

  function openSearchAccount(row: ConsoleDetectionRow): void {
    setSearchSelectedDetectionId(row.id);
    openAccountsForRow(row);
  }

  function routeToRow(row: ConsoleDetectionRow): void {
    setSelectedDetectionId(row.id);
    if (typeof row.lat === "number" && typeof row.lng === "number") {
      const destinationAddress = row.gps || `${row.lat.toFixed(5)}, ${row.lng.toFixed(5)}`;
      const destinationCoords = { lat: row.lat, lng: row.lng };
      setActiveDestination(destinationAddress);
      setActiveDestinationCoords(destinationCoords);
      setDestinationInput(destinationAddress);
      setDestinationDraftCoords(destinationCoords);
      setDestinationInitialInput(destinationAddress);
      rememberDestination(destinationAddress, destinationCoords, `Last seen - ${row.plate1}`);
      setNavigationActive(true);
    } else {
      setNavigationActive(false);
    }
    setMapLayerMenuOpen(false);
    setDestinationModalOpen(false);
    setStageView("map");
    switchScreen("console");
  }

  function centerMapOnRow(row: ConsoleDetectionRow): void {
    setSelectedDetectionId(row.id);
    setStageView("map");
    switchScreen("console");
  }

  function openAccountsForRow(row: ConsoleDetectionRow): void {
    setSelectedDetectionId(row.id);
    beginHotlistDraft(row.plate1);
    switchScreen("accounts");
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

  function routeToDetectionId(detectionId: string | null | undefined): void {
    if (!detectionId) {
      return;
    }
    const row = allRows.find((item) => item.detectionId === detectionId);
    if (!row) {
      return;
    }
    routeToRow(row);
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
      setHotlistsTab("alerts");
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

  async function runSearch(): Promise<void> {
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

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await runSearch();
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
    const nextVin = normalizeUpperValue(entry?.vin ?? hotlistDraft.vin);
    const nextVehicleYear = trimValue(entry?.vehicle_year ?? hotlistDraft.vehicleYear);
    const nextVehicleMake = trimValue(entry?.vehicle_make ?? hotlistDraft.vehicleMake);
    const nextVehicleModel = trimValue(entry?.vehicle_model ?? hotlistDraft.vehicleModel);
    const nextVehicleColor = trimValue(entry?.vehicle_color ?? hotlistDraft.vehicleColor);
    const nextAddressLabel = trimValue(entry?.address_label ?? hotlistDraft.addressLabel);
    const nextAddressLine1 = trimValue(entry?.address_line1 ?? hotlistDraft.addressLine1);
    const nextAddressLine2 = trimValue(entry?.address_line2 ?? hotlistDraft.addressLine2);
    const nextAddressCity = trimValue(entry?.address_city ?? hotlistDraft.addressCity);
    const nextAddressState = normalizeUpperValue(entry?.address_state ?? hotlistDraft.addressState);
    const nextAddressPostalCode = trimValue(entry?.address_postal_code ?? hotlistDraft.addressPostalCode);
    const nextLabel = trimValue(entry?.label ?? hotlistDraft.label);
    const nextNotes = trimValue(entry?.notes ?? hotlistDraft.notes);
    const nextActive = activeOverride ?? entry?.active ?? hotlistDraft.active;
    const hasVehicleProfile = Boolean(nextVehicleMake && nextVehicleModel);

    if (!nextPlateText && !nextVin && !hasVehicleProfile) {
      setHotlistError("Add a plate, VIN, or vehicle make and model before saving this account.");
      return;
    }

    try {
      setHotlistSaving(true);
      setHotlistError(null);
      setHotlistMessage(null);

      if (dataSource === "live") {
        if (entry) {
          await updateHotlist(entry.entry_id, {
            plate_text: nextPlateText || undefined,
            vin: nextVin || undefined,
            vehicle_year: nextVehicleYear || undefined,
            vehicle_make: nextVehicleMake || undefined,
            vehicle_model: nextVehicleModel || undefined,
            vehicle_color: nextVehicleColor || undefined,
            address_label: nextAddressLabel || undefined,
            address_line1: nextAddressLine1 || undefined,
            address_line2: nextAddressLine2 || undefined,
            address_city: nextAddressCity || undefined,
            address_state: nextAddressState || undefined,
            address_postal_code: nextAddressPostalCode || undefined,
            label: nextLabel || undefined,
            notes: nextNotes || undefined,
            active: nextActive,
          });
        } else {
          const created = await createHotlist({
            plate_text: nextPlateText || undefined,
            vin: nextVin || undefined,
            vehicle_year: nextVehicleYear || undefined,
            vehicle_make: nextVehicleMake || undefined,
            vehicle_model: nextVehicleModel || undefined,
            vehicle_color: nextVehicleColor || undefined,
            address_label: nextAddressLabel || undefined,
            address_line1: nextAddressLine1 || undefined,
            address_line2: nextAddressLine2 || undefined,
            address_city: nextAddressCity || undefined,
            address_state: nextAddressState || undefined,
            address_postal_code: nextAddressPostalCode || undefined,
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
                    plate_text: nextPlateText || null,
                    vin: nextVin || null,
                    vehicle_year: nextVehicleYear || null,
                    vehicle_make: nextVehicleMake || null,
                    vehicle_model: nextVehicleModel || null,
                    vehicle_color: nextVehicleColor || null,
                    address_label: nextAddressLabel || null,
                    address_line1: nextAddressLine1 || null,
                    address_line2: nextAddressLine2 || null,
                    address_city: nextAddressCity || null,
                    address_state: nextAddressState || null,
                    address_postal_code: nextAddressPostalCode || null,
                    address_latitude: item.address_latitude ?? null,
                    address_longitude: item.address_longitude ?? null,
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
            plate_text: nextPlateText || null,
            vin: nextVin || null,
            vehicle_year: nextVehicleYear || null,
            vehicle_make: nextVehicleMake || null,
            vehicle_model: nextVehicleModel || null,
            vehicle_color: nextVehicleColor || null,
            address_label: nextAddressLabel || null,
            address_line1: nextAddressLine1 || null,
            address_line2: nextAddressLine2 || null,
            address_city: nextAddressCity || null,
            address_state: nextAddressState || null,
            address_postal_code: nextAddressPostalCode || null,
            address_latitude: null,
            address_longitude: null,
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

      if (action === "recover") {
        setHotlistMessage("Recovery account marked inactive.");
      } else if (!nextPlateText) {
        setHotlistMessage(entry ? "Recovery account updated. Add a plate to enable automatic plate alerts." : "Recovery account created. Add a plate to enable automatic plate alerts.");
      } else {
        setHotlistMessage(entry ? "Recovery account updated." : "Recovery account created.");
      }
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
          ? "Recovery match acknowledged."
          : status === "dismissed"
            ? "Recovery match dismissed."
            : "Recovery match reopened.",
      );
    } catch (error) {
      setAlertActionError(error instanceof Error ? error.message : "Unable to update the alert.");
    } finally {
      setAlertActionId(null);
    }
  }

  const gpsIndicator = buildGpsIndicator(gpsFix);
  const currentShell = shellForScreen(screen);
  const shellCopy =
    currentShell === "operations"
      ? {
          title: "Operations Workspace",
          detail: `${activeAlerts} live hit${activeAlerts === 1 ? "" : "s"} · ${activeHotlistCount} active order${activeHotlistCount === 1 ? "" : "s"} · ${onlineCameraCount}/${Math.max(availableCameraFeeds.length, 1)} camera${availableCameraFeeds.length === 1 ? "" : "s"} online`,
        }
      : {
          title: "Admin Panel",
          detail: `${hotlists.length} repo order${hotlists.length === 1 ? "" : "s"} · ${canManageHotlistAccounts ? "edit enabled" : "read only"} · ${degradedDependencyCount === 0 ? "system healthy" : `${degradedDependencyCount} system warning${degradedDependencyCount === 1 ? "" : "s"}`}`,
        };
  const toolbarItems: ToolbarItem[] =
    currentShell === "operations"
      ? [
          {
            id: "workspace",
            label: "Workspace",
            value: screen === "console" ? "ACTIVE" : "READY",
            tone: screen === "console" ? "cyan" : "gray",
            active: screen === "console",
            onClick: () => switchScreen("console"),
          },
          {
            id: "map",
            label: "Map",
            value: navigationActive ? "ROUTING" : screen === "console" && stageView === "map" ? "ACTIVE" : "READY",
            tone: navigationActive ? "green" : screen === "console" && stageView === "map" ? "cyan" : "gray",
            active: screen === "console" && stageView === "map",
            onClick: () => {
              setStageView("map");
              switchScreen("console");
            },
          },
          {
            id: "lpr-hits",
            label: "LPR Hits",
            value: activeAlerts > 0 ? `${activeAlerts} ACTIVE` : "READY",
            tone: activeAlerts > 0 ? "green" : "gray",
            active: screen === "hotlists",
            onClick: () => switchScreen("hotlists"),
          },
          {
            id: "search",
            label: "Search",
            value: totalReads > 0 ? `${Math.min(totalReads, 8)} INDEXED` : "READY",
            tone: totalReads > 0 ? "cyan" : "gray",
            active: screen === "search",
            onClick: () => switchScreen("search"),
          },
          {
            id: "cameras",
            label: "Cameras",
            value: onlineCameraCount > 0 ? "LIVE" : "OFFLINE",
            tone: onlineCameraCount > 0 ? "green" : "gray",
            active: screen === "console" && stageView === "camera",
            onClick: () => {
              setStageView("camera");
              switchScreen("console");
            },
          },
          {
            id: "scan",
            label: "Scan LPR",
            value: navigationActive ? "SCANNING" : scanSession.lprRealtime || idleScanEnabled ? "ON" : "READY",
            tone: navigationActive || scanSession.lprRealtime || idleScanEnabled ? "green" : "gray",
            active: navigationActive || idleScanEnabled,
            onClick: () => armIdleScan(),
          },
        ]
      : [
          {
            id: "repo-orders",
            label: "Repo Orders",
            value: activeHotlistCount > 0 ? `${activeHotlistCount} ACTIVE` : "READY",
            tone: activeHotlistCount > 0 ? "cyan" : "gray",
            active: screen === "accounts",
            onClick: () => switchScreen("accounts"),
          },
          {
            id: "field-settings",
            label: "Field Settings",
            value: settings.autoArrivalScan ? "TUNED" : "REVIEW",
            tone: settings.autoArrivalScan ? "cyan" : "amber",
            active: screen === "settings" && settingsSection === "workspace",
            onClick: () => {
              setSettingsSection("workspace");
              switchScreen("settings");
            },
          },
          {
            id: "alerts",
            label: "Alerts",
            value: settings.hotlistAlerts ? "ARMED" : "MUTED",
            tone: settings.hotlistAlerts ? "green" : "gray",
            active: screen === "settings" && settingsSection === "alerts",
            onClick: () => {
              setSettingsSection("alerts");
              switchScreen("settings");
            },
          },
          {
            id: "audit",
            label: "Audit",
            value: canViewAudit ? (auditEvents.length > 0 ? `${Math.min(auditEvents.length, 9)} EVENTS` : "READY") : "LOCKED",
            tone: canViewAudit ? "purple" : "gray",
            active: screen === "settings" && settingsSection === "system",
            onClick: () => {
              setSettingsSection("system");
              switchScreen("settings");
            },
          },
          {
            id: "system",
            label: "System",
            value: dataSource === "live" ? gpsIndicator.value.toUpperCase() : dataSource.toUpperCase(),
            tone: dataSource === "live" ? (gpsIndicator.tone === "good" ? "green" : gpsIndicator.tone === "warn" ? "amber" : "gray") : "gray",
            active: screen === "settings" && settingsSection === "system",
            onClick: () => {
              setSettingsSection("system");
              switchScreen("settings");
            },
          },
        ];

  return (
    <>
      <div className="ops-app">
        <main className="workspace">
          {screen === "console" ? (
            <ConsoleScreen
              activeAlerts={activeAlerts}
              activeDestination={activeDestination}
              alertMarkers={mapAlertMarkers}
              allRows={allRows}
              cameraFeedsList={availableCameraFeeds}
              cameraFocusRow={cameraFocusRow}
              currentCamera={currentCamera}
              dataSource={dataSource}
              dashboardConfig={dashboardConfig}
              dashboardCustomizeOpen={dashboardCustomizeOpen}
              hotlists={hotlists}
              destinationCoords={activeDestinationCoords}
              destinationInput={destinationInput}
              destinationModalOpen={destinationModalOpen}
              destinationTargets={destinationTargets}
              destinationPreview={destinationPreview}
              followUps={followUps}
              recentDestinations={recentDestinations}
              idleScanEnabled={idleScanEnabled}
              layerMenuOpen={mapLayerMenuOpen}
              navigationActive={navigationActive}
              navigationGuidance={navigationGuidance}
              scanSessionState={scanSession.state}
              activeRouteFeet={activeRouteFeet}
              serviceHealthState={serviceHealthState}
              selectedCameraId={primaryCameraId}
              selectedDetectionId={selectedDetectionId}
              settings={settings}
              stageView={stageView}
              gpsFix={gpsFix}
              liveAddress={liveAddress}
              unitPosition={unitPosition}
              routeDistance={routeDistance}
              routeEta={routeEta}
              routePath={routePath}
              routeStatusLabel={routeStatusLabel}
              withinRadius={withinRadius}
              onApplyDestinationTarget={applyDestinationTarget}
              onClearDestinationDraft={clearDestinationDraft}
              onCloseDashboardCustomize={() => setDashboardCustomizeOpen(false)}
              onCloseDestinationModal={closeDestinationModal}
              onCopyPlate={handleCopyPlate}
              onDestinationChange={handleDestinationInputChange}
              onEndRoute={endRoute}
              onOpenAccount={openAccountsForRow}
              onOpenDashboardCustomize={() => setDashboardCustomizeOpen(true)}
              onOpenDetail={openDetail}
              onOpenDetectionActions={(row) => {
                setSelectedDetectionId(row.id);
                setActionSheetRow(row);
              }}
              onOpenDestinationModal={openDestinationModal}
              onOpenHotlist={(entry) => {
                loadHotlist(entry);
                switchScreen("accounts");
              }}
              onOpenRecoveries={() => switchScreen("hotlists")}
              onOpenSettings={() => {
                setSettingsSection("workspace");
                switchScreen("settings");
              }}
              onRemoveRecentDestination={removeRecentDestination}
              onResetDashboardConfig={handleDashboardReset}
              onSelectCamera={setSelectedCameraId}
              onSelectDetection={setSelectedDetectionId}
              onRouteToDetection={routeToRow}
              onSelectGeocodedAddress={selectGeocodedAddress}
              onStageResolvedDestination={stageResolvedDestination}
              onStageDestination={stageDestination}
              onStartResolvedRoute={startResolvedRoute}
              onStartRoute={startRoute}
              onStageViewChange={setStageView}
              onToggleActiveAlertPins={() => updateSetting("showActiveAlertPins", !settings.showActiveAlertPins)}
              onToggleDetectionPins={() => updateSetting("showDetectionPins", !settings.showDetectionPins)}
              onToggleHistoricalAlertPins={() => updateSetting("showHistoricalAlertPins", !settings.showHistoricalAlertPins)}
              onToggleLayerMenu={() => setMapLayerMenuOpen((current) => !current)}
              onToggleRadiusRing={() => updateSetting("showRadiusRing", !settings.showRadiusRing)}
              onUpdateDashboardLayoutMode={handleDashboardModeChange}
              onUpdateDashboardWidgetMove={handleDashboardWidgetMove}
              onUpdateDashboardWidgetSize={handleDashboardWidgetSize}
              onUpdateDashboardWidgetVisibility={handleDashboardWidgetVisibility}
            />
          ) : null}

          {screen === "search" ? (
            <SearchScreen
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
              onAddToHotlist={openSearchAccount}
              onClearFilters={clearSearchFilters}
              onCopyPlate={handleCopyPlate}
              onDetails={openSearchDetail}
              onMap={routeSearchRow}
              onRetrySearch={() => void runSearch()}
              onSelectDetection={focusSearchRow}
              onSearchSubmit={handleSearchSubmit}
              onToggleExpanded={(plate) =>
                setExpandedGroups((current) => ({
                  ...current,
                  [plate]: !(current[plate] ?? false),
                }))
              }
              setQuery={setSearchQuery}
              selectedDetectionId={searchSelectedDetectionId}
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

          {screen === "accounts" ? (
            <AccountsScreen
              activeDestination={activeDestination}
              canManageAccounts={canManageHotlistAccounts}
              dataSource={dataSource}
              deleting={hotlistDeleting}
              draft={hotlistDraft}
              error={hotlistError}
              hotlists={hotlists}
              message={hotlistMessage}
              saving={hotlistSaving}
              selectedDetectionPlate={selectedRow?.plate1 ?? ""}
              selectedHotlistId={selectedHotlistId}
              onClearDraft={() => beginHotlistDraft()}
              onDelete={() => void handleDeleteHotlist()}
              onDraftChange={setHotlistDraft}
              onSeedFromDetection={() => beginHotlistDraft(selectedRow?.plate1)}
              onSeedFromRoute={() =>
                setHotlistDraft((current) => ({
                  ...current,
                  addressLine1: current.addressLine1 || activeDestination,
                  addressLabel: current.addressLabel || "Route target",
                }))
              }
              onSelect={loadHotlist}
              onSubmit={handleHotlistSubmit}
            />
          ) : null}

          {screen === "hotlists" ? (
            <HotlistsScreen
              activeDestination={activeDestination}
              alertActionError={alertActionError}
              alertActionId={alertActionId}
              alertActionMessage={alertActionMessage}
              alerts={hotlistAlertItems}
              canManageFollowUps={canManageFollowUps}
              canUpdateAlerts={canUpdateVehicleAlerts}
              dataSource={dataSource}
              followUps={followUps}
              followUpActionError={followUpError}
              followUpActionMessage={followUpMessage}
              followUpSaving={followUpSaving}
              hotlists={hotlists}
              activity={recognitionActivityItems}
              activeTab={hotlistsTab}
              openFollowUps={openFollowUps}
              selectedAlertId={selectedAlertId}
              alertResponseNotes={alertResponseNotes}
              onAlertResponseNotesChange={setAlertResponseNotes}
              onAlertStatusChange={(alert, status, notes) => void handleAlertStatusChange(alert, status, notes)}
              onMapDetection={routeToDetectionId}
              onOpenRecord={openRecordForDetectionId}
              onSaveFollowUp={handleSaveFollowUp}
              onSelectAlert={setSelectedAlertId}
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
              canManageFollowUps={canManageFollowUps}
              canViewAudit={canViewAudit}
              canUpdateAlerts={canUpdateVehicleAlerts}
              currentPrincipal={currentPrincipal}
              dataError={dataError}
              dataSource={dataSource}
              degradedDependencyCount={degradedDependencyCount}
              edgeRuntime={edgeRuntime}
              edgeRuntimeAction={edgeRuntimeAction}
              edgeRuntimeError={edgeRuntimeError}
              hotlistWarning={hotlistWarning}
              onSettingsSectionChange={setSettingsSection}
              onApiKeyApply={() => setApiKey(apiKeyInput.trim())}
              onApiKeyChange={setApiKeyInput}
              onEdgeRuntimeCommand={(command) => void handleEdgeRuntimeCommand(command)}
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

        <footer className="dashboard-footer">
          <div className="dashboard-footer__shell">
            <div className="dashboard-footer__shell-copy">
              <span>Product Area</span>
              <strong>{shellCopy.title}</strong>
              <small>{shellCopy.detail}</small>
            </div>
            <div className="dashboard-footer__shell-toggle" role="tablist" aria-label="Workspace area">
              <button
                className={currentShell === "operations" ? "is-active" : ""}
                aria-pressed={currentShell === "operations"}
                type="button"
                onClick={() => switchShell("operations")}
              >
                Operations
              </button>
              <button
                className={currentShell === "admin" ? "is-active" : ""}
                aria-pressed={currentShell === "admin"}
                type="button"
                onClick={() => switchShell("admin")}
              >
                Admin
              </button>
            </div>
          </div>
          <UconnectStyleToolbar items={toolbarItems} />
        </footer>
      </div>

      {detailRow ? (
        <DetailOverlay
          activeDestination={activeDestination}
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
            switchScreen("accounts");
            setDetailDetectionId(null);
          }}
          onClose={() => setDetailDetectionId(null)}
          onCopyPlate={handleCopyPlate}
          onOpenMap={() => {
            routeToRow(detailRow);
            setDetailDetectionId(null);
          }}
          onSubmitReview={handleSubmitReview}
        />
      ) : null}

      {hotlistOverlayRow ? (
        <HotlistAlertOverlay
          activeDestination={activeDestination}
          canSubmitReview={dataSource !== "live" || overview?.current_principal.capabilities.can_submit_reviews === true}
          dataSource={dataSource}
          followUp={matchingFollowUpsForRow(hotlistOverlayRow, followUps)[0] ?? null}
          hotlistAudioMuted={hotlistAudioMuted}
          hotlistEntry={hotlistEntryForRow(hotlistOverlayRow, hotlists)}
          hotlistRow={hotlistOverlayRow}
          onDismiss={() => setHotlistOverlayId(null)}
          onConfirmMatch={() => {
            if (hotlistOverlayRow.detectionId) {
              void handleSubmitReview(hotlistOverlayRow.detectionId, "confirm", undefined, "Confirmed from hotlist alert.");
            }
          }}
          onFlagFalsePositive={() => {
            if (hotlistOverlayRow.detectionId) {
              void handleSubmitReview(hotlistOverlayRow.detectionId, "dismiss", undefined, "Marked false positive from hotlist alert.");
            }
          }}
          onMuteToggle={() => setHotlistAudioMuted((value) => !value)}
          onNavigate={() => {
            routeToRow(hotlistOverlayRow);
            setHotlistOverlayId(null);
          }}
          onRecover={() => void handleRecoverFromAlert()}
          onViewRecord={() => {
            openDetail(hotlistOverlayRow);
            setHotlistOverlayId(null);
          }}
          reviewError={reviewError}
          reviewMessage={reviewMessage}
          reviewSaving={reviewSaving}
        />
      ) : null}
      <DetectionActionSheet
        open={actionSheetRow !== null}
        plate={actionSheetRow?.plate1 ?? ""}
        vehicle={actionSheetRow?.vehicle ?? ""}
        meta={
          actionSheetRow
            ? [
                actionSheetRow.source,
                actionSheetRow.gps,
                formatDateTime(actionSheetRow.timestampUtc),
                `Confidence ${confidenceLabel(actionSheetRow.conf)}`,
              ]
                .filter((part): part is string => Boolean(part))
                .join(" · ")
            : undefined
        }
        statusLabel={actionSheetRow ? detectionSeverityLabel(actionSheetRow) : ""}
        statusTone={actionSheetRow ? dashboardToneForDetection(actionSheetRow) : "gray"}
        severity={actionSheetRow ? detectionSeverityForRow(actionSheetRow) : undefined}
        snapshot={
          actionSheetRow ? (
            <CompactDetectionSnapshot
              dataSource={dataSource}
              detectionId={actionSheetRow.detectionId}
              plate={actionSheetRow.plate1}
              vehicle={actionSheetRow.vehicle}
            />
          ) : null
        }
        actions={
          actionSheetRow
            ? ([
                {
                  id: "route",
                  label: "Route to last seen",
                  detail: actionSheetRow.gps || "Plot route from current position",
                  tone: "primary",
                  onClick: () => routeToRow(actionSheetRow),
                },
                {
                  id: "inspect",
                  label: "Inspect detection",
                  detail: "Open the evidence and review surface",
                  onClick: () => openDetail(actionSheetRow),
                },
                {
                  id: "copy",
                  label: "Copy plate",
                  detail: actionSheetRow.plate1,
                  onClick: () => {
                    void handleCopyPlate(actionSheetRow.plate1);
                  },
                },
                {
                  id: "account",
                  label: "Open account",
                  detail: "Find or create the recovery record",
                  onClick: () => openAccountsForRow(actionSheetRow),
                },
              ] satisfies DetectionActionSheetAction[])
            : []
        }
        onClose={() => setActionSheetRow(null)}
      />
    </>
  );
}

function searchResultSeverity(row: ConsoleDetectionRow): "critical" | "priority" | "watch" | "observed" {
  if (row.alertStatus === "active") {
    return "critical";
  }
  if (row.alertStatus === "acknowledged") {
    return "priority";
  }
  if (row.alertStatus === "dismissed" || row.hotlist) {
    return "watch";
  }
  return "observed";
}

function SearchActivityScore(props: { score: string }): ReactElement {
  return (
    <div className="search-activity-score" aria-label={`Activity score ${props.score}`}>
      {props.score.split("").map((digit, index) => (
        <span key={`${digit}-${index}`} className={`search-activity-score__digit ${index === 0 && Number(digit) >= 3 ? "is-hot" : ""}`}>
          {digit}
        </span>
      ))}
    </div>
  );
}

function SearchTimeline(props: {
  markers: SearchTimelineMarker[];
  onSelectRow: (rowId: string) => void;
  selectedRowId: string;
}): ReactElement {
  const markerRefs = useRef(new Map<string, HTMLButtonElement>());

  useLayoutEffect(() => {
    const markerPositions = new Map(props.markers.map((marker) => [marker.id, `${marker.leftPercent}%`]));
    markerRefs.current.forEach((node, markerId) => {
      const left = markerPositions.get(markerId);
      if (left) {
        node.style.left = left;
      } else {
        node.style.removeProperty("left");
      }
    });
  }, [props.markers]);

  return (
    <div className="search-timeline">
      <div className="search-timeline__rail" aria-hidden="true" />
      {props.markers.map((marker) => (
        <button
          key={marker.id}
          ref={(node) => {
            if (node) {
              markerRefs.current.set(marker.id, node);
            } else {
              markerRefs.current.delete(marker.id);
            }
          }}
          className={`search-timeline__marker search-timeline__marker--${marker.severity} ${props.selectedRowId === marker.id ? "is-selected" : ""} ${marker.isLead ? "is-lead" : ""}`}
          title={marker.timestampLabel}
          type="button"
          onClick={() => props.onSelectRow(marker.id)}
        >
          <span>{marker.timestampLabel}</span>
        </button>
      ))}
    </div>
  );
}

function followUpWorkflowTone(status: FollowUpStatus): "follow-up" | "verify" | "completed" {
  if (status === "resolved") {
    return "completed";
  }
  if (status === "monitoring") {
    return "verify";
  }
  return "follow-up";
}

function followUpStatusLabel(status: FollowUpStatus): string {
  if (status === "open") {
    return "Review First";
  }
  if (status === "monitoring") {
    return "Monitor";
  }
  return "Resolved";
}

function FollowUpStatusPill(props: { status: FollowUpStatus }): ReactElement {
  return <span className={`workflow-pill workflow-pill--${followUpWorkflowTone(props.status)}`}>{followUpStatusLabel(props.status)}</span>;
}

function LocateQuickSelectCard(props: {
  dataSource: DataSource;
  row: ConsoleDetectionRow;
  selected: boolean;
  onSelect: () => void;
}): ReactElement {
  const plateCropUrl = useDetectionPlateCropImage(props.row.detectionId, props.dataSource === "live");
  const severity = searchResultSeverity(props.row);

  return (
    <button
      className={`locate-quick-card severity-band severity-band--${severity} ${props.selected ? "is-selected" : ""}`}
      type="button"
      onClick={props.onSelect}
    >
      <div className={`locate-quick-card__thumb ${plateCropUrl ? "locate-quick-card__thumb--image" : ""}`}>
        {plateCropUrl ? <img alt={`${props.row.plate1} crop`} src={plateCropUrl} /> : <span>{props.row.plate1}</span>}
      </div>
      <div className="locate-quick-card__copy">
        <strong>{props.row.plate1}</strong>
        <span>{props.row.vehicle}</span>
        <span>{formatDateTime(props.row.timestampUtc)}</span>
      </div>
      <div className="locate-quick-card__meta">
        {props.row.hotlist ? <Badge tone="critical">Recovery</Badge> : null}
        {props.row.alertStatus ? <Badge tone={alertStatusTone(props.row.alertStatus)}>{alertStatusLabel(props.row.alertStatus)}</Badge> : null}
      </div>
    </button>
  );
}

function SearchLeadPanel(props: {
  dataSource: DataSource;
  followUp: FollowUpRecord | null;
  hotlistLabel: string | null;
  onAddToHotlist: () => void;
  onCopy: (plate: string) => Promise<void>;
  onDetails: () => void;
  onMap: () => void;
  onSelectRow: (rowId: string) => void;
  relatedRows: ConsoleDetectionRow[];
  row: ConsoleDetectionRow | null;
  selectedRowId: string | null;
}): ReactElement {
  const frameUrl = useDetectionFrameImage(props.row?.detectionId, props.dataSource === "live");
  const plateCropUrl = useDetectionPlateCropImage(props.row?.detectionId, props.dataSource === "live");

  if (!props.row) {
    return (
      <aside className="panel-card locate-intelligence-panel">
        <div className="panel-card__header">
          <div>
            <h3>Lead Intelligence</h3>
          </div>
        </div>
        <StateView
          title="No lead selected"
          description="Run a locate search or focus a result to open the DRN-style lead workspace."
        />
      </aside>
    );
  }
  const row = props.row;
  const activityScore = buildSearchActivityScore(props.relatedRows);
  const pattern = inferSearchActivityPattern(props.relatedRows);
  const timelineMarkers = buildSearchTimelineMarkers(props.relatedRows);
  const historyRows = props.relatedRows.slice(0, 5);
  const recentReadCount = Number(activityScore[0] ?? "0");
  const actionLabel = props.hotlistLabel ? "Open Account" : "Create Account";
  const responseCue = buildOperationalSignal(row, props.followUp, null);

  return (
    <aside className="panel-card locate-intelligence-panel">
      <div className="panel-card__header">
        <div>
          <h3>Lead Intelligence</h3>
          <p>{props.relatedRows.length > 1 ? `${props.relatedRows.length} related reads for this tag` : "Single read in current result set"}</p>
        </div>
        <div className="search-result-card__badges">
          <Badge tone={row.hotlist ? "critical" : "cyan"}>{row.hotlist ? "Recovery hit" : "Lead"}</Badge>
          <span className={`conf-badge conf-badge--${confidenceTone(confidencePercent(row.conf))}`}>{confidenceLabel(row.conf)}</span>
        </div>
      </div>

      <DetectionEvidenceHero
        framePlaceholder={row.camera}
        frameUrl={frameUrl}
        platePlaceholder={row.plate1 || "OCR"}
        plateCropUrl={plateCropUrl}
        plateText={row.plate1}
        tone={row.hotlist ? "critical" : "default"}
      />

      <section className={`lead-status-banner lead-status-banner--${responseCue.tone}`}>
        <div className="lead-status-banner__copy">
          <span className="eyebrow">Next action</span>
          <strong>{responseCue.label}</strong>
          <p>{responseCue.detail}</p>
        </div>
        <div className="lead-status-banner__signals">
          {props.followUp ? <FollowUpStatusPill status={props.followUp.status} /> : null}
          {props.hotlistLabel ? <Badge tone="warn">{props.hotlistLabel}</Badge> : null}
        </div>
      </section>

      <div className="locate-intelligence-strip">
        <div className="locate-intelligence-card">
          <span>Activity score</span>
          <SearchActivityScore score={activityScore} />
          <p>{`${recentReadCount} read${recentReadCount === 1 ? "" : "s"} in the last 30 days`}</p>
        </div>
        <div className="locate-intelligence-card">
          <span>Routine tag</span>
          <Badge tone={pattern.tone}>{pattern.label}</Badge>
          <p>{pattern.detail}</p>
        </div>
      </div>

      <div className="detail-summary-strip locate-intelligence-summary">
        <div className="detail-summary-card">
          <span>Lead plate</span>
          <strong>{row.plate1}</strong>
        </div>
        <div className="detail-summary-card">
          <span>Vehicle</span>
          <strong>{row.vehicle}</strong>
        </div>
        <div className="detail-summary-card">
          <span>Camera</span>
          <strong>{row.camera}</strong>
        </div>
        <div className="detail-summary-card">
          <span>Last seen</span>
          <strong>{formatDateTime(row.timestampUtc)}</strong>
        </div>
      </div>

      <div className="detail-section locate-intelligence-actions">
        <div className="detail-section__copy">
          <h4>Decision workflow</h4>
          <p>Verify the evidence pair first, then route to the last-seen point, review the record, or open the account without losing search context.</p>
        </div>
        <div className="search-result-card__actions">
          <Tooltip text="Route to this vehicle's last-seen point">
            <button className="btn btn--primary" type="button" onClick={props.onMap}>
              Route to Last Seen
            </button>
          </Tooltip>
          <Tooltip text="View full detection record and evidence">
            <button className="btn btn--ghost" type="button" onClick={props.onDetails}>
              Open Record
            </button>
          </Tooltip>
          <Tooltip text={actionLabel === "Create Account" ? "Create a new recovery account for this plate" : "Open the existing recovery account for this plate"}>
            <button className="btn btn--ghost" type="button" onClick={props.onAddToHotlist}>
              {actionLabel}
            </button>
          </Tooltip>
          <Tooltip text="Copy plate number to clipboard">
            <button className="btn btn--ghost" type="button" onClick={() => void props.onCopy(row.plate1)}>
              Copy Tag
            </button>
          </Tooltip>
        </div>
      </div>

      {(props.followUp || row.alertNotes) ? (
        <div className="detail-section">
          <div className="detail-section__copy">
            <h4>Recovery context</h4>
            <p>Current recovery state tied to this lead.</p>
          </div>
          <div className="locate-context-list">
            {props.followUp ? (
              <div className="locate-context-row">
                <FollowUpStatusPill status={props.followUp.status} />
                <span>{props.followUp.summary ?? "Follow-up queued for operator review."}</span>
              </div>
            ) : null}
            {row.alertNotes ? (
              <div className="locate-context-row">
                <Badge tone="warn">Notes</Badge>
                <span>{row.alertNotes}</span>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="detail-section">
        <div className="detail-section__copy">
          <h4>Sighting cadence</h4>
          <p>Recent reads laid out as a simple field timeline.</p>
        </div>
        <SearchTimeline markers={timelineMarkers} onSelectRow={props.onSelectRow} selectedRowId={props.selectedRowId ?? row.id} />
        <div className="locate-history-list">
          {historyRows.map((historyRow) => (
            <button
              key={historyRow.id}
              className={`locate-history-row ${historyRow.id === (props.selectedRowId ?? row.id) ? "is-selected" : ""}`}
              type="button"
              onClick={() => props.onSelectRow(historyRow.id)}
            >
              <strong>{historyRow.camera}</strong>
              <span>{formatDateTime(historyRow.timestampUtc)}</span>
              <span>{historyRow.gps}</span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

function SearchResultCard(props: {
  dataSource: DataSource;
  followUp: FollowUpRecord | null;
  selected: boolean;
  row: ConsoleDetectionRow;
  hotlistLabel: string | null;
  onAddToHotlist: () => void;
  onSelect: () => void;
  onDetails: () => void;
  onMap: () => void;
  onCopy: (plate: string) => Promise<void>;
}): ReactElement {
  const frameUrl = useDetectionFrameImage(props.row.detectionId, props.dataSource === "live");
  const plateCropUrl = useDetectionPlateCropImage(props.row.detectionId, props.dataSource === "live");
  const severity = searchResultSeverity(props.row);
  const workflowSummary = props.followUp ? props.followUp.summary ?? `Follow-up ${titleCase(props.followUp.status)}` : null;

  function stopEvent<T>(handler: () => T): (event: MouseEvent<HTMLButtonElement>) => void {
    return (event) => {
      event.stopPropagation();
      void handler();
    };
  }

  return (
    <article
      className={`search-result-card severity-band severity-band--${severity} ${props.selected ? "is-selected" : ""}`}
      tabIndex={0}
      onClick={props.onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          props.onSelect();
        }
      }}
    >
      <div className="search-result-card__evidence">
        <div className={`search-result-card__thumb search-result-card__thumb--plate ${plateCropUrl ? "search-result-card__thumb--image" : ""}`}>
          {plateCropUrl ? <img alt={`${props.row.plate1} plate crop`} src={plateCropUrl} /> : <span>{props.row.plate1 || "OCR"}</span>}
        </div>
        <div className={`search-result-card__thumb ${frameUrl ? "search-result-card__thumb--image" : ""}`}>
          {frameUrl ? <img alt={`${props.row.plate1} capture`} src={frameUrl} /> : <span>{props.row.camera}</span>}
        </div>
      </div>
      <div className="search-result-card__body">
        <div className="search-result-card__header">
          <div className="search-result-card__identity">
            <div className="search-result-card__plate-line">
              <strong>{props.row.plate1}</strong>
              <span className={`conf-badge conf-badge--${confidenceTone(confidencePercent(props.row.conf))}`}>{confidenceLabel(props.row.conf)}</span>
              {props.row.hotlist ? <Badge tone="critical">Recovery</Badge> : null}
              {props.hotlistLabel ? <Badge tone="warn">{props.hotlistLabel}</Badge> : null}
            </div>
            <p className="search-result-card__vehicle-line">{props.row.vehicle}</p>
            <p className="search-result-card__location-line">{formatDetectionLocationLine(props.row)}</p>
            <p className="search-result-card__meta-line">{formatDetectionTimestampGpsLine(props.row)}</p>
            <p className="search-result-card__meta-line">
              {formatDetectionCameraLine(props.row)}
              {props.row.direction ? ` • ${props.row.direction}` : ""}
              {props.row.lane ? ` / ${props.row.lane}` : ""}
            </p>
          </div>
          <div className="search-result-card__badges">
            {props.row.alertStatus ? <Badge tone={alertStatusTone(props.row.alertStatus)}>{alertStatusLabel(props.row.alertStatus)}</Badge> : null}
            {props.row.alertMatchType ? <Badge tone={props.row.alertMatchType === "exact" ? "success" : "warn"}>{`${titleCase(props.row.alertMatchType)} match`}</Badge> : null}
            {props.followUp ? <FollowUpStatusPill status={props.followUp.status} /> : null}
          </div>
        </div>
        {workflowSummary ? (
          <div className="search-result-card__workflow">
            <span>
              {workflowSummary}
              {props.followUp?.due_at_utc ? ` • Due ${formatDateTime(props.followUp.due_at_utc)}` : ""}
            </span>
          </div>
        ) : null}
        {props.row.alertNotes ? (
          <div className="search-result-card__workflow">
            <span>{props.row.alertNotes}</span>
          </div>
        ) : null}
        <div className="search-result-card__actions">
          <Tooltip text="Route to this vehicle's last-seen point">
            <button className="link-button" type="button" onClick={stopEvent(props.onMap)}>
              Route
            </button>
          </Tooltip>
          <Tooltip text="View full detection record">
            <button className="link-button" type="button" onClick={stopEvent(props.onDetails)}>
              Open Record
            </button>
          </Tooltip>
          <Tooltip text={props.hotlistLabel ? "Open existing recovery account" : "Create a new recovery account"}>
            <button className="link-button" type="button" onClick={stopEvent(props.onAddToHotlist)}>
              {props.hotlistLabel ? "Open Account" : "Create Account"}
            </button>
          </Tooltip>
          <Tooltip text="Copy plate number to clipboard">
            <button className="link-button" type="button" onClick={stopEvent(() => props.onCopy(props.row.plate1))}>
              Copy Tag
            </button>
          </Tooltip>
        </div>
      </div>
    </article>
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
        aria-label={props.title}
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
      <select className="select-input" aria-label={props.title} value={props.value} onChange={(event) => props.onChange(event.target.value)}>
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

function SettingsSectionBlock(props: {
  title: string;
  description: string;
  badge?: ReactNode;
  children: ReactNode;
}): ReactElement {
  return (
    <section className="settings-subsection">
      <div className="settings-subsection__header">
        <div className="settings-subsection__copy">
          <h4>{props.title}</h4>
          <p>{props.description}</p>
        </div>
        {props.badge ?? null}
      </div>
      {props.children}
    </section>
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

function Tooltip(props: { text: string; children: ReactElement }): ReactElement {
  return (
    <span className="tooltip-anchor">
      {props.children}
      <span className="tooltip-bubble">{props.text}</span>
    </span>
  );
}

function CollapsibleSection(props: {
  children: ReactNode;
  className?: string;
  defaultOpen?: boolean;
  summary?: string;
  title: string;
}): ReactElement {
  return (
    <details className={`collapsible-section ${props.className ?? ""}`.trim()} open={props.defaultOpen}>
      <summary className="collapsible-section__summary">
        <div className="collapsible-section__copy">
          <strong>{props.title}</strong>
          {props.summary ? <span>{props.summary}</span> : null}
        </div>
        <span className="collapsible-section__chevron" aria-hidden="true" />
      </summary>
      <div className="collapsible-section__body">{props.children}</div>
    </details>
  );
}

function NavPanel(props: {
  activeScreen: AppScreen;
  activeAlerts: number;
  activeHotlists: number;
  cameraOnlineCount: number;
  cameraTotalCount: number;
  dataSource: DataSource;
  idleScanEnabled: boolean;
  navigationActive: boolean;
  onOpenAlert: () => void;
  onOpenRoute: () => void;
  onScreenChange: (screen: AppScreen) => void;
  onToggleIdleScan: () => void;
  routeEta: string;
  totalReads: number;
}): ReactElement {
  const navItems: Array<{ id: AppScreen; label: string; tip: string; count: number | null }> = [
    { id: "console", label: "Console", tip: "Live cameras, map routing, and plate reads", count: null },
    { id: "search", label: "Locate", tip: "Search sightings by plate, camera, or vehicle", count: null },
    { id: "accounts", label: "Accounts", tip: "Manage recovery accounts and skip addresses", count: props.activeHotlists > 0 ? props.activeHotlists : null },
    { id: "hotlists", label: "Recoveries", tip: "Recovery matches, follow-ups, and recent sightings", count: props.activeAlerts > 0 ? props.activeAlerts : null },
    { id: "settings", label: "Settings", tip: "System settings, cameras, and API config", count: null },
  ];

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
        {navItems.map((item) => (
          <Tooltip key={item.id} text={item.tip}>
            <button
              className={`nav-tab ${props.activeScreen === item.id ? "is-active" : ""}`}
              type="button"
              onClick={() => props.onScreenChange(item.id)}
            >
              <span className="nav-tab__label">{item.label}</span>
              {typeof item.count === "number" ? <span className="nav-tab__count">{item.count}</span> : null}
            </button>
          </Tooltip>
        ))}
      </div>

      <div className="panel-card ops-glance-card">
        <div className="panel-card__header">
          <h3>Ops Glance</h3>
          <Badge tone={props.dataSource === "live" ? "success" : props.dataSource === "fallback" ? "warn" : "muted"}>
            {props.dataSource.toUpperCase()}
          </Badge>
        </div>
        <div className="ops-glance-grid">
          <div className="ops-glance-chip">
            <span>Recoveries</span>
            <strong>{props.activeAlerts}</strong>
          </div>
          <div className="ops-glance-chip">
            <span>Accounts</span>
            <strong>{props.activeHotlists}</strong>
          </div>
          <div className="ops-glance-chip">
            <span>Reads</span>
            <strong>{props.totalReads}</strong>
          </div>
          <div className="ops-glance-chip">
            <span>Cameras</span>
            <strong>{`${props.cameraOnlineCount}/${props.cameraTotalCount}`}</strong>
          </div>
        </div>
        <div className="ops-glance-actions">
          <span>{props.navigationActive ? `Routing • ETA ${props.routeEta}` : props.idleScanEnabled ? "Idle scan live" : "Idle scan paused"}</span>
          <div className="nav-action-row">
            <button className="nav-action nav-action--primary" type="button" onClick={props.navigationActive ? props.onOpenRoute : props.onToggleIdleScan}>
              <span>{props.navigationActive ? "Open Route" : props.idleScanEnabled ? "Pause Scan" : "Start Scan"}</span>
            </button>
            <button className="nav-action nav-action--ghost" disabled={props.activeAlerts === 0} type="button" onClick={props.onOpenAlert}>
              <span>Open Recovery</span>
            </button>
          </div>
        </div>
      </div>

    </aside>
  );
}

function ConsoleScreen(props: {
  activeAlerts: number;
  activeDestination: string;
  alertMarkers: MapAlertMarker[];
  allRows: ConsoleDetectionRow[];
  cameraFeedsList: CameraUiFeed[];
  cameraFocusRow: ConsoleDetectionRow | null;
  currentCamera: CameraUiFeed | undefined;
  dataSource: DataSource;
  dashboardConfig: DashboardConfig;
  dashboardCustomizeOpen: boolean;
  hotlists: DashboardHotlist[];
  destinationCoords: DestinationCoords | null;
  destinationInput: string;
  destinationModalOpen: boolean;
  destinationTargets: DestinationTarget[];
  destinationPreview: { distance: string; eta: string; feet: number } | null;
  followUps: FollowUpRecord[];
  recentDestinations: RecentDestination[];
  idleScanEnabled: boolean;
  layerMenuOpen: boolean;
  navigationActive: boolean;
  navigationGuidance: NavigationGuidance;
  scanSessionState: ScanSessionState;
  activeRouteFeet: number | null;
  serviceHealthState: ServiceHealthState;
  selectedCameraId: string;
  selectedDetectionId: string | null;
  settings: UiSettings;
  stageView: StageView;
  gpsFix: GpsFixState;
  liveAddress: LiveAddressState;
  unitPosition: { lat: number; lng: number };
  routeDistance: string;
  routeEta: string;
  routePath: [number, number][];
  routeStatusLabel: string;
  withinRadius: boolean;
  onApplyDestinationTarget: (target: DestinationTarget) => void;
  onClearDestinationDraft: () => void;
  onCloseDashboardCustomize: () => void;
  onCloseDestinationModal: () => void;
  onDestinationChange: (value: string) => void;
  onEndRoute: () => void;
  onCopyPlate: (plate: string) => Promise<void>;
  onOpenAccount: (row: ConsoleDetectionRow) => void;
  onOpenDashboardCustomize: () => void;
  onOpenDetail: (row: ConsoleDetectionRow) => void;
  onOpenDetectionActions: (row: ConsoleDetectionRow) => void;
  onOpenDestinationModal: () => void;
  onOpenHotlist: (entry: DashboardHotlist) => void;
  onOpenRecoveries: () => void;
  onOpenSettings: () => void;
  onRemoveRecentDestination: (id: string) => void;
  onResetDashboardConfig: () => void;
  onSelectCamera: (cameraId: string) => void;
  onSelectDetection: (rowId: string) => void;
  onRouteToDetection: (row: ConsoleDetectionRow) => void;
  onSelectGeocodedAddress: (address: string, coords: DestinationCoords) => void;
  onStageResolvedDestination: (address: string, coords: DestinationCoords) => void;
  onStageDestination: () => void;
  onStartResolvedRoute: (address: string, coords: DestinationCoords) => void;
  onStartRoute: () => void;
  onStageViewChange: (view: StageView) => void;
  onToggleActiveAlertPins: () => void;
  onToggleDetectionPins: () => void;
  onToggleHistoricalAlertPins: () => void;
  onToggleLayerMenu: () => void;
  onToggleRadiusRing: () => void;
  onUpdateDashboardLayoutMode: (mode: DashboardLayoutMode) => void;
  onUpdateDashboardWidgetMove: (sourceWidgetId: DashboardWidgetId, targetWidgetId: DashboardWidgetId) => void;
  onUpdateDashboardWidgetSize: (widgetId: DashboardWidgetId, size: DashboardWidgetSize) => void;
  onUpdateDashboardWidgetVisibility: (widgetId: DashboardWidgetId, visible: boolean) => void;
}): ReactElement {
  const [quickPlateVin, setQuickPlateVin] = useState("");
  const [quickSearchFeedback, setQuickSearchFeedback] = useState<string | null>(null);

  const mapPanelProps = {
    alertMarkers: props.alertMarkers,
    activeDestination: props.activeDestination,
    destinationCoords: props.destinationCoords,
    destinationInput: props.destinationInput,
    destinationModalOpen: props.destinationModalOpen,
    destinationTargets: props.destinationTargets,
    destinationPreview: props.destinationPreview,
    idleScanEnabled: props.idleScanEnabled,
    layerMenuOpen: props.layerMenuOpen,
    navigationActive: props.navigationActive,
    navigationGuidance: props.navigationGuidance,
    routeDistance: props.routeDistance,
    routeEta: props.routeEta,
    routePath: props.routePath,
    routeStatusLabel: props.routeStatusLabel,
    rows: props.allRows.slice(0, 8),
    selectedRowId: props.selectedDetectionId,
    settings: props.settings,
    gpsFix: props.gpsFix,
    liveAddress: props.liveAddress,
    unitPosition: props.unitPosition,
    withinRadius: props.withinRadius,
    onApplyDestinationTarget: props.onApplyDestinationTarget,
    onClearDestinationDraft: props.onClearDestinationDraft,
    onCloseDestinationModal: props.onCloseDestinationModal,
    onDestinationChange: props.onDestinationChange,
    onEndRoute: props.onEndRoute,
    onOpenDestinationModal: props.onOpenDestinationModal,
    onRemoveRecentDestination: props.onRemoveRecentDestination,
    onSelect: props.onSelectDetection,
    onSelectGeocodedAddress: props.onSelectGeocodedAddress,
    onStageResolvedDestination: props.onStageResolvedDestination,
    onStageDestination: props.onStageDestination,
    onStartResolvedRoute: props.onStartResolvedRoute,
    onStartRoute: props.onStartRoute,
    onToggleActiveAlertPins: props.onToggleActiveAlertPins,
    onToggleDetectionPins: props.onToggleDetectionPins,
    onToggleHistoricalAlertPins: props.onToggleHistoricalAlertPins,
    onToggleLayerMenu: props.onToggleLayerMenu,
    onToggleRadiusRing: props.onToggleRadiusRing,
  } as const;
  const selectedConsoleRow = props.allRows.find((row) => row.id === props.selectedDetectionId) ?? props.allRows[0] ?? null;
  const recoveryRows = props.allRows.filter((row) => row.hotlist || row.alertStatus === "active");
  const commandRow = recoveryRows[0] ?? selectedConsoleRow;
  const secondaryCamera = props.cameraFeedsList.find((feed) => feed.id !== props.selectedCameraId) ?? props.cameraFeedsList[1] ?? props.cameraFeedsList[0];
  const secondaryCameraRow =
    props.allRows.find((row) => row.cameraId === secondaryCamera?.id) ?? props.allRows.find((row) => row.id !== props.cameraFocusRow?.id) ?? null;
  const activeHotlistEntry = commandRow ? hotlistEntryForRow(commandRow, props.hotlists) : null;
  const activeFollowUp = commandRow ? matchingFollowUpsForRow(commandRow, props.followUps)[0] ?? null : null;
  const responseCue = commandRow ? buildOperationalSignal(commandRow, activeFollowUp, null) : null;
  const recoveryProbability = recoveryProbabilityForRow(commandRow, activeHotlistEntry, activeFollowUp);
  const dashboardClock = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const scanStatusLabel = props.navigationActive
    ? props.settings.autoArrivalScan
      ? `Auto-scan ${props.settings.arrivalRadiusFeet} ft`
      : "Auto-scan off"
    : props.idleScanEnabled
      ? "Idle scan on"
      : "Idle scan off";
  const driverActionLabel = props.navigationActive ? "End Route" : props.activeDestination ? "Start Recovery" : "Set Target";
  const driverAction = props.navigationActive ? props.onEndRoute : props.activeDestination ? props.onStartRoute : props.onOpenDestinationModal;
  const notesSummary = [activeHotlistEntry?.notes, activeFollowUp?.summary, activeFollowUp?.notes, commandRow?.alertNotes].filter(
    (value): value is string => Boolean(value),
  );
  const visibleWidgets = props.dashboardConfig.widgets
    .filter((widget) => widget.visible && widget.id !== "reports")
    .sort((a, b) => a.order - b.order);
  const widgetAvailability: Partial<Record<DashboardWidgetId, boolean>> = { reports: false };
  const heroWidget = visibleWidgets[0] ?? null;
  const supportWidgets = visibleWidgets.slice(1);
  const [sidePrimaryWidget, sideSecondaryWidget, sideTertiaryWidget, lowerLeftWidget, lowerRightPrimaryWidget, lowerRightSecondaryWidget, footerWidget] =
    supportWidgets;

  function handleQuickSearchSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const query = quickPlateVin.trim();
    if (!query) {
      return;
    }

    const normalizedQuery = normalizePlate(query);
    const lowerQuery = query.toLowerCase();

    const matchedRow = props.allRows.find((row) => {
      const plateMatch = [row.plate1, row.plate2, ...row.plateCandidates.map((candidate) => candidate.text)].some(
        (candidate) => normalizePlate(candidate).includes(normalizedQuery),
      );
      if (plateMatch) {
        return true;
      }
      return row.vehicle.toLowerCase().includes(lowerQuery);
    });
    if (matchedRow) {
      props.onSelectDetection(matchedRow.id);
      props.onOpenDetail(matchedRow);
      setQuickSearchFeedback(`Opened read ${matchedRow.plate1}.`);
      return;
    }

    const matchedAccount = props.hotlists.find((entry) => {
      const fields = [entry.plate_text, entry.vin, entry.label, entry.vehicle_make, entry.vehicle_model].filter(
        (value): value is string => Boolean(value),
      );
      return fields.some((value) => normalizePlate(value).includes(normalizedQuery) || value.toLowerCase().includes(lowerQuery));
    });
    if (matchedAccount) {
      const accountTarget = props.destinationTargets.find((target) => target.id === `target-account-${matchedAccount.entry_id}`);
      if (accountTarget) {
        useRouteTarget(accountTarget);
      }
      props.onOpenHotlist(matchedAccount);
      setQuickSearchFeedback(`Opened account ${hotlistIdentifierSummary(matchedAccount)}.`);
      return;
    }

    setQuickSearchFeedback(`No match for ${query}. Try the Search screen for full filters.`);
  }

  function useRouteTarget(target: DestinationTarget): void {
    props.onApplyDestinationTarget(target);
    if (target.coords) {
      props.onStageResolvedDestination(target.address, target.coords);
    } else {
      props.onDestinationChange(target.address);
      props.onOpenDestinationModal();
    }
  }
  const cameraFocusCount = props.cameraFeedsList.filter((feed) => feed.status === "Online").length;
  function renderWidget(widgetId: DashboardWidgetId, size: DashboardWidgetSize): ReactElement | null {
    if (widgetId === "map") {
      return (
        <DashboardWidgetFrame
          title="Recovery Map"
          eyebrow="Center navigation"
          size={size}
          className="dashboard-widget--map-frame"
          meta={<StatusPill label={props.routeStatusLabel} tone={props.withinRadius ? "green" : props.navigationActive ? "cyan" : "gray"} />}
        >
          <MapStagePanel {...mapPanelProps} compact={size === "compact"} />
        </DashboardWidgetFrame>
      );
    }

    if (widgetId === "addressIntelligence") {
      return (
        <AddressIntelligenceCard
          size={size}
          address={props.activeDestination || activeHotlistEntry?.address_line1 || commandRow?.gps || "No address staged"}
          subtitle={activeHotlistEntry ? hotlistAddressSummary(activeHotlistEntry) : commandRow?.source ?? "Route target pending"}
          recoveryProbability={recoveryProbability.label}
          recoveryTone={recoveryProbability.tone}
          recommendation={responseCue?.label ?? "Hold"}
          recommendationDetail={responseCue?.detail ?? "Select a target vehicle or stage a destination to unlock recovery guidance."}
          recentSummary={
            commandRow
              ? `${formatRelativeTime(commandRow.timestampUtc)} at ${commandRow.source}. ${props.allRows.filter((row) => row.plate1 === commandRow.plate1).length} related sighting(s) in the current dashboard feed.`
              : "No recent sighting is selected."
          }
          fields={[
            { label: "Address Label", value: activeHotlistEntry?.address_label ?? "Address on file" },
            { label: "Vehicle Profile", value: summarizeVehicleIdentity(commandRow, activeHotlistEntry) },
            { label: "Last Seen Source", value: commandRow?.source ?? "Not available" },
            { label: "Follow-Up", value: activeFollowUp ? titleCase(activeFollowUp.status) : "None" },
            { label: "Garage", value: inferNoteField(activeHotlistEntry?.notes, ["garage", "carport"], "Flagged in notes") },
            { label: "Fence / Gate", value: inferNoteField(activeHotlistEntry?.notes, ["gate", "fence"], "Flagged in notes") },
            { label: "Camera Notes", value: inferNoteField(activeHotlistEntry?.notes, ["camera", "ring", "cctv"], "Flagged in notes") },
            { label: "Parking Visibility", value: commandRow?.gps ? "Last-seen point logged" : "Not available" },
          ]}
        />
      );
    }

    if (widgetId === "aiInsight") {
      // Pick the strongest recommendation available given the current
      // operator state. Order matters: an existing target overrides the
      // empty-state recommendations.
      const activeOrders = props.hotlists.filter((entry) => entry.active);
      const stageNextOrder = !commandRow && activeOrders.length > 0 ? activeOrders[0] : null;
      const insightLabel = responseCue?.label
        ?? (stageNextOrder ? "Choose recovery target" : "Awaiting target vehicle");
      const insightDetail = responseCue?.detail
        ?? (stageNextOrder
          ? `${activeOrders.length} active order${activeOrders.length === 1 ? "" : "s"}. Highest in queue: ${
              stageNextOrder.label ?? hotlistIdentifierSummary(stageNextOrder)
            }.`
          : "Stage a target vehicle, account, or address to get a recommended recovery sequence.");
      const insightTone = responseCue?.tone === "critical"
        ? "red"
        : responseCue?.tone === "warn"
          ? "amber"
          : stageNextOrder
            ? "cyan"
            : "gray";
      const insightStatusLabel = responseCue?.label
        ?? (stageNextOrder ? "Triage queue" : "Standby");
      const primaryActionDisabled = !commandRow && !stageNextOrder;
      const primaryActionLabel = commandRow
        ? "Route to Target"
        : stageNextOrder
          ? "Open Recovery Queue"
          : "Route to Target";
      const onPrimaryAction = (): void => {
        if (commandRow) {
          props.onRouteToDetection(commandRow);
          return;
        }
        if (stageNextOrder) {
          props.onOpenRecoveries();
        }
      };
      const secondaryActionDisabled = !commandRow && !stageNextOrder;
      const secondaryActionLabel = commandRow
        ? "Review Detections"
        : stageNextOrder
          ? "Open Order"
          : "Review Detections";
      const onSecondaryAction = (): void => {
        if (commandRow) {
          props.onOpenDetail(commandRow);
          return;
        }
        if (stageNextOrder) {
          props.onOpenHotlist(stageNextOrder);
        }
      };
      return (
        <DashboardWidgetFrame
          title="AI Insight"
          eyebrow="Field recommendation"
          size={size}
          meta={<StatusPill label={insightStatusLabel} tone={insightTone} />}
        >
          <div className="dashboard-insight-card">
            <strong>{insightLabel}</strong>
            <p>{insightDetail}</p>
            <div className="dashboard-insight-card__actions">
              <button
                className="btn btn--primary btn--compact"
                disabled={primaryActionDisabled}
                type="button"
                onClick={onPrimaryAction}
              >
                {primaryActionLabel}
              </button>
              <button
                className="btn btn--ghost btn--compact"
                disabled={secondaryActionDisabled}
                type="button"
                onClick={onSecondaryAction}
              >
                {secondaryActionLabel}
              </button>
            </div>
          </div>
        </DashboardWidgetFrame>
      );
    }

    if (widgetId === "routePanel") {
      return (
        <DashboardWidgetFrame
          title="Route Panel"
          eyebrow="Target guidance"
          size={size}
          meta={<StatusPill label={scanStatusLabel} tone={props.idleScanEnabled || props.navigationActive ? "green" : "gray"} />}
        >
          <div className="dashboard-route-card">
            <div className="dashboard-route-card__metrics">
              <div>
                <span>Target Vehicle</span>
                <strong>{commandRow?.plate1 ?? "No target"}</strong>
              </div>
              <div>
                <span>Distance</span>
                <strong>{props.navigationActive ? props.routeDistance : "--"}</strong>
              </div>
              <div>
                <span>ETA</span>
                <strong>{props.navigationActive ? props.routeEta : "--"}</strong>
              </div>
            </div>
            <div className={`dashboard-route-card__guidance dashboard-route-card__guidance--${props.navigationGuidance.mode}`}>
              <strong>{props.activeDestination || "No recovery address staged"}</strong>
              <span>{props.navigationGuidance.primary}</span>
              <small>{props.navigationGuidance.secondary}</small>
            </div>
            <div className="dashboard-route-card__actions">
              <button className="btn btn--primary btn--compact" type="button" onClick={driverAction}>
                {driverActionLabel}
              </button>
              <button className="btn btn--ghost btn--compact" disabled={!commandRow} type="button" onClick={() => commandRow && props.onOpenAccount(commandRow)}>
                Open Target
              </button>
            </div>
            <form className="dashboard-route-card__lookup" onSubmit={handleQuickSearchSubmit}>
              <label className="form-label" htmlFor="console-quick-lookup">Quick Find</label>
              <div className="dashboard-route-card__lookup-row">
                <input
                  id="console-quick-lookup"
                  className="text-input"
                  placeholder="Plate, VIN, vehicle"
                  value={quickPlateVin}
                  onChange={(event) => setQuickPlateVin(event.target.value)}
                />
                <button className="btn btn--ghost btn--compact" type="submit">
                  Find
                </button>
              </div>
              {quickSearchFeedback ? <p className="ops-input-feedback">{quickSearchFeedback}</p> : null}
            </form>
          </div>
        </DashboardWidgetFrame>
      );
    }

    if (widgetId === "lprCameras") {
      return (
        <LprCameraPanel
          size={size}
          tiles={[
            {
              id: props.selectedCameraId,
              label: props.currentCamera?.shortLabel ?? "Front LPR Camera",
              statusLabel: cameraFeedBadgeLabel(props.currentCamera?.status ?? "Unknown"),
              statusTone: dashboardToneForCamera(props.currentCamera?.status ?? "Unknown"),
              meta: props.cameraFocusRow?.plate1 ? `Tracking ${props.cameraFocusRow.plate1}` : props.currentCamera?.label,
              feed: <CameraViewport cameraId={props.selectedCameraId} row={props.cameraFocusRow} dataSource={props.dataSource} compact />,
            },
            {
              id: secondaryCamera?.id ?? "secondary",
              label: secondaryCamera?.shortLabel ?? "Secondary LPR Camera",
              statusLabel: cameraFeedBadgeLabel(secondaryCamera?.status ?? "Unknown"),
              statusTone: dashboardToneForCamera(secondaryCamera?.status ?? "Unknown"),
              meta: secondaryCameraRow?.plate1 ? `Recent ${secondaryCameraRow.plate1}` : secondaryCamera?.label,
              feed: <CameraViewport cameraId={secondaryCamera?.id ?? props.selectedCameraId} row={secondaryCameraRow} dataSource={props.dataSource} compact />,
            },
          ]}
        />
      );
    }

    if (widgetId === "liveDetections") {
      return (
        <DashboardWidgetFrame
          title="Recent Reads"
          eyebrow="Latest 4 detections · snapshot"
          size={size}
          meta={<StatusPill label={`${Math.min(props.allRows.length, 4)} of ${props.allRows.length}`} tone="cyan" />}
        >
          <div className="dashboard-detections-grid">
            {props.allRows.slice(0, 4).map((row) => (
              <CompactDetectionCard
                key={row.id}
                plate={row.plate1}
                vehicle={row.vehicle}
                color={undefined}
                distance={row.gps || row.source}
                confidence={confidenceLabel(row.conf)}
                statusLabel={detectionSeverityLabel(row)}
                statusTone={dashboardToneForDetection(row)}
                severity={detectionSeverityForRow(row)}
                active={row.id === props.selectedDetectionId}
                snapshot={<CompactDetectionSnapshot dataSource={props.dataSource} detectionId={row.detectionId} plate={row.plate1} vehicle={row.vehicle} />}
                onSelect={() => props.onOpenDetectionActions(row)}
              />
            ))}
          </div>
        </DashboardWidgetFrame>
      );
    }

    if (widgetId === "recentHistory") {
      return (
        <RecentDetectionHistoryCard
          size={size}
          items={props.allRows.slice(0, 6).map((row) => ({
            id: row.id,
            plate: row.plate1,
            vehicle: row.vehicle,
            time: formatRelativeTime(row.timestampUtc),
            location: row.gps || row.source,
            statusLabel: detectionSeverityLabel(row),
            statusTone: dashboardToneForDetection(row),
            severity: detectionSeverityForRow(row),
            onSelect: () => props.onOpenDetectionActions(row),
          }))}
        />
      );
    }

    if (widgetId === "notes") {
      return (
        <DashboardWidgetFrame
          title="Notes"
          eyebrow="Recovery context"
          size={size}
          meta={<StatusPill label={activeFollowUp ? titleCase(activeFollowUp.status) : "Ready"} tone={dashboardToneForFollowUp(activeFollowUp?.status)} />}
        >
          <div className="dashboard-notes-card">
            {notesSummary.length > 0 ? (
              notesSummary.slice(0, 3).map((note, index) => (
                <div key={`${note}-${index}`} className="dashboard-notes-card__note">
                  <span>{index === 0 ? "Active Note" : "Follow-up"}</span>
                  <p>{note}</p>
                </div>
              ))
            ) : (
              <div className="dashboard-notes-card__empty">No account or follow-up notes are attached to the active target.</div>
            )}
          </div>
        </DashboardWidgetFrame>
      );
    }

    return null;
  }

  function renderDashboardSlot(
    widget: { id: DashboardWidgetId; size: DashboardWidgetSize } | null | undefined,
    slotClassName: string,
  ): ReactElement | null {
    if (!widget) {
      return null;
    }
    const rendered = renderWidget(widget.id, widget.size);
    if (!rendered) {
      return null;
    }
    return (
      <div key={widget.id} className={`dashboard-grid__slot ${slotClassName} dashboard-grid__slot--${widget.id}`.trim()}>
        {rendered}
      </div>
    );
  }

  return (
    <section className="screen dashboard-screen">
      <DashboardShell
        header={
          <InstrumentStatusBar
            brand="RepoScan Recovery"
            subtitle="Recovery intelligence"
            primaryTarget={{
              label: "Active Target",
              value: commandRow?.plate1 ?? "Standby",
              detail: activeHotlistEntry?.label ?? (props.navigationActive ? "Route active" : "No active target"),
            }}
            vehicle={{
              label: "Vehicle",
              value: summarizeVehicleIdentity(commandRow, activeHotlistEntry),
              detail: commandRow?.source ?? "Awaiting vehicle read",
            }}
            lastSeen={{
              label: "Last Seen",
              value: commandRow ? formatRelativeTime(commandRow.timestampUtc) : "--",
              detail: commandRow?.gps || commandRow?.source || "No recent sighting",
            }}
            recovery={{
              label: "Recovery Prob.",
              value: recoveryProbability.label,
              detail: responseCue?.label ?? "Ready",
            }}
            system={{
              label: "System",
              value: serviceHealthLabel(props.serviceHealthState),
              detail: scanStatusLabel,
              tone: dashboardToneForService(props.serviceHealthState),
            }}
            time={{ label: "Time", value: dashboardClock, detail: props.liveAddress.address?.city ?? "Local" }}
            actions={[
              { label: "Recoveries", onClick: props.onOpenRecoveries, icon: props.activeAlerts > 0 ? String(props.activeAlerts) : "!" },
              { label: "Settings", onClick: props.onOpenSettings, icon: "S" },
            ]}
            customizeLabel="Customize Dashboard"
            onCustomize={props.onOpenDashboardCustomize}
          />
        }
        toolbar={null}
        customizePanel={
          props.dashboardCustomizeOpen ? (
            <DashboardCustomizePanel
              config={props.dashboardConfig}
              widgetAvailability={widgetAvailability}
              onClose={props.onCloseDashboardCustomize}
              onReset={props.onResetDashboardConfig}
              onModeChange={props.onUpdateDashboardLayoutMode}
              onWidgetMove={props.onUpdateDashboardWidgetMove}
              onWidgetVisibilityChange={props.onUpdateDashboardWidgetVisibility}
              onWidgetSizeChange={props.onUpdateDashboardWidgetSize}
            />
          ) : null
        }
      >
        <ScanStateBanner
          state={props.scanSessionState}
          distanceFeet={props.activeRouteFeet}
          primaryTarget={commandRow?.plate1}
        />
        <div className={`dashboard-grid dashboard-grid--${props.dashboardConfig.mode}`} data-stage-view={props.stageView}>
          <div className="dashboard-grid__hero-column">
            {renderDashboardSlot(heroWidget, "dashboard-grid__slot--hero")}
            {lowerLeftWidget || lowerRightPrimaryWidget || lowerRightSecondaryWidget ? (
              <div className="dashboard-grid__lower-band">
                {renderDashboardSlot(lowerLeftWidget, "dashboard-grid__slot--lower-left")}
                {lowerRightPrimaryWidget || lowerRightSecondaryWidget ? (
                  <div className="dashboard-grid__lower-stack">
                    {renderDashboardSlot(lowerRightPrimaryWidget, "dashboard-grid__slot--lower-right-primary")}
                    {renderDashboardSlot(lowerRightSecondaryWidget, "dashboard-grid__slot--lower-right-secondary")}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          {sidePrimaryWidget || sideSecondaryWidget || sideTertiaryWidget ? (
            <div className="dashboard-grid__support-column">
              {renderDashboardSlot(sidePrimaryWidget, "dashboard-grid__slot--support-primary")}
              {renderDashboardSlot(sideSecondaryWidget, "dashboard-grid__slot--support-secondary")}
              {renderDashboardSlot(sideTertiaryWidget, "dashboard-grid__slot--support-tertiary")}
            </div>
          ) : null}
          {footerWidget ? <div className="dashboard-grid__footer-row">{renderDashboardSlot(footerWidget, "dashboard-grid__slot--footer")}</div> : null}
        </div>

      </DashboardShell>
    </section>
  );
}

function SearchScreen(props: {
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
  onRetrySearch: () => void;
  onSelectDetection: (rowId: string) => void;
  onSearchSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onToggleExpanded: (plate: string) => void;
  selectedDetectionId: string | null;
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
  const focusedRow =
    props.results.find((row) => row.id === props.selectedDetectionId) ??
    (props.searchGroupByPlate ? props.groupedResults[0]?.rows[0] : props.results[0]) ??
    null;
  const focusedPlate = normalizePlate(focusedRow?.plate1);
  const focusedRows = focusedRow
    ? props.results
        .filter((row) => normalizePlate(row.plate1) === focusedPlate)
        .sort((left, right) => right.timestampUtc.localeCompare(left.timestampUtc))
    : [];
  const focusedActivityScore = focusedRows.length > 0 ? buildSearchActivityScore(focusedRows) : "0000";
  const focusedPattern = focusedRows.length > 0 ? inferSearchActivityPattern(focusedRows) : null;
  const focusedFollowUp = focusedRow ? matchingFollowUpsForRow(focusedRow, props.followUps)[0] ?? null : null;
  const focusedHotlistLabel = focusedRow ? hotlistLabelForRow(focusedRow, props.hotlists) : null;
  const quickLeadRows = (props.searchGroupByPlate ? props.groupedResults.map((group) => group.rows[0]) : props.results).slice(0, 8);
  const modeLabel =
    {
      plate: "Plate / Tag",
      camera: "Camera",
      vehicle: "Vehicle Profile",
      alert: "Recovery Matches",
    }[props.searchMode] ?? titleCase(props.searchMode);
  const advancedFilterCount = [
    props.searchFromLocal,
    props.searchToLocal,
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
  const vehicleFilterCount = [
    props.searchVehicleColor,
    props.searchVehicleMake,
    props.searchVehicleModel,
    props.searchVehicleYear,
  ].filter((value) => value.trim().length > 0).length;
  const recoveryFilterCount = props.searchAlertStatus.trim().length > 0 ? 1 : 0;
  const geoFilterCount = [
    props.searchMinLatitude,
    props.searchMaxLatitude,
    props.searchMinLongitude,
    props.searchMaxLongitude,
  ].filter((value) => value.trim().length > 0).length;
  const timeFilterCount = [props.searchFromLocal, props.searchToLocal].filter((value) => value.trim().length > 0).length;
  const resultsHeadline = props.searchExecuted
    ? props.results.length !== props.resultsTotal
      ? `${props.results.length} shown of ${props.resultsTotal} read${props.resultsTotal === 1 ? "" : "s"}`
      : `${props.resultsTotal} read${props.resultsTotal === 1 ? "" : "s"} found`
    : "Recent reads";

  return (
    <section className="screen search-screen">
      <ScreenHeader
        title="Search & Locate"
        subtitle="Review sightings, search vehicle activity, and move directly into route or evidence review from the operations shell."
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
              { id: "alert" as const, label: "Recovery Matches" },
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
                      : "Recovery account plate or account notes"
              }
              type="text"
              value={props.query}
              onChange={(event) => props.setQuery(event.target.value)}
            />
            <button className="btn btn--primary" disabled={props.loading} type="submit">
              {props.loading ? "Searching..." : "Search"}
            </button>
          </div>

          <div className="search-sidebar-section">
            <div className="search-sidebar-section__header">
              <strong>Quick filters</strong>
              <span>Common field filters kept within thumb reach.</span>
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
                Group reads
              </button>
            </div>
          </div>

          <CollapsibleSection
            className="search-sidebar-section search-sidebar-section--collapsible"
            defaultOpen={timeFilterCount > 0}
            summary={summarizeFilterCount(timeFilterCount, "time filter")}
            title="Time window"
          >
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
          </CollapsibleSection>

          <CollapsibleSection
            className="search-sidebar-section search-sidebar-section--collapsible"
            defaultOpen={vehicleFilterCount > 0}
            summary={summarizeFilterCount(vehicleFilterCount, "vehicle filter")}
            title="Vehicle description"
          >
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
          </CollapsibleSection>

          <CollapsibleSection
            className="search-sidebar-section search-sidebar-section--collapsible"
            defaultOpen={recoveryFilterCount > 0}
            summary={summarizeFilterCount(recoveryFilterCount, "recovery filter")}
            title="Recovery status"
          >
            <label className="settings-input-row">
              <span>Status</span>
              <select className="select-input" value={props.searchAlertStatus} onChange={(event) => props.setSearchAlertStatus(event.target.value as DashboardAlertStatus | "")}>
                <option value="">Any recovery status</option>
                <option value="active">Active</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="dismissed">Dismissed</option>
              </select>
            </label>
          </CollapsibleSection>

          <CollapsibleSection
            className="search-sidebar-section search-sidebar-section--collapsible"
            defaultOpen={geoFilterCount > 0}
            summary={summarizeFilterCount(geoFilterCount, "coordinate")}
            title="Geo box filter"
          >
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
          </CollapsibleSection>

          <div className="button-row">
            <Tooltip text="Reset all search filters to defaults">
              <button className="btn btn--ghost" type="button" onClick={props.onClearFilters}>
                {advancedFilterCount > 0 ? `Clear ${advancedFilterCount} filter${advancedFilterCount === 1 ? "" : "s"}` : "Clear Filters"}
              </button>
            </Tooltip>
          </div>
        </form>

        <div className="search-screen__content">
          {quickLeadRows.length > 0 ? (
            <section className="panel-card locate-quick-strip">
              <div className="locate-quick-strip__header">
                <div>
                  <h3>Focus Queue</h3>
                  <p>Fast-select the next lead without losing your current search context.</p>
                </div>
                <div className="search-result-card__badges">
                  <Badge tone="cyan">{`${props.resultsTotal} reads`}</Badge>
                  {hotlistMatches > 0 ? <Badge tone="warn">{`${hotlistMatches} recovery`}</Badge> : null}
                  {advancedFilterCount > 0 ? <Badge tone="muted">{`${advancedFilterCount} filters`}</Badge> : null}
                </div>
              </div>
              <div className="locate-quick-strip__rail">
                {quickLeadRows.map((row) => (
                  <LocateQuickSelectCard
                    key={row.id}
                    dataSource={props.dataSource}
                    row={row}
                    selected={focusedRow?.id === row.id}
                    onSelect={() => props.onSelectDetection(row.id)}
                  />
                ))}
              </div>
            </section>
          ) : null}

          <div className="search-workspace-grid">
            <section className="results-panel">
              <div className="results-panel__header">
                <div>
                  <h3>{resultsHeadline}</h3>
                  <p className="screen-subtitle">
                    {focusedRow
                      ? `Focused lead ${focusedRow.plate1}${focusedPattern ? ` - ${focusedPattern.label}` : ""}`
                      : "Select a read to open the intelligence rail."}
                  </p>
                </div>
                <div className="results-panel__feedback">
                  <Badge tone="muted">{modeLabel}</Badge>
                  {props.searchError ? <span className="feedback feedback--warn">{props.searchError}</span> : null}
                  {props.searchMessage ? <span className="feedback feedback--good">{props.searchMessage}</span> : null}
                </div>
              </div>

              <div className="search-results">
                {props.loading ? (
                  <StateView
                    variant="loading"
                    title="Searching reads"
                    description="Running your query against the local read index."
                  />
                ) : props.searchError ? (
                  <StateView
                    variant="error"
                    title="Search failed"
                    description={props.searchError}
                    action={{ label: "Try again", onClick: props.onRetrySearch, tone: "ghost" }}
                  />
                ) : props.results.length === 0 ? (
                  <StateView
                    title={props.searchExecuted ? "No reads matched" : "Ready to search"}
                    description={
                      props.searchExecuted
                        ? "Widen the plate fragment, adjust the time window, or remove active filters."
                        : "Enter a plate fragment or recovery filter above to pull matching reads."
                    }
                    action={props.searchExecuted ? { label: "Clear filters", onClick: props.onClearFilters, tone: "ghost" } : undefined}
                  />
                ) : props.searchGroupByPlate ? (
                  props.groupedResults.map((group) => {
                    const expanded = props.expandedGroups[group.plate] ?? false;
                    const rows = expanded ? group.rows : group.rows.slice(0, 1);
                    const lead = group.rows[0];
                    const groupScore = buildSearchActivityScore(group.rows);
                    const leadFollowUp = matchingFollowUpsForRow(lead, props.followUps)[0] ?? null;
                    const leadHotlistLabel = hotlistLabelForRow(lead, props.hotlists);
                    return (
                      <article key={group.plate} className="result-group-card">
                        <div className="result-group-card__header">
                          <div className="result-group-card__identity">
                            <div className="result-group-card__plate-line">
                              <strong>{group.plate}</strong>
                              <span className={`conf-badge conf-badge--${confidenceTone(confidencePercent(lead.conf))}`}>{confidenceLabel(lead.conf)}</span>
                              {lead.hotlist ? <Badge tone="critical">Recovery</Badge> : null}
                              {leadHotlistLabel ? <Badge tone="warn">{leadHotlistLabel}</Badge> : null}
                            </div>
                            <p className="result-group-card__vehicle-line">{lead.vehicle}</p>
                            <p className="result-group-card__location-line">{formatDetectionLocationLine(lead)}</p>
                            <p className="result-group-card__meta-line">{formatDetectionTimestampGpsLine(lead)}</p>
                            <p className="result-group-card__meta-line">{`${formatDetectionCameraLine(lead, groupScore)} • ${group.rows.length} reads`}</p>
                          </div>
                          <div className="result-group-card__meta">
                            {leadFollowUp ? <FollowUpStatusPill status={leadFollowUp.status} /> : null}
                            {lead.alertStatus ? <Badge tone={alertStatusTone(lead.alertStatus)}>{alertStatusLabel(lead.alertStatus)}</Badge> : null}
                            {group.rows.length > 1 ? (
                              <button className="link-button" type="button" onClick={() => props.onToggleExpanded(group.plate)}>
                                {expanded ? "Collapse" : `${group.rows.length} reads`}
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <div className="result-group-list">
                          {rows.map((row) => (
                            <SearchResultCard
                              key={row.id}
                              dataSource={props.dataSource}
                              followUp={matchingFollowUpsForRow(row, props.followUps)[0] ?? null}
                              hotlistLabel={hotlistLabelForRow(row, props.hotlists)}
                              row={row}
                              selected={focusedRow?.id === row.id}
                              onAddToHotlist={() => props.onAddToHotlist(row)}
                              onCopy={props.onCopyPlate}
                              onDetails={() => props.onDetails(row)}
                              onMap={() => props.onMap(row)}
                              onSelect={() => props.onSelectDetection(row.id)}
                            />
                          ))}
                        </div>
                      </article>
                    );
                  })
                ) : (
                  props.results.map((row) => (
                    <SearchResultCard
                      key={row.id}
                      dataSource={props.dataSource}
                      followUp={matchingFollowUpsForRow(row, props.followUps)[0] ?? null}
                      hotlistLabel={hotlistLabelForRow(row, props.hotlists)}
                      row={row}
                      selected={focusedRow?.id === row.id}
                      onAddToHotlist={() => props.onAddToHotlist(row)}
                      onCopy={props.onCopyPlate}
                      onDetails={() => props.onDetails(row)}
                      onMap={() => props.onMap(row)}
                      onSelect={() => props.onSelectDetection(row.id)}
                    />
                  ))
                )}
              </div>
            </section>

            <SearchLeadPanel
              dataSource={props.dataSource}
              followUp={focusedFollowUp}
              hotlistLabel={focusedHotlistLabel}
              onAddToHotlist={() => {
                if (focusedRow) {
                  props.onAddToHotlist(focusedRow);
                }
              }}
              onCopy={props.onCopyPlate}
              onDetails={() => {
                if (focusedRow) {
                  props.onDetails(focusedRow);
                }
              }}
              onMap={() => {
                if (focusedRow) {
                  props.onMap(focusedRow);
                }
              }}
              onSelectRow={props.onSelectDetection}
              relatedRows={focusedRows}
              row={focusedRow}
              selectedRowId={focusedRow?.id ?? props.selectedDetectionId}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function AccountsScreen(props: {
  activeDestination: string;
  canManageAccounts: boolean;
  dataSource: DataSource;
  deleting: boolean;
  draft: HotlistDraft;
  error: string | null;
  hotlists: DashboardHotlist[];
  message: string | null;
  saving: boolean;
  selectedDetectionPlate: string;
  selectedHotlistId: string | null;
  onClearDraft: () => void;
  onDelete: () => void;
  onDraftChange: (draft: HotlistDraft | ((current: HotlistDraft) => HotlistDraft)) => void;
  onSeedFromDetection: () => void;
  onSeedFromRoute: () => void;
  onSelect: (entry: DashboardHotlist) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}): ReactElement {
  const armedAccounts = props.hotlists.filter((entry) => entry.active).length;
  const plateAlertingReady = Boolean(trimValue(props.draft.plateText));
  const profileReady = Boolean(trimValue(props.draft.vehicleMake) && trimValue(props.draft.vehicleModel));
  const addressReady = Boolean(trimValue(props.draft.addressLine1) || trimValue(props.draft.addressLabel));
  const [orderSearch, setOrderSearch] = useState("");
  const [orderFilter, setOrderFilter] = useState<"all" | "active" | "paused" | "addressReady">("all");
  const selectedEntry = props.selectedHotlistId ? props.hotlists.find((entry) => entry.entry_id === props.selectedHotlistId) ?? null : null;
  const lprLinkedOrders = props.hotlists.filter((entry) => accountAlertingMode(entry) === "plate").length;
  const addressReadyOrders = props.hotlists.filter((entry) => Boolean(trimValue(entry.address_line1 ?? "") || trimValue(entry.address_label ?? ""))).length;
  const filteredHotlists = useMemo(() => {
    const normalizedQuery = normalizePlate(orderSearch);
    return props.hotlists.filter((entry) => {
      if (orderFilter === "active" && !entry.active) {
        return false;
      }
      if (orderFilter === "paused" && entry.active) {
        return false;
      }
      if (orderFilter === "addressReady" && !trimValue(entry.address_line1 ?? "") && !trimValue(entry.address_label ?? "")) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      const fields = [
        entry.plate_text,
        entry.vin,
        entry.label,
        entry.address_label,
        entry.address_line1,
        entry.address_city,
        entry.vehicle_make,
        entry.vehicle_model,
      ].filter((value): value is string => Boolean(value));
      return fields.some((value) => normalizePlate(value).includes(normalizedQuery) || value.toLowerCase().includes(orderSearch.trim().toLowerCase()));
    });
  }, [orderFilter, orderSearch, props.hotlists]);
  const selectedOrderLabel = trimValue(props.draft.label) || selectedEntry?.label || "Unlabeled order";
  const selectedOrderAddress = trimValue(props.draft.addressLine1) || trimValue(selectedEntry?.address_line1 ?? "") || props.activeDestination || "No address on file";
  const recordStateLabel = props.draft.active ? "Active in operations" : "Admin only";
  const selectedOrderUpdatedAt = selectedEntry ? formatDateTime(selectedEntry.updated_at_utc) : "Draft not saved yet";
  const detectionSeedLabel = props.selectedDetectionPlate || "No detection selected";
  const routeSeedLabel = props.activeDestination || "No route staged";

  return (
    <section className="screen hotlists-screen repo-admin-screen">
      <ScreenHeader
        title="Repo Orders"
        subtitle="Create, update, and organize the active repo orders that power matching, mapping, and field operations."
        meta={
          <>
            <Badge tone="critical">{`${armedAccounts} active`}</Badge>
            <Badge tone={props.dataSource === "live" ? "success" : "muted"}>{props.dataSource.toUpperCase()}</Badge>
          </>
        }
      />

      <div className="repo-admin-summary-strip">
        <div className="repo-admin-summary-tile">
          <span>Active Orders</span>
          <strong>{armedAccounts}</strong>
          <small>Visible in operations</small>
        </div>
        <div className="repo-admin-summary-tile">
          <span>LPR Linked</span>
          <strong>{lprLinkedOrders}</strong>
          <small>Orders with live plate matching</small>
        </div>
        <div className="repo-admin-summary-tile">
          <span>Address Ready</span>
          <strong>{addressReadyOrders}</strong>
          <small>Orders with a destination on file</small>
        </div>
        <div className="repo-admin-summary-tile">
          <span>Route Staged</span>
          <strong>{props.activeDestination ? "Yes" : "No"}</strong>
          <small>{props.activeDestination || "No current route target"}</small>
        </div>
      </div>

      <div className="hotlists-grid">
        <section className="panel-card hotlists-list-card">
          <div className="panel-card__header">
            <div>
              <h3>Order Queue</h3>
              <p>{`${armedAccounts} armed · ${props.hotlists.length} total · ${props.canManageAccounts ? "Write access" : "Read only"}`}</p>
            </div>
            <Tooltip text="Start a new repo order record">
              <button className="btn btn--ghost" disabled={!props.canManageAccounts} type="button" onClick={props.onClearDraft}>
                New Order
              </button>
            </Tooltip>
          </div>
          <div className="repo-admin-toolbar">
            <input
              className="text-input"
              placeholder="Search plate, VIN, label, or city"
              type="text"
              value={orderSearch}
              onChange={(event) => setOrderSearch(event.target.value)}
            />
            <div className="segmented-control repo-admin-filter-tabs">
              <button className={orderFilter === "all" ? "is-active" : ""} type="button" onClick={() => setOrderFilter("all")}>
                All
              </button>
              <button className={orderFilter === "active" ? "is-active" : ""} type="button" onClick={() => setOrderFilter("active")}>
                Active
              </button>
              <button className={orderFilter === "paused" ? "is-active" : ""} type="button" onClick={() => setOrderFilter("paused")}>
                Paused
              </button>
              <button className={orderFilter === "addressReady" ? "is-active" : ""} type="button" onClick={() => setOrderFilter("addressReady")}>
                Address Ready
              </button>
            </div>
          </div>
          <div className="hotlist-list">
            {props.hotlists.length === 0 ? (
              <StateView
                title="No repo orders"
                description="Add a plate, VIN, vehicle profile, and address context to stage your first active recovery order."
                action={props.canManageAccounts ? { label: "New order", onClick: props.onClearDraft } : undefined}
              />
            ) : filteredHotlists.length === 0 ? (
              <StateView
                size="compact"
                title="No matching orders"
                description="Adjust the admin filters or clear the current search to see more repo orders."
                action={{ label: "Clear search", onClick: () => setOrderSearch(""), tone: "ghost" }}
              />
            ) : (
              filteredHotlists.map((entry) => {
                const rowLabel = trimValue(entry.label ?? "");
                const rowAddress = hotlistAddressSummary(entry);
                return (
                  <button
                    key={entry.entry_id}
                    className={`hotlist-row severity-band severity-band--${entry.active ? "critical" : "observed"} ${props.selectedHotlistId === entry.entry_id ? "is-selected" : ""}`}
                    type="button"
                    onClick={() => props.onSelect(entry)}
                  >
                    <div className="repo-admin-row__primary">
                      <strong>{rowLabel || hotlistIdentifierSummary(entry)}</strong>
                      <span>{rowLabel ? hotlistIdentifierSummary(entry) : rowAddress}</span>
                    </div>
                    <div className="hotlist-row__meta">
                      <Badge tone={entry.active ? "critical" : "muted"}>{entry.active ? "Active" : "Paused"}</Badge>
                      <Badge tone={accountAlertingMode(entry) === "plate" ? "success" : "warn"}>
                        {accountAlertingMode(entry) === "plate" ? "LPR linked" : "Profile only"}
                      </Badge>
                      {rowLabel ? <span>{rowAddress}</span> : null}
                      <span>{formatDateTime(entry.updated_at_utc)}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className="panel-card hotlist-editor-card">
          <div className="panel-card__header repo-admin-detail-header">
            <div>
              <h3>{props.selectedHotlistId ? "Edit Repo Order" : "Create Repo Order"}</h3>
              <p>Structure vehicle, address, and activation details here before sending the order into active field operations.</p>
            </div>
            <div className="button-row repo-admin-header-actions">
              <button className="btn btn--ghost" disabled={!props.canManageAccounts} type="button" onClick={props.onSeedFromDetection}>
                Use Current Plate
              </button>
              <button className="btn btn--ghost" disabled={!props.canManageAccounts} type="button" onClick={props.onSeedFromRoute}>
                Use Current Route
              </button>
            </div>
          </div>
          <div className="repo-admin-overview-grid">
            <div className="repo-admin-overview-card">
              <span>Order Label</span>
              <strong>{selectedOrderLabel}</strong>
              <small>{props.selectedHotlistId ? "Saved order record" : "New draft order"}</small>
            </div>
            <div className="repo-admin-overview-card">
              <span>Match Readiness</span>
              <strong>{plateAlertingReady ? "LPR linked" : "Profile only"}</strong>
              <small>{plateAlertingReady ? "Plate will trigger live matches" : "Add a plate to enable live matching"}</small>
            </div>
            <div className="repo-admin-overview-card">
              <span>Address State</span>
              <strong>{selectedOrderAddress}</strong>
              <small>{selectedOrderAddress === "No address on file" ? "No destination linked yet" : "Available to the operations workspace"}</small>
            </div>
            <div className="repo-admin-overview-card">
              <span>Record State</span>
              <strong>{recordStateLabel}</strong>
              <small>{selectedOrderUpdatedAt}</small>
            </div>
          </div>
          <form className="hotlist-form repo-admin-form" onSubmit={(event) => void props.onSubmit(event)}>
            <section className="repo-admin-section">
              <div className="repo-admin-section__header">
                <div>
                  <h4>Vehicle identifiers</h4>
                  <p>Primary keys that power order matching and live scan linking.</p>
                </div>
                <Badge tone={plateAlertingReady ? "success" : "warn"}>{plateAlertingReady ? "Match ready" : "Plate needed"}</Badge>
              </div>
              <div className="detail-note-callout">
                <strong>Order intake</strong>
                <p>
                  Create this repo order by plate, VIN, or vehicle profile. Orders with a linked plate feed live matching first,
                  while VIN and vehicle details keep the record searchable and useful for investigation.
                </p>
              </div>

              <div className="repo-admin-inline-metrics">
                <div className="repo-admin-metric">
                  <span>Current detection seed</span>
                  <strong>{detectionSeedLabel}</strong>
                </div>
                <div className="repo-admin-metric">
                  <span>Current route seed</span>
                  <strong>{routeSeedLabel}</strong>
                </div>
              </div>

              <div className="search-filter-grid repo-admin-fields">
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
                  <span>VIN</span>
                  <input
                    className="text-input"
                    placeholder="1HGCM82633A004352"
                    type="text"
                    value={props.draft.vin}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        vin: normalizeUpperValue(event.target.value),
                      }))
                    }
                  />
                </label>
              </div>
            </section>

            <section className="repo-admin-section">
              <div className="repo-admin-section__header">
                <div>
                  <h4>Vehicle profile</h4>
                  <p>Secondary descriptors used for visual confirmation and future record expansion.</p>
                </div>
                <Badge tone={profileReady ? "success" : "muted"}>{profileReady ? "Ready" : "Optional"}</Badge>
              </div>
              <div className="search-filter-grid repo-admin-fields">
                <label>
                  <span>Year</span>
                  <input
                    className="text-input"
                    placeholder="2019"
                    type="text"
                    value={props.draft.vehicleYear}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        vehicleYear: trimValue(event.target.value),
                      }))
                    }
                  />
                </label>
                <label>
                  <span>Make</span>
                  <input
                    className="text-input"
                    placeholder="Ford"
                    type="text"
                    value={props.draft.vehicleMake}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        vehicleMake: trimValue(event.target.value),
                      }))
                    }
                  />
                </label>
                <label>
                  <span>Model</span>
                  <input
                    className="text-input"
                    placeholder="Explorer"
                    type="text"
                    value={props.draft.vehicleModel}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        vehicleModel: trimValue(event.target.value),
                      }))
                    }
                  />
                </label>
                <label>
                  <span>Color</span>
                  <input
                    className="text-input"
                    placeholder="Black"
                    type="text"
                    value={props.draft.vehicleColor}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        vehicleColor: trimValue(event.target.value),
                      }))
                    }
                  />
                </label>
              </div>
            </section>

            <section className="repo-admin-section">
              <div className="repo-admin-section__header">
                <div>
                  <h4>Address intelligence</h4>
                  <p>Primary destination and access context passed through to the field workspace.</p>
                </div>
                <Badge tone={addressReady ? "success" : "muted"}>
                  {addressReady ? "Address ready" : "Optional"}
                </Badge>
              </div>
              <div className="search-filter-grid repo-admin-fields">
                <label>
                  <span>Address label</span>
                  <input
                    className="text-input"
                    placeholder="Debtor home, office lot, or impound"
                    type="text"
                    value={props.draft.addressLabel}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        addressLabel: trimValue(event.target.value),
                      }))
                    }
                  />
                </label>
                <label>
                  <span>Address line 1</span>
                  <input
                    className="text-input"
                    placeholder="123 Main St"
                    type="text"
                    value={props.draft.addressLine1}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        addressLine1: trimValue(event.target.value),
                      }))
                    }
                  />
                </label>
                <label>
                  <span>Address line 2</span>
                  <input
                    className="text-input"
                    placeholder="Apt, suite, or lot detail"
                    type="text"
                    value={props.draft.addressLine2}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        addressLine2: trimValue(event.target.value),
                      }))
                    }
                  />
                </label>
                <label>
                  <span>City</span>
                  <input
                    className="text-input"
                    placeholder="Chicago"
                    type="text"
                    value={props.draft.addressCity}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        addressCity: trimValue(event.target.value),
                      }))
                    }
                  />
                </label>
                <label>
                  <span>State</span>
                  <input
                    className="text-input"
                    placeholder="IL"
                    type="text"
                    value={props.draft.addressState}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        addressState: normalizeUpperValue(event.target.value),
                      }))
                    }
                  />
                </label>
                <label>
                  <span>ZIP</span>
                  <input
                    className="text-input"
                    placeholder="60607"
                    type="text"
                    value={props.draft.addressPostalCode}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        addressPostalCode: trimValue(event.target.value),
                      }))
                    }
                  />
                </label>
              </div>
              <div className="repo-admin-inline-metrics">
                <div className="repo-admin-metric">
                  <span>Operations map label</span>
                  <strong>{selectedOrderAddress}</strong>
                </div>
                <div className="repo-admin-metric">
                  <span>Route handoff</span>
                  <strong>{props.activeDestination ? "Ready to seed" : "No staged route"}</strong>
                </div>
              </div>
            </section>

            <section className="repo-admin-section">
              <div className="repo-admin-section__header">
                <div>
                  <h4>Order administration</h4>
                  <p>Operator-facing labels, notes, and activation state that determine how the order appears in the field workspace.</p>
                </div>
                <Badge tone={props.draft.active ? "success" : "muted"}>{recordStateLabel}</Badge>
              </div>

              <div className="search-filter-grid repo-admin-fields">
                <label className="repo-admin-field--wide">
                  <span>Order label / client reference</span>
                  <input
                    className="text-input"
                    placeholder="Client name, case ID, or internal order label"
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

                <label className="repo-admin-field--wide">
                  <span>Order notes</span>
                  <textarea
                    className="text-area"
                    placeholder="Tow instructions, debtor notes, parking pattern, access concerns, or escalation steps"
                    value={props.draft.notes}
                    onChange={(event) =>
                      props.onDraftChange((current) => ({
                        ...current,
                        notes: event.target.value,
                      }))
                    }
                  />
                </label>
              </div>

              <div className="repo-admin-inline-metrics">
                <div className="repo-admin-metric">
                  <span>Record status</span>
                  <strong>{recordStateLabel}</strong>
                </div>
                <div className="repo-admin-metric">
                  <span>Last saved</span>
                  <strong>{selectedOrderUpdatedAt}</strong>
                </div>
              </div>

              <div className="inline-setting">
                <div>
                  <strong>Active in operations</strong>
                  <span>{plateAlertingReady ? "Shows in field operations and can trigger live LPR matches." : "Saved for order management until a plate is added."}</span>
                </div>
                <Toggle
                  checked={props.draft.active}
                  label="Order active"
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
              {!plateAlertingReady ? (
                <div className="feedback feedback--warn">
                  This order has no plate yet. Live LPR matching stays limited until a plate is added.
                </div>
              ) : null}

              <div className="repo-admin-actions">
                <Tooltip text={props.selectedHotlistId ? "Save changes to this repo order" : "Create a new repo order"}>
                  <button className="btn btn--primary" disabled={!props.canManageAccounts || props.saving} type="submit">
                    {props.saving ? "Saving..." : props.selectedHotlistId ? "Save Order" : "Create Order"}
                  </button>
                </Tooltip>
                <Tooltip text="Reset the form to start a new entry">
                  <button className="btn btn--ghost" disabled={!props.canManageAccounts} type="button" onClick={props.onClearDraft}>
                    Clear Draft
                  </button>
                </Tooltip>
                <Tooltip text="Fill form with the currently selected detection">
                  <button className="btn btn--ghost" disabled={!props.canManageAccounts} type="button" onClick={props.onSeedFromDetection}>
                    Seed {props.selectedDetectionPlate || "selection"}
                  </button>
                </Tooltip>
                <Tooltip text="Permanently remove this repo order">
                  <button className="btn btn--danger" disabled={!props.canManageAccounts || !props.selectedHotlistId || props.deleting} type="button" onClick={props.onDelete}>
                    {props.deleting ? "Deleting..." : "Delete Order"}
                  </button>
                </Tooltip>
              </div>
            </section>
          </form>
        </section>
      </div>
    </section>
  );
}

function HotlistsScreen(props: {
  activeDestination: string;
  alertActionError: string | null;
  alertActionId: string | null;
  alertActionMessage: string | null;
  alerts: HotlistAlertItem[];
  canManageFollowUps: boolean;
  canUpdateAlerts: boolean;
  activity: RecognitionActivityItem[];
  activeTab: HotlistsWorkspaceTab;
  dataSource: DataSource;
  followUps: FollowUpRecord[];
  followUpActionError: string | null;
  followUpActionMessage: string | null;
  followUpSaving: boolean;
  hotlists: DashboardHotlist[];
  openFollowUps: number;
  selectedAlertId: string | null;
  alertResponseNotes: string;
  onAlertResponseNotesChange: (notes: string) => void;
  onAlertStatusChange: (alert: DashboardAlert, status: DashboardAlertStatus, responseNotes?: string) => void;
  onMapDetection: (detectionId: string | null | undefined) => void;
  onOpenRecord: (detectionId: string | null | undefined) => void;
  onSaveFollowUp: (request: FollowUpSaveRequest) => Promise<void>;
  onSelectAlert: (alertId: string | null) => void;
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
  }));
  const focusedAlertCase = alertCases.find((item) => item.alert.alert_id === props.selectedAlertId) ?? alertCases[0] ?? null;
  const focusedChecklist = focusedAlertCase
    ? buildVerificationChecklist({
        accountLabel: focusedAlertCase.entry?.label ?? focusedAlertCase.alert.hotlist_label,
        confidence: focusedAlertCase.alert.match_confidence,
        gps: focusedAlertCase.row?.gps ?? formatGpsValue(focusedAlertCase.alert.gps_latitude, focusedAlertCase.alert.gps_longitude),
        hasFrame: Boolean(focusedAlertCase.row),
        hasPlateCrop: Boolean(focusedAlertCase.row),
        notes: focusedAlertCase.entry?.notes ?? focusedAlertCase.alert.notes,
        plateText: focusedAlertCase.alert.matched_plate_text,
        vehicleLabel: focusedAlertCase.row?.vehicle ?? null,
      })
    : [];
  const [followUpDraft, setFollowUpDraft] = useState<FollowUpDraftState>(() => buildFollowUpDraft(null));

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
  }, [
    focusedAlertCase?.alert.alert_id,
    focusedAlertCase?.followUps[0]?.updated_at_utc,
  ]);

  return (
    <section className="screen hotlists-screen">
      <ScreenHeader
        title="LPR Hits"
        subtitle="Review live LPR matches, verify confidence, and update recovery queue status from the operations shell."
        meta={
          <>
            <Badge tone={activeAlertCount > 0 ? "warn" : "muted"}>{`${activeAlertCount} active`}</Badge>
            <Badge tone={props.dataSource === "live" ? "success" : "muted"}>{props.dataSource.toUpperCase()}</Badge>
          </>
        }
      />

      <div className="segmented-control hotlists-toolbar-tabs">
        <button className={props.activeTab === "alerts" ? "is-active" : ""} type="button" onClick={() => props.onTabChange("alerts")}>
          {`LPR Hits (${props.alerts.length})`}
        </button>
        <button className={props.activeTab === "recognition" ? "is-active" : ""} type="button" onClick={() => props.onTabChange("recognition")}>
          {`Recent Sightings (${props.activity.length})`}
        </button>
      </div>

      {props.activeTab === "alerts" ? (
        <div className="recovery-queue-grid">
          <section className="panel-card hotlists-workspace-card hotlists-queue-card">
            <div className="panel-card__header">
              <div>
                <h3>Active Hit Queue</h3>
                <p>{`${activeAlertCount} active · ${acknowledgedAlertCount} acknowledged · ${props.openFollowUps} follow-up`}</p>
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
                <StateView
                  title="No active recovery cases"
                  description="Scanned plates matching armed accounts will appear here."
                />
              ) : (
                alertCases.map(({ alert, row, entry }) => {
                  const matchConfidence = confidenceLabel(confidencePercent(alert.match_confidence));
                  const queueSeverity = detectionSeverityForRow({
                    alertStatus: alert.status,
                    hotlist: row?.hotlist ?? true,
                  });
                  return (
                    <button
                      key={alert.alert_id}
                      className={`queue-row queue-row--${queueSeverity} ${props.selectedAlertId === alert.alert_id ? "is-selected" : ""}`}
                      type="button"
                      onClick={() => props.onSelectAlert(alert.alert_id)}
                    >
                      <div className="queue-row__header">
                        <div>
                          <strong>{alert.matched_plate_text}</strong>
                          <span>{entry?.label ?? alert.hotlist_label ?? row?.vehicle ?? "Recovery case"}</span>
                        </div>
                        <div className="queue-row__badges">
                          <RecoveryStatePill state={alert.status} />
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
                </div>

                <div className="case-note-stack">
                  <div className="detail-note-callout detail-note-callout--checklist">
                    <strong>Verification gate</strong>
                    <VerificationChecklist compact items={focusedChecklist} />
                  </div>
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
                </div>

                <div className="detail-grid">
                  <DetailField label="Vehicle" value={focusedAlertCase.row?.vehicle ?? "Unclassified vehicle"} />
                  <DetailField label="GPS" value={focusedAlertCase.row?.gps ?? formatGpsValue(focusedAlertCase.alert.gps_latitude, focusedAlertCase.alert.gps_longitude)} />
                  <DetailField
                    label="Recovery address"
                    value={props.activeDestination}
                  />
                  <DetailField label="Permissions" value={props.canManageFollowUps ? "Follow-up write" : "Read only"} />
                </div>

                <div className="form-row">
                  <label className="form-label" htmlFor="alert-response-notes">Recovery notes</label>
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
                    <Tooltip text="Acknowledge this alert and begin response">
                      <button
                        className="btn btn--primary"
                        disabled={!props.canUpdateAlerts || props.alertActionId === focusedAlertCase.alert.alert_id}
                        type="button"
                        onClick={() => props.onAlertStatusChange(focusedAlertCase.alert, "acknowledged", props.alertResponseNotes || undefined)}
                      >
                        {props.alertActionId === focusedAlertCase.alert.alert_id ? "Updating..." : "Acknowledge"}
                      </button>
                    </Tooltip>
                  ) : null}
                  {focusedAlertCase.alert.status !== "dismissed" ? (
                    <Tooltip text="Stand down and dismiss this alert">
                      <button
                        className="btn btn--ghost"
                        disabled={!props.canUpdateAlerts || props.alertActionId === focusedAlertCase.alert.alert_id}
                        type="button"
                        onClick={() => props.onAlertStatusChange(focusedAlertCase.alert, "dismissed", props.alertResponseNotes || undefined)}
                      >
                        {props.alertActionId === focusedAlertCase.alert.alert_id ? "Updating..." : "Stand Down"}
                      </button>
                    </Tooltip>
                  ) : null}
                  {focusedAlertCase.alert.status !== "active" ? (
                    <Tooltip text="Reopen this alert for further response">
                      <button
                        className="btn btn--ghost"
                        disabled={!props.canUpdateAlerts || props.alertActionId === focusedAlertCase.alert.alert_id}
                        type="button"
                        onClick={() => props.onAlertStatusChange(focusedAlertCase.alert, "active", props.alertResponseNotes || undefined)}
                      >
                        {props.alertActionId === focusedAlertCase.alert.alert_id ? "Updating..." : "Reopen"}
                      </button>
                    </Tooltip>
                  ) : null}
                  <Tooltip text="View full detection record">
                    <button className="btn btn--ghost" disabled={!focusedAlertCase.row} type="button" onClick={() => props.onOpenRecord(focusedAlertCase.alert.detection_id)}>
                      Open Record
                    </button>
                  </Tooltip>
                  <Tooltip text="Route to this vehicle's last-seen point">
                    <button className="btn btn--ghost" disabled={!focusedAlertCase.row} type="button" onClick={() => props.onMapDetection(focusedAlertCase.alert.detection_id)}>
                      Route to Last Seen
                    </button>
                  </Tooltip>
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

                </div>
              </>
            ) : (
              <StateView
                title="No case selected"
                description="Select a recovery case from the queue or wait for a new plate match."
              />
            )}
          </section>
        </div>
      ) : null}

      {props.activeTab === "recognition" ? (
        <section className="panel-card hotlists-workspace-card">
          <div className="panel-card__header">
            <div>
              <h3>Scan Feed</h3>
            </div>
            <Badge tone="cyan">{`${props.activity.length} events`}</Badge>
          </div>
          <div className="record-list">
            {props.activity.length === 0 ? (
              <StateView
                title="No scan activity"
                description="LPR reads and recovery matches will appear here as they occur."
              />
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
  canManageFollowUps: boolean;
  canViewAudit: boolean;
  canUpdateAlerts: boolean;
  currentPrincipal: OperatorPrincipal | null;
  dataError: string | null;
  dataSource: DataSource;
  degradedDependencyCount: number;
  edgeRuntime: EdgeRuntimeStatus | null;
  edgeRuntimeAction: EdgeRuntimeCommand | null;
  edgeRuntimeError: string | null;
  hotlistWarning: boolean;
  onSettingsSectionChange: (section: SettingsSection) => void;
  onApiKeyApply: () => void;
  onApiKeyChange: (value: string) => void;
  onEdgeRuntimeCommand: (command: EdgeRuntimeCommand) => void;
  onRefresh: () => void;
  onlineCameras: number;
  settings: UiSettings;
  settingsSection: SettingsSection;
  serviceHealthState: ServiceHealthState;
  totalCameras: number;
  updateSetting: <Key extends keyof UiSettings>(key: Key, value: UiSettings[Key]) => void;
}): ReactElement {
  const sections: Array<{ id: SettingsSection; title: string; description: string }> = [
    { id: "workspace", title: "Field workflow", description: "Arrival scan, suppression, and confidence thresholds." },
    { id: "alerts", title: "Alert behavior", description: "Recovery match behavior, audio, and permissions." },
    { id: "cameras", title: "Cameras", description: "Resolution, night mode, and feed controls." },
    { id: "map", title: "Map and geofence", description: "Radius, route display, and navigation." },
    { id: "system", title: "System, audit, and API", description: "Health, connection, sessions, and audit." },
  ];
  const activeSection = sections.find((section) => section.id === props.settingsSection) ?? sections[0];
  const canControlEdgeRuntime =
    props.dataSource === "live" && props.currentPrincipal?.capabilities.can_control_edge_runtime === true;
  const edgeCommandPending = props.edgeRuntimeAction !== null;
  const operatorLabel = props.currentPrincipal?.display_name ?? props.currentPrincipal?.principal_id ?? "Local operator";
  const auditStatusLabel = !props.canViewAudit
    ? "Restricted"
    : props.auditLoading
      ? "Loading"
      : props.auditError
        ? "Unavailable"
        : `${props.auditEvents.length} recent`;
  const liveFeedLabel = `${props.onlineCameras}/${Math.max(props.totalCameras, 1)}`;

  return (
    <section className="screen settings-screen">
      <ScreenHeader
        title="Admin Settings"
        subtitle="Control field behavior, connectivity, audit visibility, and system defaults from the admin shell."
        meta={
          <>
            {props.hotlistWarning ? <Badge tone="warn">Review recovery settings</Badge> : <Badge tone="success">Operational</Badge>}
            <Badge tone={props.dataSource === "live" ? "success" : "muted"}>{props.dataSource.toUpperCase()}</Badge>
            <Badge tone={serviceHealthTone(props.serviceHealthState)}>
              {props.degradedDependencyCount === 0 ? serviceHealthLabel(props.serviceHealthState).toUpperCase() : `${props.degradedDependencyCount} WARNINGS`}
            </Badge>
          </>
        }
      />

      <div className="settings-summary-strip admin-settings-summary-strip">
        <div className="settings-summary-tile">
          <span>Operator</span>
          <strong>{operatorLabel}</strong>
          <small>{props.canManageAccounts ? "Admin write available" : "Read-only account access"}</small>
        </div>
        <div className="settings-summary-tile">
          <span>System Health</span>
          <strong>{serviceHealthLabel(props.serviceHealthState)}</strong>
          <small>{props.degradedDependencyCount === 0 ? "All services nominal" : `${props.degradedDependencyCount} warnings to review`}</small>
        </div>
        <div className="settings-summary-tile">
          <span>Edge Capture</span>
          <strong>{edgeCaptureLabel(props.edgeRuntime?.capture_state)}</strong>
          <small>{props.edgeRuntime?.edge_node_id ?? "Awaiting edge runtime status"}</small>
        </div>
        <div className="settings-summary-tile">
          <span>Audit Access</span>
          <strong>{auditStatusLabel}</strong>
          <small>{props.canViewAudit ? "Recent operator events available" : "Audit visibility restricted"}</small>
        </div>
        <div className="settings-summary-tile">
          <span>Live Feeds</span>
          <strong>{liveFeedLabel}</strong>
          <small>{props.dataSource === "live" ? "Camera status from backend" : "Demo mode camera state"}</small>
        </div>
      </div>

      <div className="settings-workspace">
        <aside className="panel-card settings-nav-card">
          <div className="panel-card__header">
            <div>
              <h3>Admin Console</h3>
              <p>Choose which operational control surface to update.</p>
            </div>
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
              {props.settingsSection === "system" ? <Badge tone={serviceHealthTone(props.serviceHealthState)}>{serviceHealthLabel(props.serviceHealthState)}</Badge> : null}
              {props.settingsSection === "system" ? <Badge tone={edgeCaptureBadgeTone(props.edgeRuntime?.capture_state)}>{edgeCaptureLabel(props.edgeRuntime?.capture_state)}</Badge> : null}
            </div>
          </div>

          <div className="settings-detail-stack">
            <section className="settings-section-banner">
              <div className="settings-section-banner__copy">
                <span>Now Editing</span>
                <strong>{activeSection.title}</strong>
                <p>{activeSection.description}</p>
              </div>
              <div className="settings-section-banner__stats">
                <div className="settings-section-banner__stat">
                  <span>Data source</span>
                  <strong>{props.dataSource.toUpperCase()}</strong>
                </div>
                <div className="settings-section-banner__stat">
                  <span>Sessions</span>
                  <strong>{props.activeSessions}</strong>
                </div>
                <div className="settings-section-banner__stat">
                  <span>Alerts</span>
                  <strong>{props.canUpdateAlerts ? "Writable" : "Read only"}</strong>
                </div>
              </div>
            </section>

            {props.settingsSection === "workspace" ? (
              <>
                <SettingsSectionBlock title="Scan thresholds" description="Tune how aggressively the workspace promotes LPR activity into actionable recovery work.">
                  <SettingsRangeRow title="Duplicate suppression" detail={`${props.settings.duplicateSuppressionSeconds} sec`} min={15} max={300} step={15} value={props.settings.duplicateSuppressionSeconds} onChange={(value) => props.updateSetting("duplicateSuppressionSeconds", value)} />
                  <SettingsRangeRow title="Min OCR confidence" detail={`${props.settings.minConfidence}%`} min={60} max={99} step={1} value={props.settings.minConfidence} onChange={(value) => props.updateSetting("minConfidence", value)} />
                </SettingsSectionBlock>
                <SettingsSectionBlock title="Workflow references" description="Read-only reminders about where the live field workflow is controlled.">
                  <ReadOnlyRow title="Idle scan control" value="Console CTA" detail="Idle scanning is toggled from the console, not from the map." />
                  <ReadOnlyRow title="Arrival scan behavior" value={props.settings.autoArrivalScan ? "Auto at destination" : "Disabled"} detail="Configured in Map and geofence settings." />
                </SettingsSectionBlock>
              </>
            ) : null}

            {props.settingsSection === "alerts" ? (
              <>
                <SettingsSectionBlock title="Recovery notices" description="Control how match alerts are presented in the field and how intrusive they should be.">
                  <SettingsToggleRow title="Recovery notifications" detail="Show a full-screen recovery notice when an assigned plate is scanned." checked={props.settings.hotlistAlerts} onChange={(checked) => props.updateSetting("hotlistAlerts", checked)} />
                  <SettingsToggleRow title="Audible alerts" detail="Play tone on recovery match." checked={props.settings.soundEnabled} onChange={(checked) => props.updateSetting("soundEnabled", checked)} />
                  <SettingsToggleRow title="Vibration" detail="Haptic feedback for field devices." checked={props.settings.vibrationEnabled} onChange={(checked) => props.updateSetting("vibrationEnabled", checked)} />
                  <SettingsRangeRow title="Alert volume" detail={`${props.settings.alertVolume}%`} min={0} max={100} step={5} value={props.settings.alertVolume} onChange={(value) => props.updateSetting("alertVolume", value)} />
                  <SettingsSelectRow title="Banner persistence" detail="How long non-critical alerts stay visible." value={props.settings.alertPersistence} options={["until-dismissed", "15 sec", "60 sec"]} onChange={(value) => props.updateSetting("alertPersistence", value as AlertPersistence)} />
                </SettingsSectionBlock>
                <SettingsSectionBlock title="Permissions" description="Current operator rights for order management and alert response.">
                  <ReadOnlyRow title="Account management" value={props.canManageAccounts ? "Write access" : "Read only"} detail="Controls recovery account CRUD." />
                  <ReadOnlyRow title="Alert management" value={props.canUpdateAlerts ? "Write access" : "Read only"} detail="Controls acknowledge / dismiss / reopen." />
                </SettingsSectionBlock>
              </>
            ) : null}

            {props.settingsSection === "cameras" ? (
              <>
                <SettingsSectionBlock title="Capture profile" description="Set the field capture profile used by the current truck camera stack.">
                  <SettingsSelectRow title="Resolution" detail="Frame capture size for records." value={props.settings.resolution} options={["1920x1080", "1600x900", "1280x720"]} onChange={(value) => props.updateSetting("resolution", value)} />
                  <SettingsSelectRow title="Stream quality" detail="Balance between latency and image quality." value={props.settings.streamQuality} options={["High", "Balanced", "Low latency"]} onChange={(value) => props.updateSetting("streamQuality", value)} />
                  <SettingsToggleRow title="Night mode" detail="Optimize for low-light plate reads." checked={props.settings.nightMode} onChange={(checked) => props.updateSetting("nightMode", checked)} />
                  <SettingsToggleRow title="IR assist" detail="Enable infrared for stationary scans." checked={props.settings.irControl} onChange={(checked) => props.updateSetting("irControl", checked)} />
                  <SettingsToggleRow title="Exposure lock" detail="Hold exposure steady against headlights." checked={props.settings.exposureLock} onChange={(checked) => props.updateSetting("exposureLock", checked)} />
                </SettingsSectionBlock>
                <SettingsSectionBlock title="Feed status" description="Current backend-reported camera availability for this workspace.">
                  <ReadOnlyRow title="Active feeds" value={liveFeedLabel} detail="Online camera count." />
                </SettingsSectionBlock>
              </>
            ) : null}

            {props.settingsSection === "map" ? (
              <>
                <SettingsSectionBlock title="Arrival behavior" description="Control what happens when the vehicle reaches a destination or target radius.">
                  <SettingsToggleRow title="Auto-scan on arrival" detail="Automatically begin scanning when the unit enters the destination radius." checked={props.settings.autoArrivalScan} onChange={(checked) => props.updateSetting("autoArrivalScan", checked)} />
                  <SettingsRangeRow title="Arrival auto-scan radius" detail={`${props.settings.arrivalRadiusFeet} ft`} min={25} max={500} step={25} value={props.settings.arrivalRadiusFeet} onChange={(value) => props.updateSetting("arrivalRadiusFeet", value)} />
                  <SettingsSelectRow title="Navigation" detail="Route to target method." value={props.settings.navProvider} options={["Internal", "External"]} onChange={(value) => props.updateSetting("navProvider", value)} />
                </SettingsSectionBlock>
                <SettingsSectionBlock title="Map overlays" description="Tune the visual context shown during recovery routing and map review.">
                  <SettingsSelectRow title="Map style" detail="Route map visualization." value={props.settings.mapMode} options={["Dark route", "Street", "Satellite-style"]} onChange={(value) => props.updateSetting("mapMode", value)} />
                  <SettingsToggleRow title="Auto-center" detail="Keep map centered on the unit." checked={props.settings.autoCenterVehicle} onChange={(checked) => props.updateSetting("autoCenterVehicle", checked)} />
                  <SettingsToggleRow title="Geofence ring" detail="Show arrival radius on map." checked={props.settings.showRadiusRing} onChange={(checked) => props.updateSetting("showRadiusRing", checked)} />
                  <SettingsToggleRow title="Active alert pins" detail="Show active recovery alerts while navigating or browsing the map." checked={props.settings.showActiveAlertPins} onChange={(checked) => props.updateSetting("showActiveAlertPins", checked)} />
                  <SettingsToggleRow title="Prior alert pins" detail="Show previous acknowledged or dismissed alerts on the map." checked={props.settings.showHistoricalAlertPins} onChange={(checked) => props.updateSetting("showHistoricalAlertPins", checked)} />
                  <SettingsToggleRow title="Live read pins" detail="Show recent detections as map markers." checked={props.settings.showDetectionPins} onChange={(checked) => props.updateSetting("showDetectionPins", checked)} />
                  <SettingsToggleRow title="Traffic overlay" detail="Show route congestion data." checked={props.settings.showTraffic} onChange={(checked) => props.updateSetting("showTraffic", checked)} />
                </SettingsSectionBlock>
              </>
            ) : null}

            {props.settingsSection === "system" ? (
              <>
                <SettingsSectionBlock
                  title="Runtime health"
                  description="Current truck node, capture pipeline, and service-level health reported by the backend."
                  badge={<Badge tone={serviceHealthTone(props.serviceHealthState)}>{serviceHealthLabel(props.serviceHealthState)}</Badge>}
                >
                  <ReadOnlyRow title="Health" value={serviceHealthLabel(props.serviceHealthState)} detail={props.degradedDependencyCount === 0 ? "All systems normal." : `${props.degradedDependencyCount} warning${props.degradedDependencyCount === 1 ? "" : "s"}.`} />
                  <ReadOnlyRow title="Data source" value={props.dataSource.toUpperCase()} detail={props.dataError ?? "Connected to live API."} />
                  <ReadOnlyRow title="Sync" value={props.dataSource === "live" ? "Online" : "Offline queue"} detail={`${props.activeSessions} active session${props.activeSessions === 1 ? "" : "s"}.`} />
                  <ReadOnlyRow
                    title="Edge node"
                    value={props.edgeRuntime?.edge_node_id ?? "Pending"}
                    detail={props.edgeRuntime?.message ?? "Waiting for Jetson runtime status."}
                  />
                  <ReadOnlyRow
                    title="Edge capture"
                    value={edgeCaptureLabel(props.edgeRuntime?.capture_state)}
                    detail={
                      props.edgeRuntimeError ??
                      `Desired ${edgeCaptureLabel(props.edgeRuntime?.desired_capture_state)} - heartbeat ${edgeHeartbeatLabel(props.edgeRuntime)}.`
                    }
                  />
                  <ReadOnlyRow
                    title="Edge cameras"
                    value={`${props.edgeRuntime?.active_camera_count ?? 0}/${Math.max(props.edgeRuntime?.total_camera_count ?? 0, 1)}`}
                    detail={`OCR ${props.edgeRuntime?.plate_ocr_provider ?? "pending"} - Attributes ${props.edgeRuntime?.vehicle_attribute_provider ?? "pending"}.`}
                  />
                  <ReadOnlyRow
                    title="Edge runtime"
                    value={props.edgeRuntime?.inference_runtime ?? "Pending hardware"}
                    detail={
                      props.edgeRuntime?.last_command
                        ? `${titleCase(props.edgeRuntime.last_command)} by ${props.edgeRuntime.last_commanded_by ?? "operator"}`
                        : "No command queued."
                    }
                  />
                </SettingsSectionBlock>

                <SettingsSectionBlock
                  title="Edge controls"
                  description="Start, stop, or restart the truck capture pipeline when hardware control is permitted."
                  badge={<Badge tone={canControlEdgeRuntime ? "success" : "muted"}>{canControlEdgeRuntime ? "Control enabled" : "Restricted"}</Badge>}
                >
                  <div className="button-row">
                    <Tooltip text={canControlEdgeRuntime ? "Request truck camera capture start" : "Edge control requires operator API access"}>
                      <button
                        className="btn btn--success"
                        disabled={!canControlEdgeRuntime || edgeCommandPending}
                        type="button"
                        onClick={() => props.onEdgeRuntimeCommand("start_capture")}
                      >
                        {props.edgeRuntimeAction === "start_capture" ? "Starting..." : "Start Capture"}
                      </button>
                    </Tooltip>
                    <Tooltip text={canControlEdgeRuntime ? "Request truck camera capture stop" : "Edge control requires operator API access"}>
                      <button
                        className="btn btn--danger"
                        disabled={!canControlEdgeRuntime || edgeCommandPending}
                        type="button"
                        onClick={() => props.onEdgeRuntimeCommand("stop_capture")}
                      >
                        {props.edgeRuntimeAction === "stop_capture" ? "Stopping..." : "Stop Capture"}
                      </button>
                    </Tooltip>
                    <Tooltip text={canControlEdgeRuntime ? "Request capture service restart" : "Edge control requires operator API access"}>
                      <button
                        className="btn btn--ghost"
                        disabled={!canControlEdgeRuntime || edgeCommandPending}
                        type="button"
                        onClick={() => props.onEdgeRuntimeCommand("restart_capture")}
                      >
                        {props.edgeRuntimeAction === "restart_capture" ? "Restarting..." : "Restart"}
                      </button>
                    </Tooltip>
                  </div>
                  <SettingsToggleRow title="Auto-delete captures" detail="Clean up temp files after sync." checked={props.settings.autoDeleteTempCaptures} onChange={(checked) => props.updateSetting("autoDeleteTempCaptures", checked)} />
                </SettingsSectionBlock>

                <SettingsSectionBlock
                  title="Operator access"
                  description="Current operator identity plus the control surfaces that are writable from this workspace."
                  badge={<Badge tone={props.currentPrincipal?.authenticated ? "success" : "muted"}>{props.currentPrincipal?.authenticated ? "Authenticated" : "Local mode"}</Badge>}
                >
                  <ReadOnlyRow
                    title="Operator"
                    value={operatorLabel}
                    detail={
                      props.currentPrincipal
                        ? `${props.currentPrincipal.authenticated ? "Auth" : "Unauth"} - ${props.currentPrincipal.roles.map((role) => titleCase(role)).join(", ")}`
                        : "Local mode."
                    }
                  />
                  <ReadOnlyRow title="Recovery records" value={props.canManageAccounts ? "Write" : "Read only"} detail="Repo order and account management." />
                  <ReadOnlyRow title="Follow-ups" value={props.canManageFollowUps ? "Write" : "Read only"} detail="Follow-up case management." />
                  <ReadOnlyRow title="Audit access" value={props.canViewAudit ? "Visible" : "Restricted"} detail="Operator and system audit history access." />
                </SettingsSectionBlock>

                <SettingsSectionBlock title="Connection and export" description="API credentials, live refresh, and export path controls for the current workspace.">
                  <ReadOnlyRow title="Export path" value="runtime/exports" detail="Record export directory." />
                  <label className="settings-input-row">
                    <span>API key</span>
                    <input className="text-input" type="password" value={props.apiKeyInput} onChange={(event) => props.onApiKeyChange(event.target.value)} />
                  </label>
                  <div className="button-row">
                    <Tooltip text="Save and activate the API key">
                      <button className="btn btn--primary" type="button" onClick={props.onApiKeyApply}>
                        Apply Key
                      </button>
                    </Tooltip>
                    <Tooltip text="Re-fetch all data from the backend">
                      <button className="btn btn--ghost" type="button" onClick={props.onRefresh}>
                        Refresh Live Data
                      </button>
                    </Tooltip>
                  </div>
                </SettingsSectionBlock>

                <section className="settings-subsection">
                  <div className="settings-subsection__header">
                    <div className="settings-subsection__copy">
                      <h4>Active sessions</h4>
                      <p>Operators and consoles currently connected to the workspace.</p>
                    </div>
                    <Badge tone={props.activeSessions > 0 ? "success" : "muted"}>{`${props.activeSessions} live`}</Badge>
                  </div>
                  <div className="settings-session-list">
                    {props.activeSessionRecords.length === 0 ? (
                      <StateView
                        size="compact"
                        title="No active sessions"
                        description="Operator sessions signed in to this workspace will show up here."
                      />
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
                  <div className="settings-subsection__header">
                    <div className="settings-subsection__copy">
                      <h4>Audit log</h4>
                      <p>Recent operator and system mutations captured by the backend.</p>
                    </div>
                    <Badge tone={props.canViewAudit ? "success" : "muted"}>{props.canViewAudit ? "Visible" : "Restricted"}</Badge>
                  </div>
                  <div className="settings-session-list">
                    {!props.canViewAudit ? (
                      <StateView
                        variant="restricted"
                        size="compact"
                        title="Audit access restricted"
                        description="Your role cannot read the audit log. Ask an admin to grant audit visibility."
                      />
                    ) : props.auditError ? (
                      <StateView
                        variant="error"
                        size="compact"
                        title="Audit log unavailable"
                        description={props.auditError}
                      />
                    ) : props.auditLoading ? (
                      <StateView
                        variant="loading"
                        size="compact"
                        title="Loading audit log"
                        description="Fetching recent operator actions."
                      />
                    ) : props.auditEvents.length === 0 ? (
                      <StateView
                        size="compact"
                        title="No audit events"
                        description="Operator and system actions will appear here once captured."
                      />
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
  const readCount = Math.max(props.detailTimeline.length, 1);
  const activeFollowUp = props.followUps[0] ?? null;
  const plateCropUrl = useDetectionPlateCropImage(props.detailRow.detectionId, props.dataSource === "live");
  const [reviewAction, setReviewAction] = useState<ReviewAction>("confirm");
  const [reviewCorrectedPlate, setReviewCorrectedPlate] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const responseCue = buildLeadResponseCue(props.detailRow, activeFollowUp, null, props.hotlistEntry?.label ?? null);
  const detailTimelineRows = props.detailTimeline.length > 0 ? props.detailTimeline : [props.detailRow];
  const detailTimelineMarkers = buildSearchTimelineMarkers(detailTimelineRows);
  const verificationChecklist = buildVerificationChecklist({
    accountLabel: props.hotlistEntry?.label,
    confidence: props.detailRow.conf,
    gps: props.detailRow.gps,
    hasFrame: Boolean(props.detailImageUrl),
    hasPlateCrop: Boolean(plateCropUrl),
    notes: props.hotlistEntry?.notes ?? props.detailRow.alertNotes,
    plateText: props.detailRow.plate1,
    vehicleLabel: props.detailRow.vehicle,
  });

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
          <DetectionEvidenceHero
            frameLabel="Vehicle overview"
            framePlaceholder={props.detailRow.vehicle}
            frameUrl={props.detailImageUrl}
            plateCropLabel="Plate crop"
            platePlaceholder={props.detailRow.plate1}
            plateCropUrl={plateCropUrl}
            plateText={props.detailRow.plate1}
          />

          <section className="detail-section detail-section--verification">
            <div className="detail-section__copy">
              <h4>Verification Gate</h4>
            </div>
            <VerificationChecklist items={verificationChecklist} />
          </section>

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
              <span>Reads</span>
              <strong>{readCount}</strong>
            </div>
            <div className="detail-summary-card">
              <span>Follow-up</span>
              <strong>{activeFollowUp ? titleCase(activeFollowUp.status) : "None"}</strong>
            </div>
            <div className="detail-summary-card">
              <span>Recovery match</span>
              <strong>{props.detailRow.alertMatchType ? `${titleCase(props.detailRow.alertMatchType)} match` : "No recovery match"}</strong>
            </div>
          </div>

          <section className="detail-section">
            <div className={`lead-status-banner lead-status-banner--${responseCue.tone} detail-workflow-banner`}>
              <div className="lead-status-banner__copy">
                <span className="eyebrow">Next action</span>
                <strong>{responseCue.label}</strong>
                <p>{responseCue.detail}</p>
              </div>
              <div className="lead-status-banner__signals">
                {activeFollowUp ? <FollowUpStatusPill status={activeFollowUp.status} /> : null}
                {props.hotlistEntry?.label ? <Badge tone="warn">{props.hotlistEntry.label}</Badge> : null}
              </div>
            </div>
          </section>

          <div className="detail-grid">
            <DetailField label="Plate" value={props.detailRow.plate1} tone={props.detailRow.hotlist ? "critical" : "cyan"} />
            <DetailField label="Vehicle" value={props.detailRow.vehicle} />
            <DetailField label="Confidence" value={confidenceLabel(props.detailRow.conf)} />
            <DetailField label="Camera" value={props.detailRow.source} />
            <DetailField label="GPS" value={props.detailRow.gps} />
            <DetailField label="Direction" value={`${props.detailRow.direction} / ${props.detailRow.lane}`} />
            <DetailField label="Recovery address" value={props.activeDestination} />
            <DetailField label="Time" value={formatDateTime(props.detailRow.timestampUtc)} />
            <DetailField label="Sync" value={props.detailRow.syncStatus ?? "local"} />
            <DetailField label="Recovery status" value={props.detailRow.alertStatus ? alertStatusLabel(props.detailRow.alertStatus) : "None"} />
            <DetailField label="Alt read" value={props.detailRow.plate2 || "--"} />
          </div>

          <section className="detail-section">
            <div className="detail-section__header">
              <div className="detail-section__copy">
                <h4>Case context</h4>
              </div>
            </div>
            <div className="detail-note-callout">
              <strong>{props.hotlistEntry?.label ?? "Unassigned vehicle"}</strong>
              <p>
                {props.hotlistEntry?.notes
                  ? props.hotlistEntry.notes
                  : `No recovery account for ${props.detailRow.plate1}. Add this plate to an account to begin tracking.`}
              </p>
            </div>
            {activeFollowUp ? (
              <div className="detail-note-callout">
                <strong>{followUpStatusLabel(activeFollowUp.status)}</strong>
                <p>
                  {activeFollowUp.summary ?? activeFollowUp.notes ?? "Follow-up record attached to this vehicle."}
                  {activeFollowUp.due_at_utc ? ` Due ${formatDateTime(activeFollowUp.due_at_utc)}.` : ""}
                </p>
              </div>
            ) : null}
          </section>

          <section className="detail-section">
            <div className="detail-section__header">
              <div className="detail-section__copy">
                <h4>Sighting pattern</h4>
                <p>Use cadence first, then exact timestamps if you need the full trail.</p>
              </div>
            </div>
            <SearchTimeline markers={detailTimelineMarkers} onSelectRow={() => undefined} selectedRowId={props.detailRow.id} />
            <div className="timeline-list">
              {detailTimelineRows.length > 0 ? (
                detailTimelineRows.map((row) => (
                  <div key={row.id} className="timeline-row">
                    <strong>{formatDateTime(row.timestampUtc)}</strong>
                    <span>{row.source}</span>
                    <span>{row.gps}</span>
                  </div>
                ))
              ) : (
                <p>No repeat reads were grouped for this plate.</p>
              )}
            </div>
          </section>

          {props.detailReviewsLoading || props.detailReviews.length > 0 || props.detailReviewsError ? (
            <CollapsibleSection
              className="detail-section detail-section--collapsible"
              defaultOpen={Boolean(props.detailReviewsError)}
              summary={
                props.detailReviewsLoading
                  ? "Loading review trail"
                  : props.detailReviews.length > 0
                    ? `${props.detailReviews.length} review entr${props.detailReviews.length === 1 ? "y" : "ies"}`
                    : "No prior review actions"
              }
              title="Review history"
            >
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
            </CollapsibleSection>
          ) : null}

          {props.detailRow.detectionId ? (
            <CollapsibleSection
              className="detail-section detail-section--collapsible"
              summary={props.canSubmitReview ? "Writable workflow" : "Read only"}
              title="OCR review"
            >
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
            </CollapsibleSection>
          ) : null}

        </div>

        <div className="detail-overlay__actions">
          <Tooltip text="Route to this vehicle's last-seen point">
            <button className="btn btn--primary" type="button" onClick={props.onOpenMap}>
              Route to Last Seen
            </button>
          </Tooltip>
          <Tooltip text={props.hotlistEntry ? "Open existing recovery account" : "Create a new recovery account for this plate"}>
            <button className="btn btn--ghost" type="button" onClick={props.onAddToHotlist}>
              {props.hotlistEntry ? "Open Account" : "Create Account"}
            </button>
          </Tooltip>
          <Tooltip text="Copy plate number to clipboard">
            <button className="btn btn--ghost" type="button" onClick={() => void props.onCopyPlate(props.detailRow.plate1)}>
              Copy Tag
            </button>
          </Tooltip>
        </div>
      </aside>
    </div>
  );
}

function HotlistAlertOverlay(props: {
  activeDestination: string;
  canSubmitReview: boolean;
  dataSource: DataSource;
  followUp: FollowUpRecord | null;
  hotlistAudioMuted: boolean;
  hotlistEntry: DashboardHotlist | null;
  hotlistRow: ConsoleDetectionRow;
  onConfirmMatch: () => void;
  onDismiss: () => void;
  onFlagFalsePositive: () => void;
  onMuteToggle: () => void;
  onNavigate: () => void;
  onRecover: () => void;
  onViewRecord: () => void;
  reviewError: string | null;
  reviewMessage: string | null;
  reviewSaving: boolean;
}): ReactElement {
  const frameUrl = useDetectionFrameImage(props.hotlistRow.detectionId, props.dataSource === "live");
  const plateCropUrl = useDetectionPlateCropImage(props.hotlistRow.detectionId, props.dataSource === "live");
  const responseCue = buildLeadResponseCue(props.hotlistRow, props.followUp, null, props.hotlistEntry?.label ?? null);
  const verificationChecklist = buildVerificationChecklist({
    accountLabel: props.hotlistEntry?.label,
    confidence: props.hotlistRow.conf,
    gps: props.hotlistRow.gps,
    hasFrame: Boolean(frameUrl),
    hasPlateCrop: Boolean(plateCropUrl),
    notes: props.hotlistEntry?.notes ?? props.hotlistRow.alertNotes,
    plateText: props.hotlistRow.plate1,
    vehicleLabel: props.hotlistRow.vehicle,
  });

  useEffect(() => {
    function handleKey(event: KeyboardEvent): void {
      if (isTypingTarget(event.target)) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "escape") {
        event.preventDefault();
        props.onDismiss();
        return;
      }
      if (key === "r") {
        event.preventDefault();
        props.onNavigate();
        return;
      }
      if (key === "c") {
        event.preventDefault();
        if (!props.reviewSaving && props.canSubmitReview && props.hotlistRow.detectionId) {
          props.onConfirmMatch();
        }
        return;
      }
      if (key === "f") {
        event.preventDefault();
        if (!props.reviewSaving && props.canSubmitReview && props.hotlistRow.detectionId) {
          props.onFlagFalsePositive();
        }
        return;
      }
      if (key === "m") {
        event.preventDefault();
        props.onMuteToggle();
        return;
      }
      if (key === "v") {
        event.preventDefault();
        props.onViewRecord();
        return;
      }
      if (key === "x") {
        event.preventDefault();
        props.onRecover();
      }
    }

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [props]);

  return (
    <>
      <div className="hotlist-alert__scrim" onClick={props.onDismiss} />
      <div className="hotlist-alert">
      <div className="hotlist-alert__header">
        <div>
          <p className="eyebrow">Recovery Alert</p>
          <h2>Recovery Match Located</h2>
        </div>
        <div className="hotlist-alert__header-right">
          <Badge tone="critical">{props.hotlistAudioMuted ? "Muted" : "Audio + visual"}</Badge>
          <button className="hotlist-alert__close" type="button" aria-label="Dismiss alert" onClick={props.onDismiss}>✕</button>
        </div>
      </div>

      <div className="hotlist-alert__hero">
        <DetectionEvidenceHero
          frameLabel="Color overview"
          framePlaceholder={props.hotlistRow.vehicle}
          frameUrl={frameUrl}
          plateCropLabel="OCR crop"
          platePlaceholder={props.hotlistRow.plate1}
          plateCropUrl={plateCropUrl}
          plateText={props.hotlistRow.plate1}
          tone="critical"
        />
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

      <div className="hotlist-alert__verification">
        <div>
          <strong>Verification gate</strong>
          <span>Clear the read, vehicle, account, and location before closing the hit.</span>
        </div>
        <VerificationChecklist compact items={verificationChecklist} />
      </div>

      <section className={`lead-status-banner lead-status-banner--${responseCue.tone} hotlist-alert__banner`}>
        <div className="lead-status-banner__copy">
          <span className="eyebrow">Field directive</span>
          <strong>{responseCue.label}</strong>
          <p>{responseCue.detail}</p>
        </div>
        <div className="lead-status-banner__signals">
          {props.followUp ? <FollowUpStatusPill status={props.followUp.status} /> : null}
          {props.hotlistEntry?.label ? <Badge tone="warn">{props.hotlistEntry.label}</Badge> : null}
        </div>
      </section>

      {props.followUp ? (
        <div className="hotlist-alert__workflow">
          {props.followUp ? <FollowUpStatusPill status={props.followUp.status} /> : null}
        </div>
      ) : null}

      <div className="hotlist-alert__grid">
        <DetailField label="Last seen" value={formatDateTime(props.hotlistRow.timestampUtc)} />
        <DetailField label="Camera" value={props.hotlistRow.source} />
        <DetailField label="GPS" value={props.hotlistRow.gps} />
        <DetailField label="Recovery address" value={props.activeDestination} />
      </div>

      <div className="hotlist-alert__review-strip">
        <div className="hotlist-alert__review-copy">
          <strong>Hit verification</strong>
          <span>Write the response into the existing review workflow before clearing the alert.</span>
        </div>
        <div className="hotlist-alert__review-actions">
          <Tooltip text="Confirm this is a valid match and log the review">
            <button
              className="btn btn--success"
              disabled={!props.canSubmitReview || props.reviewSaving || !props.hotlistRow.detectionId}
              type="button"
              onClick={props.onConfirmMatch}
            >
              {props.reviewSaving ? "Saving..." : "Confirm Match"}
            </button>
          </Tooltip>
          <Tooltip text="Flag this hit as a false positive">
            <button
              className="btn btn--danger"
              disabled={!props.canSubmitReview || props.reviewSaving || !props.hotlistRow.detectionId}
              type="button"
              onClick={props.onFlagFalsePositive}
            >
              False Positive
            </button>
          </Tooltip>
        </div>
      </div>
      {props.reviewError ? <div className="feedback feedback--error">{props.reviewError}</div> : null}
      {props.reviewMessage ? <div className="feedback feedback--good">{props.reviewMessage}</div> : null}

      <div className="hotlist-alert__shortcuts" aria-label="Recovery alert keyboard shortcuts">
        <span><kbd>R</kbd> Route</span>
        <span><kbd>C</kbd> Confirm</span>
        <span><kbd>F</kbd> False positive</span>
        <span><kbd>M</kbd> Mute</span>
        <span><kbd>Esc</kbd> Dismiss</span>
      </div>

      <div className="hotlist-alert__actions">
        <div className="hotlist-alert__actions-primary">
          <Tooltip text="Route to this vehicle's last-seen point">
            <button className="btn btn--primary" type="button" onClick={props.onNavigate}>
              Route to Last Seen
            </button>
          </Tooltip>
          <Tooltip text="View full detection record and evidence">
            <button className="btn btn--ghost" type="button" onClick={props.onViewRecord}>
              Open Record
            </button>
          </Tooltip>
        </div>
        <div className="hotlist-alert__actions-secondary">
          <Tooltip text="Mark this vehicle as recovered and close the case">
            <button className="btn btn--success" type="button" onClick={props.onRecover}>
              Mark Recovered
            </button>
          </Tooltip>
          <Tooltip text={props.hotlistAudioMuted ? "Re-enable alert audio" : "Silence alert audio"}>
            <button className="btn btn--ghost" type="button" onClick={props.onMuteToggle}>
              {props.hotlistAudioMuted ? "Unmute" : "Mute"}
            </button>
          </Tooltip>
          <Tooltip text="Dismiss this alert without action">
            <button className="btn btn--danger" type="button" onClick={props.onDismiss}>
              Dismiss
            </button>
          </Tooltip>
        </div>
      </div>
    </div>
    </>
  );
}

export default App;
