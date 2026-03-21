import { startTransition, useEffect, useRef, useState, type FormEvent, type ReactElement, type ReactNode } from "react";

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
  createHotlist,
  createReview,
  fetchDemoRuntimeStatus,
  fetchHotlists,
  fetchReviews,
  fetchDashboardOverview,
  mapOverviewToAlertItems,
  mapOverviewToPopupHistory,
  startDemoRun,
  updateHotlist,
  type DemoRuntimeStatus as DemoRuntimeStatusRecord,
  type DashboardHotlist,
  type DashboardOverviewResponse,
  type ReviewAction,
  type ReviewRecord,
} from "./live-api";

const layoutStorageKey = "reposcan.ui.dashboard-layout.v1";
const settingsStorageKey = "reposcan.ui.field-settings.v1";
const defaultPopupHistory: DetectionPopupEvent[] = [hotlistPopupDetections[0], addressScanDetections[0]];

interface PopupNotification extends DetectionPopupEvent {
  instanceId: string;
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

function App() {
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceId>("dashboard");
  const [layoutEditorOpen, setLayoutEditorOpen] = useState(false);
  const [layout, setLayout] = useState<DashboardLayout>(() => loadLayout());
  const [fieldSettings, setFieldSettings] = useState<FieldSettings>(() => loadFieldSettings());
  const [selectedAlertId, setSelectedAlertId] = useState<string>(alerts[0]?.id ?? "");
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
  const previousWithinArrivalRef = useRef(false);
  const queuedLivePopupIdsRef = useRef<Set<string>>(new Set());
  const previousDemoRunStateRef = useRef<DemoRuntimeStatusRecord["state"]>("idle");
  const previousDemoRunIdRef = useRef<string | null>(null);

  const operatorAlerts = liveOverview ? mapOverviewToAlertItems(liveOverview, alerts) : alerts;
  const selectedAlert = operatorAlerts.find((alert) => alert.id === selectedAlertId) ?? operatorAlerts[0];
  const selectedDetectionId = selectedAlert?.detectionId ?? null;
  const selectedHotlist = hotlistEntries.find((entry) => entry.entry_id === selectedHotlistId) ?? null;
  const selectedCamera = cameraFeeds.find((camera) => camera.id === selectedCameraId) ?? cameraFeeds[0];
  const onlineCameraCount = cameraFeeds.filter((camera) => camera.status === "Online").length;
  const liveHealthState = liveOverview?.health.state ?? "demo";
  const activeHotlistCount = liveOverview?.counts.active_hotlists ?? 0;
  const activeAlertCount = liveOverview?.counts.active_alerts ?? operatorAlerts.filter((alert) => alert.severity === "critical").length;
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
  const reviewsEnabled = liveDataSource === "live" && selectedDetectionId !== null;
  const hotlistsEnabled = liveDataSource === "live";
  const demoRuntimeEnabled = liveDataSource === "live";
  const latestReview = reviewHistory[0] ?? null;
  const canSubmitReview =
    reviewsEnabled &&
    !reviewSubmitting &&
    (reviewAction !== "correct" || reviewCorrectedPlate.trim().length > 0);
  const canSubmitHotlist = hotlistsEnabled && !hotlistSaving && hotlistPlateText.trim().length > 0;
  const canStartDemoRun =
    demoRuntimeEnabled &&
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
    if (operatorAlerts.some((alert) => alert.id === selectedAlertId)) {
      return;
    }

    setSelectedAlertId(operatorAlerts[0]?.id ?? "");
  }, [operatorAlerts, selectedAlertId]);

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
  }, []);

  useEffect(() => {
    setReviewAction("confirm");
    setReviewCorrectedPlate(selectedAlert.plate);
    setReviewNotes("");
    setReviewSuccess(null);
    setReviewError(null);
  }, [selectedAlert.id, selectedAlert.plate]);

  useEffect(() => {
    if (demoPlateText.trim().length > 0) {
      return;
    }
    setDemoPlateText(selectedAlert.plate);
  }, [demoPlateText, selectedAlert.plate]);

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
                  style={{
                    width: `${Math.min(100, (Math.max(0, 1760 - currentDistanceFeet) / 1760) * 100)}%`,
                  }}
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
                  style={{
                    left: `${18 + index * 19}%`,
                    top: `${20 + (index % 3) * 18}%`,
                  }}
                  type="button"
                  onClick={() => setSelectedAlertId(alert.id)}
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
                  onClick={() => setSelectedAlertId(alert.id)}
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
                <div className="target-photo">
                  <span>Target photo</span>
                  <strong>{selectedAlert.plate}</strong>
                </div>
                <div className="target-keyline">
                  <span className={`badge badge--${severityTone(selectedAlert.severity)}`}>
                    {scenarioLabels[selectedAlert.scenario]}
                  </span>
                  <span className="badge badge--outlined">{statusLabels[selectedAlert.status]}</span>
                  <h3>{selectedAlert.vehicle}</h3>
                  <p>{selectedAlert.colorYear}</p>
                </div>
              </div>
              <div className="target-details">
                <StatusLine label="Camera" value={selectedAlert.camera} />
                <StatusLine label="Confidence" value={confidenceLabel(selectedAlert.confidence)} />
                <StatusLine label="GPS" value={selectedAlert.gps} />
                <StatusLine label="Distance" value={currentDistanceLabel} />
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
              </div>
              <div className="notes-box">
                <label className="panel-label">Best approach</label>
                <p>{selectedAlert.bestApproach}</p>
              </div>
              <div className="notes-box">
                <label className="panel-label">Field notes</label>
                <p>{selectedAlert.notes}</p>
              </div>
              <div className="review-shell">
                <div className="live-activity__header">
                  <strong>Operator review</strong>
                  <span>
                    {reviewsEnabled
                      ? "Persisted locally through the live API."
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
                            <strong>{review.corrected_plate_text ?? selectedAlert.plate}</strong>
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
              {recoveryLog.map((entry) => (
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
                <strong>Field actions</strong>
                <span>Quick shortcuts for the selected target</span>
              </div>
              <div className="action-grid">
                {[
                  selectedAlert.routeAction,
                  "Mark sighted",
                  "Call office",
                  "Log pass",
                  "Tow ready",
                  "Stand down",
                ].map((action, index) => (
                  <button key={action} className={`button ${index === 0 ? "button--primary" : ""}`} type="button">
                    {action}
                  </button>
                ))}
              </div>
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
            <PanelFrame panelId="hotlistFeed" titleOverride="Hotlist Manager">
              <div className="hotlist-manager">
                <div className="live-activity__header">
                  <strong>Local hotlist control</strong>
                  <span>
                    {hotlistsEnabled
                      ? `${hotlistEntries.length} hotlist entr${hotlistEntries.length === 1 ? "y" : "ies"} loaded from the live API.`
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
        <span>
          Active alerts: {activeAlertCount} / Active hotlists: {liveOverview ? activeHotlistCount : "demo"}
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
