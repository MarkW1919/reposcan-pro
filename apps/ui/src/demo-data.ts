export interface FieldSettings {
  targetRefreshInterval: string;
  arrivalTriggerDistance: number;
  routeTrafficOverlay: boolean;
  ocrConfidenceThreshold: number;
  maxActiveTargets: number;
  autoArmArrivalScan: boolean;
  silentShiftMode: boolean;
  lowStorageWarning: boolean;
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

export const defaultFieldSettings: FieldSettings = {
  targetRefreshInterval: "60 sec",
  arrivalTriggerDistance: 300,
  routeTrafficOverlay: true,
  ocrConfidenceThreshold: 0.8,
  maxActiveTargets: 10,
  autoArmArrivalScan: true,
  silentShiftMode: false,
  lowStorageWarning: true,
};

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
