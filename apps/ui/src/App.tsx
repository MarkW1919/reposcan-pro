import { startTransition, useEffect, useMemo, useState, type CSSProperties, type FormEvent, type ReactElement } from "react";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { cameraFeeds, defaultFieldSettings } from "./demo-data";
import {
  createHotlist,
  deleteHotlist,
  fetchDashboardOverview,
  fetchDetectionFrameObjectUrl,
  fetchHotlists,
  searchDetections,
  setApiClientConfig,
  updateHotlist,
  type DashboardDetection,
  type DashboardHotlist,
  type DashboardOverviewResponse,
  type DetectionSearchFilters,
} from "./live-api";

type AppScreen = "console" | "search" | "hotlists" | "settings";
type StageView = "camera" | "map";
type ConsoleLayoutMode = "overview" | "focus";
type SearchMode = "plate" | "camera" | "vehicle" | "time";
type DataSource = "demo" | "live" | "fallback";
type AlertPersistence = "until-dismissed" | "15 sec" | "60 sec";

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
  plate1: string;
  plate2: string;
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
}

interface HotlistDraft {
  plateText: string;
  label: string;
  notes: string;
  active: boolean;
}

interface PlateGroup {
  plate: string;
  rows: ConsoleDetectionRow[];
}

const uiSettingsStorageKey = "reposcan.ui.desktop-settings.v1";
const apiKeyStorageKey = "reposcan.ui.api-key.v2";
const targetAddressStorageKey = "reposcan.ui.target-address.v1";

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

function hotlistLabelForRow(row: ConsoleDetectionRow, hotlists: DashboardHotlist[]): string | null {
  const candidates = new Set([normalizePlate(row.plate1), normalizePlate(row.plate2)]);
  const match = hotlists.find((entry) => entry.active && candidates.has(normalizePlate(entry.plate_text)));
  return match?.label ?? null;
}

function buildCameraShortLabel(cameraId: string): string {
  const index = cameraFeeds.findIndex((feed) => feed.id === cameraId);
  if (index >= 0) {
    return `Cam ${index + 1}`;
  }
  return cameraId.replace(/^cam_/i, "").replace(/_/g, " ").replace(/\b\w/g, (value) => value.toUpperCase());
}

function buildCameraDisplayName(cameraId: string): string {
  const camera = cameraFeeds.find((feed) => feed.id === cameraId);
  return camera?.label ?? buildCameraShortLabel(cameraId);
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
  const parts = [titleCase(record.vehicle_color), titleCase(record.vehicle_make), titleCase(record.vehicle_model)].filter(Boolean);
  return parts.join(" ") || "Unclassified vehicle";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
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
    },
  ];

  return seeds.map((row) => ({
    ...row,
    camera: buildCameraShortLabel(row.cameraId),
    time: formatClock(row.timestampUtc),
    hotlist: matchesHotlist(row.plate1, row.plate2, hotlists),
  }));
}

function mapDetectionToRow(record: DashboardDetection, index: number, hotlists: DashboardHotlist[]): ConsoleDetectionRow {
  const primaryPlate = record.plate_text ?? record.plate_candidates[0]?.text ?? `UNREAD-${index + 1}`;
  const alternatePlate = record.plate_candidates.find((candidate) => candidate.text !== primaryPlate)?.text ?? (primaryPlate.slice(1) || "--");
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
  return row.timestampUtc.includes(normalizedQuery) || row.time.includes(normalizedQuery);
}

function filterRowsLocally(options: {
  rows: ConsoleDetectionRow[];
  mode: SearchMode;
  query: string;
  fromUtc?: string;
  toUtc?: string;
  hotlistOnly: boolean;
  highConfidenceOnly: boolean;
  currentCameraOnly: boolean;
  currentShiftOnly: boolean;
  currentCameraId: string;
}): ConsoleDetectionRow[] {
  const shiftCutoff = new Date("2026-03-27T14:00:00Z").valueOf();
  const fromValue = options.fromUtc ? new Date(options.fromUtc).valueOf() : null;
  const toValue = options.toUtc ? new Date(options.toUtc).valueOf() : null;

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
    if (options.currentCameraOnly && row.cameraId !== options.currentCameraId) {
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

function CameraViewport(props: {
  cameraId: string;
  camera: (typeof cameraFeeds)[number] | undefined;
  row: ConsoleDetectionRow | null;
  settings: UiSettings;
  compact?: boolean;
}): ReactElement {
  return (
    <div className={`camera-stage ${props.compact ? "camera-stage--compact" : ""}`}>
      <div className="camera-stage__meta">
        <strong>{buildCameraDisplayName(props.cameraId)}</strong>
        <span>{props.camera?.fps ?? 0} FPS</span>
        <span>{props.settings.resolution}</span>
      </div>
      <div className={`camera-feed ${props.compact ? "camera-feed--compact" : ""}`}>
        <div className="camera-feed__grid" />
        <div className="camera-feed__lane camera-feed__lane--left" />
        <div className="camera-feed__lane camera-feed__lane--right" />
        <div className="camera-wireframe">
          <div className="camera-wireframe__roof" />
          <div className="camera-wireframe__body" />
          <div className="camera-wireframe__hood" />
        </div>
        {props.row ? (
          <div
            className={`detection-box detection-box--${confidenceTone(props.row.conf)} ${props.compact ? "detection-box--compact" : ""}`}
            style={buildDetectionBoxPosition(props.row.cameraId, Boolean(props.compact))}
          >
            <div className="detection-box__plate">
              {props.row.plate1} {confidenceLabel(props.row.conf)}
            </div>
            {props.settings.overlayLabels ? (
              <div className="detection-box__meta">
                <span>{props.row.vehicle}</span>
                <span>{props.row.direction}</span>
              </div>
            ) : null}
          </div>
        ) : null}
        <div className={`camera-feed__hud ${props.compact ? "camera-feed__hud--compact" : ""}`}>
          <div>
            <span>Frame</span>
            <strong>021844</strong>
          </div>
          <div>
            <span>Lane</span>
            <strong>{props.row?.lane ?? "Standby"}</strong>
          </div>
          <div>
            <span>Direction</span>
            <strong>{props.row?.direction ?? "Standby"}</strong>
          </div>
        </div>
      </div>
    </div>
  );
}

function ScreenHeader(props: { title: string; subtitle: string; meta?: ReactElement; actions?: ReactElement }): ReactElement {
  return (
    <header className="screen-header">
      <div>
        <p className="eyebrow">RepoScan Ops</p>
        <h1>{props.title}</h1>
        <p className="screen-subtitle">{props.subtitle}</p>
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
  const [selectedCameraId, setSelectedCameraId] = useState<string>(cameraFeeds[2]?.id ?? cameraFeeds[0]?.id ?? "");
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
  const [refreshToken, setRefreshToken] = useState(0);
  const [searchMode, setSearchMode] = useState<SearchMode>("plate");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFromLocal, setSearchFromLocal] = useState("");
  const [searchToLocal, setSearchToLocal] = useState("");
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
  const [hotlistOverlayId, setHotlistOverlayId] = useState<string | null>(null);
  const [hotlistAudioMuted, setHotlistAudioMuted] = useState(false);

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

  const allRows = useMemo(
    () =>
      (overview?.detections.length
        ? overview.detections.map((record, index) => mapDetectionToRow(record, index, hotlists))
        : buildSeedRows(hotlists)
      ).sort((left, right) => right.timestampUtc.localeCompare(left.timestampUtc)),
    [overview?.detections, hotlists],
  );

  useEffect(() => {
    const currentRowStillExists = selectedDetectionId ? allRows.some((row) => row.id === selectedDetectionId) : false;
    if (!currentRowStillExists && allRows[0]) {
      setSelectedDetectionId(allRows[0].id);
    }
  }, [allRows, selectedDetectionId]);

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

  const selectedRow = allRows.find((row) => row.id === selectedDetectionId) ?? allRows[0] ?? null;
  const detailRow = [...allRows, ...searchResults].find((row) => row.id === detailDetectionId) ?? null;
  const hotlistOverlayRow = allRows.find((row) => row.id === hotlistOverlayId) ?? null;
  const currentCamera = cameraFeeds.find((feed) => feed.id === selectedCameraId) ?? cameraFeeds[0];
  const secondaryCamera =
    cameraFeeds.find((feed) => feed.id !== selectedCameraId && feed.status === "Online") ??
    cameraFeeds.find((feed) => feed.id !== selectedCameraId) ??
    currentCamera;
  const cameraRows = allRows.filter((row) => row.cameraId === selectedCameraId);
  const secondaryCameraRows = allRows.filter((row) => row.cameraId === secondaryCamera?.id);
  const cameraFocusRow = cameraRows[0] ?? selectedRow;
  const secondaryCameraFocusRow = secondaryCameraRows[0] ?? allRows.find((row) => row.cameraId === secondaryCamera?.id) ?? selectedRow;
  const routeProgress = navigationActive ? clamp(1 - distanceFeet / 4800, 0, 1) : 0;
  const unitPosition = interpolatePosition(routeProgress);
  const routePath = buildRoutePath(unitPosition);
  const withinRadius = navigationActive && distanceFeet <= settings.arrivalRadiusFeet;
  const totalReads = overview?.counts.recent_detections ?? 142;
  const activeAlerts = overview?.counts.active_alerts ?? allRows.filter((row) => row.hotlist).length;
  const activeSessions = overview?.counts.active_sessions ?? 3;
  const onlineCameraCount = cameraFeeds.filter((feed) => feed.status === "Online").length;
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

  function openLatestHotlistAlert(): void {
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

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSearchLoading(true);
    setSearchError(null);
    setSearchMessage(null);

    const fromUtc = toUtcIso(searchFromLocal);
    const toUtc = toUtcIso(searchToLocal);

    const localFallback = (): void => {
      const nextRows = filterRowsLocally({
        rows: allRows,
        mode: searchMode,
        query: searchQuery,
        fromUtc,
        toUtc,
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

        if (searchMode === "plate") {
          filters.plate = searchQuery.trim();
          filters.plate_match = "contains";
        } else if (searchMode === "camera") {
          const normalizedCameraQuery = searchQuery.trim().toUpperCase();
          const matchedCamera = cameraFeeds.find(
            (feed) =>
              feed.id.toUpperCase().includes(normalizedCameraQuery) ||
              feed.label.toUpperCase().includes(normalizedCameraQuery) ||
              buildCameraShortLabel(feed.id).toUpperCase().includes(normalizedCameraQuery),
          );
          filters.camera_id = matchedCamera?.id ?? selectedCameraId;
        } else if (searchMode === "vehicle") {
          const [make, ...modelParts] = searchQuery.trim().split(/\s+/).filter(Boolean);
          if (make) {
            filters.vehicle_make = make;
          }
          if (modelParts.length > 0) {
            filters.vehicle_model = modelParts.join(" ");
          }
        }

        const result = await searchDetections(filters);
        const mappedRows = result.results.map((record, index) => mapDetectionToRow(record, index, hotlists));
        const filteredRows = filterRowsLocally({
          rows: mappedRows,
          mode: searchMode,
          query: searchQuery,
          fromUtc,
          toUtc,
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

      setHotlistMessage(action === "recover" ? "Hotlist entry marked inactive." : entry ? "Hotlist entry updated." : "Hotlist entry created.");
    } catch (error) {
      setHotlistError(error instanceof Error ? error.message : "Unable to save the hotlist entry.");
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
      setHotlistMessage("Hotlist entry deleted.");
    } catch (error) {
      setHotlistError(error instanceof Error ? error.message : "Unable to delete the hotlist entry.");
    } finally {
      setHotlistDeleting(false);
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

  const footerIndicators = [
    { label: "GPS locked", value: "ON", tone: "good" },
    { label: "Server", value: dataSource === "live" ? "Connected" : dataSource === "fallback" ? "Fallback" : "Demo", tone: dataSource === "live" ? "good" : "off" },
    { label: "LPR", value: settings.arrivalScanEnabled ? "Active" : "Paused", tone: settings.arrivalScanEnabled ? "good" : "off" },
    { label: "FPS", value: `${currentCamera?.fps ?? 0}`, tone: currentCamera?.status === "Online" ? "good" : "off" },
    { label: "Cams", value: `${onlineCameraCount}/${cameraFeeds.length}`, tone: onlineCameraCount > 0 ? "good" : "off" },
    { label: "Reads", value: `${totalReads}`, tone: "good" },
    { label: "Alerts", value: `${activeAlerts}`, tone: activeAlerts > 0 ? "warn" : "good" },
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
          onOpenSearch={() => switchScreen("search")}
          onResolve={() => {
            setActiveDestination(destinationInput.trim() || targetRoute.address);
            setStageView("map");
          }}
          onScreenChange={switchScreen}
          onToggleNavigation={() => setNavigationActive((current) => !current)}
          routeDistance={routeDistance}
          routeEta={routeEta}
          routeStatusLabel={routeStatusLabel}
          searchCount={searchExecuted ? searchTotal : allRows.length}
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
              cameraFeedsList={cameraFeeds}
              cameraFocusRow={cameraFocusRow}
              currentCamera={currentCamera}
              selectedCameraId={selectedCameraId}
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
              dataSource={dataSource}
              expandedGroups={expandedGroups}
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
              searchMessage={searchMessage}
              searchMode={searchMode}
              searchToLocal={searchToLocal}
              searchCurrentCameraOnly={searchCurrentCameraOnly}
              searchCurrentShiftOnly={searchCurrentShiftOnly}
              onCopyPlate={handleCopyPlate}
              onDetails={openDetail}
              onMap={centerMapOnRow}
              onOpenDashboard={() => switchScreen("console")}
              onOpenHotlists={() => switchScreen("hotlists")}
              onSearchSubmit={handleSearchSubmit}
              onOpenSettings={() => switchScreen("settings")}
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
              setSearchMode={setSearchMode}
              setSearchToLocal={setSearchToLocal}
              setSearchCurrentCameraOnly={setSearchCurrentCameraOnly}
              setSearchCurrentShiftOnly={setSearchCurrentShiftOnly}
            />
          ) : null}

          {screen === "hotlists" ? (
            <HotlistsScreen
              dataSource={dataSource}
              draft={hotlistDraft}
              error={hotlistError}
              hotlists={hotlists}
              message={hotlistMessage}
              saving={hotlistSaving}
              deleting={hotlistDeleting}
              selectedDetectionPlate={selectedRow?.plate1 ?? ""}
              selectedHotlistId={selectedHotlistId}
              onClearDraft={() => beginHotlistDraft()}
              onOpenDashboard={() => switchScreen("console")}
              onDelete={() => void handleDeleteHotlist()}
              onDraftChange={setHotlistDraft}
              onOpenSearch={() => switchScreen("search")}
              onSelect={loadHotlist}
              onSeedFromDetection={() => beginHotlistDraft(selectedRow?.plate1)}
              onOpenSettings={() => switchScreen("settings")}
              onSubmit={handleHotlistSubmit}
            />
          ) : null}

          {screen === "settings" ? (
            <SettingsScreen
              activeSessions={activeSessions}
              apiKeyInput={apiKeyInput}
              dataError={dataError}
              dataSource={dataSource}
              hotlistWarning={hotlistWarning}
              onApiKeyApply={() => setApiKey(apiKeyInput.trim())}
              onApiKeyChange={setApiKeyInput}
              onOpenDashboard={() => switchScreen("console")}
              onOpenHotlists={() => switchScreen("hotlists")}
              onOpenSearch={() => switchScreen("search")}
              onRefresh={() => setRefreshToken((value) => value + 1)}
              settings={settings}
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
          detailImageUrl={detailImageUrl}
          detailRow={detailRow}
          detailTimeline={detailTimeline}
          hotlists={hotlists}
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
        />
      ) : null}

      {hotlistOverlayRow ? (
        <HotlistAlertOverlay
          activeDestination={activeDestination}
          hotlistAudioMuted={hotlistAudioMuted}
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
  row: ConsoleDetectionRow;
  hotlistLabel: string | null;
  onDetails: () => void;
  onMap: () => void;
  onCopy: (plate: string) => Promise<void>;
}): ReactElement {
  return (
    <article className="search-result-card">
      <div className="search-result-card__thumb">
        <span>{props.row.camera}</span>
      </div>
      <div className="search-result-card__body">
        <div className="search-result-card__header">
          <div>
            <strong>{props.row.plate1}</strong>
            <span>{props.row.vehicle}</span>
          </div>
          <div className="search-result-card__badges">
            {props.row.hotlist ? <Badge tone="critical">Hotlist</Badge> : null}
            {props.hotlistLabel ? <Badge tone="warn">{props.hotlistLabel}</Badge> : null}
          </div>
        </div>
        <div className="search-result-card__meta">
          <span>{props.row.source}</span>
          <span>{props.row.gps}</span>
          <span>
            {formatDateTime(props.row.timestampUtc)} | {confidenceLabel(props.row.conf)}
          </span>
        </div>
        <div className="search-result-card__actions">
          <button className="link-button" type="button" onClick={props.onDetails}>
            Details
          </button>
          <button className="link-button" type="button" onClick={props.onMap}>
            Map
          </button>
          <button className="link-button" type="button" onClick={() => void props.onCopy(props.row.plate1)}>
            Copy Plate
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
  onOpenSearch: () => void;
  onResolve: () => void;
  onScreenChange: (screen: AppScreen) => void;
  onToggleNavigation: () => void;
  routeDistance: string;
  routeEta: string;
  routeStatusLabel: string;
  searchCount: number;
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
          <p className="brand-copy">Camera-first recovery console tuned to the field workflow.</p>
        </div>
      </div>

      <div className="nav-tabs">
        {[
          { id: "console", label: "Dashboard", count: props.totalReads },
          { id: "hotlists", label: "Hotlists", count: props.activeHotlists },
          { id: "settings", label: "Settings", count: 0 },
        ].map((item) => (
          <button
            key={item.id}
            className={`nav-tab ${props.activeScreen === item.id ? "is-active" : ""}`}
            type="button"
            onClick={() => props.onScreenChange(item.id as AppScreen)}
          >
            <span className="nav-tab__label">{item.label}</span>
            <span className="nav-tab__count">{item.count > 0 ? item.count : "-"}</span>
          </button>
        ))}
      </div>

      <div className="nav-action-row">
        <button className="nav-action nav-action--ghost" type="button" onClick={props.onOpenSearch}>
          <span>Search</span>
          <span className="nav-action__count">{props.searchCount > 0 ? props.searchCount : "-"}</span>
        </button>
        <button className="nav-action nav-action--primary" disabled={props.activeAlerts === 0} type="button" onClick={props.onOpenAlert}>
          <span>View Alert</span>
          <span className="nav-action__count">{props.activeAlerts}</span>
        </button>
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
  cameraFeedsList: typeof cameraFeeds;
  cameraFocusRow: ConsoleDetectionRow | null;
  consoleLayoutMode: ConsoleLayoutMode;
  currentCamera: (typeof cameraFeeds)[number] | undefined;
  secondaryCamera: (typeof cameraFeeds)[number] | undefined;
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
              {props.cameraFeedsList.map((feed, index) => (
                <button
                  key={feed.id}
                  className={`camera-tab ${props.selectedCameraId === feed.id ? "is-active" : ""}`}
                  type="button"
                  onClick={() => props.onSelectCamera(feed.id)}
                >
                  <span className={`camera-dot camera-dot--${feed.status === "Online" ? "live" : "off"}`} />
                  Cam {index + 1}
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
              <Badge tone={props.currentCamera?.status === "Online" ? "critical" : "muted"}>{props.currentCamera?.status === "Online" ? "LIVE" : "OFFLINE"}</Badge>
            </div>
          </div>

          <div className="stage-surface">
            {props.consoleLayoutMode === "overview" ? (
              <div className="console-overview-grid">
                <article className="console-overview-card console-overview-card--primary">
                  <div className="console-overview-card__header">
                    <div>
                      <p className="eyebrow">Primary Camera</p>
                      <h3>{buildCameraShortLabel(props.selectedCameraId)}</h3>
                    </div>
                    <Badge tone={props.currentCamera?.status === "Online" ? "success" : "muted"}>{props.currentCamera?.status === "Online" ? "LIVE" : "OFFLINE"}</Badge>
                  </div>
                  <CameraViewport camera={props.currentCamera} cameraId={props.selectedCameraId} row={props.cameraFocusRow} settings={props.settings} compact />
                </article>

                <article className="console-overview-card console-overview-card--secondary">
                  <div className="console-overview-card__header">
                    <div>
                      <p className="eyebrow">Support Camera</p>
                      <h3>{buildCameraShortLabel(props.secondaryCamera?.id ?? props.selectedCameraId)}</h3>
                    </div>
                    {props.secondaryCamera?.id !== props.selectedCameraId ? (
                      <button className="link-button" type="button" onClick={() => props.onSelectCamera(props.secondaryCamera?.id ?? props.selectedCameraId)}>
                        Make Primary
                      </button>
                    ) : (
                      <Badge tone="muted">Synced</Badge>
                    )}
                  </div>
                  <CameraViewport
                    camera={props.secondaryCamera}
                    cameraId={props.secondaryCamera?.id ?? props.selectedCameraId}
                    row={props.secondaryCameraFocusRow}
                    settings={props.settings}
                    compact
                  />
                </article>

                <article className="console-overview-card console-overview-card--map">
                  <div className="console-overview-card__header">
                    <div>
                      <p className="eyebrow">Live Map</p>
                      <h3>Route and Radius</h3>
                    </div>
                    <Badge tone={props.withinRadius ? "success" : "cyan"}>{props.withinRadius ? "IN RADIUS" : "EN ROUTE"}</Badge>
                  </div>
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
              <CameraViewport camera={props.currentCamera} cameraId={props.selectedCameraId} row={props.cameraFocusRow} settings={props.settings} />
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
            <div>
              <p className="eyebrow">Live Reads</p>
              <h3>Plate Detection Table</h3>
            </div>
            <div className="table-card__meta">
              <span>{props.allRows.length} visible</span>
              <span>{props.activeAlerts} active alerts</span>
            </div>
          </div>
          <div className="table-scroll">
            <table className="detection-table">
              <thead>
                <tr>
                  <th>Image</th>
                  <th>Plate 1</th>
                  <th>Plate 2</th>
                  <th>State</th>
                  <th>Camera</th>
                  <th>Conf</th>
                  <th>Time</th>
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
                        <span>{row.camera}</span>
                      </button>
                    </td>
                    <td>{row.plate1}</td>
                    <td>{row.plate2}</td>
                    <td>{row.state}</td>
                    <td>{row.camera}</td>
                    <td>{confidenceLabel(row.conf)}</td>
                    <td>{row.time}</td>
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
  dataSource: DataSource;
  expandedGroups: Record<string, boolean>;
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
  searchMessage: string | null;
  searchMode: SearchMode;
  searchToLocal: string;
  searchCurrentCameraOnly: boolean;
  searchCurrentShiftOnly: boolean;
  onCopyPlate: (plate: string) => Promise<void>;
  onDetails: (row: ConsoleDetectionRow) => void;
  onMap: (row: ConsoleDetectionRow) => void;
  onOpenDashboard: () => void;
  onOpenHotlists: () => void;
  onSearchSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onOpenSettings: () => void;
  onToggleExpanded: (plate: string) => void;
  setQuery: (value: string) => void;
  setSearchFromLocal: (value: string) => void;
  setSearchGroupByPlate: (value: boolean) => void;
  setSearchHighConfidenceOnly: (value: boolean) => void;
  setSearchHotlistOnly: (value: boolean) => void;
  setSearchMode: (mode: SearchMode) => void;
  setSearchToLocal: (value: string) => void;
  setSearchCurrentCameraOnly: (value: boolean) => void;
  setSearchCurrentShiftOnly: (value: boolean) => void;
}): ReactElement {
  return (
    <section className="screen">
      <ScreenHeader
        title="Search Results"
        subtitle="Field-ready plate and vehicle history with grouping, quick actions, and map handoff."
        meta={
          <>
            <Badge tone={props.loading ? "warn" : "cyan"}>{props.loading ? "Searching" : "Ready"}</Badge>
            <Badge tone={props.dataSource === "live" ? "success" : "muted"}>{props.dataSource.toUpperCase()}</Badge>
          </>
        }
        actions={
          <>
            <button className="btn btn--ghost btn--compact" type="button" onClick={props.onOpenDashboard}>
              Dashboard
            </button>
            <button className="btn btn--ghost btn--compact" type="button" onClick={props.onOpenHotlists}>
              Hotlists
            </button>
            <button className="btn btn--ghost btn--compact" type="button" onClick={props.onOpenSettings}>
              Settings
            </button>
          </>
        }
      />

      <form className="search-toolbar-card" onSubmit={(event) => void props.onSearchSubmit(event)}>
        <div className="search-mode-tabs">
          {(["plate", "camera", "vehicle", "time"] as const).map((mode) => (
            <button key={mode} className={props.searchMode === mode ? "is-active" : ""} type="button" onClick={() => props.setSearchMode(mode)}>
              {mode}
            </button>
          ))}
        </div>

        <div className="search-input-row">
          <input
            className="text-input text-input--large"
            placeholder={
              props.searchMode === "plate"
                ? "Search full or partial plate"
                : props.searchMode === "camera"
                  ? "Search current or named camera"
                  : props.searchMode === "vehicle"
                    ? "Search make / model / color"
                    : "Optional time keyword"
            }
            type="text"
            value={props.query}
            onChange={(event) => props.setQuery(event.target.value)}
          />
          <button className="btn btn--primary" disabled={props.loading} type="submit">
            {props.loading ? "Searching..." : "Run Search"}
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

        <div className="chip-row">
          <button className={`chip ${props.searchHotlistOnly ? "is-active" : ""}`} type="button" onClick={() => props.setSearchHotlistOnly(!props.searchHotlistOnly)}>
            Hotlist
          </button>
          <button className={`chip ${props.searchCurrentShiftOnly ? "is-active" : ""}`} type="button" onClick={() => props.setSearchCurrentShiftOnly(!props.searchCurrentShiftOnly)}>
            Current shift
          </button>
          <button className={`chip ${props.searchCurrentCameraOnly ? "is-active" : ""}`} type="button" onClick={() => props.setSearchCurrentCameraOnly(!props.searchCurrentCameraOnly)}>
            Current camera
          </button>
          <button className={`chip ${props.searchHighConfidenceOnly ? "is-active" : ""}`} type="button" onClick={() => props.setSearchHighConfidenceOnly(!props.searchHighConfidenceOnly)}>
            High conf
          </button>
          <button className={`chip ${props.searchGroupByPlate ? "is-active" : ""}`} type="button" onClick={() => props.setSearchGroupByPlate(!props.searchGroupByPlate)}>
            Group by plate
          </button>
        </div>
      </form>

      <section className="results-panel">
        <div className="results-panel__header">
          <div>
            <p className="eyebrow">History</p>
            <h3>{props.searchExecuted ? `${props.resultsTotal} result${props.resultsTotal === 1 ? "" : "s"}` : "Recent detections"}</h3>
          </div>
          <div className="results-panel__feedback">
            {props.searchError ? <span className="feedback feedback--warn">{props.searchError}</span> : null}
            {props.searchMessage ? <span className="feedback feedback--good">{props.searchMessage}</span> : null}
          </div>
        </div>

        <div className="search-results">
          {props.results.length === 0 ? (
            <div className="empty-state">
              <strong>No detections matched this search.</strong>
              <p>Try a wider plate fragment, clear the time window, or disable a filter chip.</p>
            </div>
          ) : props.searchGroupByPlate ? (
            props.groupedResults.map((group) => {
              const expanded = props.expandedGroups[group.plate] ?? false;
              const rows = expanded ? group.rows : group.rows.slice(0, 1);
              const lead = group.rows[0];
              return (
                <article key={group.plate} className="result-group-card">
                  <div className="result-group-card__header">
                    <div>
                      <strong>{group.plate}</strong>
                      <span>{group.rows.length === 1 ? lead.vehicle : `Seen ${group.rows.length} times`}</span>
                    </div>
                    <div className="result-group-card__meta">
                      {lead.hotlist ? <Badge tone="critical">Hotlist</Badge> : null}
                      {group.rows.length > 1 ? (
                        <button className="link-button" type="button" onClick={() => props.onToggleExpanded(group.plate)}>
                          {expanded ? "Collapse sightings" : "Expand sightings"}
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <div className="result-group-list">
                    {rows.map((row) => (
                      <SearchResultCard
                        key={row.id}
                        row={row}
                        hotlistLabel={hotlistLabelForRow(row, props.hotlists)}
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
                key={row.id}
                row={row}
                hotlistLabel={hotlistLabelForRow(row, props.hotlists)}
                onCopy={props.onCopyPlate}
                onDetails={() => props.onDetails(row)}
                onMap={() => props.onMap(row)}
              />
            ))
          )}
        </div>
      </section>
    </section>
  );
}

function HotlistsScreen(props: {
  dataSource: DataSource;
  draft: HotlistDraft;
  error: string | null;
  hotlists: DashboardHotlist[];
  message: string | null;
  saving: boolean;
  deleting: boolean;
  selectedDetectionPlate: string;
  selectedHotlistId: string | null;
  onClearDraft: () => void;
  onOpenDashboard: () => void;
  onDelete: () => void;
  onDraftChange: (draft: HotlistDraft | ((current: HotlistDraft) => HotlistDraft)) => void;
  onOpenSearch: () => void;
  onSelect: (entry: DashboardHotlist) => void;
  onSeedFromDetection: () => void;
  onOpenSettings: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}): ReactElement {
  return (
    <section className="screen">
      <ScreenHeader
        title="Hotlist Manager"
        subtitle="Add, edit, pause, recover, and delete local hotlist accounts from one workspace."
        meta={
          <>
            <Badge tone="critical">{`${props.hotlists.filter((entry) => entry.active).length} active`}</Badge>
            <Badge tone={props.dataSource === "live" ? "success" : "muted"}>{props.dataSource.toUpperCase()}</Badge>
          </>
        }
        actions={
          <>
            <button className="btn btn--ghost btn--compact" type="button" onClick={props.onOpenDashboard}>
              Dashboard
            </button>
            <button className="btn btn--ghost btn--compact" type="button" onClick={props.onOpenSearch}>
              Search
            </button>
            <button className="btn btn--ghost btn--compact" type="button" onClick={props.onOpenSettings}>
              Settings
            </button>
          </>
        }
      />

      <div className="hotlists-grid">
        <section className="panel-card hotlists-list-card">
          <div className="panel-card__header">
            <h3>Tracked Plates</h3>
            <button className="btn btn--ghost" type="button" onClick={props.onClearDraft}>
              New Entry
            </button>
          </div>
          <div className="hotlist-list">
            {props.hotlists.length === 0 ? (
              <div className="empty-state">
                <strong>No hotlist entries yet.</strong>
                <p>Create the first one from scratch or seed it from the selected detection.</p>
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
                    <span>{entry.label ?? "Unlabeled entry"}</span>
                  </div>
                  <div className="hotlist-row__meta">
                    <Badge tone={entry.active ? "critical" : "muted"}>{entry.active ? "Active" : "Paused"}</Badge>
                    <span>{formatDateTime(entry.updated_at_utc)}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="panel-card hotlist-editor-card">
          <div className="panel-card__header">
            <h3>{props.selectedHotlistId ? "Edit Entry" : "Create Entry"}</h3>
            <button className="btn btn--ghost" type="button" onClick={props.onSeedFromDetection}>
              Seed From Detection
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
              <span>Label</span>
              <input
                className="text-input"
                placeholder="Case name / tow-ready / visual match"
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
              <span>Notes</span>
              <textarea
                className="text-area"
                placeholder="Tell the operator what to do when this vehicle is detected."
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
                <strong>Entry active</strong>
                <span>Controls whether the plate triggers hotlist interrupts.</span>
              </div>
              <Toggle
                checked={props.draft.active}
                label="Entry active"
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
              <button className="btn btn--primary" disabled={props.saving} type="submit">
                {props.saving ? "Saving..." : props.selectedHotlistId ? "Update Hotlist" : "Create Hotlist"}
              </button>
              <button className="btn btn--ghost" type="button" onClick={props.onClearDraft}>
                Clear Draft
              </button>
              <button className="btn btn--ghost" type="button" onClick={props.onSeedFromDetection}>
                Seed {props.selectedDetectionPlate || "selection"}
              </button>
              <button className="btn btn--danger" disabled={!props.selectedHotlistId || props.deleting} type="button" onClick={props.onDelete}>
                {props.deleting ? "Deleting..." : "Delete Entry"}
              </button>
            </div>
          </form>
        </section>
      </div>
    </section>
  );
}

function SettingsScreen(props: {
  activeSessions: number;
  apiKeyInput: string;
  dataError: string | null;
  dataSource: DataSource;
  hotlistWarning: boolean;
  onApiKeyApply: () => void;
  onApiKeyChange: (value: string) => void;
  onOpenDashboard: () => void;
  onOpenHotlists: () => void;
  onOpenSearch: () => void;
  onRefresh: () => void;
  settings: UiSettings;
  updateSetting: <Key extends keyof UiSettings>(key: Key, value: UiSettings[Key]) => void;
}): ReactElement {
  return (
    <section className="screen">
      <ScreenHeader
        title="Settings Dashboard"
        subtitle="Scanning, alerts, camera tuning, storage, sync, and navigation defaults."
        meta={
          <>
            {props.hotlistWarning ? <Badge tone="warn">Review alert settings</Badge> : <Badge tone="success">Operational</Badge>}
            <Badge tone={props.dataSource === "live" ? "success" : "muted"}>{props.dataSource.toUpperCase()}</Badge>
          </>
        }
        actions={
          <>
            <button className="btn btn--ghost btn--compact" type="button" onClick={props.onOpenDashboard}>
              Dashboard
            </button>
            <button className="btn btn--ghost btn--compact" type="button" onClick={props.onOpenSearch}>
              Search
            </button>
            <button className="btn btn--ghost btn--compact" type="button" onClick={props.onOpenHotlists}>
              Hotlists
            </button>
          </>
        }
      />

      <div className="settings-columns">
        <section className="settings-card">
          <div className="settings-card__header">
            <h3>Scanning</h3>
            <p>Arrival-mode behavior and OCR thresholds.</p>
          </div>
          <SettingsToggleRow title="Auto-enable arrival scan" detail="Switch into local scan mode when entering the target radius." checked={props.settings.autoArrivalScan} onChange={(checked) => props.updateSetting("autoArrivalScan", checked)} />
          <SettingsToggleRow title="Arrival scan feature" detail="Global kill switch for arrival-scoped local detections." checked={props.settings.arrivalScanEnabled} onChange={(checked) => props.updateSetting("arrivalScanEnabled", checked)} />
          <SettingsRangeRow title="Radius size" detail={`${props.settings.arrivalRadiusFeet} ft`} min={100} max={1000} step={25} value={props.settings.arrivalRadiusFeet} onChange={(value) => props.updateSetting("arrivalRadiusFeet", value)} />
          <SettingsRangeRow title="Duplicate suppression" detail={`${props.settings.duplicateSuppressionSeconds} sec`} min={15} max={300} step={15} value={props.settings.duplicateSuppressionSeconds} onChange={(value) => props.updateSetting("duplicateSuppressionSeconds", value)} />
          <SettingsRangeRow title="Minimum confidence" detail={`${props.settings.minConfidence}%`} min={60} max={99} step={1} value={props.settings.minConfidence} onChange={(value) => props.updateSetting("minConfidence", value)} />
        </section>

        <section className="settings-card">
          <div className="settings-card__header">
            <h3>Alerts</h3>
            <p>Hotlist signaling, persistence, and escalation controls.</p>
          </div>
          <SettingsToggleRow title="Hotlist alerts" detail="Show the full-screen interrupt on any matching plate." checked={props.settings.hotlistAlerts} onChange={(checked) => props.updateSetting("hotlistAlerts", checked)} />
          <SettingsToggleRow title="Sound" detail="Enable audible alert cues." checked={props.settings.soundEnabled} onChange={(checked) => props.updateSetting("soundEnabled", checked)} />
          <SettingsToggleRow title="Vibration" detail="Trigger haptics on critical hotlist events." checked={props.settings.vibrationEnabled} onChange={(checked) => props.updateSetting("vibrationEnabled", checked)} />
          <SettingsRangeRow title="Alert volume" detail={`${props.settings.alertVolume}%`} min={0} max={100} step={5} value={props.settings.alertVolume} onChange={(value) => props.updateSetting("alertVolume", value)} />
          <SettingsSelectRow title="Alert persistence" detail="How long non-critical banners remain visible." value={props.settings.alertPersistence} options={["until-dismissed", "15 sec", "60 sec"]} onChange={(value) => props.updateSetting("alertPersistence", value as AlertPersistence)} />
        </section>

        <section className="settings-card">
          <div className="settings-card__header">
            <h3>Camera</h3>
            <p>Low-light handling and feed presentation.</p>
          </div>
          <SettingsToggleRow title="Night mode" detail="Bias the feed for low-glare operation." checked={props.settings.nightMode} onChange={(checked) => props.updateSetting("nightMode", checked)} />
          <SettingsToggleRow title="IR control" detail="Use IR assist for parked or staged review." checked={props.settings.irControl} onChange={(checked) => props.updateSetting("irControl", checked)} />
          <SettingsToggleRow title="Exposure lock" detail="Keep contrast stable across the approach." checked={props.settings.exposureLock} onChange={(checked) => props.updateSetting("exposureLock", checked)} />
          <SettingsSelectRow title="Resolution" detail="Primary acquisition resolution." value={props.settings.resolution} options={["1920x1080", "1600x900", "1280x720"]} onChange={(value) => props.updateSetting("resolution", value)} />
          <SettingsSelectRow title="Stream quality" detail="Balance decode load against visual fidelity." value={props.settings.streamQuality} options={["High", "Balanced", "Low latency"]} onChange={(value) => props.updateSetting("streamQuality", value)} />
          <SettingsToggleRow title="Overlay labels" detail="Show plate, confidence, and direction on the live feed." checked={props.settings.overlayLabels} onChange={(checked) => props.updateSetting("overlayLabels", checked)} />
        </section>

        <section className="settings-card">
          <div className="settings-card__header">
            <h3>Storage and Sync</h3>
            <p>Media pressure, upload queue, and export defaults.</p>
          </div>
          <ReadOnlyRow title="Local storage used" value="18.2 GB" detail="Estimated cache usage for the current shift." />
          <ReadOnlyRow title="Sync status" value={props.dataSource === "live" ? "Healthy" : "Queued offline"} detail={`${props.activeSessions} active console session${props.activeSessions === 1 ? "" : "s"}`} />
          <ReadOnlyRow title="Upload pending" value="00:14 ETA" detail="The most recent evidence bundle is queued for sync." />
          <ReadOnlyRow title="Export path" value="runtime/exports" detail="Detection packages are written here by default." />
          <SettingsToggleRow title="Auto-delete temp captures" detail="Remove transient captures after they are exported or synced." checked={props.settings.autoDeleteTempCaptures} onChange={(checked) => props.updateSetting("autoDeleteTempCaptures", checked)} />
        </section>

        <section className="settings-card">
          <div className="settings-card__header">
            <h3>Map and Navigation</h3>
            <p>Route visuals and map behavior.</p>
          </div>
          <SettingsSelectRow title="Default map mode" detail="Preferred presentation for the ops map." value={props.settings.mapMode} options={["Dark route", "Street", "Satellite-style"]} onChange={(value) => props.updateSetting("mapMode", value)} />
          <SettingsToggleRow title="Auto-center on vehicle" detail="Keep the unit marker centered while moving." checked={props.settings.autoCenterVehicle} onChange={(checked) => props.updateSetting("autoCenterVehicle", checked)} />
          <SettingsToggleRow title="Show radius ring" detail="Display the active target geofence." checked={props.settings.showRadiusRing} onChange={(checked) => props.updateSetting("showRadiusRing", checked)} />
          <SettingsToggleRow title="Traffic overlay" detail="Expose live traffic hints on route." checked={props.settings.showTraffic} onChange={(checked) => props.updateSetting("showTraffic", checked)} />
          <SettingsSelectRow title="Navigation provider" detail="Internal route card or external navigation handoff." value={props.settings.navProvider} options={["Internal", "External"]} onChange={(value) => props.updateSetting("navProvider", value)} />
        </section>

        <section className="settings-card">
          <div className="settings-card__header">
            <h3>API and Session</h3>
            <p>Live data connection, fallback state, and refresh controls.</p>
          </div>
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
          <ReadOnlyRow title="Current source" value={props.dataSource.toUpperCase()} detail={props.dataError ?? "Live data is available when the API responds."} />
        </section>
      </div>
    </section>
  );
}

function DetailOverlay(props: {
  activeDestination: string;
  detailImageUrl: string | null;
  detailRow: ConsoleDetectionRow;
  detailTimeline: ConsoleDetectionRow[];
  hotlists: DashboardHotlist[];
  onAddToHotlist: () => void;
  onClose: () => void;
  onCopyPlate: (plate: string) => Promise<void>;
  onOpenMap: () => void;
}): ReactElement {
  return (
    <div className="overlay-shell">
      <div className="overlay-scrim" onClick={props.onClose} />
      <aside className="detail-overlay">
        <div className="detail-overlay__header">
          <button className="link-button" type="button" onClick={props.onClose}>
            Back
          </button>
          <div>
            <p className="eyebrow">Detection Record</p>
            <h3>{props.detailRow.plate1}</h3>
          </div>
          {props.detailRow.hotlist ? <Badge tone="critical">Hotlist</Badge> : null}
        </div>

        <div className="detail-overlay__body">
          <div className="detail-hero">
            {props.detailImageUrl ? <img alt={props.detailRow.plate1} src={props.detailImageUrl} /> : <div className="detail-hero__placeholder">{props.detailRow.vehicle}</div>}
          </div>

          <div className="detail-grid">
            <DetailField label="Plate" value={props.detailRow.plate1} tone={props.detailRow.hotlist ? "critical" : "cyan"} />
            <DetailField label="Vehicle" value={props.detailRow.vehicle} />
            <DetailField label="Confidence" value={confidenceLabel(props.detailRow.conf)} />
            <DetailField label="Camera" value={props.detailRow.source} />
            <DetailField label="GPS" value={props.detailRow.gps} />
            <DetailField label="Direction" value={`${props.detailRow.direction} / ${props.detailRow.lane}`} />
            <DetailField label="Address" value={props.activeDestination} />
            <DetailField label="Time" value={formatDateTime(props.detailRow.timestampUtc)} />
          </div>

          <section className="detail-section">
            <div className="detail-section__header">
              <h4>Notes</h4>
            </div>
            <p>
              {hotlistLabelForRow(props.detailRow, props.hotlists)
                ? `${hotlistLabelForRow(props.detailRow, props.hotlists)}. Keep this vehicle surfaced as a hotlist interrupt and route immediately after confirmation.`
                : `${props.detailRow.source} captured this detection on ${formatDateTime(props.detailRow.timestampUtc)}.`}
            </p>
          </section>

          <section className="detail-section">
            <div className="detail-section__header">
              <h4>Event Timeline</h4>
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
          <button className="btn btn--ghost" type="button" onClick={props.onOpenMap}>
            Open Map
          </button>
          <button className="btn btn--ghost" type="button" onClick={props.onAddToHotlist}>
            Add to Hotlist
          </button>
          <button className="btn btn--primary" type="button" onClick={() => void props.onCopyPlate(props.detailRow.plate1)}>
            Copy Plate
          </button>
        </div>
      </aside>
    </div>
  );
}

function HotlistAlertOverlay(props: {
  activeDestination: string;
  hotlistAudioMuted: boolean;
  hotlistRow: ConsoleDetectionRow;
  onDismiss: () => void;
  onMuteToggle: () => void;
  onNavigate: () => void;
  onRecover: () => void;
  onViewRecord: () => void;
}): ReactElement {
  return (
    <div className="hotlist-alert">
      <div className="hotlist-alert__header">
        <div>
          <p className="eyebrow">Critical Alert</p>
          <h2>Hotlist Match</h2>
        </div>
        <Badge tone="critical">{props.hotlistAudioMuted ? "Muted" : "Audio + visual"}</Badge>
      </div>

      <div className="hotlist-alert__hero">
        <div className="hotlist-alert__snapshot">{props.hotlistRow.vehicle}</div>
        <div className="hotlist-alert__identity">
          <strong>{props.hotlistRow.plate1}</strong>
          <span>{props.hotlistRow.vehicle}</span>
          <span>
            {props.hotlistRow.direction} | Conf {confidenceLabel(props.hotlistRow.conf)}
          </span>
        </div>
      </div>

      <div className="hotlist-alert__grid">
        <DetailField label="Camera" value={props.hotlistRow.source} />
        <DetailField label="GPS" value={props.hotlistRow.gps} />
        <DetailField label="Address" value={props.activeDestination} />
        <DetailField label="Time" value={formatDateTime(props.hotlistRow.timestampUtc)} />
      </div>

      <div className="hotlist-alert__actions">
        <button className="btn btn--primary" type="button" onClick={props.onNavigate}>
          Navigate
        </button>
        <button className="btn btn--ghost" type="button" onClick={props.onViewRecord}>
          View Record
        </button>
        <button className="btn btn--ghost" type="button" onClick={props.onRecover}>
          Mark Recovered
        </button>
        <button className="btn btn--ghost" type="button" onClick={props.onMuteToggle}>
          {props.hotlistAudioMuted ? "Restore Audio" : "Mute Audio This Event"}
        </button>
        <button className="btn btn--danger" type="button" onClick={props.onDismiss}>
          Dismiss
        </button>
      </div>
    </div>
  );
}

export default App;
