import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { newIdempotencyKey, request } from "../api.js";
import { useCart } from "../cart.jsx";
import PaymentPanel from "../components/PaymentPanel.jsx";
import { useToast } from "../components/toast.jsx";
import { EmptyState, ErrorBox, Spinner, formatPrice } from "../components/ui.jsx";

// These match the shop's settings. The final amounts are confirmed when the order is placed.
const TAX_RATE = 0.18;
const FREE_SHIPPING_FROM = 1000;
const SHIPPING_FEE = 50;

function estimate(subtotal, discount) {
  const taxable = Math.max(0, subtotal - discount);
  const tax = Math.round(taxable * TAX_RATE * 100) / 100;
  const shipping = taxable >= FREE_SHIPPING_FROM ? 0 : SHIPPING_FEE;
  return { tax, shipping, total: Math.round((taxable + tax + shipping) * 100) / 100 };
}

const EMPTY = { full_name: "", phone: "", address_line: "", city: "", state: "", postal_code: "" };

export default function Checkout() {
  const navigate = useNavigate();
  const toast = useToast();
  const { refresh: refreshCart } = useCart();

  const [cart, setCart] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [shipping, setShipping] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [couponText, setCouponText] = useState("");
  const [coupon, setCoupon] = useState(null); // {code, discount_amount}
  const [couponError, setCouponError] = useState("");
  const [couponBusy, setCouponBusy] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [order, setOrder] = useState(null);
  // the same key is reused if the customer clicks again, so only one order is created
  const orderKey = useRef(newIdempotencyKey());

  useEffect(() => {
    request("/cart")
      .then(setCart)
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  function set(field, value) {
    setShipping((s) => ({ ...s, [field]: value }));
  }

  async function applyCoupon() {
    const code = couponText.trim().toUpperCase();
    if (code.length < 3) {
      setCouponError("Enter a coupon code.");
      return;
    }
    setCouponBusy(true);
    setCouponError("");
    try {
      const result = await request("/coupons/validate", { method: "POST", body: { code, cart_total: cart.subtotal } });
      setCoupon({ code: result.code, discount_amount: result.discount_amount });
      toast.success(`Coupon ${result.code} applied.`);
    } catch (e) {
      setCoupon(null);
      setCouponError(e.message);
    } finally {
      setCouponBusy(false);
    }
  }

  function validate() {
    const next = {};
    if (shipping.full_name.trim().length < 2) next.full_name = "Enter the full name (at least 2 characters).";
    if (!/^\+?[0-9]{10,15}$/.test(shipping.phone.trim())) next.phone = "Enter a phone number with 10 to 15 digits.";
    if (shipping.address_line.trim().length < 5) next.address_line = "Enter the full address (at least 5 characters).";
    if (shipping.city.trim().length < 2) next.city = "Enter the city.";
    if (shipping.state.trim().length < 2) next.state = "Enter the state.";
    if (!/^[A-Za-z0-9 -]{4,10}$/.test(shipping.postal_code.trim())) next.postal_code = "Enter a valid postal code (4 to 10 characters).";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function placeOrder(e) {
    e.preventDefault();
    setFormError("");
    if (!validate()) return;
    setPlacing(true);
    try {
      const created = await request("/orders", {
        method: "POST",
        headers: { "Idempotency-Key": orderKey.current },
        body: {
          shipping: Object.fromEntries(Object.entries(shipping).map(([k, v]) => [k, v.trim()])),
          coupon_code: coupon ? coupon.code : null,
        },
      });
      setOrder(created);
      refreshCart();
      window.scrollTo(0, 0);
    } catch (err) {
      setFormError(err.message);
      if (err.status === 400 && /coupon/i.test(err.message)) setCoupon(null);
    } finally {
      setPlacing(false);
    }
  }

  if (loading) return <Spinner label="Preparing checkout..." />;
  if (error) return <ErrorBox error={error} />;

  // step 2: the order exists, now pay
  if (order) {
    return (
      <div className="narrow" style={{ maxWidth: 560 }}>
        <h1>Almost done</h1>
        <div className="alert alert-warn">
          Order <strong>{order.order_number}</strong> is placed and your items are reserved for 30 minutes. Complete the payment to confirm it.
        </div>
        <PaymentPanel order={order} onPaid={() => navigate(`/orders/${order.id}/confirmation`)} />
        <p className="muted">
          Not ready? You can pay later from <Link to={`/orders/${order.id}`}>your order page</Link>.
        </p>
      </div>
    );
  }

  if (!cart || cart.items.length === 0) {
    return (
      <EmptyState title="Your cart is empty">
        <Link to="/" className="btn btn-primary">Start shopping</Link>
      </EmptyState>
    );
  }
  if (cart.has_issues) {
    return (
      <div className="alert alert-error">
        Some items in your cart have problems. <Link to="/cart">Go back to your cart</Link> to fix them.
      </div>
    );
  }

  const discount = coupon ? coupon.discount_amount : 0;
  const est = estimate(cart.subtotal, discount);

  return (
    <div>
      <h1>Checkout</h1>
      <div className="checkout-layout">
        <form className="card" onSubmit={placeOrder} noValidate>
          <h2 style={{ marginTop: 0 }}>Delivery address</h2>
          {formError && <div className="alert alert-error" role="alert">{formError}</div>}
          <div className="form-grid">
            <div>
              <label htmlFor="full_name">Full name</label>
              <input id="full_name" autoComplete="name" value={shipping.full_name} onChange={(e) => set("full_name", e.target.value)} />
              {errors.full_name && <div className="field-error">{errors.full_name}</div>}
            </div>
            <div>
              <label htmlFor="phone">Phone</label>
              <input id="phone" autoComplete="tel" value={shipping.phone} onChange={(e) => set("phone", e.target.value)} />
              {errors.phone && <div className="field-error">{errors.phone}</div>}
            </div>
            <div className="full">
              <label htmlFor="address_line">Address</label>
              <input id="address_line" autoComplete="street-address" value={shipping.address_line} onChange={(e) => set("address_line", e.target.value)} />
              {errors.address_line && <div className="field-error">{errors.address_line}</div>}
            </div>
            <div>
              <label htmlFor="city">City</label>
              <input id="city" value={shipping.city} onChange={(e) => set("city", e.target.value)} />
              {errors.city && <div className="field-error">{errors.city}</div>}
            </div>
            <div>
              <label htmlFor="state">State</label>
              <input id="state" value={shipping.state} onChange={(e) => set("state", e.target.value)} />
              {errors.state && <div className="field-error">{errors.state}</div>}
            </div>
            <div>
              <label htmlFor="postal_code">Postal code</label>
              <input id="postal_code" autoComplete="postal-code" value={shipping.postal_code} onChange={(e) => set("postal_code", e.target.value)} />
              {errors.postal_code && <div className="field-error">{errors.postal_code}</div>}
            </div>
          </div>
          <button className="btn btn-primary btn-block" disabled={placing}>
            {placing ? "Placing your order..." : "Continue to payment"}
          </button>
        </form>

        <aside className="card summary">
          <h2 style={{ marginTop: 0 }}>Order summary</h2>
          {cart.items.map((item) => (
            <div className="summary-row small" key={item.item_id}>
              <span>{item.name} × {item.quantity}</span>
              <span>{formatPrice(item.line_total)}</span>
            </div>
          ))}

          <label htmlFor="coupon">Coupon code</label>
          <div className="coupon-row">
            <input id="coupon" value={couponText} maxLength={30} onChange={(e) => setCouponText(e.target.value)} placeholder="Enter code" />
            <button type="button" className="btn btn-secondary" onClick={applyCoupon} disabled={couponBusy}>
              {couponBusy ? "..." : "Apply"}
            </button>
          </div>
          {couponError && <div className="field-error">{couponError}</div>}
          {coupon && <div className="small" style={{ color: "var(--ok)" }}>Coupon {coupon.code} applied</div>}

          <div style={{ marginTop: 12 }}>
            <div className="summary-row"><span>Subtotal</span><span>{formatPrice(cart.subtotal)}</span></div>
            {discount > 0 && <div className="summary-row"><span>Discount</span><span>− {formatPrice(discount)}</span></div>}
            <div className="summary-row"><span>Tax (estimated)</span><span>{formatPrice(est.tax)}</span></div>
            <div className="summary-row"><span>Shipping</span><span>{est.shipping === 0 ? "Free" : formatPrice(est.shipping)}</span></div>
            <div className="summary-row summary-total"><span>Total (estimated)</span><span>{formatPrice(est.total)}</span></div>
            <p className="small muted">The final amount is confirmed when you continue to payment.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}