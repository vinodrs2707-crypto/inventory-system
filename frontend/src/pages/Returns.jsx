import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api.js";
import { EmptyState, ErrorBox, Pagination, Spinner, StatusBadge, formatDate, formatPrice } from "../components/ui.jsx";

const PAGE_SIZE = 10;

export default function Returns() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setError(null);
    request("/returns/my-returns", { params: { page, page_size: PAGE_SIZE } })
      .then(setData)
      .catch(setError);
  }, [page, reloadKey]);

  if (error) return <ErrorBox error={error} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!data) return <Spinner label="Loading your returns..." />;
  if (data.items.length === 0) {
    return (
      <EmptyState title="You have not requested any returns">
        Open a delivered order and choose <strong>Request a return</strong>. <Link to="/orders">Go to your orders</Link>
      </EmptyState>
    );
  }

  return (
    <div>
      <h1>Your returns</h1>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Return</th>
              <th>Requested</th>
              <th>Items</th>
              <th>Status</th>
              <th>Refund</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.id}>
                <td><Link to={`/returns/${r.id}`}>{r.return_number}</Link></td>
                <td>{formatDate(r.created_at)}</td>
                <td>{r.item_count}</td>
                <td><StatusBadge status={r.status} /></td>
                <td>
                  {r.refund_status === "none" ? "-" : (
                    <>
                      {formatPrice(r.refund_amount)} <StatusBadge status={r.refund_status} />
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
    </div>
  );
}