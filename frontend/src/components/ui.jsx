const money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

export function formatPrice(value) {
  return money.format(Number(value || 0));
}

// the server sends UTC times without a "Z"; add it so the browser shows local time
export function parseUtc(value) {
  if (!value) return null;
  const text = /[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  return new Date(text);
}

export function formatDate(value) {
  const d = parseUtc(value);
  return d ? d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "";
}

export function Spinner({ label = "Loading..." }) {
  return (
    <div className="center-box" role="status">
      <div className="spinner" />
      <p className="muted">{label}</p>
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="alert alert-error" role="alert">
      <strong>{error.message || "Something went wrong."}</strong>
      {error.correlationId && <div className="small muted">Reference: {error.correlationId}</div>}
      {onRetry && (
        <div>
          <button className="btn btn-secondary btn-small" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

export function EmptyState({ title, children }) {
  return (
    <div className="center-box">
      <h3>{title}</h3>
      <div className="muted">{children}</div>
    </div>
  );
}

export function Stars({ value = 0, count }) {
  const filled = Math.round(value);
  return (
    <span className="stars" aria-label={`${value} out of 5 stars`}>
      {"★".repeat(filled)}
      {"☆".repeat(5 - filled)}
      {count !== undefined && <span className="muted small"> ({count})</span>}
    </span>
  );
}

export function Pagination({ page, pageSize, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav className="pagination" aria-label="Pages">
      <button className="btn btn-secondary btn-small" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {pages}
      </span>
      <button className="btn btn-secondary btn-small" disabled={page >= pages} onClick={() => onChange(page + 1)}>
        Next
      </button>
    </nav>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel = "Confirm", danger = false, busy = false, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label={title} onClick={onCancel}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="row-end">
          <button className="btn btn-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className={`btn ${danger ? "btn-danger" : "btn-primary"}`} onClick={onConfirm} disabled={busy}>
            {busy ? "Please wait..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}