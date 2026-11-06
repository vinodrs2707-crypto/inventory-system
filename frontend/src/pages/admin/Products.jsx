import { useEffect, useState } from "react";
import { request } from "../../api.js";
import { useToast } from "../../components/toast.jsx";
import { ConfirmDialog, EmptyState, ErrorBox, Modal, Pagination, Spinner, formatPrice } from "../../components/ui.jsx";
import ProductForm from "./ProductForm.jsx";

const PAGE_SIZE = 10;

function downloadSample() {
  const text =
    "name,description,category,brand,price,image_url,specifications\n" +
    "Wireless Mouse,Ergonomic 2.4GHz wireless mouse,Electronics,Logitech,799,,Color:Black;Battery:AA\n" +
    "Running Shoes,Lightweight shoes for daily running,Footwear,Nike,3499,,Size:9;Color:Blue\n";
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "sample_products.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function ImportModal({ onClose, onDone }) {
  const toast = useToast();
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  function pick(e) {
    const chosen = e.target.files[0];
    setResult(null);
    setFile(null);
    if (!chosen) return;
    if (!chosen.name.toLowerCase().endsWith(".csv")) return setError("Please choose a .csv file.");
    if (chosen.size > 1000000) return setError("The file is too large (maximum 1 MB).");
    setError("");
    setFile(chosen);
  }

  async function upload() {
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    setError("");
    try {
      const data = await request("/products/bulk-import", { method: "POST", body: form });
      setResult(data);
      toast.success(`${data.created} product(s) imported.`);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Import products from CSV" onClose={busy ? () => {} : onClose} wide>
      <p className="muted">
        The file needs these columns: name, description, category, brand, price. Optional: image_url, specifications (like <code>Color:Black;Battery:AA</code>).{" "}
        <button type="button" className="btn btn-secondary btn-small" onClick={downloadSample}>Download a sample file</button>
      </p>
      <input type="file" accept=".csv,text/csv" onChange={pick} aria-label="CSV file" />
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {result && (
        <div className="alert alert-warn">
          <strong>{result.created}</strong> created, <strong>{result.skipped}</strong> skipped (already exist).
          {result.errors.length > 0 && (
            <>
              <div>Problems found:</div>
              <ul>{result.errors.map((m, i) => <li key={i}>{m}</li>)}</ul>
            </>
          )}
        </div>
      )}
      <div className="row-end">
        <button className="btn btn-secondary" onClick={onClose} disabled={busy}>Close</button>
        <button className="btn btn-primary" onClick={upload} disabled={!file || busy}>{busy ? "Importing..." : "Import"}</button>
      </div>
    </Modal>
  );
}

export default function Products() {
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [categories, setCategories] = useState([]);
  const [editing, setEditing] = useState(null); // "new" or a product
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setError(null);
    request("/products", { auth: false, params: { search: query, page, page_size: PAGE_SIZE, sort_by: "newest", order: "desc" } })
      .then(setData)
      .catch(setError);
  }, [query, page, reloadKey]);

  useEffect(() => {
    request("/categories", { auth: false }).then(setCategories).catch(() => {});
  }, [reloadKey]);

  const reload = () => setReloadKey((k) => k + 1);

  async function confirmDelete() {
    setBusy(true);
    try {
      await request(`/products/${deleting.id}`, { method: "DELETE" });
      toast.success("Product deleted.");
      setDeleting(null);
      reload();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="row-between">
        <h1>Products</h1>
        <div className="actions">
          <button className="btn btn-secondary" onClick={() => setImportOpen(true)}>Import CSV</button>
          <button className="btn btn-primary" onClick={() => setEditing("new")}>New product</button>
        </div>
      </div>

      <input type="search" placeholder="Search products" aria-label="Search products" value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 360, marginBottom: 12 }} />

      <ErrorBox error={error} onRetry={reload} />
      {!data && !error && <Spinner label="Loading products..." />}
      {data && data.items.length === 0 && <EmptyState title="No products found">{query ? "Try another search." : "Create your first product."}</EmptyState>}
      {data && data.items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th><th>Name</th><th>Category</th><th>Brand</th><th>Price</th><th>Stock</th><th>Rating</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{p.name}</td>
                  <td>{p.category}</td>
                  <td>{p.brand}</td>
                  <td>{formatPrice(p.price)}</td>
                  <td>{p.in_stock ? p.stock_quantity : <span className="badge badge-danger">Out</span>}</td>
                  <td>{p.rating_count ? `${p.rating_average.toFixed(1)} (${p.rating_count})` : "-"}</td>
                  <td>
                    <div className="actions">
                      <button className="btn btn-secondary btn-small" onClick={() => setEditing(p)}>Edit</button>
                      <button className="btn btn-danger btn-small" onClick={() => setDeleting(p)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />}
      <p className="small muted">Stock numbers come from the Inventory page and can take a few seconds to update here.</p>

      {editing && (
        <ProductForm
          product={editing === "new" ? null : editing}
          categories={categories}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
      {importOpen && <ImportModal onClose={() => setImportOpen(false)} onDone={reload} />}
      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete this product?"
        message={deleting ? `"${deleting.name}" will disappear from the shop. Past orders keep their record of it.` : ""}
        confirmLabel="Delete"
        danger
        busy={busy}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}