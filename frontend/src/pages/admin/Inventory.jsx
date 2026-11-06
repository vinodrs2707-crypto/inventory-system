import { useCallback, useEffect, useMemo, useState } from "react";
import { request } from "../../api.js";
import { useToast } from "../../components/toast.jsx";
import { EmptyState, ErrorBox, Modal, Pagination, Spinner, formatDate } from "../../components/ui.jsx";

const PAGE_SIZE = 15;

async function loadAll(path, auth = true) {
  const items = [];
  for (let page = 1; page <= 20; page += 1) {
    const d = await request(path, { auth, params: { page, page_size: 100 } });
    items.push(...d.items);
    if (d.items.length === 0 || items.length >= d.total) break;
  }
  return items;
}

function StockBadge({ row }) {
  if (row.out_of_stock) return <span className="badge badge-danger">Out of stock</span>;
  if (row.low_stock) return <span className="badge badge-warn">Low stock</span>;
  return <span className="badge badge-ok">OK</span>;
}

function AdjustModal({ row, name, onClose, onSaved }) {
  const toast = useToast();
  const [action, setAction] = useState("add");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    const q = Number(quantity);
    const next = {};
    if (quantity === "" || !Number.isInteger(q) || q < 0 || q > 1000000) next.quantity = "Enter a whole number.";
    else if (action !== "set" && q < 1) next.quantity = "Enter at least 1.";
    if (reason.trim().length < 3) next.reason = "Please give a reason (at least 3 characters).";
    setErrors(next);
    if (Object.keys(next).length) return;
    setBusy(true);
    try {
      await request(`/inventory/${row.product_id}/stock`, { method: "PATCH", body: { action, quantity: q, reason: reason.trim() } });
      toast.success("Stock updated.");
      onSaved();
    } catch (err) {
      setErrors({ form: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Adjust stock: ${name}`} onClose={busy ? () => {} : onClose}>
      <p className="muted">
        On hand: <strong>{row.quantity_on_hand}</strong> · Reserved for orders: <strong>{row.quantity_reserved}</strong> · Available: <strong>{row.quantity_available}</strong>
      </p>
      <form onSubmit={submit} noValidate>
        {errors.form && <div className="alert alert-error" role="alert">{errors.form}</div>}
        <label htmlFor="action">What do you want to do?</label>
        <select id="action" value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="add">Add stock (new delivery)</option>
          <option value="deduct">Remove stock (damage, loss)</option>
          <option value="set">Set the exact count (stock take)</option>
        </select>
        <label htmlFor="quantity">{action === "set" ? "New on-hand count" : "Quantity"}</label>
        <input id="quantity" type="number" min="0" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        {errors.quantity && <div className="field-error">{errors.quantity}</div>}
        <label htmlFor="reason">Reason</label>
        <input id="reason" value={reason} maxLength={255} onChange={(e) => setReason(e.target.value)} />
        {errors.reason && <div className="field-error">{errors.reason}</div>}
        <div className="row-end">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Update stock"}</button>
        </div>
      </form>
    </Modal>
  );
}

function ThresholdModal({ row, name, onClose, onSaved }) {
  const toast = useToast();
  const [value, setValue] = useState(String(row.low_stock_threshold));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    const n = Number(value);
    if (value === "" || !Number.isInteger(n) || n < 0 || n > 1000000) return setError("Enter a whole number (0 or more).");
    setBusy(true);
    try {
      await request(`/inventory/${row.product_id}/threshold`, { method: "PATCH", body: { low_stock_threshold: n } });
      toast.success("Alert level updated.");
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Alert level: ${name}`} onClose={busy ? () => {} : onClose}>
      <form onSubmit={submit} noValidate>
        <p className="muted">You get a low-stock alert when the available stock drops to this number.</p>
        <label htmlFor="threshold">Alert level</label>
        <input id="threshold" type="number" min="0" value={value} onChange={(e) => setValue(e.target.value)} />
        {error && <div className="field-error">{error}</div>}
        <div className="row-end">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}

function HistoryModal({ row, name, onClose }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setError(null);
    request(`/inventory/${row.product_id}/transactions`, { params: { page, page_size: 10 } })
      .then(setData)
      .catch(setError);
  }, [row.product_id, page]);

  return (
    <Modal title={`Stock history: ${name}`} onClose={onClose} wide>
      <ErrorBox error={error} />
      {!data && !error && <Spinner />}
      {data && data.items.length === 0 && <EmptyState title="No movements yet" />}
      {data && data.items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>When</th><th>Type</th><th>On hand</th><th>Reserved</th><th>Reason</th><th>Reference</th></tr>
            </thead>
            <tbody>
              {data.items.map((t) => (
                <tr key={t.id}>
                  <td>{formatDate(t.created_at)}</td>
                  <td>{t.change_type}</td>
                  <td>{t.on_hand_change > 0 ? `+${t.on_hand_change}` : t.on_hand_change} → {t.on_hand_after}</td>
                  <td>{t.reserved_change > 0 ? `+${t.reserved_change}` : t.reserved_change} → {t.reserved_after}</td>
                  <td>{t.reason}</td>
                  <td className="small muted">{t.reference || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={page} pageSize={10} total={data.total} onChange={setPage} />}
    </Modal>
  );
}

function CreateModal({ product, onClose, onSaved }) {
  const toast = useToast();
  const [quantity, setQuantity] = useState("0");
  const [threshold, setThreshold] = useState("10");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    const q = Number(quantity);
    const t = Number(threshold);
    if (!Number.isInteger(q) || q < 0 || q > 1000000) return setError("Enter the starting stock as a whole number (0 or more).");
    if (!Number.isInteger(t) || t < 0 || t > 1000000) return setError("Enter the alert level as a whole number (0 or more).");
    setBusy(true);
    try {
      await request("/inventory", { method: "POST", body: { product_id: product.id, quantity: q, low_stock_threshold: t } });
      toast.success("Stock record created.");
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Start tracking stock: ${product.name}`} onClose={busy ? () => {} : onClose}>
      <form onSubmit={submit} noValidate>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <label htmlFor="start">Starting stock</label>
        <input id="start" type="number" min="0" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        <label htmlFor="alert">Low-stock alert level</label>
        <input id="alert" type="number" min="0" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
        <div className="row-end">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Create"}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function Inventory() {
  const [products, setProducts] = useState([]);
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [adjust, setAdjust] = useState(null);
  const [threshold, setThreshold] = useState(null);
  const [history, setHistory] = useState(null);
  const [create, setCreate] = useState(null);

  const load = useCallback(() => {
    setError(null);
    return Promise.all([loadAll("/products", false), loadAll("/inventory")])
      .then(([p, inv]) => {
        setProducts(p);
        setRows(inv);
      })
      .catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const names = useMemo(() => Object.fromEntries(products.map((p) => [p.id, p.name])), [products]);
  const tracked = useMemo(() => new Set((rows || []).map((r) => r.product_id)), [rows]);
  const missing = products.filter((p) => !tracked.has(p.id));
  const nameOf = (id) => names[id] || `Product #${id}`;

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (rows || [])
      .filter((r) => {
        if (q && !nameOf(r.product_id).toLowerCase().includes(q) && String(r.product_id) !== q) return false;
        if (filter === "low") return r.low_stock && !r.out_of_stock;
        if (filter === "out") return r.out_of_stock;
        return true;
      })
      .sort((a, b) => a.product_id - b.product_id);
  }, [rows, names, search, filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const saved = () => {
    setAdjust(null);
    setThreshold(null);
    setCreate(null);
    load();
  };

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!rows) return <Spinner label="Loading inventory..." />;

  return (
    <div>
      <h1>Inventory</h1>

      {missing.length > 0 && (
        <div className="alert alert-warn">
          <strong>{missing.length} product(s) have no stock record</strong>, so customers cannot buy them yet.
          {missing.map((p) => (
            <div className="row-between" key={p.id} style={{ marginTop: 6 }}>
              <span>{p.name}</span>
              <button className="btn btn-primary btn-small" onClick={() => setCreate(p)}>Create stock record</button>
            </div>
          ))}
        </div>
      )}

      <div className="filters-row">
        <div>
          <label htmlFor="inv-search">Search</label>
          <input id="inv-search" value={search} placeholder="Product name or ID" onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        </div>
        <div>
          <label htmlFor="inv-filter">Show</label>
          <select id="inv-filter" value={filter} onChange={(e) => { setFilter(e.target.value); setPage(1); }}>
            <option value="all">All products</option>
            <option value="low">Low stock</option>
            <option value="out">Out of stock</option>
          </select>
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState title="Nothing to show">No stock records match these filters.</EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Product</th><th>On hand</th><th>Reserved</th><th>Available</th><th>Alert level</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {pageRows.map((r) => (
                <tr key={r.product_id}>
                  <td>{nameOf(r.product_id)} <span className="small muted">#{r.product_id}</span></td>
                  <td>{r.quantity_on_hand}</td>
                  <td>{r.quantity_reserved}</td>
                  <td><strong>{r.quantity_available}</strong></td>
                  <td>{r.low_stock_threshold}</td>
                  <td><StockBadge row={r} /></td>
                  <td>
                    <div className="actions">
                      <button className="btn btn-primary btn-small" onClick={() => setAdjust(r)}>Adjust</button>
                      <button className="btn btn-secondary btn-small" onClick={() => setThreshold(r)}>Alert level</button>
                      <button className="btn btn-secondary btn-small" onClick={() => setHistory(r)}>History</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} pageSize={PAGE_SIZE} total={filtered.length} onChange={setPage} />

      {adjust && <AdjustModal row={adjust} name={nameOf(adjust.product_id)} onClose={() => setAdjust(null)} onSaved={saved} />}
      {threshold && <ThresholdModal row={threshold} name={nameOf(threshold.product_id)} onClose={() => setThreshold(null)} onSaved={saved} />}
      {history && <HistoryModal row={history} name={nameOf(history.product_id)} onClose={() => setHistory(null)} />}
      {create && <CreateModal product={create} onClose={() => setCreate(null)} onSaved={saved} />}
    </div>
  );
}