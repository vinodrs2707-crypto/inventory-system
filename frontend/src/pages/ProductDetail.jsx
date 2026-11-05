import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { request } from "../api.js";
import { useAuth } from "../auth.jsx";
import Reviews from "../components/Reviews.jsx";
import { useCart } from "../cart.jsx";
import { useToast } from "../components/toast.jsx";
import { ErrorBox, Spinner, Stars, formatPrice } from "../components/ui.jsx";

export default function ProductDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const { refresh: refreshCart } = useCart();

  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState(null);
  const [imageFailed, setImageFailed] = useState(false);

  function load() {
    setLoading(true);
    setError(null);
    request(`/products/${id}`)
      .then((p) => {
        setProduct(p);
        setImageFailed(false);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(load, [id, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function needLogin() {
    toast.info("Please sign in first.");
    navigate("/login", { state: { from: location } });
  }

  async function addToCart() {
    if (!user) return needLogin();
    setBusy(true);
    try {
      await request("/cart/items", { method: "POST", body: { product_id: product.id, quantity } });
      toast.success(`Added ${quantity} to your cart.`);
      refreshCart();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function addToWishlist() {
    if (!user) return needLogin();
    setBusy(true);
    try {
      await request("/wishlist/items", { method: "POST", body: { product_id: product.id } });
      toast.success("Saved to your wishlist.");
    } catch (e) {
      if (e.status === 409) toast.info(e.message);
      else toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading && !product) return <Spinner label="Loading product..." />;
  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!product) return null;

  const rating = summary ? summary.average : product.rating_average;
  const ratingCount = summary ? summary.count : product.rating_count;
  const maxQty = Math.max(1, Math.min(10, product.stock_quantity || 1));
  const specs = Object.entries(product.specifications || {});

  return (
    <div>
      <div className="detail">
        <div className="detail-image card">
          {product.image_url && !imageFailed ? (
            <img src={product.image_url} alt={product.name} onError={() => setImageFailed(true)} />
          ) : (
            <span className="placeholder big" aria-hidden="true">{product.name.slice(0, 1).toUpperCase()}</span>
          )}
        </div>

        <div className="detail-info">
          <div className="small muted">{product.brand} · {product.category}</div>
          <h1>{product.name}</h1>
          <Stars value={rating} count={ratingCount} />
          <div className="price big-price">{formatPrice(product.price)}</div>

          {product.in_stock ? (
            <span className={`badge ${product.stock_quantity <= 5 ? "badge-warn" : "badge-ok"}`}>
              {product.stock_quantity <= 5 ? `Only ${product.stock_quantity} left` : "In stock"}
            </span>
          ) : (
            <span className="badge badge-danger">Out of stock</span>
          )}

          <p>{product.description}</p>

          <div className="buy-row">
            <label htmlFor="qty">Quantity</label>
            <input
              id="qty"
              type="number"
              min="1"
              max={maxQty}
              value={quantity}
              disabled={!product.in_stock}
              onChange={(e) => setQuantity(Math.max(1, Math.min(maxQty, Number(e.target.value) || 1)))}
            />
            <button className="btn btn-primary" disabled={!product.in_stock || busy} onClick={addToCart}>
              Add to cart
            </button>
            <button className="btn btn-secondary" disabled={busy} onClick={addToWishlist}>
              Save to wishlist
            </button>
          </div>
        </div>
      </div>

      {specs.length > 0 && (
        <section>
          <h2>Specifications</h2>
          <table className="specs">
            <tbody>
              {specs.map(([key, value]) => (
                <tr key={key}>
                  <th>{key}</th>
                  <td>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <Reviews productId={product.id} onSummary={setSummary} />
    </div>
  );
}