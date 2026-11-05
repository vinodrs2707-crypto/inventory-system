import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api.js";
import { useCart } from "../cart.jsx";
import { useToast } from "../components/toast.jsx";
import { ConfirmDialog, EmptyState, ErrorBox, Spinner, formatPrice } from "../components/ui.jsx";

export default function Cart() {
  const toast = useToast();
  const { setCount } = useCart();
  const [cart, setCart] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [removing, setRemoving] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    return request("/cart")
      .then((c) => {
        setCart(c);
        setCount(c.item_count);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [setCount]);

  useEffect(() => {
    load();
  }, [load]);

  async function changeQuantity(item, quantity) {
    if (quantity < 1 || quantity > 10) return;
    setBusyId(item.item_id);
    try {
      const updated = await request(`/cart/items/${item.item_id}`, { method: "PATCH", body: { quantity } });
      setCart(updated);
      setCount(updated.item_count);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function confirmRemove() {
    setBusyId(removing.item_id);
    try {
      await request(`/cart/items/${removing.item_id}`, { method: "DELETE" });
      toast.success("Item removed.");
      setRemoving(null);
      await load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusyId(null);
    }
  }

  if (loading && !cart) return <Spinner label="Loading your cart..." />;
  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!cart || cart.items.length === 0) {
    return (
      <EmptyState title="Your cart is empty">
        <Link to="/" className="btn btn-primary">Start shopping</Link>
      </EmptyState>
    );
  }

  return (
    <div>
      <h1>Your cart</h1>
      <div className="cart-layout">
        <div>
          {cart.items.map((item) => {
            const busy = busyId === item.item_id;
            const maxed = item.quantity >= 10 || (item.available_quantity != null && item.quantity >= item.available_quantity);
            return (
              <div className={`card cart-row ${item.issue ? "has-issue" : ""}`} key={item.item_id}>
                <div>
                  <Link to={`/products/${item.product_id}`}><strong>{item.name}</strong></Link>
                  <div className="muted">{formatPrice(item.unit_price)} each</div>
                  {item.price_changed && <span className="badge badge-warn">Price updated</span>}
                  {item.issue && <div className="field-error">{item.issue}</div>}
                </div>
                <div className="qty">
                  <button onClick={() => changeQuantity(item, item.quantity - 1)} disabled={busy || item.quantity <= 1} aria-label="Decrease quantity">−</button>
                  <span aria-live="polite">{item.quantity}</span>
                  <button onClick={() => changeQuantity(item, item.quantity + 1)} disabled={busy || maxed} aria-label="Increase quantity">+</button>
                </div>
                <strong>{formatPrice(item.line_total)}</strong>
                <button className="btn btn-secondary btn-small" onClick={() => setRemoving(item)} disabled={busy}>
                  Remove
                </button>
              </div>
            );
          })}
        </div>

        <aside className="card summary">
          <h2 style={{ marginTop: 0 }}>Summary</h2>
          <div className="summary-row"><span>Items</span><span>{cart.item_count}</span></div>
          <div className="summary-row summary-total"><span>Subtotal</span><span>{formatPrice(cart.subtotal)}</span></div>
          <p className="small muted">Coupons, tax and shipping are added at checkout.</p>
          {cart.has_issues ? (
            <>
              <div className="alert alert-error">Please fix the items marked in red before checking out.</div>
              <button className="btn btn-primary btn-block" disabled>Proceed to checkout</button>
            </>
          ) : (
            <Link to="/checkout" className="btn btn-primary btn-block" style={{ textAlign: "center" }}>
              Proceed to checkout
            </Link>
          )}
        </aside>
      </div>

      <ConfirmDialog
        open={Boolean(removing)}
        title="Remove this item?"
        message={removing ? `${removing.name} will be removed from your cart.` : ""}
        confirmLabel="Remove"
        danger
        busy={busyId !== null}
        onConfirm={confirmRemove}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}