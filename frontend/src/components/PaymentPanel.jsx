import { useRef, useState } from "react";
import { newIdempotencyKey, request } from "../api.js";
import { useToast } from "./toast.jsx";
import { formatPrice } from "./ui.jsx";

export default function PaymentPanel({ order, onPaid, onChanged }) {
  const toast = useToast();
  const [method, setMethod] = useState("upi");
  const [simulate, setSimulate] = useState("success");
  const [busy, setBusy] = useState(false);
  const [payment, setPayment] = useState(null);
  const [error, setError] = useState("");
  // the same key is reused until we get an answer, so a double click cannot pay twice
  const keyRef = useRef(newIdempotencyKey());

  async function pay(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setPayment(null);
    try {
      const result = await request("/payments", {
        method: "POST",
        headers: { "Idempotency-Key": keyRef.current },
        body: { order_id: order.id, method, simulate },
      });
      keyRef.current = newIdempotencyKey(); // the next try is a new payment
      setPayment(result);
      if (result.status === "succeeded") {
        toast.success("Payment successful!");
        if (onPaid) onPaid(result);
      } else if (onChanged) {
        onChanged();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function cancelPayment() {
    setBusy(true);
    try {
      await request(`/payments/${payment.id}/cancel`, { method: "POST" });
      toast.info("Payment cancelled. You can start a new payment.");
      setPayment(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={pay}>
      <h2 style={{ marginTop: 0 }}>Payment</h2>
      <p>
        Amount to pay: <strong>{formatPrice(order.total_amount)}</strong>
      </p>
      <p className="small muted">This is a simulated payment. No card details are collected or stored.</p>

      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {payment && payment.status === "failed" && (
        <div className="alert alert-error" role="alert">
          The payment failed{payment.failure_reason ? ` (${payment.failure_reason})` : ""}. You can try again.
        </div>
      )}
      {payment && payment.status === "pending" && (
        <div className="alert alert-warn" role="status">
          The payment is pending.{" "}
          <button type="button" className="btn btn-secondary btn-small" onClick={cancelPayment} disabled={busy}>
            Cancel this payment
          </button>
        </div>
      )}

      <label htmlFor="method">Payment method</label>
      <select id="method" value={method} onChange={(e) => setMethod(e.target.value)}>
        <option value="upi">UPI</option>
        <option value="card">Card</option>
        <option value="netbanking">Net banking</option>
      </select>

      <label htmlFor="simulate">Demo only: result of this simulated payment</label>
      <select id="simulate" value={simulate} onChange={(e) => setSimulate(e.target.value)}>
        <option value="success">Succeeds</option>
        <option value="failure">Fails</option>
        <option value="pending">Stays pending</option>
      </select>

      <button className="btn btn-primary btn-block" disabled={busy || (payment && payment.status === "pending")}>
        {busy ? "Processing..." : `Pay ${formatPrice(order.total_amount)}`}
      </button>
    </form>
  );
}