import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { request } from "../api.js";
import { useToast } from "../components/toast.jsx";
import { EmptyState, ErrorBox, Pagination, Spinner, formatDate } from "../components/ui.jsx";
import { useNotifications } from "../notifications.jsx";

const PAGE_SIZE = 15;

export default function Notifications() {
  const navigate = useNavigate();
  const toast = useToast();
  const { refresh } = useNotifications();
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setError(null);
    request("/notifications", { params: { page, page_size: PAGE_SIZE, unread_only: unreadOnly ? "true" : "" } })
      .then(setData)
      .catch(setError);
  }, [page, unreadOnly, reloadKey]);

  async function open(n) {
    if (!n.is_read) {
      try {
        await request(`/notifications/${n.id}/read`, { method: "PATCH" });
      } catch (e) {
        toast.error(e.message);
        return;
      }
      refresh();
    }
    if (n.data && n.data.order_id) navigate(`/orders/${n.data.order_id}`);
    else setReloadKey((k) => k + 1);
  }

  async function markAll() {
    setBusy(true);
    try {
      const result = await request("/notifications/read-all", { method: "POST" });
      toast.success(result.marked_read ? `${result.marked_read} marked as read.` : "Everything was already read.");
      refresh();
      setReloadKey((k) => k + 1);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorBox error={error} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!data) return <Spinner label="Loading notifications..." />;

  return (
    <div>
      <div className="row-between">
        <h1>Notifications</h1>
        <div>
          <label className="check" style={{ display: "inline-flex", marginRight: 12 }}>
            <input type="checkbox" checked={unreadOnly} onChange={(e) => { setUnreadOnly(e.target.checked); setPage(1); }} />
            Unread only
          </label>
          <button className="btn btn-secondary btn-small" onClick={markAll} disabled={busy || data.unread_count === 0}>
            Mark all as read
          </button>
        </div>
      </div>
      <p className="muted">{data.unread_count} unread</p>

      {data.items.length === 0 ? (
        <EmptyState title={unreadOnly ? "No unread notifications" : "No notifications yet"}>
          We will let you know here when something happens with your orders.
        </EmptyState>
      ) : (
        data.items.map((n) => (
          <button key={n.id} className={`notif ${n.is_read ? "" : "unread"}`} onClick={() => open(n)}>
            <span className="mark" aria-hidden="true" />
            <span>
              <div className="notif-title">{n.title}{!n.is_read && <span className="sr-only"> (unread)</span>}</div>
              <div>{n.message}</div>
              <div className="small muted">{formatDate(n.created_at)}</div>
            </span>
          </button>
        ))
      )}
      <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
    </div>
  );
}