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
  caveat: string | null;
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

function phoneHref(phone: string): string | undefined {
  const digits = phone.replace(/[^\d]/g, "");
  return digits.length >= 10 ? `tel:${digits}` : undefined;
}

function OccupantRow(props: { occupant: OccupantView }): ReactElement {
  const { occupant } = props;
  return (
    <li className="occupant-card__row">
      <strong className="occupant-card__name">{occupant.name}</strong>
      {occupant.phones.length > 0 ? (
        <span className="occupant-card__phones">
          {occupant.phones.map((phone, i) => {
            const href = phoneHref(phone);
            return (
              <span key={`${phone}-${i}`}>
                {i > 0 ? " · " : ""}
                {href ? (
                  <a className="occupant-card__phone-link" href={href}>
                    {phone}
                  </a>
                ) : (
                  phone
                )}
              </span>
            );
          })}
        </span>
      ) : null}
      {occupant.associated_people.length > 0 ? (
        <span className="occupant-card__associated">{occupant.associated_people.join(", ")}</span>
      ) : null}
    </li>
  );
}

function OccupantList(props: { people: OccupantView[] }): ReactElement {
  return (
    <ul className="occupant-card__list">
      {props.people.map((occupant, index) => (
        <OccupantRow key={`${occupant.name}-${index}`} occupant={occupant} />
      ))}
    </ul>
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

  const hasPeople = data.highConfidence.length > 0 || data.otherPossible.length > 0;

  return (
    <div className="occupant-card">
      <div className="occupant-card__head">
        <span className="occupant-card__label">People at this address</span>
        {data.fromCache ? (
          <StatusPill
            label={
              data.status === "offline"
                ? `Offline · cached${data.cacheAgeDays != null ? ` ${data.cacheAgeDays}d` : ""}`
                : "Cached"
            }
            tone="amber"
          />
        ) : data.source && hasPeople ? (
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
      ) : !hasPeople ? (
        <p className="occupant-card__status">No occupant records found for this address.</p>
      ) : (
        <>
          {data.highConfidence.length > 0 ? <OccupantList people={data.highConfidence} /> : null}
          {data.otherPossible.length > 0 ? (
            <>
              <span className="occupant-card__sublabel">Other possible matches</span>
              <OccupantList people={data.otherPossible} />
            </>
          ) : null}
        </>
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
            <span className="address-intelligence-card__public-label">Address check</span>
            {pub.status === "loading" ? (
              <p className="address-intelligence-card__public-status">Verifying address…</p>
            ) : pub.status === "error" ? (
              <p className="address-intelligence-card__public-status">Address lookup unavailable (offline).</p>
            ) : pub.matched ? (
              <>
                <div className="address-intelligence-card__public-verified">✓ Address verified in public records</div>
                {pub.standardizedAddress ? <strong>{pub.standardizedAddress}</strong> : null}
                <div className="address-intelligence-card__public-tags">
                  <StatusPill label={pub.dwellingLabel} tone="cyan" />
                  {pub.areaSummary ? <span>{pub.areaSummary}</span> : null}
                </div>
                {pub.caveat ? (
                  <small className="address-intelligence-card__public-caveat">Note: {pub.caveat}</small>
                ) : null}
              </>
            ) : (
              <p className="address-intelligence-card__public-status">
                Couldn't match that address in public records — try a full street address (number, street, city, state).
              </p>
            )}
          </div>
        ) : null}

        {props.fields.length > 0 ? (
          <div className="address-intelligence-card__grid">
            {props.fields.map((field) => (
              <div key={field.label} className="address-intelligence-card__field">
                <span>{field.label}</span>
                <strong>{field.value}</strong>
              </div>
            ))}
          </div>
        ) : null}

        <div className="address-intelligence-card__insight">
          <div>
            <span>AI Recommendation</span>
            <strong>{props.recommendation}</strong>
          </div>
          <p>{props.recommendationDetail}</p>
        </div>
      </div>
    </DashboardWidgetFrame>
  );
}
