import type { ReactElement } from "react";

import { DashboardWidgetFrame } from "./DashboardWidgetFrame";
import { StatusPill, type StatusPillTone } from "./StatusPill";

interface IntelligenceField {
  label: string;
  value: string;
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
}): ReactElement {
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
