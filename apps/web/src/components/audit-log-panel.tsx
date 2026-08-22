import type { AuditLog } from "@/lib/types";

interface AuditLogPanelProps {
  records: AuditLog[];
  visible: boolean;
}

export function AuditLogPanel({ records, visible }: AuditLogPanelProps) {
  if (!visible) return null;
  return (
    <section className="panel auditPanel" id="audit">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Accountability</span>
          <h2>Operator audit log</h2>
          <p>Successful and rejected control-plane mutations, without request bodies or secrets.</p>
        </div>
        <span className="panelMeta">Latest {records.length}</span>
      </div>
      <div className="auditList">
        {records.length === 0 ? (
          <p className="mutedText">No operator mutations recorded yet.</p>
        ) : (
          records.map((record) => (
            <article className="auditRow" key={record.id}>
              <time>{new Date(record.created_at).toLocaleString()}</time>
              <div>
                <strong>{record.action}</strong>
                <small>
                  {record.actor_subject} · {record.actor_role}
                </small>
              </div>
              <span className={record.status_code < 400 ? "auditSuccess" : "auditFailure"}>
                HTTP {record.status_code}
              </span>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
