export type WorkspaceId = "dashboard" | "navigation" | "alerts" | "search" | "cameras" | "settings";

export type PanelId =
  | "opsMap"
  | "cameraMatrix"
  | "hotlistFeed"
  | "selectedAlert"
  | "routePlanner"
  | "statusStack"
  | "recoveryLog"
  | "dispatchBoard"
  | "crewChat";

export type SlotId = "railTop" | "railBottom" | "hero" | "support" | "board" | "detail";
export type CameraMode = "quad" | "priority" | "strip" | "dual";
export type LayoutPresetId = "route" | "recovery" | "streetSweep" | "cameraOps" | "navLpr" | "dualCamNav";

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
  { id: "dashboard", label: "Arrival Scan" },
  { id: "navigation", label: "Drive" },
  { id: "alerts", label: "Targets" },
  { id: "search", label: "Search" },
  { id: "cameras", label: "Camera" },
  { id: "settings", label: "Settings" },
];

export const panelCatalog: Record<PanelId, { label: string; description: string }> = {
  opsMap: {
    label: "Route and Radius",
    description: "Drive route, target radius, and nearby detection activity.",
  },
  cameraMatrix: {
    label: "Camera Confirm",
    description: "Plate and vehicle confirmation from the truck camera bank.",
  },
  hotlistFeed: {
    label: "Live Queue",
    description: "Hotlist hits, in-radius detections, and unsuppressed popup activity.",
  },
  selectedAlert: {
    label: "Target Focus",
    description: "Current recovery target with approach, evidence, and workflow context.",
  },
  routePlanner: {
    label: "Drive Brief",
    description: "Destination, trigger radius, and ETA context.",
  },
  statusStack: {
    label: "Cab Readiness",
    description: "GPS, cameras, sync, and storage health at a glance.",
  },
  recoveryLog: {
    label: "Case Log",
    description: "Active repossession cases and recent status changes.",
  },
  dispatchBoard: {
    label: "Repo Workflow",
    description: "Follow-up, dispatch, and alert actions for the selected target.",
  },
  crewChat: {
    label: "Crew Handoff",
    description: "Real-time messaging, evidence notes, and crew handoff coordination.",
  },
};

export const dashboardPresets: Record<LayoutPresetId, DashboardLayout> = {
  route: {
    profile: "Drive Console",
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
    profile: "Recovery Focus",
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
  streetSweep: {
    profile: "Street Sweep",
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
  cameraOps: {
    profile: "Camera Confirm",
    cameraMode: "quad",
    slots: {
      railTop: "cameraMatrix",
      railBottom: "statusStack",
      hero: "hotlistFeed",
      support: "selectedAlert",
      board: "dispatchBoard",
      detail: "recoveryLog",
    },
  },
  navLpr: {
    profile: "Drive and Detect",
    cameraMode: "quad",
    slots: {
      railTop: "routePlanner",
      railBottom: "recoveryLog",
      hero: "opsMap",
      support: "cameraMatrix",
      board: "hotlistFeed",
      detail: "statusStack",
    },
  },
  dualCamNav: {
    profile: "Dual Cam Drive",
    cameraMode: "dual",
    slots: {
      railTop: "routePlanner",
      railBottom: "statusStack",
      hero: "opsMap",
      support: "cameraMatrix",
      board: "hotlistFeed",
      detail: "selectedAlert",
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
    routeAction: "Stage and Confirm",
    location: "Shoreline Blvd curbside",
    distance: "0.2 mi",
    notes: "Target is parked curbside. Spotter reported the driver is away from the vehicle.",
    bestApproach: "Roll past once, confirm the plate and VIN, then return from the rear with a clear hookup line.",
  },
  {
    id: "alt-3lpm771",
    plate: "3LPM771",
    vehicle: "Black Ford Explorer",
    colorYear: "Black / 2019-2023",
    time: "01:12:08",
    camera: "Roadside LPR 2",
    confidence: 0.89,
    gps: "37.42243, -122.08229",
    severity: "priority",
    scenario: "departure_risk",
    status: "monitoring",
    routeAction: "Circle and Reacquire",
    location: "Apartment entrance off Rengstorff Ave",
    distance: "0.6 mi",
    notes: "Vehicle moved within the last five minutes. Keep visual contact and avoid tipping the driver.",
    bestApproach: "Circle the block and reacquire from the cross street before committing.",
  },
  {
    id: "alt-9xca441",
    plate: "9XCA441",
    vehicle: "Gray Honda Accord",
    colorYear: "Gray / 2017-2020",
    time: "01:09:44",
    camera: "Roof Cam Rear",
    confidence: 0.86,
    gps: "37.42061, -122.08155",
    severity: "priority",
    scenario: "visual_match",
    status: "en_route",
    routeAction: "Mark and Stage",
    location: "Office frontage on Plymouth St",
    distance: "1.1 mi",
    notes: "Photo match is strong. Confirm rear plate before stopping the truck.",
    bestApproach: "Pass once for confirmation, then stage one block down for a clean return.",
  },
  {
    id: "alt-1jfd552",
    plate: "1JFD552",
    vehicle: "Blue Chevy Tahoe",
    colorYear: "Blue / 2016-2020",
    time: "01:04:57",
    camera: "Neighborhood Sweep 3",
    confidence: 0.82,
    gps: "37.41983, -122.08544",
    severity: "watch",
    scenario: "assignment",
    status: "monitoring",
    routeAction: "Watch Only",
    location: "Elm side street curb line",
    distance: "2.5 mi",
    notes: "Keep on watch only. No confirmed park pattern yet.",
    bestApproach: "Stay mobile and use drive-by confirmation rather than stopping.",
  },
];

export const cameraFeeds: CameraFeed[] = [
  {
    id: "cam-front-1",
    label: "Roadside LPR 1",
    zone: "Front Left",
    status: "Online",
    fps: 30,
    tempC: 61,
    role: "Forward plate read",
  },
  {
    id: "cam-side-2",
    label: "Roadside LPR 2",
    zone: "Front Right",
    status: "Online",
    fps: 28,
    tempC: 59,
    role: "Cross-street sweep",
  },
  {
    id: "cam-rear-3",
    label: "Roof Cam Rear",
    zone: "Rear Left",
    status: "Online",
    fps: 27,
    tempC: 60,
    role: "Rear confirmation",
  },
  {
    id: "cam-west-4",
    label: "Tow Cam Right",
    zone: "Rear Right",
    status: "Offline",
    fps: 0,
    tempC: 0,
    role: "Tow alignment",
  },
];

export const recoveryLog: RecoveryLogEntry[] = [
  {
    id: "rec-001",
    status: "active",
    title: "Camry curbside recovery",
    plate: "6BZN220",
    updatedAt: "1 min ago",
  },
  {
    id: "rec-002",
    status: "watch",
    title: "Accord roadside confirmation",
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

export interface CrewChatMessage {
  id: string;
  sender: string;
  body: string;
  timestamp: string;
  type: "message" | "handoff" | "system";
}

export const demoChatMessages: CrewChatMessage[] = [
  { id: "msg-001", sender: "Unit 7", body: "Eyes on target vehicle, silver Camry curbside on Shoreline", timestamp: "04:12", type: "message" },
  { id: "msg-002", sender: "Dispatch", body: "Copy Unit 7. Unit 3 en route for backup, ETA 4 min", timestamp: "04:13", type: "message" },
  { id: "msg-003", sender: "System", body: "Handoff: Unit 3 assigned to assignment asg_001", timestamp: "04:14", type: "handoff" },
  { id: "msg-004", sender: "Unit 3", body: "Confirmed, approaching from the westbound cross street", timestamp: "04:15", type: "message" },
  { id: "msg-005", sender: "System", body: "Hotlist match: 6BZN220 detected on cam-front-1", timestamp: "04:16", type: "system" },
  { id: "msg-006", sender: "Unit 7", body: "Plates confirmed visual match. Ready for tow", timestamp: "04:17", type: "message" },
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
  route: "Map-first driving layout with hotlist and radius status close by.",
  recovery: "Target-first layout for on-scene confirmation and hookup decisions.",
  streetSweep: "Camera-led sweep for curbside, apartment, office, and roadside searches.",
  cameraOps: "Quad camera grid with queue and target detail for fast confirmation.",
  navLpr: "Drive route, active radius scan state, and vehicle recognition together.",
  dualCamNav: "Two camera windows alongside the live driving map.",
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
    camera: "Roadside LPR 1",
    location: "Apartment curb line",
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
    camera: "Roadside LPR 2",
    location: "Cross street approach",
    imageLabel: "Roadside sweep frame",
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
    camera: "Roof Cam Rear",
    location: "Driveway across the target block",
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
    camera: "Roadside LPR 2",
    location: "Shoreline Blvd curbside",
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
    camera: "Roof Cam Rear",
    location: "Office frontage on Plymouth St",
    imageLabel: "Visual match frame",
    confidence: 0.9,
    note: "Hotlist recognition stays active regardless of navigation state or address-based popup suppression.",
  },
];
