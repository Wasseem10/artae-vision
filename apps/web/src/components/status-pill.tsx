import type { AgentObservedStatus, CameraStatus, RuleStatus } from "@/lib/types";

export function StatusPill({
  status,
}: {
  status: AgentObservedStatus | CameraStatus | RuleStatus;
}) {
  return (
    <span className={`statusPill status-${status}`}>
      <span className="statusDot" />
      {status}
    </span>
  );
}
