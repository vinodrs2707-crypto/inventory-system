import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../api.js";
import PaymentPanel from "../components/PaymentPanel.jsx";
import { useToast } from "../components/toast.jsx";
import { ErrorBox, Spinner, StatusBadge, formatDate, formatPrice } from "../components/ui.jsx";

const STEPS = [
  ["pending", "Placed"],
  ["confirmed", "Confirmed"],
  ["processing", "Processing"],
  ["shipped", "Shipped"],
  ["delivered", "Delivered"],
];

function Timeline({ order }) {
  const reached = new Map();
  order.history.forEach((h) => {
    if (!reached.has(h.status)) reached.set(h.status, h.created_at);
  });
  return (
    <div className="steps" aria-label="Delivery progress">
      {STEPS.map(([key, label]) => (
        <div key={key} className={`step ${reached.has(key) ? "done" : ""}`}>
          <div className="dot">{reached.has(key) ? "✓" : ""}</div>
          <div>{label}</div>
          <div className="when">{reached.has(key) ? formatDate(reached.get(key)) : ""}</div>
        </div>
      ))}
      {order.status === "cancelled" && (
        <div className="step cancelled">
          <div className="dot">×</div>
          <div>Cancelled</div>
          <div className="when">{formatDate(reached.get("cancelled"))}</div>
        </div>
      )}
    </div>
  );
}

export default function OrderDetail() {
  const { id } = useParams();
  const toast = useToast();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState("");

  const [itemsOpen, setItemsOpen] = useState(false);
  const [quantities, setQuantities] = useState({});
  const [itemsError, setItemsError] = useState("");

  const load = useCallback(() => {
    setError(null);
    return request(`/orders/${id}`).then(setOrder).catch(setError);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function cancelOrder() {
    const text = reason.trim();
    if (text && text.length < 3) {
      setReasonError("Please write at least 3 characters, or leave it empty.");
      return;
    }
    setBusy(true);
    try {
      await request(`/orders/${id}/cancel`, { method: "POST", body: { reason: text || "Cancelled by customer" } });
      toast.success("Your order was cancelled.");
      setCancelOpen(false);
      setReason("");
      await load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  function openItems() {
    setQuantities({});
    setItemsError("");
    setItemsOpen(true);
  }

  async function cancelItems() {
    const items = Object.entries(quantities)
      .filter(([, qty]) => qty > 0)
      .map(([item_id, quantity]) => ({ item_id: Number(item_id), quantity }));
    if (items.length === 0) {
      setItemsError("Choose at least one item to cancel.");
      return;
    }
    setBusy(true);
    try {
      await request(`/orders/${id}/cancel-items`, {
        method: "POST",
        body: { items, reason: "Items cancelled by customer" },
      });
      toast.success("The selected items were cancelled. Your refund is being processed.");
      setItemsOpen(false);
      await load();
    } catch (e) {
      setItemsError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!order) return <Spinner label="Loading your order..." />;

  const canCancelItems = order.status === "confirmed" || order.status === "processing";

  return (
    <div>
      <div className="row-between">
        <h1>Order {order.order_number}</h1>
        <div>
          <StatusBadge status={order.status} /> <StatusBadge status={order.payment_status} />
        </div>
      </div>
      <p className="muted">Placed on {formatDate(order.created_at)}</p>

      <Timeline order={order} />

      {order.status === "pending" && (
        <div style={{ maxWidth: 560 }}>
          <div className="alert alert-warn">This order is waiting for payment. Unpaid orders are cancelled automatically after 30 minutes.</div>
          <PaymentPanel order={order} onPaid={load} onChanged={load} />
        </div>
      )}

      {order.payment_status === "refund_pending" && (
        <div className="alert alert-warn">Your refund is being processed.</div>
      )}
      {order.refund_due > 0 && order.status !== "cancelled" && (
        <div className="alert alert-warn">Refund due for the items you cancelled: {formatPrice(order.refund_due)}</div>
      )}
      {order.cancel_reason && <p className="muted">Cancellation reason: {order.cancel_reason}</p>}

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>Product</th><th>Price</th><th>Qty</th><th>Total</th></tr>
          </thead>
          <tbody>
            {order.items.map((i) => (
              <tr key={i.id}>
                <td><Link to={`/products/${i.product_id}`}>{i.product_name}</Link></td>
                <td>{formatPrice(i.unit_price)}</td>
                <td>
                  {i.quantity}
                  {i.cancelled_quantity > 0 && <div className="small field-error">{i.cancelled_quantity} cancelled</div>}
                </td>
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
          <div className="muted">
            {order.shipping.address_line}, {order.shipping.city}, {order.shipping.state} {order.shipping.postal_code}
          </div>
          <div className="muted">{order.shipping.phone}</div>
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Payment summary</h3>
          <div className="summary-row"><span>Subtotal</span><span>{formatPrice(order.subtotal)}</span></div>
          {order.discount_amount > 0 && (
            <div className="summary-row"><span>Discount {order.coupon_code ? `(${order.coupon_code})` : ""}</span><span>− {formatPrice(order.discount_amount)}</span></div>
          )}
          <div className="summary-row"><span>Tax</span><span>{formatPrice(order.tax_amount)}</span></div>
          <div className="summary-row"><span>Shipping</span><span>{order.shipping_amount === 0 ? "Free" : formatPrice(order.shipping_amount)}</span></div>
          <div className="summary-row summary-total"><span>Total</span><span>{formatPrice(order.total_amount)}</span></div>
        </div>
      </div>

      <div className="row-end">
        {order.status === "delivered" && (
          <Link to={`/returns/new?order=${order.id}`} className="btn btn-secondary">Request a return</Link>
        )}
        {canCancelItems && (
          <button className="btn btn-secondary" onClick={openItems}>Cancel some items</button>
        )}
        {order.can_cancel && (
          <button className="btn btn-danger" onClick={() => { setReason(""); setReasonError(""); setCancelOpen(true); }}>
            Cancel order
          </button>
        )}
      </div>

      <h2>Order history</h2>
      <ul className="timeline">
        {[...order.history].reverse().map((h, index) => (
          <li key={index}>
            <StatusBadge status={h.status} /> <span className="small muted">{formatDate(h.created_at)}</span>
            {h.note && <div>{h.note}</div>}
          </li>
        ))}
      </ul>

      {cancelOpen && (
        <div className="overlay" role="dialog" aria-modal="true" aria-label="Cancel order" onClick={() => !busy && setCancelOpen(false)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>Cancel this order?</h3>
            <p>Your items will go back to stock{order.payment_status === "paid" ? " and your payment will be refunded" : ""}.</p>
            <label htmlFor="reason">Reason (optional)</label>
            <textarea id="reason" rows={3} maxLength={255} value={reason} onChange={(e) => setReason(e.target.value)} />
            {reasonError && <div className="field-error">{reasonError}</div>}
            <div className="row-end">
              <button className="btn btn-secondary" onClick={() => setCancelOpen(false)} disabled={busy}>Keep order</button>
              <button className="btn btn-danger" onClick={cancelOrder} disabled={busy}>{busy ? "Please wait..." : "Cancel order"}</button>
            </div>
          </div>
        </div>
      )}

      {itemsOpen && (
        <div className="overlay" role="dialog" aria-modal="true" aria-label="Cancel items" onClick={() => !busy && setItemsOpen(false)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>Cancel some items</h3>
            <p className="small muted">Choose how many of each item to cancel. Cancelling everything cancels the whole order.</p>
            {order.items.map((i) => {
              const remaining = i.quantity - i.cancelled_quantity;
              if (remaining <= 0) return null;
              return (
                <div className="row-between" key={i.id} style={{ marginBottom: 8 }}>
                  <span>{i.product_name}</span>
                  <select
                    aria-label={`Quantity of ${i.product_name} to cancel`}
                    style={{ width: 90 }}
                    value={quantities[i.id] || 0}
                    onChange={(e) => setQuantities((q) => ({ ...q, [i.id]: Number(e.target.value) }))}
                  >
                    {Array.from({ length: remaining + 1 }, (_, n) => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                </div>
              );
            })}
            {itemsError && <div className="field-error">{itemsError}</div>}
            <div className="row-end">
              <button className="btn btn-secondary" onClick={() => setItemsOpen(false)} disabled={busy}>Close</button>
              <button className="btn btn-danger" onClick={cancelItems} disabled={busy}>{busy ? "Please wait..." : "Cancel selected items"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}