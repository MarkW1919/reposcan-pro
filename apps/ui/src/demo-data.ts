export type WorkspaceId = "dashboard" | "navigation" | "alerts" | "search" | "cameras" | "settings";

export type PanelId =
  | "opsMap"
  | "cameraMatrix"
  | "hotlistFeed"
  | "selectedAlert"
  | "routePlanner"
  | "statusStack"
  | "recoveryLog"
  | "dispatchBoard";

export type SlotId = "railTop" | "railBottom" | "hero" | "support" | "board" | "detail";
export type CameraMode = "quad" | "priority" | "strip";
export type LayoutPresetId = "route" | "recovery" | "lotScan";

export interface DashboardLayout {
  profile: string;
  cameraMode: CameraMode;
  slots: Record<SlotId, PanelId>;
}

export interface FieldSettings {
  targetRefreshInterval: string;
  arrivalTriggerDistance: number;
  routeTrafficOverlay: boolean;
  ocrConfidenceThreshold: number;
  maxActiveTargets: number;
  autoMarkOnScene: boolean;
  silentShiftMode: boolean;
  lowStorageWarning: boolean;
}

export interface AlertItem {
  id: string;
  detectionId?: string;
  plate: string;
  vehicle: string;
  colorYear: string;
  time: string;
  camera: string;
  confidence: number;
  gps: string;
  severity: "critical" | "priority" | "watch";
  scenario: "assignment" | "visual_match" | "departure_risk" | "tow_ready";
  status: "en_route" | "onsite" | "monitoring" | "cleared";
  routeAction: string;
  location: string;
  distance: string;
  notes: string;
  bestApproach: string;
}

export interface CameraFeed {
  id: string;
  label: string;
  zone: string;
  status: "Online" | "Offline";
  fps: number;
  tempC: number;
  role: string;
}

export interface RecoveryLogEntry {
  id: string;
  status: "active" | "watch" | "closed";
  title: string;
  plate: string;
  updatedAt: string;
}

export interface DetectionPopupEvent {
  id: string;
  type: "address" | "hotlist";
  plate: string | null;
  vehicle: string;
  colorYear: string;
  timestamp: string;
  gps: string;
  camera: string;
  location: string;
  imageLabel: string;
  confidence: number;
  note: string;
}

export const workspaceTabs: Array<{ id: WorkspaceId; label: string }> = [
  { id: "dashboard", label: "Recovery Dashboard" },
  { id: "navigation", label: "Route HUD" },
  { id: "alerts", label: "Recovery Alerts" },
  { id: "search", label: "Search" },
  { id: "cameras", label: "Camera Views" },
  { id: "settings", label: "Field Settings" },
];

export const panelCatalog: Record<PanelId, { label: string; description: string }> = {
  opsMap: {
    label: "Map and Approach",
    description: "Route line, arrival ring, and nearby target activity.",
  },
  cameraMatrix: {
    label: "Camera Grid",
    description: "Truck-mounted views for fast visual confirmation.",
  },
  hotlistFeed: {
    label: "Recovery Alerts",
    description: "Recent target hits, address-scan activity, and always-on hotlist events.",
  },
  selectedAlert: {
    label: "Target Card",
    description: "Current recovery target with best approach notes.",
  },
  routePlanner: {
    label: "Route Brief",
    description: "Destination, trigger distance, and eta context.",
  },
  statusStack: {
    label: "Cab Status",
    description: "GPS, cameras, sync, and storage health at a glance.",
  },
  recoveryLog: {
    label: "Recovery Log",
    description: "Active assignments and recent status changes.",
  },
  dispatchBoard: {
    label: "Quick Actions",
    description: "Fast field actions for the selected target.",
  },
};

export const dashboardPresets: Record<LayoutPresetId, DashboardLayout> = {
  route: {
    profile: "Route HUD",
    cameraMode: "priority",
    slots: {
      railTop: "routePlanner",
      railBottom: "statusStack",
      hero: "opsMap",
      support: "hotlistFeed",
      board: "cameraMatrix",
      detail: "selectedAlert",
    },
  },
  recovery: {
    profile: "Active Recovery",
    cameraMode: "priority",
    slots: {
      railTop: "routePlanner",
      railBottom: "recoveryLog",
      hero: "selectedAlert",
      support: "hotlistFeed",
      board: "cameraMatrix",
      detail: "dispatchBoard",
    },
  },
  lotScan: {
    profile: "Lot Scan",
    cameraMode: "quad",
    slots: {
      railTop: "statusStack",
      railBottom: "routePlanner",
      hero: "cameraMatrix",
      support: "hotlistFeed",
      board: "opsMap",
      detail: "dispatchBoard",
    },
  },
};

export const defaultFieldSettings: FieldSettings = {
  targetRefreshInterval: "60 sec",
  arrivalTriggerDistance: 300,
  routeTrafficOverlay: true,
  ocrConfidenceThreshold: 0.8,
  maxActiveTargets: 10,
  autoMarkOnScene: true,
  silentShiftMode: false,
  lowStorageWarning: true,
};

export const alerts: AlertItem[] = [
  {
    id: "alt-682n220",
    plate: "6BZN220",
    vehicle: "White Toyota Camry",
    colorYear: "White / 2018-2021",
    time: "01:14:22",
    camera: "Street Cam 2",
    confidence: 0.93,
    gps: "37.42172, -122.08408",
    severity: "critical",
    scenario: "tow_ready",
    status: "onsite",
    routeAction: "Open Route",
    location: "Shoreline Marina south lot",
    distance: "0.2 mi",
    notes: "Target is parked nose-out near the fence line. Spotter reported no wheel lock.",
    bestApproach: "Enter from the south lane and keep passenger side hidden from the office.",
  },
  {
    id: "alt-3lpm771",
    plate: "3LPM771",
    vehicle: "Black Ford Explorer",
    colorYear: "Black / 2019-2023",
    time: "01:12:08",
    camera: "Gate North",
    confidence: 0.89,
    gps: "37.42243, -122.08229",
    severity: "priority",
    scenario: "departure_risk",
    status: "monitoring",
    routeAction: "Route Around Block",
    location: "North gate inbound lane",
    distance: "0.6 mi",
    notes: "Vehicle was moving five minutes ago. Keep a rolling angle and avoid direct pass.",
    bestApproach: "Loop westbound and watch the north gate exit before committing.",
  },
  {
    id: "alt-9xca441",
    plate: "9XCA441",
    vehicle: "Gray Honda Accord",
    colorYear: "Gray / 2017-2020",
    time: "01:09:44",
    camera: "Lot East",
    confidence: 0.86,
    gps: "37.42061, -122.08155",
    severity: "priority",
    scenario: "visual_match",
    status: "en_route",
    routeAction: "Mark Sighted",
    location: "Lot east row C",
    distance: "1.1 mi",
    notes: "Photo match is strong. Confirm rear plate before engaging the row.",
    bestApproach: "Use the service alley, then turn into row C with cameras already up.",
  },
  {
    id: "alt-1jfd552",
    plate: "1JFD552",
    vehicle: "Blue Chevy Tahoe",
    colorYear: "Blue / 2016-2020",
    time: "01:04:57",
    camera: "Street Cam 1",
    confidence: 0.82,
    gps: "37.41983, -122.08544",
    severity: "watch",
    scenario: "assignment",
    status: "monitoring",
    routeAction: "Log Pass",
    location: "Elm service road",
    distance: "2.5 mi",
    notes: "Keep on watch only. No confirmed park pattern yet.",
    bestApproach: "Stay mobile and use drive-by confirmation rather than stopping.",
  },
];

export const cameraFeeds: CameraFeed[] = [
  {
    id: "cam-front-1",
    label: "Main Entry",
    zone: "Front Left",
    status: "Online",
    fps: 30,
    tempC: 61,
    role: "Lane watch",
  },
  {
    id: "cam-side-2",
    label: "Gate North",
    zone: "Front Right",
    status: "Online",
    fps: 28,
    tempC: 59,
    role: "Street sweep",
  },
  {
    id: "cam-rear-3",
    label: "Lot East",
    zone: "Rear Left",
    status: "Online",
    fps: 27,
    tempC: 60,
    role: "Approach cover",
  },
  {
    id: "cam-west-4",
    label: "Street Cam 2",
    zone: "Rear Right",
    status: "Offline",
    fps: 0,
    tempC: 0,
    role: "Tow bed check",
  },
];

export const recoveryLog: RecoveryLogEntry[] = [
  {
    id: "rec-001",
    status: "active",
    title: "Camry shoreline pull",
    plate: "6BZN220",
    updatedAt: "1 min ago",
  },
  {
    id: "rec-002",
    status: "watch",
    title: "Accord lot east sweep",
    plate: "9XCA441",
    updatedAt: "6 min ago",
  },
  {
    id: "rec-003",
    status: "closed",
    title: "Tahoe westside false lead",
    plate: "1JFD552",
    updatedAt: "42 min ago",
  },
];

export const layoutSlotLabels: Record<SlotId, string> = {
  railTop: "Left Rail Upper",
  railBottom: "Left Rail Lower",
  hero: "Main Stage Hero",
  support: "Main Stage Support",
  board: "Operations Board",
  detail: "Detail Dock",
};

export const presetDescriptions: Record<LayoutPresetId, string> = {
  route: "Map-first driving layout with alerts and camera confirmation close by.",
  recovery: "Target-first layout for when you are on scene and deciding fast.",
  lotScan: "Camera-led sweep for property entrances, rows, and staged passes.",
};

export const scenarioLabels: Record<AlertItem["scenario"], string> = {
  assignment: "Assignment",
  visual_match: "Visual Match",
  departure_risk: "Departure Risk",
  tow_ready: "Tow Ready",
};

export const statusLabels: Record<AlertItem["status"], string> = {
  en_route: "En Route",
  onsite: "On Scene",
  monitoring: "Monitoring",
  cleared: "Cleared",
};

export const detectionPopupTypeLabels: Record<DetectionPopupEvent["type"], string> = {
  address: "Address Scan",
  hotlist: "Hotlist Match",
};

export const addressScanDetections: DetectionPopupEvent[] = [
  {
    id: "scan-001",
    type: "address",
    plate: "8YXR120",
    vehicle: "Silver Nissan Altima",
    colorYear: "Silver / 2019-2022",
    timestamp: "01:15:06",
    gps: "37.42111, -122.08494",
    camera: "Main Entry",
    location: "South lot drive lane",
    imageLabel: "Front-left frame",
    confidence: 0.88,
    note: "General vehicle alert surfaced because the truck is inside the configured address radius.",
  },
  {
    id: "scan-002",
    type: "address",
    plate: null,
    vehicle: "Red Kia Soul",
    colorYear: "Red / 2018-2021",
    timestamp: "01:15:21",
    gps: "37.42088, -122.08397",
    camera: "Gate North",
    location: "Visitor row entrance",
    imageLabel: "Street sweep frame",
    confidence: 0.74,
    note: "Vehicle classification completed, but the rear plate is partially occluded.",
  },
  {
    id: "scan-003",
    type: "address",
    plate: "472XKR8",
    vehicle: "White Ford F-150",
    colorYear: "White / 2020-2024",
    timestamp: "01:15:43",
    gps: "37.42146, -122.08318",
    camera: "Lot East",
    location: "Back row near service gate",
    imageLabel: "Rear-left frame",
    confidence: 0.84,
    note: "General detection pushed to the operator because scan mode is active inside the arrival ring.",
  },
];

export const hotlistPopupDetections: DetectionPopupEvent[] = [
  {
    id: "hot-001",
    type: "hotlist",
    plate: "6BZN220",
    vehicle: "White Toyota Camry",
    colorYear: "White / 2018-2021",
    timestamp: "01:16:02",
    gps: "37.42172, -122.08408",
    camera: "Street Cam 2",
    location: "Shoreline Marina south lot",
    imageLabel: "Tow-ready hit",
    confidence: 0.93,
    note: "Confirmed hotlist match. Popup and high-priority cab notification fire even if address scan is disabled.",
  },
  {
    id: "hot-002",
    type: "hotlist",
    plate: "9XCA441",
    vehicle: "Gray Honda Accord",
    colorYear: "Gray / 2017-2020",
    timestamp: "01:16:18",
    gps: "37.42061, -122.08155",
    camera: "Lot East",
    location: "Lot east row C",
    imageLabel: "Visual match frame",
    confidence: 0.9,
    note: "Hotlist recognition stays active regardless of navigation state or address-based popup suppression.",
  },
];
