import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../api.js";
import { ErrorBox, Spinner, Steps, StatusBadge, formatDate, formatPrice } from "../components/ui.jsx";

const STEPS = [
  ["requested", "Requested"],
  ["approved", "Approved"],
  ["received", "Received"],
  ["accepted", "Inspected"],
  ["refunded", "Refunded"],
];
const ENDINGS = [
  ["rejected", "Rejected"],
  ["declined", "Declined"],
];
const REASON_LABEL = {
  damaged: "Arrived damaged",
  defective: "Defective",
  wrong_item: "Wrong item",
  not_as_described: "Not as described",
  changed_mind: "Changed my mind",
  other: "Other",
};

export default function ReturnDetail() {
  const { id } = useParams();
  const [ret, setRet] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setError(null);
    return request(`/returns/${id}`).then(setRet).catch(setError);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!ret) return <Spinner label="Loading your return..." />;

  const inspected = ret.items.some((i) => i.accepted_quantity !== null && i.accepted_quantity !== undefined);

  return (
    <div>
      <div className="row-between">
        <h1>Return {ret.return_number}</h1>
        <StatusBadge status={ret.status} />
      </div>
      <p className="muted">
        For order <Link to={`/orders/${ret.order_id}`}>#{ret.order_id}</Link>, requested on {formatDate(ret.created_at)}
      </p>

      <Steps steps={STEPS} history={ret.history} endings={ENDINGS} />

      {ret.refund_status !== "none" && (
        <div className={`alert ${ret.refund_status === "failed" ? "alert-error" : "alert-warn"}`}>
          Refund: <strong>{formatPrice(ret.refund_amount)}</strong> <StatusBadge status={ret.refund_status} />
          {ret.refund_status === "pending" && " It will be processed shortly."}
          {ret.refund_status === "failed" && " Please contact support."}
          {ret.refund_reference && <div className="small muted">Reference: {ret.refund_reference}</div>}
        </div>
      )}

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Product</th>
              <th>Requested</th>
              <th>Reason</th>
              {inspected && <th>Accepted</th>}
            </tr>
          </thead>
          <tbody>
            {ret.items.map((i) => (
              <tr key={i.order_item_id}>
                <td>{i.product_name}</td>
                <td>{i.quantity}</td>
                <td>
                  {REASON_LABEL[i.reason] || i.reason}
                  {i.comment && <div className="small muted">{i.comment}</div>}
                </td>
                {inspected && <td>{i.accepted_quantity ?? "-"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>History</h2>
      <ul className="timeline">
        {[...ret.history].reverse().map((h, index) => (
          <li key={index}>
            <StatusBadge status={h.status} /> <span className="small muted">{formatDate(h.created_at)}</span>
            {h.note && <div>{h.note}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}