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
  county: string | null;
  dwellingLabel: string;
  areaSummary: string | null;
  sources: string[];
  caveats: string[];
}

interface OccupantView {
  name: string;
  phones: string[];
  associated_people: string[];
}

interface OccupantData {
  status: "ok" | "no_match" | "unavailable" | "offline" | "disabled" | "unconfigured";
  source: string | null;
  highConfidence: OccupantView[];
  otherPossible: OccupantView[];
  previousAddresses: string[];
  fromCache: boolean;
  cacheAgeDays: number | null;
}

function OccupantRow(props: { occupant: OccupantView }): ReactElement {
  const { occupant } = props;
  return (
    <li className="occupant-card__row">
      <strong className="occupant-card__name">{occupant.name}</strong>
      {occupant.phones.length > 0 ? (
        <span className="occupant-card__phones">{occupant.phones.join(" · ")}</span>
      ) : null}
      {occupant.associated_people.length > 0 ? (
        <span className="occupant-card__associated">{occupant.associated_people.join(", ")}</span>
      ) : null}
    </li>
  );
}

function OccupantSection(props: {
  fetchStatus: PublicRecordData["status"];
  data: OccupantData;
  onInvestigatePreviousAddress?: (address: string) => void;
}): ReactElement | null {
  const { data, fetchStatus } = props;

  // Free/keyless mode: occupant lookup is intentionally off — keep the card
  // focused on the address layer instead of showing an empty people panel.
  if (data.status === "disabled" && fetchStatus !== "loading") {
    return null;
  }

  const people = [...data.highConfidence, ...data.otherPossible];

  return (
    <div className="occupant-card">
      <div className="occupant-card__head">
        <span className="occupant-card__label">People at this address</span>
        {data.fromCache ? (
          <StatusPill
            label={
              data.status === "offline"
                ? `Offline · cached${data.cacheAgeDays != null ? ` ${data.cacheAgeDays}d ago` : ""}`
                : "Cached"
            }
            tone="amber"
          />
        ) : data.source && people.length > 0 ? (
          <StatusPill label={data.source} tone="cyan" />
        ) : null}
      </div>

      {fetchStatus === "loading" ? (
        <p className="occupant-card__status">Looking up occupants…</p>
      ) : fetchStatus === "error" ? (
        <p className="occupant-card__status">Occupant lookup unavailable (offline).</p>
      ) : data.status === "unconfigured" ? (
        <p className="occupant-card__status">Add a WhitePages Pro API key to surface people associated with this address.</p>
      ) : data.status === "unavailable" ? (
        <p className="occupant-card__status">Occupant provider is unavailable right now — showing address verification only.</p>
      ) : people.length === 0 ? (
        <p className="occupant-card__status">No occupant records found for this address.</p>
      ) : (
        <ul className="occupant-card__list">
          {people.map((occupant, index) => (
            <OccupantRow key={`${occupant.name}-${index}`} occupant={occupant} />
          ))}
        </ul>
      )}

      {data.previousAddresses.length > 0 ? (
        <div className="occupant-card__previous">
          <span className="occupant-card__previous-label">Previous addresses</span>
          <ul className="occupant-card__previous-list">
            {data.previousAddresses.map((address) => (
              <li key={address}>
                <button
                  type="button"
                  className="occupant-card__previous-link"
                  title="Investigate on map"
                  onClick={() => props.onInvestigatePreviousAddress?.(address)}
                >
                  {address}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
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
  occupantData?: OccupantData | null;
  onInvestigatePreviousAddress?: (address: string) => void;
}): ReactElement {
  const pub = props.publicData;
  const occ = props.occupantData;
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

        {occ && pub && pub.status !== "idle" ? (
          <OccupantSection
            fetchStatus={pub.status}
            data={occ}
            onInvestigatePreviousAddress={props.onInvestigatePreviousAddress}
          />
        ) : null}

        {pub && pub.status !== "idle" ? (
          <div className="address-intelligence-card__public">
            <span className="address-intelligence-card__public-label">Public records</span>
            {pub.status === "loading" ? (
              <p className="address-intelligence-card__public-status">Looking up public records…</p>
            ) : pub.status === "error" ? (
              <p className="address-intelligence-card__public-status">Public records lookup unavailable (offline).</p>
            ) : pub.matched ? (
              <>
                <div className="address-intelligence-card__public-verified">✓ Address verified in public records</div>
                {pub.standardizedAddress ? <strong>{pub.standardizedAddress}</strong> : null}
                <div className="address-intelligence-card__public-tags">
                  <StatusPill label={pub.dwellingLabel} tone="cyan" />
                  {pub.county ? <span>{pub.county}</span> : null}
                  {pub.areaSummary ? <span>{pub.areaSummary}</span> : null}
                </div>
                {pub.sources.length > 0 ? (
                  <small className="address-intelligence-card__public-sources">Sources: {pub.sources.join(", ")}</small>
                ) : null}
                {pub.caveats.map((caveat) => (
                  <small key={caveat} className="address-intelligence-card__public-caveat">Note: {caveat}</small>
                ))}
              </>
            ) : (
              <p className="address-intelligence-card__public-status">
                Couldn't match that address in public records — try a full street address (number, street, city, state).
              </p>
            )}
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
