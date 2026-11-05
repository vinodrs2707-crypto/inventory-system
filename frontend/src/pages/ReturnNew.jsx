import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { request } from "../api.js";
import { useToast } from "../components/toast.jsx";
import { ErrorBox, Spinner, formatDate, parseUtc } from "../components/ui.jsx";

const REASONS = [
  ["damaged", "It arrived damaged"],
  ["defective", "It is defective or not working"],
  ["wrong_item", "I received the wrong item"],
  ["not_as_described", "It is not as described"],
  ["changed_mind", "I changed my mind"],
  ["other", "Another reason"],
];
const RETURN_DAYS = 7;

export default function ReturnNew() {
  const [params] = useSearchParams();
  const orderId = Number(params.get("order"));
  const navigate = useNavigate();
  const toast = useToast();

  const [order, setOrder] = useState(null);
  const [used, setUsed] = useState({});
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState({});
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!orderId) {
      setError({ message: "No order was chosen. Open one of your delivered orders and click Request a return." });
      return;
    }
    Promise.all([request(`/orders/${orderId}`), request("/returns/my-returns", { params: { page_size: 50 } })])
      .then(async ([o, list]) => {
        // how many of each item are already in another return
        const active = list.items.filter((r) => r.order_id === orderId && !["rejected", "declined"].includes(r.status));
        const details = await Promise.all(active.map((r) => request(`/returns/${r.id}`)));
        const map = {};
        details.forEach((d) => d.items.forEach((i) => { map[i.order_item_id] = (map[i.order_item_id] || 0) + i.quantity; }));
        setUsed(map);
        setOrder(o);
      })
      .catch(setError);
  }, [orderId]);

  function toggle(item, remaining, on) {
    setSelected((s) => {
      const next = { ...s };
      if (on) next[item.id] = { quantity: 1, reason: "", comment: "" };
      else delete next[item.id];
      return next;
    });
  }

  function change(itemId, field, value) {
    setSelected((s) => ({ ...s, [itemId]: { ...s[itemId], [field]: value } }));
  }

  async function submit(e) {
    e.preventDefault();
    setFormError("");
    const chosen = Object.entries(selected);
    const next = {};
    if (chosen.length === 0) next.none = "Choose at least one item to return.";
    chosen.forEach(([id, s]) => {
      if (!s.reason) next[id] = "Please tell us why you are returning this item.";
    });
    setErrors(next);
    if (Object.keys(next).length) return;

    setBusy(true);
    try {
      const created = await request("/returns", {
        method: "POST",
        body: {
          order_id: orderId,
          items: chosen.map(([id, s]) => ({
            order_item_id: Number(id),
            quantity: Number(s.quantity),
            reason: s.reason,
            comment: s.comment.trim() || null,
          })),
        },
      });
      toast.success("Your return request was sent.");
      navigate(`/returns/${created.id}`, { replace: true });
    } catch (err) {
      setFormError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorBox error={error} />;
  if (!order) return <Spinner label="Loading your order..." />;

  if (order.status !== "delivered") {
    return (
      <div className="alert alert-warn">
        Only delivered orders can be returned. Order {order.order_number} is {order.status}. <Link to={`/orders/${order.id}`}>Back to the order</Link>
      </div>
    );
  }

  const deliveredEntry = order.history.find((h) => h.status === "delivered");
  const deadline = deliveredEntry ? new Date(parseUtc(deliveredEntry.created_at).getTime() + RETURN_DAYS * 86400000) : null;
  const expired = deadline && deadline < new Date();

  const rows = order.items
    .map((i) => ({ item: i, remaining: i.quantity - i.cancelled_quantity - (used[i.id] || 0) }))
    .filter((r) => r.remaining > 0);

  return (
    <div className="narrow" style={{ maxWidth: 680 }}>
      <h1>Return items from order {order.order_number}</h1>
      {deadline && (
        <p className={expired ? "field-error" : "muted"}>
          {expired
            ? `The return period ended on ${formatDate(deadline.toISOString())}.`
            : `You can return items until ${formatDate(deadline.toISOString())} (${RETURN_DAYS} days after delivery).`}
        </p>
      )}

      {rows.length === 0 ? (
        <div className="alert alert-warn">There is nothing left to return from this order. <Link to="/returns">See your returns</Link></div>
      ) : (
        <form onSubmit={submit} noValidate>
          {formError && <div className="alert alert-error" role="alert">{formError}</div>}
          {errors.none && <div className="alert alert-error" role="alert">{errors.none}</div>}

          <div className="card">
            {rows.map(({ item, remaining }) => {
              const s = selected[item.id];
              return (
                <div className={`return-item ${s ? "" : "off"}`} key={item.id}>
                  <label className="check">
                    <input type="checkbox" checked={Boolean(s)} onChange={(e) => toggle(item, remaining, e.target.checked)} />
                    <strong>{item.product_name}</strong> <span className="muted">(you can return up to {remaining})</span>
                  </label>
                  {s && (
                    <div className="form-grid">
                      <div>
                        <label htmlFor={`q${item.id}`}>How many?</label>
                        <select id={`q${item.id}`} value={s.quantity} onChange={(e) => change(item.id, "quantity", e.target.value)}>
                          {Array.from({ length: remaining }, (_, n) => (
                            <option key={n + 1} value={n + 1}>{n + 1}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`r${item.id}`}>Reason</label>
                        <select id={`r${item.id}`} value={s.reason} onChange={(e) => change(item.id, "reason", e.target.value)}>
                          <option value="">Choose a reason</option>
                          {REASONS.map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                          ))}
                        </select>
                        {errors[item.id] && <div className="field-error">{errors[item.id]}</div>}
                      </div>
                      <div className="full">
                        <label htmlFor={`c${item.id}`}>Comment (optional)</label>
                        <textarea id={`c${item.id}`} rows={2} maxLength={500} value={s.comment} onChange={(e) => change(item.id, "comment", e.target.value)} />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="row-end">
            <Link to={`/orders/${order.id}`} className="btn btn-secondary">Back</Link>
            <button className="btn btn-primary" disabled={busy}>{busy ? "Sending..." : "Send return request"}</button>
          </div>
        </form>
      )}
    </div>
  );
}