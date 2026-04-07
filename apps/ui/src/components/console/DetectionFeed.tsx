import { useEffect, useRef, useState, type ReactElement } from "react";

import { DetectionFeedRow, type DetectionFeedItem } from "./DetectionFeedRow";

interface DetectionFeedProps {
  confidenceLabel: (value: number) => string;
  confidenceTone: (value: number) => "high" | "medium" | "low";
  onOpenDetail: (rowId: string) => void;
  onSelectDetection: (rowId: string) => void;
  rows: DetectionFeedItem[];
  selectedDetectionId: string | null;
}

export function DetectionFeed(props: DetectionFeedProps): ReactElement {
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const interactionLockUntilRef = useRef(0);
  const [isHovering, setIsHovering] = useState(false);
  const [isManuallyPaused, setIsManuallyPaused] = useState(false);
  const [scrollIndex, setScrollIndex] = useState(0);

  useEffect(() => {
    setScrollIndex((current) => {
      if (props.rows.length === 0) {
        return 0;
      }
      return Math.min(current, props.rows.length - 1);
    });
  }, [props.rows.length]);

  useEffect(() => {
    if (props.rows.length < 2) {
      return;
    }

    const timer = window.setInterval(() => {
      if (isHovering || isManuallyPaused || Date.now() < interactionLockUntilRef.current) {
        return;
      }

      setScrollIndex((current) => {
        const next = (current + 1) % props.rows.length;
        const nextRow = props.rows[next];
        if (nextRow) {
          rowRefs.current.get(nextRow.id)?.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
          });
        }
        return next;
      });
    }, 2600);

    return () => window.clearInterval(timer);
  }, [isHovering, isManuallyPaused, props.rows]);

  function lockFeed(rowId: string): void {
    interactionLockUntilRef.current = Date.now() + 8000;
    rowRefs.current.get(rowId)?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }

  return (
    <div className="detection-feed-shell">
      <div className="detection-feed-shell__toolbar">
        <span className="detection-feed-shell__status">{isHovering || isManuallyPaused ? "Auto-scroll paused" : "Auto-scroll live"}</span>
        <button className="link-button" type="button" onClick={() => setIsManuallyPaused((current) => !current)}>
          {isManuallyPaused ? "Resume" : "Pause"}
        </button>
      </div>

      <div
        className="detection-feed"
        onMouseEnter={() => setIsHovering(true)}
        onMouseLeave={() => setIsHovering(false)}
      >
        {props.rows.map((row) => (
          <div
            key={row.id}
            ref={(node) => {
              if (node) {
                rowRefs.current.set(row.id, node);
              } else {
                rowRefs.current.delete(row.id);
              }
            }}
          >
            <DetectionFeedRow
              confidenceLabel={props.confidenceLabel}
              confidenceTone={props.confidenceTone}
              row={row}
              selected={props.selectedDetectionId === row.id}
              onOpenDetail={() => {
                lockFeed(row.id);
                props.onOpenDetail(row.id);
              }}
              onSelect={() => {
                lockFeed(row.id);
                props.onSelectDetection(row.id);
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
