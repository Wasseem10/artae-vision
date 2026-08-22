import type { ProductionReadiness } from "@/lib/types";

interface ProductionReadinessPanelProps {
  report: ProductionReadiness | null;
  visible: boolean;
}

export function ProductionReadinessPanel({
  report,
  visible,
}: ProductionReadinessPanelProps) {
  if (!visible) return null;

  return (
    <section className="panel readinessPanel" id="production-readiness">
      <div className="panelHeader readinessHeader">
        <div>
          <span className="eyebrow">Launch safety</span>
          <h2>Production readiness</h2>
          <p>
            Local features can work while hosted security and operations still need setup.
          </p>
        </div>
        <span className={`readinessSummary ${report?.ready ? "readinessReady" : ""}`}>
          {report?.ready ? "Ready to launch" : "Not production-ready"}
        </span>
      </div>

      {!report ? (
        <p className="emptyState">Readiness state is loading.</p>
      ) : (
        <div className="readinessGrid">
          {report.checks.map((check) => (
            <article className={check.passed ? "readinessPassed" : ""} key={check.key}>
              <span aria-hidden="true">{check.passed ? "✓" : "!"}</span>
              <div>
                <strong>{check.label}</strong>
                <p>{check.passed ? "Configured" : check.guidance}</p>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
