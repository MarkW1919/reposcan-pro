import type { ReactElement } from "react";

interface DetectionEvidenceHeroProps {
  frameLabel?: string;
  framePlaceholder: string;
  frameUrl: string | null;
  plateCropLabel?: string;
  platePlaceholder: string;
  plateCropUrl: string | null;
  plateText: string;
  tone?: "default" | "critical";
}

export function DetectionEvidenceHero(props: DetectionEvidenceHeroProps): ReactElement {
  const tone = props.tone ?? "default";
  const frameLabel = props.frameLabel ?? "Color overview";
  const plateCropLabel = props.plateCropLabel ?? "Plate crop";

  return (
    <div className={`evidence-hero evidence-hero--${tone}`}>
      <div className="evidence-hero__panel evidence-hero__panel--plate">
        <div className="evidence-hero__media evidence-hero__media--plate">
          {props.plateCropUrl ? (
            <img alt={`${props.plateText} plate crop`} src={props.plateCropUrl} />
          ) : (
            <div className="evidence-hero__placeholder evidence-hero__placeholder--plate">{props.platePlaceholder}</div>
          )}
        </div>
        <span className="evidence-hero__label">{plateCropLabel}</span>
      </div>

      <div className="evidence-hero__panel evidence-hero__panel--frame">
        <div className="evidence-hero__media evidence-hero__media--frame">
          {props.frameUrl ? (
            <img alt={`${props.plateText} overview`} src={props.frameUrl} />
          ) : (
            <div className="evidence-hero__placeholder">{props.framePlaceholder}</div>
          )}
        </div>
        <span className="evidence-hero__label">{frameLabel}</span>
      </div>
    </div>
  );
}
