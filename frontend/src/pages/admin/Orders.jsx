import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api.js";
import { EmptyState, ErrorBox, Pagination, Spinner, StatusBadge, formatDate, formatPrice } from "../../components/ui.jsx";

const PAGE_SIZE = 15;
const STATUSES = ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"];

export default function Orders() {
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [customer, setCustomer] = useState("");
  const [filterError, setFilterError] = useState("");
  const [applied, setApplied] = useState({});
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setError(null);
    request("/orders", { params: { ...applied, page, page_size: PAGE_SIZE } })
      .then(setData)
      .catch(setError);
  }, [applied, page, reloadKey]);

  function apply(e) {
    e.preventDefault();
    if (from && to && from > to) return setFilterError("The start date cannot be after the end date.");
    if (customer && (!/^\d+$/.test(customer) || Number(customer) < 1)) return setFilterError("The customer number must be a positive whole number.");
    setFilterError("");
    setPage(1);
    setApplied({ status, date_from: from, date_to: to, user_id: customer });
  }

  function clear() {
    setStatus("");
    setFrom("");
    setTo("");
    setCustomer("");
    setFilterError("");
    setPage(1);
    setApplied({});
  }

  return (
    <div>
      <h1>Orders</h1>
      <form className="filters-row" onSubmit={apply} noValidate>
        <div>
          <label htmlFor="o-status">Status</label>
          <select id="o-status" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="o-from">From</label>
          <input id="o-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div>
          <label htmlFor="o-to">To</label>
          <input id="o-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <div>
          <label htmlFor="o-customer">Customer number</label>
          <input id="o-customer" value={customer} onChange={(e) => setCustomer(e.target.value)} />
        </div>
        <button className="btn btn-primary">Filter</button>
        <button type="button" className="btn btn-secondary" onClick={clear}>Clear</button>
      </form>
      {filterError && <div className="field-error">{filterError}</div>}

      <ErrorBox error={error} onRetry={() => setReloadKey((k) => k + 1)} />
      {!data && !error && <Spinner label="Loading orders..." />}
      {data && data.items.length === 0 && <EmptyState title="No orders found">Try changing the filters.</EmptyState>}
      {data && data.items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Order</th><th>Date</th><th>Items</th><th>Total</th><th>Status</th><th>Payment</th></tr>
            </thead>
            <tbody>
              {data.items.map((o) => (
                <tr key={o.id}>
                  <td><Link to={`/admin/orders/${o.id}`}>{o.order_number}</Link></td>
                  <td>{formatDate(o.created_at)}</td>
                  <td>{o.item_count}</td>
                  <td>{formatPrice(o.total_amount)}</td>
                  <td><StatusBadge status={o.status} /></td>
                  <td><StatusBadge status={o.payment_status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />}
    </div>
  );
}