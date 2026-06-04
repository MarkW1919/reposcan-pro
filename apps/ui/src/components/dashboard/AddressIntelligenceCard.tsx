import type { ReactElement } from "react";

import { DashboardWidgetFrame } from "./DashboardWidgetFrame";
import { StatusPill, type StatusPillTone } from "./StatusPill";

interface IntelligenceField {
  label: string;
  value: string;
}

interface PublicRecordData {
  status: "idle" | "loading" | "resolved" | "error";
  matched: boolean;
  standardizedAddress: string | null;
  dwellingLabel: string;
  areaSummary: string | null;
  sources: string[];
  caveats: string[];
}

export function AddressIntelligenceCard(props: {
  size?: "compact" | "standard" | "expanded";
  address: string;
  subtitle?: string;
  recoveryProbability: string;
  recoveryTone: StatusPillTone;
  recommendation: string;
  recommendationDetail: string;
  fields: IntelligenceField[];
  recentSummary?: string;
  publicData?: PublicRecordData | null;
}): ReactElement {
  const pub = props.publicData;
  return (
    <DashboardWidgetFrame
      title="Address Intelligence"
      eyebrow="Recovery location"
      size={props.size}
      meta={<StatusPill label={props.recoveryProbability} tone={props.recoveryTone} />}
    >
      <div className="address-intelligence-card">
        <div className="address-intelligence-card__hero">
          <strong>{props.address}</strong>
          {props.subtitle ? <span>{props.subtitle}</span> : null}
        </div>

        {pub && pub.status !== "idle" ? (
          <div className="address-intelligence-card__public">
            <span className="address-intelligence-card__public-label">Public records</span>
            {pub.status === "loading" ? (
              <p className="address-intelligence-card__public-status">Looking up public records…</p>
            ) : pub.status === "error" ? (
              <p className="address-intelligence-card__public-status">Public records lookup unavailable (offline).</p>
            ) : pub.matched ? (
              <>
                {pub.standardizedAddress ? <strong>{pub.standardizedAddress}</strong> : null}
                <div className="address-intelligence-card__public-tags">
                  <StatusPill label={pub.dwellingLabel} tone="cyan" />
                  {pub.areaSummary ? <span>{pub.areaSummary}</span> : null}
                </div>
                {pub.sources.length > 0 ? (
                  <small className="address-intelligence-card__public-sources">Sources: {pub.sources.join(", ")}</small>
                ) : null}
              </>
            ) : (
              <p className="address-intelligence-card__public-status">Address not found in public records — verify it was entered correctly.</p>
            )}
            {pub.caveats.map((caveat) => (
              <small key={caveat} className="address-intelligence-card__public-caveat">{caveat}</small>
            ))}
          </div>
        ) : null}

        <div className="address-intelligence-card__grid">
          {props.fields.map((field) => (
            <div key={field.label} className="address-intelligence-card__field">
              <span>{field.label}</span>
              <strong>{field.value}</strong>
            </div>
          ))}
        </div>

        <div className="address-intelligence-card__insight">
          <div>
            <span>AI Recommendation</span>
            <strong>{props.recommendation}</strong>
          </div>
          <p>{props.recommendationDetail}</p>
        </div>

        {props.recentSummary ? (
          <div className="address-intelligence-card__history">
            <span>Recent Sightings</span>
            <p>{props.recentSummary}</p>
          </div>
        ) : null}
      </div>
    </DashboardWidgetFrame>
  );
}
