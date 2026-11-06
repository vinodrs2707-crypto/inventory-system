import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api.js";
import { useAuth } from "../../auth.jsx";
import { BarChart, ErrorBox, Spinner, StatCard, formatPrice } from "../../components/ui.jsx";

const DAY = 86400000;
const isoDate = (d) => d.toISOString().slice(0, 10);

export default function Dashboard() {
  const { isAdmin } = useAuth();
  const [from, setFrom] = useState(isoDate(new Date(Date.now() - 29 * DAY)));
  const [to, setTo] = useState(isoDate(new Date()));
  const [granularity, setGranularity] = useState("day");
  const [rangeError, setRangeError] = useState("");
  const [applied, setApplied] = useState({ from, to, granularity });
  const [reloadKey, setReloadKey] = useState(0);

  const [sales, setSales] = useState(null);
  const [salesError, setSalesError] = useState(null);
  const [orders, setOrders] = useState(null);
  const [ordersError, setOrdersError] = useState(null);
  const [inventory, setInventory] = useState(null);
  const [inventoryError, setInventoryError] = useState(null);

  useEffect(() => {
    if (!isAdmin) return;
    setSales(null);
    setOrders(null);
    setSalesError(null);
    setOrdersError(null);
    const range = { date_from: applied.from, date_to: applied.to };
    request("/analytics/sales", { params: { ...range, granularity: applied.granularity } })
      .then(setSales)
      .catch(setSalesError);
    request("/analytics/orders", { params: range }).then(setOrders).catch(setOrdersError);
  }, [applied, isAdmin, reloadKey]);

  useEffect(() => {
    setInventory(null);
    setInventoryError(null);
    request("/analytics/inventory").then(setInventory).catch(setInventoryError);
  }, [reloadKey]);

  function apply(e) {
    e.preventDefault();
    if (!from || !to) return setRangeError("Choose both dates.");
    if (from > to) return setRangeError("The start date cannot be after the end date.");
    if ((new Date(to) - new Date(from)) / DAY > 366) return setRangeError("The range can be at most 366 days.");
    setRangeError("");
    setApplied({ from, to, granularity });
  }

  const retry = () => setReloadKey((k) => k + 1);

  return (
    <div>
      <h1>Dashboard</h1>

      {isAdmin && (
        <form className="filters-row" onSubmit={apply} noValidate>
          <div>
            <label htmlFor="from">From</label>
            <input id="from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div>
            <label htmlFor="to">To</label>
            <input id="to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
          <div>
            <label htmlFor="gran">Group sales by</label>
            <select id="gran" value={granularity} onChange={(e) => setGranularity(e.target.value)}>
              <option value="day">Day</option>
              <option value="week">Week</option>
              <option value="month">Month</option>
            </select>
          </div>
          <button className="btn btn-primary">Apply</button>
          {rangeError && <div className="field-error">{rangeError}</div>}
        </form>
      )}

      {isAdmin && (
        <>
          <ErrorBox error={salesError} onRetry={retry} />
          {!sales && !salesError && <Spinner label="Loading sales..." />}
          {sales && (
            <>
              <div className="stat-grid">
                <StatCard label="Net revenue" value={formatPrice(sales.totals.net_revenue)} hint="After refunds" />
                <StatCard label="Gross revenue" value={formatPrice(sales.totals.gross_revenue)} />
                <StatCard label="Orders counted" value={sales.totals.orders_counted} hint="Paid orders" />
                <StatCard label="Average order value" value={formatPrice(sales.totals.average_order_value)} />
              </div>
              <div className="card">
                <h2 style={{ marginTop: 0 }}>Revenue by {applied.granularity}</h2>
                <BarChart data={sales.series} valueKey="revenue" labelKey="period" format={formatPrice} />
              </div>
            </>
          )}

          <ErrorBox error={ordersError} onRetry={retry} />
          {orders && (
            <div className="detail">
              <div>
                <div className="stat-grid">
                  <StatCard label="Total orders" value={orders.total_orders} />
                  <StatCard label="Cancellation rate" value={`${orders.cancellations.rate_percent}%`} hint={`${orders.cancellations.count} cancelled`} />
                  <StatCard label="Return rate" value={`${orders.returns.rate_percent}%`} hint={`${orders.returns.requests} return requests`} />
                  <StatCard label="Refunded for returns" value={formatPrice(orders.returns.refunded_amount)} />
                </div>
              </div>
              <div className="card">
                <h2 style={{ marginTop: 0 }}>Orders by status</h2>
                {Object.entries(orders.by_status).map(([status, n]) => (
                  <div className="status-bar" key={status}>
                    <span>{status}</span>
                    <div className="bar">
                      <div className="bar-fill" style={{ width: `${orders.total_orders ? (n / orders.total_orders) * 100 : 0}%` }} />
                    </div>
                    <span className="small muted">{n}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <h2>Stock alerts</h2>
      <ErrorBox error={inventoryError} onRetry={retry} />
      {!inventory && !inventoryError && <Spinner label="Loading stock alerts..." />}
      {inventory && (
        <div className="card">
          <div className="stat-grid" style={{ marginBottom: 8 }}>
            <StatCard label="Out of stock" value={inventory.counts.out_of_stock} />
            <StatCard label="Low stock" value={inventory.counts.low_stock} />
          </div>
          {[...inventory.out_of_stock, ...inventory.low_stock].slice(0, 5).map((p) => (
            <div className="row-between" key={p.product_id} style={{ padding: "4px 0" }}>
              <span>{p.name}</span>
              <span className={p.quantity_available <= 0 ? "field-error" : "muted"}>
                {p.quantity_available <= 0 ? "Out of stock" : `${p.quantity_available} left`}
              </span>
            </div>
          ))}
          {inventory.counts.out_of_stock + inventory.counts.low_stock === 0 && <p className="muted">All products are well stocked.</p>}
          <Link to="/admin/inventory">Manage inventory</Link>
        </div>
      )}
    </div>
  );
}