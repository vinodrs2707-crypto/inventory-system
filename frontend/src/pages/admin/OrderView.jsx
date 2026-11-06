import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../../api.js";
import { useAuth } from "../../auth.jsx";
import { useToast } from "../../components/toast.jsx";
import { ErrorBox, Modal, Spinner, StatusBadge, Steps, formatDate, formatPrice } from "../../components/ui.jsx";

const STEPS = [
  ["pending", "Placed"],
  ["confirmed", "Confirmed"],
  ["processing", "Processing"],
  ["shipped", "Shipped"],
  ["delivered", "Delivered"],
];
const NEXT = {
  confirmed: ["processing", "Mark as processing"],
  processing: ["shipped", "Mark as shipped"],
  shipped: ["delivered", "Mark as delivered"],
};

export default function OrderView() {
  const { id } = useParams();
  const { isAdmin } = useAuth();
  const toast = useToast();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState("");

  const load = useCallback(() => {
    setError(null);
    return request(`/orders/${id}`).then(setOrder).catch(setError);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function advance(next) {
    setBusy(true);
    try {
      await request(`/orders/${id}/status`, { method: "PATCH", body: { status: next, note: note.trim() || null } });
      toast.success(`Order marked as ${next}.`);
      setNote("");
      await load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (reason.trim().length < 3) return setReasonError("Please give a reason (at least 3 characters).");
    setBusy(true);
    try {
      await request(`/orders/${id}/cancel`, { method: "POST", body: { reason: reason.trim() } });
      toast.success("Order cancelled.");
      setCancelOpen(false);
      setReason("");
      await load();
    } catch (e) {
      setReasonError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!order) return <Spinner label="Loading order..." />;

  const next = NEXT[order.status];

  return (
    <div>
      <p><Link to="/admin/orders">← All orders</Link></p>
      <div className="row-between">
        <h1>Order {order.order_number}</h1>
        <div><StatusBadge status={order.status} /> <StatusBadge status={order.payment_status} /></div>
      </div>
      <p className="muted">Customer #{order.user_id} · placed {formatDate(order.created_at)}</p>

      <Steps steps={STEPS} history={order.history} endings={[["cancelled", "Cancelled"]]} />

      {(next || (isAdmin && order.can_cancel)) && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Process this order</h3>
          {next && (
            <div className="filters-row">
              <div style={{ flex: 1 }}>
                <label htmlFor="note">Note for the history (optional)</label>
                <input id="note" value={note} maxLength={255} onChange={(e) => setNote(e.target.value)} />
              </div>
              <button className="btn btn-primary" onClick={() => advance(next[0])} disabled={busy}>
                {busy ? "Please wait..." : next[1]}
              </button>
            </div>
          )}
          {order.status === "pending" && <p className="muted">This order is waiting for payment, so it cannot be processed yet.</p>}
          {isAdmin && order.can_cancel && (
            <button className="btn btn-danger" onClick={() => { setReason(""); setReasonError(""); setCancelOpen(true); }}>
              Cancel order
            </button>
          )}
        </div>
      )}

      {order.payment_status === "refund_pending" && <div className="alert alert-warn">A refund for this cancelled order is pending.</div>}
      {order.refund_due > 0 && <div className="alert alert-warn">Refund due for cancelled items: {formatPrice(order.refund_due)}</div>}
      {order.cancel_reason && <p className="muted">Cancellation reason: {order.cancel_reason}</p>}

      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Product</th><th>Price</th><th>Qty</th><th>Total</th></tr></thead>
          <tbody>
            {order.items.map((i) => (
              <tr key={i.id}>
                <td>{i.product_name} <span className="small muted">#{i.product_id}</span></td>
                <td>{formatPrice(i.unit_price)}</td>
                <td>{i.quantity}{i.cancelled_quantity > 0 && <div className="small field-error">{i.cancelled_quantity} cancelled</div>}</td>
                <td>{formatPrice(i.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="detail" style={{ marginTop: 16 }}>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Delivery address</h3>
          <div>{order.shipping.full_name}</div>
          <div className="muted">{order.shipping.address_line}, {order.shipping.city}, {order.shipping.state} {order.shipping.postal_code}</div>
          <div className="muted">{order.shipping.phone}</div>
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Payment summary</h3>
          <div className="summary-row"><span>Subtotal</span><span>{formatPrice(order.subtotal)}</span></div>
          {order.discount_amount > 0 && <div className="summary-row"><span>Discount {order.coupon_code ? `(${order.coupon_code})` : ""}</span><span>− {formatPrice(order.discount_amount)}</span></div>}
          <div className="summary-row"><span>Tax</span><span>{formatPrice(order.tax_amount)}</span></div>
          <div className="summary-row"><span>Shipping</span><span>{formatPrice(order.shipping_amount)}</span></div>
          <div className="summary-row summary-total"><span>Total</span><span>{formatPrice(order.total_amount)}</span></div>
        </div>
      </div>

      <h2>History</h2>
      <ul className="timeline">
        {[...order.history].reverse().map((h, index) => (
          <li key={index}>
            <StatusBadge status={h.status} /> <span className="small muted">{formatDate(h.created_at)}</span>
            {h.note && <div>{h.note}</div>}
          </li>
        ))}
      </ul>

      {cancelOpen && (
        <Modal title="Cancel this order?" onClose={busy ? () => {} : () => setCancelOpen(false)}>
          <p>Stock goes back to the shelf{order.payment_status === "paid" ? " and a refund is started" : ""}. The customer is notified.</p>
          <label htmlFor="reason">Reason</label>
          <textarea id="reason" rows={3} maxLength={255} value={reason} onChange={(e) => setReason(e.target.value)} />
          {reasonError && <div className="field-error">{reasonError}</div>}
          <div className="row-end">
            <button className="btn btn-secondary" onClick={() => setCancelOpen(false)} disabled={busy}>Keep order</button>
            <button className="btn btn-danger" onClick={cancel} disabled={busy}>{busy ? "Please wait..." : "Cancel order"}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}