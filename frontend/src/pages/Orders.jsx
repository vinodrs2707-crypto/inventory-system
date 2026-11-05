import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api.js";
import { EmptyState, ErrorBox, Pagination, Spinner, StatusBadge, formatDate, formatPrice } from "../components/ui.jsx";

const PAGE_SIZE = 10;

export default function Orders() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setError(null);
    request("/orders/my-orders", { params: { page, page_size: PAGE_SIZE } })
      .then(setData)
      .catch(setError);
  }, [page, reloadKey]);

  if (error) return <ErrorBox error={error} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!data) return <Spinner label="Loading your orders..." />;
  if (data.items.length === 0) {
    return (
      <EmptyState title="You have not placed any orders yet">
        <Link to="/" className="btn btn-primary">Start shopping</Link>
      </EmptyState>
    );
  }

  return (
    <div>
      <h1>Your orders</h1>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Order</th>
              <th>Date</th>
              <th>Items</th>
              <th>Total</th>
              <th>Status</th>
              <th>Payment</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((o) => (
              <tr key={o.id}>
                <td><Link to={`/orders/${o.id}`}>{o.order_number}</Link></td>
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
      <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
    </div>
  );
}