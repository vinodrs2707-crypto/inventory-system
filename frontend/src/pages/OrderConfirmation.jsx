import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../api.js";
import PaymentPanel from "../components/PaymentPanel.jsx";
import { ErrorBox, Spinner, StatusBadge, formatPrice } from "../components/ui.jsx";

export default function OrderConfirmation() {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setError(null);
    return request(`/orders/${id}`).then(setOrder).catch(setError);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!order) return <Spinner label="Loading your order..." />;

  if (order.status === "pending") {
    return (
      <div className="narrow" style={{ maxWidth: 560 }}>
        <h1>Waiting for payment</h1>
        <p>Order {order.order_number} is not paid yet.</p>
        <PaymentPanel order={order} onPaid={load} onChanged={load} />
      </div>
    );
  }

  return (
    <div className="narrow" style={{ maxWidth: 640 }}>
      <div className="card center-box">
        <div style={{ fontSize: "3rem", color: "var(--ok)" }} aria-hidden="true">✓</div>
        <h1>Thank you for your order!</h1>
        <p>
          Your order <strong>{order.order_number}</strong> is <StatusBadge status={order.status} />. We will keep you posted by notification.
        </p>
        <p>
          Total paid: <strong>{formatPrice(order.total_amount)}</strong>
        </p>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Delivering to</h3>
        <div>{order.shipping.full_name}</div>
        <div className="muted">
          {order.shipping.address_line}, {order.shipping.city}, {order.shipping.state} {order.shipping.postal_code}
        </div>
        <div className="muted">{order.shipping.phone}</div>
      </div>

      <div className="row-end">
        <Link to="/" className="btn btn-secondary">Keep shopping</Link>
        <Link to={`/orders/${order.id}`} className="btn btn-primary">Track this order</Link>
      </div>
    </div>
  );
}