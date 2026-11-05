import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api.js";
import { useCart } from "../cart.jsx";
import { useToast } from "../components/toast.jsx";
import { EmptyState, ErrorBox, Spinner, formatDate } from "../components/ui.jsx";

export default function Wishlist() {
  const toast = useToast();
  const { refresh: refreshCart } = useCart();
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    setError(null);
    return request("/wishlist").then(setItems).catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function remove(item) {
    setBusyId(item.item_id);
    try {
      await request(`/wishlist/items/${item.item_id}`, { method: "DELETE" });
      toast.success("Removed from your wishlist.");
      await load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function moveToCart(item) {
    setBusyId(item.item_id);
    try {
      await request("/cart/items", { method: "POST", body: { product_id: item.product_id, quantity: 1 } });
      await request(`/wishlist/items/${item.item_id}`, { method: "DELETE" });
      toast.success("Moved to your cart.");
      refreshCart();
      await load();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!items) return <Spinner label="Loading your wishlist..." />;
  if (items.length === 0) {
    return (
      <EmptyState title="Your wishlist is empty">
        Save products you like and they will show up here. <Link to="/">Browse the shop</Link>
      </EmptyState>
    );
  }

  return (
    <div>
      <h1>Your wishlist</h1>
      {items.map((item) => (
        <div className="card row-between" key={item.item_id}>
          <div>
            <Link to={`/products/${item.product_id}`}><strong>{item.product_name}</strong></Link>
            <div className="small muted">Saved on {formatDate(item.added_at)}</div>
          </div>
          <div>
            <button className="btn btn-primary btn-small" onClick={() => moveToCart(item)} disabled={busyId === item.item_id}>
              Move to cart
            </button>{" "}
            <button className="btn btn-secondary btn-small" onClick={() => remove(item)} disabled={busyId === item.item_id}>
              Remove
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}