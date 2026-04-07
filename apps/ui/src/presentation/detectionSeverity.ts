import type { DashboardAlertStatus } from "../live-api";

export type DetectionSeverity = "critical" | "priority" | "watch" | "observed";

interface DetectionSeveritySource {
  alertStatus?: DashboardAlertStatus | null;
  hotlist?: boolean;
}

export function detectionSeverityForRow(source: DetectionSeveritySource): DetectionSeverity {
  if (source.alertStatus === "active") {
    return "critical";
  }
  if (source.alertStatus === "acknowledged") {
    return "priority";
  }
  if (source.alertStatus === "dismissed") {
    return "watch";
  }
  if (source.hotlist) {
    return "watch";
  }
  return "observed";
}

export function detectionSeverityLabel(source: DetectionSeveritySource): string {
  if (source.alertStatus === "active") {
    return "Active";
  }
  if (source.alertStatus === "acknowledged") {
    return "Acknowledged";
  }
  if (source.alertStatus === "dismissed") {
    return "Dismissed";
  }
  if (source.hotlist) {
    return "Recovery";
  }
  return "Observed";
}
